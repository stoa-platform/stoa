"""Signed Certificate model — tracks all certificates issued by a tenant CA.

Stores public certificate metadata (never the private key) for lifecycle
management: revocation, expiry monitoring, and future FAPI 2.0 certificate
binding (RFC 8705 — cnf.x5t#S256 in JWT).
"""

import uuid as uuid_mod
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class SignedCertificate(Base):
    """A certificate signed by a tenant CA."""

    __tablename__ = "signed_certificates"

    id: Mapped[uuid_mod.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_mod.uuid4)
    tenant_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("tenants.id", ondelete="CASCADE"),
    )
    ca_id: Mapped[uuid_mod.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenant_cas.id", ondelete="CASCADE"),
    )

    # Optional binding to a consumer (FAPI 2.0 prep — nullable until bound)
    consumer_id: Mapped[uuid_mod.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("consumers.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Certificate metadata (public — safe to expose)
    subject_dn: Mapped[str] = mapped_column(String(500))
    issuer_dn: Mapped[str] = mapped_column(String(500))
    serial_number: Mapped[str] = mapped_column(String(128))
    not_before: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    not_after: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    key_algorithm: Mapped[str] = mapped_column(String(32), default="RSA-4096")

    # SHA-256 fingerprint of the DER-encoded certificate (used for x5t#S256 binding)
    fingerprint_sha256: Mapped[str] = mapped_column(String(64), unique=True)

    # The signed certificate PEM (public, no private key)
    certificate_pem: Mapped[str] = mapped_column(Text)

    # Status: active, revoked
    status: Mapped[str] = mapped_column(String(32), default="active")

    # Who requested the signing
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Timestamps
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_signed_certs_tenant_id", "tenant_id"),
        Index("ix_signed_certs_ca_id", "ca_id"),
        Index("ix_signed_certs_consumer_id", "consumer_id"),
        Index("ix_signed_certs_status", "status"),
        Index("ix_signed_certs_fingerprint", "fingerprint_sha256"),
        Index("ix_signed_certs_not_after", "not_after"),
    )

    def __repr__(self) -> str:
        return f"<SignedCertificate(subject='{self.subject_dn}', status='{self.status}')>"
