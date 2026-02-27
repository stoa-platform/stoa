"""Pydantic schemas for usage metering pipeline (CAB-1334 Phase 1)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UsageSummaryResponse(BaseModel):
    """Single usage summary record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: str
    api_id: UUID
    consumer_id: UUID | None = None
    period: str
    period_start: datetime
    request_count: int = 0
    error_count: int = 0
    total_latency_ms: int = 0
    p99_latency_ms: int | None = None
    total_tokens: int = 0
    created_at: datetime
    updated_at: datetime


class UsageSummaryListResponse(BaseModel):
    """Paginated list of usage summaries."""

    items: list[UsageSummaryResponse]
    total: int
    limit: int
    offset: int


class UsageRecordRequest(BaseModel):
    """Gateway-submitted usage event (CAB-1568: LLM proxy metering)."""

    tenant_id: str = Field(..., description="Tenant ID from API key validation")
    subscription_id: str = Field(..., description="Subscription ID from API key validation")
    endpoint: str = Field(default="/v1/messages", description="API endpoint called")
    request_count: int = Field(default=1, ge=0, description="Number of requests")
    total_tokens: int = Field(default=0, ge=0, description="Total tokens (input + output)")
    input_tokens: int = Field(default=0, ge=0, description="Input tokens")
    output_tokens: int = Field(default=0, ge=0, description="Output tokens")
    total_latency_ms: int = Field(default=0, ge=0, description="Request latency in ms")


class UsageDetailResponse(BaseModel):
    """Detailed usage breakdown for a specific API."""

    api_id: UUID
    tenant_id: str
    period: str
    period_start: datetime
    total_requests: int = 0
    total_errors: int = 0
    error_rate: float = Field(default=0.0, description="Error rate as a percentage")
    avg_latency_ms: float = Field(default=0.0, description="Average latency in milliseconds")
    p99_latency_ms: int | None = None
    total_tokens: int = 0
