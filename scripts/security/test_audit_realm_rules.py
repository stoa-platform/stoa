"""Realm rules retain strict admission and duration checks."""

import unittest

from audit_rule_support import Recorder, rules, safe_realm
from keycloak_audit_lib.realm import realm_rules


class RealmRuleTests(unittest.TestCase):
    def test_closed_realm_and_open_registration(self):
        recorder = Recorder()
        obj = safe_realm()

        def emit(rule, message, key="", **kwargs):
            recorder.add("unit.json", "", rule, message, key, **kwargs)

        realm_rules(recorder, "unit.json", "", obj, 1, emit, "prod")
        self.assertEqual([], recorder.findings)
        obj["registrationAllowed"] = True
        realm_rules(recorder, "unit.json", "", obj, 1, emit, "prod")
        self.assertIn("KC_REGISTRATION", rules(recorder))
