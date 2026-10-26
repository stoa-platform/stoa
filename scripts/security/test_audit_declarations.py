"""Declarative timeout bounds and duplicate payload handling."""

import unittest

from audit_rule_support import Recorder, rules
from keycloak_audit_lib.declarations import inspect_representations


class DeclarationTests(unittest.TestCase):
    def test_declared_lifetime_and_duplicate_client(self):
        recorder = Recorder()
        obj = {"clientId": "unit", "tokenLifespans": {"accessToken": 300}}
        obj["tokenLifespans"]["accessToken"] += 1
        inspect_representations(recorder, "unit.json", "", [(obj, 1), (obj, 1)])
        self.assertIn("KC_DECLARED_LIFETIME", rules(recorder))
        self.assertEqual([obj], recorder.objects)
