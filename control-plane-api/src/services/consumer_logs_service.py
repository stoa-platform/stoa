"""
Consumer Logs Service (CAB-793)
Orchestrates Loki queries + PII masking for self-service logs.
"""
import csv
import io
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

from ..core.pii import PIIMasker
from ..services.loki_client import loki_client as default_loki_client, LokiClient
from ..schemas.logs import (
    LogQueryParams,
    LogEntryResponse,
    LogQueryResponse,
    LogStatus,
)

MAX_TIME_RANGE_HOURS = 24
DEFAULT_LOOKBACK_HOURS = 1


class ConsumerLogsService:
    """Service for consumer self-service log access."""

    def __init__(
        self,
        loki: LokiClient,
        pii_masker: PIIMasker,
    ):
        self._loki = loki
        self._pii_masker = pii_masker

    async def query_logs(
        self,
        user_id: str,
        tenant_id: str,
        params: LogQueryParams,
    ) -> LogQueryResponse:
        t0 = time.monotonic()

        now = datetime.now(timezone.utc)
        end_time = params.end_time or now
        start_time = params.start_time or (now - timedelta(hours=DEFAULT_LOOKBACK_HOURS))

        # Enforce max time range
        if (end_time - start_time) > timedelta(hours=MAX_TIME_RANGE_HOURS):
            start_time = end_time - timedelta(hours=MAX_TIME_RANGE_HOURS)

        status_filter = None
        if params.status and params.status != LogStatus.ALL:
            status_filter = params.status

        raw_logs = await self._loki.get_recent_calls(
            user_id=user_id,
            tenant_id=tenant_id,
            tool_id=params.tool_id,
            status=status_filter,
            from_date=start_time,
            to_date=end_time,
            limit=params.limit + 1,
            search=params.search,
            level=params.level,
        )

        has_more = len(raw_logs) > params.limit
        if has_more:
            raw_logs = raw_logs[: params.limit]

        masked_logs = [
            LogEntryResponse(**self._mask_entry(entry))
            for entry in raw_logs
        ]

        query_time_ms = (time.monotonic() - t0) * 1000

        return LogQueryResponse(
            logs=masked_logs,
            total=len(masked_logs) + params.offset + (1 if has_more else 0),
            limit=params.limit,
            offset=params.offset,
            has_more=has_more,
            query_time_ms=round(query_time_ms, 2),
            time_range_start=start_time,
            time_range_end=end_time,
        )

    async def export_csv(
        self,
        user_id: str,
        tenant_id: str,
        start_time: datetime,
        end_time: datetime,
        tool_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> str:
        if (end_time - start_time) > timedelta(hours=MAX_TIME_RANGE_HOURS):
            start_time = end_time - timedelta(hours=MAX_TIME_RANGE_HOURS)

        raw_logs = await self._loki.get_recent_calls(
            user_id=user_id,
            tenant_id=tenant_id,
            tool_id=tool_id,
            status=status,
            from_date=start_time,
            to_date=end_time,
            limit=10000,
        )

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "timestamp", "request_id", "tool_id", "tool_name",
            "status", "latency_ms", "error_message",
        ])

        for entry in raw_logs:
            masked = self._mask_entry(entry)
            writer.writerow([
                masked.get("timestamp", ""),
                masked.get("id", ""),
                masked.get("tool_id", ""),
                masked.get("tool_name", ""),
                masked.get("status", ""),
                masked.get("latency_ms", ""),
                masked.get("error_message", ""),
            ])

        return output.getvalue()

    def _mask_entry(self, entry: dict) -> dict:
        """Apply PII masking and normalize keys for LogEntryResponse."""
        masked = self._pii_masker.mask_dict(entry)
        # Map LokiClient field names to LogEntryResponse field names
        return {
            "timestamp": masked.get("timestamp"),
            "request_id": masked.get("id", ""),
            "tool_id": masked.get("tool_id"),
            "tool_name": masked.get("tool_name"),
            "status": masked.get("status", "unknown"),
            "duration_ms": masked.get("latency_ms"),
            "error_message": masked.get("error_message"),
        }


# Convenience factory
def get_consumer_logs_service(tenant_id: str) -> ConsumerLogsService:
    pii_masker = PIIMasker.for_tenant(tenant_id)
    return ConsumerLogsService(default_loki_client, pii_masker)
