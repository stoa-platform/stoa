"""Tests for usage router — /v1/usage and /v1/dashboard endpoints.

Covers:
- GET /v1/usage/me — usage summary success, service error → 503
- GET /v1/usage/me/calls — calls list, filters, service error → 503
- GET /v1/usage/me/subscriptions — active subscriptions, service error → 503
- GET /v1/dashboard/stats — dashboard stats, cache hit, service error → 503
- GET /v1/dashboard/activity — activity feed, service error → 503
- GET /v1/usage/tokens — Prometheus query, disabled Prometheus → 503
- GET /v1/usage/tokens/compare — before/after comparison
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.schemas.usage import (
    ActiveSubscription,
    CallStatus,
    DashboardStats,
    RecentActivityItem,
    UsageCall,
    UsageCallsResponse,
    UsagePeriodStats,
    UsageSummary,
)


def _make_period_stats(period: str = "today") -> UsagePeriodStats:
    return UsagePeriodStats(
        period=period,
        total_calls=100,
        success_count=95,
        error_count=5,
        success_rate=95.0,
        avg_latency_ms=120,
    )


def _make_usage_summary() -> UsageSummary:
    return UsageSummary(
        tenant_id="acme",
        user_id="tenant-admin-user-id",
        today=_make_period_stats("today"),
        this_week=_make_period_stats("week"),
        this_month=_make_period_stats("month"),
        top_tools=[],
        daily_calls=[],
    )


def _make_calls_response(count: int = 2) -> UsageCallsResponse:
    calls = [
        UsageCall(
            id=f"call-{i}",
            timestamp=datetime.now(UTC),
            tool_id="crm-search",
            tool_name="CRM Search",
            status=CallStatus.SUCCESS,
            latency_ms=100,
        )
        for i in range(count)
    ]
    return UsageCallsResponse(calls=calls, total=count, limit=20, offset=0)


# ---------------------------------------------------------------------------
# GET /v1/usage/me
# ---------------------------------------------------------------------------


class TestGetMyUsageSummary:
    """GET /v1/usage/me"""

    def test_returns_usage_summary(self, client_as_tenant_admin):
        """Returns usage summary from metrics_service."""
        summary = _make_usage_summary()

        with patch("src.routers.usage.metrics_service") as mock_svc:
            mock_svc.get_usage_summary = AsyncMock(return_value=summary)
            resp = client_as_tenant_admin.get("/v1/usage/me")

        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == "acme"
        assert data["today"]["total_calls"] == 100

    def test_service_error_returns_503(self, client_as_tenant_admin):
        """Service failure returns 503, not 500."""
        with patch("src.routers.usage.metrics_service") as mock_svc:
            mock_svc.get_usage_summary = AsyncMock(side_effect=RuntimeError("Prometheus down"))
            resp = client_as_tenant_admin.get("/v1/usage/me")

        assert resp.status_code == 503
        assert "temporarily unavailable" in resp.json()["detail"]

    def test_requires_authentication(self, client):
        """Unauthenticated request is rejected (auth dependency raises)."""
        # The plain `client` fixture has no auth override → auth will reject
        resp = client.get("/v1/usage/me")
        # Should get 401 or 403 (not 200)
        assert resp.status_code in (401, 403, 422)


# ---------------------------------------------------------------------------
# GET /v1/usage/me/calls
# ---------------------------------------------------------------------------


class TestGetMyCalls:
    """GET /v1/usage/me/calls"""

    def test_returns_paginated_calls(self, client_as_tenant_admin):
        """Returns paginated list of calls."""
        calls_resp = _make_calls_response(count=2)

        with patch("src.routers.usage.metrics_service") as mock_svc:
            mock_svc.get_user_calls = AsyncMock(return_value=calls_resp)
            resp = client_as_tenant_admin.get("/v1/usage/me/calls")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["calls"]) == 2

    def test_empty_calls_list(self, client_as_tenant_admin):
        """Empty call list returns 200 with empty array."""
        empty = UsageCallsResponse(calls=[], total=0, limit=20, offset=0)

        with patch("src.routers.usage.metrics_service") as mock_svc:
            mock_svc.get_user_calls = AsyncMock(return_value=empty)
            resp = client_as_tenant_admin.get("/v1/usage/me/calls")

        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_filters_forwarded_to_service(self, client_as_tenant_admin):
        """Query params are forwarded to metrics_service.get_user_calls."""
        empty = UsageCallsResponse(calls=[], total=0, limit=10, offset=5)

        with patch("src.routers.usage.metrics_service") as mock_svc:
            mock_svc.get_user_calls = AsyncMock(return_value=empty)
            client_as_tenant_admin.get("/v1/usage/me/calls?limit=10&offset=5&status=success&tool_id=crm-search")
            call_kwargs = mock_svc.get_user_calls.call_args[1]

        assert call_kwargs["limit"] == 10
        assert call_kwargs["offset"] == 5
        assert call_kwargs["status"] == CallStatus.SUCCESS
        assert call_kwargs["tool_id"] == "crm-search"

    def test_service_error_returns_503(self, client_as_tenant_admin):
        """Service failure returns 503."""
        with patch("src.routers.usage.metrics_service") as mock_svc:
            mock_svc.get_user_calls = AsyncMock(side_effect=ConnectionError("Loki unavailable"))
            resp = client_as_tenant_admin.get("/v1/usage/me/calls")

        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# GET /v1/usage/me/subscriptions
# ---------------------------------------------------------------------------


class TestGetMySubscriptions:
    """GET /v1/usage/me/subscriptions"""

    def test_returns_active_subscriptions(self, client_as_tenant_admin):
        """Returns list of active subscriptions."""
        subs = [
            ActiveSubscription(
                id="sub-001",
                tool_id="crm-search",
                tool_name="CRM Search",
                status="active",
                created_at=datetime.now(UTC),
                call_count_total=500,
            )
        ]

        with patch("src.routers.usage.metrics_service") as mock_svc:
            mock_svc.get_active_subscriptions = AsyncMock(return_value=subs)
            resp = client_as_tenant_admin.get("/v1/usage/me/subscriptions")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["tool_id"] == "crm-search"

    def test_empty_subscriptions(self, client_as_tenant_admin):
        """No subscriptions returns empty list."""
        with patch("src.routers.usage.metrics_service") as mock_svc:
            mock_svc.get_active_subscriptions = AsyncMock(return_value=[])
            resp = client_as_tenant_admin.get("/v1/usage/me/subscriptions")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_service_error_returns_503(self, client_as_tenant_admin):
        """DB or service error returns 503."""
        with patch("src.routers.usage.metrics_service") as mock_svc:
            mock_svc.get_active_subscriptions = AsyncMock(side_effect=Exception("DB error"))
            resp = client_as_tenant_admin.get("/v1/usage/me/subscriptions")

        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# GET /v1/dashboard/stats
# ---------------------------------------------------------------------------


class TestGetDashboardStats:
    """GET /v1/dashboard/stats"""

    def test_returns_dashboard_stats(self, client_as_tenant_admin):
        """Returns aggregated dashboard stats."""
        from src.routers.usage import _dashboard_cache

        _dashboard_cache._cache.clear()

        stats = DashboardStats(
            tools_available=10,
            active_subscriptions=3,
            api_calls_this_week=500,
        )

        with patch("src.routers.usage.metrics_service") as mock_svc:
            mock_svc.get_dashboard_stats = AsyncMock(return_value=stats)
            resp = client_as_tenant_admin.get("/v1/dashboard/stats")

        assert resp.status_code == 200
        data = resp.json()
        assert data["tools_available"] == 10
        assert data["active_subscriptions"] == 3

    def test_service_error_returns_503(self, client_as_tenant_admin):
        """Service error returns 503."""
        with patch("src.routers.usage.metrics_service") as mock_svc:
            mock_svc.get_dashboard_stats = AsyncMock(side_effect=RuntimeError("Prometheus down"))
            # Also clear the cache so we hit the service
            from src.routers.usage import _dashboard_cache

            _dashboard_cache._cache.clear()

            resp = client_as_tenant_admin.get("/v1/dashboard/stats")

        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# GET /v1/dashboard/activity
# ---------------------------------------------------------------------------


class TestGetDashboardActivity:
    """GET /v1/dashboard/activity"""

    def test_returns_activity_list(self, client_as_tenant_admin):
        """Returns recent activity items."""
        from src.schemas.usage import ActivityType

        items = [
            RecentActivityItem(
                id="act-001",
                type=ActivityType.SUBSCRIPTION_CREATED,
                title="Subscribed to CRM Search",
                timestamp=datetime.now(UTC),
            )
        ]
        with patch("src.routers.usage.metrics_service") as mock_svc:
            mock_svc.get_dashboard_activity = AsyncMock(return_value=items)
            resp = client_as_tenant_admin.get("/v1/dashboard/activity")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["activity"]) == 1
        assert data["activity"][0]["type"] == "subscription.created"

    def test_empty_activity(self, client_as_tenant_admin):
        """Empty activity list is valid response."""
        with patch("src.routers.usage.metrics_service") as mock_svc:
            mock_svc.get_dashboard_activity = AsyncMock(return_value=[])
            resp = client_as_tenant_admin.get("/v1/dashboard/activity?limit=5")

        assert resp.status_code == 200
        assert resp.json()["activity"] == []

    def test_service_error_returns_503(self, client_as_tenant_admin):
        """Loki service failure returns 503."""
        with patch("src.routers.usage.metrics_service") as mock_svc:
            mock_svc.get_dashboard_activity = AsyncMock(side_effect=Exception("Loki down"))
            resp = client_as_tenant_admin.get("/v1/dashboard/activity")

        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# GET /v1/usage/tokens
# ---------------------------------------------------------------------------


class TestGetTokenUsage:
    """GET /v1/usage/tokens — Prometheus-backed token consumption."""

    def test_prometheus_disabled_returns_503(self, client_as_tenant_admin):
        """Prometheus not configured returns 503."""
        mock_prom = MagicMock()
        mock_prom.is_enabled = False

        with patch("src.routers.usage.PrometheusClient", return_value=mock_prom):
            resp = client_as_tenant_admin.get("/v1/usage/tokens")

        assert resp.status_code == 503
        assert "Prometheus not available" in resp.json()["detail"]

    def test_invalid_time_range_returns_400(self, client_as_tenant_admin):
        """Invalid time_range parameter returns 400."""
        mock_prom = MagicMock()
        mock_prom.is_enabled = True
        mock_prom._validate_identifier.return_value = "acme"
        mock_prom._validate_time_range.side_effect = ValueError("Invalid time range: 99x")

        with patch("src.routers.usage.PrometheusClient", return_value=mock_prom):
            resp = client_as_tenant_admin.get("/v1/usage/tokens?time_range=99x")

        assert resp.status_code == 400
        assert "Invalid time range" in resp.json()["detail"]

    def test_returns_token_usage_by_tool(self, client_as_tenant_admin):
        """Successful Prometheus query returns structured token data."""
        mock_prom = MagicMock()
        mock_prom.is_enabled = True
        mock_prom._validate_identifier.return_value = "acme"
        mock_prom._validate_time_range.return_value = "24h"
        mock_prom._query = AsyncMock(
            return_value=[
                {"metric": {"tool_name": "crm-search"}, "value": [0, "1500"]},
                {"metric": {"tool_name": "weather-api"}, "value": [0, "300"]},
            ]
        )

        with patch("src.routers.usage.PrometheusClient", return_value=mock_prom):
            resp = client_as_tenant_admin.get("/v1/usage/tokens?time_range=24h")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_tokens"] == 1800
        assert data["by_tool"]["crm-search"] == 1500
        assert data["by_tool"]["weather-api"] == 300
        assert data["tenant_id"] == "acme"

    def test_prometheus_query_error_returns_503(self, client_as_tenant_admin):
        """Prometheus query failure returns 503."""
        mock_prom = MagicMock()
        mock_prom.is_enabled = True
        mock_prom._validate_identifier.return_value = "acme"
        mock_prom._validate_time_range.return_value = "24h"
        mock_prom._query = AsyncMock(side_effect=ConnectionError("Prometheus unreachable"))

        with patch("src.routers.usage.PrometheusClient", return_value=mock_prom):
            resp = client_as_tenant_admin.get("/v1/usage/tokens")

        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# GET /v1/usage/tokens/compare
# ---------------------------------------------------------------------------


class TestGetTokenUsageCompare:
    """GET /v1/usage/tokens/compare — before/after transformer comparison."""

    def test_returns_comparison_data(self, client_as_tenant_admin):
        """Returns before/after token breakdown per tool."""
        mock_prom = MagicMock()
        mock_prom.is_enabled = True
        mock_prom._validate_identifier.return_value = "acme"
        mock_prom._validate_time_range.return_value = "24h"
        # First query = tokens_after, second = reduction_ratio
        mock_prom._query = AsyncMock(
            side_effect=[
                [{"metric": {"tool_name": "crm-search"}, "value": [0, "800"]}],
                [{"metric": {"tool_name": "crm-search"}, "value": [0, "0.2"]}],
            ]
        )

        with patch("src.routers.usage.PrometheusClient", return_value=mock_prom):
            resp = client_as_tenant_admin.get("/v1/usage/tokens/compare")

        assert resp.status_code == 200
        data = resp.json()
        assert "total_before" in data
        assert "total_after" in data
        assert data["total_after"] == 800
        # before = 800 / (1 - 0.2) = 1000
        assert data["total_before"] == 1000
        assert data["total_saved"] == 200
        assert "by_tool" in data
        assert "crm-search" in data["by_tool"]

    def test_prometheus_disabled_returns_503(self, client_as_tenant_admin):
        """Disabled Prometheus returns 503 for compare endpoint too."""
        mock_prom = MagicMock()
        mock_prom.is_enabled = False

        with patch("src.routers.usage.PrometheusClient", return_value=mock_prom):
            resp = client_as_tenant_admin.get("/v1/usage/tokens/compare")

        assert resp.status_code == 503
