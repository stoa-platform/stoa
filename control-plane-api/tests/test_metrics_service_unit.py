"""Unit tests for MetricsService — CAB-1378

Tests the metrics orchestration layer (Prometheus + Loki + DB).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.metrics_service import MetricsService


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
