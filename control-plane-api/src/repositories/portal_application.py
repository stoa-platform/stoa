"""Repository for portal application CRUD (CAB-1306)."""

from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.portal_application import PortalApplication, PortalAppStatus


class PortalApplicationRepository:
    """Async repository for PortalApplication CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, app: PortalApplication) -> PortalApplication:
        """Create a new portal application."""
        self.session.add(app)
        await self.session.flush()
        return app

    async def get_by_id(self, app_id: UUID) -> PortalApplication | None:
        """Get application by primary key."""
        stmt = select(PortalApplication).where(PortalApplication.id == app_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_owner_and_name(self, owner_id: str, name: str) -> PortalApplication | None:
        """Get application by owner + name (unique pair)."""
        stmt = select(PortalApplication).where(
            and_(PortalApplication.owner_id == owner_id, PortalApplication.name == name)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_owner(
        self,
        owner_id: str,
        status: PortalAppStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[PortalApplication], int]:
        """List applications by owner with optional status filter and pagination."""
        conditions = [PortalApplication.owner_id == owner_id]
        if status:
            conditions.append(PortalApplication.status == status)

        # Count
        count_stmt = select(func.count()).select_from(PortalApplication).where(and_(*conditions))
        total = (await self.session.execute(count_stmt)).scalar() or 0

        # Items
        stmt = (
            select(PortalApplication)
            .where(and_(*conditions))
            .order_by(PortalApplication.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def update(self, app: PortalApplication) -> PortalApplication:
        """Update an existing application (caller must set fields)."""
        await self.session.flush()
        return app

    async def delete(self, app: PortalApplication) -> None:
        """Delete an application."""
        await self.session.delete(app)
        await self.session.flush()

    async def delete_all_by_owner(self, owner_id: str) -> int:
        """Delete all applications for an owner (GDPR purge)."""
        stmt = select(PortalApplication).where(PortalApplication.owner_id == owner_id)
        result = await self.session.execute(stmt)
        apps = result.scalars().all()
        for app in apps:
            await self.session.delete(app)
        await self.session.flush()
        return len(list(apps))
