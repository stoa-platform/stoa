"""Events router - SSE endpoint for real-time Kafka events"""
from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse
from typing import AsyncGenerator
import asyncio
import json

from ..auth import get_current_user, User, require_tenant_access

router = APIRouter(prefix="/v1/events", tags=["Events"])

# Event types that can be streamed
EVENT_TYPES = [
    "api-created",
    "api-updated",
    "api-deleted",
    "deploy-started",
    "deploy-progress",
    "deploy-success",
    "deploy-failed",
    "app-created",
    "app-updated",
    "app-deleted",
    "tenant-created",
    "tenant-updated",
]

async def event_generator(
    request: Request,
    tenant_id: str,
    user: User,
    event_types: list[str] | None = None
) -> AsyncGenerator[dict, None]:
    """
    Generate SSE events from Kafka consumer.

    This generator:
    1. Creates a Kafka consumer for the user's tenant
    2. Filters events by tenant_id and event_types
    3. Yields events as SSE messages
    4. Handles client disconnection gracefully
    """
    # TODO: Implement with Kafka service
    # For now, just keep connection alive with heartbeats

    try:
        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                break

            # TODO: Poll Kafka for events
            # events = await kafka_service.poll_events(
            #     tenant_id=tenant_id,
            #     event_types=event_types,
            #     timeout=1.0
            # )
            #
            # for event in events:
            #     yield {
            #         "event": event.type,
            #         "id": event.id,
            #         "data": json.dumps(event.payload)
            #     }

            # Heartbeat to keep connection alive
            yield {
                "event": "heartbeat",
                "data": json.dumps({"status": "connected"})
            }

            await asyncio.sleep(30)  # Heartbeat every 30 seconds

    except asyncio.CancelledError:
        # Client disconnected
        pass

@router.get("/stream/{tenant_id}")
@require_tenant_access
async def stream_events(
    request: Request,
    tenant_id: str,
    event_types: str | None = None,  # Comma-separated list
    user: User = Depends(get_current_user)
):
    """
    Stream real-time events for a tenant via Server-Sent Events.

    Connect to this endpoint to receive real-time updates about:
    - API lifecycle events (created, updated, deleted)
    - Deployment status changes
    - Application events

    Query params:
    - event_types: Comma-separated list of event types to filter (optional)

    Example:
    ```
    const eventSource = new EventSource('/v1/events/stream/tenant-123?event_types=deploy-progress,deploy-success');
    eventSource.onmessage = (event) => {
        console.log(event.data);
    };
    ```
    """
    types_filter = event_types.split(",") if event_types else None

    return EventSourceResponse(
        event_generator(request, tenant_id, user, types_filter)
    )

@router.get("/stream/global")
async def stream_global_events(
    request: Request,
    event_types: str | None = None,
    user: User = Depends(get_current_user)
):
    """
    Stream all events (for cpi-admin users only).

    This endpoint streams events from all tenants.
    Only users with cpi-admin role can access this.
    """
    if "cpi-admin" not in user.roles:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=403,
            detail="Only cpi-admin can access global event stream"
        )

    types_filter = event_types.split(",") if event_types else None

    return EventSourceResponse(
        event_generator(request, "*", user, types_filter)
    )

# REST endpoints for event history
@router.get("/history/{tenant_id}")
@require_tenant_access
async def get_event_history(
    tenant_id: str,
    event_type: str | None = None,
    limit: int = 100,
    user: User = Depends(get_current_user)
):
    """Get historical events from database/Kafka"""
    # TODO: Implement with event store
    return {"events": []}
