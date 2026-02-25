"""Pydantic schemas for Security Posture Dashboard (CAB-1461)."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class FindingSeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class FindingStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


class ScannerType(StrEnum):
    TRIVY = "trivy"
    KUBESCAPE = "kubescape"
    SECRETS = "secrets"


# --- Response schemas ---


class SecurityFindingResponse(BaseModel):
    """A single finding from a security scan."""

    id: str
    tenant_id: str
    scan_id: str
    scanner: str
    severity: FindingSeverity
    rule_id: str
    rule_name: str
    resource_type: str | None = None
    resource_name: str | None = None
    description: str | None = None
    remediation: str | None = None
    status: FindingStatus
    created_at: datetime
    resolved_at: datetime | None = None


class FindingsListResponse(BaseModel):
    """Paginated list of findings."""

    findings: list[SecurityFindingResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class SeverityBreakdown(BaseModel):
    """Finding counts per severity level."""

    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0


class SecurityScoreResponse(BaseModel):
    """Security score for a tenant."""

    tenant_id: str
    score: float = Field(..., ge=0, le=100, description="Security score 0-100")
    grade: str = Field(..., description="Letter grade A-F")
    findings_summary: SeverityBreakdown
    total_findings: int
    open_findings: int
    last_scan_at: datetime | None = None
    trend: float | None = Field(None, description="Score change vs previous scan")


class ComplianceControl(BaseModel):
    """A single compliance control mapping."""

    control_id: str
    framework: str  # DORA, NIS2, PCI-DSS
    article: str
    description: str
    status: str  # compliant, non_compliant, partial, not_assessed
    findings_count: int = 0


class ComplianceScoreResponse(BaseModel):
    """Compliance posture per framework."""

    tenant_id: str
    framework: str
    score: float = Field(..., ge=0, le=100)
    controls: list[ComplianceControl]
    compliant_count: int
    total_controls: int


class DriftAlert(BaseModel):
    """A drift from the golden state baseline."""

    rule_id: str
    rule_name: str
    expected_status: str
    actual_status: str
    severity: FindingSeverity
    detected_at: datetime


class DriftReportResponse(BaseModel):
    """Drift detection report."""

    tenant_id: str
    baseline_date: datetime | None = None
    drifts: list[DriftAlert]
    total_drifts: int
    has_baseline: bool


class SecretsHealthItem(BaseModel):
    """Health status of a single secret."""

    name: str
    path: str
    age_days: int
    status: str  # healthy, expiring_soon, expired, orphan
    last_rotated: datetime | None = None


class SecretsHealthResponse(BaseModel):
    """Overall secrets health report."""

    tenant_id: str
    total_secrets: int
    healthy: int
    expiring_soon: int
    expired: int
    orphan: int
    secrets: list[SecretsHealthItem]


class SecurityScanResponse(BaseModel):
    """A scan execution record."""

    id: str
    tenant_id: str
    scanner: str
    status: str
    findings_count: int
    score: float | None = None
    started_at: datetime
    completed_at: datetime | None = None


class ScanHistoryResponse(BaseModel):
    """List of past scans."""

    scans: list[SecurityScanResponse]
    total: int


# --- Request schemas ---


class IngestFindingsRequest(BaseModel):
    """Bulk ingest findings from a scanner."""

    scan_id: str
    scanner: ScannerType
    findings: list[dict] = Field(..., description="Raw findings from scanner")


class SetBaselineRequest(BaseModel):
    """Set golden state baseline for a tenant."""

    baseline: dict = Field(..., description="Map of rule_id -> expected status")
