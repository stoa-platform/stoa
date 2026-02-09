"""Provisioning service for gateway auto-provisioning on subscription approval (CAB-800).

Orchestrates application creation/deletion via the Gateway Adapter Pattern.
Uses AdapterRegistry to resolve the correct gateway adapter per API deployment.
Falls back to the default webMethods adapter when no gateway deployment exists.

CAB-1121 Phase 3: Enriches app_spec with consumer/plan context and pushes
rate-limit policies to the gateway on provision/deprovision.
"""

import asyncio
import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters import AdapterRegistry
from ..adapters.gateway_adapter_interface import GatewayAdapterInterface
from ..models.subscription import ProvisioningStatus, Subscription
from ..repositories.consumer import ConsumerRepository
from ..repositories.plan import PlanRepository

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAYS = [5, 15, 45]  # seconds

# Default adapter — resolved via AdapterRegistry (no hard-coded import)
_default_adapter = AdapterRegistry.create("webmethods")

# Backward-compatible alias used by tests that patch 'gateway_service'
gateway_service = _default_adapter._svc


async def _resolve_adapter(db: AsyncSession, api_id: str, tenant_id: str) -> GatewayAdapterInterface:
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

    # Build base app_spec
    app_spec = {
        "subscription_id": str(subscription.id),
        "application_name": subscription.application_name,
        "api_id": subscription.api_id,
        "tenant_id": subscription.tenant_id,
        "subscriber_email": subscription.subscriber_email,
        "correlation_id": correlation_id,
    }

    # Enrich with consumer context (CAB-1121 Phase 3)
    consumer = None
    if subscription.consumer_id:
        try:
            consumer_repo = ConsumerRepository(db)
            consumer = await consumer_repo.get_by_id(
                subscription.consumer_id
                if isinstance(subscription.consumer_id, UUID)
                else UUID(str(subscription.consumer_id))
            )
        except Exception as e:
            logger.warning("Failed to load consumer %s: %s", subscription.consumer_id, e)

    if consumer:
        app_spec["consumer_id"] = str(consumer.id)
        app_spec["consumer_external_id"] = consumer.external_id
        app_spec["keycloak_client_id"] = consumer.keycloak_client_id or ""

    # Enrich with plan context (CAB-1121 Phase 3)
    plan = None
    if subscription.plan_id:
        try:
            plan_repo = PlanRepository(db)
            plan = await plan_repo.get_by_id(UUID(str(subscription.plan_id)))
        except Exception as e:
            logger.warning("Failed to load plan %s: %s", subscription.plan_id, e)

    if plan:
        app_spec["plan_slug"] = plan.slug
        app_spec["rate_limit_per_second"] = plan.rate_limit_per_second
        app_spec["rate_limit_per_minute"] = plan.rate_limit_per_minute
        app_spec["daily_request_limit"] = plan.daily_request_limit
        app_spec["monthly_request_limit"] = plan.monthly_request_limit
        app_spec["burst_limit"] = plan.burst_limit

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

            # Push rate-limit policy if plan has quotas (CAB-1121 Phase 3)
            await _push_rate_limit_policy(adapter, subscription, plan, consumer, auth_token, correlation_id)

            logger.info(
                f"Provisioned gateway app {result.resource_id} for subscription "
                f"{subscription.id} (attempt {attempt})",
                extra={"correlation_id": correlation_id, "tenant_id": subscription.tenant_id},
            )
            return

        except Exception as e:
            last_error = str(e)
            logger.warning(
                f"Provisioning attempt {attempt}/{MAX_RETRIES} failed for " f"subscription {subscription.id}: {e}",
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
        f"Provisioning failed after {MAX_RETRIES} attempts for " f"subscription {subscription.id}: {last_error}",
        extra={"correlation_id": correlation_id, "tenant_id": subscription.tenant_id},
    )


async def _push_rate_limit_policy(
    adapter: GatewayAdapterInterface,
    subscription: Subscription,
    plan: object | None,
    consumer: object | None,
    auth_token: str | None,
    correlation_id: str,
) -> None:
    """Push a rate-limit policy to the gateway after successful provisioning.

    Non-blocking: logs warnings on failure but does not raise.
    """
    if not plan:
        return

    rate_limit = getattr(plan, "rate_limit_per_minute", None) or getattr(plan, "rate_limit_per_second", None)
    if not rate_limit:
        return

    consumer_ext_id = getattr(consumer, "external_id", "unknown") if consumer else "unknown"
    plan_slug = getattr(plan, "slug", "default")

    policy_spec = {
        "id": f"quota-{subscription.id}",
        "name": f"rate-limit-{consumer_ext_id}-{plan_slug}",
        "type": "rate_limit",
        "api_id": subscription.api_id,
        "config": {
            "maxRequests": getattr(plan, "rate_limit_per_minute", None) or 100,
            "intervalSeconds": 60,
        },
        "priority": 50,
    }

    try:
        result = await adapter.upsert_policy(policy_spec, auth_token=auth_token)
        if result.success:
            logger.info(
                "Pushed rate-limit policy %s for subscription %s",
                policy_spec["id"],
                subscription.id,
                extra={"correlation_id": correlation_id},
            )
        else:
            logger.warning(
                "Failed to push rate-limit policy for subscription %s: %s",
                subscription.id,
                result.error,
                extra={"correlation_id": correlation_id},
            )
    except Exception as e:
        logger.warning(
            "Error pushing rate-limit policy for subscription %s: %s",
            subscription.id,
            e,
            extra={"correlation_id": correlation_id},
        )


async def _cleanup_rate_limit_policy(
    adapter: GatewayAdapterInterface,
    subscription: Subscription,
    auth_token: str | None,
    correlation_id: str,
) -> None:
    """Remove the rate-limit policy from the gateway on deprovision.

    Non-blocking: logs warnings on failure but does not raise.
    """
    policy_id = f"quota-{subscription.id}"
    try:
        result = await adapter.delete_policy(policy_id, auth_token=auth_token)
        if result.success:
            logger.info(
                "Cleaned up rate-limit policy %s for subscription %s",
                policy_id,
                subscription.id,
                extra={"correlation_id": correlation_id},
            )
        else:
            logger.warning(
                "Failed to clean up rate-limit policy %s: %s",
                policy_id,
                result.error,
                extra={"correlation_id": correlation_id},
            )
    except Exception as e:
        logger.warning(
            "Error cleaning up rate-limit policy %s: %s",
            policy_id,
            e,
            extra={"correlation_id": correlation_id},
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
        # Clean up rate-limit policy first (CAB-1121 Phase 3)
        await _cleanup_rate_limit_policy(adapter, subscription, auth_token, correlation_id)

        result = await adapter.deprovision_application(subscription.gateway_app_id, auth_token=auth_token)

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
