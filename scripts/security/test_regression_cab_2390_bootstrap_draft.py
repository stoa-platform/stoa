"""Keep the bootstrap security contract strict with nested user-profile JSON."""

import unittest
from unittest.mock import patch

import test_bootstrap_draft as bootstrap


class BootstrapDraftRegressionTests(unittest.TestCase):
    def test_nested_profile_does_not_hide_insecure_realm_settings(self):
        source = bootstrap.load("charts/stoa-platform/templates/bootstrap-job.yaml")
        self.assertIn("kc.user.profile.config", source)
        for old, new in (
            ("length(16)", "length(8)"),
            (r"\"registrationAllowed\": false", r"\"registrationAllowed\": true"),
        ):
            with self.subTest(setting=old):
                self.assertIn(old, source)
                contract = bootstrap.DraftTests("test_helm_new_realms_and_browser_clients")
                with patch.object(bootstrap, "load", return_value=source.replace(old, new)):
                    with self.assertRaises(AssertionError):
                        contract.test_helm_new_realms_and_browser_clients()

    def test_browser_client_count_does_not_hide_a_duplicate_identity(self):
        source = bootstrap.load("charts/stoa-platform/templates/bootstrap-job.yaml")
        self.assertIn("stoa-portal", source)
        source = source.replace("stoa-portal", "control-plane-ui")
        contract = bootstrap.DraftTests("test_helm_new_realms_and_browser_clients")
        with patch.object(bootstrap, "load", return_value=source):
            with self.assertRaises(AssertionError):
                contract.test_helm_new_realms_and_browser_clients()


if __name__ == "__main__":
    unittest.main()
