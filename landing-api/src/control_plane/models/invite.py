# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Invite model for prospect tracking."""

from datetime import datetime, timedelta, timezone
from enum import Enum
from uuid import UUID

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.config import settings
from control_plane.models.base import Base, TimestampMixin, UUIDMixin


class InviteStatus(str, Enum):
    """Status of an invite."""

    PENDING = "pending"  # Created, not yet clicked
    OPENED = "opened"  # Token validated via /welcome
    CONVERTED = "converted"  # sandbox_created event received
    EXPIRED = "expired"  # Past expires_at (set by cron or on-demand)


class Invite(Base, UUIDMixin, TimestampMixin):
    """Invite model for tracking prospect invitations.

    The `opened_at` field is denormalized for performance - it allows fast
    metrics queries without joining to the prospect_events table.
    """

    __tablename__ = "invites"

    email: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str] = mapped_column(String(100), nullable=False)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        default=InviteStatus.PENDING.value,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    # Denormalized for perf: avoids JOIN on prospect_events for metrics
    opened_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        Index("idx_invites_email", "email"),
        Index("idx_invites_status", "status"),
    )

    @classmethod
    def calculate_expires_at(cls) -> datetime:
        """Calculate expiration date based on settings."""
        return datetime.now(timezone.utc) + timedelta(days=settings.invite_expiry_days)

    @property
    def is_expired(self) -> bool:
        """Check if invite has expired."""
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def is_valid(self) -> bool:
        """Check if invite is valid for use."""
        return self.status == InviteStatus.PENDING.value and not self.is_expired

    def mark_opened(self) -> None:
        """Mark invite as opened."""
        self.status = InviteStatus.OPENED.value
        self.opened_at = datetime.now(timezone.utc)

    def mark_converted(self) -> None:
        """Mark invite as converted (sandbox created)."""
        self.status = InviteStatus.CONVERTED.value

    def mark_expired(self) -> None:
        """Mark invite as expired."""
        self.status = InviteStatus.EXPIRED.value
