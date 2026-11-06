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

    @staticmethod
    def containers(objects):
        containers = []
        for obj in objects:
            if obj["kind"] not in {"Deployment", "Job", "CronJob", "Pod"}:
                continue
            spec = obj["spec"]
            if obj["kind"] == "CronJob":
                spec = spec["jobTemplate"]["spec"]
            if obj["kind"] != "Pod":
                spec = spec["template"]["spec"]
            containers.extend(spec.get("initContainers", []) + spec["containers"])
        return containers

    def test_all_chart_workloads_default_to_pinned_images_and_cached_pulls(self):
        objects = self.manifests(
            "-f", str(EXAMPLE),
            "--set", "stoaGateway.enabled=true",
            "--set", "gatewaySync.enabled=true",
            "--set", "stoa.bootstrap.enabled=true",
            "--set", "stoa.bootstrap.keycloak.existingSecret=existing-bootstrap",
            "--set", "stoa.bootstrap.firstAdmin.enabled=true",
            "--set", "stoa.bootstrap.firstAdmin.existingSecret=existing-request",
            "--set", "vault.credentialsCheck.enabled=true",
            "--set", "infisical.enabled=true",
        )
        containers = self.containers(objects)
        self.assertTrue({"stoa-gateway", "stoa-sidecar", "bootstrap", "sync", "test"}
                        <= {c["name"] for c in containers})
        for container in containers:
            with self.subTest(container=container["name"]):
                self.assertRegex(container["image"], r"@sha256:[0-9a-f]{64}$")
                self.assertEqual(container.get("imagePullPolicy"), "IfNotPresent")

    def test_release_values_restore_previous_images(self):
        # Synthetic digests exercise rendering only; no image is pulled.
        def release(digit):
            arguments = ["-f", str(EXAMPLE)]
            expected = {}
            for key, name in (("stoaGateway", "stoa-gateway"),
                              ("stoaSidecar", "stoa-sidecar"),
                              ("stoaSidecar.mainGateway", "nginx")):
                repository = "registry.example.test/" + name
                digest = "sha256:" + digit * 64
                arguments += ["--set-string", f"{key}.image.repository={repository}",
                              "--set-string", f"{key}.image.digest={digest}"]
                expected[name] = f"{repository}@{digest}"
            rendered = {c["name"]: c["image"] for c in
                        self.containers(self.manifests(*arguments))}
            self.assertEqual({name: rendered[name] for name in expected}, expected)
            return rendered

        previous = release("a")
        upgraded = release("b")
        self.assertNotEqual(previous, upgraded)
        self.assertEqual(release("a"), previous)

    def test_pull_policy_overrides_are_preserved(self):
        arguments = ["-f", str(EXAMPLE), "--set", "stoa.bootstrap.enabled=true",
                     "--set", "stoa.bootstrap.keycloak.existingSecret=existing-bootstrap"]
        for key in ("stoaGateway.image", "stoaSidecar.image",
                    "stoaSidecar.mainGateway.image", "gatewaySync", "stoa.bootstrap",
                    "testConnection"):
            arguments += ["--set", f"{key}.pullPolicy=Always"]
        for container in self.containers(self.manifests(*arguments)):
            self.assertEqual(container["imagePullPolicy"], "Always")

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
