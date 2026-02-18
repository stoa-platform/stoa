"""Tests for Business Analytics Router — CAB-1378

Endpoints:
- GET /v1/business/metrics (cpi-admin only)
- GET /v1/business/top-apis (cpi-admin only)

Also tests helper functions: _extract_scalar, _humanize_tool_name.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


class TestBusinessRouter:
    """Test suite for Business Analytics endpoints."""

    # ============== GET /metrics ==============

    def test_get_business_metrics_success(self, app_with_cpi_admin, mock_db_session):
        """GET /metrics returns business analytics for cpi-admin."""
        # Mock DB results for tenant counts
        active_result = MagicMock()
        active_result.scalar_one.return_value = 5

        new_result = MagicMock()
        new_result.scalar_one.return_value = 2

        mock_db_session.execute = AsyncMock(side_effect=[active_result, new_result])

        with patch("src.routers.business.prometheus_client") as mock_prom:
            mock_prom.is_enabled = False

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/business/metrics")

        assert response.status_code == 200
        data = response.json()
        assert data["active_tenants"] == 5
        assert data["new_tenants_30d"] == 2
        assert "tenant_growth" in data
        assert "apdex_score" in data
        assert "total_tokens" in data
        assert "total_calls" in data

    def test_get_business_metrics_with_prometheus(self, app_with_cpi_admin, mock_db_session):
        """GET /metrics includes Prometheus data when available."""
        active_result = MagicMock()
        active_result.scalar_one.return_value = 10

        new_result = MagicMock()
        new_result.scalar_one.return_value = 3

        mock_db_session.execute = AsyncMock(side_effect=[active_result, new_result])

        with patch("src.routers.business.prometheus_client") as mock_prom:
            mock_prom.is_enabled = True
            mock_prom.query = AsyncMock(side_effect=[
                {"resultType": "vector", "result": [{"value": [0, "0.95"]}]},  # apdex
                {"resultType": "vector", "result": [{"value": [0, "12345"]}]},  # tokens
                {"resultType": "vector", "result": [{"value": [0, "67890"]}]},  # calls
            ])

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/business/metrics")

        assert response.status_code == 200
        data = response.json()
        assert data["apdex_score"] == 0.95
        assert data["total_tokens"] == 12345
        assert data["total_calls"] == 67890

    def test_get_business_metrics_403_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        """GET /metrics returns 403 for tenant-admin (cpi-admin only)."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.get("/v1/business/metrics")

        assert response.status_code == 403

    def test_get_business_metrics_zero_tenants(self, app_with_cpi_admin, mock_db_session):
        """GET /metrics handles zero tenants gracefully."""
        zero_result = MagicMock()
        zero_result.scalar_one.return_value = 0

        mock_db_session.execute = AsyncMock(return_value=zero_result)

        with patch("src.routers.business.prometheus_client") as mock_prom:
            mock_prom.is_enabled = False

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/business/metrics")

        assert response.status_code == 200
        data = response.json()
        assert data["active_tenants"] == 0
        assert data["tenant_growth"] == 0.0

    # ============== GET /top-apis ==============

    def test_get_top_apis_success(self, app_with_cpi_admin):
        """GET /top-apis returns top APIs from Prometheus."""
        with patch("src.routers.business.prometheus_client") as mock_prom:
            mock_prom.is_enabled = True
            mock_prom.query = AsyncMock(return_value={
                "resultType": "vector",
                "result": [
                    {"metric": {"tool_name": "payment_api"}, "value": [0, "1000"]},
                    {"metric": {"tool_name": "order_api"}, "value": [0, "500"]},
                ],
            })

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/business/top-apis?limit=5")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["tool_name"] == "payment_api"
        assert data[0]["calls"] == 1000

    def test_get_top_apis_prometheus_disabled(self, app_with_cpi_admin):
        """GET /top-apis returns empty list when Prometheus is disabled."""
        with patch("src.routers.business.prometheus_client") as mock_prom:
            mock_prom.is_enabled = False

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/business/top-apis")

        assert response.status_code == 200
        assert response.json() == []

    def test_get_top_apis_403_tenant_admin(self, app_with_tenant_admin):
        """GET /top-apis returns 403 for non-admin roles."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.get("/v1/business/top-apis")

        assert response.status_code == 403


class TestBusinessHelpers:
    """Test helper functions directly."""

    def test_extract_scalar_valid_vector(self):
        """_extract_scalar extracts float from vector result."""
        from src.routers.business import _extract_scalar

        result = {"resultType": "vector", "result": [{"value": [0, "42.5"]}]}
        assert _extract_scalar(result) == 42.5

    def test_extract_scalar_empty_result(self):
        """_extract_scalar returns default for empty result."""
        from src.routers.business import _extract_scalar

        assert _extract_scalar(None) == 0.0
        assert _extract_scalar(None, 99.0) == 99.0

    def test_extract_scalar_nan(self):
        """_extract_scalar returns default for NaN."""
        from src.routers.business import _extract_scalar

        result = {"resultType": "vector", "result": [{"value": [0, "NaN"]}]}
        assert _extract_scalar(result, 0.92) == 0.92

    def test_humanize_tool_name(self):
        """_humanize_tool_name converts snake_case to Title Case."""
        from src.routers.business import _humanize_tool_name

        assert _humanize_tool_name("payment_api") == "Payment Api"
        assert _humanize_tool_name("mcp_order_service") == "Order Service"
        assert _humanize_tool_name("stoa_gateway_proxy") == "Gateway Proxy"
        assert _humanize_tool_name("api_users_list") == "Users List"
