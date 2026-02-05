"""
Schemas for Self-Service Logs API (CAB-793)
"""
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class LogStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    ALL = "all"


class LogLevel(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class LogQueryParams(BaseModel):
    """Query parameters for log search."""

    start_time: datetime | None = Field(
        default=None, description="Start of time range (defaults to 1 hour ago)"
    )
    end_time: datetime | None = Field(
        default=None, description="End of time range (defaults to now)"
    )
    tool_id: str | None = Field(
        default=None, description="Filter by specific tool/API ID"
    )
    status: LogStatus = Field(default=LogStatus.ALL, description="Filter by status")
    level: LogLevel | None = Field(default=None, description="Filter by log level")
    search: str | None = Field(
        default=None, max_length=200, description="Free text search in log messages"
    )
    limit: int = Field(default=50, ge=1, le=100, description="Number of results (max 100)")
    offset: int = Field(default=0, ge=0, description="Offset for pagination")

    model_config = ConfigDict(use_enum_values=True)


class LogEntryResponse(BaseModel):
    """Single log entry returned to consumer."""

    timestamp: datetime
    request_id: str
    tool_id: str | None = None
    tool_name: str | None = None
    level: str | None = None
    status: str
    status_code: int | None = None
    duration_ms: float | None = None
    message: str | None = None
    request_path: str | None = None
    request_method: str | None = None
    error_message: str | None = None

    model_config = ConfigDict(from_attributes=True)


class LogQueryResponse(BaseModel):
    """Paginated response for log query."""

    logs: list[LogEntryResponse]
    total: int
    limit: int
    offset: int
    has_more: bool
    query_time_ms: float
    time_range_start: datetime
    time_range_end: datetime


class LogExportRequest(BaseModel):
    """Request for CSV export."""

    start_time: datetime
    end_time: datetime
    tool_id: str | None = None
    status: LogStatus = LogStatus.ALL

    model_config = ConfigDict(use_enum_values=True)
