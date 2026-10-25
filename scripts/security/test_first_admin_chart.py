"""Static chart contracts; render checks are run separately with Helm."""

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


class BootstrapChartTests(unittest.TestCase):
    def test_bootstrap_only_accepts_an_existing_secret(self):
        source = (ROOT / "charts/stoa-platform/templates/bootstrap-job.yaml").read_text()
        values = yaml.safe_load((ROOT / "charts/stoa-platform/values.yaml").read_text())
        credentials = values["stoa"]["bootstrap"]["keycloak"]
        self.assertNotIn("adminPassword", credentials)
        self.assertEqual("", credentials["existingSecret"])
        self.assertIn('required "stoa.bootstrap.keycloak.existingSecret is required', source)
        self.assertIn('fail "Inline bootstrap admin passwords are unsupported', source)
        password_env = source.split("- name: KC_ADMIN_PASSWORD", 1)[1].split("volumeMounts:", 1)[0]
        self.assertNotIn("value:", password_env)
        self.assertNotIn("optional: true", password_env)
        self.assertIn("readOnlyRootFilesystem: true", source)
        self.assertFalse(values["stoa"]["bootstrap"]["adminServiceAccount"]["enabled"])
        self.assertIn("if .Values.stoa.bootstrap.adminServiceAccount.enabled", source)
        self.assertIn("docs/runbooks/first-admin-bootstrap.md", source)


class FirstAdminChartTests(unittest.TestCase):
    def test_first_admin_is_disabled_and_requires_existing_secret(self):
        values = yaml.safe_load((ROOT / "charts/stoa-platform/values.yaml").read_text())
        config = values["stoa"]["bootstrap"]["firstAdmin"]
        self.assertFalse(config["enabled"])
        self.assertEqual("", config["existingSecret"])
        source = (ROOT / "charts/stoa-platform/templates/first-admin-job.yaml").read_text()
        self.assertTrue(source.startswith("{{- if .Values.stoa.bootstrap.firstAdmin.enabled }}"))
        self.assertIn('required "stoa.bootstrap.firstAdmin.existingSecret is required', source)
        self.assertIn("files/first_admin/*.py", source)
        for setting in (
            "readOnlyRootFilesystem: true",
            "runAsNonRoot: true",
            "allowPrivilegeEscalation: false",
            "type: RuntimeDefault",
            "automountServiceAccountToken: false",
            "drop: [ALL]",
        ):
            self.assertIn(setting, source)
        self.assertNotIn("latest", config["image"])

    def test_first_admin_egress_only_keycloak_and_dns(self):
        from test_bootstrap_draft import allows_egress

        source = (
            ROOT / "charts/stoa-platform/templates/first-admin-networkpolicy.yaml"
        ).read_text()
        body = source[source.index("apiVersion:") : source.rindex("{{- end }}")]
        policy = yaml.safe_load(body.replace("{{ .Release.Namespace }}", "stoa-system"))
        self.assertTrue(allows_egress(policy, {"app": "keycloak"}, "stoa-system", 8080))
        self.assertFalse(allows_egress(policy, {"app": "keycloak"}, "other", 8080))
        self.assertFalse(allows_egress(policy, {"app": "unrelated"}, "stoa-system", 8080))
        self.assertFalse(
            allows_egress(policy, {"app": "stoa-control-plane-api"}, "stoa-system", 80)
        )
        for protocol in ("UDP", "TCP"):
            self.assertTrue(
                allows_egress(policy, {"k8s-app": "kube-dns"}, "kube-system", 53, protocol)
            )
