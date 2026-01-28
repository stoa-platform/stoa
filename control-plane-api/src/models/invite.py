# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Invite model for prospect tracking (read-only mapping to landing-api tables).

This model maps to the existing stoa.invites table created by landing-api.
It's read-only from control-plane-api's perspective - used for admin dashboard queries.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class InviteStatus(str, Enum):
    """Status of an invite (matches landing-api InviteStatus)."""

    PENDING = "pending"  # Created, not yet clicked
    OPENED = "opened"  # Token validated via /welcome
    CONVERTED = "converted"  # sandbox_created event received
    EXPIRED = "expired"  # Past expires_at


class Invite(Base):
    """Invite model for tracking prospect invitations.

    Maps to stoa.invites table (owned by landing-api).
    Read-only from control-plane-api for admin dashboard queries.
    """

    __tablename__ = "invites"
    __table_args__ = {"schema": "stoa"}

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str] = mapped_column(String(100), nullable=False)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    opened_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @property
    def is_expired(self) -> bool:
        """Check if invite has expired based on expires_at."""
        from datetime import timezone as tz

        return datetime.now(tz.utc) > self.expires_at

    @property
    def status_enum(self) -> InviteStatus:
        """Get status as enum."""
        return InviteStatus(self.status)
