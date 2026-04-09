"""Git Sync Worker — async Git commits on API CRUD events (CAB-2012).

Consumes api-created/updated/deleted events from stoa.api.lifecycle
and commits changes to stoa-catalog via GitHubService.

Pipeline: Console -> CP API -> Kafka -> GitSyncWorker -> GitHubService -> stoa-catalog

Follows the SyncEngine threading pattern for Kafka consumption
(kafka-python is synchronous) combined with asyncio bridge for async GitHubService calls.
"""

import asyncio
import json
import logging
import threading

from kafka import KafkaConsumer
from kafka.errors import KafkaError

from ..config import settings
from ..services.git_provider import get_git_provider
from ..services.kafka_service import Topics

logger = logging.getLogger(__name__)

CONSUMER_GROUP = "git-sync-worker"
DEFAULT_RETRY_DELAYS = [2, 4, 8]  # Exponential backoff: 2s, 4s, 8s


class GitSyncWorker:
    """Async Git sync worker — commits API CRUD changes to stoa-catalog.

    Uses threading for kafka-python (sync) and asyncio bridge
    for GitHubService (async).
    """

    TOPIC = Topics.API_EVENTS  # stoa.api.lifecycle
    GROUP = CONSUMER_GROUP

    def __init__(self) -> None:
        self._running = False
        self._consumer: KafkaConsumer | None = None
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._github_service = None
        self._git_sync_enabled: bool = settings.GIT_SYNC_ON_WRITE
        self._retry_delays: list[int] = list(DEFAULT_RETRY_DELAYS)

    async def start(self) -> None:
        """Start the Git sync worker."""
        if not self._git_sync_enabled:
            logger.info("Git sync worker disabled (GIT_SYNC_ON_WRITE=false)")
            return

        logger.info("Starting Git Sync Worker...")
        self._loop = asyncio.get_event_loop()
        self._running = True

        # Get the configured git provider (GitHubService when GIT_PROVIDER=github)
        try:
            self._github_service = get_git_provider()
            if not hasattr(self._github_service, "create_api"):
                logger.warning("Git provider does not support write operations, Git sync disabled")
                self._github_service = None
                return
        except Exception as e:
            logger.warning("Failed to initialize git provider for sync worker: %s", e)
            return

        # Start Kafka consumer in a background thread
        self._thread = threading.Thread(target=self._consume_thread, daemon=True)
        self._thread.start()

        logger.info("Git Sync Worker started (topic=%s, group=%s)", self.TOPIC, self.GROUP)

        # Keep the worker alive until stopped
        while self._running:
            await asyncio.sleep(1)

    async def stop(self) -> None:
        """Stop the Git sync worker."""
        logger.info("Stopping Git Sync Worker...")
        self._running = False
        if self._consumer:
            self._consumer.close()
        logger.info("Git Sync Worker stopped")

    # ── Kafka consumer thread ──────────────────────────────────────────

    def _consume_thread(self) -> None:
        """Thread that runs the Kafka consumer for API lifecycle events."""
        try:
            self._consumer = self._create_consumer()
            if self._consumer is None:
                logger.warning("Git Sync Kafka consumer not available")
                return

            logger.info("Git Sync Kafka consumer connected, listening on %s", self.TOPIC)

            while self._running:
                try:
                    messages = self._consumer.poll(timeout_ms=1000)
                    for _topic_partition, records in messages.items():
                        for message in records:
                            if not self._running:
                                break
                            self._dispatch_event(message)
                except Exception as e:
                    if self._running:
                        logger.error("Error polling git sync messages: %s", e, exc_info=True)

        except Exception as e:
            logger.error("Error in git sync consumer thread: %s", e, exc_info=True)
        finally:
            if self._consumer:
                self._consumer.close()

    def _create_consumer(self) -> KafkaConsumer | None:
        """Create Kafka consumer for API lifecycle events."""
        try:
            kafka_config: dict = {
                "bootstrap_servers": settings.KAFKA_BOOTSTRAP_SERVERS.split(","),
                "group_id": self.GROUP,
                "auto_offset_reset": "latest",
                "enable_auto_commit": True,
                "value_deserializer": lambda m: json.loads(m.decode("utf-8")),
            }

            if settings.KAFKA_SASL_USERNAME:
                kafka_config.update(
                    {
                        "security_protocol": "SASL_PLAINTEXT",
                        "sasl_mechanism": "SCRAM-SHA-256",
                        "sasl_plain_username": settings.KAFKA_SASL_USERNAME,
                        "sasl_plain_password": settings.KAFKA_SASL_PASSWORD,
                    }
                )

            return KafkaConsumer(self.TOPIC, **kafka_config)

        except KafkaError as e:
            logger.error("Failed to create Kafka consumer for git sync: %s", e)
            return None

    def _dispatch_event(self, message) -> None:
        """Dispatch Kafka message to async handler via event loop."""
        try:
            if self._loop:
                future = asyncio.run_coroutine_threadsafe(
                    self._handle_event(message.value),
                    self._loop,
                )
                future.add_done_callback(self._event_callback)
        except Exception as e:
            logger.error("Failed to dispatch git sync event: %s", e, exc_info=True)

    @staticmethod
    def _event_callback(future) -> None:
        """Log exceptions from async event handling."""
        try:
            future.result()
        except Exception as e:
            logger.error("Git sync event handling failed: %s", e, exc_info=True)

    # ── Event handling ─────────────────────────────────────────────────

    async def _handle_event(self, event: dict) -> None:
        """Handle a single API lifecycle event with retry logic."""
        if not self._git_sync_enabled:
            logger.debug("Git sync disabled, skipping event %s", event.get("id"))
            return

        if self._github_service is None:
            logger.debug("GitHubService not available, skipping event %s", event.get("id"))
            return

        event_type = event.get("event_type", "")
        tenant_id = event.get("tenant_id", "")
        payload = event.get("payload", {})
        api_name = payload.get("name", "")

        if event_type not in ("api-created", "api-updated", "api-deleted"):
            logger.debug("Ignoring unknown event type: %s", event_type)
            return

        # Retry loop with exponential backoff
        last_error = None
        max_attempts = 1 + len(self._retry_delays)

        for attempt in range(max_attempts):
            try:
                if event_type == "api-created":
                    await self._handle_create(tenant_id, payload)
                elif event_type == "api-updated":
                    await self._handle_update(tenant_id, api_name, payload)
                elif event_type == "api-deleted":
                    await self._handle_delete(tenant_id, api_name)

                logger.info(
                    "Git sync %s: tenant=%s api=%s",
                    event_type,
                    tenant_id,
                    api_name,
                )
                return  # Success

            except ValueError as e:
                # Idempotency: "already exists" or "not found" — not retriable
                logger.info("Git sync %s skipped (idempotent): %s", event_type, e)
                return

            except Exception as e:
                last_error = e
                if attempt < len(self._retry_delays):
                    delay = self._retry_delays[attempt]
                    logger.warning(
                        "Git sync %s failed (attempt %d/%d), retrying in %ds: %s",
                        event_type,
                        attempt + 1,
                        max_attempts,
                        delay,
                        e,
                    )
                    await asyncio.sleep(delay)

        logger.error(
            "Git sync %s failed after %d attempts: tenant=%s api=%s error=%s",
            event_type,
            max_attempts,
            tenant_id,
            api_name,
            last_error,
        )

    async def _handle_create(self, tenant_id: str, payload: dict) -> None:
        """Handle api-created event."""
        await self._github_service.create_api(tenant_id, payload)

    async def _handle_update(self, tenant_id: str, api_name: str, payload: dict) -> None:
        """Handle api-updated event with idempotency check."""
        if hasattr(self._github_service, "is_api_up_to_date") and await self._github_service.is_api_up_to_date(
            tenant_id, api_name, payload
        ):
            logger.debug("Git content identical, skipping update for %s/%s", tenant_id, api_name)
            return

        await self._github_service.update_api(tenant_id, api_name, payload)

    async def _handle_delete(self, tenant_id: str, api_name: str) -> None:
        """Handle api-deleted event."""
        await self._github_service.delete_api(tenant_id, api_name)


# Module-level singleton
git_sync_worker = GitSyncWorker()
