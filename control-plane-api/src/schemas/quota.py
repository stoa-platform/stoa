"""Pydantic schemas for quota enforcement endpoints (CAB-1121 Phase 4)."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class QuotaUsageResponse(BaseModel):
    """Full quota usage row."""

    id: UUID
    consumer_id: UUID
    subscription_id: UUID | None
    tenant_id: str
    request_count_daily: int
    request_count_monthly: int
    bandwidth_bytes_daily: int
    bandwidth_bytes_monthly: int
    period_start_daily: date
    period_start_monthly: date
    last_reset_at: datetime | None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class QuotaLimits(BaseModel):
    """Plan limits sub-object."""

    daily_request_limit: int | None
    monthly_request_limit: int | None


class QuotaCounters(BaseModel):
    """Current usage counters."""

    daily: int
    monthly: int


class QuotaRemaining(BaseModel):
    """Remaining quota before hitting limits."""

    daily: int | None
    monthly: int | None


class QuotaResets(BaseModel):
    """Timestamps when counters reset."""

    daily: datetime
    monthly: datetime


class QuotaStatusResponse(BaseModel):
    """Consumer-facing quota status."""

    consumer_id: UUID
    tenant_id: str
    plan: QuotaLimits
    usage: QuotaCounters
    remaining: QuotaRemaining
    resets_at: QuotaResets


class QuotaListResponse(BaseModel):
    """Paginated list of quota usage for admin."""

    items: list[QuotaUsageResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class TopConsumer(BaseModel):
    """Top consumer by request count."""

    consumer_id: UUID
    request_count_monthly: int


class NearLimitConsumer(BaseModel):
    """Consumer approaching their quota limit."""

    consumer_id: UUID
    request_count_monthly: int
    monthly_limit: int
    usage_percent: float


class QuotaStatsResponse(BaseModel):
    """Aggregate quota stats for admin."""

    total_requests_today: int
    total_requests_month: int
    top_consumers: list[TopConsumer]
    near_limit: list[NearLimitConsumer]


class QuotaExceededResponse(BaseModel):
    """429 response body when quota exceeded."""

    error: str = "quota_exceeded"
    detail: str
    limit: int
    current: int
    resets_at: datetime
