"""Scoped API key model for SaaS MCP access (CAB-1188/CAB-1249)."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum as SQLEnum, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from src.database import Base


class SaasApiKeyStatus(enum.StrEnum):
    """API key lifecycle status."""

    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class SaasApiKey(Base):
    """Scoped API key for tenant MCP access.

    Each key is scoped to a set of backend APIs (by ID) and optionally
    rate-limited. Keys are hashed (SHA-256) for storage; the plaintext
    is returned only once at creation time.

    Prefix format: stoa_saas_ + 4 hex chars (for identification in logs).
    """

    __tablename__ = "saas_api_keys"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Tenant ownership
    tenant_id = Column(String(255), nullable=False, index=True)

    # Identity
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Key material (hashed)
    key_hash = Column(String(512), nullable=False, unique=True)
    key_prefix = Column(String(20), nullable=False)

    # Scoping — list of backend_api IDs this key can access
    allowed_backend_api_ids = Column(JSONB, nullable=False, default=list)

    # Rate limiting
    rate_limit_rpm = Column(Integer, nullable=True)

    # Status
    status = Column(
        SQLEnum(
            SaasApiKeyStatus,
            values_callable=lambda x: [e.value for e in x],
            name="saas_api_key_status_enum",
        ),
        nullable=False,
        default=SaasApiKeyStatus.ACTIVE,
    )

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)

    # Audit
    created_by = Column(String(255), nullable=True)

    # Indexes
    __table_args__ = (
        Index("ix_saas_api_keys_tenant_name", "tenant_id", "name", unique=True),
        Index("ix_saas_api_keys_tenant_status", "tenant_id", "status"),
        Index("ix_saas_api_keys_prefix", "key_prefix"),
    )

    def __repr__(self) -> str:
        return f"<SaasApiKey {self.id} name={self.name} tenant={self.tenant_id}>"
