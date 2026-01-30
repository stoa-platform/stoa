"""Subscription SQLAlchemy model for API subscriptions"""
from sqlalchemy import Column, String, DateTime, Enum as SQLEnum, Text, Index, Integer
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid
import enum

from src.database import Base


class SubscriptionStatus(str, enum.Enum):
    """Subscription status enum"""
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
    EXPIRED = "expired"


class ProvisioningStatus(str, enum.Enum):
    """Gateway provisioning status for webMethods integration (CAB-800)"""
    NONE = "none"                        # No provisioning needed
    PENDING = "pending"                  # Awaiting provisioning
    PROVISIONING = "provisioning"        # In progress
    READY = "ready"                      # Route active in gateway
    FAILED = "failed"                    # Provisioning failed
    DEPROVISIONING = "deprovisioning"    # Removal in progress
    DEPROVISIONED = "deprovisioned"      # Removed from gateway


class Subscription(Base):
    """Subscription model - represents an API subscription with API key"""
    __tablename__ = "subscriptions"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Subscriber info (from Developer Portal)
    application_id = Column(String(255), nullable=False, index=True)
    application_name = Column(String(255), nullable=False)
    subscriber_id = Column(String(255), nullable=False, index=True)  # Keycloak user ID
    subscriber_email = Column(String(255), nullable=False)

    # API info
    api_id = Column(String(255), nullable=False, index=True)
    api_name = Column(String(255), nullable=False)
    api_version = Column(String(50), nullable=False)
    tenant_id = Column(String(255), nullable=False, index=True)

    # Subscription plan
    plan_id = Column(String(255), nullable=True)
    plan_name = Column(String(255), nullable=True, default="default")

    # API Key (hashed for security)
    api_key_hash = Column(String(512), nullable=False, unique=True)
    api_key_prefix = Column(String(10), nullable=False)  # First 8 chars for display

    # Key rotation with grace period (CAB-314)
    previous_api_key_hash = Column(String(512), nullable=True, index=True)  # Old key during grace period
    previous_key_expires_at = Column(DateTime, nullable=True)  # When old key becomes invalid
    last_rotated_at = Column(DateTime, nullable=True)  # Last rotation timestamp
    rotation_count = Column(Integer, nullable=False, default=0)  # Number of rotations

    # Status
    status = Column(
        SQLEnum(SubscriptionStatus),
        nullable=False,
        default=SubscriptionStatus.PENDING
    )
    status_reason = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    approved_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)

    # Audit fields
    approved_by = Column(String(255), nullable=True)  # Admin user ID who approved
    revoked_by = Column(String(255), nullable=True)   # Admin user ID who revoked

    # Gateway provisioning (CAB-800)
    provisioning_status = Column(
        SQLEnum(ProvisioningStatus),
        nullable=False,
        default=ProvisioningStatus.NONE,
        server_default="none",
    )
    gateway_app_id = Column(String(255), nullable=True)    # webMethods application ID
    provisioning_error = Column(Text, nullable=True)        # Last error message
    provisioned_at = Column(DateTime, nullable=True)        # When route was created

    # Indexes for common queries
    __table_args__ = (
        Index('ix_subscriptions_tenant_api', 'tenant_id', 'api_id'),
        Index('ix_subscriptions_subscriber_status', 'subscriber_id', 'status'),
        Index('ix_subscriptions_application_api', 'application_id', 'api_id'),
        Index('ix_subscriptions_provisioning_status', 'provisioning_status'),
    )

    def __repr__(self) -> str:
        return f"<Subscription {self.id} app={self.application_name} api={self.api_name}>"
