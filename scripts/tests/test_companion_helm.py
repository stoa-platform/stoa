"""Local Helm render contracts for the opt-in companion example."""

import copy
import sys
import tempfile
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
        # Synthetic references exercise local rendering; nothing is pulled or applied.
        release_a = {
            "stoa": {"bootstrap": {
                "enabled": True,
                "keycloak": {"existingSecret": "existing-bootstrap"},
                "defaultTenant": {"name": "example-tenant"},
            }},
            "stoaGateway": {
                "replicas": 2,
                "controlPlaneUrl": "http://control-plane.example.test:8000",
                "policyBootTenants": ["example-tenant"],
                "routing": {"reloadEnabled": True, "reloadIntervalSecs": 30},
                "federation": {"enabled": True, "upstreamsSecretRef": {
                    "name": "existing-upstreams", "key": "upstreams",
                }},
                "policies": {"enabled": True},
                "secretName": "existing-gateway",
            },
            "stoaSidecar": {
                "policyBootTenants": ["example-tenant"],
                "secretName": "existing-sidecar",
                "mainGateway": {},
            },
            "gatewaySync": {"enabled": True, "schedule": "*/30 * * * *"},
        }
        image_keys = (("stoaGateway", "stoa-gateway"),
                      ("stoaSidecar", "stoa-sidecar"),
                      ("mainGateway", "nginx"))
        release_b = copy.deepcopy(release_a)
        release_b["stoaGateway"].update({
            "replicas": 3,
            "routing": {"reloadEnabled": True, "reloadIntervalSecs": 60},
        })
        release_b["gatewaySync"]["schedule"] = "*/15 * * * *"
        for values, digit in ((release_a, "a"), (release_b, "b")):
            for key, name in image_keys:
                target = (values["stoaSidecar"][key] if key == "mainGateway"
                          else values[key])
                target["image"] = {
                    "repository": "registry.example.test/" + name,
                    "digest": "sha256:" + digit * 64,
                    "pullPolicy": "IfNotPresent",
                }

        def snapshot(values, upgrade):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "release.yaml"
                path.write_text(yaml.safe_dump(values))
                objects = self.manifests(
                    "-f", str(EXAMPLE), "-f", str(path),
                    *(["--is-upgrade"] if upgrade else []),
                )
            containers = {c["name"]: c for c in self.containers(objects)}
            for _, name in image_keys:
                expected = "registry.example.test/" + name + "@sha256:"
                expected += "b" * 64 if values is release_b else "a" * 64
                self.assertEqual(containers[name]["image"], expected)
            for container in containers.values():
                self.assertEqual(container["imagePullPolicy"], "IfNotPresent")

            deployment = next(o for o in objects if o["kind"] == "Deployment"
                              and o["metadata"]["name"] == "stoa-gateway")
            self.assertEqual(deployment["spec"]["replicas"], values["stoaGateway"]["replicas"])
            sync = next(o for o in objects if o["kind"] == "CronJob"
                        and "sync" in o["metadata"]["name"])
            self.assertEqual(sync["spec"]["schedule"], values["gatewaySync"]["schedule"])
            gateway = containers["stoa-gateway"]
            env = {entry["name"]: entry for entry in gateway["env"]}
            self.assertEqual(env["STOA_ROUTE_RELOAD_INTERVAL_SECS"]["value"],
                             str(values["stoaGateway"]["routing"]["reloadIntervalSecs"]))
            # Data remains external: every phase points at the same catalog,
            # tenant and upstream/credential Secrets, with no bootstrap replay.
            self.assertEqual(env["STOA_CONTROL_PLANE_URL"]["value"],
                             release_a["stoaGateway"]["controlPlaneUrl"])
            self.assertEqual(env["STOA_POLICY_BOOT_TENANTS"]["value"], "example-tenant")
            self.assertEqual(env["STOA_FEDERATION_UPSTREAMS"]["valueFrom"]["secretKeyRef"],
                             {"name": "existing-upstreams", "key": "upstreams"})
            self.assertEqual(env["STOA_CONTROL_PLANE_API_KEY"]["valueFrom"]["secretKeyRef"]["name"],
                             "existing-gateway")
            hooks = [o["metadata"].get("annotations", {}).get("helm.sh/hook", "")
                     for o in objects if "bootstrap" in o["metadata"]["name"]]
            self.assertTrue(hooks)
            self.assertEqual(set(hooks), {"post-install"})
            self.assertFalse(any(o["kind"] in {"PersistentVolume", "PersistentVolumeClaim",
                                               "StatefulSet"} for o in objects))
            # Offline Helm lookup cannot read existing Secrets and generates
            # random bytes. Compare their identity/key shape, never their values;
            # this proof does not establish live Secret or database preservation.
            for obj in objects:
                if obj["kind"] == "Secret":
                    obj["data"] = sorted(obj.get("data", {}))
            return objects

        previous = snapshot(release_a, upgrade=False)
        for cycle in range(2):
            with self.subTest(cycle=cycle):
                upgraded = snapshot(release_b, upgrade=True)
                self.assertNotEqual(previous, upgraded)
                self.assertEqual(snapshot(release_a, upgrade=True), previous)

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
