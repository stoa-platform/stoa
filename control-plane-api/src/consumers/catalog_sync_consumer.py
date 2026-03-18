"""Kafka consumer for API lifecycle events → catalog cache sync.

Subscribes to stoa.api.lifecycle and triggers a targeted catalog sync
for the affected API whenever an api-created, api-updated, or
api-deleted event is received.  This keeps the api_catalog table (used
by the gateway-deployments dropdown) in sync with GitLab without manual
intervention.

Topic:   stoa.api.lifecycle
Group:   catalog-sync-consumer
Events:  api-created | api-updated | api-deleted
"""

import asyncio
import json
import logging
import threading

from kafka import KafkaConsumer
from kafka.errors import KafkaError

from ..config import settings
from ..database import _get_session_factory
from ..services.git_service import git_service

logger = logging.getLogger(__name__)

TOPIC = "stoa.api.lifecycle"
GROUP_ID = "catalog-sync-consumer"


class CatalogSyncConsumer:
    """Kafka consumer that syncs individual API changes into the catalog cache.

    Runs kafka-python in a background thread to avoid blocking the asyncio
    event loop.  Async DB work is dispatched back via run_coroutine_threadsafe.
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
        logger.info("CatalogSyncConsumer started, consuming from %s", TOPIC)

    async def stop(self) -> None:
        self._running = False
        if self._consumer:
            self._consumer.close()
        logger.info("CatalogSyncConsumer stopped")

    # ------------------------------------------------------------------
    # Thread internals
    # ------------------------------------------------------------------

    def _consume_thread(self) -> None:
        try:
            self._consumer = self._create_consumer()
            if self._consumer is None:
                return
            logger.info("Kafka catalog-sync consumer connected, listening on %s", TOPIC)
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
                        logger.error("Error polling API lifecycle events: %s", exc, exc_info=True)
        except Exception as exc:
            logger.error("Catalog sync consumer thread error: %s", exc, exc_info=True)
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
            logger.error("Failed to create catalog-sync Kafka consumer: %s", exc)
            return None

    def _handle(self, message) -> None:
        try:
            data: dict = message.value
            event_type: str = data.get("event_type", "")
            payload: dict = data.get("payload", data)

            if event_type not in ("api-created", "api-updated", "api-deleted"):
                return

            tenant_id = payload.get("tenant_id") or data.get("tenant_id")
            # For api-deleted the payload is {"api_id": ...}
            api_id = payload.get("name") or payload.get("api_id") or payload.get("id")

            if not tenant_id or not api_id:
                logger.warning(
                    "Catalog sync consumer: missing tenant_id or api_id in %s event",
                    event_type,
                )
                return

            logger.info("Catalog sync consumer: %s → %s/%s", event_type, tenant_id, api_id)

            if self._loop:
                future = asyncio.run_coroutine_threadsafe(
                    self._sync_api(tenant_id, api_id),
                    self._loop,
                )
                future.result(timeout=30)
        except Exception as exc:
            logger.error("Failed to handle API lifecycle event: %s", exc, exc_info=True)

    @staticmethod
    async def _sync_api(tenant_id: str, api_id: str) -> None:
        """Run a single-API catalog sync inside a fresh DB session."""
        from ..services.catalog_sync_service import CatalogSyncService

        session_factory = _get_session_factory()
        async with session_factory() as session:
            try:
                svc = CatalogSyncService(session, git_service)
                await svc.sync_single_api(tenant_id, api_id)
            except Exception as exc:
                logger.error(
                    "Catalog sync failed for %s/%s: %s",
                    tenant_id, api_id, exc, exc_info=True,
                )


# Singleton
catalog_sync_consumer = CatalogSyncConsumer()
