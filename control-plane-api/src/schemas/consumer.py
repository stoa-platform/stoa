"""Pydantic schemas for consumer endpoints (CAB-1121 + CAB-864)."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConsumerStatusEnum(StrEnum):
    """Consumer status enum for API responses."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    BLOCKED = "blocked"


class CertificateStatusEnum(StrEnum):
    """Certificate lifecycle status for API responses (CAB-864)."""

    ACTIVE = "active"
    ROTATING = "rotating"
    REVOKED = "revoked"
    EXPIRED = "expired"


class ConsumerCreate(BaseModel):
    """Schema for creating a new consumer."""

    external_id: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., min_length=1, max_length=255)
    company: str | None = Field(None, max_length=255)
    description: str | None = None
    keycloak_user_id: str | None = Field(None, max_length=255)
    consumer_metadata: dict | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "external_id": "partner-acme-001",
                "name": "ACME Corp",
                "email": "api@acme.com",
                "company": "ACME Corporation",
                "description": "Strategic API partner",
            }
        }
    )


class ConsumerUpdate(BaseModel):
    """Schema for updating an existing consumer."""

    name: str | None = Field(None, min_length=1, max_length=255)
    email: str | None = Field(None, min_length=1, max_length=255)
    company: str | None = Field(None, max_length=255)
    description: str | None = None
    keycloak_user_id: str | None = Field(None, max_length=255)
    consumer_metadata: dict | None = None


class ConsumerResponse(BaseModel):
    """Schema for consumer response."""

    id: UUID
    external_id: str
    name: str
    email: str
    company: str | None
    description: str | None
    tenant_id: str
    keycloak_user_id: str | None
    keycloak_client_id: str | None = None
    status: ConsumerStatusEnum
    consumer_metadata: dict | None
    certificate_fingerprint: str | None = None
    certificate_status: str | None = None
    certificate_subject_dn: str | None = None
    certificate_not_before: datetime | None = None
    certificate_not_after: datetime | None = None
    last_rotated_at: datetime | None = None
    rotation_count: int | None = None
    created_at: datetime
    updated_at: datetime
    created_by: str | None

    model_config = ConfigDict(from_attributes=True)


class ConsumerCredentialsResponse(BaseModel):
    """Schema for one-time credential display after consumer activation."""

    consumer_id: UUID
    client_id: str
    client_secret: str
    token_endpoint: str
    grant_type: str = "client_credentials"


class ConsumerListResponse(BaseModel):
    """Schema for paginated consumer list."""

    items: list[ConsumerResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class CertificateRotateRequest(BaseModel):
    """Schema for certificate rotation request (CAB-864)."""

    certificate_pem: str = Field(..., min_length=1, description="New PEM-encoded X.509 certificate")
    grace_period_hours: int = Field(
        default=24, ge=1, le=720, description="Hours during which both certs are valid"
    )


class BulkResultItem(BaseModel):
    """Result of a single row in bulk onboarding."""

    row: int
    status: str
    external_id: str | None = None
    consumer_id: UUID | None = None
    client_id: str | None = None
    client_secret: str | None = None
    error: str | None = None


class BulkResultResponse(BaseModel):
    """Response for bulk onboarding endpoint."""

    total: int
    success: int
    failed: int
    results: list[BulkResultItem]
