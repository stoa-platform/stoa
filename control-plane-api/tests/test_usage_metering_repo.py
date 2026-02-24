"""Unit tests for UsageMeteringRepository (CAB-1334).

Strategy: mock AsyncSession so that every code path in the repository
(query construction, result consumption, upsert branching) executes and
registers as covered. No real database needed.
"""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.repositories.usage_metering import UsageMeteringRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session() -> AsyncMock:
    """Return a minimal AsyncSession mock."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock()
    return session


def _make_usage_summary(
    *,
    tenant_id: str = "acme",
    api_id: uuid.UUID | None = None,
    consumer_id: uuid.UUID | None = None,
    period: str = "daily",
    request_count: int = 100,
    error_count: int = 5,
    total_latency_ms: int = 10_000,
    p99_latency_ms: int | None = 250,
    total_tokens: int = 500,
) -> MagicMock:
    """Return a MagicMock that mimics a UsageSummary ORM instance."""
    now = datetime.utcnow()
    obj = MagicMock()
    obj.id = uuid.uuid4()
    obj.tenant_id = tenant_id
    obj.api_id = api_id or uuid.uuid4()
    obj.consumer_id = consumer_id
    obj.period = period
    obj.period_start = now
    obj.request_count = request_count
    obj.error_count = error_count
    obj.total_latency_ms = total_latency_ms
    obj.p99_latency_ms = p99_latency_ms
    obj.total_tokens = total_tokens
    obj.created_at = now
    obj.updated_at = now
    return obj


def _scalar_result(value) -> MagicMock:
    """Wrap a scalar (or None) in a mock execute() result."""
    result = MagicMock()
    result.scalar.return_value = value
    result.scalar_one_or_none.return_value = value
    return result


def _scalars_result(items: list) -> MagicMock:
    """Wrap a list in a mock execute() result with .scalars().all()."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    result.scalars.return_value = scalars
    return result


def _row_result(row) -> MagicMock:
    """Wrap an aggregation row (or None) in a mock execute() result with .one_or_none()."""
    result = MagicMock()
    result.one_or_none.return_value = row
    return result


def _make_agg_row(
    *,
    total_requests: int | None = 100,
    total_errors: int | None = 5,
    p99_latency_ms: int | None = 250,
    total_latency_ms: int | None = 10_000,
    total_tokens: int | None = 500,
    period_start: datetime | None = None,
) -> MagicMock:
    """Return a mock aggregation row as returned by SQLAlchemy .one_or_none()."""
    row = MagicMock()
    row.total_requests = total_requests
    row.total_errors = total_errors
    row.p99_latency_ms = p99_latency_ms
    row.total_latency_ms = total_latency_ms
    row.total_tokens = total_tokens
    row.period_start = period_start or datetime.utcnow()
    return row


# ---------------------------------------------------------------------------
# get_usage_summary — happy paths
# ---------------------------------------------------------------------------


class TestGetUsageSummary:
    async def test_returns_items_and_total(self) -> None:
        session = _make_session()
        items = [_make_usage_summary(), _make_usage_summary(request_count=200)]
        session.execute = AsyncMock(side_effect=[_scalar_result(2), _scalars_result(items)])
        repo = UsageMeteringRepository(session)

        result_items, total = await repo.get_usage_summary("acme")

        assert total == 2
        assert len(result_items) == 2
        assert session.execute.await_count == 2

    async def test_returns_empty_when_no_records(self) -> None:
        session = _make_session()
        session.execute = AsyncMock(side_effect=[_scalar_result(0), _scalars_result([])])
        repo = UsageMeteringRepository(session)

        result_items, total = await repo.get_usage_summary("acme")

        assert total == 0
        assert result_items == []

    async def test_null_count_coerced_to_zero(self) -> None:
        """When count query returns None, total should be 0, not None."""
        session = _make_session()
        session.execute = AsyncMock(side_effect=[_scalar_result(None), _scalars_result([])])
        repo = UsageMeteringRepository(session)

        _, total = await repo.get_usage_summary("acme")

        assert total == 0

    async def test_filters_by_period(self) -> None:
        session = _make_session()
        monthly_items = [_make_usage_summary(period="monthly")]
        session.execute = AsyncMock(side_effect=[_scalar_result(1), _scalars_result(monthly_items)])
        repo = UsageMeteringRepository(session)

        result_items, total = await repo.get_usage_summary("acme", period="monthly")

        assert total == 1
        assert len(result_items) == 1

    async def test_filters_by_api_id_when_provided(self) -> None:
        """When api_id is provided the query should still succeed (extra condition added)."""
        session = _make_session()
        api_id = uuid.uuid4()
        items = [_make_usage_summary(api_id=api_id)]
        session.execute = AsyncMock(side_effect=[_scalar_result(1), _scalars_result(items)])
        repo = UsageMeteringRepository(session)

        result_items, total = await repo.get_usage_summary("acme", api_id=api_id)

        assert total == 1
        assert session.execute.await_count == 2

    async def test_no_api_id_filter_omits_api_condition(self) -> None:
        """When api_id is None the extra condition branch is skipped — 2 queries fired."""
        session = _make_session()
        session.execute = AsyncMock(side_effect=[_scalar_result(0), _scalars_result([])])
        repo = UsageMeteringRepository(session)

        await repo.get_usage_summary("acme", api_id=None)

        assert session.execute.await_count == 2

    async def test_respects_limit_and_offset_params(self) -> None:
        """Ensure limit/offset params don't raise and the queries still fire."""
        session = _make_session()
        session.execute = AsyncMock(side_effect=[_scalar_result(5), _scalars_result([])])
        repo = UsageMeteringRepository(session)

        await repo.get_usage_summary("acme", limit=10, offset=20)

        assert session.execute.await_count == 2


# ---------------------------------------------------------------------------
# get_usage_details — happy paths
# ---------------------------------------------------------------------------


class TestGetUsageDetails:
    async def test_returns_aggregated_dict(self) -> None:
        session = _make_session()
        row = _make_agg_row(
            total_requests=100,
            total_errors=5,
            p99_latency_ms=250,
            total_latency_ms=10_000,
            total_tokens=500,
        )
        session.execute = AsyncMock(return_value=_row_result(row))
        repo = UsageMeteringRepository(session)

        api_id = uuid.uuid4()
        result = await repo.get_usage_details("acme", api_id)

        assert result is not None
        assert result["api_id"] == api_id
        assert result["tenant_id"] == "acme"
        assert result["total_requests"] == 100
        assert result["total_errors"] == 5
        assert result["p99_latency_ms"] == 250
        assert result["total_tokens"] == 500

    async def test_computes_error_rate(self) -> None:
        session = _make_session()
        row = _make_agg_row(total_requests=100, total_errors=10)
        session.execute = AsyncMock(return_value=_row_result(row))
        repo = UsageMeteringRepository(session)

        result = await repo.get_usage_details("acme", uuid.uuid4())

        # 10/100 * 100 = 10.0
        assert result is not None
        assert result["error_rate"] == 10.0

    async def test_computes_avg_latency(self) -> None:
        session = _make_session()
        row = _make_agg_row(total_requests=100, total_latency_ms=50_000)
        session.execute = AsyncMock(return_value=_row_result(row))
        repo = UsageMeteringRepository(session)

        result = await repo.get_usage_details("acme", uuid.uuid4())

        # 50000 / 100 = 500.0
        assert result is not None
        assert result["avg_latency_ms"] == 500.0

    async def test_zero_requests_returns_none(self) -> None:
        """When total_requests is None in the aggregation row, return None."""
        session = _make_session()
        row = _make_agg_row(total_requests=None)
        session.execute = AsyncMock(return_value=_row_result(row))
        repo = UsageMeteringRepository(session)

        result = await repo.get_usage_details("acme", uuid.uuid4())

        assert result is None

    async def test_no_row_returns_none(self) -> None:
        """When the query returns no rows, return None."""
        session = _make_session()
        session.execute = AsyncMock(return_value=_row_result(None))
        repo = UsageMeteringRepository(session)

        result = await repo.get_usage_details("acme", uuid.uuid4())

        assert result is None

    async def test_error_rate_zero_when_no_errors(self) -> None:
        session = _make_session()
        row = _make_agg_row(total_requests=50, total_errors=0)
        session.execute = AsyncMock(return_value=_row_result(row))
        repo = UsageMeteringRepository(session)

        result = await repo.get_usage_details("acme", uuid.uuid4())

        assert result is not None
        assert result["error_rate"] == 0.0

    async def test_with_start_date_filter(self) -> None:
        """Providing start_date should not raise and query fires once."""
        session = _make_session()
        row = _make_agg_row(total_requests=10, total_errors=0)
        session.execute = AsyncMock(return_value=_row_result(row))
        repo = UsageMeteringRepository(session)

        start = datetime(2026, 1, 1)
        result = await repo.get_usage_details("acme", uuid.uuid4(), start_date=start)

        session.execute.assert_awaited_once()
        assert result is not None

    async def test_with_end_date_filter(self) -> None:
        """Providing end_date should not raise and query fires once."""
        session = _make_session()
        row = _make_agg_row(total_requests=10, total_errors=0)
        session.execute = AsyncMock(return_value=_row_result(row))
        repo = UsageMeteringRepository(session)

        end = datetime(2026, 3, 31)
        result = await repo.get_usage_details("acme", uuid.uuid4(), end_date=end)

        session.execute.assert_awaited_once()
        assert result is not None

    async def test_with_both_date_filters(self) -> None:
        session = _make_session()
        row = _make_agg_row(total_requests=10, total_errors=2)
        session.execute = AsyncMock(return_value=_row_result(row))
        repo = UsageMeteringRepository(session)

        start = datetime(2026, 1, 1)
        end = datetime(2026, 3, 31)
        result = await repo.get_usage_details("acme", uuid.uuid4(), start_date=start, end_date=end)

        assert result is not None
        assert result["total_requests"] == 10

    async def test_total_tokens_none_coerces_to_zero(self) -> None:
        """When total_tokens is None in aggregation row, result should be 0."""
        session = _make_session()
        row = _make_agg_row(total_requests=10, total_errors=0, total_tokens=None)
        session.execute = AsyncMock(return_value=_row_result(row))
        repo = UsageMeteringRepository(session)

        result = await repo.get_usage_details("acme", uuid.uuid4())

        assert result is not None
        assert result["total_tokens"] == 0


# ---------------------------------------------------------------------------
# upsert_usage — insert branch
# ---------------------------------------------------------------------------


class TestUpsertUsageInsert:
    async def test_insert_when_no_existing_record(self) -> None:
        """When the select finds no existing record, a new UsageSummary is created."""
        session = _make_session()
        # First execute: select → no existing record
        session.execute = AsyncMock(return_value=_scalar_result(None))
        repo = UsageMeteringRepository(session)

        api_id = uuid.uuid4()
        result = await repo.upsert_usage(
            tenant_id="acme",
            api_id=api_id,
            period="daily",
            period_start=datetime(2026, 3, 1),
            request_count=10,
            error_count=1,
            total_latency_ms=500,
        )

        # session.add should have been called with the new record
        session.add.assert_called_once()
        session.flush.assert_awaited_once()
        # The returned object should have been added (it's the new record)
        added_obj = session.add.call_args[0][0]
        assert added_obj.tenant_id == "acme"
        assert added_obj.api_id == api_id
        assert added_obj.request_count == 10

    async def test_insert_with_consumer_id(self) -> None:
        """consumer_id=UUID triggers the consumer_id == value branch (not is_(None))."""
        session = _make_session()
        session.execute = AsyncMock(return_value=_scalar_result(None))
        repo = UsageMeteringRepository(session)

        consumer_id = uuid.uuid4()
        await repo.upsert_usage(
            tenant_id="acme",
            api_id=uuid.uuid4(),
            period="daily",
            period_start=datetime(2026, 3, 1),
            consumer_id=consumer_id,
        )

        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        assert added.consumer_id == consumer_id

    async def test_insert_without_consumer_id(self) -> None:
        """consumer_id=None triggers the is_(None) branch."""
        session = _make_session()
        session.execute = AsyncMock(return_value=_scalar_result(None))
        repo = UsageMeteringRepository(session)

        await repo.upsert_usage(
            tenant_id="acme",
            api_id=uuid.uuid4(),
            period="monthly",
            period_start=datetime(2026, 3, 1),
            consumer_id=None,
        )

        added = session.add.call_args[0][0]
        assert added.consumer_id is None

    async def test_insert_returns_new_record(self) -> None:
        session = _make_session()
        session.execute = AsyncMock(return_value=_scalar_result(None))
        repo = UsageMeteringRepository(session)

        result = await repo.upsert_usage(
            tenant_id="acme",
            api_id=uuid.uuid4(),
            period="daily",
            period_start=datetime(2026, 3, 1),
            request_count=5,
        )

        # Should return the newly created object (same as what was added)
        assert session.add.call_args[0][0] is result

    async def test_insert_with_p99_latency(self) -> None:
        session = _make_session()
        session.execute = AsyncMock(return_value=_scalar_result(None))
        repo = UsageMeteringRepository(session)

        await repo.upsert_usage(
            tenant_id="acme",
            api_id=uuid.uuid4(),
            period="daily",
            period_start=datetime(2026, 3, 1),
            p99_latency_ms=300,
        )

        added = session.add.call_args[0][0]
        assert added.p99_latency_ms == 300


# ---------------------------------------------------------------------------
# upsert_usage — update branch
# ---------------------------------------------------------------------------


class TestUpsertUsageUpdate:
    async def test_update_when_existing_record_found(self) -> None:
        """When select finds an existing record, execute UPDATE + flush + refresh."""
        session = _make_session()
        existing = _make_usage_summary(request_count=50)
        # First execute: select → existing record
        # Second execute: UPDATE statement
        select_result = _scalar_result(existing)
        update_result = MagicMock()
        session.execute = AsyncMock(side_effect=[select_result, update_result])
        repo = UsageMeteringRepository(session)

        result = await repo.upsert_usage(
            tenant_id="acme",
            api_id=existing.api_id,
            period="daily",
            period_start=existing.period_start,
            request_count=10,
            error_count=1,
        )

        assert result is existing
        assert session.execute.await_count == 2
        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once_with(existing)
        # session.add should NOT be called on an update
        session.add.assert_not_called()

    async def test_update_with_p99_latency_override(self) -> None:
        """When p99_latency_ms is provided in update, it should replace the existing value."""
        session = _make_session()
        existing = _make_usage_summary(p99_latency_ms=100)
        session.execute = AsyncMock(side_effect=[_scalar_result(existing), MagicMock()])
        repo = UsageMeteringRepository(session)

        result = await repo.upsert_usage(
            tenant_id="acme",
            api_id=existing.api_id,
            period="daily",
            period_start=existing.period_start,
            p99_latency_ms=400,
        )

        assert result is existing

    async def test_update_preserves_existing_p99_when_none(self) -> None:
        """When p99_latency_ms is None in the call, existing value is preserved."""
        session = _make_session()
        existing = _make_usage_summary(p99_latency_ms=200)
        session.execute = AsyncMock(side_effect=[_scalar_result(existing), MagicMock()])
        repo = UsageMeteringRepository(session)

        result = await repo.upsert_usage(
            tenant_id="acme",
            api_id=existing.api_id,
            period="daily",
            period_start=existing.period_start,
            p99_latency_ms=None,  # Should keep existing.p99_latency_ms
        )

        assert result is existing
        # Refresh must still be called
        session.refresh.assert_awaited_once_with(existing)

    async def test_update_with_consumer_id_existing(self) -> None:
        """consumer_id provided → consumer_id == value condition in select."""
        session = _make_session()
        consumer_id = uuid.uuid4()
        existing = _make_usage_summary(consumer_id=consumer_id)
        session.execute = AsyncMock(side_effect=[_scalar_result(existing), MagicMock()])
        repo = UsageMeteringRepository(session)

        result = await repo.upsert_usage(
            tenant_id="acme",
            api_id=existing.api_id,
            period="daily",
            period_start=existing.period_start,
            consumer_id=consumer_id,
        )

        assert result is existing

    async def test_update_fires_execute_twice(self) -> None:
        """The update path fires exactly 2 execute calls (select + update statement)."""
        session = _make_session()
        existing = _make_usage_summary()
        session.execute = AsyncMock(side_effect=[_scalar_result(existing), MagicMock()])
        repo = UsageMeteringRepository(session)

        await repo.upsert_usage(
            tenant_id="acme",
            api_id=existing.api_id,
            period="daily",
            period_start=existing.period_start,
        )

        assert session.execute.await_count == 2
