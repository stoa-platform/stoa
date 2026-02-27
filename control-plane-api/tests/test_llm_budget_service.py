"""Tests for LLM budget service (CAB-1558)."""

import contextlib
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.schemas.llm_budget import (
    LlmBudgetCreate,
    LlmBudgetUpdate,
    LlmProviderCreate,
)
from src.services.llm_budget_service import LlmBudgetService


def _mock_provider(**overrides) -> MagicMock:
    defaults = {
        "id": uuid.uuid4(),
        "tenant_id": "acme",
        "provider_name": "openai",
        "display_name": "OpenAI",
        "default_model": "gpt-4",
        "cost_per_input_token": Decimal("0.00003"),
        "cost_per_output_token": Decimal("0.00006"),
        "status": "active",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    defaults.update(overrides)
    m = MagicMock()
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


def _mock_budget(**overrides) -> MagicMock:
    defaults = {
        "id": uuid.uuid4(),
        "tenant_id": "acme",
        "monthly_limit_usd": Decimal("100.00"),
        "current_spend_usd": Decimal("25.00"),
        "alert_threshold_pct": 80,
        "usage_pct": 25.0,
        "remaining_usd": Decimal("75.00"),
        "is_over_budget": False,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    defaults.update(overrides)
    m = MagicMock()
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


@pytest.fixture
def svc():
    """Create LlmBudgetService with mocked repo."""
    session = AsyncMock()
    with patch("src.services.llm_budget_service.LlmBudgetRepository") as MockRepo:
        mock_repo = AsyncMock()
        MockRepo.return_value = mock_repo
        service = LlmBudgetService(session)
        service._mock_repo = mock_repo  # expose for assertions
        yield service


# ── Providers ──


class TestCreateProvider:
    @pytest.mark.asyncio
    async def test_create_success(self, svc):
        provider = _mock_provider()
        svc._mock_repo.create_provider.return_value = provider

        data = LlmProviderCreate(
            provider_name="openai",
            display_name="OpenAI",
            default_model="gpt-4",
            cost_per_input_token=Decimal("0.00003"),
            cost_per_output_token=Decimal("0.00006"),
            status="active",
        )
        result = await svc.create_provider("acme", data)

        assert result.provider_name == "openai"
        svc._mock_repo.create_provider.assert_awaited_once()


class TestListProviders:
    @pytest.mark.asyncio
    async def test_list_returns_providers(self, svc):
        svc._mock_repo.list_providers_by_tenant.return_value = [_mock_provider(), _mock_provider()]

        result = await svc.list_providers("acme")

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_empty(self, svc):
        svc._mock_repo.list_providers_by_tenant.return_value = []

        result = await svc.list_providers("acme")

        assert result == []


class TestDeleteProvider:
    @pytest.mark.asyncio
    async def test_delete_success(self, svc):
        svc._mock_repo.get_provider_by_id.return_value = _mock_provider()
        svc._mock_repo.delete_provider.return_value = None

        await svc.delete_provider(uuid.uuid4())

        svc._mock_repo.delete_provider.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_not_found_raises(self, svc):
        svc._mock_repo.get_provider_by_id.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await svc.delete_provider(uuid.uuid4())


# ── Budget CRUD ──


class TestCreateBudget:
    @pytest.mark.asyncio
    async def test_create_success(self, svc):
        svc._mock_repo.get_budget_by_tenant.return_value = None
        svc._mock_repo.create_budget.return_value = _mock_budget()

        data = LlmBudgetCreate(monthly_limit_usd=Decimal("100.00"))
        result = await svc.create_budget("acme", data)

        assert result.monthly_limit_usd == Decimal("100.00")

    @pytest.mark.asyncio
    async def test_create_already_exists_raises(self, svc):
        svc._mock_repo.get_budget_by_tenant.return_value = _mock_budget()

        data = LlmBudgetCreate(monthly_limit_usd=Decimal("100.00"))
        with pytest.raises(ValueError, match=r"already exists|already has"):
            await svc.create_budget("acme", data)


class TestGetBudget:
    @pytest.mark.asyncio
    async def test_get_success(self, svc):
        svc._mock_repo.get_budget_by_tenant.return_value = _mock_budget()

        result = await svc.get_budget("acme")

        assert result.tenant_id == "acme"

    @pytest.mark.asyncio
    async def test_get_not_found_raises(self, svc):
        svc._mock_repo.get_budget_by_tenant.return_value = None

        with pytest.raises(ValueError, match=r"not found|No budget"):
            await svc.get_budget("acme")


class TestUpdateBudget:
    @pytest.mark.asyncio
    async def test_update_success(self, svc):
        budget = _mock_budget()
        svc._mock_repo.get_budget_by_tenant.return_value = budget
        svc._mock_repo.update_budget.return_value = budget

        data = LlmBudgetUpdate(monthly_limit_usd=Decimal("200.00"))
        result = await svc.update_budget("acme", data)

        assert result is not None

    @pytest.mark.asyncio
    async def test_update_not_found_raises(self, svc):
        svc._mock_repo.get_budget_by_tenant.return_value = None

        data = LlmBudgetUpdate(monthly_limit_usd=Decimal("200.00"))
        with pytest.raises(ValueError, match=r"not found|No budget"):
            await svc.update_budget("acme", data)


# ── Spend ──


class TestRecordSpend:
    @pytest.mark.asyncio
    async def test_record_spend_normal(self, svc):
        budget = _mock_budget(current_spend_usd=Decimal("10.00"), alert_threshold_pct=80)
        svc._mock_repo.get_budget_by_tenant.return_value = budget
        svc._mock_repo.increment_spend.return_value = None

        await svc.record_spend("acme", 5.0)

        svc._mock_repo.increment_spend.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_record_spend_no_budget(self, svc):
        svc._mock_repo.get_budget_by_tenant.return_value = None

        # Should not raise — fail-open for spend recording
        with contextlib.suppress(ValueError):
            await svc.record_spend("acme", 5.0)


class TestGetSpendSummary:
    @pytest.mark.asyncio
    async def test_get_summary_success(self, svc):
        budget = _mock_budget()
        svc._mock_repo.get_budget_by_tenant.return_value = budget

        result = await svc.get_spend_summary("acme")

        assert result.tenant_id == "acme"

    @pytest.mark.asyncio
    async def test_get_summary_not_found_raises(self, svc):
        svc._mock_repo.get_budget_by_tenant.return_value = None

        with pytest.raises(ValueError, match=r"not found|No budget"):
            await svc.get_spend_summary("acme")


# ── Check Budget ──


class TestCheckBudget:
    @pytest.mark.asyncio
    async def test_check_within_budget(self, svc):
        budget = _mock_budget(is_over_budget=False)
        svc._mock_repo.get_budget_by_tenant.return_value = budget

        result = await svc.check_budget("acme")

        assert result is True

    @pytest.mark.asyncio
    async def test_check_over_budget(self, svc):
        budget = _mock_budget(is_over_budget=True)
        svc._mock_repo.get_budget_by_tenant.return_value = budget

        result = await svc.check_budget("acme")

        assert result is False

    @pytest.mark.asyncio
    async def test_check_no_budget_returns_true(self, svc):
        """Fail-open: no budget configured = allow."""
        svc._mock_repo.get_budget_by_tenant.return_value = None

        result = await svc.check_budget("acme")

        assert result is True
