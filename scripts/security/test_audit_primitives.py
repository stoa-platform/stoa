"""Primitive bounds and safe discovery contracts."""

import unittest
from pathlib import Path

from keycloak_audit_lib import common


class PrimitiveTests(unittest.TestCase):
    def test_boolean_and_unbounded_durations_are_rejected(self):
        for value in (False, True, 0, -1, "${DYNAMIC}", 301):
            self.assertFalse(common.bounded(value, 300))
        self.assertTrue(common.bounded("300", 300))

    def test_payload_line_and_escaped_json_are_preserved(self):
        self.assertEqual(
            [({"realm": "unit"}, 2)], list(common.json_objects('prefix\n{"realm":"unit"}'))
        )

    def test_credential_paths_are_excluded(self):
        for name in (".env", "credentials.json", "client.key"):
            self.assertTrue(common.credential_path(Path(name)))
