"""Local command doubles verify stdin storage and value-free output."""

import base64
import contextlib
import io
import json
import secrets
import sys
import unittest
from unittest.mock import patch

import store_oidc_secret as storage


class StorageTests(unittest.TestCase):
    def run_storage(self, arguments, existing="", failure=False):
        token = secrets.token_urlsafe(32)
        calls = []

        def run(args, **kwargs):
            self.assertNotIn(token, " ".join(args))
            calls.append((args, kwargs.get("input")))

            class Result:
                returncode = int(failure)
                stdout = existing if "get" in args else token
                stderr = token

            return Result()

        out, err = io.StringIO(), io.StringIO()
        with (
            patch.object(sys, "argv", ["store", *arguments]),
            patch.object(sys, "stdin", io.StringIO(json.dumps({"value": token}))),
            patch.object(storage.subprocess, "run", run),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            code = storage.main()
        self.assertNotIn(token, out.getvalue() + err.getvalue())
        return code, calls

    def test_new_cookie_has_32_random_bytes_and_existing_cookie_is_preserved(self):
        code, calls = self.run_storage(["--cookie", "--client-id", "observability"])
        self.assertEqual(0, code)
        secret = json.loads(calls[-1][1])
        cookie = base64.b64decode(secret["data"]["cookie-secret"])
        self.assertEqual(32, len(base64.b64decode(cookie)))
        secret["metadata"]["resourceVersion"] = "1"
        code, calls = self.run_storage(["--cookie"], json.dumps(secret))
        self.assertEqual(0, code)
        self.assertEqual(
            secret["data"]["cookie-secret"], json.loads(calls[-1][1])["data"]["cookie-secret"]
        )
        self.assertIn("replace", calls[-1][0])

    def test_explicit_cookie_rotation_changes_only_the_requested_cookie(self):
        secret = {
            "metadata": {"resourceVersion": "1"},
            "data": {"cookie-secret": secrets.token_urlsafe(32)},
        }
        code, calls = self.run_storage(["--cookie", "--rotate-cookie"], json.dumps(secret))
        self.assertEqual(0, code)
        self.assertNotEqual(
            secret["data"]["cookie-secret"], json.loads(calls[-1][1])["data"]["cookie-secret"]
        )

    def test_get_failure_never_overwrites_an_unread_secret(self):
        code, calls = self.run_storage(["--cookie"], failure=True)
        self.assertEqual(1, code)
        self.assertEqual(1, len(calls))

    def test_vault_input_uses_stdin(self):
        code, calls = self.run_storage(
            ["--vault-path", "secret/oidc", "--key", "oidc-client-secret"]
        )
        self.assertEqual(0, code)
        self.assertEqual(["vault", "kv", "patch", "secret/oidc", "-"], calls[0][0])
        self.assertIn("oidc-client-secret", json.loads(calls[0][1]))

    def test_operator_scripts_restore_direct_storage_and_document_followup(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        for name in (
            "deploy/observability/setup-keycloak-client.sh",
            "deploy/observability/create-keycloak-client.sh",
            "deploy/scripts/setup-observability-oidc.sh",
            "deploy/scripts/setup-netbox-oidc.sh",
        ):
            source = (root / name).read_text()
            self.assertIn("store_oidc_secret.py", source, name)
            self.assertIn("client-secret", source, name)
            self.assertIn("docs/runbooks/first-admin-bootstrap.md", source, name)
            self.assertNotIn("Sensitive values are withheld", source, name)
        source = (root / "deploy/scripts/setup-observability-oidc.sh").read_text()
        self.assertNotIn('echo "  OAUTH2_PROXY_COOKIE_SECRET=', source)
