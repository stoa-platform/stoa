"""Payload failures are sanitized without executing source."""

import unittest

from audit_rule_support import Recorder, rules
from keycloak_audit_lib.parsing import parse_representations


class PayloadTests(unittest.TestCase):
    def test_invalid_json_reports_only_constant_message(self):
        recorder = Recorder()
        self.assertIsNone(parse_representations(recorder, "unit.json", "not-json", "bootstrap"))
        self.assertTrue(recorder.errors)
        self.assertIn("KC_PARSE", rules(recorder))

    def test_shell_parameters_are_not_evaluated(self):
        recorder = Recorder()
        result = parse_representations(
            recorder,
            "unit.sh",
            "kcadm.sh update realms/unit -s registrationAllowed=false",
            "bootstrap",
        )
        self.assertEqual([({"registrationAllowed": False}, 1)], result)
