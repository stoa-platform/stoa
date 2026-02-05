"""Pydantic schemas for webhook endpoints (CAB-315)"""
from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WebhookEventTypeEnum(str, Enum):
    """Supported webhook event types"""
    SUBSCRIPTION_CREATED = "subscription.created"
    SUBSCRIPTION_APPROVED = "subscription.approved"
    SUBSCRIPTION_REVOKED = "subscription.revoked"
    SUBSCRIPTION_KEY_ROTATED = "subscription.key_rotated"
    SUBSCRIPTION_EXPIRED = "subscription.expired"
    ALL = "*"


class WebhookDeliveryStatusEnum(str, Enum):
    """Webhook delivery status"""
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"


# ============ Webhook Configuration Schemas ============

class WebhookCreate(BaseModel):
    """Schema for creating a new webhook"""
    name: str = Field(..., min_length=1, max_length=255, description="Human-readable name for this webhook")
    url: str = Field(..., min_length=1, max_length=2048, description="URL to send webhook events to")
    events: list[str] = Field(
        ...,
        min_length=1,
        description="List of events to subscribe to, or ['*'] for all events"
    )
    secret: str | None = Field(
        None,
        min_length=16,
        max_length=512,
        description="Secret for HMAC signature verification (min 16 chars)"
    )
    headers: dict | None = Field(
        None,
        description="Custom headers to include in webhook requests"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Slack Notifications",
                "url": "https://hooks.slack.com/services/xxx/yyy/zzz",
                "events": ["subscription.created", "subscription.approved"],
                "secret": "my-super-secret-key-min16chars",
                "headers": {"X-Custom-Header": "custom-value"}
            }
        }
    )


class WebhookUpdate(BaseModel):
    """Schema for updating a webhook"""
    name: str | None = Field(None, min_length=1, max_length=255)
    url: str | None = Field(None, min_length=1, max_length=2048)
    events: list[str] | None = Field(None, min_length=1)
    secret: str | None = Field(None, min_length=16, max_length=512)
    headers: dict | None = None
    enabled: bool | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Updated Slack Notifications",
                "events": ["*"],
                "enabled": True
            }
        }
    )


class WebhookResponse(BaseModel):
    """Schema for webhook response"""
    id: UUID
    tenant_id: str
    name: str
    url: str
    events: list[str]
    has_secret: bool = Field(..., description="Whether a secret is configured (secret value not returned)")
    headers: dict | None
    enabled: bool
    created_at: datetime
    updated_at: datetime
    created_by: str | None

    model_config = ConfigDict(from_attributes=True)


class WebhookListResponse(BaseModel):
    """Schema for webhook list response"""
    items: list[WebhookResponse]
    total: int


# ============ Webhook Delivery Schemas ============

class WebhookDeliveryResponse(BaseModel):
    """Schema for webhook delivery response"""
    id: UUID
    webhook_id: UUID
    subscription_id: UUID | None
    event_type: str
    payload: dict
    status: WebhookDeliveryStatusEnum
    attempt_count: int
    max_attempts: int
    response_status_code: int | None
    response_body: str | None
    error_message: str | None
    created_at: datetime
    last_attempt_at: datetime | None
    next_retry_at: datetime | None
    delivered_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class WebhookDeliveryListResponse(BaseModel):
    """Schema for delivery history response"""
    items: list[WebhookDeliveryResponse]
    total: int


# ============ Test Webhook Schema ============

class WebhookTestRequest(BaseModel):
    """Schema for testing a webhook"""
    event_type: str = Field(
        default="subscription.created",
        description="Event type to simulate"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "event_type": "subscription.created"
            }
        }
    )


class WebhookTestResponse(BaseModel):
    """Schema for webhook test response"""
    success: bool
    status_code: int | None
    response_body: str | None
    error: str | None
    signature_header: str | None = Field(
        None,
        description="The X-Webhook-Signature header that was sent (if secret configured)"
    )


# ============ Event Types Info ============

class EventTypeInfo(BaseModel):
    """Information about a webhook event type"""
    event: str
    description: str
    payload_example: dict


class EventTypesResponse(BaseModel):
    """Schema for listing available event types"""
    events: list[EventTypeInfo]
