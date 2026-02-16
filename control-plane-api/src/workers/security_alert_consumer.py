"""Kafka consumer for security alerts — persists to security_events table.

CAB-1177: Consumes security alerts from stoa.security.alerts
and stores them in PostgreSQL for DORA 5-year retention.
"""

import asyncio
import json
import logging
import threading
import uuid

from kafka import KafkaConsumer
from kafka.errors import KafkaError
from pydantic import BaseModel, ValidationError
from sqlalchemy import insert

from ..config import settings
from ..database import _get_session_factory
from ..models.security_event import SecurityEvent

logger = logging.getLogger(__name__)

TOPIC = "stoa.security.alerts"
GROUP_ID = "security-alert-consumer"

VALID_SEVERITIES = {"critical", "high", "medium", "low"}


class SecurityAlertPayload(BaseModel):
    id: str
    type: str
    source: str = "unknown"
    tenant_id: str = ""
    payload: dict = {}

    @property
    def severity(self) -> str:
        return self.payload.get("severity", "medium")

    @property
    def details(self) -> dict:
        return self.payload.get("details", {})


class SecurityAlertConsumer:
    """Kafka consumer that sinks security alerts to PostgreSQL."""

    def __init__(self) -> None:
        self._consumer: KafkaConsumer | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        """Start consuming security alerts in a background thread."""
        self._loop = asyncio.get_event_loop()
        self._running = True

        self._thread = threading.Thread(target=self._consume_thread, daemon=True)
        self._thread.start()

        logger.info("SecurityAlertConsumer started, consuming from %s", TOPIC)

    async def stop(self) -> None:
        """Stop the consumer."""
        self._running = False
        if self._consumer:
            self._consumer.close()
        logger.info("SecurityAlertConsumer stopped")

    def _consume_thread(self) -> None:
        """Thread that runs the Kafka consumer."""
        try:
            self._consumer = self._create_consumer()
            if self._consumer is None:
                return

            logger.info("Security alert consumer connected, listening on %s", TOPIC)

            while self._running:
                try:
                    messages = self._consumer.poll(timeout_ms=1000)
                    for _tp, records in messages.items():
                        for message in records:
                            if not self._running:
                                break
                            self._process_message(message)
                except Exception as e:
                    if self._running:
                        logger.error("Error polling security alerts: %s", e, exc_info=True)

        except Exception as e:
            logger.error("Error in security alert consumer thread: %s", e, exc_info=True)
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

            if hasattr(settings, "KAFKA_SASL_USERNAME") and settings.KAFKA_SASL_USERNAME:
                kafka_config.update(
                    {
                        "security_protocol": "SASL_PLAINTEXT",
                        "sasl_mechanism": "SCRAM-SHA-256",
                        "sasl_plain_username": settings.KAFKA_SASL_USERNAME,
                        "sasl_plain_password": settings.KAFKA_SASL_PASSWORD,
                    }
                )

            return KafkaConsumer(TOPIC, **kafka_config)

        except KafkaError as e:
            logger.error("Failed to create security alert consumer: %s", e)
            return None

    def _process_message(self, message) -> None:
        """Process a single security alert message."""
        try:
            data = message.value
            alert = SecurityAlertPayload.model_validate(data)

            severity = alert.severity
            if severity not in VALID_SEVERITIES:
                severity = "medium"

            if self._loop:
                future = asyncio.run_coroutine_threadsafe(self._persist_alert(alert, severity), self._loop)
                future.result(timeout=10)

        except ValidationError as e:
            logger.warning("Invalid security alert format: %s", e.errors())
        except Exception as e:
            logger.error("Failed to process security alert: %s", e, exc_info=True)

    async def _persist_alert(self, alert: SecurityAlertPayload, severity: str) -> None:
        """Insert a security alert into the database."""
        factory = _get_session_factory()
        async with factory() as session:
            stmt = insert(SecurityEvent).values(
                id=uuid.uuid4(),
                event_id=uuid.UUID(alert.id),
                tenant_id=alert.tenant_id,
                event_type=alert.type,
                severity=severity,
                source=alert.source,
                payload=alert.payload,
            )
            await session.execute(stmt)
            await session.commit()

        logger.info(
            "Persisted security alert event_id=%s type=%s severity=%s tenant=%s",
            alert.id,
            alert.type,
            severity,
            alert.tenant_id,
        )


# Singleton instance
security_alert_consumer = SecurityAlertConsumer()
