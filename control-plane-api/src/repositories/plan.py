"""Repository for plan CRUD operations (CAB-1121)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.plan import Plan, PlanStatus


class PlanRepository:
    """Repository for plan database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, plan: Plan) -> Plan:
        """Create a new plan."""
        self.session.add(plan)
        await self.session.flush()
        await self.session.refresh(plan)
        return plan

    async def get_by_id(self, plan_id: UUID) -> Plan | None:
        """Get plan by ID."""
        result = await self.session.execute(select(Plan).where(Plan.id == plan_id))
        return result.scalar_one_or_none()

    async def get_by_slug(self, tenant_id: str, slug: str) -> Plan | None:
        """Get plan by tenant + slug (unique pair)."""
        result = await self.session.execute(
            select(Plan).where(
                and_(
                    Plan.tenant_id == tenant_id,
                    Plan.slug == slug,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_by_tenant(
        self,
        tenant_id: str,
        status: PlanStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Plan], int]:
        """List plans for a tenant with pagination."""
        query = select(Plan).where(Plan.tenant_id == tenant_id)

        if status:
            query = query.where(Plan.status == status)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        # Paginate
        query = query.order_by(Plan.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        plans = result.scalars().all()

        return list(plans), total

    async def update(self, plan: Plan) -> Plan:
        """Update a plan (caller sets fields before calling)."""
        plan.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(plan)
        return plan

    async def delete(self, plan: Plan) -> None:
        """Delete a plan (hard delete)."""
        await self.session.delete(plan)
        await self.session.flush()
