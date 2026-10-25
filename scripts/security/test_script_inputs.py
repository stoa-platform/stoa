"""Input guards terminate before invoking any external program."""

import secrets
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class ScriptInputTests(unittest.TestCase):
    def test_positional_credentials_are_refused_without_echo(self):
        token = secrets.token_urlsafe(32)
        for name in (
            "scripts/setup-keycloak-self-registration.sh",
            "scripts/setup-keycloak-google-idp.sh",
        ):
            run = subprocess.run(
                ["/bin/bash", str(ROOT / name), token],
                env={"PATH": "/nonexistent"},
                capture_output=True,
                text=True,
            )
            self.assertEqual(2, run.returncode, name)
            self.assertIn("Positional credentials are unsupported", run.stderr)
            self.assertNotIn(token, run.stdout + run.stderr)

    def test_terms_url_is_required_before_external_commands(self):
        token = secrets.token_urlsafe(32)
        run = subprocess.run(
            ["/bin/bash", str(ROOT / "scripts/setup-keycloak-self-registration.sh")],
            env={"PATH": "/nonexistent", "KEYCLOAK_ADMIN_PASSWORD": token},
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(0, run.returncode)
        self.assertIn("TERMS_URL is required", run.stderr)
        self.assertNotIn(token, run.stdout + run.stderr)

    def test_additional_positional_interfaces_refuse_credentials(self):
        token = secrets.token_urlsafe(32)
        for name in (
            "deploy/observability/create-keycloak-client.sh",
            "scripts/setup-keycloak-admin-client.sh",
        ):
            run = subprocess.run(
                ["/bin/bash", str(ROOT / name), token],
                env={"PATH": "/nonexistent"},
                capture_output=True,
                text=True,
            )
            self.assertEqual(2, run.returncode, name)
            self.assertNotIn(token, run.stdout + run.stderr)

    def test_reviewed_scripts_use_strict_mode(self):
        names = (
            "deploy/observability/create-keycloak-client.sh",
            "deploy/observability/setup-keycloak-client.sh",
            "scripts/setup-keycloak-admin-client.sh",
            "scripts/setup-keycloak-google-idp.sh",
            "scripts/setup-keycloak-self-registration.sh",
            "scripts/update-keycloak-console-redirect.sh",
            "scripts/demo/setup-rpo-keycloak-users.sh",
            "scripts/setup-e2e-rpo-users.sh",
            "tests/e2e/scripts/setup_test_users.sh",
        )
        for name in names:
            self.assertIn("set -euo pipefail", (ROOT / name).read_text(), name)
