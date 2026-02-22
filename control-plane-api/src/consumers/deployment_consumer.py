"""Kafka consumer for deployment lifecycle events (CAB-1413).

Subscribes to stoa.deployment.events and fans out to Slack via
the notification service. Uses the same thread-pool pattern as
ErrorSnapshotConsumer to avoid blocking the asyncio event loop.

Topic:   stoa.deployment.events
Group:   deployment-notification-consumer
Events:  deployment.started | deployment.completed |
         deployment.failed  | deployment.rolledback
"""

import asyncio
import json
import logging
import threading

from kafka import KafkaConsumer
from kafka.errors import KafkaError

from ..config import settings
from ..notifications.deployment_notifier import notify_deployment_event

logger = logging.getLogger(__name__)

TOPIC = "stoa.deployment.events"
GROUP_ID = "deployment-notification-consumer"


class DeploymentConsumer:
    """Kafka consumer that fans deployment events out to Slack.

    Uses kafka-python in a background thread to avoid blocking the
    asyncio event loop. Async work (Slack HTTP call) is dispatched
    back via run_coroutine_threadsafe.
    """

    def __init__(self) -> None:
        self._consumer: KafkaConsumer | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        self._loop = asyncio.get_event_loop()
        self._running = True
        self._thread = threading.Thread(target=self._consume_thread, daemon=True)
        self._thread.start()
        logger.info("DeploymentConsumer started, consuming from %s", TOPIC)

    async def stop(self) -> None:
        self._running = False
        if self._consumer:
            self._consumer.close()
        logger.info("DeploymentConsumer stopped")

    # ------------------------------------------------------------------
    # Thread internals
    # ------------------------------------------------------------------

    def _consume_thread(self) -> None:
        try:
            self._consumer = self._create_consumer()
            if self._consumer is None:
                return
            logger.info("Kafka deployment consumer connected, listening on %s", TOPIC)
            while self._running:
                try:
                    messages = self._consumer.poll(timeout_ms=1000)
                    for _tp, records in messages.items():
                        for msg in records:
                            if not self._running:
                                break
                            self._handle(msg)
                except Exception as exc:
                    if self._running:
                        logger.error("Error polling deployment events: %s", exc, exc_info=True)
        except Exception as exc:
            logger.error("Deployment consumer thread error: %s", exc, exc_info=True)
        finally:
            if self._consumer:
                self._consumer.close()

    def _create_consumer(self) -> KafkaConsumer | None:
        try:
            kafka_cfg: dict = {
                "bootstrap_servers": settings.KAFKA_BOOTSTRAP_SERVERS.split(","),
                "group_id": GROUP_ID,
                "auto_offset_reset": "earliest",
                "enable_auto_commit": True,
                "value_deserializer": lambda m: json.loads(m.decode("utf-8")),
            }
            if getattr(settings, "KAFKA_SASL_USERNAME", None):
                kafka_cfg.update(
                    {
                        "security_protocol": "SASL_PLAINTEXT",
                        "sasl_mechanism": "SCRAM-SHA-256",
                        "sasl_plain_username": settings.KAFKA_SASL_USERNAME,
                        "sasl_plain_password": settings.KAFKA_SASL_PASSWORD,
                    }
                )
            return KafkaConsumer(TOPIC, **kafka_cfg)
        except KafkaError as exc:
            logger.error("Failed to create deployment Kafka consumer: %s", exc)
            return None

    def _handle(self, message) -> None:
        try:
            data: dict = message.value
            event_type: str = data.get("event_type", "")
            payload: dict = data.get("payload", data)  # support both wrapped + flat envelopes

            if not event_type:
                logger.debug("Deployment event missing event_type, skipping")
                return

            if self._loop:
                future = asyncio.run_coroutine_threadsafe(
                    notify_deployment_event(event_type, payload),
                    self._loop,
                )
                future.result(timeout=10)
        except Exception as exc:
            logger.error("Failed to handle deployment event: %s", exc, exc_info=True)


# Singleton
deployment_consumer = DeploymentConsumer()
