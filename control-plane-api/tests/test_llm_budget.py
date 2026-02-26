"""Tests for LLM Budget Service and Provider Config (CAB-1491).

Covers: models, schemas, repository, service, router (22 tests).
"""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.llm_budget import LlmBudget, LlmProvider, LlmProviderStatus
from src.schemas.llm_budget import (
    LlmBudgetCreate,
    LlmBudgetUpdate,
    LlmProviderCreate,
    LlmProviderResponse,
    SpendSummaryResponse,
)
from src.services.llm_budget_service import LlmBudgetService

# ---- Fixtures ----


def _make_provider_orm(
    *,
    tenant_id: str = "acme",
    provider_name: str = "openai",
    display_name: str = "OpenAI",
    default_model: str = "gpt-4o",
    cost_per_input_token: Decimal = Decimal("0.000015"),
    cost_per_output_token: Decimal = Decimal("0.000075"),
    status: str = "active",
) -> MagicMock:
    """Create a mock LlmProvider ORM object."""
    mock = MagicMock(spec=LlmProvider)
    mock.id = uuid.uuid4()
    mock.tenant_id = tenant_id
    mock.provider_name = provider_name
    mock.display_name = display_name
    mock.default_model = default_model
    mock.cost_per_input_token = cost_per_input_token
    mock.cost_per_output_token = cost_per_output_token
    mock.status = status
    mock.created_at = "2026-01-01T00:00:00"
    mock.updated_at = "2026-01-01T00:00:00"
    return mock


def _make_budget_orm(
    *,
    tenant_id: str = "acme",
    monthly_limit_usd: Decimal = Decimal("100.00"),
    current_spend_usd: Decimal = Decimal("25.00"),
    alert_threshold_pct: int = 80,
) -> MagicMock:
    """Create a mock LlmBudget ORM object."""
    mock = MagicMock(spec=LlmBudget)
    mock.id = uuid.uuid4()
    mock.tenant_id = tenant_id
    mock.monthly_limit_usd = monthly_limit_usd
    mock.current_spend_usd = current_spend_usd
    mock.alert_threshold_pct = alert_threshold_pct
    mock.usage_pct = float((current_spend_usd / monthly_limit_usd) * 100) if monthly_limit_usd else 0.0
    mock.remaining_usd = max(Decimal("0"), monthly_limit_usd - current_spend_usd)
    mock.is_over_budget = current_spend_usd >= monthly_limit_usd and monthly_limit_usd > 0
    mock.created_at = "2026-01-01T00:00:00"
    mock.updated_at = "2026-01-01T00:00:00"
    return mock


@pytest.fixture()
def service() -> LlmBudgetService:
    """Create a service with mocked session and repo."""
    session = MagicMock()
    svc = LlmBudgetService(session)
    svc.repo = MagicMock()
    return svc


# ---- Model Tests ----


class TestLlmProviderModel:
    """Tests for the LlmProvider ORM model."""

    def test_provider_status_enum(self) -> None:
        """LlmProviderStatus has expected values."""
        assert LlmProviderStatus.ACTIVE == "active"
        assert LlmProviderStatus.INACTIVE == "inactive"
        assert LlmProviderStatus.RATE_LIMITED == "rate_limited"

    def test_provider_repr(self) -> None:
        """LlmProvider repr includes key fields."""
        provider = LlmProvider(
            id=uuid.uuid4(),
            tenant_id="acme",
            provider_name="anthropic",
        )
        result = repr(provider)
        assert "acme" in result
        assert "anthropic" in result


class TestLlmBudgetModel:
    """Tests for the LlmBudget ORM model."""

    def test_usage_pct_normal(self) -> None:
        """usage_pct computes correctly."""
        budget = LlmBudget(
            id=uuid.uuid4(),
            tenant_id="acme",
            monthly_limit_usd=Decimal("100.00"),
            current_spend_usd=Decimal("25.00"),
        )
        assert budget.usage_pct == 25.0

    def test_usage_pct_zero_limit(self) -> None:
        """usage_pct returns 0 when limit is zero."""
        budget = LlmBudget(
            id=uuid.uuid4(),
            tenant_id="acme",
            monthly_limit_usd=Decimal("0"),
            current_spend_usd=Decimal("10.00"),
        )
        assert budget.usage_pct == 0.0

    def test_remaining_usd(self) -> None:
        """remaining_usd returns correct difference."""
        budget = LlmBudget(
            id=uuid.uuid4(),
            tenant_id="acme",
            monthly_limit_usd=Decimal("100.00"),
            current_spend_usd=Decimal("60.00"),
        )
        assert budget.remaining_usd == Decimal("40.00")

    def test_remaining_usd_over_budget(self) -> None:
        """remaining_usd floors at zero when over budget."""
        budget = LlmBudget(
            id=uuid.uuid4(),
            tenant_id="acme",
            monthly_limit_usd=Decimal("50.00"),
            current_spend_usd=Decimal("80.00"),
        )
        assert budget.remaining_usd == Decimal("0")

    def test_is_over_budget_true(self) -> None:
        """is_over_budget returns True when spend >= limit."""
        budget = LlmBudget(
            id=uuid.uuid4(),
            tenant_id="acme",
            monthly_limit_usd=Decimal("50.00"),
            current_spend_usd=Decimal("50.00"),
        )
        assert budget.is_over_budget is True

    def test_is_over_budget_false(self) -> None:
        """is_over_budget returns False when under limit."""
        budget = LlmBudget(
            id=uuid.uuid4(),
            tenant_id="acme",
            monthly_limit_usd=Decimal("100.00"),
            current_spend_usd=Decimal("25.00"),
        )
        assert budget.is_over_budget is False

    def test_budget_repr(self) -> None:
        """LlmBudget repr includes spend and limit."""
        budget = LlmBudget(
            id=uuid.uuid4(),
            tenant_id="acme",
            monthly_limit_usd=Decimal("100.00"),
            current_spend_usd=Decimal("25.00"),
        )
        result = repr(budget)
        assert "acme" in result
        assert "25" in result


# ---- Schema Tests ----


class TestSchemas:
    """Tests for Pydantic schemas."""

    def test_provider_create_validation(self) -> None:
        """LlmProviderCreate validates correctly."""
        data = LlmProviderCreate(provider_name="openai")
        assert data.provider_name == "openai"
        assert data.status == "active"
        assert data.cost_per_input_token == Decimal("0")

    def test_provider_response_from_orm(self) -> None:
        """LlmProviderResponse validates from ORM attributes."""
        mock = _make_provider_orm()
        response = LlmProviderResponse.model_validate(mock)
        assert response.provider_name == "openai"
        assert response.tenant_id == "acme"

    def test_budget_create_defaults(self) -> None:
        """LlmBudgetCreate uses defaults."""
        data = LlmBudgetCreate(monthly_limit_usd=Decimal("200"))
        assert data.alert_threshold_pct == 80

    def test_budget_update_optional(self) -> None:
        """LlmBudgetUpdate allows all None."""
        data = LlmBudgetUpdate()
        assert data.monthly_limit_usd is None
        assert data.alert_threshold_pct is None

    def test_spend_summary_fields(self) -> None:
        """SpendSummaryResponse constructs correctly."""
        summary = SpendSummaryResponse(
            tenant_id="acme",
            monthly_limit_usd=Decimal("100"),
            current_spend_usd=Decimal("25"),
            remaining_usd=Decimal("75"),
            usage_pct=25.0,
            is_over_budget=False,
        )
        assert summary.tenant_id == "acme"
        assert summary.remaining_usd == Decimal("75")


# ---- Service Tests ----


class TestLlmBudgetService:
    """Tests for the LlmBudgetService."""

    @pytest.mark.asyncio
    async def test_create_provider(self, service: LlmBudgetService) -> None:
        """create_provider creates and returns a provider response."""
        mock_orm = _make_provider_orm()
        service.repo.create_provider = AsyncMock(return_value=mock_orm)

        data = LlmProviderCreate(provider_name="openai")
        result = await service.create_provider("acme", data)

        assert result.provider_name == "openai"
        service.repo.create_provider.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_providers(self, service: LlmBudgetService) -> None:
        """list_providers returns list of provider responses."""
        service.repo.list_providers_by_tenant = AsyncMock(
            return_value=[_make_provider_orm(), _make_provider_orm(provider_name="anthropic")]
        )

        result = await service.list_providers("acme")

        assert len(result) == 2
        service.repo.list_providers_by_tenant.assert_awaited_once_with("acme")

    @pytest.mark.asyncio
    async def test_delete_provider_success(self, service: LlmBudgetService) -> None:
        """delete_provider deletes existing provider."""
        mock_orm = _make_provider_orm()
        service.repo.get_provider_by_id = AsyncMock(return_value=mock_orm)
        service.repo.delete_provider = AsyncMock()

        await service.delete_provider(mock_orm.id)

        service.repo.delete_provider.assert_awaited_once_with(mock_orm)

    @pytest.mark.asyncio
    async def test_delete_provider_not_found(self, service: LlmBudgetService) -> None:
        """delete_provider raises ValueError when not found."""
        service.repo.get_provider_by_id = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="Provider not found"):
            await service.delete_provider(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_create_budget_success(self, service: LlmBudgetService) -> None:
        """create_budget creates a new budget."""
        mock_orm = _make_budget_orm()
        service.repo.get_budget_by_tenant = AsyncMock(return_value=None)
        service.repo.create_budget = AsyncMock(return_value=mock_orm)

        data = LlmBudgetCreate(monthly_limit_usd=Decimal("100"))
        result = await service.create_budget("acme", data)

        assert result.tenant_id == "acme"
        service.repo.create_budget.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_budget_duplicate(self, service: LlmBudgetService) -> None:
        """create_budget raises ValueError when budget already exists."""
        service.repo.get_budget_by_tenant = AsyncMock(return_value=_make_budget_orm())

        data = LlmBudgetCreate(monthly_limit_usd=Decimal("100"))
        with pytest.raises(ValueError, match="Budget already exists"):
            await service.create_budget("acme", data)

    @pytest.mark.asyncio
    async def test_get_budget_success(self, service: LlmBudgetService) -> None:
        """get_budget returns budget response."""
        mock_orm = _make_budget_orm()
        service.repo.get_budget_by_tenant = AsyncMock(return_value=mock_orm)

        result = await service.get_budget("acme")

        assert result.tenant_id == "acme"
        assert result.usage_pct == 25.0

    @pytest.mark.asyncio
    async def test_get_budget_not_found(self, service: LlmBudgetService) -> None:
        """get_budget raises ValueError when not found."""
        service.repo.get_budget_by_tenant = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="Budget not found"):
            await service.get_budget("acme")

    @pytest.mark.asyncio
    async def test_update_budget_success(self, service: LlmBudgetService) -> None:
        """update_budget updates and returns budget."""
        mock_orm = _make_budget_orm()
        service.repo.get_budget_by_tenant = AsyncMock(return_value=mock_orm)
        service.repo.update_budget = AsyncMock(return_value=mock_orm)

        data = LlmBudgetUpdate(monthly_limit_usd=Decimal("200"))
        await service.update_budget("acme", data)

        service.repo.update_budget.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_record_spend(self, service: LlmBudgetService) -> None:
        """record_spend calls repo increment_spend."""
        mock_orm = _make_budget_orm()
        service.repo.get_budget_by_tenant = AsyncMock(return_value=mock_orm)
        service.repo.increment_spend = AsyncMock()

        await service.record_spend("acme", 5.50)

        service.repo.increment_spend.assert_awaited_once_with("acme", 5.50)

    @pytest.mark.asyncio
    async def test_record_spend_not_found(self, service: LlmBudgetService) -> None:
        """record_spend raises ValueError when budget not found."""
        service.repo.get_budget_by_tenant = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="Budget not found"):
            await service.record_spend("acme", 5.50)

    @pytest.mark.asyncio
    async def test_get_spend_summary(self, service: LlmBudgetService) -> None:
        """get_spend_summary returns summary with computed fields."""
        mock_orm = _make_budget_orm()
        service.repo.get_budget_by_tenant = AsyncMock(return_value=mock_orm)

        result = await service.get_spend_summary("acme")

        assert result.tenant_id == "acme"
        assert result.remaining_usd == Decimal("75.00")
        assert result.usage_pct == 25.0
        assert result.is_over_budget is False

    @pytest.mark.asyncio
    async def test_check_budget_within(self, service: LlmBudgetService) -> None:
        """check_budget returns True when within budget."""
        mock_orm = _make_budget_orm()
        service.repo.get_budget_by_tenant = AsyncMock(return_value=mock_orm)

        result = await service.check_budget("acme")

        assert result is True

    @pytest.mark.asyncio
    async def test_check_budget_no_budget(self, service: LlmBudgetService) -> None:
        """check_budget returns True (fail-open) when no budget exists."""
        service.repo.get_budget_by_tenant = AsyncMock(return_value=None)

        result = await service.check_budget("acme")

        assert result is True

    @pytest.mark.asyncio
    async def test_check_budget_over(self, service: LlmBudgetService) -> None:
        """check_budget returns False when over budget."""
        mock_orm = _make_budget_orm(current_spend_usd=Decimal("150.00"))
        service.repo.get_budget_by_tenant = AsyncMock(return_value=mock_orm)

        result = await service.check_budget("acme")

        assert result is False
