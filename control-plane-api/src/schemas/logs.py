"""
Schemas for Self-Service Logs API (CAB-793)
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, Field


class LogStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    ALL = "all"


class LogLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class LogQueryParams(BaseModel):
    """Query parameters for log search."""

    start_time: Optional[datetime] = Field(
        default=None, description="Start of time range (defaults to 1 hour ago)"
    )
    end_time: Optional[datetime] = Field(
        default=None, description="End of time range (defaults to now)"
    )
    tool_id: Optional[str] = Field(
        default=None, description="Filter by specific tool/API ID"
    )
    status: LogStatus = Field(default=LogStatus.ALL, description="Filter by status")
    level: Optional[LogLevel] = Field(default=None, description="Filter by log level")
    search: Optional[str] = Field(
        default=None, max_length=200, description="Free text search in log messages"
    )
    limit: int = Field(default=50, ge=1, le=100, description="Number of results (max 100)")
    offset: int = Field(default=0, ge=0, description="Offset for pagination")

    model_config = ConfigDict(use_enum_values=True)


class LogEntryResponse(BaseModel):
    """Single log entry returned to consumer."""

    timestamp: datetime
    request_id: str
    tool_id: Optional[str] = None
    tool_name: Optional[str] = None
    level: Optional[str] = None
    status: str
    status_code: Optional[int] = None
    duration_ms: Optional[float] = None
    message: Optional[str] = None
    request_path: Optional[str] = None
    request_method: Optional[str] = None
    error_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class LogQueryResponse(BaseModel):
    """Paginated response for log query."""

    logs: List[LogEntryResponse]
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
    tool_id: Optional[str] = None
    status: LogStatus = LogStatus.ALL

    model_config = ConfigDict(use_enum_values=True)
