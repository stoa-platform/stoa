"""Pydantic schemas for metrics endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from control_plane.models.invite import InviteStatus
from control_plane.schemas.event import EventDetail


class InviteMetrics(BaseModel):
    """Calculated metrics for an invite."""

    time_to_sandbox_seconds: float | None = Field(
        None,
        description="Seconds from invite_opened to sandbox_created",
    )
    time_to_first_tool_seconds: float | None = Field(
        None,
        description="Seconds from sandbox_created to first tool_called",
    )
    tools_called_count: int = Field(
        0,
        description="Total number of tool_called events",
    )
    pages_viewed_count: int = Field(
        0,
        description="Total number of page_viewed events",
    )
    errors_encountered_count: int = Field(
        0,
        description="Total number of error_encountered events",
    )
    session_duration_seconds: float | None = Field(
        None,
        description="Seconds from first to last event",
    )


class MetricsResponse(BaseModel):
    """Full metrics response for an invite."""

    invite_id: UUID
    email: str
    company: str
    status: InviteStatus
    total_events: int
    metrics: InviteMetrics
    timeline: list[EventDetail] = Field(
        default_factory=list,
        description="Chronological list of events",
    )
    created_at: datetime
    opened_at: datetime | None = None
