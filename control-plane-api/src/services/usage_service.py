"""Usage metering service (CAB-1334 Phase 1)."""

import logging
from collections import defaultdict
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.usage_repository import UsageRepository
from src.schemas.metering import (
    ToolUsage,
    UsageDetailItem,
    UsageDetailResponse,
    UsageSummary,
)

logger = logging.getLogger(__name__)


class UsageMeteringService:
    """Business logic for usage metering queries and recording."""

    def __init__(self, db: AsyncSession):
        self.repo = UsageRepository(db)

    async def get_summary(
        self,
        tenant_id: str,
        period_type: str,
        start: datetime,
        end: datetime,
    ) -> UsageSummary:
        """Aggregate usage records into a summary with per-tool breakdown."""
        records = await self.repo.get_usage_summary(tenant_id, period_type, start, end)

        # Aggregate per tool
        tool_map: dict[str, dict] = defaultdict(
            lambda: {
                "request_count": 0,
                "token_count": 0,
                "error_count": 0,
                "latency_sum": 0.0,
                "latency_records": 0,
            }
        )
        total_requests = 0
        total_tokens = 0
        total_errors = 0
        latency_sum = 0.0
        latency_records = 0

        for rec in records:
            t = tool_map[rec.tool_name]
            t["request_count"] += rec.request_count
            t["token_count"] += rec.token_count
            t["error_count"] += rec.error_count
            if rec.avg_latency_ms is not None:
                t["latency_sum"] += rec.avg_latency_ms * rec.request_count
                t["latency_records"] += rec.request_count

            total_requests += rec.request_count
            total_tokens += rec.token_count
            total_errors += rec.error_count
            if rec.avg_latency_ms is not None:
                latency_sum += rec.avg_latency_ms * rec.request_count
                latency_records += rec.request_count

        tools = []
        for tool_name, data in sorted(tool_map.items()):
            avg_lat = (
                data["latency_sum"] / data["latency_records"]
                if data["latency_records"] > 0
                else None
            )
            tools.append(
                ToolUsage(
                    tool_name=tool_name,
                    request_count=data["request_count"],
                    token_count=data["token_count"],
                    error_count=data["error_count"],
                    avg_latency_ms=round(avg_lat, 2) if avg_lat is not None else None,
                )
            )

        overall_avg = latency_sum / latency_records if latency_records > 0 else None

        return UsageSummary(
            tenant_id=tenant_id or "(all)",
            period_type=period_type,
            period_start=start,
            period_end=end,
            total_requests=total_requests,
            total_tokens=total_tokens,
            total_errors=total_errors,
            avg_latency_ms=round(overall_avg, 2) if overall_avg is not None else None,
            tools=tools,
        )

    async def get_details(
        self,
        tenant_id: str,
        period_type: str,
        start: datetime,
        end: datetime,
        tool_name: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> UsageDetailResponse:
        """Fetch paginated usage detail records."""
        records, total = await self.repo.get_usage_details(
            tenant_id=tenant_id,
            period_type=period_type,
            start=start,
            end=end,
            tool_name=tool_name,
            limit=limit,
            offset=offset,
        )

        items = [
            UsageDetailItem(
                period_start=rec.period_start,
                period_end=rec.period_end,
                request_count=rec.request_count,
                token_count=rec.token_count,
                error_count=rec.error_count,
                avg_latency_ms=rec.avg_latency_ms,
            )
            for rec in records
        ]

        return UsageDetailResponse(
            tenant_id=tenant_id or "(all)",
            tool_name=tool_name,
            period_type=period_type,
            items=items,
            total=total,
        )

    async def record_usage(
        self,
        tenant_id: str,
        tool_name: str,
        period_start: datetime,
        period_end: datetime,
        period_type: str,
        request_count: int = 0,
        token_count: int = 0,
        error_count: int = 0,
        avg_latency_ms: float | None = None,
    ) -> None:
        """Record (upsert) a usage entry — called by Kafka consumer or batch job."""
        await self.repo.upsert_usage_record(
            tenant_id=tenant_id,
            tool_name=tool_name,
            period_start=period_start,
            period_end=period_end,
            period_type=period_type,
            request_count=request_count,
            token_count=token_count,
            error_count=error_count,
            avg_latency_ms=avg_latency_ms,
        )
