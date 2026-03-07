"""Repository for proxy backend CRUD operations (CAB-1725)."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.proxy_backend import ProxyBackend


class ProxyBackendRepository:
    """Repository for proxy backend database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, backend: ProxyBackend) -> ProxyBackend:
        """Create a new proxy backend."""
        self.session.add(backend)
        await self.session.flush()
        await self.session.refresh(backend)
        return backend

    async def get_by_id(self, backend_id: UUID) -> ProxyBackend | None:
        """Get proxy backend by ID."""
        result = await self.session.execute(select(ProxyBackend).where(ProxyBackend.id == backend_id))
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> ProxyBackend | None:
        """Get proxy backend by unique name."""
        result = await self.session.execute(select(ProxyBackend).where(ProxyBackend.name == name))
        return result.scalar_one_or_none()

    async def list_all(
        self,
        active_only: bool = False,
    ) -> tuple[list[ProxyBackend], int]:
        """List all proxy backends with optional active filter."""
        query = select(ProxyBackend)

        if active_only:
            query = query.where(ProxyBackend.is_active.is_(True))

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        # Order by name
        query = query.order_by(ProxyBackend.name)

        result = await self.session.execute(query)
        backends = result.scalars().all()

        return list(backends), total

    async def update(self, backend: ProxyBackend) -> ProxyBackend:
        """Update a proxy backend (caller sets fields before calling)."""
        from datetime import datetime

        backend.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(backend)
        return backend

    async def delete(self, backend: ProxyBackend) -> None:
        """Delete a proxy backend (hard delete)."""
        await self.session.delete(backend)
        await self.session.flush()
