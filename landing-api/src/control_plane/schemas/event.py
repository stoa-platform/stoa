"""Pydantic schemas for event tracking endpoints."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from control_plane.models.prospect_event import EventType


class EventCreate(BaseModel):
    """Request schema for recording an event."""

    invite_id: UUID = Field(..., description="UUID of the associated invite")
    event_type: EventType = Field(..., description="Type of event being recorded")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional event-specific data",
    )


class EventResponse(BaseModel):
    """Response schema for event recording."""

    id: UUID
    recorded: bool = True

    model_config = {"from_attributes": True}


class EventDetail(BaseModel):
    """Detailed event information."""

    id: UUID
    invite_id: UUID
    event_type: EventType
    metadata: dict[str, Any]
    timestamp: datetime

    model_config = {"from_attributes": True}


class EventListResponse(BaseModel):
    """Response schema for listing events."""

    events: list[EventDetail]
    total: int
