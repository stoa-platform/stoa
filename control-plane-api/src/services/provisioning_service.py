"""Provisioning service for gateway auto-provisioning on subscription approval (CAB-800).

Orchestrates application creation/deletion in webMethods when subscriptions
are approved or revoked. Runs provisioning asynchronously with retry logic.
"""
import asyncio
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.subscription import Subscription, ProvisioningStatus
from .gateway_service import gateway_service

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAYS = [5, 15, 45]  # seconds


async def provision_on_approval(
    db: AsyncSession,
    subscription: Subscription,
    auth_token: str | None,
    correlation_id: str,
) -> None:
    """Provision a gateway application after subscription approval.

    Sets provisioning_status through the lifecycle:
    PENDING -> PROVISIONING -> READY (or FAILED with retry).

    This function is meant to be called via asyncio.create_task()
    so that the approval endpoint returns immediately.

    Args:
        db: Database session
        subscription: The approved subscription
        auth_token: JWT token for OIDC proxy mode
        correlation_id: Request correlation ID
    """
    subscription.provisioning_status = ProvisioningStatus.PROVISIONING
    subscription.provisioning_error = None
    await db.commit()

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = await gateway_service.provision_application(
                subscription_id=str(subscription.id),
                application_name=subscription.application_name,
                api_id=subscription.api_id,
                tenant_id=subscription.tenant_id,
                subscriber_email=subscription.subscriber_email,
                correlation_id=correlation_id,
                auth_token=auth_token,
            )

            subscription.provisioning_status = ProvisioningStatus.READY
            subscription.gateway_app_id = result["app_id"]
            subscription.provisioned_at = datetime.utcnow()
            subscription.provisioning_error = None
            await db.commit()

            logger.info(
                f"Provisioned gateway app {result['app_id']} for subscription {subscription.id} "
                f"(attempt {attempt})",
                extra={"correlation_id": correlation_id, "tenant_id": subscription.tenant_id},
            )
            return

        except Exception as e:
            last_error = str(e)
            logger.warning(
                f"Provisioning attempt {attempt}/{MAX_RETRIES} failed for subscription {subscription.id}: {e}",
                extra={"correlation_id": correlation_id},
            )

            if attempt < MAX_RETRIES:
                delay = RETRY_DELAYS[attempt - 1]
                await asyncio.sleep(delay)

    # All retries exhausted
    subscription.provisioning_status = ProvisioningStatus.FAILED
    subscription.provisioning_error = last_error
    await db.commit()

    logger.error(
        f"Provisioning failed after {MAX_RETRIES} attempts for subscription {subscription.id}: {last_error}",
        extra={"correlation_id": correlation_id, "tenant_id": subscription.tenant_id},
    )


async def deprovision_on_revocation(
    db: AsyncSession,
    subscription: Subscription,
    auth_token: str | None,
    correlation_id: str,
) -> None:
    """Remove a gateway application when a subscription is revoked.

    Args:
        db: Database session
        subscription: The revoked subscription
        auth_token: JWT token for OIDC proxy mode
        correlation_id: Request correlation ID
    """
    if not subscription.gateway_app_id:
        return

    subscription.provisioning_status = ProvisioningStatus.DEPROVISIONING
    await db.commit()

    try:
        await gateway_service.deprovision_application(
            app_id=subscription.gateway_app_id,
            correlation_id=correlation_id,
            auth_token=auth_token,
        )

        subscription.provisioning_status = ProvisioningStatus.DEPROVISIONED
        subscription.gateway_app_id = None
        await db.commit()

        logger.info(
            f"Deprovisioned gateway app for subscription {subscription.id}",
            extra={"correlation_id": correlation_id},
        )

    except Exception as e:
        subscription.provisioning_status = ProvisioningStatus.FAILED
        subscription.provisioning_error = f"Deprovision failed: {e}"
        await db.commit()

        logger.error(
            f"Deprovision failed for subscription {subscription.id}: {e}",
            extra={"correlation_id": correlation_id},
        )
