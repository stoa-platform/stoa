# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Event service for tracking prospect actions."""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.models.prospect_event import EventType, ProspectEvent
from control_plane.schemas.event import EventCreate


async def record_event(
    db: AsyncSession,
    event_data: EventCreate,
) -> ProspectEvent:
    """Record a new prospect event.

    Args:
        db: Database session
        event_data: Event creation data

    Returns:
        Created event instance
    """
    event = ProspectEvent(
        invite_id=event_data.invite_id,
        event_type=event_data.event_type.value,
        event_data=event_data.metadata,
        timestamp=datetime.now(timezone.utc),
    )

    db.add(event)
    await db.flush()
    await db.refresh(event)

    return event


async def record_event_simple(
    db: AsyncSession,
    invite_id: UUID,
    event_type: EventType,
    metadata: dict[str, Any] | None = None,
) -> ProspectEvent:
    """Record a new prospect event with simple parameters.

    Convenience function for internal use.

    Args:
        db: Database session
        invite_id: UUID of the associated invite
        event_type: Type of event
        metadata: Optional additional data

    Returns:
        Created event instance
    """
    event = ProspectEvent(
        invite_id=invite_id,
        event_type=event_type.value,
        event_data=metadata or {},
        timestamp=datetime.now(timezone.utc),
    )

    db.add(event)
    await db.flush()
    await db.refresh(event)

    return event


async def get_events_for_invite(
    db: AsyncSession,
    invite_id: UUID,
    event_type: EventType | None = None,
) -> list[ProspectEvent]:
    """Get all events for an invite.

    Args:
        db: Database session
        invite_id: UUID of the invite
        event_type: Optional filter by event type

    Returns:
        List of events ordered by timestamp
    """
    query = select(ProspectEvent).where(ProspectEvent.invite_id == invite_id)

    if event_type:
        query = query.where(ProspectEvent.event_type == event_type.value)

    query = query.order_by(ProspectEvent.timestamp.asc())

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_first_event_of_type(
    db: AsyncSession,
    invite_id: UUID,
    event_type: EventType,
) -> ProspectEvent | None:
    """Get the first event of a specific type for an invite.

    Args:
        db: Database session
        invite_id: UUID of the invite
        event_type: Type of event to find

    Returns:
        First matching event or None
    """
    query = (
        select(ProspectEvent)
        .where(ProspectEvent.invite_id == invite_id)
        .where(ProspectEvent.event_type == event_type.value)
        .order_by(ProspectEvent.timestamp.asc())
        .limit(1)
    )

    result = await db.execute(query)
    return result.scalar_one_or_none()


async def count_events_by_type(
    db: AsyncSession,
    invite_id: UUID,
    event_type: EventType,
) -> int:
    """Count events of a specific type for an invite.

    Args:
        db: Database session
        invite_id: UUID of the invite
        event_type: Type of event to count

    Returns:
        Number of matching events
    """
    query = (
        select(ProspectEvent.id)
        .where(ProspectEvent.invite_id == invite_id)
        .where(ProspectEvent.event_type == event_type.value)
    )

    result = await db.execute(query)
    return len(result.scalars().all())
