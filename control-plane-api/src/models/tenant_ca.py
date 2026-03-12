"""Tenant CA model — per-tenant Certificate Authority keypair (CAB-1787).

Stores the CA certificate and encrypted private key for each tenant,
enabling server-side CSR signing for consumer mTLS onboarding.
"""

import uuid as uuid_mod

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from src.database import Base


class TenantCA(Base):
    """Per-tenant Certificate Authority keypair."""

    __tablename__ = "tenant_cas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_mod.uuid4)
    tenant_id = Column(
        String(64),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # CA certificate (PEM-encoded, public — safe to expose via API)
    ca_certificate_pem = Column(Text, nullable=False)

    # CA private key (PEM-encoded, Fernet-encrypted at rest — NEVER exposed via API)
    encrypted_private_key = Column(Text, nullable=False)

    # Certificate metadata
    subject_dn = Column(String(500), nullable=False)
    serial_number = Column(String(128), nullable=False)
    not_before = Column(DateTime(timezone=True), nullable=False)
    not_after = Column(DateTime(timezone=True), nullable=False)
    key_algorithm = Column(String(32), nullable=False, default="RSA-4096")
    fingerprint_sha256 = Column(String(64), nullable=False)

    # Status: active, revoked
    status = Column(String(32), nullable=False, default="active")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_tenant_cas_tenant_id", "tenant_id"),
        Index("ix_tenant_cas_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<TenantCA(tenant_id='{self.tenant_id}', status='{self.status}')>"
