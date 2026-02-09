"""Consumer SQLAlchemy model for external API consumers."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum as SQLEnum, Index, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID

from src.database import Base


class ConsumerStatus(enum.StrEnum):
    """Consumer status enum."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    BLOCKED = "blocked"


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
        SQLEnum(ConsumerStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ConsumerStatus.ACTIVE,
    )

    # Metadata (JSON for custom attributes)
    consumer_metadata = Column(JSON, nullable=True)

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
    )

    def __repr__(self) -> str:
        return f"<Consumer {self.id} name={self.name} tenant={self.tenant_id}>"
