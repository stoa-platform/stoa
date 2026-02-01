"""
Tenant Lifecycle Management - Models & Schemas
CAB-409: Auto-Cleanup & Notifications for demo.gostoa.dev
"""
from __future__ import annotations

import enum
from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, Field, computed_field
from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text, Boolean, func, UniqueConstraint
from sqlalchemy.orm import relationship

from src.database import Base

# ─── Constants ────────────────────────────────────────────────────────────────

TRIAL_DURATION_DAYS = 14
WARNING_THRESHOLD_DAYS = 3       # Warning starts at day 11 (14 - 3)
GRACE_PERIOD_DAYS = 7            # Read-only grace after expiration
CLEANUP_AFTER_DAYS = 7           # Delete 7 days after expiration (day 21)
MAX_EXTENSIONS = 1               # One extension allowed per tenant
EXTENSION_DAYS = 7               # Each extension adds 7 days


# ─── Enums ────────────────────────────────────────────────────────────────────

class TenantLifecycleState(str, enum.Enum):
    ACTIVE = "active"           # Day 0-10: full access
    WARNING = "warning"         # Day 11-14: full access + warnings
    EXPIRED = "expired"         # Day 15-21: read-only, login disabled
    DELETED = "deleted"         # Day 22+: cleaned up
    CONVERTED = "converted"     # Upgraded to Enterprise


class NotificationType(str, enum.Enum):
    WARNING_3D = "warning_3d"     # J+11: "Trial expires in 3 days"
    URGENT_1D = "urgent_1d"       # J+13: "Last chance - expires tomorrow"
    EXPIRED = "expired"           # J+14: "Trial expired - read-only mode"
    GRACE = "grace"               # J+15: "Data will be deleted in 7 days"
    FINAL = "final"               # J+21: "Deletion scheduled tomorrow"


# Mapping: notification type → days before/after expiration
NOTIFICATION_SCHEDULE: dict[NotificationType, int] = {
    NotificationType.WARNING_3D: -3,    # 3 days before expiration
    NotificationType.URGENT_1D: -1,     # 1 day before expiration
    NotificationType.EXPIRED: 0,        # On expiration day
    NotificationType.GRACE: 1,          # 1 day after expiration
    NotificationType.FINAL: 7,          # 7 days after expiration (cleanup tomorrow)
}


# ─── SQLAlchemy Mixin (add to existing Tenant model) ─────────────────────────

class TenantLifecycleMixin:
    """Mixin to add to existing Tenant SQLAlchemy model."""

    lifecycle_state = Column(
        Enum(TenantLifecycleState, name="tenant_lifecycle_state"),
        default=TenantLifecycleState.ACTIVE,
        nullable=False,
        index=True,
    )
    trial_expires_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )
    trial_extended_count = Column(
        Integer,
        default=0,
        nullable=False,
    )
    lifecycle_changed_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    converted_at = Column(DateTime(timezone=True), nullable=True)


# ─── TenantLifecycleNotification ORM (COUNCIL #1) ────────────────────────────

class TenantLifecycleNotification(Base):
    """Tracks sent notifications to prevent duplicates (send-once logic)."""
    __tablename__ = "tenant_lifecycle_notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    notification_type = Column(String(50), nullable=False)
    sent_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    channel = Column(String(20), server_default="email", nullable=False)
    recipient_email = Column(String(255), nullable=True)
    success = Column(Boolean, server_default="true", nullable=False)
    error_message = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "notification_type", name="uq_tenant_notification_type"),
    )


# ─── Pydantic Schemas ────────────────────────────────────────────────────────

class TenantStatusResponse(BaseModel):
    """GET /tenants/{id}/lifecycle/status"""
    tenant_id: str
    tenant_name: str
    state: TenantLifecycleState
    created_at: datetime
    expires_at: Optional[datetime] = None
    lifecycle_changed_at: datetime

    @computed_field
    @property
    def days_left(self) -> Optional[int]:
        if self.expires_at is None:
            return None
        delta = self.expires_at - datetime.now(timezone.utc)
        return max(0, delta.days)

    @computed_field
    @property
    def can_extend(self) -> bool:
        return (
            self.state in (TenantLifecycleState.ACTIVE, TenantLifecycleState.WARNING)
            and self._extended_count < MAX_EXTENSIONS
        )

    @computed_field
    @property
    def can_upgrade(self) -> bool:
        return self.state not in (TenantLifecycleState.DELETED,)

    @computed_field
    @property
    def is_read_only(self) -> bool:
        return self.state == TenantLifecycleState.EXPIRED

    # Internal field not exposed in JSON
    _extended_count: int = 0

    model_config = {"from_attributes": True}


class ExtendTrialRequest(BaseModel):
    """POST /tenants/{id}/lifecycle/extend"""
    reason: Optional[str] = Field(None, max_length=500, description="Why the extension is needed")


class ExtendTrialResponse(BaseModel):
    tenant_id: str
    new_expires_at: datetime
    extensions_remaining: int
    message: str


class UpgradeTenantRequest(BaseModel):
    """POST /tenants/{id}/lifecycle/upgrade"""
    target_tier: str = Field(..., description="Target tier: pro, business, enterprise")
    contact_email: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=1000)


class UpgradeTenantResponse(BaseModel):
    tenant_id: str
    previous_state: TenantLifecycleState
    new_state: TenantLifecycleState = TenantLifecycleState.CONVERTED
    target_tier: str
    message: str


class LifecycleTransitionEvent(BaseModel):
    """Event emitted on state transitions (for Kafka/audit)."""
    tenant_id: str
    from_state: TenantLifecycleState
    to_state: TenantLifecycleState
    triggered_by: str  # "cron", "admin", "self-service"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = Field(default_factory=dict)


class LifecycleCronSummary(BaseModel):
    """Summary returned by the lifecycle cron job."""
    run_at: datetime
    tenants_warned: int = 0
    tenants_expired: int = 0
    tenants_deleted: int = 0
    notifications_sent: int = 0
    errors: list[str] = Field(default_factory=list)
