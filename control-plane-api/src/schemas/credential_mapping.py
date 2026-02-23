"""Pydantic schemas for credential mapping endpoints (CAB-1432)."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CredentialAuthTypeEnum(StrEnum):
    """Backend credential type."""

    API_KEY = "api_key"
    BEARER = "bearer"
    BASIC = "basic"


class CredentialMappingCreate(BaseModel):
    """Schema for creating a credential mapping."""

    consumer_id: UUID
    api_id: str = Field(..., min_length=1, max_length=255)
    auth_type: CredentialAuthTypeEnum
    header_name: str = Field(..., min_length=1, max_length=255)
    credential_value: str = Field(..., min_length=1, description="Plaintext credential (encrypted at rest)")
    description: str | None = Field(None, max_length=500)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "consumer_id": "550e8400-e29b-41d4-a716-446655440000",
                "api_id": "weather-api-v1",
                "auth_type": "api_key",
                "header_name": "X-API-Key",
                "credential_value": "sk-live-abc123...",
                "description": "ACME Corp production API key",
            }
        }
    )


class CredentialMappingUpdate(BaseModel):
    """Schema for updating a credential mapping."""

    auth_type: CredentialAuthTypeEnum | None = None
    header_name: str | None = Field(None, min_length=1, max_length=255)
    credential_value: str | None = Field(None, min_length=1, description="New credential value (re-encrypted)")
    description: str | None = Field(None, max_length=500)
    is_active: bool | None = None


class CredentialMappingResponse(BaseModel):
    """Schema for credential mapping response (value never exposed)."""

    id: UUID
    consumer_id: UUID
    api_id: str
    tenant_id: str
    auth_type: CredentialAuthTypeEnum
    header_name: str
    has_credential: bool
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by: str | None

    model_config = ConfigDict(from_attributes=True)


class CredentialMappingListResponse(BaseModel):
    """Schema for paginated credential mapping list."""

    items: list[CredentialMappingResponse]
    total: int
    page: int
    page_size: int


class CredentialMappingSyncItem(BaseModel):
    """Schema for a single credential mapping in gateway sync payload."""

    consumer_id: str
    api_id: str
    auth_type: str
    header_name: str
    header_value: str
