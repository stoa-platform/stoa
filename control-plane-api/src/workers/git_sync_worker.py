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
import time
from typing import Any

from kafka import KafkaConsumer
from kafka.errors import KafkaError
from prometheus_client import Counter, Histogram

from ..config import settings
from ..services.git_provider import get_git_provider
from ..services.kafka_service import Topics

logger = logging.getLogger(__name__)

# ── Prometheus metrics (CAB-2026) ─────────────────────────────────────

CATALOG_PREFIX = "catalog"

GIT_SYNC_TOTAL = Counter(
    f"{CATALOG_PREFIX}_git_sync_total",
    "Git sync operations (commits to stoa-catalog)",
    ["status", "operation"],
)

GIT_SYNC_DURATION_SECONDS = Histogram(
    f"{CATALOG_PREFIX}_git_sync_duration_seconds",
    "Time between Kafka event received and Git commit confirmed",
    ["operation"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

GIT_SYNC_RETRIES_TOTAL = Counter(
    f"{CATALOG_PREFIX}_git_sync_retries_total",
    "Number of Git sync retry attempts (backoff)",
)

CONSUMER_GROUP = "git-sync-worker"
DEFAULT_RETRY_DELAYS = [2, 4, 8]  # Exponential backoff: 2s, 4s, 8s

# CP-1 H.7: upper bound on how long the consumer thread waits for the
# async handler to complete before declaring failure. 60 s is 2x the
# provider HTTP timeout (DEFAULT_TIMEOUT_S=30 in services/git_executor.py)
# so a handler that waits on a normal timeout can still finish. Past 60 s
# we treat it as failure and do NOT commit — Kafka will redeliver.
HANDLER_RESULT_TIMEOUT_S = 60.0

# CP-1 H.8: substrings that classify a ValueError as an expected
# idempotent outcome (not an error). Anything else is treated as a real
# failure so a functional bug (e.g. batch_commit("unknown action")) is
# not silently counted as success in GIT_SYNC_TOTAL.
_IDEMPOTENT_VALUE_ERROR_SUBSTRINGS = ("already exists", "not found")


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
        self._github_service: Any = None  # GitHubService (write methods not on GitProvider ABC)
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
        """Create Kafka consumer for API lifecycle events.

        CP-1 H.7: enable_auto_commit is now False. Offsets are committed
        synchronously from _dispatch_event AFTER the async handler
        completes successfully. Previously auto-commit could advance the
        offset before the handler ran, losing the event if the worker
        crashed in between.

        Known follow-up (not in P1 scope): handle on_partitions_revoked
        during rebalance. Between future.result() success and
        consumer.commit(), a rebalance can reassign the partition and
        cause the next consumer to re-read the offset — a duplicate
        delivery. Current handlers are idempotent by design (create →
        'already exists' path, treated as success via H.8 discriminator),
        so this is acceptable for P1. Upgrade to a ConsumerRebalance
        Listener when this worker scales past one replica.
        """
        try:
            kafka_config: dict = {
                "bootstrap_servers": settings.KAFKA_BOOTSTRAP_SERVERS.split(","),
                "group_id": self.GROUP,
                "auto_offset_reset": "latest",
                "enable_auto_commit": False,  # CP-1 H.7: manual commit after success
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
        """Dispatch Kafka message to async handler and commit on success.

        CP-1 H.7: this method now blocks the consumer thread on the
        handler future before committing the offset. Under the prior
        fire-and-forget callback pattern combined with
        enable_auto_commit=True the offset could advance before the
        async handler ran, losing events on crash. Serialising per
        message trades throughput for at-least-once durability, which
        is the right tradeoff for a low-volume catalog-write worker.
        """
        if not self._loop or self._consumer is None:
            return
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._handle_event(message.value),
                self._loop,
            )
            try:
                future.result(timeout=HANDLER_RESULT_TIMEOUT_S)
            except TimeoutError:
                # Do NOT commit — Kafka will redeliver. We also cancel
                # the still-running coroutine so the event loop is not
                # poisoned by a growing backlog of stuck tasks.
                future.cancel()
                logger.error(
                    "Git sync handler exceeded %.0fs; offset NOT committed, "
                    "event will be redelivered",
                    HANDLER_RESULT_TIMEOUT_S,
                )
                return
            except Exception as e:
                logger.error("Git sync event handling failed: %s", e, exc_info=True)
                return

            # Handler succeeded — commit the offset so this message is
            # not re-delivered.
            try:
                self._consumer.commit()
            except Exception as e:
                # Commit failure means the message will be redelivered.
                # Handlers are idempotent (create → "already exists"
                # path is classified as success by H.8 discriminator),
                # so this is recoverable.
                logger.error(
                    "Git sync offset commit failed (message will be redelivered): %s",
                    e,
                    exc_info=True,
                )
        except Exception as e:
            logger.error("Failed to dispatch git sync event: %s", e, exc_info=True)

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

        # Map event_type to operation label
        operation = event_type.removeprefix("api-")  # create, update, delete

        # Retry loop with exponential backoff
        last_error = None
        max_attempts = 1 + len(self._retry_delays)
        start_time = time.monotonic()

        for attempt in range(max_attempts):
            try:
                if event_type == "api-created":
                    await self._handle_create(tenant_id, payload)
                elif event_type == "api-updated":
                    await self._handle_update(tenant_id, api_name, payload)
                elif event_type == "api-deleted":
                    await self._handle_delete(tenant_id, api_name)

                # Record success metrics
                duration = time.monotonic() - start_time
                GIT_SYNC_TOTAL.labels(status="success", operation=operation).inc()
                GIT_SYNC_DURATION_SECONDS.labels(operation=operation).observe(duration)

                logger.info(
                    "Git sync %s: tenant=%s api=%s duration=%.2fs",
                    event_type,
                    tenant_id,
                    api_name,
                    duration,
                )
                return  # Success

            except ValueError as e:
                # CP-1 H.8: not every ValueError is an idempotent
                # outcome. Discriminate by message: "already exists" /
                # "not found" are real idempotency signals, anything
                # else (e.g. batch_commit("unknown action") raising
                # ValueError) is a genuine failure. The prior blanket
                # success classification biased GIT_SYNC_TOTAL metrics
                # and hid functional bugs.
                msg = str(e).lower()
                if any(s in msg for s in _IDEMPOTENT_VALUE_ERROR_SUBSTRINGS):
                    GIT_SYNC_TOTAL.labels(status="success", operation=operation).inc()
                    logger.info("Git sync %s skipped (idempotent): %s", event_type, e)
                    return
                # Fall through to the retry path: treat as real error.
                last_error = e
                if attempt < len(self._retry_delays):
                    delay = self._retry_delays[attempt]
                    GIT_SYNC_RETRIES_TOTAL.inc()
                    logger.warning(
                        "Git sync %s ValueError (unknown; attempt %d/%d), retrying in %ds: %s",
                        event_type,
                        attempt + 1,
                        max_attempts,
                        delay,
                        e,
                    )
                    await asyncio.sleep(delay)
                continue

            except Exception as e:
                last_error = e
                if attempt < len(self._retry_delays):
                    delay = self._retry_delays[attempt]
                    GIT_SYNC_RETRIES_TOTAL.inc()
                    logger.warning(
                        "Git sync %s failed (attempt %d/%d), retrying in %ds: %s",
                        event_type,
                        attempt + 1,
                        max_attempts,
                        delay,
                        e,
                    )
                    await asyncio.sleep(delay)

        # All retries exhausted — record error
        duration = time.monotonic() - start_time
        GIT_SYNC_TOTAL.labels(status="error", operation=operation).inc()
        GIT_SYNC_DURATION_SECONDS.labels(operation=operation).observe(duration)

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
