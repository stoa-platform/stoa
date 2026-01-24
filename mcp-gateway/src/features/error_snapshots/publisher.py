"""
Kafka Publisher for MCP Error Snapshots

Publishes snapshots to dedicated Kafka topic and persists to database.

Phase 3: Kafka publishing
Phase 4: Database persistence
"""

import asyncio
import json
from datetime import datetime
from functools import lru_cache
from typing import Optional

import structlog

from .config import get_mcp_snapshot_settings
from .models import MCPErrorSnapshot

logger = structlog.get_logger(__name__)

# Global publisher instance
_publisher: Optional["MCPSnapshotPublisher"] = None


class MCPSnapshotPublisher:
    """
    Kafka publisher for MCP error snapshots.

    Uses the existing aiokafka infrastructure from metering.
    """

    def __init__(self):
        self._producer = None
        self._settings = get_mcp_snapshot_settings()
        self._started = False
        self._buffer: list[MCPErrorSnapshot] = []
        self._buffer_lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Initialize Kafka producer"""
        if self._started:
            return

        if not self._settings.kafka_enabled:
            logger.info("mcp_snapshot_publisher_disabled")
            return

        try:
            from aiokafka import AIOKafkaProducer

            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._settings.kafka_bootstrap_servers,
                value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
                compression_type="gzip",
                acks="all",
                enable_idempotence=True,
            )

            await self._producer.start()
            self._started = True

            # Start background flush task
            self._flush_task = asyncio.create_task(self._periodic_flush())

            logger.info(
                "mcp_snapshot_publisher_started",
                topic=self._settings.kafka_topic,
                bootstrap_servers=self._settings.kafka_bootstrap_servers,
            )

        except Exception as e:
            logger.error("mcp_snapshot_publisher_start_failed", error=str(e))
            self._started = False

    async def stop(self) -> None:
        """Shutdown Kafka producer"""
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Flush remaining buffer
        await self._flush_buffer()

        if self._producer:
            await self._producer.stop()
            self._producer = None
            self._started = False

        logger.info("mcp_snapshot_publisher_stopped")

    async def publish(self, snapshot: MCPErrorSnapshot) -> bool:
        """
        Publish a snapshot to Kafka and persist to database.

        Uses buffering for Kafka efficiency, with periodic flush.
        Database persistence is immediate.
        """
        # Phase 4: Persist to database (always, even if Kafka is disabled)
        await self._persist_to_db(snapshot)

        if not self._settings.kafka_enabled:
            return True  # Success if DB persistence worked

        if not self._started:
            await self.start()

        if not self._producer:
            logger.warning("mcp_snapshot_publisher_not_available")
            return True  # Still success if DB worked

        try:
            # Add to buffer
            async with self._buffer_lock:
                self._buffer.append(snapshot)

                # Flush if buffer is full
                if len(self._buffer) >= 10:
                    await self._flush_buffer_locked()

            return True

        except Exception as e:
            logger.warning("mcp_snapshot_publish_failed", error=str(e))
            return True  # Still success if DB worked

    async def _persist_to_db(self, snapshot: MCPErrorSnapshot) -> bool:
        """Persist snapshot to database (Phase 4)."""
        try:
            from ...services.database import get_db_session
            from .repository import ErrorSnapshotRepository

            async with get_db_session() as session:
                repo = ErrorSnapshotRepository(session)
                await repo.save(snapshot)

            logger.debug("snapshot_persisted_to_db", snapshot_id=snapshot.id)
            return True

        except Exception as e:
            # Don't fail if DB is unavailable - log and continue
            logger.warning(
                "snapshot_db_persist_failed",
                snapshot_id=snapshot.id,
                error=str(e),
            )
            return False

    async def publish_immediate(self, snapshot: MCPErrorSnapshot) -> bool:
        """Publish immediately without buffering"""
        if not self._settings.kafka_enabled or not self._producer:
            return False

        try:
            await self._producer.send_and_wait(
                self._settings.kafka_topic,
                value=snapshot.to_kafka_message(),
                key=snapshot.id.encode("utf-8"),
            )
            return True
        except Exception as e:
            logger.warning("mcp_snapshot_immediate_publish_failed", error=str(e))
            return False

    async def _periodic_flush(self) -> None:
        """Periodically flush the buffer"""
        while True:
            try:
                await asyncio.sleep(5)  # Flush every 5 seconds
                await self._flush_buffer()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("mcp_snapshot_periodic_flush_error", error=str(e))

    async def _flush_buffer(self) -> None:
        """Flush buffered snapshots"""
        async with self._buffer_lock:
            await self._flush_buffer_locked()

    async def _flush_buffer_locked(self) -> None:
        """Flush buffer (must hold lock)"""
        if not self._buffer or not self._producer:
            return

        snapshots = self._buffer.copy()
        self._buffer.clear()

        for snapshot in snapshots:
            try:
                await self._producer.send(
                    self._settings.kafka_topic,
                    value=snapshot.to_kafka_message(),
                    key=snapshot.id.encode("utf-8"),
                )
            except Exception as e:
                logger.warning(
                    "mcp_snapshot_send_failed",
                    snapshot_id=snapshot.id,
                    error=str(e),
                )

        # Ensure delivery
        await self._producer.flush()

        if snapshots:
            logger.debug("mcp_snapshots_flushed", count=len(snapshots))


def get_snapshot_publisher() -> MCPSnapshotPublisher:
    """Get the global snapshot publisher"""
    global _publisher
    if _publisher is None:
        _publisher = MCPSnapshotPublisher()
    return _publisher


async def setup_snapshot_publisher() -> MCPSnapshotPublisher:
    """Initialize and start the snapshot publisher"""
    publisher = get_snapshot_publisher()
    await publisher.start()
    return publisher


async def shutdown_snapshot_publisher() -> None:
    """Shutdown the snapshot publisher"""
    global _publisher
    if _publisher:
        await _publisher.stop()
        _publisher = None
