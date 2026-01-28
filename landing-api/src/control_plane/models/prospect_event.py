# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Prospect event model for tracking user actions."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from control_plane.models.base import Base, UUIDMixin


class EventType(str, Enum):
    """Types of events that can be tracked."""

    INVITE_OPENED = "invite_opened"  # GET /welcome/{token}
    SANDBOX_CREATED = "sandbox_created"  # API key generated
    TOOL_CALLED = "tool_called"  # Each MCP tool call
    PAGE_VIEWED = "page_viewed"  # Navigation in Console
    ERROR_ENCOUNTERED = "error_encountered"  # Response 4xx/5xx
    SESSION_ENDED = "session_ended"  # Timeout or explicit close


class ProspectEvent(Base, UUIDMixin):
    """Event model for tracking prospect actions.

    Events are linked to invites and capture the prospect's journey
    through the demo experience.
    """

    __tablename__ = "prospect_events"

    invite_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("stoa.invites.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    event_data: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False, name="metadata"
    )  # Column name is 'metadata' in DB, attribute is 'event_data' to avoid SQLAlchemy conflict
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    # Relationship to invite
    invite = relationship("Invite", backref="events", lazy="selectin")

    __table_args__ = (
        Index("idx_prospect_events_invite_timestamp", "invite_id", "timestamp"),
        Index("idx_prospect_events_type", "event_type"),
    )

    def __repr__(self) -> str:
        return f"<ProspectEvent {self.event_type} for invite {self.invite_id}>"
