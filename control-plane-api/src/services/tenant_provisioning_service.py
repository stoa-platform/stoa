"""Tenant provisioning service — saga-based provisioning pipeline (CAB-1315).

Mirrors provisioning_service.py pattern: PENDING → PROVISIONING → READY | FAILED.
Async task creates its own DB session (not request-scoped) because
asyncio.create_task() outlives the router's session.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from ..config import settings
from ..database import get_db
from ..models.gateway_policy import GatewayPolicy, PolicyScope, PolicyType
from ..models.tenant import TenantProvisioningStatus, TenantStatus
from ..repositories.gateway_policy import GatewayPolicyRepository
from ..repositories.tenant import TenantRepository
from ..services.kafka_service import Topics, kafka_service
from ..services.keycloak_service import keycloak_service

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAYS = [5, 15, 45]


async def _retry_kc_group(tenant_id: str, display_name: str) -> str:
    """Retry Keycloak group creation with backoff. Returns group ID."""
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            group_id = await keycloak_service.setup_tenant_group(tenant_id, display_name)
            return group_id
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAYS[attempt]
                logger.warning(
                    f"KC group creation attempt {attempt + 1} failed for {tenant_id}: {e}, "
                    f"retrying in {delay}s..."
                )
                await asyncio.sleep(delay)
            else:
                logger.error(f"KC group creation failed after {MAX_RETRIES} attempts for {tenant_id}: {e}")
    raise last_error  # type: ignore[misc]


async def _seed_default_rate_limit_policy(db_session, tenant_id: str) -> None:
    """Create default rate-limit policy for the tenant."""
    repo = GatewayPolicyRepository(db_session)
    policy = GatewayPolicy(
        id=str(uuid.uuid4()),
        name=f"default-rate-limit-{tenant_id}",
        policy_type=PolicyType.RATE_LIMIT.value,
        tenant_id=tenant_id,
        scope=PolicyScope.TENANT.value,
        config={
            "maxRequests": settings.TENANT_DEFAULT_RATE_LIMIT_RPM,
            "intervalSeconds": 60,
        },
        enabled=True,
        priority=100,
    )
    await repo.create(policy)
    logger.info(f"Seeded default rate-limit policy for tenant {tenant_id}")


async def provision_tenant(
    tenant_id: str,
    owner_email: str,
    display_name: str,
    correlation_id: str,
) -> None:
    """Saga: PENDING → PROVISIONING → READY | FAILED.

    Creates its own DB session via get_db() — does NOT receive the router's session
    because asyncio.create_task() outlives the request-scoped session.
    """
    logger.info(f"Starting provisioning for tenant {tenant_id} (correlation={correlation_id})")

    async for db in get_db():
        try:
            repo = TenantRepository(db)
            tenant = await repo.get_by_id(tenant_id)
            if not tenant:
                logger.error(f"Tenant {tenant_id} not found during provisioning")
                return

            # Set PROVISIONING status
            tenant.provisioning_status = TenantProvisioningStatus.PROVISIONING.value
            tenant.provisioning_started_at = datetime.now(UTC)
            tenant.provisioning_attempts = (tenant.provisioning_attempts or 0) + 1
            tenant.provisioning_error = None
            await db.commit()

            # Step 1: KC group creation (blocking gate, retried)
            try:
                group_id = await _retry_kc_group(tenant_id, display_name)
                tenant.kc_group_id = group_id
                await db.commit()
                logger.info(f"KC group created for {tenant_id}: {group_id}")
            except Exception as e:
                tenant.provisioning_status = TenantProvisioningStatus.FAILED.value
                tenant.provisioning_error = f"KC group creation failed: {e}"
                await db.commit()
                logger.error(f"Provisioning FAILED for {tenant_id}: {e}")
                return

            # Step 2: Admin user creation (best-effort)
            try:
                user_id = await keycloak_service.create_user(
                    username=f"admin-{tenant_id}",
                    email=owner_email,
                    first_name="Admin",
                    last_name=display_name,
                    tenant_id=tenant_id,
                    roles=["tenant-admin"],
                )
                logger.info(f"Admin user created for {tenant_id}: {user_id}")
            except Exception as e:
                logger.warning(f"Admin user creation failed for {tenant_id} (best-effort): {e}")

            # Step 3: Add user to tenant group (best-effort)
            try:
                await keycloak_service.add_user_to_tenant(f"admin-{tenant_id}", tenant_id)
            except Exception as e:
                logger.warning(f"Add user to tenant failed for {tenant_id} (best-effort): {e}")

            # Step 4: Seed default rate-limit policy
            try:
                await _seed_default_rate_limit_policy(db, tenant_id)
                await db.commit()
            except Exception as e:
                logger.warning(f"Policy seed failed for {tenant_id} (best-effort): {e}")

            # Step 5: Emit Kafka events
            try:
                await kafka_service.publish(
                    topic=Topics.TENANT_EVENTS,
                    event_type="tenant-provisioned",
                    tenant_id=tenant_id,
                    payload={"tenant_id": tenant_id, "kc_group_id": tenant.kc_group_id},
                )
                await kafka_service.publish(
                    topic=Topics.TENANT_PROVISIONING,
                    event_type="tenant-namespace-requested",
                    tenant_id=tenant_id,
                    payload={"tenant_id": tenant_id, "namespace": f"tenant-{tenant_id}"},
                )
                await kafka_service.publish(
                    topic=Topics.TENANT_PROVISIONING,
                    event_type="tenant-resources-seed-requested",
                    tenant_id=tenant_id,
                    payload={"tenant_id": tenant_id},
                )
            except Exception as e:
                logger.warning(f"Kafka event emission failed for {tenant_id}: {e}")

            # Step 6: Set READY
            tenant.provisioning_status = TenantProvisioningStatus.READY.value
            await db.commit()
            logger.info(f"Provisioning READY for tenant {tenant_id}")

        except Exception as e:
            logger.error(f"Unexpected error during provisioning of {tenant_id}: {e}")
            try:
                tenant = await repo.get_by_id(tenant_id)
                if tenant:
                    tenant.provisioning_status = TenantProvisioningStatus.FAILED.value
                    tenant.provisioning_error = str(e)
                    await db.commit()
            except Exception:
                logger.error(f"Failed to update status to FAILED for {tenant_id}")
        break  # Only iterate once through the generator


async def deprovision_tenant(
    tenant_id: str,
    user_id: str,
    correlation_id: str,
) -> None:
    """Reverse saga: cleanup all tenant resources."""
    logger.info(f"Starting deprovisioning for tenant {tenant_id} (correlation={correlation_id})")

    async for db in get_db():
        try:
            repo = TenantRepository(db)
            tenant = await repo.get_by_id(tenant_id)
            if not tenant:
                logger.error(f"Tenant {tenant_id} not found during deprovisioning")
                return

            # Step 1: Emit deprovisioning-started
            try:
                await kafka_service.publish(
                    topic=Topics.TENANT_EVENTS,
                    event_type="tenant-deprovisioning-started",
                    tenant_id=tenant_id,
                    payload={"tenant_id": tenant_id},
                    user_id=user_id,
                )
            except Exception as e:
                logger.warning(f"Kafka event failed for deprovision of {tenant_id}: {e}")

            # Step 2: Disable gateway policies
            try:
                policy_repo = GatewayPolicyRepository(db)
                policies = await policy_repo.list_all(tenant_id=tenant_id)
                for policy in policies:
                    policy.enabled = False
                await db.commit()
                logger.info(f"Disabled {len(policies)} policies for tenant {tenant_id}")
            except Exception as e:
                logger.warning(f"Policy disable failed for {tenant_id}: {e}")

            # Step 3: Delete KC group (best-effort)
            try:
                await keycloak_service.delete_tenant_group(tenant_id)
                logger.info(f"KC group deleted for {tenant_id}")
            except Exception as e:
                logger.warning(f"KC group deletion failed for {tenant_id}: {e}")

            # Step 4: Emit namespace cleanup
            try:
                await kafka_service.publish(
                    topic=Topics.TENANT_PROVISIONING,
                    event_type="tenant-namespace-cleanup-requested",
                    tenant_id=tenant_id,
                    payload={"tenant_id": tenant_id, "namespace": f"tenant-{tenant_id}"},
                    user_id=user_id,
                )
            except Exception as e:
                logger.warning(f"Kafka namespace cleanup event failed for {tenant_id}: {e}")

            # Step 5: Archive tenant
            tenant.status = TenantStatus.ARCHIVED.value
            await db.commit()

            # Step 6: Emit deprovisioned event
            try:
                await kafka_service.publish(
                    topic=Topics.TENANT_EVENTS,
                    event_type="tenant-deprovisioned",
                    tenant_id=tenant_id,
                    payload={"tenant_id": tenant_id},
                    user_id=user_id,
                )
            except Exception as e:
                logger.warning(f"Kafka deprovisioned event failed for {tenant_id}: {e}")

            logger.info(f"Deprovisioning complete for tenant {tenant_id}")

        except Exception as e:
            logger.error(f"Unexpected error during deprovisioning of {tenant_id}: {e}")
        break  # Only iterate once through the generator
