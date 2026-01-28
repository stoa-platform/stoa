# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Cache cleanup background worker — CAB-881.

Runs two periodic jobs:
1. TTL cleanup: every 60 seconds, delete expired entries
2. GDPR hard-delete: every 60 seconds, delete entries older than 24 hours
"""

import asyncio

import structlog

from ..services.database import get_db_session
from .semantic_cache import SemanticCache

logger = structlog.get_logger(__name__)


class CacheCleanupWorker:
    """Background asyncio task for cache cleanup."""

    def __init__(
        self,
        cache: SemanticCache | None = None,
        interval_seconds: int = 60,
        gdpr_max_age_hours: int = 24,
    ) -> None:
        self._cache = cache or SemanticCache()
        self._interval = interval_seconds
        self._gdpr_max_age = gdpr_max_age_hours
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """Start the cleanup loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            "cache_cleanup_started",
            interval=self._interval,
            gdpr_max_age_hours=self._gdpr_max_age,
        )

    async def stop(self) -> None:
        """Stop the cleanup loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("cache_cleanup_stopped")

    async def _loop(self) -> None:
        """Run cleanup on interval."""
        while self._running:
            try:
                await self._run_once()
            except Exception as e:
                logger.error("cache_cleanup_error", error=str(e))
            await asyncio.sleep(self._interval)

    async def _run_once(self) -> None:
        """Execute one cleanup cycle."""
        async with get_db_session() as session:
            expired = await self._cache.cleanup_expired(session)
            gdpr = await self._cache.cleanup_gdpr(session, self._gdpr_max_age)
            if expired > 0 or gdpr > 0:
                logger.info(
                    "cache_cleanup_cycle",
                    expired_deleted=expired,
                    gdpr_deleted=gdpr,
                )


# Singleton instance (started/stopped in main.py lifespan)
cache_cleanup_worker = CacheCleanupWorker()
