"""CredentialMapping SQLAlchemy model for per-consumer backend credentials (CAB-1432).

Maps a consumer's OAuth2 identity to a specific backend API credential,
enabling per-consumer credential injection at the gateway.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SQLEnum, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class CredentialAuthType(enum.StrEnum):
    """Backend credential type for injection."""

    API_KEY = "api_key"
    BEARER = "bearer"
    BASIC = "basic"


class CredentialMapping(Base):
    """Maps a consumer to a backend API credential.

    Unique constraint: one credential per consumer per API.
    The encrypted_value is Fernet-encrypted and never returned in API responses.
    """

    __tablename__ = "credential_mappings"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign references (not FK constraints — soft references for flexibility)
    consumer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    api_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Credential config
    auth_type: Mapped[CredentialAuthType] = mapped_column(
        SQLEnum(CredentialAuthType, values_callable=lambda x: [e.value for e in x], name="credential_auth_type"),
        nullable=False,
    )
    header_name: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)

    # Metadata
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Audit
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        UniqueConstraint("consumer_id", "api_id", name="uq_credential_mappings_consumer_api"),
        Index("ix_credential_mappings_consumer_api_active", "consumer_id", "api_id", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<CredentialMapping {self.id} consumer={self.consumer_id} api={self.api_id}>"
