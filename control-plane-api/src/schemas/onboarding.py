"""Onboarding schemas — Pydantic v2 request/response models (CAB-1325)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class OnboardingStepUpdate(BaseModel):
    """No body required — step name is in the URL path."""


class OnboardingProgressResponse(BaseModel):
    """Full onboarding progress response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    user_id: str
    steps_completed: dict[str, str | None]
    started_at: datetime
    completed_at: datetime | None = None
    ttftc_seconds: int | None = None
    is_complete: bool = False


class OnboardingCompleteResponse(BaseModel):
    """Response from completing onboarding."""

    completed_at: datetime
    ttftc_seconds: int | None = None


class TrialKeyResponse(BaseModel):
    """Trial API key metadata (Phase 2 — not plaintext)."""

    key_prefix: str
    name: str
    rate_limit_rpm: int | None = None
    expires_at: datetime | None = None
    created_at: datetime


# Phase 3 — Analytics schemas

class FunnelStage(BaseModel):
    """Single stage in the onboarding funnel."""

    stage: str
    count: int
    conversion_rate: float | None = None


class FunnelResponse(BaseModel):
    """Full funnel analytics response."""

    stages: list[FunnelStage]
    total_started: int
    total_completed: int
    avg_ttftc_seconds: float | None = None
    p50_ttftc_seconds: float | None = None
    p90_ttftc_seconds: float | None = None


class StalledUserResponse(BaseModel):
    """User who started but hasn't completed onboarding."""

    user_id: str
    tenant_id: str
    last_step: str | None = None
    started_at: datetime
    hours_stalled: float
