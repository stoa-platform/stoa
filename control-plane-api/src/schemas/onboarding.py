"""Pydantic schemas for onboarding endpoints (CAB-1325)."""

from datetime import datetime

from pydantic import BaseModel, Field


class OnboardingStepUpdate(BaseModel):
    """Request body for marking a step complete (optional metadata)."""

    metadata: dict | None = None


class OnboardingProgressResponse(BaseModel):
    """Current onboarding progress for a user."""

    tenant_id: str
    user_id: str
    steps_completed: dict = Field(default_factory=dict)
    started_at: datetime
    completed_at: datetime | None = None
    ttftc_seconds: int | None = None
    is_complete: bool = False

    model_config = {"from_attributes": True}


class OnboardingCompleteResponse(BaseModel):
    """Response when onboarding is marked complete."""

    completed: bool
    ttftc_seconds: int | None = None


# Phase 2 — Trial key info (metadata only, NOT plaintext)
class TrialKeyResponse(BaseModel):
    """Trial API key metadata (returned by GET /v1/me/onboarding/trial-key)."""

    key_prefix: str
    name: str
    rate_limit_rpm: int
    expires_at: datetime | None = None
    status: str
    created_at: datetime


# Phase 3 — Funnel analytics
class FunnelStage(BaseModel):
    """A single stage in the onboarding funnel."""

    stage: str
    count: int
    conversion_rate: float | None = None


class FunnelResponse(BaseModel):
    """Onboarding funnel analytics."""

    stages: list[FunnelStage]
    total_started: int
    total_completed: int
    avg_ttftc_seconds: float | None = None
    p50_ttftc_seconds: float | None = None
    p90_ttftc_seconds: float | None = None


class StalledUserResponse(BaseModel):
    """User stuck in onboarding for too long."""

    user_id: str
    tenant_id: str
    last_step: str | None = None
    started_at: datetime
    hours_stalled: float
