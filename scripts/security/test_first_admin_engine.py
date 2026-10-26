"""Provisioning contracts against a stateful Keycloak double."""

import importlib
import secrets
import sys
import unittest
from pathlib import Path

from first_admin_fake import FakeKeycloak

sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "charts/stoa-platform/files/first_admin")
)
engine = importlib.import_module("engine")


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.kc = FakeKeycloak()
        self.identity = {
            "username": "operator",
            "email": "operator@example.com",
            "bootstrap_id": secrets.token_urlsafe(32),
            "initial_password": secrets.token_urlsafe(32),
        }

    def test_existing_admin_refuses_without_any_write(self):
        self.kc.users = [{"id": "existing", "username": "existing"}]
        self.kc.roles["/users/existing/role-mappings/realm/composite"] = [{"name": "cpi-admin"}]
        self.assertEqual(
            (20, "administrator_exists", "existing"), engine.provision(self.kc, self.identity)
        )
        self.assertEqual([], self.kc.writes)

    def test_group_admin_is_also_refused(self):
        self.kc.users = [{"id": "existing", "username": "existing"}]
        self.kc.groups["existing"] = [{"id": "admins"}]
        self.kc.roles["/groups/admins/role-mappings/realm/composite"] = [{"name": "cpi-admin"}]
        self.assertEqual(20, engine.provision(self.kc, self.identity)[0])
        self.assertFalse(self.kc.writes)

    def test_second_execution_is_consumed_and_does_not_write(self):
        self.assertEqual(0, engine.provision(self.kc, self.identity)[0])
        writes = list(self.kc.writes)
        self.assertEqual(10, engine.provision(self.kc, self.identity)[0])
        self.assertEqual(writes, self.kc.writes)
        user = self.kc.users[0]
        self.assertTrue(user["credentials"][0]["temporary"])
        self.assertIn("UPDATE_PASSWORD", user["requiredActions"])
        self.assertIn("CONFIGURE_TOTP", user["requiredActions"])
        self.assertTrue(self.kc.realm["adminEventsEnabled"])
        self.assertFalse(self.kc.realm["adminEventsDetailsEnabled"])
        self.assertEqual("yes", self.kc.realm["attributes"]["preserved"])

    def test_resume_after_each_write_never_duplicates_or_resets_password(self):
        for position in range(1, 6):
            with self.subTest(position=position):
                kc = FakeKeycloak()
                kc.interrupt_after = position
                with self.assertRaises(InterruptedError):
                    engine.provision(kc, self.identity)
                kc.interrupt_after = None
                self.assertIn(engine.provision(kc, self.identity)[0], {0, 10, 20})
                self.assertEqual(1, len(kc.users))
                self.assertEqual(1, sum(path == "/users" for _, path in kc.writes))

    def test_other_identity_cannot_take_over_pending_request(self):
        self.kc.interrupt_after = 1
        with self.assertRaises(InterruptedError):
            engine.provision(self.kc, self.identity)
        self.kc.interrupt_after = None
        writes = list(self.kc.writes)
        with self.assertRaises(engine.Refused):
            engine.provision(self.kc, {**self.identity, "bootstrap_id": secrets.token_urlsafe(32)})
        self.assertEqual(writes, self.kc.writes)

    def test_service_account_admin_is_checked_even_when_user_listing_omits_it(self):
        self.kc.clients = [{"id": "sa-client", "serviceAccountsEnabled": True}]
        self.kc.service_accounts["sa-client"] = {"id": "sa-user"}
        self.kc.roles["/users/sa-user/role-mappings/realm/composite"] = [{"name": "cpi-admin"}]
        self.assertEqual(20, engine.provision(self.kc, self.identity)[0])
        self.assertEqual([], self.kc.writes)

    def test_parent_group_administration_is_refused(self):
        self.kc.users = [{"id": "existing", "username": "existing"}]
        self.kc.groups["existing"] = [{"id": "child"}]
        self.kc.parent_groups["child"] = {"id": "child", "parentId": "parent"}
        self.kc.roles["/groups/parent/role-mappings/realm/composite"] = [{"name": "cpi-admin"}]
        self.assertEqual(20, engine.provision(self.kc, self.identity)[0])
        self.assertFalse(self.kc.writes)

    def test_consumption_survives_deletion_of_the_created_admin(self):
        self.assertEqual(0, engine.provision(self.kc, self.identity)[0])
        self.kc.users.clear()
        writes = list(self.kc.writes)
        self.assertEqual(10, engine.provision(self.kc, self.identity)[0])
        self.assertEqual(writes, self.kc.writes)

    def test_preexisting_username_is_never_adopted(self):
        self.kc.users = [
            {
                "id": "unprivileged",
                "username": self.identity["username"],
                "email": self.identity["email"],
            }
        ]
        with self.assertRaisesRegex(engine.Refused, "identity_exists"):
            engine.provision(self.kc, self.identity)
        self.assertFalse(self.kc.writes)

    def test_client_composite_can_confer_platform_admin(self):
        self.kc.users = [{"id": "existing", "username": "existing"}]
        self.kc.all_mappings["/users/existing/role-mappings"] = {
            "clientMappings": {
                "client": {
                    "mappings": [{"id": "composite", "clientRole": True, "composite": True}]
                },
            }
        }
        self.kc.composites["composite"] = [{"name": "cpi-admin", "clientRole": False}]
        self.assertEqual(20, engine.provision(self.kc, self.identity)[0])
        self.assertFalse(self.kc.writes)

    def test_same_named_client_role_does_not_count_as_realm_admin(self):
        self.kc.users = [{"id": "existing", "username": "existing"}]
        self.kc.all_mappings["/users/existing/role-mappings"] = {
            "clientMappings": {
                "client": {"mappings": [{"name": "cpi-admin", "clientRole": True}]},
            }
        }
        self.assertEqual(0, engine.provision(self.kc, self.identity)[0])
        self.assertEqual(2, len(self.kc.users))
