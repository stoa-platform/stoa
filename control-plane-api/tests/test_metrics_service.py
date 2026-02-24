"""Tests for MetricsService — CAB-840

Covers:
- connect / disconnect lifecycle
- get_usage_summary (period stats, top tools, daily calls, fallback to empty)
- _get_period_stats (success_rate calculation, zero-total edge case)
- _enrich_tool_stats (per-tool enrichment)
- get_user_calls (status mapping, pagination, bad-entry skipping)
- get_active_subscriptions (Prometheus call count, DB fallback)
- get_dashboard_stats (trend calculation, zero last-week guard)
- get_dashboard_activity (ActivityType mapping, bad-entry skipping)
- _generate_empty_daily_calls (length, zero counts)
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.schemas.usage import (
    ActivityType,
    CallStatus,
    DailyCallStat,
    DashboardStats,
)
from src.services.metrics_service import MetricsService


# ========== Helpers ==========


def _make_prometheus(**overrides):
    """Build a fully-mocked PrometheusClient."""
    m = AsyncMock()
    m.connect = AsyncMock()
    m.disconnect = AsyncMock()
    m.get_request_count = AsyncMock(return_value=0)
    m.get_success_count = AsyncMock(return_value=0)
    m.get_error_count = AsyncMock(return_value=0)
    m.get_avg_latency_ms = AsyncMock(return_value=0)
    m.get_top_tools = AsyncMock(return_value=[])
    m.get_daily_calls = AsyncMock(return_value=[])
    m.get_tool_success_rate = AsyncMock(return_value=100.0)
    m.get_tool_avg_latency = AsyncMock(return_value=0)
    for k, v in overrides.items():
        setattr(m, k, v)
    return m


def _make_loki(**overrides):
    """Build a fully-mocked LokiClient."""
    m = AsyncMock()
    m.connect = AsyncMock()
    m.disconnect = AsyncMock()
    m.get_recent_calls = AsyncMock(return_value=[])
    m.get_recent_activity = AsyncMock(return_value=[])
    for k, v in overrides.items():
        setattr(m, k, v)
    return m


def _make_db_execute_result(rows):
    """Mock execute() returning rows of (sub, server) tuples."""
    result = MagicMock()
    result.all.return_value = rows
    result.scalar_one.return_value = len(rows)
    return result


def _make_mcp_sub(user_id="user-001", usage_count=0):
    sub = MagicMock()
    sub.id = uuid4()
    sub.subscriber_id = user_id
    sub.status = MagicMock()
    sub.status.value = "active"
    sub.created_at = datetime.utcnow()
    sub.last_used_at = None
    sub.usage_count = usage_count
    return sub


def _make_mcp_server(name="crm-search", display_name="CRM Search", description="Find customers"):
    server = MagicMock()
    server.name = name
    server.display_name = display_name
    server.description = description
    return server


# ========== Fixtures ==========


@pytest.fixture
def prometheus():
    return _make_prometheus()


@pytest.fixture
def loki():
    return _make_loki()


@pytest.fixture
def svc(prometheus, loki):
    return MetricsService(prometheus=prometheus, loki=loki)


@pytest.fixture
def mock_db():
    from sqlalchemy.ext.asyncio import AsyncSession

    db = AsyncMock(spec=AsyncSession)
    db.execute = AsyncMock()
    return db


# ========== connect / disconnect ==========


class TestLifecycle:
    async def test_connect_calls_both_clients(self, svc, prometheus, loki):
        await svc.connect()
        prometheus.connect.assert_awaited_once()
        loki.connect.assert_awaited_once()

    async def test_disconnect_calls_both_clients(self, svc, prometheus, loki):
        await svc.disconnect()
        prometheus.disconnect.assert_awaited_once()
        loki.disconnect.assert_awaited_once()


# ========== _generate_empty_daily_calls ==========


class TestGenerateEmptyDailyCalls:
    def test_correct_number_of_days(self, svc):
        result = svc._generate_empty_daily_calls(7)
        assert len(result) == 7

    def test_all_calls_are_zero(self, svc):
        result = svc._generate_empty_daily_calls(3)
        assert all(d.calls == 0 for d in result)

    def test_dates_are_strings_in_iso_format(self, svc):
        result = svc._generate_empty_daily_calls(5)
        for d in result:
            datetime.strptime(d.date, "%Y-%m-%d")  # Raises if format wrong

    def test_last_date_is_today(self, svc):
        result = svc._generate_empty_daily_calls(1)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        assert result[-1].date == today

    def test_one_day(self, svc):
        result = svc._generate_empty_daily_calls(1)
        assert len(result) == 1
        assert result[0].calls == 0

    def test_zero_days(self, svc):
        result = svc._generate_empty_daily_calls(0)
        assert result == []


# ========== _get_period_stats ==========


class TestGetPeriodStats:
    async def test_success_rate_when_total_zero(self, svc, prometheus):
        """Zero total → success_rate defaults to 100.0 (no division)."""
        prometheus.get_request_count = AsyncMock(return_value=0)
        prometheus.get_success_count = AsyncMock(return_value=0)
        prometheus.get_error_count = AsyncMock(return_value=0)
        prometheus.get_avg_latency_ms = AsyncMock(return_value=0)

        stats = await svc._get_period_stats("u1", "t1", "1d", "today")

        assert stats.total_calls == 0
        assert stats.success_rate == 100.0
        assert stats.period == "today"

    async def test_success_rate_calculation(self, svc, prometheus):
        """success_rate = (success / total) * 100, rounded to 1 decimal."""
        prometheus.get_request_count = AsyncMock(return_value=200)
        prometheus.get_success_count = AsyncMock(return_value=180)
        prometheus.get_error_count = AsyncMock(return_value=20)
        prometheus.get_avg_latency_ms = AsyncMock(return_value=150)

        stats = await svc._get_period_stats("u1", "t1", "7d", "week")

        assert stats.success_rate == 90.0
        assert stats.total_calls == 200
        assert stats.success_count == 180
        assert stats.error_count == 20
        assert stats.avg_latency_ms == 150

    async def test_partial_success(self, svc, prometheus):
        prometheus.get_request_count = AsyncMock(return_value=3)
        prometheus.get_success_count = AsyncMock(return_value=1)
        prometheus.get_error_count = AsyncMock(return_value=2)
        prometheus.get_avg_latency_ms = AsyncMock(return_value=300)

        stats = await svc._get_period_stats("u", "t", "30d", "month")
        assert stats.success_rate == round(1 / 3 * 100, 1)

    async def test_period_label_passed_through(self, svc, prometheus):
        prometheus.get_request_count = AsyncMock(return_value=10)
        prometheus.get_success_count = AsyncMock(return_value=10)
        prometheus.get_error_count = AsyncMock(return_value=0)
        prometheus.get_avg_latency_ms = AsyncMock(return_value=100)

        stats = await svc._get_period_stats("u", "t", "30d", "month")
        assert stats.period == "month"


# ========== _enrich_tool_stats ==========


class TestEnrichToolStats:
    async def test_enrich_empty_list(self, svc):
        result = await svc._enrich_tool_stats([], "u", "t")
        assert result == []

    async def test_enrich_single_tool(self, svc, prometheus):
        prometheus.get_tool_success_rate = AsyncMock(return_value=98.5)
        prometheus.get_tool_avg_latency = AsyncMock(return_value=120)

        tools = [{"tool_id": "crm-search", "tool_name": "CRM Search", "call_count": 100}]
        result = await svc._enrich_tool_stats(tools, "u", "t")

        assert len(result) == 1
        assert result[0].tool_id == "crm-search"
        assert result[0].tool_name == "CRM Search"
        assert result[0].call_count == 100
        assert result[0].success_rate == 98.5
        assert result[0].avg_latency_ms == 120

    async def test_enrich_tool_missing_name_uses_unknown(self, svc, prometheus):
        """Missing tool_name defaults to 'Unknown'."""
        prometheus.get_tool_success_rate = AsyncMock(return_value=100.0)
        prometheus.get_tool_avg_latency = AsyncMock(return_value=0)

        tools = [{"tool_id": "t1", "call_count": 5}]  # no tool_name
        result = await svc._enrich_tool_stats(tools, "u", "t")

        assert result[0].tool_name == "Unknown"

    async def test_enrich_multiple_tools(self, svc, prometheus):
        prometheus.get_tool_success_rate = AsyncMock(return_value=90.0)
        prometheus.get_tool_avg_latency = AsyncMock(return_value=50)

        tools = [
            {"tool_id": "t1", "tool_name": "T1", "call_count": 10},
            {"tool_id": "t2", "tool_name": "T2", "call_count": 20},
        ]
        result = await svc._enrich_tool_stats(tools, "u", "t")
        assert len(result) == 2


# ========== get_usage_summary ==========


class TestGetUsageSummary:
    async def test_summary_structure(self, svc, prometheus, loki):
        prometheus.get_request_count = AsyncMock(return_value=100)
        prometheus.get_success_count = AsyncMock(return_value=90)
        prometheus.get_error_count = AsyncMock(return_value=10)
        prometheus.get_avg_latency_ms = AsyncMock(return_value=150)
        prometheus.get_top_tools = AsyncMock(return_value=[])
        prometheus.get_daily_calls = AsyncMock(return_value=[{"date": "2026-01-01", "calls": 10}])

        summary = await svc.get_usage_summary("user-001", "acme")

        assert summary.user_id == "user-001"
        assert summary.tenant_id == "acme"
        assert summary.today.period == "today"
        assert summary.this_week.period == "week"
        assert summary.this_month.period == "month"
        assert len(summary.daily_calls) == 1
        assert summary.daily_calls[0].date == "2026-01-01"

    async def test_summary_fallback_empty_daily_calls(self, svc, prometheus):
        """When Prometheus returns no daily calls, _generate_empty_daily_calls is used."""
        prometheus.get_request_count = AsyncMock(return_value=0)
        prometheus.get_success_count = AsyncMock(return_value=0)
        prometheus.get_error_count = AsyncMock(return_value=0)
        prometheus.get_avg_latency_ms = AsyncMock(return_value=0)
        prometheus.get_top_tools = AsyncMock(return_value=[])
        prometheus.get_daily_calls = AsyncMock(return_value=[])

        summary = await svc.get_usage_summary("user-001", "acme")

        assert len(summary.daily_calls) == 7  # _generate_empty_daily_calls(7)
        assert all(d.calls == 0 for d in summary.daily_calls)

    async def test_summary_with_top_tools(self, svc, prometheus):
        prometheus.get_request_count = AsyncMock(return_value=50)
        prometheus.get_success_count = AsyncMock(return_value=50)
        prometheus.get_error_count = AsyncMock(return_value=0)
        prometheus.get_avg_latency_ms = AsyncMock(return_value=100)
        prometheus.get_top_tools = AsyncMock(
            return_value=[{"tool_id": "crm", "tool_name": "CRM", "call_count": 50}]
        )
        prometheus.get_tool_success_rate = AsyncMock(return_value=100.0)
        prometheus.get_tool_avg_latency = AsyncMock(return_value=100)
        prometheus.get_daily_calls = AsyncMock(return_value=[])

        summary = await svc.get_usage_summary("u", "t")
        assert len(summary.top_tools) == 1
        assert summary.top_tools[0].tool_id == "crm"


# ========== get_user_calls ==========


class TestGetUserCalls:
    async def test_empty_calls(self, svc, loki):
        loki.get_recent_calls = AsyncMock(return_value=[])
        result = await svc.get_user_calls("u", "t")

        assert result.calls == []
        assert result.total == 0
        assert result.limit == 20
        assert result.offset == 0

    async def test_loki_returns_none(self, svc, loki):
        """None response from loki treated as empty list."""
        loki.get_recent_calls = AsyncMock(return_value=None)
        result = await svc.get_user_calls("u", "t")
        assert result.calls == []
        assert result.total == 0

    async def test_status_mapping_success(self, svc, loki):
        loki.get_recent_calls = AsyncMock(return_value=[{
            "id": "call-1",
            "timestamp": datetime.utcnow(),
            "tool_id": "crm",
            "tool_name": "CRM",
            "status": "success",
            "latency_ms": 100,
        }])
        result = await svc.get_user_calls("u", "t")
        assert result.calls[0].status == CallStatus.SUCCESS

    async def test_status_mapping_timeout(self, svc, loki):
        loki.get_recent_calls = AsyncMock(return_value=[{
            "id": "call-2",
            "timestamp": datetime.utcnow(),
            "tool_id": "crm",
            "tool_name": "CRM",
            "status": "timeout",
            "latency_ms": 30000,
        }])
        result = await svc.get_user_calls("u", "t")
        assert result.calls[0].status == CallStatus.TIMEOUT

    async def test_status_mapping_other_becomes_error(self, svc, loki):
        loki.get_recent_calls = AsyncMock(return_value=[{
            "id": "call-3",
            "timestamp": datetime.utcnow(),
            "tool_id": "crm",
            "tool_name": "CRM",
            "status": "rate_limited",
            "latency_ms": 5,
        }])
        result = await svc.get_user_calls("u", "t")
        assert result.calls[0].status == CallStatus.ERROR

    async def test_bad_entry_skipped(self, svc, loki):
        """Entries with missing required keys are silently dropped."""
        loki.get_recent_calls = AsyncMock(return_value=[
            {"id": "good", "timestamp": datetime.utcnow(), "tool_id": "t1", "tool_name": "T1", "status": "success", "latency_ms": 50},
            {"status": "success"},  # missing required keys — should be skipped
        ])
        result = await svc.get_user_calls("u", "t")
        assert len(result.calls) == 1
        assert result.calls[0].id == "good"

    async def test_pagination_offset(self, svc, loki):
        """offset skips the first N results."""
        calls_raw = [
            {"id": f"call-{i}", "timestamp": datetime.utcnow(), "tool_id": "t", "tool_name": "T", "status": "success", "latency_ms": 10}
            for i in range(5)
        ]
        loki.get_recent_calls = AsyncMock(return_value=calls_raw)

        result = await svc.get_user_calls("u", "t", limit=2, offset=2)
        assert result.total == 5
        assert len(result.calls) == 2
        assert result.calls[0].id == "call-2"

    async def test_passes_filters_to_loki(self, svc, loki):
        """status, tool_id, from_date, to_date are forwarded to loki."""
        loki.get_recent_calls = AsyncMock(return_value=[])
        from_dt = datetime(2026, 1, 1)
        to_dt = datetime(2026, 1, 31)

        await svc.get_user_calls("u", "t", status=CallStatus.ERROR, tool_id="crm", from_date=from_dt, to_date=to_dt)

        loki.get_recent_calls.assert_awaited_once_with(
            user_id="u",
            tenant_id="t",
            limit=120,  # offset(0) + limit(20) + 100
            tool_id="crm",
            status="error",
            from_date=from_dt,
            to_date=to_dt,
        )

    async def test_error_message_optional(self, svc, loki):
        """error_message is None when not present in loki record."""
        loki.get_recent_calls = AsyncMock(return_value=[{
            "id": "c1",
            "timestamp": datetime.utcnow(),
            "tool_id": "t1",
            "tool_name": "T1",
            "status": "success",
            "latency_ms": 10,
            # no error_message key
        }])
        result = await svc.get_user_calls("u", "t")
        assert result.calls[0].error_message is None


# ========== get_active_subscriptions ==========


class TestGetActiveSubscriptions:
    async def test_empty_subscriptions(self, svc, prometheus, mock_db):
        mock_db.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))

        result = await svc.get_active_subscriptions("user-001", mock_db)
        assert result == []

    async def test_subscription_with_prometheus_count(self, svc, prometheus, mock_db):
        sub = _make_mcp_sub("user-001", usage_count=0)
        server = _make_mcp_server()
        mock_db.execute = AsyncMock(
            return_value=MagicMock(all=MagicMock(return_value=[(sub, server)]))
        )
        prometheus.get_request_count = AsyncMock(return_value=42)

        result = await svc.get_active_subscriptions("user-001", mock_db)

        assert len(result) == 1
        assert result[0].call_count_total == 42
        assert result[0].tool_id == "crm-search"
        assert result[0].tool_name == "CRM Search"

    async def test_subscription_fallback_to_db_count(self, svc, prometheus, mock_db):
        """When Prometheus returns 0, fall back to sub.usage_count."""
        sub = _make_mcp_sub("user-001", usage_count=15)
        server = _make_mcp_server()
        mock_db.execute = AsyncMock(
            return_value=MagicMock(all=MagicMock(return_value=[(sub, server)]))
        )
        prometheus.get_request_count = AsyncMock(return_value=0)

        result = await svc.get_active_subscriptions("user-001", mock_db)
        assert result[0].call_count_total == 15

    async def test_subscription_fallback_when_usage_count_none(self, svc, prometheus, mock_db):
        """usage_count=None falls back to 0."""
        sub = _make_mcp_sub("user-001")
        sub.usage_count = None
        server = _make_mcp_server()
        mock_db.execute = AsyncMock(
            return_value=MagicMock(all=MagicMock(return_value=[(sub, server)]))
        )
        prometheus.get_request_count = AsyncMock(return_value=0)

        result = await svc.get_active_subscriptions("user-001", mock_db)
        assert result[0].call_count_total == 0

    async def test_multiple_subscriptions(self, svc, prometheus, mock_db):
        pairs = [
            (_make_mcp_sub("user-001"), _make_mcp_server("t1", "Tool 1")),
            (_make_mcp_sub("user-001"), _make_mcp_server("t2", "Tool 2")),
        ]
        mock_db.execute = AsyncMock(
            return_value=MagicMock(all=MagicMock(return_value=pairs))
        )
        prometheus.get_request_count = AsyncMock(return_value=5)

        result = await svc.get_active_subscriptions("user-001", mock_db)
        assert len(result) == 2


# ========== get_dashboard_stats ==========


class TestGetDashboardStats:
    async def _make_db_for_dashboard(self, tools_count=5, subs_count=2):
        """Create a mock DB that returns scalars in two execute() calls."""
        from sqlalchemy.ext.asyncio import AsyncSession

        db = AsyncMock(spec=AsyncSession)
        tools_result = MagicMock()
        tools_result.scalar_one.return_value = tools_count
        subs_result = MagicMock()
        subs_result.scalar_one.return_value = subs_count

        db.execute = AsyncMock(side_effect=[tools_result, subs_result])
        return db

    async def test_basic_stats_structure(self, svc, prometheus):
        db = await self._make_db_for_dashboard(tools_count=10, subs_count=3)
        prometheus.get_request_count = AsyncMock(side_effect=[100, 200])  # this_week, last_two_weeks

        stats = await svc.get_dashboard_stats("u", "t", db)

        assert stats.tools_available == 10
        assert stats.active_subscriptions == 3
        assert stats.api_calls_this_week == 100

    async def test_trend_calculation(self, svc, prometheus):
        """calls_trend = (this_week - last_week) / last_week * 100."""
        db = await self._make_db_for_dashboard()
        # this_week=100, last_two_weeks=150 → last_week=50
        prometheus.get_request_count = AsyncMock(side_effect=[100, 150])

        stats = await svc.get_dashboard_stats("u", "t", db)

        # (100 - 50) / 50 * 100 = 100%
        assert stats.calls_trend == 100.0

    async def test_trend_none_when_no_last_week_calls(self, svc, prometheus):
        """calls_trend is None when last week had 0 calls (no division by zero)."""
        db = await self._make_db_for_dashboard()
        # this_week=50, last_two_weeks=50 → last_week=0
        prometheus.get_request_count = AsyncMock(side_effect=[50, 50])

        stats = await svc.get_dashboard_stats("u", "t", db)

        assert stats.calls_trend is None

    async def test_negative_trend(self, svc, prometheus):
        """Trend can be negative when calls decreased."""
        db = await self._make_db_for_dashboard()
        # this_week=40, last_two_weeks=120 → last_week=80
        prometheus.get_request_count = AsyncMock(side_effect=[40, 120])

        stats = await svc.get_dashboard_stats("u", "t", db)

        # (40 - 80) / 80 * 100 = -50%
        assert stats.calls_trend == -50.0

    async def test_tools_subscriptions_trends_are_none(self, svc, prometheus):
        """tools_trend and subscriptions_trend are always None (no historical snapshots)."""
        db = await self._make_db_for_dashboard()
        prometheus.get_request_count = AsyncMock(side_effect=[0, 0])

        stats = await svc.get_dashboard_stats("u", "t", db)

        assert stats.tools_trend is None
        assert stats.subscriptions_trend is None


# ========== get_dashboard_activity ==========


class TestGetDashboardActivity:
    async def test_empty_activity(self, svc, loki):
        loki.get_recent_activity = AsyncMock(return_value=[])
        result = await svc.get_dashboard_activity("u", "t")
        assert result == []

    async def test_none_activity_from_loki(self, svc, loki):
        """None response treated as empty list."""
        loki.get_recent_activity = AsyncMock(return_value=None)
        result = await svc.get_dashboard_activity("u", "t")
        assert result == []

    async def test_activity_type_mapping_known(self, svc, loki):
        loki.get_recent_activity = AsyncMock(return_value=[{
            "id": "act-1",
            "type": "subscription.created",
            "title": "New Subscription",
            "timestamp": datetime.utcnow(),
        }])
        result = await svc.get_dashboard_activity("u", "t")
        assert result[0].type == ActivityType.SUBSCRIPTION_CREATED

    async def test_activity_type_unknown_defaults_to_api_call(self, svc, loki):
        loki.get_recent_activity = AsyncMock(return_value=[{
            "id": "act-2",
            "type": "some.unknown.type",
            "title": "Mystery Event",
            "timestamp": datetime.utcnow(),
        }])
        result = await svc.get_dashboard_activity("u", "t")
        assert result[0].type == ActivityType.API_CALL

    async def test_bad_entry_skipped(self, svc, loki):
        """Entries missing required keys are silently dropped."""
        loki.get_recent_activity = AsyncMock(return_value=[
            {"id": "good", "type": "api.call", "title": "A call", "timestamp": datetime.utcnow()},
            {"type": "api.call"},  # missing id and title
        ])
        result = await svc.get_dashboard_activity("u", "t")
        assert len(result) == 1
        assert result[0].id == "good"

    async def test_optional_fields_are_none(self, svc, loki):
        loki.get_recent_activity = AsyncMock(return_value=[{
            "id": "act-3",
            "type": "api.call",
            "title": "A call",
            "timestamp": datetime.utcnow(),
            # no description, tool_id, tool_name
        }])
        result = await svc.get_dashboard_activity("u", "t")
        assert result[0].description is None
        assert result[0].tool_id is None
        assert result[0].tool_name is None

    async def test_limit_forwarded_to_loki(self, svc, loki):
        loki.get_recent_activity = AsyncMock(return_value=[])
        await svc.get_dashboard_activity("u", "t", limit=3)
        loki.get_recent_activity.assert_awaited_once_with(user_id="u", tenant_id="t", limit=3)

    async def test_all_activity_types(self, svc, loki):
        """All known ActivityType values can be mapped from Loki records."""
        entries = [
            {"id": f"act-{i}", "type": at.value, "title": f"T{i}", "timestamp": datetime.utcnow()}
            for i, at in enumerate(ActivityType)
        ]
        loki.get_recent_activity = AsyncMock(return_value=entries)
        result = await svc.get_dashboard_activity("u", "t", limit=len(entries))
        assert len(result) == len(list(ActivityType))
