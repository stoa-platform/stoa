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

from migration_http_support import ROOT, SECRET, FakeKeycloak, Response, policy

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

    def test_conflicting_inherited_tenant_mapper_blocks_entire_plan(self):
        self.fake.objects[ROOT + "/clients/c1/default-client-scopes"] = [
            {"id": "s1", "name": "identity"}
        ]
        self.fake.objects[ROOT + "/client-scopes"] = [{"id": "s1", "name": "identity"}]
        self.fake.objects[ROOT + "/client-scopes/s1/protocol-mappers/models"] = [
            {
                "id": "legacy",
                "name": "legacy-tenant",
                "protocolMapper": "oidc-usermodel-attribute-mapper",
                "config": {"claim.name": "tenant_id", "user.attribute": "tenant"},
            }
        ]
        with self.assertRaises(m.MigrationError):
            self.plan()
        self.assertFalse(self.fake.writes)

    def test_explicit_scope_mapper_update_preserves_id_and_is_idempotent(self):
        self.p["clients"]["portal"]["mappers"].pop("tenant-id")
        self.p["scopes"] = {"identity": {"legacy-tenant": "tenant"}}
        self.fake.objects[ROOT + "/clients/c1/default-client-scopes"] = [
            {"id": "s1", "name": "identity"}
        ]
        self.fake.objects[ROOT + "/client-scopes"] = [{"id": "s1", "name": "identity"}]
        path = ROOT + "/client-scopes/s1/protocol-mappers/models"
        self.fake.objects[path] = [
            {
                "id": "legacy",
                "name": "legacy-tenant",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-usermodel-attribute-mapper",
                "consentRequired": False,
                "config": {"claim.name": "tenant_id", "user.attribute": "tenant"},
            }
        ]
        self.apply()
        self.assertEqual(self.fake.objects[path][0]["id"], "legacy")
        self.assertEqual(self.fake.objects[path][0]["config"]["user.attribute"], "tenant_id")
        self.assertEqual(self.plan(), [])

    def test_tenant_requires_explicit_review(self):
        self.p["tenant_attribute_reviewed"] = False
        with self.assertRaises(m.MigrationError):
            self.plan()

    def test_password_recovery_requires_explicit_boolean_decision(self):
        self.p["reset_password_allowed"] = True
        self.apply()
        self.assertTrue(self.fake.objects[ROOT]["resetPasswordAllowed"])
        for invalid in (None, "false", 0):
            self.p["reset_password_allowed"] = invalid
            with self.assertRaises(m.MigrationError):
                self.plan()

    def test_concurrent_managed_change_aborts_before_mutation(self):
        ops = self.plan()
        self.fake.objects[ROOT]["registrationAllowed"] = False
        with self.assertRaises(m.MigrationError):
            m.execute(self.api, ops, Path(self.temp.name) / "journal.json", self.output)
        self.assertFalse(self.fake.writes)

    def test_rollback_refuses_concurrent_drift(self):
        self.apply()
        self.fake.objects[ROOT + "/clients/c1"]["redirectUris"] = ["https://other.example.invalid/"]
        count = len(self.fake.writes)
        with self.assertRaises(m.MigrationError):
            m.rollback(self.api, Path(self.temp.name) / "journal.json", True, self.output)
        self.assertEqual(len(self.fake.writes), count)

    def test_journal_exclusive_and_no_symlinks(self):
        target = Path(self.temp.name) / "existing"
        target.write_text("do not replace")
        for path in (target, Path(self.temp.name) / "link"):
            if path.name == "link":
                path.symlink_to(target)
            with self.assertRaises(m.MigrationError):
                m.execute(self.api, self.plan(), path, self.output)
        self.assertEqual(target.read_text(), "do not replace")
        self.assertFalse(self.fake.writes)

    def test_rollback_default_is_simulation_and_repeat_is_noop(self):
        self.apply()
        count = len(self.fake.writes)
        journal = Path(self.temp.name) / "journal.json"
        m.rollback(self.api, journal, False, self.output)
        self.assertEqual(count, len(self.fake.writes))
        m.rollback(self.api, journal, True, self.output)
        count = len(self.fake.writes)
        m.rollback(self.api, journal, True, self.output)
        self.assertEqual(count, len(self.fake.writes))

    def test_invalid_redirects_unknown_keys_and_duplicate_inventory_rejected(self):
        for uri in (
            "https://portal.example.invalid/*",
            "http://portal.example.invalid/",
            "/relative",
            "+",
            "https://user:password@portal.example.invalid/",
            "https://portal.example.invalid/?token=value",
            "https://portal.example.invalid/#fragment",
            "https://portal.example.invalid/%2a",
        ):
            with self.subTest(uri=uri):
                self.p = policy()
                self.p["clients"]["portal"]["redirect_uris"] = [uri]
                with self.assertRaises(m.MigrationError):
                    self.plan()
        self.p = policy()
        self.p["typo"] = True
        with self.assertRaises(m.MigrationError):
            self.plan()
        self.p = policy()
        self.p["reviewed_clients"] *= 2
        with self.assertRaises(m.MigrationError):
            self.plan()

    def test_transport_refuses_redirects_http_and_secret_in_url(self):
        for url in (
            "http://auth.example.invalid",
            "https://user:pass@auth.example.invalid",
            "https://auth.example.invalid?token=value",
        ):
            with self.assertRaises(m.MigrationError):
                m.Admin(url, "example", SECRET)
        for status in (302, 401, 403, 429, 500):
            self.fake.request = lambda *a, status=status: Response(status, {"error": SECRET})
            with self.assertRaises(m.MigrationError) as caught:
                self.api.get("")
            self.assertNotIn(SECRET, str(caught.exception))

    def test_token_validation_does_not_echo_input(self):
        for token in ("", SECRET + "\nInjected: header", "x" * 20000):
            with self.assertRaises(m.MigrationError) as caught:
                m.Admin("https://auth.example.invalid", "example", token)
            self.assertNotIn(SECRET, str(caught.exception))

    def test_tls_key_logging_environment_is_ignored_with_ca_validation_enabled(self):
        keylog = Path(self.temp.name) / "tls-keylog.txt"
        with (
            patch.dict(os.environ, {"SSLKEYLOGFILE": str(keylog)}),
            patch.object(m.ssl.SSLContext, "load_default_certs", autospec=True) as load_certs,
        ):
            api = m.Admin("https://auth.example.invalid", "example", SECRET)
        self.assertIsNone(api.context.keylog_filename)
        self.assertFalse(keylog.exists())
        self.assertEqual(api.context.verify_mode, m.ssl.CERT_REQUIRED)
        self.assertTrue(api.context.check_hostname)
        load_certs.assert_called_once_with(api.context)

    def test_error_cli_is_sanitized_without_traceback(self):
        pol = Path(self.temp.name) / "policy.json"
        pol.write_text('{"bad": "' + SECRET + '"}')
        with patch("sys.stdin", io.StringIO(SECRET)), patch("sys.stderr", self.output):
            code = m.main(["--url", "https://auth.example.invalid", "--policy", str(pol)])
        self.assertEqual(code, 2)
        self.assertNotIn(SECRET, self.output.getvalue())
        self.assertNotIn("Traceback", self.output.getvalue())

    def test_already_compliant_realm_has_zero_writes(self):
        realm = self.fake.objects[ROOT]
        realm.update(m.BOUNDS, resetPasswordAllowed=False)
        self.fake.objects[ROOT + "/identity-provider/instances/social"]["enabled"] = False
        c = self.fake.objects[ROOT + "/clients/c1"]
        cfg = self.p["clients"]["portal"]
        c.update(
            redirectUris=cfg["redirect_uris"],
            webOrigins=cfg["web_origins"],
            standardFlowEnabled=True,
            implicitFlowEnabled=False,
            directAccessGrantsEnabled=False,
        )
        c["attributes"].update(m.CLIENT_BOUNDS)
        c["attributes"].update(
            {
                "pkce.code.challenge.method": "S256",
                "post.logout.redirect.uris": "##".join(cfg["post_logout_redirect_uris"]),
            }
        )
        self.fake.objects[ROOT + "/clients/c1/protocol-mappers/models"] = [
            dict(m.mapper(preset, name), id=name) for name, preset in cfg["mappers"].items()
        ]
        self.assertEqual(self.plan(), [])
        self.assertFalse(self.fake.writes)

    def test_stricter_duration_bounds_never_lengthened(self):
        self.fake.objects[ROOT]["accessTokenLifespan"] = 60
        self.fake.objects[ROOT]["ssoSessionMaxLifespan"] = 600
        self.fake.objects[ROOT + "/clients/c1"]["attributes"]["access.token.lifespan"] = "30"
        self.apply()
        self.assertEqual(self.fake.objects[ROOT]["accessTokenLifespan"], 60)
        self.assertEqual(self.fake.objects[ROOT]["ssoSessionIdleTimeout"], 600)
        self.assertEqual(
            self.fake.objects[ROOT + "/clients/c1"]["attributes"]["access.token.lifespan"], "30"
        )
        self.assertEqual(self.plan(), [])

    def test_all_client_pages_included_in_inventory(self):
        for n in range(105):
            name = "reviewed-" + str(n)
            self.fake.objects[ROOT + "/clients"].append({"clientId": name, "id": name})
            self.p["reviewed_clients"].append(name)
        self.plan()
        self.assertIn(("GET", ROOT + "/clients?first=100&max=100"), self.fake.requests)
        self.p["reviewed_clients"].pop()
        with self.assertRaises(m.MigrationError):
            self.plan()
        self.assertFalse(self.fake.writes)

    def test_lost_mapper_creation_response_does_not_duplicate_on_resume(self):
        original = self.fake.request

        def fail_after_create(method, *args):
            if method == "POST":
                self.fake.lost_response = True
                self.fake.request = original
            return original(method, *args)

        self.fake.request = fail_after_create
        with self.assertRaises(m.MigrationError):
            self.apply()
        self.apply("resume.json")
        self.assertEqual(self.plan(), [])
        names = [x["name"] for x in self.fake.objects[ROOT + "/clients/c1/protocol-mappers/models"]]
        self.assertEqual(len(names), len(set(names)))
        m.rollback(self.api, Path(self.temp.name) / "resume.json", True, self.output)
        m.rollback(self.api, Path(self.temp.name) / "journal.json", True, self.output)
        self.assertEqual(self.fake.objects[ROOT + "/clients/c1/protocol-mappers/models"], [])

    def test_duplicate_mapper_names_rejected_even_when_unmanaged(self):
        self.fake.objects[ROOT + "/clients/c1/protocol-mappers/models"] = [
            {"id": "one", "name": "duplicate"},
            {"id": "two", "name": "duplicate"},
        ]
        with self.assertRaises(m.MigrationError):
            self.plan()
        self.assertFalse(self.fake.writes)

    def test_optional_scope_conflict_also_rejected(self):
        self.fake.objects[ROOT + "/clients/c1/optional-client-scopes"] = [{"id": "s1"}]
        self.fake.objects[ROOT + "/client-scopes/s1/protocol-mappers/models"] = [
            dict(m.mapper("tenant", "other-tenant"), id="existing")
        ]
        with self.assertRaises(m.MigrationError):
            self.plan()
        self.assertFalse(self.fake.writes)

    def test_scope_update_refused_when_used_by_exempt_client(self):
        self.p["scopes"] = {"shared": {"tenant-id": "tenant"}}
        self.fake.objects[ROOT + "/client-scopes"] = [{"id": "s1", "name": "shared"}]
        self.fake.objects[ROOT + "/clients/c0/default-client-scopes"] = [{"id": "s1"}]
        with self.assertRaises(m.MigrationError):
            self.plan()
        self.assertFalse(self.fake.writes)

    def test_rollback_rejects_wrong_target_and_public_journal(self):
        self.apply()
        journal = Path(self.temp.name) / "journal.json"
        other = m.Admin("https://other.example.invalid", "example", SECRET)
        count = len(self.fake.writes)
        with self.assertRaises(m.MigrationError):
            m.rollback(other, journal, True, self.output)
        journal.chmod(0o644)
        with self.assertRaises(m.MigrationError):
            m.rollback(self.api, journal, True, self.output)
        self.assertEqual(count, len(self.fake.writes))
