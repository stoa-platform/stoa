"""Local Helm render contracts for the opt-in companion example."""

import sys
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "security"))
from helm_contract_support import CHART, render

EXAMPLE = CHART / "examples/companion-nginx.yaml"


class CompanionRenderTests(unittest.TestCase):
    def manifests(self, *args):
        result = render(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return [item for item in yaml.safe_load_all(result.stdout) if item]

    def test_off_by_default(self):
        objects = self.manifests()
        self.assertFalse(any("sidecar" in o["metadata"]["name"] for o in objects))

    def test_example_colocation_and_wiring(self):
        objects = self.manifests("-f", str(EXAMPLE))
        deployment = next(o for o in objects if o["kind"] == "Deployment" and
                          o["metadata"]["name"] == "nginx-with-stoa-sidecar")
        pod = deployment["spec"]["template"]["spec"]
        host, companion = pod["containers"]
        self.assertEqual([host["name"], companion["name"]], ["nginx", "stoa-sidecar"])
        env = {item["name"]: item.get("value") for item in companion["env"]}
        self.assertEqual(env["STOA_GATEWAY_MODE"], "sidecar")
        self.assertEqual(env["STOA_PORT"], "8081")
        self.assertIn({"name": "companion-auth", "secret": {"secretName": "companion-basic-auth"}},
                      pod["volumes"])
        self.assertTrue(any(m["mountPath"] == "/etc/nginx/conf.d/default.conf" and m["readOnly"]
                            for m in host["volumeMounts"]))
        config = next(o for o in objects if o["kind"] == "ConfigMap" and
                      o["metadata"]["name"] == "nginx-companion-config")["data"]["default.conf"]
        for required in ('auth_basic_user_file /etc/companion-auth/htpasswd;',
                         'ngx.var.remote_user', 'cjson.encode', 'ngx.HTTP_POST',
                         'http://127.0.0.1:8081/authz', 'internal;',
                         'response.status ~= 200',
                         'proxy_set_header Authorization "";'):
            self.assertIn(required, config)
        self.assertNotIn('satisfy any', config)
        self.assertNotIn('error_page', config)
        self.assertFalse(any(o["kind"] == "Secret" and
                             o["metadata"]["name"] == "companion-basic-auth" for o in objects))

    def test_images_are_pinned(self):
        for arguments in ((), ("-f", str(EXAMPLE))):
            objects = self.manifests(*arguments)
            for obj in objects:
                if obj["kind"] != "Deployment":
                    continue
                for container in obj["spec"]["template"]["spec"]["containers"]:
                    self.assertRegex(container["image"], r"@sha256:[0-9a-f]{64}$")
                    self.assertEqual(container["imagePullPolicy"], "IfNotPresent")

    def test_companion_requires_valid_image_digests(self):
        for image in ("stoaSidecar.image", "stoaSidecar.mainGateway.image"):
            for digest in ("", "sha256:invalid"):
                result = render("-f", str(EXAMPLE), "--set", f"{image}.digest={digest}")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("digest", result.stderr)

    def test_example_requires_auth_secret_and_tenant(self):
        for setting in ("authSecret", "tenantId"):
            result = render("-f", str(EXAMPLE), "--set", f"stoaSidecar.nginxExample.{setting}=")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(setting, result.stderr)

    def test_example_rejects_unsafe_config(self):
        for setting in ("tenantId=tenant;invalid", "backendUrl=http://backend/path"):
            result = render("-f", str(EXAMPLE), "--set", f"stoaSidecar.nginxExample.{setting}")
            self.assertNotEqual(result.returncode, 0)

    def test_example_cannot_be_enabled_without_companion(self):
        result = render("-f", str(EXAMPLE), "--set", "stoaSidecar.enabled=false")
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
