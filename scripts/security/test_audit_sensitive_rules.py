"""Sensitive findings never contain inspected values."""

import unittest

from audit_rule_support import Recorder, rules
from keycloak_audit_lib.sensitive import secret_rules


class SensitiveRuleTests(unittest.TestCase):
    def test_credentials_and_tenant_claim_are_redacted(self):
        recorder = Recorder()
        marker = "_".join(["synthetic", "private", "value"])

        def emit(rule, message, key="", **kwargs):
            recorder.add("unit.json", "", rule, message, key, **kwargs)

        secret_rules(
            recorder,
            "unit.json",
            "",
            {"password": marker, "config": {"claim.name": "tenant_id", "user.attribute": "tenant"}},
            1,
            emit,
        )
        self.assertTrue({"KC_HARDCODED_SECRET", "KC_TENANT_ATTRIBUTE"} <= rules(recorder))
        self.assertNotIn(marker, str(recorder.findings))
