"""
Gateway Health Worker - Universal health checking for all gateway types (ADR-028).

Two strategies:
1. **Heartbeat-based** (all STOA types): marks stale gateways as OFFLINE
   when heartbeat times out (default: 90 seconds).
2. **Active polling** (Kong, Gravitee, webMethods, Apigee, AWS, Azure): periodically
   calls adapter.health_check() with a per-check timeout (default: 10s) and updates
   status based on response. 3 consecutive failures → OFFLINE (only if gateway was
   previously confirmed healthy; never-reachable gateways keep their seeded status).

Both strategies run on the same interval (GATEWAY_HEALTH_CHECK_INTERVAL_SECONDS).
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import not_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters.registry import AdapterRegistry
from ..config import settings
from ..database import _get_session_factory
from ..models.gateway_instance import GatewayInstance, GatewayInstanceStatus, GatewayType
from ..services.credential_resolver import create_adapter_with_credentials

logger = logging.getLogger(__name__)

# STOA types use heartbeat-based health (auto-register + send heartbeats)
_HEARTBEAT_TYPES = frozenset(
    {
        GatewayType.STOA,
        GatewayType.STOA_EDGE_MCP,
        GatewayType.STOA_SIDECAR,
        GatewayType.STOA_PROXY,
        GatewayType.STOA_SHADOW,
    }
)

# Max consecutive failures before marking OFFLINE
_MAX_CONSECUTIVE_FAILURES = 3

# Per-check timeout in seconds
_HEALTH_CHECK_TIMEOUT = 10


class GatewayHealthWorker:
    """
    Worker that periodically checks gateway health via two strategies:
    - Heartbeat timeout for STOA gateways
    - Active polling for external gateways (Kong, Gravitee, etc.)
    """

    def __init__(self):
        self._running = False
        self._check_interval = settings.GATEWAY_HEALTH_CHECK_INTERVAL_SECONDS
        self._heartbeat_timeout = settings.GATEWAY_HEARTBEAT_TIMEOUT_SECONDS

    async def start(self):
        """Start the health check worker."""
        logger.info(
            "Starting Gateway Health Worker: interval=%ds, timeout=%ds",
            self._check_interval,
            self._heartbeat_timeout,
        )
        self._running = True

        while self._running:
            try:
                await self._check_gateway_health()
            except Exception as e:
                logger.error("Error in gateway health check: %s", e, exc_info=True)

            await asyncio.sleep(self._check_interval)

    async def stop(self):
        """Stop the health check worker."""
        logger.info("Stopping Gateway Health Worker...")
        self._running = False

    async def _check_gateway_health(self):
        """Check all gateways — heartbeat-based for STOA, active polling for external."""
        session_factory = _get_session_factory()
        async with session_factory() as session:
            await self._mark_stale_gateways_offline(session)
            await self._active_health_check_external_gateways(session)
            await self._purge_stale_gateways(session)
            await session.commit()

    async def _mark_stale_gateways_offline(self, session: AsyncSession):
        """Find and mark stale STOA gateways as OFFLINE (heartbeat-based)."""
        cutoff_time = datetime.now(UTC) - timedelta(seconds=self._heartbeat_timeout)

        stmt = select(GatewayInstance).where(
            GatewayInstance.gateway_type.in_(list(_HEARTBEAT_TYPES)),
            GatewayInstance.status.in_(
                [GatewayInstanceStatus.ONLINE, GatewayInstanceStatus.DEGRADED]
            ),
            GatewayInstance.last_health_check < cutoff_time,
            GatewayInstance.deleted_at.is_(None),
        )
        result = await session.execute(stmt)
        stale_gateways = result.scalars().all()

        if not stale_gateways:
            return

        for gateway in stale_gateways:
            logger.warning(
                "Gateway %s (%s) marked OFFLINE: no heartbeat since %s (cutoff: %s)",
                gateway.name,
                gateway.id,
                gateway.last_health_check.isoformat() if gateway.last_health_check else "never",
                cutoff_time.isoformat(),
            )

            gateway.status = GatewayInstanceStatus.OFFLINE
            gateway.health_details = {
                **(gateway.health_details or {}),
                "offline_reason": "heartbeat_timeout",
                "marked_offline_at": datetime.now(UTC).isoformat(),
                "last_heartbeat": (gateway.last_health_check.isoformat() if gateway.last_health_check else None),
            }

        logger.info("Marked %d gateways as OFFLINE due to heartbeat timeout", len(stale_gateways))

    async def _purge_stale_gateways(self, session: AsyncSession):
        """Soft-delete gateway instances that have been offline for longer than the purge TTL.

        Default: 7 days without any heartbeat → soft-deleted (CAB-1897).
        Protected instances are never purged.
        """
        purge_cutoff = datetime.now(UTC) - timedelta(days=settings.GATEWAY_PURGE_AFTER_DAYS)

        stmt = select(GatewayInstance).where(
            GatewayInstance.status == GatewayInstanceStatus.OFFLINE,
            GatewayInstance.last_health_check < purge_cutoff,
            GatewayInstance.deleted_at.is_(None),
            GatewayInstance.protected.is_(False),
        )
        result = await session.execute(stmt)
        stale_gateways = result.scalars().all()

        if not stale_gateways:
            return

        now = datetime.now(UTC)
        for gateway in stale_gateways:
            logger.info(
                "Purging stale gateway %s (%s): offline since %s (purge cutoff: %s)",
                gateway.name,
                gateway.id,
                gateway.last_health_check.isoformat() if gateway.last_health_check else "never",
                purge_cutoff.isoformat(),
            )
            gateway.deleted_at = now
            gateway.deleted_by = "system:auto-purge"

        logger.info(
            "Auto-purged %d stale gateway instances (offline > %d days)",
            len(stale_gateways),
            settings.GATEWAY_PURGE_AFTER_DAYS,
        )

    async def _active_health_check_external_gateways(self, session: AsyncSession):
        """Actively poll external gateways (non-STOA) via their adapter health_check().

        For each external gateway instance:
        1. Create adapter with base_url + auth_config from the instance record
        2. Call health_check() with a timeout
        3. On success: reset failure counter, mark ONLINE, update last_health_check
        4. On failure: increment counter. After 3 consecutive failures → OFFLINE
        """
        stmt = select(GatewayInstance).where(
            not_(GatewayInstance.gateway_type.in_(list(_HEARTBEAT_TYPES))),
            GatewayInstance.status != GatewayInstanceStatus.MAINTENANCE,
            GatewayInstance.deleted_at.is_(None),
        )
        result = await session.execute(stmt)
        external_gateways = result.scalars().all()

        if not external_gateways:
            return

        for gateway in external_gateways:
            await self._poll_single_gateway(session, gateway)

    async def _poll_single_gateway(self, session: AsyncSession, gateway: GatewayInstance):
        """Poll a single external gateway and update its status."""
        gw_type = gateway.gateway_type.value if hasattr(gateway.gateway_type, "value") else str(gateway.gateway_type)

        if not AdapterRegistry.has_type(gw_type):
            logger.debug("No adapter registered for gateway type %s, skipping %s", gw_type, gateway.name)
            return

        now = datetime.now(UTC)
        health_details = dict(gateway.health_details or {})
        consecutive_failures = health_details.get("consecutive_failures", 0)

        try:
            adapter = await create_adapter_with_credentials(
                gw_type, gateway.base_url, gateway.auth_config or {},
            )
            check_result = await asyncio.wait_for(adapter.health_check(), timeout=_HEALTH_CHECK_TIMEOUT)

            if check_result.success:
                gateway.status = GatewayInstanceStatus.ONLINE
                gateway.last_health_check = now
                gateway.health_details = {
                    **health_details,
                    "check_method": "active_poll",
                    "last_success_at": now.isoformat(),
                    "consecutive_failures": 0,
                    "last_check_data": check_result.data,
                }
                logger.debug("Gateway %s (%s) health check: ONLINE", gateway.name, gw_type)
            else:
                consecutive_failures += 1
                error_msg = check_result.error or "health_check returned success=False"
                self._handle_failure(gateway, health_details, consecutive_failures, error_msg, now)
                logger.warning("Gateway %s (%s) health check failed: %s", gateway.name, gw_type, error_msg)

        except TimeoutError:
            consecutive_failures += 1
            self._handle_failure(
                gateway, health_details, consecutive_failures, f"timeout after {_HEALTH_CHECK_TIMEOUT}s", now
            )
            logger.warning("Gateway %s (%s) health check timed out", gateway.name, gw_type)

        except Exception as e:
            consecutive_failures += 1
            self._handle_failure(gateway, health_details, consecutive_failures, str(e), now)
            logger.warning("Gateway %s (%s) health check error: %s", gateway.name, gw_type, e)

    def _handle_failure(
        self,
        gateway: GatewayInstance,
        health_details: dict,
        consecutive_failures: int,
        error_msg: str,
        now: datetime,
    ):
        """Update gateway health details on failure, mark OFFLINE after threshold."""
        gateway.health_details = {
            **health_details,
            "check_method": "active_poll",
            "consecutive_failures": consecutive_failures,
            "last_failure_at": now.isoformat(),
            "last_error": error_msg,
        }

        if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
            # Only transition to OFFLINE if gateway was previously confirmed healthy.
            # Gateways that have never been reachable from this worker (e.g. external VPS
            # not accessible from K8s) keep their seeded status to avoid false negatives.
            if gateway.last_health_check is not None:
                gateway.status = GatewayInstanceStatus.OFFLINE
                gateway.health_details["offline_reason"] = "consecutive_failures"
                gateway.health_details["marked_offline_at"] = now.isoformat()
                logger.warning(
                    "Gateway %s marked OFFLINE after %d consecutive failures",
                    gateway.name,
                    consecutive_failures,
                )
            else:
                logger.info(
                    "Gateway %s has %d consecutive failures but was never reachable, keeping status %s",
                    gateway.name,
                    consecutive_failures,
                    gateway.status.value,
                )


# Global instance
gateway_health_worker = GatewayHealthWorker()
