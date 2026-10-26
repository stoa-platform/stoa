"""Malformed collections fail closed before rule dispatch."""

import unittest

from audit_rule_support import Recorder, rules
from keycloak_audit_lib.representation import RepresentationRules


class RepresentationTests(unittest.TestCase):
    def test_malformed_mapper_sets_error(self):
        class Audit(RepresentationRules, Recorder):
            pass

        recorder = Audit()
        recorder.representation("unit.json", "", {"protocolMappers": [None]})
        self.assertTrue(recorder.errors)
        self.assertIn("KC_PARSE", rules(recorder))
