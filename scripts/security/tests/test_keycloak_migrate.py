"""Offline contract tests: real planner/HTTP client, simulated Admin REST boundary."""

import copy
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from migration_http_support import ROOT, SECRET, FakeKeycloak, policy

MODULE = Path(__file__).resolve().parents[1] / "keycloak_migrate.py"
spec = importlib.util.spec_from_file_location("keycloak_migrate", MODULE)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get("TEST_TMPDIR"))
        self.addCleanup(self.temp.cleanup)
        self.fake = FakeKeycloak()
        self.output = io.StringIO()
        self.addCleanup(patch.stopall)
        patch("socket.socket", side_effect=AssertionError("network forbidden")).start()
        patch.object(
            m.http.client,
            "HTTPSConnection",
            lambda *args, **kwargs: self.fake.connection(*args, **kwargs),
        ).start()
        self.api = m.Admin("https://auth.example.invalid", "example", SECRET)
        self.p = policy()

    def plan(self):
        return m.plan(self.api, m.validate_policy(copy.deepcopy(self.p)))

    def apply(self, name="journal.json"):
        return m.execute(self.api, self.plan(), Path(self.temp.name) / name, self.output)

    def test_dry_run_is_default_and_prints_diff_before_writes(self):
        pol = Path(self.temp.name) / "policy.json"
        pol.write_text(json.dumps(self.p))
        with patch("sys.stdin", io.StringIO(SECRET)), patch("sys.stdout", self.output):
            code = m.main(["--url", "https://auth.example.invalid", "--policy", str(pol)])
        self.assertEqual(code, 0)
        self.assertIn('"before"', self.output.getvalue())
        self.assertIn('"after"', self.output.getvalue())
        self.assertFalse(self.fake.writes)

    def test_open_realm_converges_and_second_pass_has_no_writes(self):
        self.apply()
        self.assertFalse(self.fake.objects[ROOT]["registrationAllowed"])
        self.assertFalse(self.fake.objects[ROOT]["resetPasswordAllowed"])
        self.assertFalse(self.fake.objects[ROOT + "/identity-provider/instances/social"]["enabled"])
        self.assertEqual(self.plan(), [])
        count = len(self.fake.writes)
        self.apply("second.json")
        self.assertEqual(len(self.fake.writes), count)

    def test_partial_failure_resume_and_reverse_order_rollback(self):
        before = copy.deepcopy(self.fake.objects)
        self.fake.fail_write = 3
        with self.assertRaises(m.MigrationError):
            self.apply()
        self.fake.fail_write = None
        self.apply("resume.json")
        self.assertEqual(self.plan(), [])
        m.rollback(self.api, Path(self.temp.name) / "resume.json", True, self.output)
        m.rollback(self.api, Path(self.temp.name) / "journal.json", True, self.output)
        for path in (ROOT, ROOT + "/clients/c1", ROOT + "/identity-provider/instances/social"):
            for key, value in before[path].items():
                self.assertEqual(self.fake.objects[path][key], value)
        self.assertEqual(self.fake.objects[ROOT + "/clients/c1/protocol-mappers/models"], [])

    def test_journal_written_before_first_mutation_and_mode_private(self):
        original = self.fake.request
        journal = Path(self.temp.name) / "journal.json"

        def check(method, *args):
            if method != "GET":
                self.assertTrue(journal.exists())
                self.assertEqual(journal.stat().st_mode & 0o777, 0o600)
                self.assertTrue(json.loads(journal.read_text())["operations"])
            return original(method, *args)

        self.fake.request = check
        self.apply()

    def test_no_sensitive_output_in_diff_apply_rollback_and_error(self):
        self.apply()
        m.rollback(self.api, Path(self.temp.name) / "journal.json", False, self.output)
        self.assertNotIn(SECRET, self.output.getvalue())
        self.fake.fail_write = len(self.fake.writes) + 1
        with self.assertRaises(m.MigrationError) as caught:
            m.rollback(self.api, Path(self.temp.name) / "journal.json", True, self.output)
        self.assertNotIn(SECRET, str(caught.exception))
        self.assertNotIn(SECRET, self.output.getvalue())

    def test_unrelated_configuration_and_credentials_preserved(self):
        self.apply()
        self.assertEqual(self.fake.objects[ROOT]["smtpServer"]["password"], SECRET)
        client = self.fake.objects[ROOT + "/clients/c1"]
        self.assertEqual(client["secret"], SECRET)
        self.assertEqual(client["attributes"]["unrelated"], SECRET)
        self.assertEqual(
            self.fake.objects[ROOT + "/identity-provider/instances/social"]["config"][
                "clientSecret"
            ],
            SECRET,
        )
        journal = (Path(self.temp.name) / "journal.json").read_text()
        self.assertNotIn("smtpServer", journal)
        self.assertNotIn("clientSecret", journal)
        self.assertNotIn("unrelated", journal)

    def test_no_users_password_reset_logout_or_token_endpoint(self):
        self.apply()
        for _, path in self.fake.requests:
            self.assertFalse(
                any(s in path for s in ("/users", "reset-password", "logout", "/token"))
            )

    def test_ambiguous_lost_response_replanned_without_duplicate_mapper(self):
        self.fake.lost_response = True
        with self.assertRaises(m.MigrationError):
            self.apply()
        self.apply("resume.json")
        self.assertEqual(self.plan(), [])
        self.assertEqual(len(self.fake.objects[ROOT + "/clients/c1/protocol-mappers/models"]), 2)

    def test_server_ignoring_update_is_failure(self):
        self.fake.ignore_write = True
        with self.assertRaises(m.MigrationError):
            self.apply()
        self.assertEqual(len(self.fake.writes), 1)

    def test_client_and_idp_inventory_must_be_complete(self):
        for key, val in (("reviewed_clients", []), ("idps", [])):
            with self.subTest(key=key):
                self.p = policy()
                self.p[key] = val
                with self.assertRaises(m.MigrationError):
                    self.plan()
        self.assertFalse(self.fake.writes)

    def test_saml_cannot_be_accidentally_managed_as_oidc(self):
        self.fake.objects[ROOT + "/clients/c1"]["protocol"] = "saml"
        with self.assertRaises(m.MigrationError):
            self.plan()
