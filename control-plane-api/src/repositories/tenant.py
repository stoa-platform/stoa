"""Repository for tenant CRUD operations"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional, List

from src.models.tenant import Tenant, TenantStatus


class TenantRepository:
    """Repository for tenant database operations"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, tenant: Tenant) -> Tenant:
        """Create a new tenant"""
        self.session.add(tenant)
        await self.session.flush()
        await self.session.refresh(tenant)
        return tenant

    async def get_by_id(self, tenant_id: str) -> Optional[Tenant]:
        """Get tenant by ID"""
        result = await self.session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        include_archived: bool = False
    ) -> List[Tenant]:
        """List all tenants (optionally including archived)"""
        query = select(Tenant)

        if not include_archived:
            query = query.where(Tenant.status != TenantStatus.ARCHIVED.value)

        query = query.order_by(Tenant.name)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_for_user(
        self,
        tenant_id: Optional[str] = None,
        is_admin: bool = False
    ) -> List[Tenant]:
        """
        List tenants based on user access.

        - Admin users: see all non-archived tenants
        - Regular users: see only their assigned tenant
        """
        if is_admin:
            return await self.list_all(include_archived=False)

        if tenant_id:
            tenant = await self.get_by_id(tenant_id)
            if tenant and tenant.status != TenantStatus.ARCHIVED.value:
                return [tenant]

        return []

    async def update(self, tenant: Tenant) -> Tenant:
        """Update a tenant"""
        await self.session.flush()
        await self.session.refresh(tenant)
        return tenant

    async def delete(self, tenant: Tenant) -> None:
        """Delete a tenant (use with caution)"""
        await self.session.delete(tenant)
        await self.session.flush()

    async def count(self, include_archived: bool = False) -> int:
        """Count tenants"""
        query = select(func.count()).select_from(Tenant)

        if not include_archived:
            query = query.where(Tenant.status != TenantStatus.ARCHIVED.value)

        result = await self.session.execute(query)
        return result.scalar_one()

    async def get_stats(self) -> dict:
        """Get tenant statistics"""
        # Total count
        total = await self.count(include_archived=True)

        # Count by status
        by_status = {}
        for status in TenantStatus:
            result = await self.session.execute(
                select(func.count()).where(Tenant.status == status.value)
            )
            by_status[status.value] = result.scalar_one()

        return {
            "total": total,
            "by_status": by_status,
            "active": by_status.get(TenantStatus.ACTIVE.value, 0),
        }
