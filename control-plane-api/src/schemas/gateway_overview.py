"""Schemas for the Gateway Detail overview read-model."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class GatewayOverviewSyncStatus(StrEnum):
    """Gateway overview sync status."""

    IN_SYNC = "in_sync"
    PENDING = "pending"
    DRIFT = "drift"
    FAILED = "failed"
    UNKNOWN = "unknown"


class GatewayOverviewRuntimeStatus(StrEnum):
    """Gateway overview runtime status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    STALE = "stale"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class GatewayOverviewMetricsStatus(StrEnum):
    """Gateway overview metrics status."""

    AVAILABLE = "available"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class GatewayOverviewDataQualitySeverity(StrEnum):
    """Data-quality warning severity."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class GatewayOverviewRuntimeFreshness(StrEnum):
    """Freshness of runtime data."""

    FRESH = "fresh"
    STALE = "stale"
    MISSING = "missing"


class GatewayOverviewWarning(BaseModel):
    """Stable data-quality warning returned by the overview endpoint."""

    code: str
    severity: GatewayOverviewDataQualitySeverity
    message: str


class GatewayOverviewGateway(BaseModel):
    """Basic gateway identity for the overview page."""

    id: UUID
    name: str
    display_name: str
    gateway_type: str
    environment: str
    status: str
    mode: str | None = None
    version: str | None = None


class GatewayOverviewVisibility(BaseModel):
    """RBAC visibility metadata for the response."""

    rbac_scope: str
    tenant_id: str | None = None
    filtered: bool


class GatewayOverviewSource(BaseModel):
    """Top-level source metadata for the overview read-model."""

    control_plane_revision: str | None = None
    last_loaded_at: datetime | None = None


class GatewayOverviewApiSource(BaseModel):
    """Per-API source metadata."""

    git_path: str | None = None
    git_commit_sha: str | None = None
    spec_hash: str | None = None


class GatewayOverviewRoutePreview(BaseModel):
    """Compact route preview row for the UI."""

    method: str
    path: str
    backend: str | None = None


class GatewayOverviewApi(BaseModel):
    """API deployment as interpreted for the Gateway Detail page."""

    tenant_id: str
    api_id: str
    api_catalog_id: UUID
    name: str
    version: str
    source: GatewayOverviewApiSource
    routes_count: int
    routes_preview: list[GatewayOverviewRoutePreview] = Field(default_factory=list)
    backend: str | None = None
    policies_count: int
    sync_status: GatewayOverviewSyncStatus
    last_sync_at: datetime | None = None
    last_error: str | None = None


class GatewayOverviewPolicyTarget(BaseModel):
    """Effective policy target."""

    type: str
    id: str | None = None
    name: str | None = None


class GatewayOverviewPolicyBindingSource(BaseModel):
    """Source binding used to resolve an effective policy."""

    id: UUID
    scope: str
    target_id: str | None = None


class GatewayOverviewPolicy(BaseModel):
    """Effective enabled policy visible on a gateway."""

    id: UUID
    name: str
    type: str
    scope: str
    target: GatewayOverviewPolicyTarget
    enabled: bool
    priority: int
    summary: str
    sync_status: GatewayOverviewSyncStatus
    source_binding: GatewayOverviewPolicyBindingSource


class GatewayOverviewResolvedConfig(BaseModel):
    """Expected Control Plane configuration, without runtime data."""

    apis: list[GatewayOverviewApi] = Field(default_factory=list)
    policies: list[GatewayOverviewPolicy] = Field(default_factory=list)


class GatewayOverviewSync(BaseModel):
    """Gateway reconciliation state, without runtime metrics."""

    desired_generation: int | None = None
    applied_generation: int | None = None
    status: GatewayOverviewSyncStatus
    drift: bool
    last_reconciled_at: datetime | None = None
    last_error: str | None = None
    steps: list[dict] = Field(default_factory=list)


class GatewayOverviewRuntime(BaseModel):
    """Observed dataplane runtime state."""

    status: GatewayOverviewRuntimeStatus
    last_heartbeat_at: datetime | None = None
    heartbeat_age_seconds: int | None = None
    version: str | None = None
    mode: str | None = None
    uptime_seconds: int | None = None
    reported_routes_count: int | None = None
    reported_policies_count: int | None = None
    mcp_tools_count: int | None = None
    requests_total: int | None = None
    error_rate: float | None = None
    memory_usage_bytes: int | None = None


class GatewayOverviewDataQuality(BaseModel):
    """Freshness and partial-data metadata."""

    runtime_freshness: GatewayOverviewRuntimeFreshness
    heartbeat_stale_after_seconds: int
    metrics_status: GatewayOverviewMetricsStatus
    metrics_window_seconds: int | None = None
    warnings: list[GatewayOverviewWarning] = Field(default_factory=list)


class GatewayOverviewSummary(BaseModel):
    """Top-level values used by Gateway Detail summary cards."""

    sync_status: GatewayOverviewSyncStatus
    runtime_status: GatewayOverviewRuntimeStatus
    metrics_status: GatewayOverviewMetricsStatus
    apis_count: int
    expected_routes_count: int
    reported_routes_count: int | None = None
    effective_policies_count: int
    reported_policies_count: int | None = None
    failed_policies_count: int


class GatewayOverviewResponse(BaseModel):
    """Gateway Detail overview read-model."""

    schema_version: str = "1.0"
    generated_at: datetime
    gateway: GatewayOverviewGateway
    visibility: GatewayOverviewVisibility
    source: GatewayOverviewSource
    summary: GatewayOverviewSummary
    resolved_config: GatewayOverviewResolvedConfig
    sync: GatewayOverviewSync
    runtime: GatewayOverviewRuntime
    data_quality: GatewayOverviewDataQuality
