"""Tests for onboarding progress model, schemas, and router (CAB-1325)."""

import pytest
from datetime import datetime, UTC

from src.models.onboarding_progress import OnboardingProgress
from src.schemas.onboarding import (
    FunnelResponse,
    FunnelStage,
    OnboardingCompleteResponse,
    OnboardingProgressResponse,
    OnboardingStepUpdate,
    StalledUserResponse,
    TrialKeyResponse,
)
from src.routers.onboarding import VALID_STEPS, TRIAL_KEY_NAME, TRIAL_KEY_RPM, TRIAL_KEY_DAYS


# ============== Model Tests ==============


class TestOnboardingProgressModel:
    """OnboardingProgress SQLAlchemy model tests."""

    def test_model_has_required_columns(self):
        columns = {c.name for c in OnboardingProgress.__table__.columns}
        expected = {
            "id", "tenant_id", "user_id", "steps_completed",
            "started_at", "completed_at", "ttftc_seconds",
        }
        assert expected.issubset(columns)

    def test_tablename(self):
        assert OnboardingProgress.__tablename__ == "onboarding_progress"

    def test_unique_constraint_exists(self):
        constraints = [c.name for c in OnboardingProgress.__table__.constraints if hasattr(c, "name")]
        assert "uq_onboarding_tenant_user" in constraints

    def test_repr(self):
        obj = OnboardingProgress(tenant_id="t1", user_id="u1")
        r = repr(obj)
        assert "t1" in r
        assert "u1" in r


# ============== Schema Tests ==============


class TestOnboardingSchemas:
    """Pydantic schema validation tests."""

    def test_step_update_optional_metadata(self):
        s = OnboardingStepUpdate()
        assert s.metadata is None

    def test_step_update_with_metadata(self):
        s = OnboardingStepUpdate(metadata={"use_case": "rest-api"})
        assert s.metadata["use_case"] == "rest-api"

    def test_progress_response_defaults(self):
        now = datetime.now(UTC)
        r = OnboardingProgressResponse(
            tenant_id="t1", user_id="u1", started_at=now,
        )
        assert r.is_complete is False
        assert r.steps_completed == {}
        assert r.ttftc_seconds is None

    def test_progress_response_complete(self):
        now = datetime.now(UTC)
        r = OnboardingProgressResponse(
            tenant_id="t1", user_id="u1", started_at=now,
            completed_at=now, ttftc_seconds=45, is_complete=True,
        )
        assert r.is_complete is True
        assert r.ttftc_seconds == 45

    def test_complete_response(self):
        r = OnboardingCompleteResponse(completed=True, ttftc_seconds=30)
        assert r.completed is True

    def test_trial_key_response(self):
        now = datetime.now(UTC)
        r = TrialKeyResponse(
            key_prefix="stoa_trial_ab12",
            name="trial-key",
            rate_limit_rpm=100,
            expires_at=now,
            status="active",
            created_at=now,
        )
        assert r.key_prefix.startswith("stoa_trial_")


# ============== Constants Tests ==============


class TestOnboardingConstants:
    """Verify step names and trial key constants."""

    def test_valid_steps(self):
        assert "choose_use_case" in VALID_STEPS
        assert "create_app" in VALID_STEPS
        assert "subscribe_api" in VALID_STEPS
        assert "first_call" in VALID_STEPS
        assert len(VALID_STEPS) == 4

    def test_trial_key_name(self):
        assert TRIAL_KEY_NAME == "trial-key"

    def test_trial_key_rpm(self):
        assert TRIAL_KEY_RPM == 100

    def test_trial_key_days(self):
        assert TRIAL_KEY_DAYS == 30


# ============== Funnel Schema Tests ==============


class TestFunnelSchemas:
    """Phase 3 analytics schema tests."""

    def test_funnel_stage(self):
        s = FunnelStage(stage="registered", count=100, conversion_rate=0.85)
        assert s.stage == "registered"
        assert s.conversion_rate == 0.85

    def test_funnel_response(self):
        stages = [
            FunnelStage(stage="registered", count=100),
            FunnelStage(stage="tenant_provisioned", count=85, conversion_rate=0.85),
        ]
        r = FunnelResponse(
            stages=stages, total_started=100, total_completed=50,
            avg_ttftc_seconds=42.5,
        )
        assert len(r.stages) == 2
        assert r.total_completed == 50

    def test_stalled_user_response(self):
        now = datetime.now(UTC)
        r = StalledUserResponse(
            user_id="u1", tenant_id="t1",
            last_step="create_app", started_at=now, hours_stalled=26.5,
        )
        assert r.hours_stalled > 24
