"""Pydantic schemas for subscription endpoints"""
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from enum import Enum


class SubscriptionStatusEnum(str, Enum):
    """Subscription status enum for API responses"""
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
    EXPIRED = "expired"


class SubscriptionCreate(BaseModel):
    """Schema for creating a new subscription request"""
    application_id: str = Field(..., min_length=1, max_length=255)
    application_name: str = Field(..., min_length=1, max_length=255)
    api_id: str = Field(..., min_length=1, max_length=255)
    api_name: str = Field(..., min_length=1, max_length=255)
    api_version: str = Field(..., min_length=1, max_length=50)
    tenant_id: str = Field(..., min_length=1, max_length=255)
    plan_id: Optional[str] = Field(None, max_length=255)
    plan_name: Optional[str] = Field("default", max_length=255)

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
                "plan_name": "Basic Plan"
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
    plan_id: Optional[str]
    plan_name: Optional[str]
    api_key_prefix: str
    status: SubscriptionStatusEnum
    status_reason: Optional[str]
    created_at: datetime
    updated_at: datetime
    approved_at: Optional[datetime]
    expires_at: Optional[datetime]
    revoked_at: Optional[datetime]
    approved_by: Optional[str]
    revoked_by: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class SubscriptionListResponse(BaseModel):
    """Schema for paginated subscription list"""
    items: List[SubscriptionResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class SubscriptionApprove(BaseModel):
    """Schema for approving a subscription"""
    expires_at: Optional[datetime] = Field(
        None,
        description="Optional expiration date for the subscription"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "expires_at": "2025-12-31T23:59:59Z"
            }
        }
    )


class SubscriptionRevoke(BaseModel):
    """Schema for revoking a subscription"""
    reason: str = Field(..., min_length=1, max_length=500)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "reason": "Violation of terms of service"
            }
        }
    )


class APIKeyResponse(BaseModel):
    """Schema for API key response (only shown once at creation)"""
    subscription_id: UUID
    api_key: str = Field(..., description="Full API key - shown only once!")
    api_key_prefix: str = Field(..., description="Key prefix for reference")
    expires_at: Optional[datetime]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "subscription_id": "550e8400-e29b-41d4-a716-446655440000",
                "api_key": "stoa_sk_abcd1234efgh5678ijkl9012mnop3456",
                "api_key_prefix": "stoa_sk_",
                "expires_at": "2025-12-31T23:59:59Z"
            }
        }
    )


class SubscriptionStats(BaseModel):
    """Schema for subscription statistics"""
    total: int
    by_status: dict[str, int]
    by_tenant: dict[str, int]
    recent_24h: int
