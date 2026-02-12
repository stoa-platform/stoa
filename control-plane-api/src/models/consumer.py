"""Consumer SQLAlchemy model for external API consumers."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum as SQLEnum, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID

from src.database import Base


class ConsumerStatus(enum.StrEnum):
    """Consumer status enum."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    BLOCKED = "blocked"


class CertificateStatus(enum.StrEnum):
    """Certificate lifecycle status (CAB-864)."""

    ACTIVE = "active"
    ROTATING = "rotating"
    REVOKED = "revoked"
    EXPIRED = "expired"


class Consumer(Base):
    """Consumer model - represents an external API consumer (company, partner, developer)."""

    __tablename__ = "consumers"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identity
    external_id = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    company = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)

    # Tenant (the API provider)
    tenant_id = Column(String(255), nullable=False, index=True)

    # Optional Keycloak link
    keycloak_user_id = Column(String(255), nullable=True, index=True)
    keycloak_client_id = Column(String(255), nullable=True, index=True)

    # Status
    status = Column(
        SQLEnum(ConsumerStatus, values_callable=lambda x: [e.value for e in x], name="consumer_status_enum"),
        nullable=False,
        default=ConsumerStatus.ACTIVE,
    )

    # Metadata (JSON for custom attributes)
    consumer_metadata = Column(JSON, nullable=True)

    # mTLS Certificate fields (CAB-864)
    certificate_fingerprint = Column(String(64), nullable=True)
    certificate_fingerprint_previous = Column(String(64), nullable=True)
    certificate_subject_dn = Column(String(500), nullable=True)
    certificate_issuer_dn = Column(String(500), nullable=True)
    certificate_serial = Column(String(64), nullable=True)
    certificate_not_before = Column(DateTime(timezone=True), nullable=True)
    certificate_not_after = Column(DateTime(timezone=True), nullable=True)
    certificate_pem = Column(Text, nullable=True)
    certificate_status = Column(String(20), nullable=True, default="active")
    previous_cert_expires_at = Column(DateTime(timezone=True), nullable=True)
    last_rotated_at = Column(DateTime(timezone=True), nullable=True)
    rotation_count = Column(Integer, nullable=True, default=0)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Audit
    created_by = Column(String(255), nullable=True)

    # Indexes
    __table_args__ = (
        Index("ix_consumers_tenant_external", "tenant_id", "external_id", unique=True),
        Index("ix_consumers_tenant_status", "tenant_id", "status"),
        Index("ix_consumers_email", "email"),
        Index("ix_consumers_fingerprint", "certificate_fingerprint"),
        Index("ix_consumers_fingerprint_prev", "certificate_fingerprint_previous"),
    )

    def __repr__(self) -> str:
        return f"<Consumer {self.id} name={self.name} tenant={self.tenant_id}>"
