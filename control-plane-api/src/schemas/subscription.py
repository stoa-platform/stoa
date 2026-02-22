"""Pydantic schemas for subscription endpoints"""

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SubscriptionStatusEnum(StrEnum):
    """Subscription status enum for API responses"""

    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
    EXPIRED = "expired"


class ProvisioningStatusEnum(StrEnum):
    """Gateway provisioning status for API responses (CAB-800)"""

    NONE = "none"
    PENDING = "pending"
    PROVISIONING = "provisioning"
    READY = "ready"
    FAILED = "failed"
    DEPROVISIONING = "deprovisioning"
    DEPROVISIONED = "deprovisioned"


class SubscriptionCreate(BaseModel):
    """Schema for creating a new subscription request"""

    application_id: str = Field(..., min_length=1, max_length=255)
    application_name: str = Field(..., min_length=1, max_length=255)
    api_id: str = Field(..., min_length=1, max_length=255)
    api_name: str = Field(..., min_length=1, max_length=255)
    api_version: str = Field(..., min_length=1, max_length=50)
    tenant_id: str = Field(..., min_length=1, max_length=255)
    plan_id: str | None = Field(None, max_length=255)
    plan_name: str | None = Field("default", max_length=255)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "application_id": "app-123",
                "application_name": "My App",
                "api_id": "api-456",
                "api_name": "Weather API",
                "api_version": "1.0",
                "tenant_id": "acme",
                "plan_id": "basic",
                "plan_name": "Basic Plan",
            }
        }
    )


class SubscriptionResponse(BaseModel):
    """Schema for subscription response"""

    id: UUID
    application_id: str
    application_name: str
    subscriber_id: str
    subscriber_email: str
    api_id: str
    api_name: str
    api_version: str
    tenant_id: str
    plan_id: str | None
    plan_name: str | None
    api_key_prefix: str
    status: SubscriptionStatusEnum
    status_reason: str | None
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None
    approved_by: str | None
    revoked_by: str | None

    # Gateway provisioning (CAB-800)
    provisioning_status: ProvisioningStatusEnum | None = None
    gateway_app_id: str | None = None
    provisioning_error: str | None = None
    provisioned_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class SubscriptionListResponse(BaseModel):
    """Schema for paginated subscription list"""

    items: list[SubscriptionResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class SubscriptionApprove(BaseModel):
    """Schema for approving a subscription"""

    expires_at: datetime | None = Field(None, description="Optional expiration date for the subscription")

    model_config = ConfigDict(json_schema_extra={"example": {"expires_at": "2025-12-31T23:59:59Z"}})


class SubscriptionRevoke(BaseModel):
    """Schema for revoking a subscription"""

    reason: str = Field(..., min_length=1, max_length=500)

    model_config = ConfigDict(json_schema_extra={"example": {"reason": "Violation of terms of service"}})


class APIKeyResponse(BaseModel):
    """Schema for API key response (only shown once at creation)"""

    subscription_id: UUID
    api_key: str = Field(..., description="Full API key - shown only once!")
    api_key_prefix: str = Field(..., description="Key prefix for reference")
    expires_at: datetime | None
    status: str = Field("pending", description="Subscription status after creation")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "subscription_id": "550e8400-e29b-41d4-a716-446655440000",
                "api_key": "stoa_sk_abcd1234efgh5678ijkl9012mnop3456",
                "api_key_prefix": "stoa_sk_",
                "expires_at": "2025-12-31T23:59:59Z",
            }
        }
    )


class SubscriptionStats(BaseModel):
    """Schema for subscription statistics"""

    total: int
    by_status: dict[str, int]
    by_tenant: dict[str, int]
    recent_24h: int


# ============== Key Rotation Schemas (CAB-314) ==============


class KeyRotationRequest(BaseModel):
    """Schema for requesting API key rotation"""

    grace_period_hours: int = Field(
        default=24, ge=1, le=168, description="Number of hours the old key remains valid (1-168)"  # Max 7 days
    )

    model_config = ConfigDict(json_schema_extra={"example": {"grace_period_hours": 24}})


class KeyRotationResponse(BaseModel):
    """Schema for key rotation response"""

    subscription_id: UUID
    new_api_key: str = Field(..., description="New API key - shown only once!")
    new_api_key_prefix: str = Field(..., description="New key prefix for reference")
    old_key_expires_at: datetime = Field(..., description="When the old key becomes invalid")
    grace_period_hours: int = Field(..., description="Grace period duration in hours")
    rotation_count: int = Field(..., description="Total number of rotations for this subscription")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "subscription_id": "550e8400-e29b-41d4-a716-446655440000",
                "new_api_key": "stoa_sk_newkey1234efgh5678ijkl9012mnop3456",
                "new_api_key_prefix": "stoa_sk_",
                "old_key_expires_at": "2026-01-10T16:00:00Z",
                "grace_period_hours": 24,
                "rotation_count": 1,
            }
        }
    )


class SubscriptionWithRotationInfo(SubscriptionResponse):
    """Extended subscription response with rotation info"""

    previous_key_expires_at: datetime | None = Field(None, description="If set, old key is still valid until this time")
    last_rotated_at: datetime | None = Field(None, description="When the key was last rotated")
    rotation_count: int = Field(default=0, description="Number of times the key has been rotated")
    has_active_grace_period: bool = Field(
        default=False, description="True if old key is still valid during grace period"
    )

    model_config = ConfigDict(from_attributes=True)


# ============== TTL Extension Schemas (CAB-86) ==============


class TTLExtendRequest(BaseModel):
    """Schema for requesting a TTL extension on a subscription."""

    extend_days: Literal[7, 14] = Field(..., description="Days to extend (7 or 14)")
    reason: str = Field(..., min_length=1, max_length=500, description="Reason for extension")

    model_config = ConfigDict(
        json_schema_extra={"example": {"extend_days": 7, "reason": "Need more time to complete integration testing"}}
    )


class TTLExtendResponse(BaseModel):
    """Schema for TTL extension response."""

    id: UUID
    new_expires_at: datetime
    ttl_extension_count: int
    ttl_total_extended_days: int
    remaining_extensions: int

    model_config = ConfigDict(from_attributes=True)
