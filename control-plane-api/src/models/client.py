"""
Client Model with mTLS Certificate Support

CAB-865: mTLS API Client Certificate Provisioning

Security Notes:
- Private key is NEVER stored - returned ONE TIME at creation
- tenant_id comes from JWT only, never from request body
- Soft delete via deleted_at for audit trail
"""
import uuid
import enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Column, String, DateTime, Text, Index, Enum as SAEnum
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from src.database import Base


class AuthType(str, enum.Enum):
    """Client authentication type."""
    OAUTH2 = "oauth2"
    MTLS = "mtls"
    MTLS_OAUTH2 = "mtls_oauth2"


class ClientStatus(str, enum.Enum):
    """Client lifecycle status."""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"  # Certificate revoked


class Client(Base):
    """
    API Client with optional mTLS certificate.

    Security Notes:
    - Private key is NEVER stored - returned ONE TIME at creation
    - tenant_id comes from JWT only, never from request body
    - Soft delete via deleted_at for audit trail
    """
    __tablename__ = "clients"

    # Primary key
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique client identifier"
    )

    # Tenant isolation (from JWT only)
    tenant_id = Column(
        String(64),
        nullable=False,
        index=True,
        comment="Tenant ID - always from JWT, never from body"
    )

    # Client identity
    name = Column(
        String(100),
        nullable=False,
        comment="Client name - unique per tenant"
    )
    description = Column(
        String(500),
        nullable=True,
        comment="Optional description"
    )

    # Authentication
    auth_type = Column(
        SAEnum(AuthType, name='auth_type_enum', create_type=True),
        nullable=False,
        default=AuthType.OAUTH2,
        comment="Authentication method"
    )

    # Status
    status = Column(
        SAEnum(ClientStatus, name='client_status_enum', create_type=True),
        nullable=False,
        default=ClientStatus.ACTIVE,
        index=True,
        comment="Client lifecycle status"
    )

    # Certificate metadata (NO private key)
    certificate_fingerprint_sha256 = Column(
        String(128),
        unique=True,
        index=True,
        nullable=True,
        comment="SHA256 fingerprint for identification"
    )
    certificate_serial = Column(
        String(128),
        unique=True,
        nullable=True,
        comment="Certificate serial number (hex)"
    )
    certificate_subject = Column(
        String(256),
        nullable=True,
        comment="Certificate subject DN"
    )
    certificate_issuer = Column(
        String(256),
        nullable=True,
        comment="Certificate issuer DN"
    )
    certificate_valid_from = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Certificate not_before"
    )
    certificate_valid_until = Column(
        DateTime(timezone=True),
        nullable=True,
        index=True,  # Index for expiration queries
        comment="Certificate not_after"
    )
    certificate_revoked_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When certificate was revoked"
    )
    certificate_revoked_by = Column(
        String(255),
        nullable=True,
        comment="Who revoked the certificate"
    )
    certificate_revocation_reason = Column(
        String(500),
        nullable=True,
        comment="Why certificate was revoked"
    )

    # Vault reference (for revocation)
    vault_pki_serial = Column(
        String(128),
        nullable=True,
        comment="Vault PKI serial for revocation API"
    )

    # Audit trail
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Creation timestamp"
    )
    created_by = Column(
        String(255),
        nullable=False,
        comment="User who created the client"
    )
    updated_at = Column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
        comment="Last update timestamp"
    )
    updated_by = Column(
        String(255),
        nullable=True,
        comment="User who last updated"
    )

    # Soft delete
    deleted_at = Column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Soft delete timestamp - null means active"
    )
    deleted_by = Column(
        String(255),
        nullable=True,
        comment="User who deleted"
    )

    __table_args__ = (
        # Unique name per tenant (only for non-deleted)
        Index(
            'ix_clients_tenant_name_active',
            'tenant_id',
            'name',
            unique=True,
            postgresql_where=(deleted_at.is_(None))
        ),
        # Index for certificate expiration monitoring
        Index(
            'ix_clients_cert_expiry',
            'certificate_valid_until',
            postgresql_where=(certificate_valid_until.isnot(None))
        ),
        {'comment': 'API Clients with optional mTLS certificates'}
    )

    @property
    def is_deleted(self) -> bool:
        """Check if client is soft-deleted."""
        return self.deleted_at is not None

    @property
    def is_certificate_valid(self) -> bool:
        """Check if certificate is currently valid."""
        if not self.certificate_valid_until:
            return False
        if self.certificate_revoked_at:
            return False
        now = datetime.now(timezone.utc)
        return now < self.certificate_valid_until

    @property
    def days_until_expiry(self) -> Optional[int]:
        """Days until certificate expires (negative if expired)."""
        if not self.certificate_valid_until:
            return None
        now = datetime.now(timezone.utc)
        delta = self.certificate_valid_until - now
        return delta.days

    def __repr__(self) -> str:
        return f"<Client id={self.id} name={self.name} tenant={self.tenant_id}>"
