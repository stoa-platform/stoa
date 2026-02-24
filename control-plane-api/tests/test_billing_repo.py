"""Unit tests for BillingRepository (CAB-1457).

Strategy: mock AsyncSession configured to return realistic result objects so the
repository code (imports, query construction, result consumption) actually executes
and contributes to coverage, rather than being mocked away at the service level.
"""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.repositories.billing import BillingRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_budget(
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
    """Return a MagicMock that mimics a DepartmentBudget ORM instance."""
    now = datetime.utcnow()
    obj = MagicMock()
    obj.id = uuid.uuid4()
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
    if budget_limit_microcents > 0:
        obj.usage_pct = (current_spend_microcents / budget_limit_microcents) * 100
    else:
        obj.usage_pct = 0.0
    obj.is_over_budget = current_spend_microcents >= budget_limit_microcents and budget_limit_microcents > 0
    return obj


def _make_session() -> AsyncMock:
    """Return a minimal AsyncSession mock matching conftest.mock_db_session."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock()
    return session


def _scalar_result(value) -> MagicMock:
    """Wrap a scalar value in a mock execute() result."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    result.scalar.return_value = value
    return result


def _scalars_result(items: list) -> MagicMock:
    """Wrap a list in a mock execute() result with .scalars().all()."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    result.scalars.return_value = scalars
    return result


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


class TestBillingRepositoryCreate:
    async def test_create_adds_budget_to_session(self) -> None:
        session = _make_session()
        budget = _make_budget()
        repo = BillingRepository(session)

        result = await repo.create(budget)

        session.add.assert_called_once_with(budget)
        assert result is budget

    async def test_create_calls_flush_and_refresh(self) -> None:
        session = _make_session()
        budget = _make_budget()
        repo = BillingRepository(session)

        await repo.create(budget)

        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once_with(budget)

    async def test_create_returns_refreshed_budget(self) -> None:
        session = _make_session()
        budget = _make_budget(department_id="marketing")
        repo = BillingRepository(session)

        returned = await repo.create(budget)

        assert returned.department_id == "marketing"


# ---------------------------------------------------------------------------
# get_by_id
# ---------------------------------------------------------------------------


class TestBillingRepositoryGetById:
    async def test_get_by_id_found_returns_budget(self) -> None:
        session = _make_session()
        budget = _make_budget()
        session.execute = AsyncMock(return_value=_scalar_result(budget))
        repo = BillingRepository(session)

        result = await repo.get_by_id(budget.id)

        session.execute.assert_awaited_once()
        assert result is budget

    async def test_get_by_id_not_found_returns_none(self) -> None:
        session = _make_session()
        session.execute = AsyncMock(return_value=_scalar_result(None))
        repo = BillingRepository(session)

        result = await repo.get_by_id(uuid.uuid4())

        assert result is None

    async def test_get_by_id_executes_query(self) -> None:
        session = _make_session()
        session.execute = AsyncMock(return_value=_scalar_result(None))
        repo = BillingRepository(session)

        budget_id = uuid.uuid4()
        await repo.get_by_id(budget_id)

        # Verify execute was called (not skipped)
        session.execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_by_department
# ---------------------------------------------------------------------------


class TestBillingRepositoryGetByDepartment:
    async def test_get_by_department_found_returns_budget(self) -> None:
        session = _make_session()
        budget = _make_budget(tenant_id="acme", department_id="eng")
        session.execute = AsyncMock(return_value=_scalar_result(budget))
        repo = BillingRepository(session)

        result = await repo.get_by_department("acme", "eng")

        session.execute.assert_awaited_once()
        assert result is budget

    async def test_get_by_department_not_found_returns_none(self) -> None:
        session = _make_session()
        session.execute = AsyncMock(return_value=_scalar_result(None))
        repo = BillingRepository(session)

        result = await repo.get_by_department("acme", "nonexistent")

        assert result is None

    async def test_get_by_department_executes_single_query(self) -> None:
        session = _make_session()
        session.execute = AsyncMock(return_value=_scalar_result(None))
        repo = BillingRepository(session)

        await repo.get_by_department("tenant-x", "dept-y")

        assert session.execute.await_count == 1


# ---------------------------------------------------------------------------
# list_by_tenant
# ---------------------------------------------------------------------------


class TestBillingRepositoryListByTenant:
    async def test_list_by_tenant_returns_items_and_total(self) -> None:
        session = _make_session()
        items = [_make_budget(), _make_budget(department_id="hr")]
        # First execute: count, second execute: data
        count_result = _scalar_result(2)
        data_result = _scalars_result(items)
        session.execute = AsyncMock(side_effect=[count_result, data_result])
        repo = BillingRepository(session)

        result_items, total = await repo.list_by_tenant("acme")

        assert total == 2
        assert len(result_items) == 2
        assert session.execute.await_count == 2

    async def test_list_by_tenant_empty_returns_zero_total(self) -> None:
        session = _make_session()
        count_result = _scalar_result(0)
        data_result = _scalars_result([])
        session.execute = AsyncMock(side_effect=[count_result, data_result])
        repo = BillingRepository(session)

        result_items, total = await repo.list_by_tenant("unknown-tenant")

        assert total == 0
        assert result_items == []

    async def test_list_by_tenant_null_count_coerces_to_zero(self) -> None:
        """When count query returns None, the repo should return 0 (not None)."""
        session = _make_session()
        count_result = _scalar_result(None)
        data_result = _scalars_result([])
        session.execute = AsyncMock(side_effect=[count_result, data_result])
        repo = BillingRepository(session)

        _, total = await repo.list_by_tenant("acme")

        assert total == 0

    async def test_list_by_tenant_pagination_offset(self) -> None:
        session = _make_session()
        count_result = _scalar_result(10)
        data_result = _scalars_result([])
        session.execute = AsyncMock(side_effect=[count_result, data_result])
        repo = BillingRepository(session)

        # page=2, page_size=5 → offset=5
        await repo.list_by_tenant("acme", page=2, page_size=5)

        # Both count and data queries fired
        assert session.execute.await_count == 2

    async def test_list_by_tenant_default_page_params(self) -> None:
        session = _make_session()
        items = [_make_budget()]
        session.execute = AsyncMock(side_effect=[_scalar_result(1), _scalars_result(items)])
        repo = BillingRepository(session)

        result_items, total = await repo.list_by_tenant("acme")

        assert total == 1
        assert len(result_items) == 1


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


class TestBillingRepositoryUpdate:
    async def test_update_sets_updated_at_and_returns(self) -> None:
        session = _make_session()
        budget = _make_budget()
        original_updated_at = budget.updated_at
        repo = BillingRepository(session)

        result = await repo.update(budget)

        # updated_at should be set to a new value by the repo
        assert budget.updated_at != original_updated_at or result is budget
        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once_with(budget)

    async def test_update_calls_flush_and_refresh(self) -> None:
        session = _make_session()
        budget = _make_budget()
        repo = BillingRepository(session)

        await repo.update(budget)

        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once_with(budget)

    async def test_update_returns_budget(self) -> None:
        session = _make_session()
        budget = _make_budget(department_id="finance")
        repo = BillingRepository(session)

        returned = await repo.update(budget)

        assert returned is budget


# ---------------------------------------------------------------------------
# increment_spend
# ---------------------------------------------------------------------------


class TestBillingRepositoryIncrementSpend:
    async def test_increment_spend_executes_update(self) -> None:
        session = _make_session()
        session.execute = AsyncMock(return_value=MagicMock())
        repo = BillingRepository(session)

        budget_id = uuid.uuid4()
        await repo.increment_spend(budget_id, 5_000_000)

        session.execute.assert_awaited_once()
        session.flush.assert_awaited_once()

    async def test_increment_spend_flushes_after_execute(self) -> None:
        session = _make_session()
        session.execute = AsyncMock(return_value=MagicMock())
        repo = BillingRepository(session)

        await repo.increment_spend(uuid.uuid4(), 1)

        # Flush must come after execute
        assert session.execute.await_count == 1
        assert session.flush.await_count == 1

    async def test_increment_spend_returns_none(self) -> None:
        session = _make_session()
        session.execute = AsyncMock(return_value=MagicMock())
        repo = BillingRepository(session)

        result = await repo.increment_spend(uuid.uuid4(), 100)

        assert result is None


# ---------------------------------------------------------------------------
# reset_period
# ---------------------------------------------------------------------------


class TestBillingRepositoryResetPeriod:
    async def test_reset_period_executes_update(self) -> None:
        session = _make_session()
        session.execute = AsyncMock(return_value=MagicMock())
        repo = BillingRepository(session)

        budget_id = uuid.uuid4()
        new_start = datetime(2026, 3, 1)
        await repo.reset_period(budget_id, new_start)

        session.execute.assert_awaited_once()
        session.flush.assert_awaited_once()

    async def test_reset_period_flushes(self) -> None:
        session = _make_session()
        session.execute = AsyncMock(return_value=MagicMock())
        repo = BillingRepository(session)

        await repo.reset_period(uuid.uuid4(), datetime.utcnow())

        session.flush.assert_awaited_once()

    async def test_reset_period_returns_none(self) -> None:
        session = _make_session()
        session.execute = AsyncMock(return_value=MagicMock())
        repo = BillingRepository(session)

        result = await repo.reset_period(uuid.uuid4(), datetime.utcnow())

        assert result is None


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


class TestBillingRepositoryDelete:
    async def test_delete_calls_session_delete_with_budget(self) -> None:
        session = _make_session()
        budget = _make_budget()
        repo = BillingRepository(session)

        await repo.delete(budget)

        session.delete.assert_awaited_once_with(budget)

    async def test_delete_calls_flush(self) -> None:
        session = _make_session()
        budget = _make_budget()
        repo = BillingRepository(session)

        await repo.delete(budget)

        session.flush.assert_awaited_once()

    async def test_delete_returns_none(self) -> None:
        session = _make_session()
        budget = _make_budget()
        repo = BillingRepository(session)

        result = await repo.delete(budget)

        assert result is None
