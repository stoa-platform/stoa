"""Pydantic schemas for federation endpoints (CAB-1313/CAB-1361/CAB-1370)."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MasterAccountStatusEnum(StrEnum):
    """Master account lifecycle status."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    DISABLED = "disabled"


class SubAccountTypeEnum(StrEnum):
    """Sub-account type."""

    DEVELOPER = "developer"
    AGENT = "agent"


class SubAccountStatusEnum(StrEnum):
    """Sub-account lifecycle status."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


# ============== Master Account Schemas ==============


class MasterAccountCreate(BaseModel):
    """Schema for creating a federation master account."""

    name: str = Field(..., min_length=1, max_length=255)
    display_name: str | None = Field(None, max_length=255)
    description: str | None = None
    max_sub_accounts: int = Field(10, ge=1, le=1000)
    quota_config: dict | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "acme-federation",
                "display_name": "Acme Corp Federation",
                "description": "Master account for Acme developer program",
                "max_sub_accounts": 50,
            }
        }
    )


class MasterAccountUpdate(BaseModel):
    """Schema for updating a federation master account."""

    display_name: str | None = Field(None, max_length=255)
    description: str | None = None
    status: MasterAccountStatusEnum | None = None
    max_sub_accounts: int | None = Field(None, ge=1, le=1000)
    quota_config: dict | None = None


class MasterAccountResponse(BaseModel):
    """Schema for master account response."""

    id: UUID
    tenant_id: str
    name: str
    display_name: str | None
    description: str | None
    status: MasterAccountStatusEnum
    max_sub_accounts: int
    quota_config: dict | None
    sub_account_count: int = Field(0, description="Number of sub-accounts")
    created_at: datetime
    updated_at: datetime
    created_by: str | None

    model_config = ConfigDict(from_attributes=True)


class MasterAccountListResponse(BaseModel):
    """Schema for paginated master account list."""

    items: list[MasterAccountResponse]
    total: int
    page: int
    page_size: int


# ============== Sub-Account Schemas ==============


class SubAccountCreate(BaseModel):
    """Schema for creating a federation sub-account."""

    name: str = Field(..., min_length=1, max_length=255)
    display_name: str | None = Field(None, max_length=255)
    account_type: SubAccountTypeEnum = SubAccountTypeEnum.DEVELOPER

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "agent-alpha",
                "display_name": "Agent Alpha",
                "account_type": "agent",
            }
        }
    )


class SubAccountUpdate(BaseModel):
    """Schema for updating a federation sub-account."""

    display_name: str | None = Field(None, max_length=255)
    status: SubAccountStatusEnum | None = None


class SubAccountResponse(BaseModel):
    """Schema for sub-account response (never exposes key hash)."""

    id: UUID
    master_account_id: UUID
    tenant_id: str
    name: str
    display_name: str | None
    account_type: SubAccountTypeEnum
    status: SubAccountStatusEnum
    api_key_prefix: str | None
    kc_client_id: str | None
    created_at: datetime
    updated_at: datetime
    created_by: str | None

    model_config = ConfigDict(from_attributes=True)


class SubAccountCreatedResponse(BaseModel):
    """Schema returned once at creation — includes the plaintext API key."""

    id: UUID
    name: str
    api_key: str = Field(description="Plaintext API key — shown only once")
    api_key_prefix: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "agent-alpha",
                "api_key": "stoa_fed_a1b2_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                "api_key_prefix": "stoa_fed_a1b2",
            }
        }
    )


class SubAccountListResponse(BaseModel):
    """Schema for paginated sub-account list."""

    items: list[SubAccountResponse]
    total: int
    page: int
    page_size: int


# ============== CAB-1370: Delegation Token + Usage Schemas ==============


class DelegationTokenRequest(BaseModel):
    """Request schema for token delegation via master account."""

    scopes: list[str] = Field(default_factory=lambda: ["stoa:read"], description="OAuth2 scopes to request")
    ttl_seconds: int = Field(3600, ge=60, le=86400, description="Token TTL in seconds (1min to 24h)")


class DelegationTokenResponse(BaseModel):
    """Response schema for a delegated federation token."""

    access_token: str = Field(description="Delegated OAuth2 access token")
    token_type: str = Field(default="Bearer")
    expires_in: int = Field(description="Token lifetime in seconds")
    scope: str = Field(description="Granted scopes (space-separated)")
    sub_account_id: UUID
    sub_account_name: str


class UsageStat(BaseModel):
    """Single sub-account usage statistics entry."""

    sub_account_id: UUID
    sub_account_name: str
    request_count: int = Field(0, ge=0)
    token_count: int = Field(0, ge=0)
    error_count: int = Field(0, ge=0)
    last_active_at: datetime | None = None


class UsageResponse(BaseModel):
    """Aggregated usage statistics for all sub-accounts of a master account."""

    master_account_id: UUID
    period_days: int
    total_requests: int = 0
    total_tokens: int = 0
    sub_accounts: list[UsageStat]


class FederationBulkRevokeResponse(BaseModel):
    """Response schema for bulk sub-account revocation."""

    revoked_count: int = Field(description="Number of sub-accounts newly revoked")
    already_revoked: int = Field(description="Number already in revoked state")
    total: int = Field(description="Total sub-accounts in master account")


class ToolAllowListUpdate(BaseModel):
    """Request schema for updating a sub-account tool allow-list."""

    tools: list[str] = Field(..., description="List of tool names (replaces existing)")


class ToolAllowListResponse(BaseModel):
    """Response schema for sub-account tool allow-list."""

    sub_account_id: UUID
    tools: list[str] = Field(description="Currently allowed tool names")
