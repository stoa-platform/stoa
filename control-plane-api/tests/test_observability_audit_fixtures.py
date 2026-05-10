"""Tests for synthetic audit-log fixtures."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from scripts.seeder.observability_fixtures import audit_events
from scripts.seeder.runner import SeederRunner
from sqlalchemy.ext.asyncio import AsyncSession


def _mock_session(existing_count: int = 0) -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalar_one.return_value = existing_count
    result.rowcount = 0
    session.execute = AsyncMock(return_value=result)
    return session


def _clear_fixture_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "ENVIRONMENT",
        "STOA_ENVIRONMENT",
        audit_events.OPT_IN_ENV,
        audit_events.FIXTURE_PROFILE_ENV,
    ):
        monkeypatch.delenv(name, raising=False)


def _insert_calls(session: AsyncMock) -> list:
    return [
        call
        for call in session.execute.await_args_list
        if call.args and "INSERT INTO audit_events" in str(call.args[0])
    ]


@pytest.mark.asyncio
async def test_dev_profile_seeds_target_volume_with_locked_markers(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_fixture_env(monkeypatch)
    session = _mock_session()

    result = await audit_events.seed(session, "dev")

    assert result.name == "observability_fixtures"
    assert result.created == audit_events.TARGET_EVENT_COUNT
    inserts = _insert_calls(session)
    assert len(inserts) == audit_events.TARGET_EVENT_COUNT
    for call in inserts:
        details = json.loads(call.args[1]["details"])
        assert details == audit_events.SYNTHETIC_DETAILS


@pytest.mark.asyncio
async def test_production_environment_refuses_synthetic_audit_fixtures(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_fixture_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(RuntimeError, match="forbidden"):
        await audit_events.seed(_mock_session(), "dev")


@pytest.mark.asyncio
async def test_prod_profile_refuses_synthetic_audit_fixtures(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_fixture_env(monkeypatch)

    with pytest.raises(RuntimeError, match="prod profile"):
        await audit_events.seed(_mock_session(), "prod")


def test_runner_refuses_prod_fixture_step(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_fixture_env(monkeypatch)

    with pytest.raises(ValueError, match="forbidden in prod profile"):
        SeederRunner(session=_mock_session(), profile="prod", step="observability_fixtures")


def test_runner_refuses_prod_fixture_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_fixture_env(monkeypatch)
    monkeypatch.setenv(audit_events.OPT_IN_ENV, "true")

    with pytest.raises(ValueError, match="forbidden in prod profile"):
        SeederRunner(session=_mock_session(), profile="prod")


def test_runner_does_not_treat_false_prod_opt_in_as_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_fixture_env(monkeypatch)
    monkeypatch.setenv(audit_events.OPT_IN_ENV, "false")

    runner = SeederRunner(session=_mock_session(), profile="prod")

    assert runner.profile == "prod"


@pytest.mark.asyncio
async def test_staging_demo_requires_explicit_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_fixture_env(monkeypatch)
    monkeypatch.setenv(audit_events.FIXTURE_PROFILE_ENV, "staging-demo")
    session = _mock_session()

    result = await audit_events.seed(session, "staging")

    assert result.created == 0
    session.execute.assert_not_awaited()

    monkeypatch.setenv(audit_events.OPT_IN_ENV, "true")
    enabled_session = _mock_session()

    enabled_result = await audit_events.seed(enabled_session, "staging")

    assert enabled_result.created == audit_events.TARGET_EVENT_COUNT
    assert len(_insert_calls(enabled_session)) == audit_events.TARGET_EVENT_COUNT


@pytest.mark.asyncio
async def test_staging_prodlike_does_not_seed_even_with_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_fixture_env(monkeypatch)
    monkeypatch.setenv(audit_events.FIXTURE_PROFILE_ENV, "staging-prodlike")
    monkeypatch.setenv(audit_events.OPT_IN_ENV, "true")
    session = _mock_session()

    result = await audit_events.seed(session, "staging")

    assert result.created == 0
    session.execute.assert_not_awaited()
