"""
Admin Logs Service (CAB-2004)
Orchestrates Loki queries + PII masking for admin log viewer.
"""

import contextlib
import json
import os
import re
import time
from datetime import UTC, datetime, timedelta

from ..core.pii import PIIMasker
from ..schemas.logs import AdminLogEntry, AdminLogQueryResponse
from ..services.loki_client import LokiClient

MAX_TIME_RANGE_HOURS = 24
DEFAULT_LOOKBACK_HOURS = 1

SERVICE_JOB_MAP = {
    "gateway": "stoa-gateway",
    "api": "control-plane-api",
    "auth": "keycloak",
}

# Loki stream label: "job" in K8s (promtail default), "service" in docker-compose
_LOKI_LABEL = os.environ.get("LOKI_SERVICE_LABEL", "job")


class AdminLogsService:
    """Service for admin-level structured log access via Loki."""

    def __init__(self, loki: LokiClient, pii_masker: PIIMasker):
        self._loki = loki
        self._pii_masker = pii_masker

    async def query_logs(
        self,
        *,
        service: str = "all",
        level: str | None = None,
        search: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 50,
        tenant_id: str | None = None,
    ) -> AdminLogQueryResponse:
        t0 = time.monotonic()

        now = datetime.now(UTC)
        end = end_time or now
        start = start_time or (now - timedelta(hours=DEFAULT_LOOKBACK_HOURS))

        # Enforce max time range
        if (end - start) > timedelta(hours=MAX_TIME_RANGE_HOURS):
            raise ValueError(f"Max time range is 24 hours. Requested: {end - start}")

        logql = self._build_logql(
            service=service,
            level=level,
            search=search,
            tenant_id=tenant_id,
        )

        raw = await self._loki.query_range(
            logql=logql,
            start=start,
            end=end,
            limit=limit + 1,
        )

        if raw is None:
            return None  # Signals Loki unavailable to the router

        has_more = len(raw) > limit
        if has_more:
            raw = raw[:limit]

        logs = [self._to_entry(entry) for entry in raw]
        query_time_ms = (time.monotonic() - t0) * 1000

        return AdminLogQueryResponse(
            logs=logs,
            total=len(logs),
            limit=limit,
            has_more=has_more,
            query_time_ms=round(query_time_ms, 2),
        )

    def _build_logql(
        self,
        *,
        service: str,
        level: str | None,
        search: str | None,
        tenant_id: str | None,
    ) -> str:
        # Stream selector (label name varies: "job" in K8s, "service" in docker-compose)
        label = _LOKI_LABEL
        if service == "all":
            values = "|".join(SERVICE_JOB_MAP.values())
            selector = f'{{{label}=~"{values}"}}'
        else:
            value = SERVICE_JOB_MAP.get(service, service)
            selector = f'{{{label}="{value}"}}'

        parts = [selector, "| json"]

        if tenant_id:
            parts.append(f'| tenant_id="{tenant_id}"')

        if level:
            parts.append(f'| level="{level}"')

        if search:
            # Escape regex special chars AND double quotes for LogQL safety
            escaped = re.escape(search).replace('"', '\\"')
            parts.append(f'|~ "{escaped}"')

        return " ".join(parts)

    def _to_entry(self, raw: dict) -> AdminLogEntry:
        # raw = {"timestamp": datetime, "raw": str(json), "labels": dict}
        labels = raw.get("labels", {})
        timestamp = raw.get("timestamp", datetime.now(UTC))

        # Parse the JSON log line
        log_data: dict = {}
        raw_line = raw.get("raw", "")
        if raw_line and raw_line != "<no value>":
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                log_data = json.loads(raw_line)

        # Rust tracing-subscriber nests fields under "fields"
        fields = log_data.get("fields", {})

        # Build a flat dict: prefer parsed fields, fallback to stream labels
        def _get(*keys: str) -> str | None:
            for k in keys:
                if v := fields.get(k):
                    return str(v)
                if v := log_data.get(k):
                    return str(v)
                if v := labels.get(k):
                    return str(v)
            return None

        merged = {
            "timestamp": timestamp,
            "service": _get("service", "job") or "unknown",
            "level": _get("level") or "info",
            "message": _get("message", "event", "msg") or raw_line[:200],
            "trace_id": _get("trace_id") or "-",
            "tenant_id": _get("tenant_id"),
            "request_id": _get("request_id", "id"),
            "duration_ms": _get("duration_ms", "latency_ms"),
            "path": _get("path"),
            "method": _get("method"),
            "status_code": _get("status_code", "status"),
            "consumer_id": _get("consumer_id"),
        }

        masked = self._pii_masker.mask_dict(merged)

        # Parse numeric fields
        duration = masked.get("duration_ms")
        status_code = masked.get("status_code")

        return AdminLogEntry(
            timestamp=masked.get("timestamp", timestamp),
            service=masked.get("service", "unknown"),
            level=masked.get("level", "info"),
            message=masked.get("message", ""),
            trace_id=masked.get("trace_id", "-"),
            tenant_id=masked.get("tenant_id"),
            request_id=masked.get("request_id"),
            duration_ms=float(duration) if duration else None,
            path=masked.get("path"),
            method=masked.get("method"),
            status_code=int(status_code) if status_code and str(status_code).isdigit() else None,
            consumer_id=masked.get("consumer_id"),
        )
