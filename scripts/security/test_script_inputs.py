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
