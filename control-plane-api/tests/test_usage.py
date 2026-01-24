"""
Tests for Usage Router and Metrics Services - CAB-840

Tests cover:
1. Router endpoint responses with mocked services
2. Graceful degradation when services unavailable
3. Pagination and filtering
4. Prometheus client query handling
5. Loki client log parsing
"""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.schemas.usage import (
    UsageSummary,
    UsagePeriodStats,
    ToolUsageStat,
    DailyCallStat,
    UsageCallsResponse,
    UsageCall,
    ActiveSubscription,
    DashboardStats,
    DashboardActivityResponse,
    RecentActivityItem,
    CallStatus,
    ActivityType,
)


class TestUsageRouter:
    """Test suite for Usage Router endpoints."""

    # ============== GET /v1/usage/me ==============

    def test_get_usage_summary_success(self, app_with_tenant_admin, mock_db_session):
        """Test usage summary returns valid data."""
        mock_summary = UsageSummary(
            tenant_id="acme",
            user_id="tenant-admin-user-id",
            today=UsagePeriodStats(
                period="today",
                total_calls=100,
                success_count=95,
                error_count=5,
                success_rate=95.0,
                avg_latency_ms=150
            ),
            this_week=UsagePeriodStats(
                period="week",
                total_calls=500,
                success_count=480,
                error_count=20,
                success_rate=96.0,
                avg_latency_ms=140
            ),
            this_month=UsagePeriodStats(
                period="month",
                total_calls=2000,
                success_count=1950,
                error_count=50,
                success_rate=97.5,
                avg_latency_ms=135
            ),
            top_tools=[],
            daily_calls=[],
        )

        with patch("src.routers.usage.metrics_service") as mock_service:
            mock_service.get_usage_summary = AsyncMock(return_value=mock_summary)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/usage/me")

            assert response.status_code == 200
            data = response.json()
            assert "today" in data
            assert "this_week" in data
            assert "this_month" in data
            assert data["tenant_id"] == "acme"
            assert data["today"]["total_calls"] == 100

    def test_get_usage_summary_service_unavailable(self, app_with_tenant_admin):
        """Test usage summary returns 503 when service fails."""
        with patch("src.routers.usage.metrics_service") as mock_service:
            mock_service.get_usage_summary = AsyncMock(
                side_effect=Exception("Prometheus connection failed")
            )

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/usage/me")

            assert response.status_code == 503
            assert "unavailable" in response.json()["detail"]

    # ============== GET /v1/usage/me/calls ==============

    def test_get_calls_success(self, app_with_tenant_admin):
        """Test calls endpoint returns paginated call list."""
        mock_response = UsageCallsResponse(
            calls=[
                UsageCall(
                    id="call-0001",
                    timestamp=datetime.utcnow(),
                    tool_id="crm-search",
                    tool_name="CRM Search",
                    status=CallStatus.SUCCESS,
                    latency_ms=150,
                    error_message=None,
                )
            ],
            total=1,
            limit=20,
            offset=0,
        )

        with patch("src.routers.usage.metrics_service") as mock_service:
            mock_service.get_user_calls = AsyncMock(return_value=mock_response)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/usage/me/calls")

            assert response.status_code == 200
            data = response.json()
            assert "calls" in data
            assert data["total"] == 1
            assert len(data["calls"]) == 1

    def test_get_calls_with_pagination(self, app_with_tenant_admin):
        """Test calls endpoint respects pagination parameters."""
        mock_response = UsageCallsResponse(
            calls=[],
            total=100,
            limit=20,
            offset=40,
        )

        with patch("src.routers.usage.metrics_service") as mock_service:
            mock_service.get_user_calls = AsyncMock(return_value=mock_response)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/usage/me/calls?limit=20&offset=40")

            assert response.status_code == 200
            mock_service.get_user_calls.assert_called_once()
            # Check pagination params were passed
            call_args = mock_service.get_user_calls.call_args
            assert call_args.kwargs["limit"] == 20
            assert call_args.kwargs["offset"] == 40

    def test_get_calls_with_filters(self, app_with_tenant_admin):
        """Test calls endpoint accepts filter parameters."""
        mock_response = UsageCallsResponse(
            calls=[],
            total=10,
            limit=20,
            offset=0,
        )

        with patch("src.routers.usage.metrics_service") as mock_service:
            mock_service.get_user_calls = AsyncMock(return_value=mock_response)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/usage/me/calls?status=error&tool_id=test-tool")

            assert response.status_code == 200
            call_args = mock_service.get_user_calls.call_args
            assert call_args.kwargs["status"] == CallStatus.ERROR
            assert call_args.kwargs["tool_id"] == "test-tool"

    def test_get_calls_service_unavailable(self, app_with_tenant_admin):
        """Test calls endpoint returns 503 when service fails."""
        with patch("src.routers.usage.metrics_service") as mock_service:
            mock_service.get_user_calls = AsyncMock(
                side_effect=Exception("Loki connection failed")
            )

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/usage/me/calls")

            assert response.status_code == 503

    # ============== GET /v1/usage/me/subscriptions ==============

    def test_get_subscriptions_success(self, app_with_tenant_admin, mock_db_session):
        """Test subscriptions endpoint returns active subscriptions."""
        mock_subs = [
            ActiveSubscription(
                id="sub-001",
                tool_id="crm-search",
                tool_name="CRM Search",
                tool_description="Search customers in CRM",
                status="active",
                created_at=datetime.utcnow() - timedelta(days=30),
                last_used_at=datetime.utcnow() - timedelta(hours=1),
                call_count_total=1250,
            )
        ]

        with patch("src.routers.usage.metrics_service") as mock_service:
            mock_service.get_active_subscriptions = AsyncMock(return_value=mock_subs)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/usage/me/subscriptions")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["tool_id"] == "crm-search"

    def test_get_subscriptions_empty(self, app_with_tenant_admin, mock_db_session):
        """Test subscriptions endpoint returns empty list when no subscriptions."""
        with patch("src.routers.usage.metrics_service") as mock_service:
            mock_service.get_active_subscriptions = AsyncMock(return_value=[])

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/usage/me/subscriptions")

            assert response.status_code == 200
            assert response.json() == []

    # ============== GET /v1/dashboard/stats ==============

    def test_get_dashboard_stats_success(self, app_with_tenant_admin, mock_db_session):
        """Test dashboard stats returns aggregated data."""
        mock_stats = DashboardStats(
            tools_available=10,
            active_subscriptions=5,
            api_calls_this_week=500,
            tools_trend=None,
            subscriptions_trend=None,
            calls_trend=15.5,
        )

        with patch("src.routers.usage.metrics_service") as mock_service:
            mock_service.get_dashboard_stats = AsyncMock(return_value=mock_stats)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/dashboard/stats")

            assert response.status_code == 200
            data = response.json()
            assert data["tools_available"] == 10
            assert data["api_calls_this_week"] == 500

    # ============== GET /v1/dashboard/activity ==============

    def test_get_dashboard_activity_success(self, app_with_tenant_admin):
        """Test dashboard activity returns recent items."""
        mock_activity = [
            RecentActivityItem(
                id="act-001",
                type=ActivityType.SUBSCRIPTION_CREATED,
                title="Subscribed to CRM Search",
                description="New subscription created",
                tool_id="crm-search",
                tool_name="CRM Search",
                timestamp=datetime.utcnow(),
            )
        ]

        with patch("src.routers.usage.metrics_service") as mock_service:
            mock_service.get_dashboard_activity = AsyncMock(return_value=mock_activity)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/dashboard/activity?limit=10")

            assert response.status_code == 200
            data = response.json()
            assert "activity" in data
            assert len(data["activity"]) == 1

    def test_get_dashboard_activity_empty(self, app_with_tenant_admin):
        """Test dashboard activity returns empty list when no activity."""
        with patch("src.routers.usage.metrics_service") as mock_service:
            mock_service.get_dashboard_activity = AsyncMock(return_value=[])

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/dashboard/activity")

            assert response.status_code == 200
            assert response.json()["activity"] == []


class TestPrometheusClient:
    """Unit tests for Prometheus client."""

    @pytest.mark.asyncio
    async def test_query_success(self):
        """Test successful PromQL query."""
        from src.services.prometheus_client import PrometheusClient

        client = PrometheusClient()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [{"value": [1234567890, "100"]}]
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_httpx:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_httpx.return_value = mock_client_instance

            result = await client.query("test_query")

            assert result is not None
            assert result["resultType"] == "vector"

    @pytest.mark.asyncio
    async def test_query_timeout(self):
        """Test graceful handling of timeout."""
        from src.services.prometheus_client import PrometheusClient
        import httpx

        client = PrometheusClient()

        with patch("httpx.AsyncClient") as mock_httpx:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(
                side_effect=httpx.TimeoutException("timeout")
            )
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_httpx.return_value = mock_client_instance

            result = await client.query("test_query")

            assert result is None  # Graceful degradation

    @pytest.mark.asyncio
    async def test_query_disabled(self):
        """Test query returns None when client is disabled."""
        from src.services.prometheus_client import PrometheusClient

        with patch("src.services.prometheus_client.settings") as mock_settings:
            mock_settings.PROMETHEUS_INTERNAL_URL = "http://prometheus:9090"
            mock_settings.PROMETHEUS_TIMEOUT_SECONDS = 30
            mock_settings.PROMETHEUS_ENABLED = False

            client = PrometheusClient()
            result = await client.query("test_query")

            assert result is None

    @pytest.mark.asyncio
    async def test_extract_scalar(self):
        """Test scalar extraction from Prometheus result."""
        from src.services.prometheus_client import PrometheusClient

        client = PrometheusClient()

        # Test vector result
        result = {"resultType": "vector", "result": [{"value": [0, "42"]}]}
        assert client._extract_scalar(result) == 42

        # Test empty result
        assert client._extract_scalar(None) == 0
        assert client._extract_scalar({}) == 0

        # Test NaN handling
        result_nan = {"resultType": "vector", "result": [{"value": [0, "NaN"]}]}
        assert client._extract_scalar(result_nan) == 0


class TestLokiClient:
    """Unit tests for Loki client."""

    @pytest.mark.asyncio
    async def test_query_range_success(self):
        """Test successful LogQL query."""
        from src.services.loki_client import LokiClient

        client = LokiClient()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "result": [
                    {
                        "stream": {"job": "mcp-gateway"},
                        "values": [
                            ["1234567890000000000", '{"request_id":"call-001","status":"success"}']
                        ]
                    }
                ]
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_httpx:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_httpx.return_value = mock_client_instance

            result = await client.query_range(
                "{job='test'}",
                datetime.utcnow() - timedelta(hours=1),
                datetime.utcnow()
            )

            assert result is not None
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_query_range_timeout(self):
        """Test graceful handling of timeout."""
        from src.services.loki_client import LokiClient
        import httpx

        client = LokiClient()

        with patch("httpx.AsyncClient") as mock_httpx:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(
                side_effect=httpx.TimeoutException("timeout")
            )
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_httpx.return_value = mock_client_instance

            result = await client.query_range(
                "{job='test'}",
                datetime.utcnow() - timedelta(hours=1),
                datetime.utcnow()
            )

            assert result is None  # Graceful degradation

    def test_format_call_entries(self):
        """Test formatting of log entries to call objects."""
        from src.services.loki_client import LokiClient

        client = LokiClient()

        entries = [
            {
                "timestamp": datetime.utcnow(),
                "raw": '{"request_id":"call-001","tool_id":"crm","tool_name":"CRM","status":"success","duration_ms":150}',
            }
        ]

        calls = client._format_call_entries(entries)

        assert len(calls) == 1
        assert calls[0]["id"] == "call-001"
        assert calls[0]["status"] == "success"
        assert calls[0]["latency_ms"] == 150

    def test_format_call_entries_invalid_json(self):
        """Test handling of invalid JSON in log entries."""
        from src.services.loki_client import LokiClient

        client = LokiClient()

        entries = [
            {"timestamp": datetime.utcnow(), "raw": "invalid json"},
            {"timestamp": datetime.utcnow(), "raw": '{"valid":"json"}'},
        ]

        calls = client._format_call_entries(entries)

        # Invalid JSON entries are skipped, valid JSON with missing fields uses defaults
        assert len(calls) == 1
        assert calls[0]["tool_id"] == "unknown"  # Default for missing field
        assert calls[0]["status"] == "success"  # Default for missing field


class TestMetricsService:
    """Unit tests for MetricsService orchestration layer."""

    @pytest.mark.asyncio
    async def test_get_usage_summary(self):
        """Test usage summary aggregation."""
        from src.services.metrics_service import MetricsService

        mock_prometheus = MagicMock()
        mock_prometheus.get_request_count = AsyncMock(return_value=100)
        mock_prometheus.get_success_count = AsyncMock(return_value=95)
        mock_prometheus.get_error_count = AsyncMock(return_value=5)
        mock_prometheus.get_avg_latency_ms = AsyncMock(return_value=150)
        mock_prometheus.get_top_tools = AsyncMock(return_value=[])
        mock_prometheus.get_daily_calls = AsyncMock(return_value=[])
        mock_prometheus.get_tool_success_rate = AsyncMock(return_value=98.0)
        mock_prometheus.get_tool_avg_latency = AsyncMock(return_value=120)

        mock_loki = MagicMock()

        service = MetricsService(prometheus=mock_prometheus, loki=mock_loki)

        result = await service.get_usage_summary("user-123", "tenant-abc")

        assert result.tenant_id == "tenant-abc"
        assert result.user_id == "user-123"
        assert result.today.total_calls == 100
        assert result.today.success_rate == 95.0

    @pytest.mark.asyncio
    async def test_get_user_calls(self):
        """Test call history retrieval."""
        from src.services.metrics_service import MetricsService

        mock_prometheus = MagicMock()
        mock_loki = MagicMock()
        mock_loki.get_recent_calls = AsyncMock(return_value=[
            {
                "id": "call-001",
                "timestamp": datetime.utcnow(),
                "tool_id": "crm",
                "tool_name": "CRM",
                "status": "success",
                "latency_ms": 150,
                "error_message": None,
            }
        ])

        service = MetricsService(prometheus=mock_prometheus, loki=mock_loki)

        result = await service.get_user_calls(
            user_id="user-123",
            tenant_id="tenant-abc",
            limit=20,
            offset=0,
        )

        assert result.total == 1
        assert len(result.calls) == 1
        assert result.calls[0].id == "call-001"

    @pytest.mark.asyncio
    async def test_generate_empty_daily_calls(self):
        """Test fallback generation of empty daily stats."""
        from src.services.metrics_service import MetricsService

        service = MetricsService()
        result = service._generate_empty_daily_calls(7)

        assert len(result) == 7
        for stat in result:
            assert stat.calls == 0
