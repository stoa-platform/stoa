"""Pydantic schemas for Usage Metering endpoints (CAB-1334 Phase 1)."""

from datetime import datetime

from pydantic import BaseModel


class ToolUsage(BaseModel):
    """Per-tool usage aggregation."""

    tool_name: str
    request_count: int
    token_count: int
    error_count: int
    avg_latency_ms: float | None = None


class UsageSummary(BaseModel):
    """Aggregated usage summary for a time range."""

    tenant_id: str
    period_type: str
    period_start: datetime
    period_end: datetime
    total_requests: int
    total_tokens: int
    total_errors: int
    avg_latency_ms: float | None = None
    tools: list[ToolUsage] = []


class UsageDetailItem(BaseModel):
    """Single usage record in the details list."""

    period_start: datetime
    period_end: datetime
    request_count: int
    token_count: int
    error_count: int
    avg_latency_ms: float | None = None


class UsageDetailResponse(BaseModel):
    """Paginated detail response."""

    tenant_id: str
    tool_name: str | None = None
    period_type: str
    items: list[UsageDetailItem] = []
    total: int = 0
