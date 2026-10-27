"""URI and identifier contracts reject ambiguous input."""

import unittest

from keycloak_migration.core import MigrationError, exact_uri, identifier


class MigrationPrimitiveTests(unittest.TestCase):
    def test_invalid_uri_and_traversal_are_rejected(self):
        for uri in (
            "http://example.test",
            "https://example.test/*",
            "https://user@example.test",
            "https://example.test?",
        ):
            with self.assertRaises(MigrationError):
                exact_uri(uri)
        for value in (".", "..", "a/b", "%2e%2e"):
            with self.assertRaises(MigrationError):
                identifier(value)
        self.assertEqual("unit", identifier("unit"))
