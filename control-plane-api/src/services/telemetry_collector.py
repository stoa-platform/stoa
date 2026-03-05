"""Telemetry Collector Service — normalizes and routes gateway telemetry.

Sits between telemetry sources (pull worker, push webhook) and the
LogWriter. Normalizes entries to the common schema before writing.

See CAB-1682 for architectural context.
"""

import logging
from datetime import UTC, datetime

from prometheus_client import Counter

from ..opensearch.log_writer import log_writer

logger = logging.getLogger("stoa.telemetry.collector")

TELEMETRY_INGEST = Counter(
    "stoa_telemetry_ingest_total",
    "Total telemetry entries ingested",
    ["source"],
)

# Common schema fields
_REQUIRED_FIELDS = {"timestamp", "gateway_type", "method", "path", "status"}
_OPTIONAL_FIELDS = {
    "gateway_id",
    "tenant_id",
    "latency_ms",
    "request_id",
    "trace_id",
    "user_agent",
    "source_ip",
}
_ALL_FIELDS = _REQUIRED_FIELDS | _OPTIONAL_FIELDS


class TelemetryCollector:
    """Normalizes and buffers telemetry entries for bulk writing."""

    async def ingest(self, entries: list[dict], source: str = "push") -> bool:
        """Ingest a batch of telemetry entries.

        Args:
            entries: Raw log entries from a gateway adapter or webhook.
            source: Origin identifier ("push", "pull", gateway type).

        Returns:
            True if accepted, False if backpressure limit reached.
        """
        normalized = [self._normalize(entry) for entry in entries]
        TELEMETRY_INGEST.labels(source=source).inc(len(normalized))
        return await log_writer.add(normalized)

    @staticmethod
    def _normalize(entry: dict) -> dict:
        """Normalize a raw log entry to the common telemetry schema."""
        now = datetime.now(UTC)

        ts = entry.get("timestamp")
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts)
            except (ValueError, TypeError):
                ts = now
        elif not isinstance(ts, datetime):
            ts = now

        return {
            "timestamp": ts.isoformat(),
            "gateway_type": entry.get("gateway_type", "unknown"),
            "gateway_id": entry.get("gateway_id"),
            "tenant_id": entry.get("tenant_id", "platform"),
            "method": entry.get("method", "UNKNOWN"),
            "path": entry.get("path", "/"),
            "status": int(entry.get("status", 0)),
            "latency_ms": float(entry.get("latency_ms", 0)),
            "request_id": entry.get("request_id"),
            "trace_id": entry.get("trace_id"),
            "user_agent": entry.get("user_agent"),
            "source_ip": entry.get("source_ip"),
        }


# Global instance
telemetry_collector = TelemetryCollector()
