"""Planning validates inventory before mutations."""

import unittest

from keycloak_migration.core import MigrationError
from keycloak_migration.planner import plan
from keycloak_migration.policy import validate_policy
from migration_http_support import policy


class PlannerTests(unittest.TestCase):
    def test_inventory_mismatch_is_read_only(self):
        class API:
            def get(self, path):
                return {"realm": "example"}

            def clients(self):
                return []

        with self.assertRaises(MigrationError):
            plan(API(), validate_policy(policy()))
