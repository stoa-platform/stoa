"""Régressions sur les fichiers du brouillon, jamais sur un serveur Keycloak."""

import json
import unittest
from pathlib import Path

import keycloak_audit as kc

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1] if HERE.name == "security" else HERE / "validation"


def load(name):
    return (ROOT / name).read_text()


def allows_egress(policy, dest_labels, dest_namespace, port, protocol="TCP"):
    """Subset of NetworkPolicy used here: peer OR, selector AND, numeric ports."""
    source_namespace = policy["metadata"].get("namespace", "stoa-system")
    for rule in policy["spec"].get("egress", []):
        ports = rule.get("ports", [])
        if ports and not any(
            p.get("port") == port and p.get("protocol", "TCP") == protocol for p in ports
        ):
            continue
        for peer in rule.get("to", []):
            if "ipBlock" in peer:
                continue  # Never infer an IP/label match.
            ns = peer.get("namespaceSelector")
            if ns is None and source_namespace != dest_namespace:
                continue
            if ns is not None and any(
                {"kubernetes.io/metadata.name": dest_namespace}.get(k) != v
                for k, v in ns.get("matchLabels", {}).items()
            ):
                continue
            pod = peer.get("podSelector")
            if pod is None or all(
                dest_labels.get(k) == v for k, v in pod.get("matchLabels", {}).items()
            ):
                return True
    return False


class DraftTests(unittest.TestCase):
    def test_local_import_no_high_findings(self):
        name = "deploy/docker-compose/init/keycloak-realm.json"
        result = kc.Audit()
        result.audit_text(name, load(name))
        self.assertEqual([], [f.rule for f in result.findings if f.severity in {"HIGH", "ERROR"}])

    def test_all_realms_have_closed_registration_and_bounded_sessions(self):
        paths = [
            ROOT / "deploy/docker-compose/init/keycloak-realm.json",
            *sorted((ROOT / "deploy/demo-federation/keycloak").glob("*.json")),
        ]
        self.assertEqual(6, len(paths))
        for p in paths:
            obj = json.loads(p.read_text())
            with self.subTest(file=p.name):
                self.assertIs(obj["registrationAllowed"], False)
                self.assertIs(obj["resetPasswordAllowed"], False)
                self.assertEqual(300, obj["accessTokenLifespan"])
                self.assertEqual(28800, obj["ssoSessionMaxLifespan"])
                self.assertTrue(obj["offlineSessionMaxLifespanEnabled"])

    def test_local_import_is_rejected_as_production(self):
        name = "deploy/docker-compose/init/keycloak-realm.json"
        result = kc.Audit("prod")
        result.audit_text(name, load(name))
        self.assertIn("KC_DEFAULT_USERS", {f.rule for f in result.findings if f.severity == "HIGH"})
        self.assertIn(
            "KC_HARDCODED_SECRET", {f.rule for f in result.findings if f.severity == "HIGH"}
        )

    def test_helm_new_realms_and_browser_clients(self):
        name = "charts/stoa-platform/templates/bootstrap-job.yaml"
        result = kc.Audit()
        source = load(name)
        result.audit_text(name, source)
        self.assertEqual([], [f.rule for f in result.findings if f.severity in {"HIGH", "ERROR"}])
        objects = list(kc.json_objects(source))
        realm = next(o for o, _ in objects if "realm" in o)
        self.assertIn("length(16)", realm["passwordPolicy"])
        clients = [
            o
            for o, _ in objects
            if o.get("publicClient") is True and o.get("standardFlowEnabled") is True
        ]
        self.assertEqual(2, len(clients))
        for client in clients:
            self.assertEqual("S256", client["attributes"]["pkce.code.challenge.method"])
            self.assertTrue(
                all("*" not in uri and "localhost" not in uri for uri in client["redirectUris"])
            )
        self.assertNotIn("Create admin user (if adminEmail provided)", source)

    def test_api_and_gateway_keycloak_peers_are_scoped_and_complete(self):
        policies = list(kc.yaml.safe_load_all(load("k8s/networkpolicy-control-plane.yaml")))
        for policy in policies[:2]:
            for labels in [
                {"app.kubernetes.io/component": "keycloak"},
                {"app.kubernetes.io/name": "keycloak"},
                {"app": "keycloak"},
            ]:
                for port in [80, 8080]:
                    self.assertTrue(allows_egress(policy, labels, "stoa-system", port))
                    self.assertFalse(allows_egress(policy, labels, "unrelated", port))
                    self.assertFalse(allows_egress(policy, labels, "stoa-system", 9000))

    def test_bootstrap_network_policy_does_not_allow_arbitrary_pods(self):
        source = load("charts/stoa-platform/templates/bootstrap-networkpolicy.yaml")
        # Inspect only the static manifest body. This is not a Helm render test.
        body = source[source.index("apiVersion:") : source.rindex("{{- end }}")]
        body = body.replace("{{ .Release.Namespace }}", "stoa-system")
        policy = kc.yaml.safe_load(body)
        self.assertFalse(allows_egress(policy, {"app": "unrelated"}, "stoa-system", 8080))
        self.assertTrue(
            allows_egress(policy, {"app": "stoa-control-plane-api"}, "stoa-system", 8000)
        )
        for protocol in ["UDP", "TCP"]:
            self.assertTrue(
                allows_egress(policy, {"k8s-app": "kube-dns"}, "kube-system", 53, protocol)
            )
            self.assertFalse(
                allows_egress(policy, {"app": "unrelated"}, "kube-system", 53, protocol)
            )

    def test_environment_values_feed_the_domain_consumed_by_bootstrap(self):
        for filename in ["values-dev.yaml", "values-staging.yaml", "values-prod.yaml"]:
            obj = kc.yaml.safe_load(load("charts/stoa-platform/" + filename))
            self.assertEqual(obj["global"]["domain"], obj["stoa"]["domain"])

    def test_realm_import_environment_defaults_are_wired(self):
        defaults = {
            "CONSOLE_ORIGIN": "http://localhost:3000",
            "PORTAL_ORIGIN": "http://localhost:3002",
            "FEDERATION_KEYCLOAK_URL": "http://keycloak:8080",
        }
        compose = kc.yaml.safe_load(load("deploy/docker-compose/docker-compose.yml"))
        environment = compose["services"]["keycloak"]["environment"]
        for name, value in defaults.items():
            self.assertEqual("${" + name + ":-" + value + "}", environment[name])
            self.assertIn(name + "=" + value, load("deploy/docker-compose/.env.example"))
        federation = kc.yaml.safe_load(load("deploy/demo-federation/docker-compose.yml"))
        self.assertEqual(
            environment["FEDERATION_KEYCLOAK_URL"],
            federation["services"]["keycloak"]["environment"]["FEDERATION_KEYCLOAK_URL"],
        )
        for name in (
            "deploy/docker-compose/init/keycloak-realm.json",
            "deploy/demo-federation/keycloak/idp-source-alpha.json",
            "deploy/demo-federation/keycloak/idp-source-beta.json",
        ):
            raw = load(name)
            for parameter, value in defaults.items():
                raw = raw.replace("${" + parameter + "}", value)
            for parameter in defaults:
                self.assertTrue("${" + parameter + "}" not in raw)
            self.assertIsInstance(json.loads(raw), dict)


if __name__ == "__main__":
    unittest.main()
