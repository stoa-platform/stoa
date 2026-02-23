"""Events router - SSE endpoint for real-time Kafka events"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ..auth import User, get_current_user, require_tenant_access
from ..events.event_bus import event_bus
from ..services.kafka_service import Topics, kafka_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/events", tags=["Events"])


class DeploymentResult(BaseModel):
    """Deployment result from gateway adapter"""

    api_name: str
    api_version: str | None = "1.0"
    api_id: str | None = None
    tenant_id: str
    status: str  # success, failed, rollback
    action: str | None = None
    message: str | None = None
    error: str | None = None


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
    request: Request, tenant_id: str, user: User, event_types: list[str] | None = None
) -> AsyncGenerator[dict, None]:
    """
    Generate SSE events via in-memory EventBus fan-out (CAB-1420).

    Events are published to the bus by Kafka consumers and service-layer
    code (e.g. deployment log entries). Each SSE client gets its own
    subscriber queue with tenant + event-type filtering.
    """
    sub = event_bus.subscribe(tenant_id=tenant_id, event_types=event_types)
    try:
        async for event in event_bus.listen(sub):
            if await request.is_disconnected():
                break
            data = event.get("data", {})
            yield {
                "event": event.get("event", "message"),
                "data": json.dumps(data) if isinstance(data, dict) else data,
            }
    except asyncio.CancelledError:
        pass
    finally:
        event_bus.unsubscribe(sub)


@router.get("/stream/global")
async def stream_global_events(
    request: Request, event_types: str | None = None, user: User = Depends(get_current_user)
):
    """
    Stream all events (for cpi-admin users only).

    This endpoint streams events from all tenants.
    Only users with cpi-admin role can access this.
    """
    if "cpi-admin" not in user.roles:
        raise HTTPException(status_code=403, detail="Only cpi-admin can access global event stream")

    types_filter = event_types.split(",") if event_types else None

    return EventSourceResponse(event_generator(request, "*", user, types_filter))


@router.get("/stream/{tenant_id}")
@require_tenant_access
async def stream_events(
    request: Request,
    tenant_id: str,
    event_types: str | None = None,  # Comma-separated list
    user: User = Depends(get_current_user),
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

    return EventSourceResponse(event_generator(request, tenant_id, user, types_filter))


# REST endpoints for event history
@router.get("/history/{tenant_id}")
@require_tenant_access
async def get_event_history(
    tenant_id: str, event_type: str | None = None, limit: int = 100, user: User = Depends(get_current_user)
):
    """Get historical events for a tenant.

    Event store (DB-backed) deferred — Kafka-only audit log has no query API.
    See deployment history for recent activity.
    """
    return {
        "events": [],
        "message": "Event store not yet configured. See deployment history for recent activity.",
    }


@router.post("/deployment-result")
async def receive_deployment_result(result: DeploymentResult):
    """
    Receive deployment result notification from gateway adapters.

    This endpoint is called by gateway adapters after completing
    deployment, rollback, or other gateway operations.

    The result is published to Kafka for:
    - Real-time UI updates via SSE
    - Audit logging
    - Metrics collection
    """
    logger.info(f"Received deployment result: {result.api_name} - {result.status}")

    try:
        # Publish to Kafka for downstream consumers
        if kafka_service._producer:
            await kafka_service.publish(
                topic=Topics.DEPLOY_RESULTS,
                event_type=f"deployment-{result.status}",
                tenant_id=result.tenant_id,
                payload={
                    "api_name": result.api_name,
                    "api_version": result.api_version,
                    "api_id": result.api_id,
                    "status": result.status,
                    "action": result.action,
                    "message": result.message,
                    "error": result.error,
                },
            )
            logger.info(f"Published deployment result to Kafka: {result.api_name}")
    except Exception as e:
        logger.warning(f"Failed to publish to Kafka (non-blocking): {e}")

    return {"status": "received", "api_name": result.api_name, "deployment_status": result.status}
