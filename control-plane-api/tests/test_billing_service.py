"""Tests for BillingService (CAB-1457)."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.schemas.billing import (
    BudgetCheckResponse,
    DepartmentBudgetCreate,
    DepartmentBudgetListResponse,
    DepartmentBudgetResponse,
    DepartmentBudgetUpdate,
)
from src.services.billing_service import BillingService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session() -> AsyncMock:
    """Minimal async SQLAlchemy session mock."""
    return AsyncMock()


def _make_budget_orm(
    *,
    tenant_id: str = "acme",
    department_id: str = "engineering",
    department_name: str | None = "Engineering",
    budget_limit_microcents: int = 100_000_000,
    current_spend_microcents: int = 0,
    warning_threshold_pct: int = 80,
    critical_threshold_pct: int = 95,
    enforcement: str = "disabled",
    period: str = "monthly",
) -> MagicMock:
    """Return a MagicMock that mimics a DepartmentBudget ORM row."""
    now = datetime.utcnow()
    obj = MagicMock()
    obj.id = uuid4()
    obj.tenant_id = tenant_id
    obj.department_id = department_id
    obj.department_name = department_name
    obj.period = period
    obj.budget_limit_microcents = budget_limit_microcents
    obj.current_spend_microcents = current_spend_microcents
    obj.period_start = now
    obj.warning_threshold_pct = warning_threshold_pct
    obj.critical_threshold_pct = critical_threshold_pct
    obj.enforcement = enforcement
    obj.created_by = None
    obj.created_at = now
    obj.updated_at = now
    # Derived properties — use the same logic as the real model
    obj.usage_pct = (current_spend_microcents / budget_limit_microcents) * 100 if budget_limit_microcents > 0 else 0.0
    obj.is_over_budget = current_spend_microcents >= budget_limit_microcents and budget_limit_microcents > 0
    return obj


@pytest.fixture
def session() -> AsyncMock:
    return _make_session()


@pytest.fixture
def service(session: AsyncMock) -> BillingService:
    """BillingService with a mocked BillingRepository."""
    svc = BillingService(session)
    svc.repo = MagicMock()
    return svc


@pytest.fixture
def budget_create_data() -> DepartmentBudgetCreate:
    return DepartmentBudgetCreate(
        department_id="engineering",
        department_name="Engineering",
        period="monthly",
        budget_limit_microcents=100_000_000,
        period_start=datetime.utcnow(),
        warning_threshold_pct=80,
        critical_threshold_pct=95,
        enforcement="disabled",
    )


# ---------------------------------------------------------------------------
# create_budget
# ---------------------------------------------------------------------------


class TestCreateBudget:
    async def test_creates_budget_and_returns_response(
        self, service: BillingService, budget_create_data: DepartmentBudgetCreate
    ) -> None:
        orm_obj = _make_budget_orm()
        service.repo.create = AsyncMock(return_value=orm_obj)

        with patch("src.services.billing_service.DepartmentBudgetResponse.model_validate") as mv:
            mv.return_value = MagicMock(spec=DepartmentBudgetResponse)
            await service.create_budget("acme", budget_create_data, created_by="admin")

        service.repo.create.assert_called_once()
        mv.assert_called_once_with(orm_obj)

    async def test_passes_tenant_id_and_created_by(
        self, service: BillingService, budget_create_data: DepartmentBudgetCreate
    ) -> None:
        orm_obj = _make_budget_orm(tenant_id="tenant-xyz", department_id="engineering")
        service.repo.create = AsyncMock(return_value=orm_obj)

        with patch("src.services.billing_service.DepartmentBudgetResponse.model_validate"):
            await service.create_budget("tenant-xyz", budget_create_data, created_by="user-1")

        created_arg = service.repo.create.call_args[0][0]
        assert created_arg.tenant_id == "tenant-xyz"
        assert created_arg.created_by == "user-1"
        assert created_arg.current_spend_microcents == 0

    async def test_initial_spend_is_zero(
        self, service: BillingService, budget_create_data: DepartmentBudgetCreate
    ) -> None:
        orm_obj = _make_budget_orm()
        service.repo.create = AsyncMock(return_value=orm_obj)

        with patch("src.services.billing_service.DepartmentBudgetResponse.model_validate"):
            await service.create_budget("acme", budget_create_data)

        created_arg = service.repo.create.call_args[0][0]
        assert created_arg.current_spend_microcents == 0


# ---------------------------------------------------------------------------
# get_budget
# ---------------------------------------------------------------------------


class TestGetBudget:
    async def test_found_returns_response(self, service: BillingService) -> None:
        budget_id = uuid4()
        orm_obj = _make_budget_orm()
        service.repo.get_by_id = AsyncMock(return_value=orm_obj)

        with patch("src.services.billing_service.DepartmentBudgetResponse.model_validate") as mv:
            mv.return_value = MagicMock(spec=DepartmentBudgetResponse)
            await service.get_budget(budget_id)

        service.repo.get_by_id.assert_called_once_with(budget_id)
        mv.assert_called_once_with(orm_obj)

    async def test_not_found_raises_value_error(self, service: BillingService) -> None:
        budget_id = uuid4()
        service.repo.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match=str(budget_id)):
            await service.get_budget(budget_id)

    async def test_error_message_contains_budget_id(self, service: BillingService) -> None:
        budget_id = uuid4()
        service.repo.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(ValueError) as exc_info:
            await service.get_budget(budget_id)

        assert str(budget_id) in str(exc_info.value)


# ---------------------------------------------------------------------------
# list_budgets
# ---------------------------------------------------------------------------


class TestListBudgets:
    async def test_returns_paginated_list(self, service: BillingService) -> None:
        orm_items = [_make_budget_orm(), _make_budget_orm()]
        service.repo.list_by_tenant = AsyncMock(return_value=(orm_items, 2))

        with patch("src.services.billing_service.DepartmentBudgetResponse.model_validate") as mv:
            mv.side_effect = lambda _x: MagicMock(spec=DepartmentBudgetResponse)
            result = await service.list_budgets("acme", page=1, page_size=20)

        assert isinstance(result, DepartmentBudgetListResponse)
        assert result.total == 2
        assert len(result.items) == 2
        assert result.page == 1
        assert result.page_size == 20

    async def test_empty_result(self, service: BillingService) -> None:
        service.repo.list_by_tenant = AsyncMock(return_value=([], 0))

        with patch("src.services.billing_service.DepartmentBudgetResponse.model_validate"):
            result = await service.list_budgets("acme")

        assert result.total == 0
        assert result.items == []

    async def test_passes_pagination_params(self, service: BillingService) -> None:
        service.repo.list_by_tenant = AsyncMock(return_value=([], 0))

        with patch("src.services.billing_service.DepartmentBudgetResponse.model_validate"):
            await service.list_budgets("acme", page=3, page_size=10)

        service.repo.list_by_tenant.assert_called_once_with("acme", 3, 10)


# ---------------------------------------------------------------------------
# update_budget
# ---------------------------------------------------------------------------


class TestUpdateBudget:
    async def test_partial_update_applies_non_none_fields(self, service: BillingService) -> None:
        budget_id = uuid4()
        orm_obj = _make_budget_orm(department_name="Old Name", enforcement="disabled")
        service.repo.get_by_id = AsyncMock(return_value=orm_obj)
        service.repo.update = AsyncMock(return_value=orm_obj)

        data = DepartmentBudgetUpdate(department_name="New Name")

        with patch("src.services.billing_service.DepartmentBudgetResponse.model_validate"):
            await service.update_budget(budget_id, data)

        # department_name should be updated
        assert orm_obj.department_name == "New Name"
        # enforcement was not in update data, so stays unchanged
        assert orm_obj.enforcement == "disabled"
        service.repo.update.assert_called_once_with(orm_obj)

    async def test_update_limit_and_enforcement(self, service: BillingService) -> None:
        budget_id = uuid4()
        orm_obj = _make_budget_orm(budget_limit_microcents=50_000_000, enforcement="disabled")
        service.repo.get_by_id = AsyncMock(return_value=orm_obj)
        service.repo.update = AsyncMock(return_value=orm_obj)

        data = DepartmentBudgetUpdate(budget_limit_microcents=200_000_000, enforcement="enabled")

        with patch("src.services.billing_service.DepartmentBudgetResponse.model_validate"):
            await service.update_budget(budget_id, data)

        assert orm_obj.budget_limit_microcents == 200_000_000
        assert orm_obj.enforcement == "enabled"

    async def test_update_not_found_raises_value_error(self, service: BillingService) -> None:
        budget_id = uuid4()
        service.repo.get_by_id = AsyncMock(return_value=None)

        data = DepartmentBudgetUpdate(department_name="Anything")

        with pytest.raises(ValueError, match=str(budget_id)):
            await service.update_budget(budget_id, data)

    async def test_none_fields_not_applied(self, service: BillingService) -> None:
        """Fields explicitly set to None in the update schema must not overwrite existing values."""
        budget_id = uuid4()
        orm_obj = _make_budget_orm(warning_threshold_pct=80, critical_threshold_pct=95)
        service.repo.get_by_id = AsyncMock(return_value=orm_obj)
        service.repo.update = AsyncMock(return_value=orm_obj)

        # Only update enforcement, leave thresholds as None
        data = DepartmentBudgetUpdate(enforcement="warn_only")

        with patch("src.services.billing_service.DepartmentBudgetResponse.model_validate"):
            await service.update_budget(budget_id, data)

        assert orm_obj.warning_threshold_pct == 80
        assert orm_obj.critical_threshold_pct == 95


# ---------------------------------------------------------------------------
# check_budget
# ---------------------------------------------------------------------------


class TestCheckBudget:
    async def test_no_budget_returns_fail_open(self, service: BillingService) -> None:
        """When no budget record exists, fail-open: over_budget=False."""
        service.repo.get_by_department = AsyncMock(return_value=None)

        result = await service.check_budget("dept-x")

        assert isinstance(result, BudgetCheckResponse)
        assert result.over_budget is False
        assert result.enforcement == "disabled"

    async def test_under_budget_not_over(self, service: BillingService) -> None:
        orm_obj = _make_budget_orm(
            department_id="dept-x",
            tenant_id="dept-x",
            budget_limit_microcents=100_000_000,
            current_spend_microcents=50_000_000,
            enforcement="enabled",
        )
        # Fix derived properties to match constructor logic
        orm_obj.usage_pct = 50.0
        orm_obj.is_over_budget = False
        service.repo.get_by_department = AsyncMock(return_value=orm_obj)

        result = await service.check_budget("dept-x")

        assert result.over_budget is False

    async def test_over_budget_with_enforcement_enabled(self, service: BillingService) -> None:
        orm_obj = _make_budget_orm(
            department_id="dept-x",
            tenant_id="dept-x",
            budget_limit_microcents=100_000_000,
            current_spend_microcents=110_000_000,
            enforcement="enabled",
        )
        orm_obj.usage_pct = 110.0
        orm_obj.is_over_budget = True
        service.repo.get_by_department = AsyncMock(return_value=orm_obj)

        result = await service.check_budget("dept-x")

        assert result.over_budget is True
        assert result.enforcement == "enabled"
        assert result.current_spend_microcents == 110_000_000

    async def test_over_budget_with_enforcement_disabled(self, service: BillingService) -> None:
        """Even if spend exceeds limit, over_budget=False when enforcement is disabled."""
        orm_obj = _make_budget_orm(
            department_id="dept-x",
            tenant_id="dept-x",
            budget_limit_microcents=100_000_000,
            current_spend_microcents=110_000_000,
            enforcement="disabled",
        )
        orm_obj.usage_pct = 110.0
        orm_obj.is_over_budget = True
        service.repo.get_by_department = AsyncMock(return_value=orm_obj)

        result = await service.check_budget("dept-x")

        # enforcement=disabled → over_budget must be False (fail-open for non-enforced)
        assert result.over_budget is False
        assert result.enforcement == "disabled"

    async def test_check_budget_uses_department_id_as_both_keys(self, service: BillingService) -> None:
        """The gateway maps tenant_id = department_id, so both args should equal dept_id."""
        service.repo.get_by_department = AsyncMock(return_value=None)

        await service.check_budget("my-dept")

        service.repo.get_by_department.assert_called_once_with(tenant_id="my-dept", department_id="my-dept")

    async def test_returns_usage_pct_rounded_to_two_decimal_places(self, service: BillingService) -> None:
        orm_obj = _make_budget_orm(
            department_id="d",
            tenant_id="d",
            budget_limit_microcents=300,
            current_spend_microcents=100,
            enforcement="disabled",
        )
        # 100/300 * 100 = 33.3333...
        orm_obj.usage_pct = 33.3333333
        orm_obj.is_over_budget = False
        service.repo.get_by_department = AsyncMock(return_value=orm_obj)

        result = await service.check_budget("d")

        assert result.usage_pct == 33.33


# ---------------------------------------------------------------------------
# record_spend
# ---------------------------------------------------------------------------


class TestRecordSpend:
    async def test_no_budget_skips_silently(self, service: BillingService) -> None:
        service.repo.get_by_department = AsyncMock(return_value=None)
        service.repo.increment_spend = AsyncMock()

        # Should not raise
        await service.record_spend("acme", "engineering", 1_000_000)

        service.repo.increment_spend.assert_not_called()

    async def test_increments_spend_when_budget_exists(self, service: BillingService) -> None:
        orm_obj = _make_budget_orm(
            current_spend_microcents=10_000_000,
            budget_limit_microcents=100_000_000,
        )
        service.repo.get_by_department = AsyncMock(return_value=orm_obj)
        service.repo.increment_spend = AsyncMock()

        await service.record_spend("acme", "engineering", 5_000_000)

        service.repo.increment_spend.assert_called_once_with(orm_obj.id, 5_000_000)

    async def test_logs_warning_at_warning_threshold(
        self, service: BillingService, caplog: pytest.LogCaptureFixture
    ) -> None:
        # current: 79M, adding 5M → 84M / 100M = 84% → exceeds warning=80
        orm_obj = _make_budget_orm(
            current_spend_microcents=79_000_000,
            budget_limit_microcents=100_000_000,
            warning_threshold_pct=80,
            critical_threshold_pct=95,
        )
        service.repo.get_by_department = AsyncMock(return_value=orm_obj)
        service.repo.increment_spend = AsyncMock()

        import logging

        with caplog.at_level(logging.WARNING, logger="src.services.billing_service"):
            await service.record_spend("acme", "engineering", 5_000_000)

        assert any("WARNING" in msg for msg in caplog.messages)

    async def test_logs_critical_at_critical_threshold(
        self, service: BillingService, caplog: pytest.LogCaptureFixture
    ) -> None:
        # current: 94M, adding 5M → 99M / 100M = 99% → exceeds critical=95
        orm_obj = _make_budget_orm(
            current_spend_microcents=94_000_000,
            budget_limit_microcents=100_000_000,
            warning_threshold_pct=80,
            critical_threshold_pct=95,
        )
        service.repo.get_by_department = AsyncMock(return_value=orm_obj)
        service.repo.increment_spend = AsyncMock()

        import logging

        with caplog.at_level(logging.WARNING, logger="src.services.billing_service"):
            await service.record_spend("acme", "engineering", 5_000_000)

        assert any("CRITICAL" in msg for msg in caplog.messages)

    async def test_no_log_when_under_thresholds(
        self, service: BillingService, caplog: pytest.LogCaptureFixture
    ) -> None:
        # current: 10M, adding 5M → 15M / 100M = 15% → well below 80
        orm_obj = _make_budget_orm(
            current_spend_microcents=10_000_000,
            budget_limit_microcents=100_000_000,
            warning_threshold_pct=80,
            critical_threshold_pct=95,
        )
        service.repo.get_by_department = AsyncMock(return_value=orm_obj)
        service.repo.increment_spend = AsyncMock()

        import logging

        with caplog.at_level(logging.WARNING, logger="src.services.billing_service"):
            await service.record_spend("acme", "engineering", 5_000_000)

        billing_msgs = [r.message for r in caplog.records if r.name == "src.services.billing_service"]
        assert billing_msgs == []

    async def test_zero_limit_does_not_compute_threshold(
        self, service: BillingService, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When budget_limit_microcents=0, threshold check is skipped (no division by zero)."""
        orm_obj = _make_budget_orm(
            current_spend_microcents=0,
            budget_limit_microcents=0,
        )
        service.repo.get_by_department = AsyncMock(return_value=orm_obj)
        service.repo.increment_spend = AsyncMock()

        import logging

        with caplog.at_level(logging.WARNING, logger="src.services.billing_service"):
            await service.record_spend("acme", "engineering", 1_000)

        # No warning should be raised for a zero-limit budget
        billing_msgs = [r.message for r in caplog.records if r.name == "src.services.billing_service"]
        assert billing_msgs == []
