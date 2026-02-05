"""Provisioning service for gateway auto-provisioning on subscription approval (CAB-800).

Orchestrates application creation/deletion via the Gateway Adapter Pattern.
Uses AdapterRegistry to resolve the correct gateway adapter per API deployment.
Falls back to the default webMethods adapter when no gateway deployment exists.
"""
import asyncio
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters import AdapterRegistry
from ..adapters.gateway_adapter_interface import GatewayAdapterInterface
from ..models.subscription import ProvisioningStatus, Subscription

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAYS = [5, 15, 45]  # seconds

# Default adapter — resolved via AdapterRegistry (no hard-coded import)
_default_adapter = AdapterRegistry.create("webmethods")

# Backward-compatible alias used by tests that patch 'gateway_service'
gateway_service = _default_adapter._svc


async def _resolve_adapter(
    db: AsyncSession, api_id: str, tenant_id: str
) -> GatewayAdapterInterface:
    """Resolve the gateway adapter for an API.

    Looks up gateway_deployments to find which gateway the API is deployed to.
    Falls back to the default webMethods adapter if no deployment exists.
    """
    try:
        from ..repositories.gateway_deployment import GatewayDeploymentRepository
        from ..repositories.gateway_instance import GatewayInstanceRepository

        deploy_repo = GatewayDeploymentRepository(db)
        deployment = await deploy_repo.get_primary_for_api(api_id, tenant_id)

        if not deployment:
            return _default_adapter

        gw_repo = GatewayInstanceRepository(db)
        gateway = await gw_repo.get_by_id(deployment.gateway_instance_id)

        if not gateway:
            return _default_adapter

        return AdapterRegistry.create(
            gateway.gateway_type.value,
            config={"base_url": gateway.base_url, "auth_config": gateway.auth_config},
        )
    except Exception as e:
        logger.warning("Failed to resolve gateway adapter, using default: %s", e)
        return _default_adapter


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

    adapter = await _resolve_adapter(db, subscription.api_id, subscription.tenant_id)

    app_spec = {
        "subscription_id": str(subscription.id),
        "application_name": subscription.application_name,
        "api_id": subscription.api_id,
        "tenant_id": subscription.tenant_id,
        "subscriber_email": subscription.subscriber_email,
        "correlation_id": correlation_id,
    }

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = await adapter.provision_application(app_spec, auth_token=auth_token)

            if not result.success:
                raise RuntimeError(result.error or "Adapter returned failure")

            subscription.provisioning_status = ProvisioningStatus.READY
            subscription.gateway_app_id = result.resource_id
            subscription.provisioned_at = datetime.utcnow()
            subscription.provisioning_error = None
            await db.commit()

            logger.info(
                f"Provisioned gateway app {result.resource_id} for subscription "
                f"{subscription.id} (attempt {attempt})",
                extra={"correlation_id": correlation_id, "tenant_id": subscription.tenant_id},
            )
            return

        except Exception as e:
            last_error = str(e)
            logger.warning(
                f"Provisioning attempt {attempt}/{MAX_RETRIES} failed for "
                f"subscription {subscription.id}: {e}",
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
        f"Provisioning failed after {MAX_RETRIES} attempts for "
        f"subscription {subscription.id}: {last_error}",
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

    adapter = await _resolve_adapter(db, subscription.api_id, subscription.tenant_id)

    try:
        result = await adapter.deprovision_application(
            subscription.gateway_app_id, auth_token=auth_token
        )

        if not result.success:
            raise RuntimeError(result.error or "Adapter returned failure")

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
