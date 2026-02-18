"""Tests for Gateway Observability Router — CAB-1378

Endpoints:
- GET /v1/admin/gateways/metrics
- GET /v1/admin/gateways/health-summary
- GET /v1/admin/gateways/{gateway_id}/metrics

RBAC: require_role(["cpi-admin", "tenant-admin"])
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import Depends
from fastapi.testclient import TestClient


class TestGatewayObservabilityRouter:
    """Test suite for Gateway Observability endpoints."""

    # ============== GET /metrics ==============

    def test_get_aggregated_metrics_success(self, app_with_cpi_admin, mock_db_session):
        """GET /metrics returns aggregated metrics for cpi-admin."""
        mock_metrics = {
            "health": {"online": 2, "offline": 0, "total_gateways": 2, "health_percentage": 100.0},
            "sync": {"synced": 5, "total_deployments": 5, "sync_percentage": 100.0},
            "overall_status": "healthy",
        }

        with patch("src.routers.gateway_observability.GatewayMetricsService") as MockSvc:
            MockSvc.return_value.get_aggregated_metrics = AsyncMock(return_value=mock_metrics)

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/gateways/metrics")

        assert response.status_code == 200
        data = response.json()
        assert data["overall_status"] == "healthy"
        assert data["health"]["total_gateways"] == 2

    def test_get_aggregated_metrics_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        """GET /metrics is also accessible to tenant-admin."""
        mock_metrics = {
            "health": {"online": 1, "total_gateways": 1, "health_percentage": 100.0},
            "sync": {"synced": 3, "total_deployments": 3, "sync_percentage": 100.0},
            "overall_status": "healthy",
        }

        with patch("src.routers.gateway_observability.GatewayMetricsService") as MockSvc:
            MockSvc.return_value.get_aggregated_metrics = AsyncMock(return_value=mock_metrics)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/admin/gateways/metrics")

        assert response.status_code == 200

    def test_get_aggregated_metrics_403_viewer(self, app, mock_db_session):
        """GET /metrics returns 403 for viewer role."""
        from src.auth.dependencies import get_current_user
        from src.database import get_db

        viewer = MagicMock()
        viewer.id = "viewer-id"
        viewer.email = "viewer@acme.com"
        viewer.username = "viewer"
        viewer.roles = ["viewer"]
        viewer.tenant_id = "acme"

        app.dependency_overrides[get_current_user] = lambda: viewer
        app.dependency_overrides[get_db] = lambda: mock_db_session

        with TestClient(app) as client:
            response = client.get("/v1/admin/gateways/metrics")

        assert response.status_code == 403
        app.dependency_overrides.clear()

    # ============== GET /health-summary ==============

    def test_get_health_summary_success(self, app_with_cpi_admin, mock_db_session):
        """GET /health-summary returns gateway status counts."""
        mock_summary = {
            "online": 3,
            "offline": 1,
            "degraded": 0,
            "maintenance": 0,
            "total_gateways": 4,
            "health_percentage": 75.0,
        }

        with patch("src.routers.gateway_observability.GatewayMetricsService") as MockSvc:
            MockSvc.return_value.get_health_summary = AsyncMock(return_value=mock_summary)

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/gateways/health-summary")

        assert response.status_code == 200
        data = response.json()
        assert data["total_gateways"] == 4
        assert data["health_percentage"] == 75.0

    # ============== GET /{gateway_id}/metrics ==============

    def test_get_gateway_metrics_success(self, app_with_cpi_admin, mock_db_session):
        """GET /{gateway_id}/metrics returns per-gateway metrics."""
        gw_id = uuid4()
        mock_gw_metrics = {
            "gateway_id": str(gw_id),
            "name": "kong-standalone",
            "display_name": "Kong DB-less",
            "gateway_type": "kong",
            "status": "online",
            "last_health_check": "2026-02-18T10:00:00",
            "sync": {"synced": 5, "total_deployments": 5, "sync_percentage": 100.0},
            "recent_errors": [],
        }

        with patch("src.routers.gateway_observability.GatewayMetricsService") as MockSvc:
            MockSvc.return_value.get_gateway_metrics = AsyncMock(return_value=mock_gw_metrics)

            with TestClient(app_with_cpi_admin) as client:
                response = client.get(f"/v1/admin/gateways/{gw_id}/metrics")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "kong-standalone"
        assert data["status"] == "online"

    def test_get_gateway_metrics_404(self, app_with_cpi_admin, mock_db_session):
        """GET /{gateway_id}/metrics returns 404 when gateway not found."""
        gw_id = uuid4()

        with patch("src.routers.gateway_observability.GatewayMetricsService") as MockSvc:
            MockSvc.return_value.get_gateway_metrics = AsyncMock(return_value=None)

            with TestClient(app_with_cpi_admin) as client:
                response = client.get(f"/v1/admin/gateways/{gw_id}/metrics")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_gateway_metrics_invalid_uuid(self, app_with_cpi_admin, mock_db_session):
        """GET /{gateway_id}/metrics returns 422 for invalid UUID."""
        with TestClient(app_with_cpi_admin) as client:
            response = client.get("/v1/admin/gateways/not-a-uuid/metrics")

        assert response.status_code == 422
