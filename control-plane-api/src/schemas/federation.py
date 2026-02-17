"""Pydantic schemas for federation endpoints (CAB-1313/CAB-1361)."""

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
