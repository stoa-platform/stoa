"""
Gateway Health Worker - Marks stale gateways as OFFLINE (ADR-028).

This worker runs periodically to check for gateways that have not sent
a heartbeat within the timeout window (default: 90 seconds).

Gateways that miss heartbeats are marked OFFLINE to provide accurate
real-time status visibility in the Console UI.
"""
import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_session_factory
from ..models.gateway_instance import GatewayInstance, GatewayInstanceStatus, GatewayType

logger = logging.getLogger(__name__)


class GatewayHealthWorker:
    """
    Worker that periodically checks gateway heartbeats and marks
    stale gateways as OFFLINE.
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

            # Wait for next check interval
            await asyncio.sleep(self._check_interval)

    async def stop(self):
        """Stop the health check worker."""
        logger.info("Stopping Gateway Health Worker...")
        self._running = False

    async def _check_gateway_health(self):
        """Check all gateways for stale heartbeats."""
        session_factory = get_session_factory()
        async with session_factory() as session:
            await self._mark_stale_gateways_offline(session)
            await session.commit()

    async def _mark_stale_gateways_offline(self, session: AsyncSession):
        """Find and mark stale gateways as OFFLINE."""
        cutoff_time = datetime.now(UTC) - timedelta(seconds=self._heartbeat_timeout)

        # Find STOA gateways (native and sidecar) that are ONLINE but have stale heartbeats
        # Only check auto-registered gateways (STOA and STOA_SIDECAR types)
        stmt = select(GatewayInstance).where(
            GatewayInstance.gateway_type.in_([GatewayType.STOA, GatewayType.STOA_SIDECAR]),
            GatewayInstance.status == GatewayInstanceStatus.ONLINE,
            GatewayInstance.last_health_check < cutoff_time,
        )
        result = await session.execute(stmt)
        stale_gateways = result.scalars().all()

        if not stale_gateways:
            return

        # Mark each stale gateway as OFFLINE
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
                "last_heartbeat": (
                    gateway.last_health_check.isoformat() if gateway.last_health_check else None
                ),
            }

        logger.info("Marked %d gateways as OFFLINE due to heartbeat timeout", len(stale_gateways))


# Global instance
gateway_health_worker = GatewayHealthWorker()
