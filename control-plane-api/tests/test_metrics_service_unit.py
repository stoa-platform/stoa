"""Unit tests for MetricsService — CAB-1378 + CAB-1560

Tests the metrics orchestration layer (Prometheus + Loki + DB).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.metrics_service import MetricsService
from src.schemas.usage import CallStatus, ActivityType


@pytest.fixture()
def mock_prom():
    """Mock Prometheus client."""
    prom = MagicMock()
    prom.connect = AsyncMock()
    prom.disconnect = AsyncMock()
    prom.get_request_count = AsyncMock(return_value=100)
    prom.get_success_count = AsyncMock(return_value=95)
    prom.get_error_count = AsyncMock(return_value=5)
    prom.get_avg_latency_ms = AsyncMock(return_value=42)
    prom.get_top_tools = AsyncMock(return_value=[])
    prom.get_daily_calls = AsyncMock(return_value=[])
    prom.get_tool_success_rate = AsyncMock(return_value=98.0)
    prom.get_tool_avg_latency = AsyncMock(return_value=35.0)
    return prom


@pytest.fixture()
def mock_loki():
    """Mock Loki client."""
    loki = MagicMock()
    loki.connect = AsyncMock()
    loki.disconnect = AsyncMock()
    return loki


@pytest.fixture()
def svc(mock_prom, mock_loki):
    return MetricsService(prometheus=mock_prom, loki=mock_loki)


class TestConnect:
    """MetricsService.connect / disconnect"""

    def test_connect_initializes_clients(self, svc, mock_prom, mock_loki):
        """Connect initializes both Prometheus and Loki."""
        import asyncio

        asyncio.get_event_loop().run_until_complete(svc.connect())

        mock_prom.connect.assert_awaited_once()
        mock_loki.connect.assert_awaited_once()

    def test_disconnect_cleans_up(self, svc, mock_prom, mock_loki):
        """Disconnect cleans up both clients."""
        import asyncio

        asyncio.get_event_loop().run_until_complete(svc.disconnect())

        mock_prom.disconnect.assert_awaited_once()
        mock_loki.disconnect.assert_awaited_once()


class TestGetPeriodStats:
    """MetricsService._get_period_stats"""

    def test_period_stats_with_data(self, svc):
        """Returns correct stats when data is available."""
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            svc._get_period_stats("user-1", "acme", "1d", "today")
        )

        assert result.total_calls == 100
        assert result.success_count == 95
        assert result.error_count == 5
        assert result.success_rate == 95.0
        assert result.avg_latency_ms == 42

    def test_period_stats_zero_calls(self, svc, mock_prom):
        """Returns 100% success rate when no calls."""
        mock_prom.get_request_count = AsyncMock(return_value=0)
        mock_prom.get_success_count = AsyncMock(return_value=0)
        mock_prom.get_error_count = AsyncMock(return_value=0)

        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            svc._get_period_stats("user-1", "acme", "1d", "today")
        )

        assert result.total_calls == 0
        assert result.success_rate == 100.0


class TestEnrichToolStats:
    """MetricsService._enrich_tool_stats"""

    def test_enriches_tools_with_metrics(self, svc):
        """Adds success rate and latency to each tool."""
        raw_tools = [
            {"tool_id": "tool-1", "tool_name": "Linear:create_issue", "call_count": 50},
        ]

        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            svc._enrich_tool_stats(raw_tools, "user-1", "acme")
        )

        assert len(result) == 1
        assert result[0].tool_id == "tool-1"
        assert result[0].call_count == 50
        assert result[0].success_rate == 98.0
        assert result[0].avg_latency_ms == 35.0

    @pytest.mark.asyncio
    async def test_enrich_empty_tools(self, svc):
        """Returns empty list for empty input."""
        result = await svc._enrich_tool_stats([], "user-1", "acme")
        assert result == []

    @pytest.mark.asyncio
    async def test_enrich_tool_missing_name(self, svc):
        """Tool without tool_name gets 'Unknown' default."""
        raw = [{"tool_id": "t-1", "call_count": 10}]
        result = await svc._enrich_tool_stats(raw, "u1", "acme")
        assert result[0].tool_name == "Unknown"


class TestGetUserCalls:
    """MetricsService.get_user_calls — Loki call history with status mapping."""

    @pytest.mark.asyncio
    async def test_success_status_mapping(self, svc, mock_loki):
        """'success' string maps to CallStatus.SUCCESS."""
        mock_loki.get_recent_calls = AsyncMock(return_value=[
            {"id": "c1", "timestamp": "2026-01-01T00:00:00Z", "tool_id": "t1",
             "tool_name": "API", "status": "success", "latency_ms": 50},
        ])
        result = await svc.get_user_calls("u1", "acme", limit=10)
        assert len(result.calls) == 1
        assert result.calls[0].status == CallStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_timeout_status_mapping(self, svc, mock_loki):
        """'timeout' string maps to CallStatus.TIMEOUT."""
        mock_loki.get_recent_calls = AsyncMock(return_value=[
            {"id": "c2", "timestamp": "2026-01-01T00:00:00Z", "tool_id": "t1",
             "tool_name": "API", "status": "timeout", "latency_ms": 5000},
        ])
        result = await svc.get_user_calls("u1", "acme")
        assert result.calls[0].status == CallStatus.TIMEOUT

    @pytest.mark.asyncio
    async def test_error_status_mapping(self, svc, mock_loki):
        """Unknown status string maps to CallStatus.ERROR."""
        mock_loki.get_recent_calls = AsyncMock(return_value=[
            {"id": "c3", "timestamp": "2026-01-01T00:00:00Z", "tool_id": "t1",
             "tool_name": "API", "status": "server_error", "latency_ms": 100,
             "error_message": "Internal error"},
        ])
        result = await svc.get_user_calls("u1", "acme")
        assert result.calls[0].status == CallStatus.ERROR
        assert result.calls[0].error_message == "Internal error"

    @pytest.mark.asyncio
    async def test_pagination_offset(self, svc, mock_loki):
        """Offset + limit slices the result correctly."""
        entries = [
            {"id": f"c{i}", "timestamp": "2026-01-01T00:00:00Z", "tool_id": "t1",
             "tool_name": "API", "status": "success", "latency_ms": 10}
            for i in range(30)
        ]
        mock_loki.get_recent_calls = AsyncMock(return_value=entries)
        result = await svc.get_user_calls("u1", "acme", limit=5, offset=10)
        assert len(result.calls) == 5
        assert result.offset == 10
        assert result.total == 30

    @pytest.mark.asyncio
    async def test_malformed_entries_skipped(self, svc, mock_loki):
        """Entries missing required keys are silently skipped."""
        mock_loki.get_recent_calls = AsyncMock(return_value=[
            {"id": "good", "timestamp": "2026-01-01T00:00:00Z", "tool_id": "t1",
             "tool_name": "API", "status": "success", "latency_ms": 10},
            {"bad": "entry"},  # missing id, timestamp, etc.
        ])
        result = await svc.get_user_calls("u1", "acme")
        assert len(result.calls) == 1
        assert result.calls[0].id == "good"

    @pytest.mark.asyncio
    async def test_none_raw_returns_empty(self, svc, mock_loki):
        """None from Loki returns empty list."""
        mock_loki.get_recent_calls = AsyncMock(return_value=None)
        result = await svc.get_user_calls("u1", "acme")
        assert result.calls == []
        assert result.total == 0


class TestGetDashboardStats:
    """MetricsService.get_dashboard_stats — DB counts + Prometheus trends."""

    @pytest.mark.asyncio
    async def test_calculates_trend(self, svc, mock_prom):
        """Trend is positive when this week > last week."""
        mock_db = AsyncMock()
        tools_result = MagicMock()
        tools_result.scalar_one.return_value = 10
        subs_result = MagicMock()
        subs_result.scalar_one.return_value = 3
        mock_db.execute = AsyncMock(side_effect=[tools_result, subs_result])

        # This week = 100, two weeks = 150 → last week = 50 → trend = +100%
        mock_prom.get_request_count = AsyncMock(side_effect=[100, 150])

        result = await svc.get_dashboard_stats("u1", "acme", mock_db)
        assert result.tools_available == 10
        assert result.active_subscriptions == 3
        assert result.api_calls_this_week == 100
        assert result.calls_trend == 100.0

    @pytest.mark.asyncio
    async def test_no_trend_when_no_previous_calls(self, svc, mock_prom):
        """Trend is None when last week had zero calls."""
        mock_db = AsyncMock()
        tools_result = MagicMock()
        tools_result.scalar_one.return_value = 5
        subs_result = MagicMock()
        subs_result.scalar_one.return_value = 0
        mock_db.execute = AsyncMock(side_effect=[tools_result, subs_result])

        # This week = 10, two weeks = 10 → last week = 0 → trend = None
        mock_prom.get_request_count = AsyncMock(side_effect=[10, 10])

        result = await svc.get_dashboard_stats("u1", "acme", mock_db)
        assert result.calls_trend is None


class TestGetDashboardActivity:
    """MetricsService.get_dashboard_activity — Loki activity feed."""

    @pytest.mark.asyncio
    async def test_maps_activity_type(self, svc, mock_loki):
        """Known activity type strings map to ActivityType enum."""
        mock_loki.get_recent_activity = AsyncMock(return_value=[
            {"id": "a1", "type": "api.call", "title": "Called API",
             "timestamp": "2026-01-01T00:00:00Z"},
        ])
        result = await svc.get_dashboard_activity("u1", "acme")
        assert len(result) == 1
        assert result[0].type == ActivityType.API_CALL

    @pytest.mark.asyncio
    async def test_unknown_type_defaults_to_api_call(self, svc, mock_loki):
        """Unknown activity type falls back to API_CALL."""
        mock_loki.get_recent_activity = AsyncMock(return_value=[
            {"id": "a2", "type": "unknown.type", "title": "Unknown",
             "timestamp": "2026-01-01T00:00:00Z"},
        ])
        result = await svc.get_dashboard_activity("u1", "acme")
        assert result[0].type == ActivityType.API_CALL

    @pytest.mark.asyncio
    async def test_malformed_entries_skipped(self, svc, mock_loki):
        """Entries missing required keys are silently dropped."""
        mock_loki.get_recent_activity = AsyncMock(return_value=[
            {"id": "good", "type": "api.call", "title": "OK",
             "timestamp": "2026-01-01T00:00:00Z"},
            {"missing": "keys"},
        ])
        result = await svc.get_dashboard_activity("u1", "acme")
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_none_raw_returns_empty(self, svc, mock_loki):
        """None from Loki returns empty list."""
        mock_loki.get_recent_activity = AsyncMock(return_value=None)
        result = await svc.get_dashboard_activity("u1", "acme")
        assert result == []


class TestGenerateEmptyDailyCalls:
    """MetricsService._generate_empty_daily_calls — fallback chart data."""

    def test_generates_correct_count(self, svc):
        """Generates exactly N days of empty stats."""
        result = svc._generate_empty_daily_calls(7)
        assert len(result) == 7
        assert all(d.calls == 0 for d in result)

    def test_dates_are_ordered(self, svc):
        """Dates are in ascending order (oldest first)."""
        result = svc._generate_empty_daily_calls(3)
        assert result[0].date < result[1].date < result[2].date
