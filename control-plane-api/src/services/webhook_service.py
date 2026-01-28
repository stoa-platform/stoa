# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Webhook service for subscription event notifications (CAB-315)

This service handles:
1. Webhook configuration management per tenant
2. Event dispatching to registered webhooks
3. Retry logic with exponential backoff
4. HMAC signature generation for payload verification
"""
import json
import hmac
import hashlib
import logging
import asyncio
from typing import Optional, List
from datetime import datetime, timedelta
from uuid import UUID
import httpx

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.webhook import (
    TenantWebhook,
    WebhookDelivery,
    WebhookEventType,
    WebhookDeliveryStatus,
)
from src.models.subscription import Subscription

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRY_ATTEMPTS = 5
RETRY_DELAYS = [60, 300, 900, 3600, 7200]  # 1min, 5min, 15min, 1h, 2h


class WebhookService:
    """Service for managing webhooks and dispatching events"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ============ Webhook Configuration CRUD ============

    async def create_webhook(
        self,
        tenant_id: str,
        name: str,
        url: str,
        events: List[str],
        secret: Optional[str] = None,
        headers: Optional[dict] = None,
        created_by: Optional[str] = None,
    ) -> TenantWebhook:
        """Create a new webhook configuration for a tenant"""
        # Validate events
        valid_events = {"*"} | {e.value for e in WebhookEventType}
        for event in events:
            if event not in valid_events:
                raise ValueError(f"Invalid event type: {event}. Valid types: {valid_events}")

        webhook = TenantWebhook(
            tenant_id=tenant_id,
            name=name,
            url=url,
            events=events,
            secret=secret,
            headers=headers or {},
            created_by=created_by,
        )
        self.db.add(webhook)
        await self.db.flush()
        logger.info(f"Created webhook {webhook.id} for tenant {tenant_id}: {name}")
        return webhook

    async def get_webhook(self, webhook_id: UUID) -> Optional[TenantWebhook]:
        """Get a webhook by ID"""
        result = await self.db.execute(
            select(TenantWebhook).where(TenantWebhook.id == webhook_id)
        )
        return result.scalar_one_or_none()

    async def list_webhooks(
        self,
        tenant_id: str,
        enabled_only: bool = False,
    ) -> List[TenantWebhook]:
        """List all webhooks for a tenant"""
        query = select(TenantWebhook).where(TenantWebhook.tenant_id == tenant_id)
        if enabled_only:
            query = query.where(TenantWebhook.enabled == True)
        result = await self.db.execute(query.order_by(TenantWebhook.created_at.desc()))
        return list(result.scalars().all())

    async def update_webhook(
        self,
        webhook_id: UUID,
        name: Optional[str] = None,
        url: Optional[str] = None,
        events: Optional[List[str]] = None,
        secret: Optional[str] = None,
        headers: Optional[dict] = None,
        enabled: Optional[bool] = None,
    ) -> Optional[TenantWebhook]:
        """Update a webhook configuration"""
        webhook = await self.get_webhook(webhook_id)
        if not webhook:
            return None

        if name is not None:
            webhook.name = name
        if url is not None:
            webhook.url = url
        if events is not None:
            # Validate events
            valid_events = {"*"} | {e.value for e in WebhookEventType}
            for event in events:
                if event not in valid_events:
                    raise ValueError(f"Invalid event type: {event}")
            webhook.events = events
        if secret is not None:
            webhook.secret = secret
        if headers is not None:
            webhook.headers = headers
        if enabled is not None:
            webhook.enabled = enabled

        webhook.updated_at = datetime.utcnow()
        await self.db.flush()
        logger.info(f"Updated webhook {webhook_id}")
        return webhook

    async def delete_webhook(self, webhook_id: UUID) -> bool:
        """Delete a webhook configuration"""
        webhook = await self.get_webhook(webhook_id)
        if not webhook:
            return False
        await self.db.delete(webhook)
        await self.db.flush()
        logger.info(f"Deleted webhook {webhook_id}")
        return True

    # ============ Event Dispatching ============

    async def dispatch_event(
        self,
        event_type: str,
        subscription: Subscription,
        additional_data: Optional[dict] = None,
    ) -> List[WebhookDelivery]:
        """
        Dispatch an event to all matching webhooks for the subscription's tenant.

        Args:
            event_type: The event type (e.g., "subscription.created")
            subscription: The subscription that triggered the event
            additional_data: Optional additional data to include in payload

        Returns:
            List of WebhookDelivery records created
        """
        # Get all enabled webhooks for this tenant that match the event
        webhooks = await self.list_webhooks(subscription.tenant_id, enabled_only=True)
        matching_webhooks = [w for w in webhooks if w.matches_event(event_type)]

        if not matching_webhooks:
            logger.debug(f"No webhooks configured for event {event_type} in tenant {subscription.tenant_id}")
            return []

        # Build the payload
        payload = self._build_payload(event_type, subscription, additional_data)

        # Create delivery records and dispatch
        deliveries = []
        for webhook in matching_webhooks:
            delivery = WebhookDelivery(
                webhook_id=webhook.id,
                subscription_id=subscription.id,
                event_type=event_type,
                payload=payload,
                status=WebhookDeliveryStatus.PENDING.value,
            )
            self.db.add(delivery)
            await self.db.flush()
            deliveries.append(delivery)

            # Dispatch asynchronously (fire and forget for immediate response)
            asyncio.create_task(self._deliver_webhook(webhook, delivery))

        logger.info(f"Dispatched {event_type} to {len(deliveries)} webhooks for subscription {subscription.id}")
        return deliveries

    def _build_payload(
        self,
        event_type: str,
        subscription: Subscription,
        additional_data: Optional[dict] = None,
    ) -> dict:
        """Build the webhook payload"""
        payload = {
            "event": event_type,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "data": {
                "subscription_id": str(subscription.id),
                "application_id": subscription.application_id,
                "application_name": subscription.application_name,
                "api_id": subscription.api_id,
                "api_name": subscription.api_name,
                "tenant_id": subscription.tenant_id,
                "subscriber_id": subscription.subscriber_id,
                "subscriber_email": subscription.subscriber_email,
                "status": subscription.status.value if hasattr(subscription.status, 'value') else str(subscription.status),
            },
        }

        # Add event-specific data
        if event_type == WebhookEventType.SUBSCRIPTION_APPROVED.value:
            payload["data"]["approved_by"] = subscription.approved_by
            payload["data"]["approved_at"] = subscription.approved_at.isoformat() + "Z" if subscription.approved_at else None

        elif event_type == WebhookEventType.SUBSCRIPTION_REVOKED.value:
            payload["data"]["revoked_by"] = subscription.revoked_by
            payload["data"]["revoked_at"] = subscription.revoked_at.isoformat() + "Z" if subscription.revoked_at else None
            payload["data"]["reason"] = subscription.status_reason

        elif event_type == WebhookEventType.SUBSCRIPTION_KEY_ROTATED.value:
            payload["data"]["rotation_count"] = subscription.rotation_count
            payload["data"]["last_rotated_at"] = subscription.last_rotated_at.isoformat() + "Z" if subscription.last_rotated_at else None
            payload["data"]["grace_period_expires_at"] = subscription.previous_key_expires_at.isoformat() + "Z" if subscription.previous_key_expires_at else None

        # Add any additional data
        if additional_data:
            payload["data"].update(additional_data)

        return payload

    def _generate_signature(self, secret: str, payload: dict) -> str:
        """Generate HMAC-SHA256 signature for the payload"""
        payload_bytes = json.dumps(payload, sort_keys=True).encode('utf-8')
        signature = hmac.new(
            secret.encode('utf-8'),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()
        return f"sha256={signature}"

    async def _deliver_webhook(
        self,
        webhook: TenantWebhook,
        delivery: WebhookDelivery,
    ) -> None:
        """
        Attempt to deliver a webhook with retry logic.

        Uses exponential backoff: 1min, 5min, 15min, 1h, 2h
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            while delivery.attempt_count < delivery.max_attempts:
                delivery.attempt_count += 1
                delivery.last_attempt_at = datetime.utcnow()

                try:
                    # Build headers
                    headers = {
                        "Content-Type": "application/json",
                        "User-Agent": "STOA-Webhook/1.0",
                        "X-Webhook-Event": delivery.event_type,
                        "X-Webhook-Delivery": str(delivery.id),
                    }

                    # Add HMAC signature if secret is configured
                    if webhook.secret:
                        signature = self._generate_signature(webhook.secret, delivery.payload)
                        headers["X-Webhook-Signature"] = signature

                    # Add custom headers from webhook config
                    if webhook.headers:
                        headers.update(webhook.headers)

                    # Send the request
                    response = await client.post(
                        webhook.url,
                        json=delivery.payload,
                        headers=headers,
                    )

                    delivery.response_status_code = response.status_code
                    delivery.response_body = response.text[:2000] if response.text else None  # Truncate response

                    # Check for success (2xx status codes)
                    if 200 <= response.status_code < 300:
                        delivery.status = WebhookDeliveryStatus.SUCCESS.value
                        delivery.delivered_at = datetime.utcnow()
                        delivery.next_retry_at = None
                        await self.db.commit()
                        logger.info(f"Webhook {webhook.id} delivered successfully for delivery {delivery.id}")
                        return
                    else:
                        # Non-2xx response, will retry
                        delivery.error_message = f"HTTP {response.status_code}: {response.text[:500]}"
                        logger.warning(f"Webhook {webhook.id} returned {response.status_code}, attempt {delivery.attempt_count}/{delivery.max_attempts}")

                except httpx.TimeoutException as e:
                    delivery.error_message = f"Timeout: {str(e)}"
                    logger.warning(f"Webhook {webhook.id} timed out, attempt {delivery.attempt_count}/{delivery.max_attempts}")

                except httpx.RequestError as e:
                    delivery.error_message = f"Request error: {str(e)}"
                    logger.warning(f"Webhook {webhook.id} request failed: {e}, attempt {delivery.attempt_count}/{delivery.max_attempts}")

                except Exception as e:
                    delivery.error_message = f"Unexpected error: {str(e)}"
                    logger.error(f"Webhook {webhook.id} unexpected error: {e}", exc_info=True)

                # Schedule retry if attempts remaining
                if delivery.attempt_count < delivery.max_attempts:
                    retry_delay = RETRY_DELAYS[min(delivery.attempt_count - 1, len(RETRY_DELAYS) - 1)]
                    delivery.next_retry_at = datetime.utcnow() + timedelta(seconds=retry_delay)
                    delivery.status = WebhookDeliveryStatus.RETRYING.value
                    await self.db.commit()

                    # Wait before retrying
                    await asyncio.sleep(retry_delay)
                else:
                    # Max attempts reached
                    delivery.status = WebhookDeliveryStatus.FAILED.value
                    delivery.next_retry_at = None
                    await self.db.commit()
                    logger.error(f"Webhook {webhook.id} failed after {delivery.max_attempts} attempts for delivery {delivery.id}")

    # ============ Delivery History ============

    async def get_delivery_history(
        self,
        webhook_id: UUID,
        limit: int = 50,
    ) -> List[WebhookDelivery]:
        """Get recent delivery history for a webhook"""
        result = await self.db.execute(
            select(WebhookDelivery)
            .where(WebhookDelivery.webhook_id == webhook_id)
            .order_by(WebhookDelivery.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def retry_delivery(self, delivery_id: UUID) -> Optional[WebhookDelivery]:
        """Manually retry a failed delivery"""
        result = await self.db.execute(
            select(WebhookDelivery).where(WebhookDelivery.id == delivery_id)
        )
        delivery = result.scalar_one_or_none()
        if not delivery:
            return None

        if delivery.status != WebhookDeliveryStatus.FAILED.value:
            raise ValueError("Can only retry failed deliveries")

        # Get the webhook
        webhook = await self.get_webhook(delivery.webhook_id)
        if not webhook:
            raise ValueError("Webhook no longer exists")

        # Reset delivery for retry
        delivery.status = WebhookDeliveryStatus.PENDING.value
        delivery.attempt_count = 0
        delivery.next_retry_at = None
        delivery.error_message = None
        await self.db.flush()

        # Dispatch again
        asyncio.create_task(self._deliver_webhook(webhook, delivery))
        return delivery


# ============ Event Emission Helpers ============

async def emit_subscription_created(db: AsyncSession, subscription: Subscription) -> None:
    """Emit subscription.created event"""
    service = WebhookService(db)
    await service.dispatch_event(
        WebhookEventType.SUBSCRIPTION_CREATED.value,
        subscription,
    )


async def emit_subscription_approved(db: AsyncSession, subscription: Subscription) -> None:
    """Emit subscription.approved event"""
    service = WebhookService(db)
    await service.dispatch_event(
        WebhookEventType.SUBSCRIPTION_APPROVED.value,
        subscription,
    )


async def emit_subscription_revoked(db: AsyncSession, subscription: Subscription) -> None:
    """Emit subscription.revoked event"""
    service = WebhookService(db)
    await service.dispatch_event(
        WebhookEventType.SUBSCRIPTION_REVOKED.value,
        subscription,
    )


async def emit_subscription_key_rotated(
    db: AsyncSession,
    subscription: Subscription,
    grace_period_hours: int,
) -> None:
    """Emit subscription.key_rotated event"""
    service = WebhookService(db)
    await service.dispatch_event(
        WebhookEventType.SUBSCRIPTION_KEY_ROTATED.value,
        subscription,
        additional_data={"grace_period_hours": grace_period_hours},
    )
