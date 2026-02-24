"""Repository for billing and budget data access (CAB-1457)."""

import logging
import uuid
from datetime import datetime

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.department_budget import DepartmentBudget

logger = logging.getLogger(__name__)


class BillingRepository:
    """Data access layer for department_budgets table."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, budget: DepartmentBudget) -> DepartmentBudget:
        """Create a new department budget."""
        self.session.add(budget)
        await self.session.flush()
        await self.session.refresh(budget)
        return budget

    async def get_by_id(self, budget_id: uuid.UUID) -> DepartmentBudget | None:
        """Get a budget by ID."""
        result = await self.session.execute(select(DepartmentBudget).where(DepartmentBudget.id == budget_id))
        return result.scalar_one_or_none()

    async def get_by_department(
        self,
        tenant_id: str,
        department_id: str,
    ) -> DepartmentBudget | None:
        """Get the active budget for a department (most recent period_start)."""
        result = await self.session.execute(
            select(DepartmentBudget)
            .where(
                and_(
                    DepartmentBudget.tenant_id == tenant_id,
                    DepartmentBudget.department_id == department_id,
                )
            )
            .order_by(DepartmentBudget.period_start.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_by_tenant(
        self,
        tenant_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[DepartmentBudget], int]:
        """List budgets for a tenant with pagination."""
        base_condition = DepartmentBudget.tenant_id == tenant_id

        # Count
        count_query = select(func.count()).select_from(DepartmentBudget).where(base_condition)
        count_result = await self.session.execute(count_query)
        total = count_result.scalar() or 0

        # Data
        data_query = (
            select(DepartmentBudget)
            .where(base_condition)
            .order_by(DepartmentBudget.department_id, DepartmentBudget.period_start.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(data_query)
        items = list(result.scalars().all())

        return items, total

    async def update(self, budget: DepartmentBudget) -> DepartmentBudget:
        """Update a budget record."""
        budget.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(budget)
        return budget

    async def increment_spend(
        self,
        budget_id: uuid.UUID,
        amount_microcents: int,
    ) -> None:
        """Atomically increment current_spend_microcents (called by metering consumer)."""
        stmt = (
            update(DepartmentBudget)
            .where(DepartmentBudget.id == budget_id)
            .values(
                current_spend_microcents=DepartmentBudget.current_spend_microcents + amount_microcents,
                updated_at=datetime.utcnow(),
            )
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def reset_period(
        self,
        budget_id: uuid.UUID,
        new_period_start: datetime,
    ) -> None:
        """Reset spend for a new period (called by scheduled job)."""
        stmt = (
            update(DepartmentBudget)
            .where(DepartmentBudget.id == budget_id)
            .values(
                current_spend_microcents=0,
                period_start=new_period_start,
                updated_at=datetime.utcnow(),
            )
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def delete(self, budget: DepartmentBudget) -> None:
        """Delete a budget record."""
        await self.session.delete(budget)
        await self.session.flush()
