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


class UsageRecordCreate(BaseModel):
    """Request schema for recording LLM proxy usage from the gateway (CAB-1568)."""

    consumer_id: str = Field(..., min_length=1, max_length=255, description="Consumer key suffix")
    model: str = Field(..., min_length=1, max_length=100, description="LLM model identifier")
    input_tokens: int = Field(..., ge=0, description="Input tokens consumed")
    output_tokens: int = Field(..., ge=0, description="Output tokens consumed")
    provider: str = Field(default="anthropic", max_length=50, description="LLM provider name")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "consumer_id": "pane-backend",
                "model": "claude-sonnet-4-20250514",
                "input_tokens": 1500,
                "output_tokens": 800,
                "provider": "anthropic",
            }
        }
    )


class UsageRecordResponse(BaseModel):
    """Response after recording usage."""

    status: str = "recorded"
    input_tokens: int
    output_tokens: int
    total_tokens: int


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
