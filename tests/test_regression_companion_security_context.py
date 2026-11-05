"""Keep the companion container hardening covered by a named regression test."""

import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "security"))

import test_companion_security_context as companion_security


class CompanionSecurityContextRegressionTests(unittest.TestCase):
    def test_regression_companion_security_context(self):
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(
            companion_security.CompanionSecurityContextTests
        )
        output = io.StringIO()
        result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
        self.assertTrue(result.wasSuccessful(), output.getvalue())


if __name__ == "__main__":
    unittest.main()
