"""Journal persistence is exclusive and precedes writes."""

import tempfile
import unittest
from pathlib import Path

from keycloak_migration.core import MigrationError
from keycloak_migration.execution import create_journal


class ExecutionTests(unittest.TestCase):
    def test_journal_is_private_and_exclusive(self):
        class API:
            def binding(self):
                return {"url": "https://auth.example.test", "realm": "unit"}

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.json"
            create_journal(path, API(), [])
            self.assertEqual(0o600, path.stat().st_mode & 0o777)
            with self.assertRaises(MigrationError):
                create_journal(path, API(), [])
