"""Tests for OnboardingRepository (CAB-1388)."""
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.repositories.onboarding import OnboardingRepository, _last_step, _percentile


def _mock_session():
    s = AsyncMock()
    s.add = MagicMock()
    s.flush = AsyncMock()
    return s


def _make_progress(
    tenant_id: str = "acme",
    user_id: str = "user-1",
    steps: dict | None = None,
    completed_at=None,
    ttftc_seconds: int | None = None,
    started_at=None,
):
    p = MagicMock()
    p.tenant_id = tenant_id
    p.user_id = user_id
    p.steps_completed = steps or {}
    p.completed_at = completed_at
    p.ttftc_seconds = ttftc_seconds
    p.started_at = started_at or datetime.now(UTC) - timedelta(minutes=10)
    return p


# ── get_by_user ──


class TestGetByUser:
    async def test_returns_progress_when_found(self):
        session = _mock_session()
        repo = OnboardingRepository(session)
        progress = _make_progress()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = progress
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_by_user("acme", "user-1")
        assert result is progress

    async def test_returns_none_when_not_found(self):
        session = _mock_session()
        repo = OnboardingRepository(session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_by_user("acme", "missing")
        assert result is None


# ── create ──


class TestCreate:
    async def test_creates_and_returns_progress(self):
        session = _mock_session()
        repo = OnboardingRepository(session)

        result = await repo.create("acme", "user-1")

        session.add.assert_called_once()
        session.flush.assert_awaited_once()
        assert result.tenant_id == "acme"
        assert result.user_id == "user-1"
        assert result.steps_completed == {}


# ── get_or_create ──


class TestGetOrCreate:
    async def test_returns_existing_when_found(self):
        session = _mock_session()
        repo = OnboardingRepository(session)
        progress = _make_progress()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = progress
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_or_create("acme", "user-1")
        assert result is progress

    async def test_creates_new_when_not_found(self):
        session = _mock_session()
        repo = OnboardingRepository(session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_or_create("acme", "user-new")
        assert result.tenant_id == "acme"
        assert result.user_id == "user-new"


# ── upsert_step ──


class TestUpsertStep:
    async def test_adds_new_step(self):
        session = _mock_session()
        repo = OnboardingRepository(session)

        progress = MagicMock()
        progress.steps_completed = {}
        progress.ttftc_seconds = None
        started = datetime.now(UTC) - timedelta(minutes=5)
        progress.started_at = started

        result = await repo.upsert_step(progress, "create_app")
        assert "create_app" in progress.steps_completed
        session.flush.assert_awaited_once()

    async def test_idempotent_when_step_already_completed(self):
        session = _mock_session()
        repo = OnboardingRepository(session)

        progress = MagicMock()
        progress.steps_completed = {"create_app": "2026-01-01T00:00:00"}

        result = await repo.upsert_step(progress, "create_app")
        assert result is progress
        session.flush.assert_not_awaited()

    async def test_computes_ttftc_on_first_call_step(self):
        session = _mock_session()
        repo = OnboardingRepository(session)

        progress = MagicMock()
        progress.steps_completed = {}
        progress.ttftc_seconds = None
        progress.started_at = datetime.now(UTC) - timedelta(seconds=120)

        await repo.upsert_step(progress, "first_call")
        # ttftc_seconds should be set
        assert progress.ttftc_seconds is not None
        assert progress.ttftc_seconds >= 120

    async def test_does_not_overwrite_existing_ttftc(self):
        session = _mock_session()
        repo = OnboardingRepository(session)

        progress = MagicMock()
        progress.steps_completed = {}
        progress.ttftc_seconds = 999  # Already set
        progress.started_at = datetime.now(UTC) - timedelta(seconds=120)

        await repo.upsert_step(progress, "first_call")
        # Should not overwrite
        assert progress.ttftc_seconds == 999


# ── mark_complete ──


class TestMarkComplete:
    async def test_marks_completed(self):
        session = _mock_session()
        repo = OnboardingRepository(session)

        progress = MagicMock()
        progress.completed_at = None
        progress.ttftc_seconds = 60
        progress.started_at = datetime.now(UTC) - timedelta(seconds=300)

        result = await repo.mark_complete(progress)
        assert progress.completed_at is not None
        session.flush.assert_awaited_once()

    async def test_idempotent_when_already_completed(self):
        session = _mock_session()
        repo = OnboardingRepository(session)

        progress = MagicMock()
        progress.completed_at = datetime.now(UTC)

        result = await repo.mark_complete(progress)
        assert result is progress
        session.flush.assert_not_awaited()

    async def test_computes_ttftc_if_not_set(self):
        session = _mock_session()
        repo = OnboardingRepository(session)

        progress = MagicMock()
        progress.completed_at = None
        progress.ttftc_seconds = None
        progress.started_at = datetime.now(UTC) - timedelta(seconds=200)

        await repo.mark_complete(progress)
        assert progress.ttftc_seconds is not None
        assert progress.ttftc_seconds >= 200


# ── get_funnel_stats ──


class TestGetFunnelStats:
    async def test_empty_returns_zeros(self):
        session = _mock_session()
        repo = OnboardingRepository(session)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        stats = await repo.get_funnel_stats()
        assert stats["total_started"] == 0
        assert stats["total_completed"] == 0
        assert stats["avg_ttftc_seconds"] is None
        assert stats["p50_ttftc_seconds"] is None
        assert stats["p90_ttftc_seconds"] is None

    async def test_with_records(self):
        session = _mock_session()
        repo = OnboardingRepository(session)

        r1 = MagicMock()
        r1.completed_at = datetime.now(UTC)
        r1.ttftc_seconds = 100
        r1.steps_completed = {"choose_use_case": "ts", "create_app": "ts"}

        r2 = MagicMock()
        r2.completed_at = None
        r2.ttftc_seconds = None
        r2.steps_completed = {"choose_use_case": "ts"}

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [r1, r2]
        session.execute = AsyncMock(return_value=mock_result)

        stats = await repo.get_funnel_stats()
        assert stats["total_started"] == 2
        assert stats["total_completed"] == 1
        assert stats["avg_ttftc_seconds"] == 100.0
        assert stats["step_counts"]["choose_use_case"] == 2
        assert stats["step_counts"]["create_app"] == 1


# ── get_stalled_users ──


class TestGetStalledUsers:
    async def test_returns_stalled_users(self):
        session = _mock_session()
        repo = OnboardingRepository(session)

        stalled = MagicMock()
        stalled.user_id = "user-stalled"
        stalled.tenant_id = "acme"
        stalled.started_at = datetime.now(UTC) - timedelta(hours=30)
        stalled.steps_completed = {"choose_use_case": "2026-01-01T00:00:00"}

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [stalled]
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_stalled_users(stall_hours=24.0)
        assert len(result) == 1
        assert result[0]["user_id"] == "user-stalled"
        assert result[0]["tenant_id"] == "acme"

    async def test_returns_empty_when_none_stalled(self):
        session = _mock_session()
        repo = OnboardingRepository(session)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_stalled_users()
        assert result == []


# ── count_all ──


class TestCountAll:
    async def test_returns_count(self):
        session = _mock_session()
        repo = OnboardingRepository(session)

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 42
        session.execute = AsyncMock(return_value=mock_result)

        count = await repo.count_all()
        assert count == 42


# ── _percentile ──


class TestPercentile:
    def test_p50_of_single_value(self):
        assert _percentile([100], 50) == 100.0

    def test_p50_of_two_values(self):
        result = _percentile([10, 20], 50)
        assert result == 15.0

    def test_p90_of_list(self):
        values = list(range(1, 11))  # 1..10
        result = _percentile(values, 90)
        assert result >= 9.0

    def test_empty_list_returns_zero(self):
        assert _percentile([], 50) == 0.0

    def test_p100_returns_last(self):
        assert _percentile([5, 10, 15], 100) == 15.0


# ── _last_step ──


class TestLastStep:
    def test_returns_most_recent_step(self):
        steps = {
            "choose_use_case": "2026-01-01T10:00:00",
            "create_app": "2026-01-01T11:00:00",
        }
        result = _last_step(steps)
        assert result == "create_app"

    def test_returns_none_when_empty(self):
        assert _last_step({}) is None

    def test_returns_none_when_none(self):
        assert _last_step(None) is None

    def test_single_step(self):
        assert _last_step({"first_call": "2026-01-01T12:00:00"}) == "first_call"
