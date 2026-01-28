"""
Pydantic schemas for client endpoints

CAB-865: mTLS API Client Certificate Provisioning
"""
from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from enum import Enum
import re


class AuthTypeEnum(str, Enum):
    """Client authentication type."""
    OAUTH2 = "oauth2"
    MTLS = "mtls"
    MTLS_OAUTH2 = "mtls_oauth2"


class ClientStatusEnum(str, Enum):
    """Client lifecycle status."""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class ClientCreate(BaseModel):
    """Schema for creating a new client."""
    name: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="Client name - alphanumeric with dash/underscore only"
    )
    description: Optional[str] = Field(
        None,
        max_length=500,
        description="Optional description"
    )
    auth_type: AuthTypeEnum = Field(
        default=AuthTypeEnum.OAUTH2,
        description="Authentication method"
    )
    certificate_validity_days: int = Field(
        default=365,
        ge=1,
        le=730,
        description="Certificate validity in days (1-730)"
    )
    certificate_key_size: int = Field(
        default=4096,
        ge=2048,
        le=8192,
        description="RSA key size in bits (2048-8192)"
    )

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """
        Validate client name to prevent injection.

        Security (N3m0):
        - Must start with letter
        - Only alphanumeric, dash, underscore allowed
        - 3-100 characters
        """
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_-]{2,99}$', v):
            raise ValueError(
                'Name must start with a letter and contain only '
                'alphanumeric characters, dashes, and underscores (3-100 chars)'
            )
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "billing-service",
                "description": "Backend billing service",
                "auth_type": "mtls_oauth2",
                "certificate_validity_days": 365,
                "certificate_key_size": 4096
            }
        }
    )


class ClientUpdate(BaseModel):
    """Schema for updating a client."""
    description: Optional[str] = Field(None, max_length=500)
    status: Optional[ClientStatusEnum] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "description": "Updated description",
                "status": "suspended"
            }
        }
    )


class CertificateBundleResponse(BaseModel):
    """
    One-time certificate bundle response.

    WARNING: private_key_pem is returned ONCE ONLY at creation.
    Store it securely - it cannot be retrieved again.
    """
    certificate_pem: str = Field(..., description="X.509 certificate in PEM format")
    private_key_pem: str = Field(..., description="Private key in PEM format - ONE TIME ONLY")
    ca_chain_pem: str = Field(..., description="CA certificate chain in PEM format")
    fingerprint_sha256: str = Field(..., description="Certificate SHA-256 fingerprint")
    serial_number: str = Field(..., description="Certificate serial number (hex)")
    expires_at: datetime = Field(..., description="Certificate expiration timestamp")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "certificate_pem": "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----",
                "private_key_pem": "-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----",
                "ca_chain_pem": "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----",
                "fingerprint_sha256": "a1b2c3d4e5f6...",
                "serial_number": "1234567890abcdef",
                "expires_at": "2026-01-28T12:00:00Z"
            }
        }
    )


class CertificateInfoResponse(BaseModel):
    """Certificate metadata (no private key)."""
    fingerprint_sha256: str
    serial_number: str
    subject: str
    issuer: str
    valid_from: datetime
    valid_until: datetime
    days_until_expiry: int
    is_valid: bool
    is_revoked: bool
    revoked_at: Optional[datetime] = None
    revoked_by: Optional[str] = None
    revocation_reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ClientResponse(BaseModel):
    """Schema for client response."""
    id: UUID
    tenant_id: str
    name: str
    description: Optional[str]
    auth_type: AuthTypeEnum
    status: ClientStatusEnum
    certificate_info: Optional[CertificateInfoResponse] = None
    created_at: datetime
    created_by: str
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_model(cls, client) -> 'ClientResponse':
        """Create response from Client model."""
        cert_info = None
        if client.certificate_fingerprint_sha256:
            cert_info = CertificateInfoResponse(
                fingerprint_sha256=client.certificate_fingerprint_sha256,
                serial_number=client.certificate_serial or "",
                subject=client.certificate_subject or "",
                issuer=client.certificate_issuer or "",
                valid_from=client.certificate_valid_from,
                valid_until=client.certificate_valid_until,
                days_until_expiry=client.days_until_expiry or 0,
                is_valid=client.is_certificate_valid,
                is_revoked=client.certificate_revoked_at is not None,
                revoked_at=client.certificate_revoked_at,
                revoked_by=client.certificate_revoked_by,
                revocation_reason=client.certificate_revocation_reason,
            )

        return cls(
            id=client.id,
            tenant_id=client.tenant_id,
            name=client.name,
            description=client.description,
            auth_type=AuthTypeEnum(client.auth_type.value),
            status=ClientStatusEnum(client.status.value),
            certificate_info=cert_info,
            created_at=client.created_at,
            created_by=client.created_by,
            updated_at=client.updated_at,
        )


class ClientCreateResponse(BaseModel):
    """Response for client creation."""
    client: ClientResponse
    certificate_bundle: Optional[CertificateBundleResponse] = Field(
        None,
        description="Certificate bundle - only for mTLS auth types, returned ONE TIME ONLY"
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Any warnings (e.g., mock provider usage)"
    )


class ClientListResponse(BaseModel):
    """Schema for paginated client list."""
    items: List[ClientResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class CertificateRevokeRequest(BaseModel):
    """Schema for revoking a certificate."""
    reason: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Reason for revocation"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "reason": "Certificate compromised"
            }
        }
    )


class CertificateRenewResponse(BaseModel):
    """Response for certificate renewal."""
    client: ClientResponse
    certificate_bundle: CertificateBundleResponse = Field(
        ...,
        description="New certificate bundle - returned ONE TIME ONLY"
    )
    previous_fingerprint: str = Field(
        ...,
        description="Fingerprint of the revoked previous certificate"
    )
