"""
Admin Logs Service (CAB-2004)
Orchestrates Loki queries + PII masking for admin log viewer.
"""

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
        # Stream selector
        if service == "all":
            jobs = "|".join(SERVICE_JOB_MAP.values())
            selector = f'{{job=~"{jobs}"}}'
        else:
            job = SERVICE_JOB_MAP.get(service, service)
            selector = f'{{job="{job}"}}'

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
        masked = self._pii_masker.mask_dict(raw)
        return AdminLogEntry(
            timestamp=masked.get("timestamp", datetime.now(UTC)),
            service=masked.get("service", masked.get("job", "unknown")),
            level=masked.get("level", "info"),
            message=masked.get("message", masked.get("msg", "")),
            trace_id=masked.get("trace_id", "-"),
            tenant_id=masked.get("tenant_id"),
            request_id=masked.get("request_id", masked.get("id", "")),
            duration_ms=masked.get("duration_ms", masked.get("latency_ms")),
            path=masked.get("path"),
            method=masked.get("method"),
            status_code=masked.get("status_code", masked.get("status")),
            consumer_id=masked.get("consumer_id"),
        )
