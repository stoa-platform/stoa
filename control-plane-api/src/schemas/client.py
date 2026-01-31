"""
Pydantic Schemas for Client Certificate Provisioning (CAB-865)
"""
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ClientStatusEnum(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class ClientCreate(BaseModel):
    """Create a new client. CN is auto-generated from name."""
    name: str = Field(..., min_length=1, max_length=255, description="Client display name")

    model_config = ConfigDict(
        json_schema_extra={"example": {"name": "my-api-consumer"}}
    )


class ClientResponse(BaseModel):
    """Client details (never includes private key)."""
    id: UUID
    tenant_id: str
    name: str
    certificate_cn: str
    certificate_serial: Optional[str] = None
    certificate_fingerprint: Optional[str] = None
    certificate_pem: Optional[str] = None
    certificate_not_before: Optional[datetime] = None
    certificate_not_after: Optional[datetime] = None
    status: ClientStatusEnum
    created_at: datetime
    updated_at: datetime
    # Rotation fields (CAB-869)
    certificate_fingerprint_previous: Optional[str] = None
    previous_cert_expires_at: Optional[datetime] = None
    is_in_grace_period: bool = False
    last_rotated_at: Optional[datetime] = None
    rotation_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class ClientWithCertificate(ClientResponse):
    """Client with private key — returned ONE TIME only at creation/rotation."""
    private_key_pem: str = Field(..., description="PEM-encoded private key. Save immediately — not retrievable again.")
    grace_period_ends: Optional[datetime] = None


class CertificateRotateRequest(BaseModel):
    """Request to rotate a client certificate."""
    reason: str = Field(default="rotation", max_length=255, description="Reason for rotation")
    grace_period_hours: Optional[int] = Field(None, ge=1, le=168, description="Grace period in hours (default from config)")
