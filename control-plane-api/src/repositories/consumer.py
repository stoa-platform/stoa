"""Repository for consumer CRUD operations (CAB-1121 + CAB-864 + CAB-872)."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.consumer import CertificateStatus, Consumer, ConsumerStatus


def escape_like(value: str) -> str:
    """Escape special SQL LIKE characters: %, _, \\"""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


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

    async def get_by_fingerprint(self, tenant_id: str, fingerprint: str) -> Consumer | None:
        """Get consumer by certificate fingerprint within a tenant (CAB-864).

        Checks both current and previous fingerprint columns.
        """
        result = await self.session.execute(
            select(Consumer).where(
                and_(
                    Consumer.tenant_id == tenant_id,
                    or_(
                        Consumer.certificate_fingerprint == fingerprint,
                        Consumer.certificate_fingerprint_previous == fingerprint,
                    ),
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

        if search and search.strip():
            search_term = escape_like(search.strip())
            search_pattern = f"%{search_term}%"
            query = query.where(
                or_(
                    Consumer.name.ilike(search_pattern, escape="\\"),
                    Consumer.email.ilike(search_pattern, escape="\\"),
                    Consumer.external_id.ilike(search_pattern, escape="\\"),
                    Consumer.company.ilike(search_pattern, escape="\\"),
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

    async def list_expiring(
        self,
        tenant_id: str,
        days: int = 30,
    ) -> list[Consumer]:
        """List consumers with certificates expiring within N days (CAB-872)."""
        cutoff = datetime.now(UTC) + timedelta(days=days)
        query = (
            select(Consumer)
            .where(
                and_(
                    Consumer.tenant_id == tenant_id,
                    Consumer.certificate_not_after.isnot(None),
                    Consumer.certificate_not_after <= cutoff,
                    Consumer.certificate_status == CertificateStatus.ACTIVE,
                )
            )
            .order_by(Consumer.certificate_not_after.asc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def expire_overdue_certificates(self, tenant_id: str) -> int:
        """Set expired status on active certs past not_after (CAB-872).

        Returns:
            Number of certificates marked as expired.
        """
        now = datetime.now(UTC)
        query = select(Consumer).where(
            and_(
                Consumer.tenant_id == tenant_id,
                Consumer.certificate_not_after.isnot(None),
                Consumer.certificate_not_after < now,
                Consumer.certificate_status == CertificateStatus.ACTIVE,
            )
        )
        result = await self.session.execute(query)
        consumers = result.scalars().all()
        count = 0
        for consumer in consumers:
            consumer.certificate_status = CertificateStatus.EXPIRED
            consumer.updated_at = datetime.utcnow()
            count += 1
        if count:
            await self.session.flush()
        return count

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
