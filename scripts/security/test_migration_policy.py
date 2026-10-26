"""Policy review and duplicate-key checks fail closed."""

import tempfile
import unittest
from pathlib import Path

from keycloak_migration.core import MigrationError
from keycloak_migration.policy import mapper, read_policy


class PolicyLoadingTests(unittest.TestCase):
    def test_tenant_mapper_shape(self):
        config = mapper("tenant", "unit")["config"]
        self.assertEqual("tenant_id", config["user.attribute"])
        self.assertEqual("true", config["access.token.claim"])

    def test_duplicate_json_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            path.write_text('{"version":1,"version":1}')
            with self.assertRaises(MigrationError):
                read_policy(path)
