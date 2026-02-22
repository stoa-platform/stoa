"""Tests for quota check dependency (CAB-1388)."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.dependencies.quota import (
    _get_plan_limits,
    _seconds_until_daily_reset,
    _seconds_until_monthly_reset,
    check_quota,
)


# ── _seconds_until_daily_reset ──


class TestSecondsUntilDailyReset:
    def test_returns_positive_int(self):
        result = _seconds_until_daily_reset()
        assert isinstance(result, int)
        assert 0 < result <= 86400

    def test_less_than_one_day(self):
        assert _seconds_until_daily_reset() < 86401


# ── _seconds_until_monthly_reset ──


class TestSecondsUntilMonthlyReset:
    def test_returns_positive_int(self):
        result = _seconds_until_monthly_reset()
        assert isinstance(result, int)
        assert result > 0

    def test_less_than_max_month_seconds(self):
        assert _seconds_until_monthly_reset() <= 31 * 86400

    def test_december_wraps_to_january_next_year(self):
        mock_now = datetime(2026, 12, 15, 10, 30, 0)
        with patch("src.dependencies.quota.datetime") as mock_dt:
            mock_dt.utcnow.return_value = mock_now

            result = _seconds_until_monthly_reset()

        expected = int((datetime(2027, 1, 1, 0, 0, 0) - mock_now).total_seconds())
        assert result == expected

    def test_non_december_uses_same_year(self):
        mock_now = datetime(2026, 6, 15, 12, 0, 0)
        with patch("src.dependencies.quota.datetime") as mock_dt:
            mock_dt.utcnow.return_value = mock_now

            result = _seconds_until_monthly_reset()

        expected = int((datetime(2026, 7, 1, 0, 0, 0) - mock_now).total_seconds())
        assert result == expected


# ── _get_plan_limits ──


class TestGetPlanLimits:
    async def test_returns_cached_value(self):
        db = AsyncMock()
        cached = {"daily_request_limit": 1000, "monthly_request_limit": 30000}

        with patch("src.dependencies.quota.quota_plan_cache") as mock_cache:
            mock_cache.get = AsyncMock(return_value=cached)
            result = await _get_plan_limits(uuid4(), "acme", db)

        assert result == cached
        db.execute.assert_not_called()

    async def test_returns_none_when_no_subscription(self):
        db = AsyncMock()
        sub_result = MagicMock()
        sub_result.first.return_value = None
        db.execute = AsyncMock(return_value=sub_result)

        with patch("src.dependencies.quota.quota_plan_cache") as mock_cache:
            mock_cache.get = AsyncMock(return_value=None)
            result = await _get_plan_limits(uuid4(), "acme", db)

        assert result is None

    async def test_returns_none_when_subscription_has_no_plan_id(self):
        db = AsyncMock()
        sub_row = MagicMock()
        sub_row.plan_id = None
        sub_result = MagicMock()
        sub_result.first.return_value = sub_row
        db.execute = AsyncMock(return_value=sub_result)

        with patch("src.dependencies.quota.quota_plan_cache") as mock_cache:
            mock_cache.get = AsyncMock(return_value=None)
            result = await _get_plan_limits(uuid4(), "acme", db)

        assert result is None

    async def test_returns_none_when_plan_not_found(self):
        db = AsyncMock()
        sub_row = MagicMock()
        sub_row.plan_id = uuid4()
        sub_result = MagicMock()
        sub_result.first.return_value = sub_row

        plan_result = MagicMock()
        plan_result.scalar_one_or_none.return_value = None

        db.execute = AsyncMock(side_effect=[sub_result, plan_result])

        with patch("src.dependencies.quota.quota_plan_cache") as mock_cache:
            mock_cache.get = AsyncMock(return_value=None)
            result = await _get_plan_limits(uuid4(), "acme", db)

        assert result is None

    async def test_fetches_and_caches_limits(self):
        db = AsyncMock()
        consumer_id = uuid4()

        sub_row = MagicMock()
        sub_row.plan_id = uuid4()
        sub_result = MagicMock()
        sub_result.first.return_value = sub_row

        plan = MagicMock()
        plan.daily_request_limit = 500
        plan.monthly_request_limit = 15000
        plan_result = MagicMock()
        plan_result.scalar_one_or_none.return_value = plan

        db.execute = AsyncMock(side_effect=[sub_result, plan_result])

        with patch("src.dependencies.quota.quota_plan_cache") as mock_cache:
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()
            result = await _get_plan_limits(consumer_id, "acme", db)

        assert result == {"daily_request_limit": 500, "monthly_request_limit": 15000}
        mock_cache.set.assert_awaited_once()


# ── check_quota ──


class TestCheckQuota:
    async def test_no_plan_returns_without_error(self):
        db = AsyncMock()
        with patch("src.dependencies.quota._get_plan_limits", new=AsyncMock(return_value=None)):
            await check_quota(uuid4(), "acme", db, 0)

    async def test_no_limits_defined_returns_without_error(self):
        db = AsyncMock()
        limits = {"daily_request_limit": None, "monthly_request_limit": None}
        with patch("src.dependencies.quota._get_plan_limits", new=AsyncMock(return_value=limits)):
            await check_quota(uuid4(), "acme", db, 0)

    async def test_daily_limit_exceeded_raises_429(self):
        db = AsyncMock()
        consumer_id = uuid4()
        limits = {"daily_request_limit": 100, "monthly_request_limit": None}

        usage = MagicMock()
        usage.request_count_daily = 100
        usage.request_count_monthly = 0

        with patch("src.dependencies.quota._get_plan_limits", new=AsyncMock(return_value=limits)):
            with patch("src.dependencies.quota.QuotaUsageRepository") as MockRepo:
                MockRepo.return_value.get_or_create = AsyncMock(return_value=usage)

                with pytest.raises(HTTPException) as exc_info:
                    await check_quota(consumer_id, "acme", db, 0)

        assert exc_info.value.status_code == 429
        assert exc_info.value.detail["error"] == "quota_exceeded"
        assert "Daily" in exc_info.value.detail["detail"]

    async def test_monthly_limit_exceeded_raises_429(self):
        db = AsyncMock()
        consumer_id = uuid4()
        limits = {"daily_request_limit": None, "monthly_request_limit": 1000}

        usage = MagicMock()
        usage.request_count_daily = 0
        usage.request_count_monthly = 1000

        with patch("src.dependencies.quota._get_plan_limits", new=AsyncMock(return_value=limits)):
            with patch("src.dependencies.quota.QuotaUsageRepository") as MockRepo:
                MockRepo.return_value.get_or_create = AsyncMock(return_value=usage)

                with pytest.raises(HTTPException) as exc_info:
                    await check_quota(consumer_id, "acme", db, 0)

        assert exc_info.value.status_code == 429
        assert "monthly" in exc_info.value.detail["detail"].lower()

    async def test_under_limit_increments(self):
        db = AsyncMock()
        consumer_id = uuid4()
        limits = {"daily_request_limit": 100, "monthly_request_limit": 1000}

        usage = MagicMock()
        usage.request_count_daily = 50
        usage.request_count_monthly = 500

        with patch("src.dependencies.quota._get_plan_limits", new=AsyncMock(return_value=limits)):
            with patch("src.dependencies.quota.QuotaUsageRepository") as MockRepo:
                MockRepo.return_value.get_or_create = AsyncMock(return_value=usage)
                MockRepo.return_value.increment = AsyncMock()

                await check_quota(consumer_id, "acme", db, 128)

                MockRepo.return_value.increment.assert_awaited_once_with(consumer_id, "acme", 128)

    async def test_retry_after_header_present_on_daily_exceeded(self):
        db = AsyncMock()
        limits = {"daily_request_limit": 10, "monthly_request_limit": None}

        usage = MagicMock()
        usage.request_count_daily = 10

        with patch("src.dependencies.quota._get_plan_limits", new=AsyncMock(return_value=limits)):
            with patch("src.dependencies.quota.QuotaUsageRepository") as MockRepo:
                MockRepo.return_value.get_or_create = AsyncMock(return_value=usage)

                with pytest.raises(HTTPException) as exc_info:
                    await check_quota(uuid4(), "acme", db, 0)

        assert "Retry-After" in exc_info.value.headers
