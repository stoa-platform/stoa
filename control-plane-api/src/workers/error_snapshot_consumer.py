"""Kafka consumer for error snapshots from webMethods Gateway.

CAB-485: Consumes error snapshots published by webMethods Gateway
and stores them in MinIO using the existing SnapshotService.
"""

import asyncio
import json
import logging
import threading

from kafka import KafkaConsumer
from kafka.errors import KafkaError
from pydantic import ValidationError

from ..config import settings
from ..features.error_snapshots import get_snapshot_service
from ..features.error_snapshots.models import ErrorSnapshot

logger = logging.getLogger(__name__)

TOPIC = "stoa.errors.snapshots"
GROUP_ID = "error-snapshot-consumer"


class ErrorSnapshotConsumer:
    """Kafka consumer for gateway error snapshots.

    Uses kafka-python in a thread pool to avoid blocking the asyncio event loop.
    """

    def __init__(self):
        self._consumer: KafkaConsumer | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        """Start consuming error snapshots from Kafka in a background thread."""
        self._loop = asyncio.get_event_loop()
        self._running = True

        # Start consumer in a thread to not block the event loop
        self._thread = threading.Thread(target=self._consume_thread, daemon=True)
        self._thread.start()

        logger.info(f"ErrorSnapshotConsumer started, consuming from {TOPIC}")

    async def stop(self) -> None:
        """Stop the consumer."""
        self._running = False
        if self._consumer:
            self._consumer.close()
        logger.info("ErrorSnapshotConsumer stopped")

    def _consume_thread(self) -> None:
        """Thread that runs the Kafka consumer."""
        try:
            self._consumer = self._create_consumer()
            if self._consumer is None:
                return

            logger.info(f"Kafka snapshot consumer connected, listening on {TOPIC}")

            while self._running:
                try:
                    # Poll with timeout to check _running flag periodically
                    messages = self._consumer.poll(timeout_ms=1000)
                    for topic_partition, records in messages.items():
                        for message in records:
                            if not self._running:
                                break
                            self._process_message_sync(message)
                except Exception as e:
                    if self._running:  # Only log if not stopping
                        logger.error(f"Error polling messages: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Error in snapshot consumer thread: {e}", exc_info=True)
        finally:
            if self._consumer:
                self._consumer.close()

    def _create_consumer(self) -> KafkaConsumer | None:
        """Create and configure Kafka consumer."""
        try:
            kafka_config = {
                "bootstrap_servers": settings.KAFKA_BOOTSTRAP_SERVERS.split(","),
                "group_id": GROUP_ID,
                "auto_offset_reset": "earliest",
                "enable_auto_commit": True,
                "value_deserializer": lambda m: json.loads(m.decode("utf-8")),
            }

            # Add SASL config if credentials are provided
            if hasattr(settings, 'KAFKA_SASL_USERNAME') and settings.KAFKA_SASL_USERNAME:
                kafka_config.update({
                    "security_protocol": "SASL_PLAINTEXT",
                    "sasl_mechanism": "SCRAM-SHA-256",
                    "sasl_plain_username": settings.KAFKA_SASL_USERNAME,
                    "sasl_plain_password": settings.KAFKA_SASL_PASSWORD,
                })

            return KafkaConsumer(TOPIC, **kafka_config)

        except KafkaError as e:
            logger.error(f"Failed to create Kafka consumer: {e}")
            return None

    def _process_message_sync(self, message) -> None:
        """Process a single snapshot message synchronously."""
        try:
            data = message.value

            # Ensure source is set (default to webmethods-gateway)
            if "source" not in data:
                data["source"] = "webmethods-gateway"

            # Validate and parse the snapshot
            snapshot = ErrorSnapshot.model_validate(data)

            service = get_snapshot_service()

            if service is not None:
                # Run async storage in the main event loop
                if self._loop:
                    future = asyncio.run_coroutine_threadsafe(
                        service.storage.save(snapshot),
                        self._loop
                    )
                    future.result(timeout=10)  # Wait up to 10s

                    logger.info(
                        f"Stored gateway snapshot snapshot_id={snapshot.id} "
                        f"tenant_id={snapshot.tenant_id} status={snapshot.response.status} "
                        f"source={snapshot.source}"
                    )
            else:
                logger.debug(f"Discarded snapshot (service unavailable): {snapshot.id}")

        except ValidationError as e:
            logger.warning(f"Invalid snapshot format: {e.errors()}")
        except Exception as e:
            logger.error(f"Failed to store snapshot: {e}", exc_info=True)


# Singleton instance
error_snapshot_consumer = ErrorSnapshotConsumer()
