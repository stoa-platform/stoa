"""Pydantic schemas for execution log endpoints (CAB-1318)."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ExecutionStatusEnum(StrEnum):
    """Execution status for API responses."""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


class ErrorCategoryEnum(StrEnum):
    """Error category for API responses."""

    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    BACKEND = "backend"
    TIMEOUT = "timeout"
    VALIDATION = "validation"


class ExecutionLogResponse(BaseModel):
    """Full execution log entry."""

    id: str
    tenant_id: str
    consumer_id: str | None = None
    api_id: str | None = None
    api_name: str | None = None
    tool_name: str | None = None
    request_id: str
    method: str | None = None
    path: str | None = None
    status_code: int | None = None
    status: ExecutionStatusEnum
    error_category: ErrorCategoryEnum | None = None
    error_message: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int | None = None
    request_headers: dict | None = None
    response_summary: dict | None = None

    model_config = ConfigDict(from_attributes=True)


class ExecutionLogSummary(BaseModel):
    """Abbreviated execution log for list views."""

    id: str
    api_name: str | None = None
    tool_name: str | None = None
    request_id: str
    method: str | None = None
    path: str | None = None
    status_code: int | None = None
    status: ExecutionStatusEnum
    error_category: ErrorCategoryEnum | None = None
    error_message: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int | None = None

    model_config = ConfigDict(from_attributes=True)


class ExecutionLogListResponse(BaseModel):
    """Paginated list of execution logs."""

    items: list[ExecutionLogSummary]
    total: int
    page: int
    page_size: int


class TaxonomyItem(BaseModel):
    """Single error category aggregate."""

    category: str
    count: int
    avg_duration_ms: float | None = None
    percentage: float


class ErrorTaxonomyResponse(BaseModel):
    """Aggregated error taxonomy."""

    items: list[TaxonomyItem]
    total_errors: int
    total_executions: int
    error_rate: float = Field(description="Error rate as percentage")


class ExecutionQueryParams(BaseModel):
    """Query parameters for execution log filtering."""

    consumer_id: str | None = None
    api_id: str | None = None
    status: ExecutionStatusEnum | None = None
    error_category: ErrorCategoryEnum | None = None
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
