# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Kafka producer for metering events.

This module provides an async-compatible Kafka producer for
sending metering events to the STOA event streaming platform.
"""

import asyncio
import json
from typing import Any

import structlog
from aiokafka import AIOKafkaProducer

from ..config import get_settings
from .models import MeteringEvent, MeteringEventBatch

logger = structlog.get_logger(__name__)

# Singleton instance
_producer: "MeteringProducer | None" = None


class MeteringProducer:
    """Async Kafka producer for metering events.

    Supports both single event and batch publishing to Kafka/Redpanda.
    Implements graceful degradation when Kafka is unavailable.

    Attributes:
        topic: Kafka topic for metering events
        bootstrap_servers: Kafka broker addresses
        enabled: Whether metering is enabled
    """

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        topic: str = "stoa.metering.events",
        enabled: bool = True,
        client_id: str = "stoa-mcp-gateway",
    ):
        """Initialize the metering producer.

        Args:
            bootstrap_servers: Comma-separated Kafka broker addresses
            topic: Target topic for metering events
            enabled: Enable/disable metering
            client_id: Kafka client identifier
        """
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self.enabled = enabled
        self.client_id = client_id
        self._producer: AIOKafkaProducer | None = None
        self._started = False
        self._buffer: list[MeteringEvent] = []
        self._buffer_size = 100
        self._flush_interval = 5.0  # seconds
        self._flush_task: asyncio.Task | None = None

    async def startup(self) -> None:
        """Initialize the Kafka producer.

        Starts the producer connection and background flush task.
        If connection fails, metering will be disabled gracefully.
        """
        if not self.enabled:
            logger.info("Metering disabled, skipping producer startup")
            return

        try:
            self._producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                client_id=self.client_id,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                acks="all",  # Wait for all replicas
                enable_idempotence=True,  # Exactly-once semantics
                compression_type="gzip",
                linger_ms=100,  # Batch window
                max_batch_size=32768,  # 32KB batches
            )
            await self._producer.start()
            self._started = True

            # Start background flush task
            self._flush_task = asyncio.create_task(self._periodic_flush())

            logger.info(
                "Metering producer started",
                bootstrap_servers=self.bootstrap_servers,
                topic=self.topic,
            )
        except Exception as e:
            logger.error(
                "Failed to start metering producer, metering disabled",
                error=str(e),
            )
            self._started = False
            self.enabled = False

    async def shutdown(self) -> None:
        """Shutdown the producer gracefully.

        Flushes any buffered events and closes the connection.
        """
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Flush remaining events
        await self._flush_buffer()

        if self._producer:
            await self._producer.stop()
            self._producer = None
            self._started = False
            logger.info("Metering producer stopped")

    async def emit(self, event: MeteringEvent) -> bool:
        """Emit a single metering event.

        Events are buffered and sent in batches for efficiency.
        If the buffer is full, triggers an immediate flush.

        Args:
            event: The metering event to emit

        Returns:
            True if event was accepted, False otherwise.
        """
        if not self.enabled:
            return False

        self._buffer.append(event)

        # Flush if buffer is full
        if len(self._buffer) >= self._buffer_size:
            await self._flush_buffer()

        return True

    async def emit_batch(self, batch: MeteringEventBatch) -> int:
        """Emit a batch of metering events.

        Args:
            batch: Batch of events to emit

        Returns:
            Number of events successfully queued.
        """
        if not self.enabled:
            return 0

        count = 0
        for event in batch.events:
            if await self.emit(event):
                count += 1

        return count

    async def emit_immediate(self, event: MeteringEvent) -> bool:
        """Emit an event immediately without buffering.

        Use for high-priority events that shouldn't be delayed.

        Args:
            event: The metering event to emit

        Returns:
            True if sent successfully, False otherwise.
        """
        if not self.enabled or not self._started:
            return False

        try:
            await self._send_event(event)
            return True
        except Exception as e:
            logger.error(
                "Failed to emit metering event",
                event_id=str(event.event_id),
                error=str(e),
            )
            return False

    async def _send_event(self, event: MeteringEvent) -> None:
        """Send a single event to Kafka.

        Args:
            event: Event to send
        """
        if not self._producer:
            return

        # Use tenant as partition key for locality
        key = event.tenant
        value = event.to_kafka_message()

        await self._producer.send_and_wait(
            self.topic,
            key=key,
            value=value,
        )

    async def _flush_buffer(self) -> None:
        """Flush all buffered events to Kafka."""
        if not self._buffer or not self._started:
            return

        events_to_flush = self._buffer[:]
        self._buffer.clear()

        if not self._producer:
            return

        # Send all events as a batch
        batch = self._producer.create_batch()

        for event in events_to_flush:
            try:
                key = event.tenant.encode("utf-8")
                value = json.dumps(event.to_kafka_message()).encode("utf-8")

                metadata = batch.append(
                    key=key,
                    value=value,
                    timestamp=None,
                )
                if metadata is None:
                    # Batch full, send and create new one
                    await self._producer.send_batch(batch, self.topic, partition=0)
                    batch = self._producer.create_batch()
                    batch.append(key=key, value=value, timestamp=None)
            except Exception as e:
                logger.error(
                    "Failed to add event to batch",
                    event_id=str(event.event_id),
                    error=str(e),
                )

        # Send remaining batch
        if batch.record_count() > 0:
            try:
                await self._producer.send_batch(batch, self.topic, partition=0)
                logger.debug(
                    "Flushed metering events",
                    count=len(events_to_flush),
                )
            except Exception as e:
                logger.error(
                    "Failed to flush metering batch",
                    error=str(e),
                )

    async def _periodic_flush(self) -> None:
        """Background task to periodically flush buffered events."""
        while True:
            try:
                await asyncio.sleep(self._flush_interval)
                await self._flush_buffer()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in periodic flush", error=str(e))


async def get_metering_producer() -> MeteringProducer:
    """Get or create the singleton metering producer.

    Returns:
        The global MeteringProducer instance.
    """
    global _producer

    if _producer is None:
        settings = get_settings()

        # Get Kafka settings from environment
        bootstrap_servers = getattr(settings, "kafka_bootstrap_servers", "localhost:9092")
        metering_topic = getattr(settings, "metering_topic", "stoa.metering.events")
        metering_enabled = getattr(settings, "metering_enabled", True)

        _producer = MeteringProducer(
            bootstrap_servers=bootstrap_servers,
            topic=metering_topic,
            enabled=metering_enabled,
            client_id=settings.otlp_service_name,
        )
        await _producer.startup()

    return _producer


async def shutdown_metering_producer() -> None:
    """Shutdown the singleton metering producer."""
    global _producer

    if _producer:
        await _producer.shutdown()
        _producer = None
