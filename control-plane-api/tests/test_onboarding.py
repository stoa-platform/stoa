"""Tests for onboarding progress model, schemas, and steps (CAB-1325)."""

from datetime import UTC, datetime

from src.schemas.onboarding import (
    FunnelResponse,
    FunnelStage,
    OnboardingCompleteResponse,
    OnboardingProgressResponse,
    StalledUserResponse,
    TrialKeyResponse,
)


class TestOnboardingProgressModel:
    """Test OnboardingProgress SQLAlchemy model."""

    def test_model_import(self):
        from src.models.onboarding_progress import OnboardingProgress

        assert OnboardingProgress.__tablename__ == "onboarding_progress"

    def test_model_columns(self):
        from src.models.onboarding_progress import OnboardingProgress

        columns = {c.name for c in OnboardingProgress.__table__.columns}
        expected = {"id", "tenant_id", "user_id", "steps_completed", "started_at", "completed_at", "ttftc_seconds"}
        assert expected == columns

    def test_unique_constraint(self):
        from src.models.onboarding_progress import OnboardingProgress

        constraints = [c.name for c in OnboardingProgress.__table__.constraints if hasattr(c, "name") and c.name]
        assert "uq_onboarding_tenant_user" in constraints


class TestOnboardingStepUpdate:
    """Test OnboardingStepUpdate schema."""

    def test_empty_body(self):
        from src.schemas.onboarding import OnboardingStepUpdate

        update = OnboardingStepUpdate()
        assert update is not None

    def test_schema_name(self):
        from src.schemas.onboarding import OnboardingStepUpdate

        assert OnboardingStepUpdate.__name__ == "OnboardingStepUpdate"


class TestOnboardingProgressResponse:
    """Test OnboardingProgressResponse schema."""

    def test_full_response(self):
        now = datetime(2026, 2, 20, 14, 0, 0, tzinfo=UTC)
        resp = OnboardingProgressResponse(
            id="abc-123",
            tenant_id="tenant-1",
            user_id="user-1",
            steps_completed={"choose_use_case": "2026-02-20T14:00:00", "subscribe_api": None},
            started_at=now,
            completed_at=None,
            ttftc_seconds=None,
            is_complete=False,
        )
        assert resp.id == "abc-123"
        assert resp.tenant_id == "tenant-1"
        assert resp.is_complete is False
        assert resp.steps_completed["choose_use_case"] == "2026-02-20T14:00:00"

    def test_completed_response(self):
        now = datetime(2026, 2, 20, 14, 0, 0, tzinfo=UTC)
        completed = datetime(2026, 2, 20, 14, 0, 45, tzinfo=UTC)
        resp = OnboardingProgressResponse(
            id="abc-456",
            tenant_id="tenant-1",
            user_id="user-1",
            steps_completed={
                "choose_use_case": "2026-02-20T14:00:00",
                "subscribe_api": "2026-02-20T14:00:10",
                "create_app": "2026-02-20T14:00:20",
                "first_call": "2026-02-20T14:00:30",
            },
            started_at=now,
            completed_at=completed,
            ttftc_seconds=30,
            is_complete=True,
        )
        assert resp.is_complete is True
        assert resp.ttftc_seconds == 30
        assert resp.completed_at == completed


class TestOnboardingCompleteResponse:
    """Test OnboardingCompleteResponse schema."""

    def test_complete_response(self):
        now = datetime(2026, 2, 20, 14, 0, 45, tzinfo=UTC)
        resp = OnboardingCompleteResponse(completed_at=now, ttftc_seconds=45)
        assert resp.completed_at == now
        assert resp.ttftc_seconds == 45

    def test_complete_without_ttftc(self):
        now = datetime(2026, 2, 20, 14, 0, 45, tzinfo=UTC)
        resp = OnboardingCompleteResponse(completed_at=now)
        assert resp.ttftc_seconds is None


class TestTrialKeyResponse:
    """Test TrialKeyResponse schema (Phase 2)."""

    def test_trial_key_metadata(self):
        now = datetime(2026, 2, 20, 14, 0, 0, tzinfo=UTC)
        resp = TrialKeyResponse(
            key_prefix="stoa_trial_abc",
            name="trial-key",
            rate_limit_rpm=100,
            expires_at=datetime(2026, 3, 22, 14, 0, 0, tzinfo=UTC),
            created_at=now,
        )
        assert resp.key_prefix == "stoa_trial_abc"
        assert resp.rate_limit_rpm == 100


class TestOnboardingSteps:
    """Test valid step names used by the router."""

    def test_valid_steps_constant(self):
        from src.routers.onboarding import VALID_STEPS

        assert "choose_use_case" in VALID_STEPS
        assert "subscribe_api" in VALID_STEPS
        assert "create_app" in VALID_STEPS
        assert "first_call" in VALID_STEPS
        assert len(VALID_STEPS) == 4

    def test_invalid_step_not_in_list(self):
        from src.routers.onboarding import VALID_STEPS

        assert "invalid_step" not in VALID_STEPS

    def test_step_order_convention(self):
        from src.routers.onboarding import VALID_STEPS

        assert VALID_STEPS[0] == "choose_use_case"
        assert VALID_STEPS[-1] == "first_call"


class TestFunnelResponse:
    """Test FunnelResponse schema (Phase 3)."""

    def test_funnel_with_stages(self):
        resp = FunnelResponse(
            stages=[
                FunnelStage(stage="registered", count=100, conversion_rate=1.0),
                FunnelStage(stage="tenant_provisioned", count=80, conversion_rate=0.8),
                FunnelStage(stage="first_tool_call", count=50, conversion_rate=0.625),
            ],
            total_started=100,
            total_completed=40,
            avg_ttftc_seconds=45.2,
        )
        assert len(resp.stages) == 3
        assert resp.total_started == 100
        assert resp.avg_ttftc_seconds == 45.2

    def test_empty_funnel(self):
        resp = FunnelResponse(stages=[], total_started=0, total_completed=0)
        assert len(resp.stages) == 0
        assert resp.p50_ttftc_seconds is None


class TestStalledUserResponse:
    """Test StalledUserResponse schema (Phase 3)."""

    def test_stalled_user(self):
        now = datetime(2026, 2, 19, 10, 0, 0, tzinfo=UTC)
        resp = StalledUserResponse(
            user_id="user-1",
            tenant_id="tenant-1",
            last_step="subscribe_api",
            started_at=now,
            hours_stalled=26.5,
        )
        assert resp.hours_stalled == 26.5
        assert resp.last_step == "subscribe_api"

    def test_stalled_user_no_step(self):
        now = datetime(2026, 2, 19, 10, 0, 0, tzinfo=UTC)
        resp = StalledUserResponse(
            user_id="user-2",
            tenant_id="tenant-2",
            last_step=None,
            started_at=now,
            hours_stalled=48.0,
        )
        assert resp.last_step is None
