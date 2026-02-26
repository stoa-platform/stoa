"""SecurityFinding model — stores scanner results for posture dashboard (CAB-1461, CAB-1489)."""

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from ..database import Base


class SecurityFinding(Base):
    """Individual security finding from Trivy/Kubescape/custom scans."""

    __tablename__ = "security_findings"

    id = sa.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = sa.Column(sa.String(255), nullable=False, index=True)
    scan_id = sa.Column(UUID(as_uuid=True), nullable=False, index=True)
    scanner = sa.Column(sa.String(50), nullable=False)  # trivy, kubescape, secrets, custom
    severity = sa.Column(sa.String(20), nullable=False, index=True)  # critical, high, medium, low, info
    rule_id = sa.Column(sa.String(255), nullable=False)
    title = sa.Column(sa.String(500), nullable=False)  # CAB-1489: renamed from rule_name
    resource_type = sa.Column(sa.String(100), nullable=True)  # container, deployment, secret, ...
    resource_name = sa.Column(sa.String(500), nullable=True)
    description = sa.Column(sa.Text, nullable=True)
    remediation = sa.Column(sa.Text, nullable=True)
    details = sa.Column(JSONB, nullable=False, default=dict)
    status = sa.Column(sa.String(20), nullable=False, default="open")  # open, resolved, suppressed
    first_seen_at = sa.Column(sa.DateTime(), nullable=False, server_default=sa.text("now()"), index=True)
    created_at = sa.Column(sa.DateTime(), nullable=False, server_default=sa.text("now()"))
    resolved_at = sa.Column(sa.DateTime(), nullable=True)

    @property
    def rule_name(self) -> str:
        """Backward-compatible alias for title."""
        return self.title


class SecurityScan(Base):
    """A single scan execution record."""

    __tablename__ = "security_scans"

    id = sa.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = sa.Column(sa.String(255), nullable=False, index=True)
    scanner = sa.Column(sa.String(50), nullable=False)
    scan_type = sa.Column(sa.String(50), nullable=False, default="trivy")  # trivy, kubescape, custom
    status = sa.Column(sa.String(20), nullable=False, default="running")  # running, completed, failed
    findings_count = sa.Column(sa.Integer, nullable=False, default=0)
    critical_count = sa.Column(sa.Integer, nullable=False, default=0)
    high_count = sa.Column(sa.Integer, nullable=False, default=0)
    medium_count = sa.Column(sa.Integer, nullable=False, default=0)
    low_count = sa.Column(sa.Integer, nullable=False, default=0)
    score = sa.Column(sa.Float, nullable=True)  # 0-100, calculated after scan
    scan_duration_ms = sa.Column(sa.Integer, nullable=True)  # scan wall-clock time in ms
    started_at = sa.Column(sa.DateTime(), nullable=False, server_default=sa.text("now()"))
    completed_at = sa.Column(sa.DateTime(), nullable=True)
    details = sa.Column(JSONB, nullable=False, default=dict)


class SecurityBaseline(Base):
    """Golden state baseline per tenant for drift detection."""

    __tablename__ = "security_baselines"

    id = sa.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = sa.Column(sa.String(255), nullable=False, unique=True)
    baseline = sa.Column(JSONB, nullable=False, default=dict)  # {rule_id: expected_status}
    created_at = sa.Column(sa.DateTime(), nullable=False, server_default=sa.text("now()"))
    updated_at = sa.Column(sa.DateTime(), nullable=True, onupdate=sa.text("now()"))
