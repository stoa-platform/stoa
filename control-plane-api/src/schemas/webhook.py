# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Pydantic schemas for webhook endpoints (CAB-315)"""
from pydantic import BaseModel, Field, HttpUrl, ConfigDict
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from enum import Enum


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
    events: List[str] = Field(
        ...,
        min_length=1,
        description="List of events to subscribe to, or ['*'] for all events"
    )
    secret: Optional[str] = Field(
        None,
        min_length=16,
        max_length=512,
        description="Secret for HMAC signature verification (min 16 chars)"
    )
    headers: Optional[dict] = Field(
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
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    url: Optional[str] = Field(None, min_length=1, max_length=2048)
    events: Optional[List[str]] = Field(None, min_length=1)
    secret: Optional[str] = Field(None, min_length=16, max_length=512)
    headers: Optional[dict] = None
    enabled: Optional[bool] = None

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
    events: List[str]
    has_secret: bool = Field(..., description="Whether a secret is configured (secret value not returned)")
    headers: Optional[dict]
    enabled: bool
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class WebhookListResponse(BaseModel):
    """Schema for webhook list response"""
    items: List[WebhookResponse]
    total: int


# ============ Webhook Delivery Schemas ============

class WebhookDeliveryResponse(BaseModel):
    """Schema for webhook delivery response"""
    id: UUID
    webhook_id: UUID
    subscription_id: Optional[UUID]
    event_type: str
    payload: dict
    status: WebhookDeliveryStatusEnum
    attempt_count: int
    max_attempts: int
    response_status_code: Optional[int]
    response_body: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    last_attempt_at: Optional[datetime]
    next_retry_at: Optional[datetime]
    delivered_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class WebhookDeliveryListResponse(BaseModel):
    """Schema for delivery history response"""
    items: List[WebhookDeliveryResponse]
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
    status_code: Optional[int]
    response_body: Optional[str]
    error: Optional[str]
    signature_header: Optional[str] = Field(
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
    events: List[EventTypeInfo]
