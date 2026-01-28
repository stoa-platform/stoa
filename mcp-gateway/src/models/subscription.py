# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""SQLAlchemy Models for Subscription Persistence.

Database models for storing subscription metadata.
API keys are stored in HashiCorp Vault, only hashes stored here.

Reference: CAB-XXX - Secure API Key Management with Vault & 2FA
"""

import enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Integer,
    String,
    Text,
    Boolean,
    Index,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""
    pass


class SubscriptionStatus(enum.Enum):
    """Subscription status values."""

    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    SUSPENDED = "suspended"


class SubscriptionModel(Base):
    """Subscription database model.

    Stores subscription metadata. API keys are stored in Vault.
    """

    __tablename__ = "mcp_subscriptions"

    # Primary key
    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # User and tenant
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, default="default")

    # Tool reference
    tool_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Subscription details
    plan: Mapped[str] = mapped_column(String(50), nullable=False, default="free")
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus),
        nullable=False,
        default=SubscriptionStatus.ACTIVE,
        index=True,
    )

    # API Key (hash only - actual key in Vault)
    api_key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    api_key_prefix: Mapped[str] = mapped_column(String(12), nullable=False)

    # Vault reference
    vault_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # 2FA status
    totp_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Usage tracking
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Audit fields
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    revoked_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Indexes for common queries
    __table_args__ = (
        Index("ix_mcp_subscriptions_user_status", "user_id", "status"),
        Index("ix_mcp_subscriptions_tool_status", "tool_id", "status"),
        Index("ix_mcp_subscriptions_tenant_user", "tenant_id", "user_id"),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "tool_id": self.tool_id,
            "plan": self.plan,
            "status": self.status.value,
            "api_key_prefix": self.api_key_prefix,
            "totp_required": self.totp_required,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "usage_count": self.usage_count,
        }

    def __repr__(self) -> str:
        return f"<Subscription {self.id} user={self.user_id} tool={self.tool_id} status={self.status.value}>"
