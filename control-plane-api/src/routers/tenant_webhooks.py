"""Tenant Webhooks router - Subscription event notification endpoints (CAB-315)

This router provides CRUD operations for tenant webhook configurations
and delivery history endpoints.
"""
import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.auth import get_current_user
from src.schemas.webhook import (
    WebhookCreate,
    WebhookUpdate,
    WebhookResponse,
    WebhookListResponse,
    WebhookDeliveryResponse,
    WebhookDeliveryListResponse,
    WebhookTestRequest,
    WebhookTestResponse,
    EventTypeInfo,
    EventTypesResponse,
)
from src.services.webhook_service import WebhookService
from src.models.webhook import WebhookEventType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants/{tenant_id}/webhooks", tags=["Tenant Webhooks"])


def _webhook_to_response(webhook) -> WebhookResponse:
    """Convert webhook model to response schema"""
    return WebhookResponse(
        id=webhook.id,
        tenant_id=webhook.tenant_id,
        name=webhook.name,
        url=webhook.url,
        events=webhook.events,
        has_secret=bool(webhook.secret),
        headers=webhook.headers,
        enabled=webhook.enabled,
        created_at=webhook.created_at,
        updated_at=webhook.updated_at,
        created_by=webhook.created_by,
    )


def _delivery_to_response(delivery) -> WebhookDeliveryResponse:
    """Convert delivery model to response schema"""
    return WebhookDeliveryResponse(
        id=delivery.id,
        webhook_id=delivery.webhook_id,
        subscription_id=delivery.subscription_id,
        event_type=delivery.event_type,
        payload=delivery.payload,
        status=delivery.status,
        attempt_count=delivery.attempt_count,
        max_attempts=delivery.max_attempts,
        response_status_code=delivery.response_status_code,
        response_body=delivery.response_body,
        error_message=delivery.error_message,
        created_at=delivery.created_at,
        last_attempt_at=delivery.last_attempt_at,
        next_retry_at=delivery.next_retry_at,
        delivered_at=delivery.delivered_at,
    )


# ============ Event Types Info ============

@router.get("/events", response_model=EventTypesResponse)
async def list_event_types():
    """
    List all available webhook event types with descriptions and payload examples.
    """
    events = [
        EventTypeInfo(
            event=WebhookEventType.SUBSCRIPTION_CREATED.value,
            description="Triggered when a new subscription request is created",
            payload_example={
                "event": "subscription.created",
                "timestamp": "2026-01-09T12:00:00Z",
                "data": {
                    "subscription_id": "sub-123",
                    "application_id": "app-456",
                    "application_name": "My App",
                    "api_id": "api-789",
                    "api_name": "Weather API",
                    "tenant_id": "acme",
                    "subscriber_id": "user-001",
                    "subscriber_email": "alice@example.com",
                    "status": "pending",
                }
            }
        ),
        EventTypeInfo(
            event=WebhookEventType.SUBSCRIPTION_APPROVED.value,
            description="Triggered when a subscription is approved by an admin",
            payload_example={
                "event": "subscription.approved",
                "timestamp": "2026-01-09T12:00:00Z",
                "data": {
                    "subscription_id": "sub-123",
                    "application_id": "app-456",
                    "application_name": "My App",
                    "api_id": "api-789",
                    "api_name": "Weather API",
                    "tenant_id": "acme",
                    "subscriber_id": "user-001",
                    "subscriber_email": "alice@example.com",
                    "status": "active",
                    "approved_by": "admin-001",
                    "approved_at": "2026-01-09T12:00:00Z",
                }
            }
        ),
        EventTypeInfo(
            event=WebhookEventType.SUBSCRIPTION_REVOKED.value,
            description="Triggered when a subscription is revoked",
            payload_example={
                "event": "subscription.revoked",
                "timestamp": "2026-01-09T12:00:00Z",
                "data": {
                    "subscription_id": "sub-123",
                    "application_id": "app-456",
                    "application_name": "My App",
                    "api_id": "api-789",
                    "api_name": "Weather API",
                    "tenant_id": "acme",
                    "subscriber_id": "user-001",
                    "subscriber_email": "alice@example.com",
                    "status": "revoked",
                    "revoked_by": "admin-001",
                    "revoked_at": "2026-01-09T12:00:00Z",
                    "reason": "Policy violation",
                }
            }
        ),
        EventTypeInfo(
            event=WebhookEventType.SUBSCRIPTION_KEY_ROTATED.value,
            description="Triggered when an API key is rotated",
            payload_example={
                "event": "subscription.key_rotated",
                "timestamp": "2026-01-09T12:00:00Z",
                "data": {
                    "subscription_id": "sub-123",
                    "application_id": "app-456",
                    "application_name": "My App",
                    "api_id": "api-789",
                    "api_name": "Weather API",
                    "tenant_id": "acme",
                    "subscriber_id": "user-001",
                    "subscriber_email": "alice@example.com",
                    "status": "active",
                    "rotation_count": 2,
                    "last_rotated_at": "2026-01-09T12:00:00Z",
                    "grace_period_expires_at": "2026-01-10T12:00:00Z",
                    "grace_period_hours": 24,
                }
            }
        ),
        EventTypeInfo(
            event=WebhookEventType.SUBSCRIPTION_EXPIRED.value,
            description="Triggered when a subscription expires",
            payload_example={
                "event": "subscription.expired",
                "timestamp": "2026-01-09T12:00:00Z",
                "data": {
                    "subscription_id": "sub-123",
                    "application_id": "app-456",
                    "application_name": "My App",
                    "api_id": "api-789",
                    "api_name": "Weather API",
                    "tenant_id": "acme",
                    "subscriber_id": "user-001",
                    "subscriber_email": "alice@example.com",
                    "status": "expired",
                }
            }
        ),
    ]
    return EventTypesResponse(events=events)


# ============ Webhook CRUD ============

@router.post("", response_model=WebhookResponse, status_code=201)
async def create_webhook(
    tenant_id: str,
    webhook_data: WebhookCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Create a new webhook configuration for a tenant.

    Requires tenant-admin or cpi-admin role.
    """
    # Check authorization - user must be tenant-admin for this tenant or cpi-admin
    user_tenant = current_user.get("tenant_id")
    user_roles = current_user.get("roles", [])

    if "cpi-admin" not in user_roles and user_tenant != tenant_id:
        raise HTTPException(
            status_code=403,
            detail="You can only create webhooks for your own tenant"
        )

    service = WebhookService(db)

    try:
        webhook = await service.create_webhook(
            tenant_id=tenant_id,
            name=webhook_data.name,
            url=webhook_data.url,
            events=webhook_data.events,
            secret=webhook_data.secret,
            headers=webhook_data.headers,
            created_by=current_user.get("sub"),
        )
        await db.commit()
        logger.info(f"Created webhook {webhook.id} for tenant {tenant_id} by {current_user.get('sub')}")
        return _webhook_to_response(webhook)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=WebhookListResponse)
async def list_webhooks(
    tenant_id: str,
    enabled_only: bool = Query(False, description="Only return enabled webhooks"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List all webhooks for a tenant.
    """
    # Check authorization
    user_tenant = current_user.get("tenant_id")
    user_roles = current_user.get("roles", [])

    if "cpi-admin" not in user_roles and user_tenant != tenant_id:
        raise HTTPException(
            status_code=403,
            detail="You can only view webhooks for your own tenant"
        )

    service = WebhookService(db)
    webhooks = await service.list_webhooks(tenant_id, enabled_only=enabled_only)

    return WebhookListResponse(
        items=[_webhook_to_response(w) for w in webhooks],
        total=len(webhooks),
    )


@router.get("/{webhook_id}", response_model=WebhookResponse)
async def get_webhook(
    tenant_id: str,
    webhook_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get a specific webhook configuration.
    """
    service = WebhookService(db)
    webhook = await service.get_webhook(webhook_id)

    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    # Check authorization
    user_tenant = current_user.get("tenant_id")
    user_roles = current_user.get("roles", [])

    if "cpi-admin" not in user_roles and user_tenant != webhook.tenant_id:
        raise HTTPException(
            status_code=403,
            detail="You can only view webhooks for your own tenant"
        )

    if webhook.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Webhook not found in this tenant")

    return _webhook_to_response(webhook)


@router.patch("/{webhook_id}", response_model=WebhookResponse)
async def update_webhook(
    tenant_id: str,
    webhook_id: UUID,
    webhook_data: WebhookUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Update a webhook configuration.
    """
    service = WebhookService(db)
    webhook = await service.get_webhook(webhook_id)

    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    # Check authorization
    user_tenant = current_user.get("tenant_id")
    user_roles = current_user.get("roles", [])

    if "cpi-admin" not in user_roles and user_tenant != webhook.tenant_id:
        raise HTTPException(
            status_code=403,
            detail="You can only update webhooks for your own tenant"
        )

    if webhook.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Webhook not found in this tenant")

    try:
        updated = await service.update_webhook(
            webhook_id=webhook_id,
            name=webhook_data.name,
            url=webhook_data.url,
            events=webhook_data.events,
            secret=webhook_data.secret,
            headers=webhook_data.headers,
            enabled=webhook_data.enabled,
        )
        await db.commit()
        logger.info(f"Updated webhook {webhook_id} by {current_user.get('sub')}")
        return _webhook_to_response(updated)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(
    tenant_id: str,
    webhook_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Delete a webhook configuration.
    """
    service = WebhookService(db)
    webhook = await service.get_webhook(webhook_id)

    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    # Check authorization
    user_tenant = current_user.get("tenant_id")
    user_roles = current_user.get("roles", [])

    if "cpi-admin" not in user_roles and user_tenant != webhook.tenant_id:
        raise HTTPException(
            status_code=403,
            detail="You can only delete webhooks for your own tenant"
        )

    if webhook.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Webhook not found in this tenant")

    await service.delete_webhook(webhook_id)
    await db.commit()
    logger.info(f"Deleted webhook {webhook_id} by {current_user.get('sub')}")


# ============ Delivery History ============

@router.get("/{webhook_id}/deliveries", response_model=WebhookDeliveryListResponse)
async def list_deliveries(
    tenant_id: str,
    webhook_id: UUID,
    limit: int = Query(50, ge=1, le=200, description="Max number of deliveries to return"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get delivery history for a webhook.
    """
    service = WebhookService(db)
    webhook = await service.get_webhook(webhook_id)

    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    # Check authorization
    user_tenant = current_user.get("tenant_id")
    user_roles = current_user.get("roles", [])

    if "cpi-admin" not in user_roles and user_tenant != webhook.tenant_id:
        raise HTTPException(
            status_code=403,
            detail="You can only view deliveries for your own tenant's webhooks"
        )

    if webhook.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Webhook not found in this tenant")

    deliveries = await service.get_delivery_history(webhook_id, limit=limit)

    return WebhookDeliveryListResponse(
        items=[_delivery_to_response(d) for d in deliveries],
        total=len(deliveries),
    )


@router.post("/{webhook_id}/deliveries/{delivery_id}/retry", response_model=WebhookDeliveryResponse)
async def retry_delivery(
    tenant_id: str,
    webhook_id: UUID,
    delivery_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Manually retry a failed webhook delivery.
    """
    service = WebhookService(db)
    webhook = await service.get_webhook(webhook_id)

    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    # Check authorization
    user_tenant = current_user.get("tenant_id")
    user_roles = current_user.get("roles", [])

    if "cpi-admin" not in user_roles and user_tenant != webhook.tenant_id:
        raise HTTPException(
            status_code=403,
            detail="You can only retry deliveries for your own tenant's webhooks"
        )

    if webhook.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Webhook not found in this tenant")

    try:
        delivery = await service.retry_delivery(delivery_id)
        if not delivery:
            raise HTTPException(status_code=404, detail="Delivery not found")

        await db.commit()
        logger.info(f"Retrying delivery {delivery_id} by {current_user.get('sub')}")
        return _delivery_to_response(delivery)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============ Test Webhook ============

@router.post("/{webhook_id}/test", response_model=WebhookTestResponse)
async def test_webhook(
    tenant_id: str,
    webhook_id: UUID,
    test_data: WebhookTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Send a test event to a webhook to verify it's working.
    """
    import httpx
    import json
    import hmac
    import hashlib
    from datetime import datetime
    from uuid import uuid4

    service = WebhookService(db)
    webhook = await service.get_webhook(webhook_id)

    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    # Check authorization
    user_tenant = current_user.get("tenant_id")
    user_roles = current_user.get("roles", [])

    if "cpi-admin" not in user_roles and user_tenant != webhook.tenant_id:
        raise HTTPException(
            status_code=403,
            detail="You can only test webhooks for your own tenant"
        )

    if webhook.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Webhook not found in this tenant")

    # Build test payload
    payload = {
        "event": test_data.event_type,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "test": True,
        "data": {
            "subscription_id": str(uuid4()),
            "application_id": "test-app-123",
            "application_name": "Test Application",
            "api_id": "test-api-456",
            "api_name": "Test API",
            "tenant_id": tenant_id,
            "subscriber_id": current_user.get("sub", "test-user"),
            "subscriber_email": current_user.get("email", "test@example.com"),
            "status": "active",
        }
    }

    # Build headers
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "STOA-Webhook/1.0",
        "X-Webhook-Event": test_data.event_type,
        "X-Webhook-Delivery": str(uuid4()),
        "X-Webhook-Test": "true",
    }

    signature_header = None
    if webhook.secret:
        payload_bytes = json.dumps(payload, sort_keys=True).encode('utf-8')
        signature = hmac.new(
            webhook.secret.encode('utf-8'),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()
        signature_header = f"sha256={signature}"
        headers["X-Webhook-Signature"] = signature_header

    if webhook.headers:
        headers.update(webhook.headers)

    # Send test request
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                webhook.url,
                json=payload,
                headers=headers,
            )

            success = 200 <= response.status_code < 300
            logger.info(f"Test webhook {webhook_id}: status={response.status_code} success={success}")

            return WebhookTestResponse(
                success=success,
                status_code=response.status_code,
                response_body=response.text[:2000] if response.text else None,
                error=None if success else f"HTTP {response.status_code}",
                signature_header=signature_header,
            )

    except httpx.TimeoutException:
        return WebhookTestResponse(
            success=False,
            status_code=None,
            response_body=None,
            error="Request timed out after 10 seconds",
            signature_header=signature_header,
        )

    except httpx.RequestError as e:
        return WebhookTestResponse(
            success=False,
            status_code=None,
            response_body=None,
            error=f"Request failed: {str(e)}",
            signature_header=signature_header,
        )
