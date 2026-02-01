"""Portal Executions data models.

CAB-432: Consumer-facing execution view with simplified error taxonomy.
Black-box philosophy — consumer sees WHAT happened, never HOW.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ErrorSource(str, Enum):
    """Where the error originated (consumer-visible)."""

    GATEWAY = "gateway"
    BACKEND = "backend"
    TOOL = "tool"
    KAFKA = "kafka"
    CLIENT = "client"


class ErrorCategory(str, Enum):
    """Simplified error category for consumers."""

    AUTH_FAILED = "auth_failed"
    RATE_LIMIT = "rate_limit"
    FORBIDDEN = "forbidden"
    TIMEOUT = "timeout"
    BAD_GATEWAY = "bad_gateway"
    UNAVAILABLE = "unavailable"
    TOOL_ERROR = "tool_error"
    KAFKA_ERROR = "kafka_error"
    BAD_REQUEST = "bad_request"
    NOT_FOUND = "not_found"


class ExecutionError(BaseModel):
    """A single execution error visible to the consumer."""

    id: str
    timestamp: datetime
    method: str
    path: str
    status_code: int
    duration_ms: int
    error_source: ErrorSource
    error_category: ErrorCategory
    summary: str
    help_text: str
    suggested_action: str
    trace_id: str = Field(
        description="Reference ID for support escalation",
    )


class ExecutionStats(BaseModel):
    """Aggregated execution statistics for an app."""

    total_calls_24h: int = 0
    success_rate: float = 0.0
    avg_latency_ms: float = 0.0
    error_count_24h: int = 0


class ExecutionSummary(BaseModel):
    """Complete execution summary for a consumer app."""

    app_id: str
    app_name: str
    api_key_hint: str = Field(
        description="Masked API key, e.g. sk-***abc",
    )
    stats: ExecutionStats
    recent_errors: list[ExecutionError] = []
    degraded: bool = False
    degraded_services: list[str] = []
