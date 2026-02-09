"""Repository for consumer CRUD operations (CAB-1121)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.consumer import Consumer, ConsumerStatus


class ConsumerRepository:
    """Repository for consumer database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, consumer: Consumer) -> Consumer:
        """Create a new consumer."""
        self.session.add(consumer)
        await self.session.flush()
        await self.session.refresh(consumer)
        return consumer

    async def get_by_id(self, consumer_id: UUID) -> Consumer | None:
        """Get consumer by ID."""
        result = await self.session.execute(select(Consumer).where(Consumer.id == consumer_id))
        return result.scalar_one_or_none()

    async def get_by_external_id(self, tenant_id: str, external_id: str) -> Consumer | None:
        """Get consumer by tenant + external_id (unique pair)."""
        result = await self.session.execute(
            select(Consumer).where(
                and_(
                    Consumer.tenant_id == tenant_id,
                    Consumer.external_id == external_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_by_tenant(
        self,
        tenant_id: str,
        status: ConsumerStatus | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Consumer], int]:
        """List consumers for a tenant with pagination and optional filtering."""
        query = select(Consumer).where(Consumer.tenant_id == tenant_id)

        if status:
            query = query.where(Consumer.status == status)

        if search:
            search_pattern = f"%{search}%"
            query = query.where(
                or_(
                    Consumer.name.ilike(search_pattern),
                    Consumer.email.ilike(search_pattern),
                    Consumer.external_id.ilike(search_pattern),
                    Consumer.company.ilike(search_pattern),
                )
            )

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        # Paginate
        query = query.order_by(Consumer.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        consumers = result.scalars().all()

        return list(consumers), total

    async def update(self, consumer: Consumer) -> Consumer:
        """Update a consumer (caller sets fields before calling)."""
        consumer.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(consumer)
        return consumer

    async def update_status(
        self,
        consumer: Consumer,
        new_status: ConsumerStatus,
    ) -> Consumer:
        """Update consumer status."""
        consumer.status = new_status
        consumer.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(consumer)
        return consumer

    async def delete(self, consumer: Consumer) -> None:
        """Delete a consumer (hard delete)."""
        await self.session.delete(consumer)
        await self.session.flush()

    async def get_stats(self, tenant_id: str | None = None) -> dict:
        """Get consumer statistics."""
        base_query = select(Consumer)
        if tenant_id:
            base_query = base_query.where(Consumer.tenant_id == tenant_id)

        # Total count
        total_result = await self.session.execute(select(func.count()).select_from(base_query.subquery()))
        total = total_result.scalar_one()

        # Count by status
        by_status = {}
        for status in ConsumerStatus:
            status_query = select(func.count()).where(Consumer.status == status)
            if tenant_id:
                status_query = status_query.where(Consumer.tenant_id == tenant_id)
            result = await self.session.execute(status_query)
            by_status[status.value] = result.scalar_one()

        return {
            "total": total,
            "by_status": by_status,
        }
