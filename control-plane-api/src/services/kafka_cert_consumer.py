"""
Certificate Event Consumer (CAB-866)

Consumes certificate lifecycle events from Kafka and syncs to Keycloak.
Implements exponential backoff retry with Dead Letter Queue.
"""
import asyncio
import json
import logging
from typing import Optional

from kafka import KafkaConsumer
from kafka.errors import KafkaError

from src.config import settings
from src.database import async_session
from src.models.client import Client
from src.services.kafka_service import kafka_service, Topics
from src.services.keycloak_cert_sync_service import keycloak_cert_sync_service

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 1  # 1, 2, 4, 8, 16


class CertificateEventConsumer:
    """Async Kafka consumer for certificate lifecycle events."""

    def __init__(self):
        self._consumer: Optional[KafkaConsumer] = None
        self._running = False
        self._consumer_group = "cert-keycloak-sync"

    async def start(self):
        """Start consuming CERT_EVENTS topic."""
        self._consumer = KafkaConsumer(
            Topics.CERT_EVENTS,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS.split(","),
            group_id=self._consumer_group,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            consumer_timeout_ms=1000,
        )
        self._running = True
        logger.info("Certificate event consumer started", extra={"topic": Topics.CERT_EVENTS})
        await self._consume_loop()

    async def stop(self):
        """Stop the consumer."""
        self._running = False
        if self._consumer:
            self._consumer.close()
            self._consumer = None
        logger.info("Certificate event consumer stopped")

    async def _consume_loop(self):
        while self._running:
            try:
                for message in self._consumer:
                    if not self._running:
                        break
                    await self._process_with_retry(message.value)
                await asyncio.sleep(0.1)
            except KafkaError as e:
                logger.error("Kafka consumer error", extra={"error": str(e)})
                await asyncio.sleep(5)
            except Exception as e:
                logger.error("Unexpected consumer error", extra={"error": str(e)}, exc_info=True)
                await asyncio.sleep(5)

    async def _process_with_retry(self, event: dict):
        """Process event with exponential backoff retry."""
        correlation_id = event.get("correlation_id", "unknown")
        event_type = event.get("type", "unknown")

        for attempt in range(MAX_RETRIES):
            try:
                await self._handle_event(event)
                return
            except Exception as e:
                delay = BACKOFF_BASE_SECONDS * (2 ** attempt)
                logger.warning(
                    "cert_sync_retry",
                    extra={
                        "correlation_id": correlation_id,
                        "event_type": event_type,
                        "attempt": attempt + 1,
                        "max_retries": MAX_RETRIES,
                        "next_delay_s": delay,
                        "error": str(e),
                    },
                )
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(delay)

        # All retries exhausted — send to DLQ
        await self._send_to_dlq(event, correlation_id)

    async def _handle_event(self, event: dict):
        """Route event to appropriate sync handler."""
        event_type = event.get("type")
        payload = event.get("payload", {})
        correlation_id = event.get("correlation_id", "unknown")
        client_id = payload.get("client_id")

        if not client_id:
            logger.warning("cert_event_missing_client_id", extra={"correlation_id": correlation_id, "event": event})
            return

        # Load client from database
        async with async_session() as session:
            client = await session.get(Client, client_id)

        if not client:
            logger.warning("cert_event_client_not_found", extra={"correlation_id": correlation_id, "client_id": client_id})
            return

        if event_type == "CLIENT_CREATED":
            await keycloak_cert_sync_service.sync_client_certificate(client, correlation_id)

        elif event_type == "CERTIFICATE_ROTATED":
            old_fingerprint = payload.get("old_fingerprint", "")
            grace_expires_at = payload.get("grace_expires_at")
            await keycloak_cert_sync_service.rotate_client_certificate(
                client, old_fingerprint, correlation_id,
                grace_expires_at=grace_expires_at,
            )

        elif event_type == "GRACE_PERIOD_EXPIRED":
            from src.services.grace_period_service import grace_period_service
            await grace_period_service.cleanup_expired(str(client.id), correlation_id)

        elif event_type == "CLIENT_REVOKED":
            await keycloak_cert_sync_service.revoke_client_certificate(client, correlation_id)

        else:
            logger.warning("cert_event_unknown_type", extra={"correlation_id": correlation_id, "event_type": event_type})

    async def _send_to_dlq(self, event: dict, correlation_id: str):
        """Publish failed event to Dead Letter Queue."""
        try:
            await kafka_service.publish(
                topic=Topics.CERT_EVENTS_DLQ,
                event_type="cert-sync-failed",
                tenant_id=event.get("tenant_id", "unknown"),
                payload={
                    "original_event": event,
                    "retries_exhausted": MAX_RETRIES,
                },
                key=correlation_id,
            )
            logger.error(
                "cert_sync_dlq",
                extra={"correlation_id": correlation_id, "event_type": event.get("type")},
            )
        except Exception as e:
            logger.critical(
                "cert_sync_dlq_publish_failed",
                extra={"correlation_id": correlation_id, "error": str(e)},
            )


cert_event_consumer = CertificateEventConsumer()
