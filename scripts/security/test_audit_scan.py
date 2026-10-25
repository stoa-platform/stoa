"""Audit inventory preserves error and category behavior."""

import unittest

from keycloak_audit_lib.audit import Audit


class ScanTests(unittest.TestCase):
    def test_json_failure_and_documentation_inventory(self):
        recorder = Audit()
        recorder.audit_text("unit.md", "keycloak")
        self.assertEqual("documentation", recorder.inventory[0]["category"])
        self.assertFalse(recorder.errors)
        recorder.audit_text("realm.json", "not-json")
        self.assertTrue(recorder.errors)
        self.assertEqual("KC_PARSE", recorder.findings[0].rule)
