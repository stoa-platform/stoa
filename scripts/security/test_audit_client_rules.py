"""Client rules preserve PKCE and exact redirect enforcement."""

import unittest

from audit_rule_support import Recorder, rules, safe_client
from keycloak_audit_lib.client import client_rules


class ClientRuleTests(unittest.TestCase):
    def test_pkce_and_redirects(self):
        recorder = Recorder()
        obj = safe_client()

        def emit(rule, message, key="", **kwargs):
            recorder.add("unit.json", "", rule, message, key, **kwargs)

        client_rules(recorder, "unit.json", "", obj, 1, emit, "prod", None)
        self.assertEqual([], recorder.findings)
        obj["attributes"].clear()
        obj["redirectUris"] = ["https://example.test/*"]
        client_rules(recorder, "unit.json", "", obj, 1, emit, "prod", None)
        self.assertTrue({"KC_PKCE", "KC_REDIRECT_WILDCARD"} <= rules(recorder))
