"""SecurityFinding model — stores scanner results for posture dashboard (CAB-1461)."""

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from ..database import Base


class SecurityFinding(Base):
    """Individual security finding from Trivy/Kubescape scans."""

    __tablename__ = "security_findings"

    id = sa.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = sa.Column(sa.String(255), nullable=False, index=True)
    scan_id = sa.Column(UUID(as_uuid=True), nullable=False, index=True)
    scanner = sa.Column(sa.String(50), nullable=False)  # trivy, kubescape, secrets
    severity = sa.Column(sa.String(20), nullable=False, index=True)  # critical, high, medium, low, info
    rule_id = sa.Column(sa.String(255), nullable=False)
    rule_name = sa.Column(sa.String(500), nullable=False)
    resource_type = sa.Column(sa.String(100), nullable=True)  # container, deployment, secret, ...
    resource_name = sa.Column(sa.String(500), nullable=True)
    description = sa.Column(sa.Text, nullable=True)
    remediation = sa.Column(sa.Text, nullable=True)
    details = sa.Column(JSONB, nullable=False, default=dict)
    status = sa.Column(sa.String(20), nullable=False, default="open")  # open, resolved, suppressed
    created_at = sa.Column(sa.DateTime(), nullable=False, server_default=sa.text("now()"), index=True)
    resolved_at = sa.Column(sa.DateTime(), nullable=True)


class SecurityScan(Base):
    """A single scan execution record."""

    __tablename__ = "security_scans"

    id = sa.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = sa.Column(sa.String(255), nullable=False, index=True)
    scanner = sa.Column(sa.String(50), nullable=False)
    status = sa.Column(sa.String(20), nullable=False, default="running")  # running, completed, failed
    findings_count = sa.Column(sa.Integer, nullable=False, default=0)
    score = sa.Column(sa.Float, nullable=True)  # 0-100, calculated after scan
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
