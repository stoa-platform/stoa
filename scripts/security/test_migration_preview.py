"""Preview withholds remote values and identifiers."""

import io
import unittest

from keycloak_migration.state import preview


class PreviewTests(unittest.TestCase):
    def test_remote_string_is_redacted(self):
        output = io.StringIO()
        marker = "_".join(["private", "synthetic", "value"])
        op = {
            "kind": "fields",
            "path": "/clients/private-id",
            "changes": [
                {
                    "key": ["redirectUris"],
                    "before": {"exists": True, "value": [marker]},
                    "after": {"exists": True, "value": []},
                }
            ],
        }
        preview([op], output)
        self.assertNotIn(marker, output.getvalue())
        self.assertNotIn("private-id", output.getvalue())
        self.assertIn('"redacted_items": 1', output.getvalue())
