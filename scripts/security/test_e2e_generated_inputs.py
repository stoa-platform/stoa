"""Verify fixture credentials without starting Docker or contacting a service."""

import os
import secrets
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class GeneratedInputTests(unittest.TestCase):
    def run_prefix(self, supplied=None):
        script = (ROOT / "stoa-gateway/tests/e2e/run-e2e.sh").read_text()
        boundary = "\nSCRIPT_DIR="
        if boundary not in script:
            raise AssertionError("E2E credential boundary is missing")
        prefix = script.split(boundary, 1)[0]
        prefix += '\npython3 -c \'import os; assert len(os.environ["ADMIN_TOKEN"]) >= 32; assert len(os.environ["E2E_KEYCLOAK_ADMIN_PASSWORD"]) >= 32\'\n'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prefix.sh"
            path.write_text(prefix)
            env = dict(os.environ)
            env.pop("ADMIN_TOKEN", None)
            env.pop("E2E_KEYCLOAK_ADMIN_PASSWORD", None)
            env.update(supplied or {})
            return subprocess.run(
                ["/bin/bash", "-x", str(path)], env=env, capture_output=True, text=True
            )

    def test_runner_generates_inputs_before_any_container_command(self):
        result = self.run_prefix()
        self.assertEqual(0, result.returncode)
        self.assertNotIn("docker compose", result.stderr)

    def test_explicit_inputs_are_not_exposed_under_shell_tracing(self):
        token = secrets.token_urlsafe(32)
        result = self.run_prefix({"ADMIN_TOKEN": token, "E2E_KEYCLOAK_ADMIN_PASSWORD": token})
        self.assertEqual(0, result.returncode)
        self.assertNotIn(token, result.stdout + result.stderr)
