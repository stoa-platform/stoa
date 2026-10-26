"""Run the offline security contracts in the existing API pytest job."""

import sys
import unittest
from pathlib import Path

import pytest

SECURITY = Path(__file__).resolve().parents[2] / "scripts/security"
sys.path.insert(0, str(SECURITY))


def cases(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from cases(item)
        else:
            yield item


SUITES = [
    unittest.TestLoader().discover(str(SECURITY), pattern="test_*.py"),
    unittest.TestLoader().discover(str(SECURITY / "tests"), pattern="test_*.py"),
]


@pytest.mark.parametrize("case", list(cases(SUITES)), ids=lambda case: case.id())
def test_offline_security_contract(case):
    result = unittest.TestResult()
    case.run(result)
    assert not result.skipped, "Security contracts must run without skips"
    assert result.wasSuccessful(), result.errors + result.failures


def test_security_suites_keep_conftest_mocks():
    import src.main as main
    from src.services.keycloak_service import keycloak_service
    from tests.conftest import _mock_kafka_service, _mock_keycloak_service

    assert main.kafka_service is _mock_kafka_service
    assert keycloak_service is _mock_keycloak_service
