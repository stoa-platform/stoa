"""Shared parameter render contracts: python3 -m unittest discover -s charts/stoa-platform/tests -v."""
import pathlib
import subprocess
import unittest

import yaml

CHART = pathlib.Path(__file__).resolve().parents[1]
EXAMPLE = CHART / "examples/companion-nginx.yaml"
OVERLAYS = ("dev", "staging", "prod")
# Enables every environment and identity consumer; Secret names are references only.
CONSUMERS = [
    "-f", str(EXAMPLE),
    "--set", "stoaSidecar.serviceMonitor.enabled=true",
    "--set", "stoa.bootstrap.enabled=true",
    "--set", "stoa.bootstrap.keycloak.existingSecret=bootstrap-ref",
    "--set", "stoa.bootstrap.firstAdmin.enabled=true",
    "--set", "stoa.bootstrap.firstAdmin.existingSecret=first-admin-ref",
]


def render(*args, namespace="stoa-system"):
    command = ["helm", "template", "params-test", str(CHART), "--namespace", namespace, *args]
    return [doc for doc in yaml.safe_load_all(subprocess.check_output(command, text=True)) if doc]


def find(objects, kind, name):
    matches = [o for o in objects if o["kind"] == kind and o["metadata"]["name"] == name]
    return matches[0] if matches else None


def env_of(objects, kind, name, container):
    spec = find(objects, kind, name)["spec"]["template"]["spec"]
    c, = [c for c in spec["containers"] if c["name"] == container]
    return {e["name"]: e.get("value") for e in c.get("env", [])}


def script_vars(objects):
    script = find(objects, "ConfigMap", "stoa-bootstrap-script")["data"]["bootstrap.sh"]
    return dict(line.strip().split("=", 1) for line in script.splitlines()
                if line.strip().startswith(("KEYCLOAK_URL=", "REALM=")))


def environment_labels(objects):
    labels = {
        "gateway-env": env_of(objects, "Deployment", "stoa-gateway", "stoa-gateway")["STOA_ENVIRONMENT"],
        "sidecar-env": env_of(objects, "Deployment", "nginx-with-stoa-sidecar", "stoa-sidecar")["STOA_ENVIRONMENT"],
    }
    for name in ("stoa-gateway", "nginx-stoa-sidecar", "stoa-control-plane-api"):
        relabels = find(objects, "ServiceMonitor", name)["spec"]["endpoints"][0]["metricRelabelings"]
        labels[name], = [r["replacement"] for r in relabels if r.get("targetLabel") == "environment"]
    return labels


def keycloak_ports(policy):
    rule, = [r for r in policy["spec"]["egress"]
             if {"app": "keycloak"} in [p.get("podSelector", {}).get("matchLabels") for p in r["to"]]]
    return sorted(p["port"] for p in rule["ports"])


class EnvironmentTests(unittest.TestCase):
    def test_every_consumer_inherits_global_environment(self):
        labels = environment_labels(render(*CONSUMERS, "--set", "global.environment=qa"))
        self.assertEqual(set(labels.values()), {"qa"}, labels)

    def test_default_environment_is_dev(self):
        self.assertEqual(set(environment_labels(render(*CONSUMERS)).values()), {"dev"})

    def test_component_override_wins_for_that_component_only(self):
        labels = environment_labels(render(*CONSUMERS, "--set", "global.environment=qa",
                                           "--set", "stoaSidecar.environment=edge"))
        self.assertEqual(labels.pop("sidecar-env"), "edge")
        self.assertEqual(labels.pop("nginx-stoa-sidecar"), "edge")
        self.assertEqual(set(labels.values()), {"qa"}, labels)

    def test_overlays_label_every_consumer_with_their_environment(self):
        for overlay in OVERLAYS:
            path = CHART / f"values-{overlay}.yaml"
            values = yaml.safe_load(path.read_text())
            with self.subTest(overlay=overlay):
                for component in ("stoaGateway", "stoaSidecar", "controlPlaneApi"):
                    self.assertNotIn("environment", values.get(component) or {})
                labels = environment_labels(render("-f", str(path), *CONSUMERS))
                self.assertEqual(set(labels.values()), {values["global"]["environment"]}, labels)


class IdentityTests(unittest.TestCase):
    def test_default_identity_parameters(self):
        objects = render(*CONSUMERS, namespace="identity-ns")
        internal = "http://keycloak-http.identity-ns.svc.cluster.local:80"
        self.assertEqual(script_vars(objects), {"KEYCLOAK_URL": f'"{internal}"', "REALM": '"stoa"'})
        first_admin = env_of(objects, "Job", "stoa-first-admin", "first-admin")
        self.assertEqual((first_admin["KEYCLOAK_URL"], first_admin["KEYCLOAK_REALM"]), (internal, "stoa"))
        for name, container in (("stoa-gateway", "stoa-gateway"),
                                ("nginx-with-stoa-sidecar", "stoa-sidecar")):
            self.assertEqual(env_of(objects, "Deployment", name, container)["STOA_KEYCLOAK_REALM"], "stoa")

    def test_shared_realm_and_internal_url_reach_every_consumer(self):
        url = "https://identity.internal.test"
        objects = render(*CONSUMERS, "--set", "keycloak.realm=sentinel-realm",
                         "--set", f"keycloak.internalUrl={url}")
        self.assertEqual(script_vars(objects), {"KEYCLOAK_URL": f'"{url}"', "REALM": '"sentinel-realm"'})
        first_admin = env_of(objects, "Job", "stoa-first-admin", "first-admin")
        self.assertEqual((first_admin["KEYCLOAK_URL"], first_admin["KEYCLOAK_REALM"]),
                         (url, "sentinel-realm"))
        for name, container in (("stoa-gateway", "stoa-gateway"),
                                ("nginx-with-stoa-sidecar", "stoa-sidecar")):
            env = env_of(objects, "Deployment", name, container)
            self.assertEqual(env["STOA_KEYCLOAK_REALM"], "sentinel-realm")

    def test_bootstrap_does_not_borrow_gateway_identity_values(self):
        objects = render(*CONSUMERS, "--set", "stoaGateway.keycloakRealm=gateway-only",
                         "--set", "stoaGateway.keycloakUrl=https://gateway-only.test")
        self.assertEqual(script_vars(objects)["REALM"], '"stoa"')
        self.assertEqual(env_of(objects, "Job", "stoa-first-admin", "first-admin")["KEYCLOAK_REALM"], "stoa")
        gateway = env_of(objects, "Deployment", "stoa-gateway", "stoa-gateway")
        self.assertEqual(gateway["STOA_KEYCLOAK_REALM"], "gateway-only")

    def test_first_admin_url_override_is_job_scoped(self):
        objects = render(*CONSUMERS, "--set", "keycloak.internalUrl=https://shared.test",
                         "--set", "stoa.bootstrap.firstAdmin.keycloakUrl=https://first-admin.test")
        self.assertEqual(script_vars(objects)["KEYCLOAK_URL"], '"https://shared.test"')
        self.assertEqual(env_of(objects, "Job", "stoa-first-admin", "first-admin")["KEYCLOAK_URL"],
                         "https://first-admin.test")

    def test_operator_managed_realm_skips_realm_bootstrap_only(self):
        objects = render(*CONSUMERS, "--set", "keycloak.operator.enabled=true")
        self.assertIsNone(find(objects, "Job", "stoa-bootstrap"))
        self.assertIsNone(find(objects, "NetworkPolicy", "stoa-bootstrap-egress"))
        self.assertIsNotNone(find(objects, "Job", "stoa-first-admin"))

    def test_bootstrap_jobs_share_identity_egress_ports(self):
        objects = render(*CONSUMERS)
        self.assertEqual(keycloak_ports(find(objects, "NetworkPolicy", "stoa-bootstrap-egress")),
                         keycloak_ports(find(objects, "NetworkPolicy", "stoa-first-admin-egress")))

    def test_templates_read_identity_parameters_from_one_place(self):
        for path in (CHART / "templates").rglob("*.*"):
            source = path.read_text()
            with self.subTest(template=path.name):
                self.assertNotIn(".Values.AsMap", source)
                if path.name != "stoa-gateway-deployment.yaml":
                    self.assertNotIn("stoaGateway.keycloakRealm", source)
                if path.name != "_helpers.tpl":
                    self.assertNotIn("keycloak-http.", source)
                    self.assertNotIn("/realms/stoa/", source)


if __name__ == "__main__":
    unittest.main()
