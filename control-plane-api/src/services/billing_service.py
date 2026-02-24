"""Service layer for billing and budget management (CAB-1457)."""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.department_budget import DepartmentBudget
from src.repositories.billing import BillingRepository
from src.schemas.billing import (
    BudgetCheckResponse,
    DepartmentBudgetCreate,
    DepartmentBudgetListResponse,
    DepartmentBudgetResponse,
    DepartmentBudgetUpdate,
)

logger = logging.getLogger(__name__)


class BillingService:
    """Business logic for department budgets and chargeback tracking."""

    def __init__(self, session: AsyncSession) -> None:
        self.repo = BillingRepository(session)

    async def create_budget(
        self,
        tenant_id: str,
        data: DepartmentBudgetCreate,
        created_by: str | None = None,
    ) -> DepartmentBudgetResponse:
        """Create a new department budget."""
        budget = DepartmentBudget(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            department_id=data.department_id,
            department_name=data.department_name,
            period=data.period,
            budget_limit_microcents=data.budget_limit_microcents,
            current_spend_microcents=0,
            period_start=data.period_start,
            warning_threshold_pct=data.warning_threshold_pct,
            critical_threshold_pct=data.critical_threshold_pct,
            enforcement=data.enforcement,
            created_by=created_by,
        )
        budget = await self.repo.create(budget)
        logger.info(
            "Created department budget: id=%s dept=%s tenant=%s limit=%d",
            budget.id,
            budget.department_id,
            tenant_id,
            budget.budget_limit_microcents,
        )
        return DepartmentBudgetResponse.model_validate(budget)

    async def get_budget(self, budget_id: uuid.UUID) -> DepartmentBudgetResponse:
        """Get a budget by ID."""
        budget = await self.repo.get_by_id(budget_id)
        if not budget:
            raise ValueError(f"Budget not found: {budget_id}")
        return DepartmentBudgetResponse.model_validate(budget)

    async def list_budgets(
        self,
        tenant_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> DepartmentBudgetListResponse:
        """List budgets for a tenant."""
        items, total = await self.repo.list_by_tenant(tenant_id, page, page_size)
        return DepartmentBudgetListResponse(
            items=[DepartmentBudgetResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def update_budget(
        self,
        budget_id: uuid.UUID,
        data: DepartmentBudgetUpdate,
    ) -> DepartmentBudgetResponse:
        """Update a budget's configuration."""
        budget = await self.repo.get_by_id(budget_id)
        if not budget:
            raise ValueError(f"Budget not found: {budget_id}")

        if data.department_name is not None:
            budget.department_name = data.department_name
        if data.budget_limit_microcents is not None:
            budget.budget_limit_microcents = data.budget_limit_microcents
        if data.warning_threshold_pct is not None:
            budget.warning_threshold_pct = data.warning_threshold_pct
        if data.critical_threshold_pct is not None:
            budget.critical_threshold_pct = data.critical_threshold_pct
        if data.enforcement is not None:
            budget.enforcement = data.enforcement

        budget = await self.repo.update(budget)
        logger.info("Updated department budget: id=%s dept=%s", budget.id, budget.department_id)
        return DepartmentBudgetResponse.model_validate(budget)

    async def check_budget(self, department_id: str) -> BudgetCheckResponse:
        """Check if a department is over budget (gateway internal endpoint).

        This uses department_id as tenant_id for the simple 1:1 mapping
        used by the gateway (where dept_id = tenant_id).
        Returns fail-open: if no budget record exists, over_budget=False.
        """
        # department_id is used as both tenant_id and department_id
        # because the gateway maps tenant_id → department_id 1:1
        budget = await self.repo.get_by_department(
            tenant_id=department_id,
            department_id=department_id,
        )

        if not budget:
            # Fail-open: no budget configured = no enforcement
            return BudgetCheckResponse(
                over_budget=False,
                enforcement="disabled",
            )

        over = budget.is_over_budget and budget.enforcement == "enabled"

        return BudgetCheckResponse(
            over_budget=over,
            enforcement=budget.enforcement,
            usage_pct=round(budget.usage_pct, 2),
            budget_limit_microcents=budget.budget_limit_microcents,
            current_spend_microcents=budget.current_spend_microcents,
        )

    async def record_spend(
        self,
        tenant_id: str,
        department_id: str,
        amount_microcents: int,
    ) -> None:
        """Record spend against a department's budget (called by metering consumer)."""
        budget = await self.repo.get_by_department(tenant_id, department_id)
        if not budget:
            logger.debug(
                "No budget for dept=%s tenant=%s, skipping spend recording",
                department_id,
                tenant_id,
            )
            return

        await self.repo.increment_spend(budget.id, amount_microcents)

        # Check thresholds for alerting
        new_spend = budget.current_spend_microcents + amount_microcents
        if budget.budget_limit_microcents > 0:
            new_pct = (new_spend / budget.budget_limit_microcents) * 100
            if new_pct >= budget.critical_threshold_pct:
                logger.warning(
                    "Department budget CRITICAL: dept=%s tenant=%s usage=%.1f%%",
                    department_id,
                    tenant_id,
                    new_pct,
                )
            elif new_pct >= budget.warning_threshold_pct:
                logger.warning(
                    "Department budget WARNING: dept=%s tenant=%s usage=%.1f%%",
                    department_id,
                    tenant_id,
                    new_pct,
                )
