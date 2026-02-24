"""Repository for usage_records table (CAB-1334 Phase 1)."""

import logging
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.usage import UsageRecord

logger = logging.getLogger(__name__)


class UsageRepository:
    """Data-access layer for aggregated usage records."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_usage_summary(
        self,
        tenant_id: str,
        period_type: str,
        start: datetime,
        end: datetime,
    ) -> list[UsageRecord]:
        """Fetch usage records for the summary aggregation."""
        stmt = select(UsageRecord).where(
            UsageRecord.period_type == period_type,
            UsageRecord.period_start >= start,
            UsageRecord.period_start < end,
        )
        if tenant_id:
            stmt = stmt.where(UsageRecord.tenant_id == tenant_id)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_usage_details(
        self,
        tenant_id: str,
        period_type: str,
        start: datetime,
        end: datetime,
        tool_name: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[UsageRecord], int]:
        """Fetch paginated usage detail records."""
        base = select(UsageRecord).where(
            UsageRecord.period_type == period_type,
            UsageRecord.period_start >= start,
            UsageRecord.period_start < end,
        )
        if tenant_id:
            base = base.where(UsageRecord.tenant_id == tenant_id)
        if tool_name:
            base = base.where(UsageRecord.tool_name == tool_name)

        # Total count
        count_stmt = select(func.count()).select_from(base.subquery())
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar() or 0

        # Paginated data
        data_stmt = (
            base.order_by(UsageRecord.period_start.desc()).offset(offset).limit(limit)
        )
        data_result = await self.db.execute(data_stmt)
        records = list(data_result.scalars().all())

        return records, total

    async def upsert_usage_record(
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
        """Insert or update a usage record (PostgreSQL ON CONFLICT)."""
        stmt = pg_insert(UsageRecord).values(
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
        stmt = stmt.on_conflict_do_update(
            constraint="uq_usage_tenant_tool_period",
            set_={
                "request_count": stmt.excluded.request_count,
                "token_count": stmt.excluded.token_count,
                "error_count": stmt.excluded.error_count,
                "avg_latency_ms": stmt.excluded.avg_latency_ms,
                "period_end": stmt.excluded.period_end,
                "updated_at": func.now(),
            },
        )
        await self.db.execute(stmt)
        await self.db.commit()
