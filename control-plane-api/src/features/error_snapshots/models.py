"""Error Snapshot Pydantic models.

CAB-397: Time-travel debugging via error snapshots.
Captures complete request/response context when errors occur.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict


class SnapshotTrigger(str, Enum):
    """What triggered the snapshot capture."""

    ERROR_4XX = "4xx"
    ERROR_5XX = "5xx"
    TIMEOUT = "timeout"
    MANUAL = "manual"


class RequestSnapshot(BaseModel):
    """Captured HTTP request data."""

    method: str
    path: str
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any | None = None
    query_params: dict[str, str] = Field(default_factory=dict)
    client_ip: str | None = None
    user_agent: str | None = None


class ResponseSnapshot(BaseModel):
    """Captured HTTP response data."""

    status: int
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any | None = None
    duration_ms: int


class RoutingInfo(BaseModel):
    """API routing information at time of error."""

    api_name: str | None = None
    api_version: str | None = None
    route: str | None = None
    backend_url: str | None = None


class PolicyResult(BaseModel):
    """Result of a policy evaluation."""

    name: str
    result: str  # pass, fail, skip, timeout
    duration_ms: int = 0
    error: str | None = None


class BackendState(BaseModel):
    """Backend service state at time of error."""

    health: str = "unknown"  # healthy, degraded, unhealthy, unknown
    last_success: datetime | None = None
    error_rate_1m: float | None = None
    p99_latency_ms: int | None = None


class LogEntry(BaseModel):
    """Log entry captured around the error time."""

    timestamp: datetime
    level: str
    message: str
    extra: dict[str, Any] = Field(default_factory=dict)


class EnvironmentInfo(BaseModel):
    """Kubernetes/runtime environment info."""

    pod: str | None = None
    node: str | None = None
    namespace: str | None = None
    memory_percent: float | None = None
    cpu_percent: float | None = None


def _generate_snapshot_id() -> str:
    """Generate a unique snapshot ID with timestamp prefix."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    suffix = uuid4().hex[:8]
    return f"SNP-{ts}-{suffix}"


class ErrorSnapshot(BaseModel):
    """Complete error snapshot for time-travel debugging.

    Captures the full context of an error including:
    - Request/response data (with PII masked)
    - Routing and policy information
    - Backend state and health
    - Related log entries
    - Environment information
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "SNP-20260115-094512-a1b2c3d4",
                "timestamp": "2026-01-15T09:45:12.345Z",
                "tenant_id": "tenant-acme",
                "trigger": "5xx",
                "request": {
                    "method": "POST",
                    "path": "/api/v1/payments",
                    "headers": {"Content-Type": "application/json"},
                    "body": {"amount": 100},
                    "client_ip": "192.168.1.100",
                },
                "response": {
                    "status": 502,
                    "body": {"error": "upstream_timeout"},
                    "duration_ms": 30042,
                },
            }
        }
    )

    # Identifiers
    id: str = Field(default_factory=_generate_snapshot_id)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tenant_id: str

    # Trigger info
    trigger: SnapshotTrigger = SnapshotTrigger.ERROR_5XX

    # Request/Response
    request: RequestSnapshot
    response: ResponseSnapshot

    # Context
    routing: RoutingInfo = Field(default_factory=RoutingInfo)
    policies_applied: list[PolicyResult] = Field(default_factory=list)
    backend_state: BackendState = Field(default_factory=BackendState)

    # Observability
    logs: list[LogEntry] = Field(default_factory=list)
    trace_id: str | None = None
    span_id: str | None = None

    # Environment
    environment: EnvironmentInfo = Field(default_factory=EnvironmentInfo)

    # Metadata
    masked_fields: list[str] = Field(default_factory=list)
    source: str = "control-plane"  # "control-plane" | "webmethods-gateway"


class SnapshotSummary(BaseModel):
    """Lightweight snapshot summary for list views."""

    id: str
    timestamp: datetime
    tenant_id: str
    trigger: SnapshotTrigger
    status: int
    method: str
    path: str
    duration_ms: int
    source: str = "control-plane"


class SnapshotListResponse(BaseModel):
    """Paginated list of snapshots."""

    items: list[SnapshotSummary]
    total: int
    page: int
    page_size: int


class SnapshotFilters(BaseModel):
    """Filters for listing snapshots."""

    start_date: datetime | None = None
    end_date: datetime | None = None
    status_code: int | None = None
    trigger: SnapshotTrigger | None = None
    path_contains: str | None = None
    source: str | None = None  # Filter by source: "control-plane" | "webmethods-gateway"


class ReplayResponse(BaseModel):
    """Response for replay endpoint."""

    curl_command: str
    warning: str | None = None
