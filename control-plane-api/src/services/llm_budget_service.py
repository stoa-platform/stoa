"""Service layer for LLM budget and provider management (CAB-1491)."""

import logging
import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.llm_budget import LlmBudget, LlmProvider
from src.repositories.llm_budget import LlmBudgetRepository
from src.schemas.llm_budget import (
    LlmBudgetCreate,
    LlmBudgetResponse,
    LlmBudgetUpdate,
    LlmProviderCreate,
    LlmProviderResponse,
    SpendSummaryResponse,
)

logger = logging.getLogger(__name__)


class LlmBudgetService:
    """Business logic for LLM budgets and provider configurations."""

    def __init__(self, session: AsyncSession) -> None:
        self.repo = LlmBudgetRepository(session)

    # ---- Provider operations ----

    async def create_provider(
        self,
        tenant_id: str,
        data: LlmProviderCreate,
    ) -> LlmProviderResponse:
        """Create a new LLM provider configuration for a tenant."""
        provider = LlmProvider(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            provider_name=data.provider_name,
            display_name=data.display_name,
            default_model=data.default_model,
            cost_per_input_token=data.cost_per_input_token,
            cost_per_output_token=data.cost_per_output_token,
            status=data.status,
        )
        provider = await self.repo.create_provider(provider)
        logger.info(
            "Created LLM provider: id=%s provider=%s tenant=%s",
            provider.id,
            provider.provider_name,
            tenant_id,
        )
        return LlmProviderResponse.model_validate(provider)

    async def list_providers(self, tenant_id: str) -> list[LlmProviderResponse]:
        """List all LLM providers for a tenant."""
        providers = await self.repo.list_providers_by_tenant(tenant_id)
        return [LlmProviderResponse.model_validate(p) for p in providers]

    async def delete_provider(self, provider_id: uuid.UUID) -> None:
        """Delete an LLM provider configuration."""
        provider = await self.repo.get_provider_by_id(provider_id)
        if not provider:
            raise ValueError(f"Provider not found: {provider_id}")
        await self.repo.delete_provider(provider)
        logger.info("Deleted LLM provider: id=%s", provider_id)

    # ---- Budget operations ----

    async def create_budget(
        self,
        tenant_id: str,
        data: LlmBudgetCreate,
    ) -> LlmBudgetResponse:
        """Create a new LLM budget for a tenant."""
        existing = await self.repo.get_budget_by_tenant(tenant_id)
        if existing:
            raise ValueError(f"Budget already exists for tenant: {tenant_id}")

        budget = LlmBudget(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            monthly_limit_usd=data.monthly_limit_usd,
            current_spend_usd=Decimal("0"),
            alert_threshold_pct=data.alert_threshold_pct,
        )
        budget = await self.repo.create_budget(budget)
        logger.info(
            "Created LLM budget: id=%s tenant=%s limit=%s",
            budget.id,
            tenant_id,
            budget.monthly_limit_usd,
        )
        return LlmBudgetResponse.model_validate(budget)

    async def get_budget(self, tenant_id: str) -> LlmBudgetResponse:
        """Get the LLM budget for a tenant."""
        budget = await self.repo.get_budget_by_tenant(tenant_id)
        if not budget:
            raise ValueError(f"Budget not found for tenant: {tenant_id}")
        return LlmBudgetResponse.model_validate(budget)

    async def update_budget(
        self,
        tenant_id: str,
        data: LlmBudgetUpdate,
    ) -> LlmBudgetResponse:
        """Update an LLM budget configuration."""
        budget = await self.repo.get_budget_by_tenant(tenant_id)
        if not budget:
            raise ValueError(f"Budget not found for tenant: {tenant_id}")

        if data.monthly_limit_usd is not None:
            budget.monthly_limit_usd = data.monthly_limit_usd
        if data.alert_threshold_pct is not None:
            budget.alert_threshold_pct = data.alert_threshold_pct

        budget = await self.repo.update_budget(budget)
        logger.info("Updated LLM budget: tenant=%s", tenant_id)
        return LlmBudgetResponse.model_validate(budget)

    async def record_spend(
        self,
        tenant_id: str,
        amount_usd: float,
        provider_name: str | None = None,
        model: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_seconds: float | None = None,
        cached: int = 0,
    ) -> None:
        """Record LLM spend against a tenant's budget.

        Also writes to llm_spend_events audit table when provider metadata is supplied.
        """
        budget = await self.repo.get_budget_by_tenant(tenant_id)
        if not budget:
            raise ValueError(f"Budget not found for tenant: {tenant_id}")

        await self.repo.increment_spend(tenant_id, amount_usd)

        # Write audit event if provider metadata is available (CAB-1487)
        if provider_name:
            from src.models.llm_budget import LlmSpendEvent

            event = LlmSpendEvent(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                provider_name=provider_name,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=Decimal(str(round(amount_usd, 6))),
                latency_seconds=Decimal(str(round(latency_seconds, 4))) if latency_seconds is not None else None,
                cached=cached,
            )
            self.repo.session.add(event)
            await self.repo.session.flush()

        new_spend = float(budget.current_spend_usd) + amount_usd
        usage_pct = (new_spend / float(budget.monthly_limit_usd)) * 100 if budget.monthly_limit_usd else 0
        if usage_pct >= budget.alert_threshold_pct:
            logger.warning("Tenant %s LLM spend at %.1f%% of budget", tenant_id, usage_pct)

    async def get_spend_summary(self, tenant_id: str) -> SpendSummaryResponse:
        """Get current spend summary for a tenant."""
        budget = await self.repo.get_budget_by_tenant(tenant_id)
        if not budget:
            raise ValueError(f"Budget not found for tenant: {tenant_id}")

        return SpendSummaryResponse(
            tenant_id=tenant_id,
            monthly_limit_usd=budget.monthly_limit_usd,
            current_spend_usd=budget.current_spend_usd,
            remaining_usd=budget.remaining_usd,
            usage_pct=round(budget.usage_pct, 2),
            is_over_budget=budget.is_over_budget,
        )

    async def check_budget(self, tenant_id: str) -> bool:
        """Check if tenant is within budget (used by gateway)."""
        budget = await self.repo.get_budget_by_tenant(tenant_id)
        if not budget:
            return True  # Fail-open: no budget = allow
        return not budget.is_over_budget
