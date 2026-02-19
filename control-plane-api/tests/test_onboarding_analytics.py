"""Tests for onboarding analytics — funnel, stalled users, percentiles (CAB-1325 Phase 3)."""

from datetime import UTC, datetime

from src.repositories.onboarding import _last_step, _percentile
from src.routers.onboarding_admin import FUNNEL_STAGES
from src.schemas.onboarding import FunnelResponse, FunnelStage, StalledUserResponse


class TestPercentileHelper:
    """Test the _percentile helper function."""

    def test_p50_single_value(self):
        assert _percentile([42], 50) == 42.0

    def test_p50_two_values(self):
        result = _percentile([10, 20], 50)
        assert result == 15.0

    def test_p90_ten_values(self):
        values = list(range(10, 110, 10))  # [10, 20, ..., 100]
        result = _percentile(values, 90)
        # idx = 9 * 0.9 = 8.1 → interpolate between values[8]=90 and values[9]=100
        assert 90 <= result <= 100

    def test_p50_empty(self):
        assert _percentile([], 50) == 0.0

    def test_p0_returns_first(self):
        assert _percentile([5, 10, 15], 0) == 5.0

    def test_p100_returns_last(self):
        assert _percentile([5, 10, 15], 100) == 15.0


class TestLastStepHelper:
    """Test the _last_step helper function."""

    def test_none_steps(self):
        assert _last_step(None) is None

    def test_empty_steps(self):
        assert _last_step({}) is None

    def test_single_step(self):
        steps = {"choose_use_case": "2026-02-20T14:00:00"}
        assert _last_step(steps) == "choose_use_case"

    def test_multiple_steps_returns_latest(self):
        steps = {
            "choose_use_case": "2026-02-20T14:00:00",
            "create_app": "2026-02-20T14:00:10",
            "first_call": "2026-02-20T14:00:30",
        }
        assert _last_step(steps) == "first_call"

    def test_steps_with_none_values(self):
        steps = {
            "choose_use_case": "2026-02-20T14:00:00",
            "create_app": None,
            "first_call": None,
        }
        assert _last_step(steps) == "choose_use_case"


class TestFunnelStagesConstant:
    """Test the FUNNEL_STAGES used by the admin router."""

    def test_stage_order(self):
        assert FUNNEL_STAGES[0] == "registered"
        assert FUNNEL_STAGES[-1] == "first_call"

    def test_stage_count(self):
        assert len(FUNNEL_STAGES) == 5

    def test_includes_all_steps(self):
        assert "choose_use_case" in FUNNEL_STAGES
        assert "create_app" in FUNNEL_STAGES
        assert "subscribe_api" in FUNNEL_STAGES
        assert "first_call" in FUNNEL_STAGES


class TestFunnelResponseConstruction:
    """Test building FunnelResponse from repo stats."""

    def test_full_funnel(self):
        stats = {
            "total_started": 100,
            "total_completed": 40,
            "step_counts": {
                "choose_use_case": 90,
                "create_app": 70,
                "subscribe_api": 60,
                "first_call": 50,
            },
            "avg_ttftc_seconds": 45.2,
            "p50_ttftc_seconds": 30.0,
            "p90_ttftc_seconds": 90.0,
        }

        stages = []
        for stage_name in FUNNEL_STAGES:
            count = stats["total_started"] if stage_name == "registered" else stats["step_counts"].get(stage_name, 0)
            rate = count / stats["total_started"] if stats["total_started"] > 0 else None
            stages.append(FunnelStage(stage=stage_name, count=count, conversion_rate=rate))

        resp = FunnelResponse(
            stages=stages,
            total_started=stats["total_started"],
            total_completed=stats["total_completed"],
            avg_ttftc_seconds=stats["avg_ttftc_seconds"],
            p50_ttftc_seconds=stats["p50_ttftc_seconds"],
            p90_ttftc_seconds=stats["p90_ttftc_seconds"],
        )

        assert resp.total_started == 100
        assert resp.total_completed == 40
        assert len(resp.stages) == 5
        assert resp.stages[0].stage == "registered"
        assert resp.stages[0].count == 100
        assert resp.stages[0].conversion_rate == 1.0
        assert resp.stages[4].stage == "first_call"
        assert resp.stages[4].count == 50
        assert resp.stages[4].conversion_rate == 0.5
        assert resp.p50_ttftc_seconds == 30.0
        assert resp.p90_ttftc_seconds == 90.0

    def test_empty_funnel(self):
        stats = {
            "total_started": 0,
            "total_completed": 0,
            "step_counts": {},
            "avg_ttftc_seconds": None,
            "p50_ttftc_seconds": None,
            "p90_ttftc_seconds": None,
        }

        stages = []
        for stage_name in FUNNEL_STAGES:
            count = stats["total_started"] if stage_name == "registered" else stats["step_counts"].get(stage_name, 0)
            rate = count / stats["total_started"] if stats["total_started"] > 0 else None
            stages.append(FunnelStage(stage=stage_name, count=count, conversion_rate=rate))

        resp = FunnelResponse(
            stages=stages,
            total_started=0,
            total_completed=0,
        )

        assert resp.total_started == 0
        assert all(s.count == 0 for s in resp.stages)
        assert all(s.conversion_rate is None for s in resp.stages)


class TestStalledUserConstruction:
    """Test building StalledUserResponse from repo results."""

    def test_stalled_user_from_dict(self):
        now = datetime(2026, 2, 19, 10, 0, 0, tzinfo=UTC)
        data = {
            "user_id": "user-1",
            "tenant_id": "tenant-1",
            "last_step": "subscribe_api",
            "started_at": now,
            "hours_stalled": 26.5,
        }
        resp = StalledUserResponse(**data)
        assert resp.user_id == "user-1"
        assert resp.hours_stalled == 26.5
        assert resp.last_step == "subscribe_api"

    def test_stalled_user_no_step(self):
        now = datetime(2026, 2, 19, 10, 0, 0, tzinfo=UTC)
        data = {
            "user_id": "user-2",
            "tenant_id": "tenant-2",
            "last_step": None,
            "started_at": now,
            "hours_stalled": 48.0,
        }
        resp = StalledUserResponse(**data)
        assert resp.last_step is None
        assert resp.hours_stalled == 48.0
