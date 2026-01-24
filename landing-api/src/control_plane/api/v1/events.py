"""Event tracking API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.database import get_db
from control_plane.models.prospect_event import EventType
from control_plane.schemas.event import (
    EventCreate,
    EventDetail,
    EventListResponse,
    EventResponse,
)
from control_plane.services import event_service, invite_service

router = APIRouter(prefix="/events", tags=["events"])


@router.post(
    "",
    response_model=EventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record an event",
    description="Record a prospect event for tracking.",
)
async def record_event(
    event_data: EventCreate,
    db: AsyncSession = Depends(get_db),
) -> EventResponse:
    """Record a new prospect event.

    This is a fallback endpoint for manual event tracking.
    Most events are recorded automatically via middleware.

    Args:
        event_data: Event data to record
        db: Database session

    Returns:
        Confirmation that event was recorded
    """
    # Verify invite exists
    invite = await invite_service.get_invite_by_id(db, event_data.invite_id)
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "invite_not_found", "message": "Invite not found"},
        )

    event = await event_service.record_event(db, event_data)

    # If this is a sandbox_created event, mark invite as converted
    if event_data.event_type == EventType.SANDBOX_CREATED:
        await invite_service.mark_invite_converted(db, invite)

    return EventResponse(id=event.id, recorded=True)


@router.get(
    "",
    response_model=EventListResponse,
    summary="List events for an invite",
    description="Get all events for a specific invite.",
)
async def list_events(
    invite_id: UUID = Query(..., description="UUID of the invite"),
    event_type: EventType | None = Query(None, description="Filter by event type"),
    db: AsyncSession = Depends(get_db),
) -> EventListResponse:
    """List events for an invite.

    Args:
        invite_id: UUID of the invite to get events for
        event_type: Optional filter by event type
        db: Database session

    Returns:
        List of events with total count
    """
    # Verify invite exists
    invite = await invite_service.get_invite_by_id(db, invite_id)
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "invite_not_found", "message": "Invite not found"},
        )

    events = await event_service.get_events_for_invite(db, invite_id, event_type)

    return EventListResponse(
        events=[
            EventDetail(
                id=e.id,
                invite_id=e.invite_id,
                event_type=EventType(e.event_type),
                metadata=e.event_data,
                timestamp=e.timestamp,
            )
            for e in events
        ],
        total=len(events),
    )
