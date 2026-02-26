"""Repository for LLM budget and provider data access (CAB-1491)."""

import logging
import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.llm_budget import LlmBudget, LlmProvider

logger = logging.getLogger(__name__)


class LlmBudgetRepository:
    """Data access layer for llm_providers and llm_budgets tables."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---- Provider CRUD ----

    async def create_provider(self, provider: LlmProvider) -> LlmProvider:
        """Create a new LLM provider configuration."""
        self.session.add(provider)
        await self.session.flush()
        await self.session.refresh(provider)
        return provider

    async def get_provider_by_id(self, provider_id: uuid.UUID) -> LlmProvider | None:
        """Get a provider by ID."""
        result = await self.session.execute(select(LlmProvider).where(LlmProvider.id == provider_id))
        return result.scalar_one_or_none()

    async def list_providers_by_tenant(self, tenant_id: str) -> list[LlmProvider]:
        """List all providers for a tenant."""
        result = await self.session.execute(
            select(LlmProvider).where(LlmProvider.tenant_id == tenant_id).order_by(LlmProvider.provider_name)
        )
        return list(result.scalars().all())

    async def delete_provider(self, provider: LlmProvider) -> None:
        """Delete a provider record."""
        await self.session.delete(provider)
        await self.session.flush()

    # ---- Budget CRUD ----

    async def create_budget(self, budget: LlmBudget) -> LlmBudget:
        """Create a new LLM budget."""
        self.session.add(budget)
        await self.session.flush()
        await self.session.refresh(budget)
        return budget

    async def get_budget_by_tenant(self, tenant_id: str) -> LlmBudget | None:
        """Get the budget for a tenant."""
        result = await self.session.execute(select(LlmBudget).where(LlmBudget.tenant_id == tenant_id))
        return result.scalar_one_or_none()

    async def update_budget(self, budget: LlmBudget) -> LlmBudget:
        """Update a budget record."""
        budget.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(budget)
        return budget

    async def increment_spend(self, tenant_id: str, amount_usd: float) -> None:
        """Atomically increment current_spend_usd (called by metering or service layer)."""
        stmt = (
            update(LlmBudget)
            .where(LlmBudget.tenant_id == tenant_id)
            .values(
                current_spend_usd=LlmBudget.current_spend_usd + amount_usd,
                updated_at=datetime.utcnow(),
            )
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def reset_spend(self, tenant_id: str) -> None:
        """Reset spend to zero for a new billing period."""
        stmt = (
            update(LlmBudget)
            .where(LlmBudget.tenant_id == tenant_id)
            .values(
                current_spend_usd=0,
                updated_at=datetime.utcnow(),
            )
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def count_providers(self, tenant_id: str) -> int:
        """Count providers for a tenant."""
        result = await self.session.execute(
            select(func.count()).select_from(LlmProvider).where(LlmProvider.tenant_id == tenant_id)
        )
        return result.scalar() or 0
