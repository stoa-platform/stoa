"""Journal edits cannot expand the mutation surface."""

import unittest

from keycloak_migration.core import MigrationError
from keycloak_migration.journal import validate_operation


class JournalValidationTests(unittest.TestCase):
    def test_user_and_credential_paths_are_rejected(self):
        for path in (
            "/users/unit",
            "/clients/unit/client-secret",
            "/clients/../protocol-mappers/models",
        ):
            with self.assertRaises(MigrationError):
                validate_operation({"kind": "fields", "path": path, "changes": []})
