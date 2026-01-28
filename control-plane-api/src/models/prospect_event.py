# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Prospect event model for tracking user actions (read-only mapping to landing-api tables).

This model maps to the existing stoa.prospect_events table created by landing-api.
It's read-only from control-plane-api's perspective - used for admin dashboard queries.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class EventType(str, Enum):
    """Types of events that can be tracked (matches landing-api EventType)."""

    INVITE_OPENED = "invite_opened"  # GET /welcome/{token}
    SANDBOX_CREATED = "sandbox_created"  # API key generated
    TOOL_CALLED = "tool_called"  # Each MCP tool call
    PAGE_VIEWED = "page_viewed"  # Navigation in Console
    ERROR_ENCOUNTERED = "error_encountered"  # Response 4xx/5xx
    SESSION_ENDED = "session_ended"  # Timeout or explicit close


class ProspectEvent(Base):
    """Event model for tracking prospect actions.

    Maps to stoa.prospect_events table (owned by landing-api).
    Read-only from control-plane-api for admin dashboard queries.
    """

    __tablename__ = "prospect_events"
    __table_args__ = {"schema": "stoa"}

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    invite_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Column name is 'metadata' in DB, attribute is 'event_data' to avoid SQLAlchemy conflict
    event_data: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False, name="metadata"
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    @property
    def event_type_enum(self) -> EventType:
        """Get event_type as enum."""
        return EventType(self.event_type)

    def __repr__(self) -> str:
        return f"<ProspectEvent {self.event_type} for invite {self.invite_id}>"
