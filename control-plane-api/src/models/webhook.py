# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Webhook SQLAlchemy models for subscription event notifications (CAB-315)"""
from sqlalchemy import Column, String, DateTime, Boolean, Text, Index, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from datetime import datetime
import uuid
import enum

from src.database import Base


class WebhookEventType(str, enum.Enum):
    """Supported webhook event types"""
    SUBSCRIPTION_CREATED = "subscription.created"
    SUBSCRIPTION_APPROVED = "subscription.approved"
    SUBSCRIPTION_REVOKED = "subscription.revoked"
    SUBSCRIPTION_KEY_ROTATED = "subscription.key_rotated"
    SUBSCRIPTION_EXPIRED = "subscription.expired"


class WebhookDeliveryStatus(str, enum.Enum):
    """Webhook delivery status"""
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"


class TenantWebhook(Base):
    """Tenant webhook configuration - defines where to send notifications"""
    __tablename__ = "tenant_webhooks"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Tenant info
    tenant_id = Column(String(255), nullable=False, index=True)

    # Webhook config
    name = Column(String(255), nullable=False)
    url = Column(String(2048), nullable=False)
    secret = Column(String(512), nullable=True)  # For HMAC signature verification

    # Event filtering - store as JSON array for flexibility
    # ["subscription.created", "subscription.approved"] or ["*"] for all
    events = Column(JSON, nullable=False, default=list)

    # Optional headers (e.g., for authentication)
    headers = Column(JSON, nullable=True)

    # Status
    enabled = Column(Boolean, nullable=False, default=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(255), nullable=True)

    # Indexes
    __table_args__ = (
        Index('ix_tenant_webhooks_tenant_enabled', 'tenant_id', 'enabled'),
    )

    def __repr__(self) -> str:
        return f"<TenantWebhook {self.id} tenant={self.tenant_id} url={self.url[:50]}...>"

    def matches_event(self, event_type: str) -> bool:
        """Check if this webhook should receive the given event type"""
        if not self.enabled:
            return False
        if not self.events:
            return False
        # "*" matches all events
        if "*" in self.events:
            return True
        return event_type in self.events


class WebhookDelivery(Base):
    """Webhook delivery log - tracks each delivery attempt"""
    __tablename__ = "webhook_deliveries"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # References
    webhook_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    subscription_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    # Event info
    event_type = Column(String(100), nullable=False)
    payload = Column(JSON, nullable=False)

    # Delivery status
    status = Column(String(50), nullable=False, default=WebhookDeliveryStatus.PENDING.value)
    attempt_count = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=5)

    # Response info
    response_status_code = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_attempt_at = Column(DateTime, nullable=True)
    next_retry_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)

    # Indexes
    __table_args__ = (
        Index('ix_webhook_deliveries_status_retry', 'status', 'next_retry_at'),
        Index('ix_webhook_deliveries_webhook_created', 'webhook_id', 'created_at'),
    )

    def __repr__(self) -> str:
        return f"<WebhookDelivery {self.id} event={self.event_type} status={self.status}>"
