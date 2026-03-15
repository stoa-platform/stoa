"""Repository for usage metering data access (CAB-1334 Phase 1)."""

import logging
import uuid
from datetime import datetime

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.usage_summary import UsageSummary

logger = logging.getLogger(__name__)


class UsageMeteringRepository:
    """Data access layer for usage_summaries table."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_usage_summary(
        self,
        tenant_id: str,
        api_id: uuid.UUID | None = None,
        period: str = "daily",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[UsageSummary], int]:
        """Retrieve paginated usage summaries for a tenant, optionally filtered by API."""
        conditions = [UsageSummary.tenant_id == tenant_id, UsageSummary.period == period]
        if api_id is not None:
            conditions.append(UsageSummary.api_id == api_id)

        # Count query
        count_query = select(func.count()).select_from(UsageSummary).where(and_(*conditions))
        count_result = await self.session.execute(count_query)
        total = count_result.scalar() or 0

        # Data query with pagination
        data_query = (
            select(UsageSummary)
            .where(and_(*conditions))
            .order_by(UsageSummary.period_start.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(data_query)
        items = list(result.scalars().all())

        return items, total

    async def get_usage_details(
        self,
        tenant_id: str,
        api_id: uuid.UUID,
        period: str = "daily",
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict | None:
        """Get aggregated usage details for a specific API within a tenant."""
        conditions = [
            UsageSummary.tenant_id == tenant_id,
            UsageSummary.api_id == api_id,
            UsageSummary.period == period,
        ]
        if start_date is not None:
            conditions.append(UsageSummary.period_start >= start_date)
        if end_date is not None:
            conditions.append(UsageSummary.period_start <= end_date)

        query = select(
            func.sum(UsageSummary.request_count).label("total_requests"),
            func.sum(UsageSummary.error_count).label("total_errors"),
            func.max(UsageSummary.p99_latency_ms).label("p99_latency_ms"),
            func.sum(UsageSummary.total_latency_ms).label("total_latency_ms"),
            func.sum(UsageSummary.total_tokens).label("total_tokens"),
            func.max(UsageSummary.period_start).label("period_start"),
        ).where(and_(*conditions))

        result = await self.session.execute(query)
        row = result.one_or_none()

        if row is None or row.total_requests is None:
            return None

        total_requests = int(row.total_requests)
        total_errors = int(row.total_errors)
        total_latency = int(row.total_latency_ms)
        avg_latency = total_latency / total_requests if total_requests > 0 else 0.0
        error_rate = (total_errors / total_requests * 100) if total_requests > 0 else 0.0

        return {
            "api_id": api_id,
            "tenant_id": tenant_id,
            "period": period,
            "period_start": row.period_start,
            "total_requests": total_requests,
            "total_errors": total_errors,
            "error_rate": round(error_rate, 2),
            "avg_latency_ms": round(avg_latency, 2),
            "p99_latency_ms": row.p99_latency_ms,
            "total_tokens": int(row.total_tokens) if row.total_tokens else 0,
        }

    async def upsert_usage(
        self,
        tenant_id: str,
        api_id: uuid.UUID,
        period: str,
        period_start: datetime,
        request_count: int = 0,
        error_count: int = 0,
        total_latency_ms: int = 0,
        p99_latency_ms: int | None = None,
        total_tokens: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_creation_input_tokens: int = 0,
        cache_read_input_tokens: int = 0,
        consumer_id: uuid.UUID | None = None,
    ) -> UsageSummary:
        """Insert or update a usage summary record (upsert on tenant+api+period+period_start)."""
        # Check for existing record
        conditions = [
            UsageSummary.tenant_id == tenant_id,
            UsageSummary.api_id == api_id,
            UsageSummary.period == period,
            UsageSummary.period_start == period_start,
        ]
        if consumer_id is not None:
            conditions.append(UsageSummary.consumer_id == consumer_id)
        else:
            conditions.append(UsageSummary.consumer_id.is_(None))

        query = select(UsageSummary).where(and_(*conditions))
        result = await self.session.execute(query)
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing record — increment counters
            stmt = (
                update(UsageSummary)
                .where(UsageSummary.id == existing.id)
                .values(
                    request_count=UsageSummary.request_count + request_count,
                    error_count=UsageSummary.error_count + error_count,
                    total_latency_ms=UsageSummary.total_latency_ms + total_latency_ms,
                    p99_latency_ms=p99_latency_ms if p99_latency_ms is not None else existing.p99_latency_ms,
                    total_tokens=UsageSummary.total_tokens + total_tokens,
                    input_tokens=UsageSummary.input_tokens + input_tokens,
                    output_tokens=UsageSummary.output_tokens + output_tokens,
                    cache_creation_input_tokens=UsageSummary.cache_creation_input_tokens + cache_creation_input_tokens,
                    cache_read_input_tokens=UsageSummary.cache_read_input_tokens + cache_read_input_tokens,
                    updated_at=datetime.utcnow(),
                )
            )
            await self.session.execute(stmt)
            await self.session.flush()
            # Refresh the object
            await self.session.refresh(existing)
            return existing

        # Create new record
        new_record = UsageSummary(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            api_id=api_id,
            consumer_id=consumer_id,
            period=period,
            period_start=period_start,
            request_count=request_count,
            error_count=error_count,
            total_latency_ms=total_latency_ms,
            p99_latency_ms=p99_latency_ms,
            total_tokens=total_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_input_tokens=cache_creation_input_tokens,
            cache_read_input_tokens=cache_read_input_tokens,
        )
        self.session.add(new_record)
        await self.session.flush()
        return new_record

    async def get_llm_usage_totals(
        self,
        tenant_id: str,
        since: datetime,
    ) -> dict:
        """Get aggregated LLM token usage for a tenant since a given date."""
        conditions = [
            UsageSummary.tenant_id == tenant_id,
            UsageSummary.period_start >= since,
        ]

        query = select(
            func.coalesce(func.sum(UsageSummary.request_count), 0).label("total_requests"),
            func.coalesce(func.sum(UsageSummary.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(UsageSummary.output_tokens), 0).label("output_tokens"),
            func.coalesce(func.sum(UsageSummary.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(UsageSummary.total_latency_ms), 0).label("total_latency_ms"),
            func.coalesce(func.sum(UsageSummary.cache_creation_input_tokens), 0).label("cache_creation_input_tokens"),
            func.coalesce(func.sum(UsageSummary.cache_read_input_tokens), 0).label("cache_read_input_tokens"),
        ).where(and_(*conditions))

        result = await self.session.execute(query)
        row = result.one()
        return {
            "total_requests": int(row.total_requests),
            "input_tokens": int(row.input_tokens),
            "output_tokens": int(row.output_tokens),
            "total_tokens": int(row.total_tokens),
            "total_latency_ms": int(row.total_latency_ms),
            "cache_creation_input_tokens": int(row.cache_creation_input_tokens),
            "cache_read_input_tokens": int(row.cache_read_input_tokens),
        }

    async def get_llm_usage_timeseries(
        self,
        tenant_id: str,
        since: datetime,
    ) -> list[dict]:
        """Get daily LLM token usage for a tenant, grouped by period_start."""
        conditions = [
            UsageSummary.tenant_id == tenant_id,
            UsageSummary.period_start >= since,
        ]

        query = (
            select(
                UsageSummary.period_start,
                func.sum(UsageSummary.input_tokens).label("input_tokens"),
                func.sum(UsageSummary.output_tokens).label("output_tokens"),
                func.sum(UsageSummary.cache_creation_input_tokens).label("cache_creation_input_tokens"),
                func.sum(UsageSummary.cache_read_input_tokens).label("cache_read_input_tokens"),
            )
            .where(and_(*conditions))
            .group_by(UsageSummary.period_start)
            .order_by(UsageSummary.period_start)
        )

        result = await self.session.execute(query)
        rows = result.all()
        return [
            {
                "period_start": row.period_start,
                "input_tokens": int(row.input_tokens or 0),
                "output_tokens": int(row.output_tokens or 0),
                "cache_creation_input_tokens": int(row.cache_creation_input_tokens or 0),
                "cache_read_input_tokens": int(row.cache_read_input_tokens or 0),
            }
            for row in rows
        ]
