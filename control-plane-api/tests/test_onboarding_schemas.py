"""Tests for Onboarding Pydantic schemas (CAB-1452).

Validates serialization, field types, defaults, and edge cases
for all onboarding request/response schemas.
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.schemas.onboarding import (
    FunnelResponse,
    FunnelStage,
    OnboardingCompleteResponse,
    OnboardingProgressResponse,
    OnboardingStepUpdate,
    StalledUserResponse,
    TrialKeyResponse,
)

# =============================================================================
# OnboardingStepUpdate
# =============================================================================


class TestOnboardingStepUpdate:
    def test_empty_body_valid(self):
        """No fields required — step name comes from URL path."""
        s = OnboardingStepUpdate()
        assert s is not None


# =============================================================================
# OnboardingProgressResponse
# =============================================================================


class TestOnboardingProgressResponse:
    def _sample(self, **overrides):
        defaults = {
            "id": "prog-123",
            "tenant_id": "acme",
            "user_id": "user-1",
            "steps_completed": {"welcome": "2026-01-01T00:00:00", "api_call": None},
            "started_at": datetime(2026, 1, 1, tzinfo=UTC),
            "completed_at": None,
            "ttftc_seconds": None,
            "is_complete": False,
        }
        defaults.update(overrides)
        return defaults

    def test_valid(self):
        r = OnboardingProgressResponse(**self._sample())
        assert r.tenant_id == "acme"
        assert r.is_complete is False
        assert len(r.steps_completed) == 2

    def test_completed(self):
        r = OnboardingProgressResponse(
            **self._sample(
                completed_at=datetime(2026, 1, 1, 0, 5, tzinfo=UTC),
                ttftc_seconds=300,
                is_complete=True,
            )
        )
        assert r.is_complete is True
        assert r.ttftc_seconds == 300

    def test_is_complete_default_false(self):
        data = self._sample()
        del data["is_complete"]
        r = OnboardingProgressResponse(**data)
        assert r.is_complete is False

    def test_from_attributes_config(self):
        assert OnboardingProgressResponse.model_config.get("from_attributes") is True

    def test_steps_completed_empty_dict(self):
        r = OnboardingProgressResponse(**self._sample(steps_completed={}))
        assert r.steps_completed == {}

    def test_steps_completed_with_none_values(self):
        """Steps can have None values (step marked but no timestamp)."""
        r = OnboardingProgressResponse(**self._sample(steps_completed={"step1": None}))
        assert r.steps_completed["step1"] is None


# =============================================================================
# OnboardingCompleteResponse
# =============================================================================


class TestOnboardingCompleteResponse:
    def test_valid(self):
        r = OnboardingCompleteResponse(
            completed_at=datetime(2026, 1, 1, 0, 10, tzinfo=UTC),
            ttftc_seconds=600,
        )
        assert r.ttftc_seconds == 600

    def test_ttftc_optional(self):
        r = OnboardingCompleteResponse(completed_at=datetime(2026, 1, 1, tzinfo=UTC))
        assert r.ttftc_seconds is None

    def test_completed_at_required(self):
        with pytest.raises(ValidationError):
            OnboardingCompleteResponse()


# =============================================================================
# TrialKeyResponse
# =============================================================================


class TestTrialKeyResponse:
    def test_valid(self):
        r = TrialKeyResponse(
            key_prefix="stoa_trial_abc",
            name="My Trial Key",
            rate_limit_rpm=60,
            expires_at=datetime(2026, 2, 1, tzinfo=UTC),
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        assert r.key_prefix == "stoa_trial_abc"
        assert r.rate_limit_rpm == 60

    def test_optional_fields(self):
        r = TrialKeyResponse(
            key_prefix="stoa_trial_xyz",
            name="Basic Key",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        assert r.rate_limit_rpm is None
        assert r.expires_at is None


# =============================================================================
# FunnelStage / FunnelResponse
# =============================================================================


class TestFunnelStage:
    def test_valid(self):
        s = FunnelStage(stage="welcome", count=100, conversion_rate=0.85)
        assert s.stage == "welcome"
        assert s.conversion_rate == 0.85

    def test_conversion_rate_optional(self):
        s = FunnelStage(stage="welcome", count=100)
        assert s.conversion_rate is None


class TestFunnelResponse:
    def test_valid(self):
        r = FunnelResponse(
            stages=[FunnelStage(stage="welcome", count=100)],
            total_started=100,
            total_completed=50,
            avg_ttftc_seconds=120.5,
        )
        assert r.total_completed == 50
        assert len(r.stages) == 1

    def test_optional_percentile_fields(self):
        r = FunnelResponse(stages=[], total_started=0, total_completed=0)
        assert r.avg_ttftc_seconds is None
        assert r.p50_ttftc_seconds is None
        assert r.p90_ttftc_seconds is None


# =============================================================================
# StalledUserResponse
# =============================================================================


class TestStalledUserResponse:
    def test_valid(self):
        r = StalledUserResponse(
            user_id="user-1",
            tenant_id="acme",
            last_step="api_call",
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
            hours_stalled=48.5,
        )
        assert r.hours_stalled == 48.5
        assert r.last_step == "api_call"

    def test_last_step_optional(self):
        r = StalledUserResponse(
            user_id="user-1",
            tenant_id="acme",
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
            hours_stalled=24.0,
        )
        assert r.last_step is None

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            StalledUserResponse(user_id="user-1")
