"""Tests for QuotaUsageRepository (CAB-1291)"""
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.repositories.quota_usage import QuotaUsageRepository


def _mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db


def _mock_usage(**kwargs):
    usage = MagicMock()
    usage.id = kwargs.get("id", uuid4())
    usage.consumer_id = kwargs.get("consumer_id", uuid4())
    usage.tenant_id = kwargs.get("tenant_id", "acme")
    usage.subscription_id = kwargs.get("subscription_id", None)
    usage.request_count_daily = kwargs.get("request_count_daily", 0)
    usage.request_count_monthly = kwargs.get("request_count_monthly", 0)
    usage.bandwidth_bytes_daily = kwargs.get("bandwidth_bytes_daily", 0)
    usage.bandwidth_bytes_monthly = kwargs.get("bandwidth_bytes_monthly", 0)
    usage.period_start_daily = kwargs.get("period_start_daily", date(2026, 2, 16))
    usage.period_start_monthly = kwargs.get("period_start_monthly", date(2026, 2, 1))
    usage.last_reset_at = kwargs.get("last_reset_at", None)
    usage.updated_at = kwargs.get("updated_at", None)
    return usage


# ── static methods ──


class TestStaticMethods:
    def test_current_daily_start(self):
        result = QuotaUsageRepository._current_daily_start()
        assert isinstance(result, date)

    def test_current_monthly_start(self):
        result = QuotaUsageRepository._current_monthly_start()
        assert isinstance(result, date)
        assert result.day == 1


# ── get_or_create ──


class TestGetOrCreate:
    async def test_existing_same_month(self):
        db = _mock_db()
        consumer_id = uuid4()
        usage = _mock_usage(
            consumer_id=consumer_id,
            period_start_monthly=date(2026, 2, 1),
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = usage
        db.execute = AsyncMock(return_value=mock_result)

        repo = QuotaUsageRepository(db)
        with patch.object(repo, "_current_daily_start", return_value=date(2026, 2, 16)), \
             patch.object(repo, "_current_monthly_start", return_value=date(2026, 2, 1)):
            result = await repo.get_or_create(consumer_id, "acme")
        assert result is usage

    async def test_existing_new_month_rollover(self):
        db = _mock_db()
        consumer_id = uuid4()
        usage = _mock_usage(
            consumer_id=consumer_id,
            period_start_monthly=date(2026, 1, 1),
            request_count_monthly=100,
            bandwidth_bytes_monthly=5000,
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = usage
        db.execute = AsyncMock(return_value=mock_result)

        repo = QuotaUsageRepository(db)
        with patch.object(repo, "_current_daily_start", return_value=date(2026, 2, 16)), \
             patch.object(repo, "_current_monthly_start", return_value=date(2026, 2, 1)):
            result = await repo.get_or_create(consumer_id, "acme")
        assert usage.request_count_monthly == 0
        assert usage.bandwidth_bytes_monthly == 0
        db.flush.assert_awaited_once()

    async def test_new_no_previous(self):
        db = _mock_db()
        consumer_id = uuid4()
        # First query: no today row
        mock_today = MagicMock()
        mock_today.scalar_one_or_none.return_value = None
        # Second query: no previous row
        mock_prev = MagicMock()
        mock_prev.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(side_effect=[mock_today, mock_prev])

        repo = QuotaUsageRepository(db)
        with patch.object(repo, "_current_daily_start", return_value=date(2026, 2, 16)), \
             patch.object(repo, "_current_monthly_start", return_value=date(2026, 2, 1)):
            result = await repo.get_or_create(consumer_id, "acme")
        db.add.assert_called_once()
        db.flush.assert_awaited_once()

    async def test_new_with_previous_same_month(self):
        db = _mock_db()
        consumer_id = uuid4()
        # First query: no today row
        mock_today = MagicMock()
        mock_today.scalar_one_or_none.return_value = None
        # Second query: previous row from same month
        prev = _mock_usage(
            period_start_monthly=date(2026, 2, 1),
            request_count_monthly=50,
            bandwidth_bytes_monthly=2000,
        )
        mock_prev = MagicMock()
        mock_prev.scalar_one_or_none.return_value = prev
        db.execute = AsyncMock(side_effect=[mock_today, mock_prev])

        repo = QuotaUsageRepository(db)
        with patch.object(repo, "_current_daily_start", return_value=date(2026, 2, 16)), \
             patch.object(repo, "_current_monthly_start", return_value=date(2026, 2, 1)):
            result = await repo.get_or_create(consumer_id, "acme")
        # Should have created a new usage row (db.add called)
        db.add.assert_called_once()

    async def test_new_with_previous_old_month(self):
        db = _mock_db()
        consumer_id = uuid4()
        mock_today = MagicMock()
        mock_today.scalar_one_or_none.return_value = None
        prev = _mock_usage(period_start_monthly=date(2026, 1, 1))
        mock_prev = MagicMock()
        mock_prev.scalar_one_or_none.return_value = prev
        db.execute = AsyncMock(side_effect=[mock_today, mock_prev])

        repo = QuotaUsageRepository(db)
        with patch.object(repo, "_current_daily_start", return_value=date(2026, 2, 16)), \
             patch.object(repo, "_current_monthly_start", return_value=date(2026, 2, 1)):
            result = await repo.get_or_create(consumer_id, "acme")
        db.add.assert_called_once()


# ── increment ──


class TestIncrement:
    async def test_increments(self):
        db = _mock_db()
        consumer_id = uuid4()
        usage = _mock_usage(consumer_id=consumer_id)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = usage
        # get_or_create returns existing, then increment does update
        mock_update = MagicMock()
        db.execute = AsyncMock(side_effect=[mock_result, mock_update])

        repo = QuotaUsageRepository(db)
        with patch.object(repo, "_current_daily_start", return_value=date(2026, 2, 16)), \
             patch.object(repo, "_current_monthly_start", return_value=date(2026, 2, 1)):
            result = await repo.increment(consumer_id, "acme", bandwidth_bytes=1024)
        db.refresh.assert_awaited()


# ── get_current ──


class TestGetCurrent:
    async def test_found(self):
        db = _mock_db()
        usage = _mock_usage()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = usage
        db.execute = AsyncMock(return_value=mock_result)

        repo = QuotaUsageRepository(db)
        result = await repo.get_current(uuid4(), "acme")
        assert result is usage

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        repo = QuotaUsageRepository(db)
        result = await repo.get_current(uuid4(), "acme")
        assert result is None


# ── list_by_tenant ──


class TestListByTenant:
    async def test_returns_list(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 2
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_usage(), _mock_usage()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])

        repo = QuotaUsageRepository(db)
        items, total = await repo.list_by_tenant("acme")
        assert total == 2
        assert len(items) == 2


# ── get_stats ──


class TestGetStats:
    async def test_returns_stats(self):
        db = _mock_db()
        mock_daily = MagicMock()
        mock_daily.scalar_one.return_value = 100
        mock_monthly = MagicMock()
        mock_monthly.scalar_one.return_value = 3000
        mock_top = MagicMock()
        consumer_row = MagicMock()
        consumer_row.consumer_id = uuid4()
        consumer_row.request_count_monthly = 500
        mock_top.all.return_value = [consumer_row]
        db.execute = AsyncMock(side_effect=[mock_daily, mock_monthly, mock_top])

        repo = QuotaUsageRepository(db)
        stats = await repo.get_stats("acme")
        assert stats["total_requests_today"] == 100
        assert stats["total_requests_month"] == 3000
        assert len(stats["top_consumers"]) == 1
        assert stats["near_limit"] == []


# ── reset ──


class TestReset:
    async def test_resets(self):
        db = _mock_db()
        usage = _mock_usage(
            request_count_daily=50,
            request_count_monthly=500,
            bandwidth_bytes_daily=1000,
            bandwidth_bytes_monthly=10000,
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = usage
        db.execute = AsyncMock(return_value=mock_result)

        repo = QuotaUsageRepository(db)
        result = await repo.reset(uuid4(), "acme")
        assert usage.request_count_daily == 0
        assert usage.request_count_monthly == 0
        assert usage.bandwidth_bytes_daily == 0
        assert usage.bandwidth_bytes_monthly == 0
        db.flush.assert_awaited_once()

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        repo = QuotaUsageRepository(db)
        result = await repo.reset(uuid4(), "acme")
        assert result is None
