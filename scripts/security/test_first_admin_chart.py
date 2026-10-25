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
