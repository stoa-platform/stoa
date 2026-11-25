"""/health/ready reports a failed dependency check as "error" only.

The exception text stays out of the response (also in the 503 body when a
critical dependency fails); the logs record the exception type only.
"""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from src.config import settings
from src.routers import health

DETAIL = "synthetic-detail http://dependency.invalid:9092 user=placeholder"
CHECKS = {
    "kafka": "_check_kafka_connected",
    "keycloak": "_check_keycloak_connected",
    "git": "_check_git_connected",
    "gateway": "_check_gateway_connected",
}
CRITICAL = {"kafka", "keycloak"}


@pytest.fixture(autouse=True)
def _fresh_cache():
    health._reset_vault_readiness_cache()
    yield
    health._reset_vault_readiness_cache()


def _disabled_vault() -> MagicMock:
    vault = MagicMock()
    vault.enabled = False
    return vault


async def _ready_with_failure(failing: str, monkeypatch) -> tuple[int, dict, str]:
    """Run readiness with one check raising; return (status code, checks, serialized body)."""
    monkeypatch.setattr(settings, "KAFKA_ENABLED", True)
    for name, fn in CHECKS.items():
        if name == failing:
            monkeypatch.setattr(health, fn, MagicMock(side_effect=RuntimeError(DETAIL)))
        else:
            monkeypatch.setattr(health, fn, MagicMock(return_value=True))
    monkeypatch.setattr(health, "get_vault_client", MagicMock(return_value=_disabled_vault()))
    try:
        response = await health.readiness()
    except HTTPException as exc:
        return exc.status_code, exc.detail["checks"], str(exc.detail)
    return 200, response.checks, response.model_dump_json()


@pytest.mark.asyncio
@pytest.mark.parametrize("failing", sorted(CHECKS))
async def test_failed_check_reports_error_without_details(failing, monkeypatch, caplog):
    with caplog.at_level("WARNING", logger=health.__name__):
        code, checks, body = await _ready_with_failure(failing, monkeypatch)
    assert code == (503 if failing in CRITICAL else 200)
    assert checks[failing] == "error"
    assert DETAIL not in body
    assert "placeholder" not in body
    messages = [r.getMessage() for r in caplog.records]
    assert any(failing in m and "RuntimeError" in m for m in messages)
    assert not any(DETAIL in m for m in messages)


def test_no_exception_text_in_readiness_source():
    import inspect

    assert "e!s" not in inspect.getsource(health.readiness)
