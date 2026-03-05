"""Batched bulk writer for gateway telemetry logs to OpenSearch.

Accumulates log entries in an in-memory buffer and flushes them
to OpenSearch in bulk when either:
- Buffer reaches BATCH_SIZE (500 entries), or
- FLUSH_INTERVAL (5 seconds) elapses since last flush.

Includes a circuit breaker that opens after MAX_FAILURES consecutive
OpenSearch errors (fail-open: logs are dropped, API keeps running).

See CAB-1682 for architectural context.
"""

import asyncio
import contextlib
import logging
import time
from datetime import UTC, datetime

from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger("stoa.telemetry.log_writer")

# --- Prometheus Metrics ---

TELEMETRY_BULK_WRITES = Counter(
    "stoa_telemetry_bulk_writes_total",
    "Total bulk write operations to OpenSearch",
    ["status"],
)

TELEMETRY_BULK_WRITE_DURATION = Histogram(
    "stoa_telemetry_bulk_write_duration_seconds",
    "Duration of bulk write operations",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

TELEMETRY_BUFFER_SIZE = Gauge(
    "stoa_telemetry_buffer_size",
    "Current number of entries in the log writer buffer",
)

TELEMETRY_CIRCUIT_BREAKER = Gauge(
    "stoa_telemetry_circuit_breaker_open",
    "1 if circuit breaker is open (OS unreachable), 0 if closed",
)

# --- Constants ---

BATCH_SIZE = 500
FLUSH_INTERVAL = 5.0  # seconds
MAX_FAILURES = 5
RECOVERY_TIMEOUT = 30.0  # seconds
BACKPRESSURE_LIMIT = 10_000


class LogWriter:
    """Batched, circuit-breaker-protected bulk writer to OpenSearch."""

    def __init__(self, os_client=None):
        self._client = os_client
        self._buffer: list[dict] = []
        self._lock = asyncio.Lock()
        self._consecutive_failures = 0
        self._circuit_open = False
        self._circuit_opened_at: float = 0.0
        self._flush_task: asyncio.Task | None = None
        self._running = False

    def set_client(self, client) -> None:
        self._client = client

    async def start(self) -> None:
        self._running = True
        self._flush_task = asyncio.create_task(self._periodic_flush())
        logger.info("LogWriter started (batch=%d, flush_interval=%.1fs)", BATCH_SIZE, FLUSH_INTERVAL)

    async def stop(self) -> None:
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._flush_task
        await self.flush()
        logger.info("LogWriter stopped")

    def buffer_count(self) -> int:
        return len(self._buffer)

    async def add(self, entries: list[dict]) -> bool:
        """Add log entries to the buffer. Returns False if backpressure limit reached."""
        async with self._lock:
            if len(self._buffer) + len(entries) > BACKPRESSURE_LIMIT:
                logger.warning(
                    "Backpressure limit reached (%d + %d > %d), rejecting entries",
                    len(self._buffer),
                    len(entries),
                    BACKPRESSURE_LIMIT,
                )
                return False

            self._buffer.extend(entries)
            TELEMETRY_BUFFER_SIZE.set(len(self._buffer))

            if len(self._buffer) >= BATCH_SIZE:
                await self._do_flush()

        return True

    async def flush(self) -> None:
        async with self._lock:
            await self._do_flush()

    async def _periodic_flush(self) -> None:
        while self._running:
            await asyncio.sleep(FLUSH_INTERVAL)
            try:
                async with self._lock:
                    if self._buffer:
                        await self._do_flush()
            except Exception as e:
                logger.error("Periodic flush error: %s", e)

    async def _do_flush(self) -> None:
        if not self._buffer:
            return

        if self._circuit_open:
            elapsed = time.monotonic() - self._circuit_opened_at
            if elapsed < RECOVERY_TIMEOUT:
                logger.debug("Circuit breaker open, dropping %d entries", len(self._buffer))
                self._buffer.clear()
                TELEMETRY_BUFFER_SIZE.set(0)
                return
            logger.info("Circuit breaker recovery attempt after %.1fs", elapsed)

        if not self._client:
            logger.warning("No OpenSearch client configured, dropping %d entries", len(self._buffer))
            self._buffer.clear()
            TELEMETRY_BUFFER_SIZE.set(0)
            return

        batch = self._buffer[:BATCH_SIZE]
        start = time.perf_counter()

        try:
            body = self._build_bulk_body(batch)
            result = await self._client.bulk(body=body)

            duration = time.perf_counter() - start
            TELEMETRY_BULK_WRITE_DURATION.observe(duration)

            if result.get("errors"):
                error_count = sum(1 for item in result.get("items", []) if "error" in item.get("index", {}))
                logger.warning("Bulk write partial failure: %d/%d errors", error_count, len(batch))
                TELEMETRY_BULK_WRITES.labels(status="partial_error").inc()
            else:
                TELEMETRY_BULK_WRITES.labels(status="success").inc()

            self._buffer = self._buffer[len(batch) :]
            TELEMETRY_BUFFER_SIZE.set(len(self._buffer))
            self._consecutive_failures = 0

            if self._circuit_open:
                self._circuit_open = False
                TELEMETRY_CIRCUIT_BREAKER.set(0)
                logger.info("Circuit breaker closed — OpenSearch recovered")

        except Exception as e:
            duration = time.perf_counter() - start
            TELEMETRY_BULK_WRITE_DURATION.observe(duration)
            TELEMETRY_BULK_WRITES.labels(status="error").inc()

            self._consecutive_failures += 1
            logger.error(
                "Bulk write failed (%d/%d consecutive): %s",
                self._consecutive_failures,
                MAX_FAILURES,
                e,
            )

            if self._consecutive_failures >= MAX_FAILURES and not self._circuit_open:
                self._circuit_open = True
                self._circuit_opened_at = time.monotonic()
                TELEMETRY_CIRCUIT_BREAKER.set(1)
                logger.error(
                    "Circuit breaker OPEN after %d consecutive failures — " "dropping logs for %.0fs",
                    MAX_FAILURES,
                    RECOVERY_TIMEOUT,
                )
                self._buffer.clear()
                TELEMETRY_BUFFER_SIZE.set(0)

    @staticmethod
    def _build_bulk_body(entries: list[dict]) -> str:
        import json

        lines = []
        for entry in entries:
            ts = entry.get("timestamp", datetime.now(UTC).isoformat())
            gateway_type = entry.get("gateway_type", "unknown")
            tenant_id = entry.get("tenant_id", "platform")

            date_str = ts.strftime("%Y.%m.%d") if isinstance(ts, datetime) else ts[:10].replace("-", ".")

            index_name = f"stoa-gw-{gateway_type}-{tenant_id}-{date_str}"
            lines.append(json.dumps({"index": {"_index": index_name}}))
            lines.append(json.dumps(entry))

        return "\n".join(lines) + "\n"


# Global instance
log_writer = LogWriter()
