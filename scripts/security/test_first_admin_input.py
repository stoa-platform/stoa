"""Input and audit contracts, including subprocess stderr."""

import contextlib
import importlib.util
import io
import json
import os
import secrets
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from first_admin_fake import FakeKeycloak

MODULES = Path(__file__).resolve().parents[2] / "charts/stoa-platform/files/first_admin"
sys.path.insert(0, str(MODULES))
spec = importlib.util.spec_from_file_location("stoa_first_admin_main", MODULES / "main.py")
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class InputTests(unittest.TestCase):
    def setUp(self):
        self.token = secrets.token_urlsafe(40)
        self.request = {
            "username": "operator",
            "email": "operator@example.com",
            "bootstrap_id": self.token,
            "initial_password": self.token,
            "admin_user": "operator",
            "admin_password": self.token,
        }

    def test_success_and_replay_audit_contain_no_secret(self):
        kc = FakeKeycloak()
        for expected in (0, 10):
            out, err = io.StringIO(), io.StringIO()
            with (
                patch.object(sys, "argv", ["bootstrap"]),
                patch.object(sys, "stdin", io.StringIO(json.dumps(self.request))),
                patch.object(bootstrap, "Keycloak", return_value=kc),
                contextlib.redirect_stdout(out),
                contextlib.redirect_stderr(err),
            ):
                self.assertEqual(expected, bootstrap.main())
            self.assertNotIn(self.token, out.getvalue() + err.getvalue())
            audit = json.loads(out.getvalue().splitlines()[0])
            self.assertEqual(expected, audit["exit_code"])
            self.assertIn("timestamp", audit)
            self.assertIn("Delete", out.getvalue())

    def test_failure_does_not_echo_exception(self):
        out = io.StringIO()
        with (
            patch.object(sys, "argv", ["bootstrap"]),
            patch.object(sys, "stdin", io.StringIO(json.dumps(self.request))),
            patch.object(bootstrap, "Keycloak", side_effect=RuntimeError(self.token)),
            contextlib.redirect_stdout(out),
        ):
            self.assertEqual(23, bootstrap.main())
        self.assertNotIn(self.token, out.getvalue())

    def test_file_permissions_and_symlink_are_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_text(json.dumps(self.request))
            path.chmod(0o600)
            self.assertEqual(self.request, bootstrap.read_identity(str(path)))
            path.chmod(0o644)
            with self.assertRaises(bootstrap.Refused):
                bootstrap.read_identity(str(path))
            link = path.with_name("link")
            link.symlink_to(path)
            with self.assertRaises(OSError):
                bootstrap.read_identity(str(link))

    def test_old_secret_argument_is_refused_without_echo(self):
        run = subprocess.run(
            [sys.executable, str(MODULES / "main.py"), self.token],
            input="",
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(22, run.returncode)
        self.assertNotIn(self.token, run.stdout + run.stderr)

    def test_invalid_json_is_value_blind(self):
        with patch.object(sys, "stdin", io.StringIO(self.token)):
            with self.assertRaises(ValueError):
                bootstrap.read_identity(None)
