"""Tempo trace proxy — queries Grafana Tempo for distributed traces (CAB-1984).

Maps Tempo TraceQL search results to the existing APITransactionSummary/APITransaction
schemas so the Console Call Flow dashboard can switch from mock data to real traces
without any UI changes.

Implements MonitoringProxy pattern (Adjustment A2): circuit breaker + timeout.
Supports cursor-based pagination (Adjustment A3).
"""

import logging
import time
from datetime import UTC, datetime

import httpx

from ..config import settings
from ..schemas.monitoring import (
    APITransaction,
    APITransactionSummary,
    TransactionSpan,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Circuit breaker (A2) — simple counter-based, process-local
# ---------------------------------------------------------------------------

_CB_THRESHOLD = 5  # consecutive failures before opening
_CB_RESET_SECONDS = 60  # seconds to wait before half-open retry

_cb_failures: int = 0
_cb_open_since: float = 0.0


def _cb_is_open() -> bool:
    """Return True if the circuit breaker is open (Tempo considered down)."""
    if _cb_failures < _CB_THRESHOLD:
        return False
    # Check if enough time elapsed for a half-open retry
    return not (time.monotonic() - _cb_open_since >= _CB_RESET_SECONDS)


def _cb_record_success() -> None:
    global _cb_failures, _cb_open_since
    _cb_failures = 0
    _cb_open_since = 0.0


def _cb_record_failure() -> None:
    global _cb_failures, _cb_open_since
    _cb_failures += 1
    if _cb_failures >= _CB_THRESHOLD:
        _cb_open_since = time.monotonic()


# ---------------------------------------------------------------------------
# Tempo response → schema mapping
# ---------------------------------------------------------------------------


def _ns_to_iso(nanos: int | str) -> str:
    """Convert nanosecond Unix timestamp to ISO 8601 string."""
    ns = int(nanos)
    dt = datetime.fromtimestamp(ns / 1_000_000_000, tz=UTC)
    return dt.isoformat()


def _ns_to_ms(nanos: int | str) -> int:
    """Convert nanosecond duration to milliseconds."""
    return max(int(int(nanos) / 1_000_000), 0)


def _status_from_code(code: int) -> str:
    if code == 504:
        return "timeout"
    if code >= 400:
        return "error"
    return "success"


def _extract_service_name(span: dict) -> str:
    """Extract service.name from span attributes or resource."""
    for attr in span.get("attributes", []):
        if attr.get("key") == "service.name":
            return attr.get("value", {}).get("stringValue", "unknown")
    resource = span.get("resource", {})
    for attr in resource.get("attributes", []):
        if attr.get("key") == "service.name":
            return attr.get("value", {}).get("stringValue", "unknown")
    return "unknown"


def _map_trace_to_summary(trace: dict) -> APITransactionSummary:
    """Map a Tempo search result trace to APITransactionSummary."""
    root = trace.get("rootServiceName", "unknown")
    root_trace_name = trace.get("rootTraceName", "")
    trace_id = trace.get("traceID", "")
    duration_ms = _ns_to_ms(trace.get("durationMs", 0) * 1_000_000)  # durationMs is already ms
    start_time = trace.get("startTimeUnixNano", 0)
    span_count = trace.get("spanSets", [{}])[0].get("matchCount", 0) if trace.get("spanSets") else 0

    # Parse method + path from root trace name (e.g. "GET /v1/apis")
    method = "GET"
    path = root_trace_name
    if " " in root_trace_name:
        parts = root_trace_name.split(" ", 1)
        method = parts[0]
        path = parts[1]

    # Extract status code from spanSet attributes if available
    status_code = 200
    span_sets = trace.get("spanSets", [])
    if span_sets:
        for span_attr in span_sets[0].get("attributes", []):
            if span_attr.get("key") == "http.status_code":
                status_code = int(span_attr.get("value", {}).get("intValue", 200))

    return APITransactionSummary(
        id=trace_id,
        trace_id=trace_id,
        api_name=root,
        method=method,
        path=path,
        status_code=status_code,
        status=_status_from_code(status_code),
        status_text="",
        error_source=None,
        started_at=_ns_to_iso(start_time) if start_time else "",
        total_duration_ms=int(trace.get("durationMs", duration_ms)),
        spans_count=span_count or int(trace.get("spanCount", 1)),
    )


def _map_spans(trace_data: dict) -> tuple[list[TransactionSpan], dict]:
    """Map Tempo trace spans to TransactionSpan list. Returns (spans, root_span_info)."""
    batches = trace_data.get("batches", [])
    raw_spans: list[dict] = []
    for batch in batches:
        resource = batch.get("resource", {})
        for scope_span in batch.get("scopeSpans", batch.get("instrumentationLibrarySpans", [])):
            for span in scope_span.get("spans", []):
                span["_resource"] = resource
                raw_spans.append(span)

    if not raw_spans:
        return [], {}

    # Sort by startTimeUnixNano
    raw_spans.sort(key=lambda s: int(s.get("startTimeUnixNano", 0)))

    root_info: dict = {}
    result_spans: list[TransactionSpan] = []
    first_start = int(raw_spans[0].get("startTimeUnixNano", 0))

    for span in raw_spans:
        span_start = int(span.get("startTimeUnixNano", 0))
        span_end = int(span.get("endTimeUnixNano", span_start))
        duration_ms = max(int((span_end - span_start) / 1_000_000), 0)
        offset_ms = max(int((span_start - first_start) / 1_000_000), 0)

        # Extract service name from resource
        service = "unknown"
        for attr in span.get("_resource", {}).get("attributes", []):
            if attr.get("key") == "service.name":
                service = attr.get("value", {}).get("stringValue", "unknown")
                break

        # Determine span status
        otel_status = span.get("status", {})
        span_status = "error" if otel_status.get("code") == 2 else "success"

        span_name = span.get("name", "unknown")

        # Collect metadata from attributes
        metadata: dict = {}
        for attr in span.get("attributes", []):
            key = attr.get("key", "")
            val = attr.get("value", {})
            if key.startswith("http."):
                # Flatten http attributes
                short_key = key.replace("http.", "")
                metadata[short_key] = val.get("stringValue") or val.get("intValue") or val.get("boolValue")

        result_spans.append(
            TransactionSpan(
                name=span_name,
                service=service,
                start_offset_ms=offset_ms,
                duration_ms=duration_ms,
                status=span_status,
                metadata=metadata,
            )
        )

        # Identify root span (no parentSpanId or empty)
        if not span.get("parentSpanId"):
            root_info = {
                "method": metadata.get("method", "GET"),
                "path": metadata.get("target", metadata.get("url", span_name)),
                "status_code": int(metadata.get("status_code", 200)),
                "service": service,
            }

    return result_spans, root_info


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def search_traces(
    limit: int = 50,
    api_name: str | None = None,
    status: str | None = None,
    time_range_minutes: int = 60,
    cursor: str | None = None,
) -> tuple[list[APITransactionSummary], str | None] | None:
    """Search Tempo for recent traces. Returns (traces, next_cursor) or None on failure.

    Cursor-based pagination (A3): pass the returned cursor as `cursor` to get next page.
    """
    if not settings.TEMPO_ENABLED:
        return None

    if _cb_is_open():
        logger.debug("Tempo circuit breaker is open, skipping")
        return None

    try:
        params: dict[str, str | int] = {
            "limit": limit,
        }

        # Build tags query
        tags: list[str] = ["service.name=stoa-gateway"]
        if api_name:
            tags.append(f'name="{api_name}"')
        if status == "error":
            tags.append("status=error")

        if tags:
            params["tags"] = " && ".join(tags)

        # Time range
        end_ns = int(time.time() * 1_000_000_000)
        start_ns = end_ns - (time_range_minutes * 60 * 1_000_000_000)
        params["start"] = start_ns
        params["end"] = end_ns

        # Cursor for pagination
        if cursor:
            params["start"] = cursor

        async with httpx.AsyncClient(
            base_url=settings.TEMPO_INTERNAL_URL,
            timeout=settings.TEMPO_TIMEOUT_SECONDS,
        ) as client:
            resp = await client.get("/api/search", params=params)
            resp.raise_for_status()

        data = resp.json()
        traces = data.get("traces", [])

        summaries = [_map_trace_to_summary(t) for t in traces]

        # Cursor for next page: use the last trace's start time
        next_cursor = None
        if traces and len(traces) >= limit:
            last_start = traces[-1].get("startTimeUnixNano")
            if last_start:
                next_cursor = str(last_start)

        _cb_record_success()
        return summaries, next_cursor

    except Exception:
        _cb_record_failure()
        logger.warning("Tempo search failed (failures=%d)", _cb_failures, exc_info=True)
        return None


async def get_trace(trace_id: str) -> APITransaction | None:
    """Fetch a single trace from Tempo and map to APITransaction with span waterfall."""
    if not settings.TEMPO_ENABLED:
        return None

    if _cb_is_open():
        logger.debug("Tempo circuit breaker is open, skipping")
        return None

    try:
        async with httpx.AsyncClient(
            base_url=settings.TEMPO_INTERNAL_URL,
            timeout=settings.TEMPO_TIMEOUT_SECONDS,
        ) as client:
            resp = await client.get(f"/api/traces/{trace_id}")
            resp.raise_for_status()

        data = resp.json()
        spans, root_info = _map_spans(data)

        if not spans:
            _cb_record_success()
            return None

        method = root_info.get("method", "GET")
        path = root_info.get("path", "")
        status_code = root_info.get("status_code", 200)
        service = root_info.get("service", "unknown")
        total_ms = spans[-1].start_offset_ms + spans[-1].duration_ms if spans else 0

        _cb_record_success()
        return APITransaction(
            id=trace_id,
            trace_id=trace_id,
            api_name=service,
            method=method,
            path=path,
            status_code=status_code,
            status=_status_from_code(status_code),
            status_text="",
            started_at=spans[0].metadata.get("started_at", "") if spans else "",
            total_duration_ms=total_ms,
            spans=spans,
        )

    except Exception:
        _cb_record_failure()
        logger.warning("Tempo trace fetch failed for %s (failures=%d)", trace_id, _cb_failures, exc_info=True)
        return None
