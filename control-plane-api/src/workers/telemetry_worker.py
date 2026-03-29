"""Telemetry Worker — periodic pull-based telemetry collection.

Runs every TELEMETRY_POLL_INTERVAL seconds, iterates all registered
gateway instances, and pulls access logs via their TelemetryAdapter.

Non-blocking: individual gateway failures are logged as warnings,
never crash the worker or the API.

See CAB-1682 for architectural context.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import _get_session_factory
from ..models.gateway_instance import GatewayInstance, GatewayInstanceStatus
from ..services.telemetry_collector import telemetry_collector

logger = logging.getLogger("stoa.telemetry.worker")

# Default poll interval: 60 seconds
TELEMETRY_POLL_INTERVAL = getattr(settings, "TELEMETRY_POLL_INTERVAL_SECONDS", 60)

# How far back to look on first poll
INITIAL_LOOKBACK = timedelta(minutes=5)


class TelemetryWorker:
    """Background worker that polls gateway instances for telemetry data."""

    def __init__(self):
        self._running = False
        self._last_poll: dict[str, datetime] = {}

    async def start(self) -> None:
        logger.info("Starting Telemetry Worker (interval=%ds)", TELEMETRY_POLL_INTERVAL)
        self._running = True

        while self._running:
            try:
                await self._poll_all_gateways()
            except Exception as e:
                logger.error("Telemetry poll cycle error: %s", e, exc_info=True)

            await asyncio.sleep(TELEMETRY_POLL_INTERVAL)

    async def stop(self) -> None:
        logger.info("Stopping Telemetry Worker...")
        self._running = False

    async def _poll_all_gateways(self) -> None:
        session_factory = _get_session_factory()
        async with session_factory() as session:
            gateways = await self._get_online_gateways(session)

        for gw in gateways:
            try:
                await self._poll_single_gateway(gw)
            except Exception as e:
                logger.warning(
                    "Telemetry poll failed for gateway %s (%s): %s",
                    gw.name,
                    gw.gateway_type.value,
                    e,
                )

    async def _get_online_gateways(self, session: AsyncSession) -> list[GatewayInstance]:
        stmt = select(GatewayInstance).where(
            GatewayInstance.status == GatewayInstanceStatus.ONLINE,
            GatewayInstance.deleted_at.is_(None),
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def _poll_single_gateway(self, gw: GatewayInstance) -> None:
        from ..adapters.telemetry_registry import TelemetryAdapterRegistry

        gw_type = gw.gateway_type.value if hasattr(gw.gateway_type, "value") else str(gw.gateway_type)

        if not TelemetryAdapterRegistry.has_type(gw_type):
            return

        if gw.source == "self_register":
            logger.debug("Skipping telemetry pull for agent-managed gateway %s", gw.name)
            return

        config = {
            "base_url": gw.base_url,
            "auth_config": gw.auth_config or {},
        }

        adapter = TelemetryAdapterRegistry.create(gw_type, config=config)

        gw_id = str(gw.id)
        since = self._last_poll.get(gw_id, datetime.now(UTC) - INITIAL_LOOKBACK)

        logs = await adapter.get_access_logs(since=since, limit=1000)

        if logs:
            for entry in logs:
                entry.setdefault("gateway_type", gw_type)
                entry.setdefault("gateway_id", gw_id)

            accepted = await telemetry_collector.ingest(logs, source=f"pull:{gw_type}")
            if accepted:
                logger.debug("Pulled %d logs from %s (%s)", len(logs), gw.name, gw_type)
            else:
                logger.warning("Backpressure: rejected %d logs from %s", len(logs), gw.name)

        self._last_poll[gw_id] = datetime.now(UTC)


# Global instance
telemetry_worker = TelemetryWorker()
