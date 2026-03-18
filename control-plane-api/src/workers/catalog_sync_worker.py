"""Periodic catalog sync worker — safety net for the event-driven consumer.

Runs a full catalog sync at a configurable interval (default: 5 minutes)
to ensure the api_catalog table stays in sync with GitLab even if Kafka
events are missed due to network issues, restarts, etc.

Also runs an initial sync on startup so the catalog is populated
immediately after deployment.
"""

import asyncio
import logging
from datetime import UTC, datetime

from ..config import settings
from ..database import _get_session_factory
from ..services.git_service import git_service

logger = logging.getLogger(__name__)

# Default: sync every 5 minutes
DEFAULT_INTERVAL_SECONDS = 300


class CatalogSyncWorker:
    """Periodic worker that triggers a full catalog sync from GitLab."""

    def __init__(self) -> None:
        self._running = False
        self._interval = getattr(
            settings, "CATALOG_SYNC_INTERVAL_SECONDS", DEFAULT_INTERVAL_SECONDS
        )
        self._last_run: datetime | None = None
        self._last_error: str | None = None

    @property
    def status(self) -> dict:
        return {
            "active": self._running,
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "last_error": self._last_error,
            "interval_seconds": self._interval,
        }

    async def start(self) -> None:
        logger.info(
            "Starting Catalog Sync Worker: interval=%ds", self._interval,
        )
        self._running = True

        # Initial sync on startup
        await self._run_sync()

        while self._running:
            await asyncio.sleep(self._interval)
            if not self._running:
                break
            await self._run_sync()

    async def stop(self) -> None:
        logger.info("Stopping Catalog Sync Worker...")
        self._running = False

    async def _run_sync(self) -> None:
        from ..services.catalog_sync_service import CatalogSyncService

        try:
            session_factory = _get_session_factory()
            async with session_factory() as session:
                svc = CatalogSyncService(session, git_service)
                await svc.sync_all()

            self._last_run = datetime.now(UTC)
            self._last_error = None
            logger.info("Periodic catalog sync completed")
        except Exception as exc:
            self._last_error = str(exc)
            logger.error("Periodic catalog sync failed: %s", exc, exc_info=True)


# Singleton
catalog_sync_worker = CatalogSyncWorker()
