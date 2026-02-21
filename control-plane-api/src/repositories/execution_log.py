"""Repository for execution log operations (CAB-1318)."""

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.execution_log import ErrorCategory, ExecutionLog, ExecutionStatus


class ExecutionLogRepository:
    """Repository for execution log database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, log_id: str) -> ExecutionLog | None:
        """Get execution log by ID."""
        result = await self.session.execute(select(ExecutionLog).where(ExecutionLog.id == log_id))
        return result.scalar_one_or_none()

    async def list_by_tenant(
        self,
        tenant_id: str,
        status: ExecutionStatus | None = None,
        error_category: ErrorCategory | None = None,
        consumer_id: str | None = None,
        api_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ExecutionLog], int]:
        """List execution logs for a tenant with pagination and filtering."""
        query = select(ExecutionLog).where(ExecutionLog.tenant_id == tenant_id)

        if status:
            query = query.where(ExecutionLog.status == status)
        if error_category:
            query = query.where(ExecutionLog.error_category == error_category)
        if consumer_id:
            query = query.where(ExecutionLog.consumer_id == consumer_id)
        if api_id:
            query = query.where(ExecutionLog.api_id == api_id)

        # Count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        # Paginate
        query = query.order_by(ExecutionLog.started_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        logs = list(result.scalars().all())

        return logs, total

    async def list_by_consumer(
        self,
        consumer_id: str,
        status: ExecutionStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ExecutionLog], int]:
        """List execution logs for a consumer (portal view)."""
        query = select(ExecutionLog).where(ExecutionLog.consumer_id == consumer_id)

        if status:
            query = query.where(ExecutionLog.status == status)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        query = query.order_by(ExecutionLog.started_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        logs = list(result.scalars().all())

        return logs, total

    async def get_taxonomy(
        self,
        tenant_id: str,
        consumer_id: str | None = None,
    ) -> tuple[list[dict], int, int]:
        """Get error taxonomy aggregates.

        Returns (taxonomy_items, total_errors, total_executions).
        """
        # Total executions
        base_filter = [ExecutionLog.tenant_id == tenant_id]
        if consumer_id:
            base_filter.append(ExecutionLog.consumer_id == consumer_id)

        total_query = select(func.count()).where(and_(*base_filter))
        total_result = await self.session.execute(total_query)
        total_executions = total_result.scalar_one()

        # Error taxonomy
        error_filter = [*base_filter, ExecutionLog.error_category.is_not(None)]
        taxonomy_query = (
            select(
                ExecutionLog.error_category,
                func.count().label("count"),
                func.avg(ExecutionLog.duration_ms).label("avg_duration_ms"),
            )
            .where(and_(*error_filter))
            .group_by(ExecutionLog.error_category)
            .order_by(func.count().desc())
        )

        taxonomy_result = await self.session.execute(taxonomy_query)
        rows = taxonomy_result.all()

        total_errors = sum(row.count for row in rows)

        items = []
        for row in rows:
            pct = round((row.count / total_errors) * 100, 1) if total_errors > 0 else 0
            items.append(
                {
                    "category": row.error_category.value if row.error_category else "unknown",
                    "count": row.count,
                    "avg_duration_ms": round(row.avg_duration_ms, 1) if row.avg_duration_ms else None,
                    "percentage": pct,
                }
            )

        return items, total_errors, total_executions
