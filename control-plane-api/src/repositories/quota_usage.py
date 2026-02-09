"""Repository for quota usage CRUD operations (CAB-1121 Phase 4)."""

import uuid
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.quota_usage import QuotaUsage


class QuotaUsageRepository:
    """Repository for quota usage database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _current_daily_start() -> date:
        """Return today's date as the daily period start."""
        return datetime.now(tz=UTC).date()

    @staticmethod
    def _current_monthly_start() -> date:
        """Return the 1st of the current month as the monthly period start."""
        today = datetime.now(tz=UTC).date()
        return today.replace(day=1)

    async def get_or_create(
        self,
        consumer_id: UUID,
        tenant_id: str,
        subscription_id: UUID | None = None,
    ) -> QuotaUsage:
        """Get existing quota usage for current period, or create a new row.

        Handles period auto-reset: if the existing row's period_start_daily
        is before today, daily counters are reset. Same for monthly.
        """
        daily_start = self._current_daily_start()
        monthly_start = self._current_monthly_start()

        result = await self.session.execute(
            select(QuotaUsage).where(
                and_(
                    QuotaUsage.consumer_id == consumer_id,
                    QuotaUsage.tenant_id == tenant_id,
                    QuotaUsage.period_start_daily == daily_start,
                )
            )
        )
        usage = result.scalar_one_or_none()

        if usage:
            # Monthly period rollover: if the row was from a previous month, reset monthly
            if usage.period_start_monthly < monthly_start:
                usage.request_count_monthly = 0
                usage.bandwidth_bytes_monthly = 0
                usage.period_start_monthly = monthly_start
                usage.last_reset_at = datetime.utcnow()
                await self.session.flush()
                await self.session.refresh(usage)
            return usage

        # No row for today — create a new one (daily counters start at 0).
        # Check if there's a row from a previous day to carry over monthly counters.
        prev_result = await self.session.execute(
            select(QuotaUsage)
            .where(
                and_(
                    QuotaUsage.consumer_id == consumer_id,
                    QuotaUsage.tenant_id == tenant_id,
                )
            )
            .order_by(QuotaUsage.period_start_daily.desc())
            .limit(1)
        )
        prev_usage = prev_result.scalar_one_or_none()

        monthly_count = 0
        monthly_bw = 0
        if prev_usage and prev_usage.period_start_monthly >= monthly_start:
            monthly_count = prev_usage.request_count_monthly
            monthly_bw = prev_usage.bandwidth_bytes_monthly

        usage = QuotaUsage(
            id=uuid.uuid4(),
            consumer_id=consumer_id,
            subscription_id=subscription_id,
            tenant_id=tenant_id,
            request_count_daily=0,
            request_count_monthly=monthly_count,
            bandwidth_bytes_daily=0,
            bandwidth_bytes_monthly=monthly_bw,
            period_start_daily=daily_start,
            period_start_monthly=monthly_start,
        )
        self.session.add(usage)
        await self.session.flush()
        await self.session.refresh(usage)
        return usage

    async def increment(
        self,
        consumer_id: UUID,
        tenant_id: str,
        bandwidth_bytes: int = 0,
    ) -> QuotaUsage:
        """Atomically increment request count (and optionally bandwidth).

        Uses get_or_create to handle period rollovers, then does an
        atomic UPDATE ... SET count = count + 1.
        """
        usage = await self.get_or_create(consumer_id, tenant_id)

        await self.session.execute(
            update(QuotaUsage)
            .where(QuotaUsage.id == usage.id)
            .values(
                request_count_daily=QuotaUsage.request_count_daily + 1,
                request_count_monthly=QuotaUsage.request_count_monthly + 1,
                bandwidth_bytes_daily=QuotaUsage.bandwidth_bytes_daily + bandwidth_bytes,
                bandwidth_bytes_monthly=QuotaUsage.bandwidth_bytes_monthly + bandwidth_bytes,
                updated_at=datetime.utcnow(),
            )
        )
        await self.session.refresh(usage)
        return usage

    async def get_current(self, consumer_id: UUID, tenant_id: str) -> QuotaUsage | None:
        """Get current period usage for a consumer (does not create)."""
        daily_start = self._current_daily_start()

        result = await self.session.execute(
            select(QuotaUsage).where(
                and_(
                    QuotaUsage.consumer_id == consumer_id,
                    QuotaUsage.tenant_id == tenant_id,
                    QuotaUsage.period_start_daily == daily_start,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_by_tenant(
        self,
        tenant_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[QuotaUsage], int]:
        """List quota usage rows for a tenant with pagination."""
        daily_start = self._current_daily_start()

        base_query = select(QuotaUsage).where(
            and_(
                QuotaUsage.tenant_id == tenant_id,
                QuotaUsage.period_start_daily == daily_start,
            )
        )

        # Count total
        count_query = select(func.count()).select_from(base_query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        # Paginate
        query = base_query.order_by(QuotaUsage.request_count_daily.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        items = result.scalars().all()

        return list(items), total

    async def get_stats(self, tenant_id: str) -> dict:
        """Aggregate stats: total requests, top 10 consumers, near-limit list."""
        daily_start = self._current_daily_start()
        monthly_start = self._current_monthly_start()

        # Total daily requests
        daily_result = await self.session.execute(
            select(func.coalesce(func.sum(QuotaUsage.request_count_daily), 0)).where(
                and_(
                    QuotaUsage.tenant_id == tenant_id,
                    QuotaUsage.period_start_daily == daily_start,
                )
            )
        )
        total_daily = daily_result.scalar_one()

        # Total monthly requests
        monthly_result = await self.session.execute(
            select(func.coalesce(func.sum(QuotaUsage.request_count_monthly), 0)).where(
                and_(
                    QuotaUsage.tenant_id == tenant_id,
                    QuotaUsage.period_start_monthly == monthly_start,
                )
            )
        )
        total_monthly = monthly_result.scalar_one()

        # Top 10 consumers by monthly requests
        top_result = await self.session.execute(
            select(QuotaUsage.consumer_id, QuotaUsage.request_count_monthly)
            .where(
                and_(
                    QuotaUsage.tenant_id == tenant_id,
                    QuotaUsage.period_start_daily == daily_start,
                )
            )
            .order_by(QuotaUsage.request_count_monthly.desc())
            .limit(10)
        )
        top_consumers = [
            {"consumer_id": row.consumer_id, "request_count_monthly": row.request_count_monthly}
            for row in top_result.all()
        ]

        return {
            "total_requests_today": total_daily,
            "total_requests_month": total_monthly,
            "top_consumers": top_consumers,
            "near_limit": [],  # Populated by the router with plan data
        }

    async def reset(self, consumer_id: UUID, tenant_id: str) -> QuotaUsage | None:
        """Admin manual reset — set all counters to 0."""
        daily_start = self._current_daily_start()

        result = await self.session.execute(
            select(QuotaUsage).where(
                and_(
                    QuotaUsage.consumer_id == consumer_id,
                    QuotaUsage.tenant_id == tenant_id,
                    QuotaUsage.period_start_daily == daily_start,
                )
            )
        )
        usage = result.scalar_one_or_none()
        if not usage:
            return None

        usage.request_count_daily = 0
        usage.request_count_monthly = 0
        usage.bandwidth_bytes_daily = 0
        usage.bandwidth_bytes_monthly = 0
        usage.last_reset_at = datetime.utcnow()
        usage.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(usage)
        return usage
