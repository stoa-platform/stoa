# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Metrics service for calculating invite metrics."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.models.invite import Invite, InviteStatus
from control_plane.models.prospect_event import EventType, ProspectEvent
from control_plane.schemas.event import EventDetail
from control_plane.schemas.metrics import InviteMetrics, MetricsResponse
from control_plane.services import event_service


async def calculate_metrics(
    db: AsyncSession,
    invite: Invite,
) -> MetricsResponse:
    """Calculate comprehensive metrics for an invite.

    Calculates:
    - time_to_sandbox: sandbox_created.timestamp - invite_opened.timestamp
    - time_to_first_tool: first tool_called.timestamp - sandbox_created.timestamp
    - Event counts by type
    - Session duration

    Args:
        db: Database session
        invite: Invite to calculate metrics for

    Returns:
        MetricsResponse with calculated metrics and timeline
    """
    # Get all events for this invite
    events = await event_service.get_events_for_invite(db, invite.id)

    # Find key events
    invite_opened = _find_first_event(events, EventType.INVITE_OPENED)
    sandbox_created = _find_first_event(events, EventType.SANDBOX_CREATED)
    first_tool = _find_first_event(events, EventType.TOOL_CALLED)

    # Calculate time metrics
    time_to_sandbox = None
    if invite_opened and sandbox_created:
        delta = sandbox_created.timestamp - invite_opened.timestamp
        time_to_sandbox = delta.total_seconds()

    time_to_first_tool = None
    if sandbox_created and first_tool:
        delta = first_tool.timestamp - sandbox_created.timestamp
        time_to_first_tool = delta.total_seconds()

    # Count events by type
    tools_called = _count_events(events, EventType.TOOL_CALLED)
    pages_viewed = _count_events(events, EventType.PAGE_VIEWED)
    errors_encountered = _count_events(events, EventType.ERROR_ENCOUNTERED)

    # Calculate session duration (first to last event)
    session_duration = None
    if len(events) >= 2:
        first_event = events[0]
        last_event = events[-1]
        delta = last_event.timestamp - first_event.timestamp
        session_duration = delta.total_seconds()

    # Build timeline
    timeline = [
        EventDetail(
            id=e.id,
            invite_id=e.invite_id,
            event_type=EventType(e.event_type),
            metadata=e.event_data,
            timestamp=e.timestamp,
        )
        for e in events
    ]

    return MetricsResponse(
        invite_id=invite.id,
        email=invite.email,
        company=invite.company,
        status=InviteStatus(invite.status),
        total_events=len(events),
        metrics=InviteMetrics(
            time_to_sandbox_seconds=time_to_sandbox,
            time_to_first_tool_seconds=time_to_first_tool,
            tools_called_count=tools_called,
            pages_viewed_count=pages_viewed,
            errors_encountered_count=errors_encountered,
            session_duration_seconds=session_duration,
        ),
        timeline=timeline,
        created_at=invite.created_at,
        opened_at=invite.opened_at,
    )


def _find_first_event(
    events: list[ProspectEvent],
    event_type: EventType,
) -> ProspectEvent | None:
    """Find the first event of a given type."""
    for event in events:
        if event.event_type == event_type.value:
            return event
    return None


def _count_events(
    events: list[ProspectEvent],
    event_type: EventType,
) -> int:
    """Count events of a given type."""
    return sum(1 for e in events if e.event_type == event_type.value)
