"""Diagnostic report schemas for auto-RCA and connectivity checks (CAB-1316)."""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field


class DiagnosticCategory(StrEnum):
    """Root cause categories for diagnostic classification."""

    CONNECTIVITY = "connectivity"
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    BACKEND = "backend"
    POLICY = "policy"
    CERTIFICATE = "certificate"
    CIRCUIT_BREAKER = "circuit_breaker"


class RootCause(BaseModel):
    """A classified root cause with confidence score."""

    category: DiagnosticCategory
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    evidence: list[str] = Field(default_factory=list)
    suggested_fix: str | None = None


class TimingBreakdown(BaseModel):
    """Timing breakdown for gateway and backend processing."""

    gateway_ms: float | None = None
    backend_ms: float | None = None
    total_ms: float | None = None


class RequestSummary(BaseModel):
    """GDPR-safe request summary — no body, no headers."""

    method: str | None = None
    path: str | None = None
    status_code: int | None = None
    request_id: str | None = None


class HopInfo(BaseModel):
    """A single hop in the network path (Via header)."""

    protocol: str
    pseudonym: str
    latency_ms: float | None = None


class NetworkPath(BaseModel):
    """Network path information from Via headers and intermediary detection."""

    hops: list[HopInfo] = Field(default_factory=list)
    total_hops: int = 0
    detected_intermediaries: list[str] = Field(default_factory=list)
    total_latency_ms: float | None = None


def _generate_diag_id() -> str:
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"DIAG-{ts}-{uuid4().hex[:8]}"


class DiagnosticReport(BaseModel):
    """Full diagnostic report with root causes and timing."""

    id: str = Field(default_factory=_generate_diag_id)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    tenant_id: str
    gateway_id: str
    root_causes: list[RootCause] = Field(default_factory=list)
    timing: TimingBreakdown = Field(default_factory=TimingBreakdown)
    request_summary: RequestSummary | None = None
    network_path: NetworkPath | None = None
    redacted: bool = True
    error_count: int = 0
    time_range_minutes: int = 60


class ConnectivityStage(BaseModel):
    """Result of a single connectivity check stage."""

    name: str
    status: str  # "ok", "error", "timeout"
    latency_ms: float | None = None
    error: str | None = None


class ConnectivityResult(BaseModel):
    """Multi-stage connectivity check result."""

    gateway_id: str
    overall_status: str  # "healthy", "degraded", "unhealthy"
    stages: list[ConnectivityStage] = Field(default_factory=list)
    network_path: NetworkPath | None = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DiagnosticListResponse(BaseModel):
    """Paginated list of diagnostic reports."""

    items: list[DiagnosticReport]
    total: int


class ErrorCategoryStat(BaseModel):
    """Error category with occurrence count."""

    category: DiagnosticCategory
    count: int
    percentage: float = 0.0


class DiagnosticSummaryResponse(BaseModel):
    """Aggregated diagnostic summary across all gateways."""

    tenant_id: str
    total_errors: int = 0
    time_range_minutes: int = 60
    top_categories: list[ErrorCategoryStat] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
