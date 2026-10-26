"""Comments stay inert and explicit mutations are detected."""

import unittest

from audit_rule_support import Recorder, rules
from keycloak_audit_lib.lexical import lexical_checks


class LexicalTests(unittest.TestCase):
    def test_comments_are_ignored_and_mutations_are_reported(self):
        recorder = Recorder()
        mutation = "kcadm.sh update realms/unit -s registrationAllowed=" + str(True).lower() + "\n"
        lexical_checks(recorder, "unit.sh", "# " + mutation)
        self.assertEqual([], recorder.findings)
        lexical_checks(recorder, "unit.sh", mutation)
        self.assertIn("KC_REGISTRATION", rules(recorder))
