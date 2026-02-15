"""Pydantic schemas for backend API endpoints (CAB-1188/CAB-1249)."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BackendApiAuthTypeEnum(StrEnum):
    """Authentication type for the backend API."""

    NONE = "none"
    API_KEY = "api_key"
    BEARER = "bearer"
    BASIC = "basic"
    OAUTH2_CC = "oauth2_cc"


class BackendApiStatusEnum(StrEnum):
    """Backend API lifecycle status."""

    DRAFT = "draft"
    ACTIVE = "active"
    DISABLED = "disabled"


class SaasApiKeyStatusEnum(StrEnum):
    """API key lifecycle status."""

    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


# ============== Backend API Schemas ==============


class BackendApiCreate(BaseModel):
    """Schema for registering a new backend API."""

    name: str = Field(..., min_length=1, max_length=255)
    display_name: str | None = Field(None, max_length=255)
    description: str | None = None
    backend_url: str = Field(..., min_length=1, max_length=2048)
    openapi_spec_url: str | None = Field(None, max_length=2048)
    auth_type: BackendApiAuthTypeEnum = BackendApiAuthTypeEnum.NONE
    auth_config: dict | None = Field(
        None,
        description="Backend credentials (api_key, bearer token, basic user/pass, oauth2 client_id/secret+token_url)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "petstore-api",
                "display_name": "Petstore API",
                "description": "Sample Petstore backend",
                "backend_url": "https://petstore.swagger.io/v2",
                "openapi_spec_url": "https://petstore.swagger.io/v2/swagger.json",
                "auth_type": "api_key",
                "auth_config": {"header_name": "X-API-Key", "header_value": "secret123"},
            }
        }
    )


class BackendApiUpdate(BaseModel):
    """Schema for updating a backend API."""

    display_name: str | None = Field(None, max_length=255)
    description: str | None = None
    backend_url: str | None = Field(None, max_length=2048)
    openapi_spec_url: str | None = Field(None, max_length=2048)
    auth_type: BackendApiAuthTypeEnum | None = None
    auth_config: dict | None = None
    status: BackendApiStatusEnum | None = None


class BackendApiResponse(BaseModel):
    """Schema for backend API response."""

    id: UUID
    tenant_id: str
    name: str
    display_name: str | None
    description: str | None
    backend_url: str
    openapi_spec_url: str | None
    auth_type: BackendApiAuthTypeEnum
    has_credentials: bool = Field(description="Whether backend credentials are configured")
    status: BackendApiStatusEnum
    tool_count: int
    spec_hash: str | None
    last_synced_at: datetime | None
    created_at: datetime
    updated_at: datetime
    created_by: str | None

    model_config = ConfigDict(from_attributes=True)


class BackendApiListResponse(BaseModel):
    """Schema for paginated backend API list."""

    items: list[BackendApiResponse]
    total: int
    page: int
    page_size: int


# ============== Scoped API Key Schemas ==============


class SaasApiKeyCreate(BaseModel):
    """Schema for creating a scoped API key."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    allowed_backend_api_ids: list[UUID] = Field(..., min_length=1, description="Backend API IDs this key can access")
    rate_limit_rpm: int | None = Field(None, ge=1, le=100000, description="Requests per minute")
    expires_at: datetime | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "my-agent-key",
                "allowed_backend_api_ids": ["550e8400-e29b-41d4-a716-446655440000"],
                "rate_limit_rpm": 60,
            }
        }
    )


class SaasApiKeyResponse(BaseModel):
    """Schema for API key response (without the key itself)."""

    id: UUID
    tenant_id: str
    name: str
    description: str | None
    key_prefix: str
    allowed_backend_api_ids: list[UUID]
    rate_limit_rpm: int | None
    status: SaasApiKeyStatusEnum
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None
    created_by: str | None

    model_config = ConfigDict(from_attributes=True)


class SaasApiKeyCreatedResponse(BaseModel):
    """Schema returned once at creation — includes the plaintext key."""

    id: UUID
    name: str
    key: str = Field(description="Plaintext API key — shown only once")
    key_prefix: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "my-agent-key",
                "key": "stoa_saas_a1b2_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                "key_prefix": "stoa_saas_a1b2",
            }
        }
    )


class SaasApiKeyListResponse(BaseModel):
    """Schema for paginated API key list."""

    items: list[SaasApiKeyResponse]
    total: int
    page: int
    page_size: int
