"""Tests for Gateway Instances Router — CAB-1378

Endpoints:
- POST /v1/admin/gateways (cpi-admin only)
- GET /v1/admin/gateways
- GET /v1/admin/gateways/modes/stats
- GET /v1/admin/gateways/{gateway_id}
- PUT /v1/admin/gateways/{gateway_id} (cpi-admin only)
- DELETE /v1/admin/gateways/{gateway_id} (cpi-admin only)
- POST /v1/admin/gateways/{gateway_id}/health
- POST /v1/admin/gateways/{gateway_id}/import/preview (cpi-admin only)
- POST /v1/admin/gateways/{gateway_id}/import (cpi-admin only)

Auth: require_role — cpi-admin for writes, cpi-admin/tenant-admin for reads.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient


class TestGatewayInstancesRouter:
    """Test suite for Gateway Instances management endpoints."""

    def _mock_gateway_instance(self, **overrides):
        """Create a mock gateway instance matching GatewayInstanceResponse schema."""
        mock = MagicMock()
        defaults = {
            "id": uuid4(),
            "name": "kong-standalone",
            "display_name": "Kong DB-less",
            "gateway_type": "kong",
            "base_url": "https://kong.gostoa.dev",
            "status": "online",
            "environment": "production",
            "mode": None,
            "tenant_id": None,
            "last_health_check": None,
            "auth_config": {},
            "health_details": None,
            "capabilities": [],
            "version": None,
            "tags": [],
            "created_at": datetime(2026, 2, 1),
            "updated_at": datetime(2026, 2, 1),
        }
        for k, v in {**defaults, **overrides}.items():
            setattr(mock, k, v)
        return mock

    def _mock_health_check_response(self, **overrides):
        """Create a mock matching GatewayHealthCheckResponse schema."""
        mock = MagicMock()
        defaults = {
            "status": "online",
            "details": None,
            "gateway_name": "kong-standalone",
            "gateway_type": "kong",
        }
        for k, v in {**defaults, **overrides}.items():
            setattr(mock, k, v)
        return mock

    # ============== POST / (register) ==============

    def test_register_gateway_success(self, app_with_cpi_admin, mock_db_session):
        """POST / registers a new gateway instance (201)."""
        mock_instance = self._mock_gateway_instance()

        with patch("src.routers.gateway_instances.GatewayInstanceService") as MockSvc:
            MockSvc.return_value.create = AsyncMock(return_value=mock_instance)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    "/v1/admin/gateways",
                    json={
                        "name": "kong-standalone",
                        "display_name": "Kong DB-less",
                        "gateway_type": "kong",
                        "base_url": "https://kong.gostoa.dev",
                        "environment": "production",
                    },
                )

        assert response.status_code == 201
        mock_db_session.commit.assert_awaited_once()

    def test_register_gateway_400_duplicate(self, app_with_cpi_admin, mock_db_session):
        """POST / returns 400 when gateway name already exists."""
        with patch("src.routers.gateway_instances.GatewayInstanceService") as MockSvc:
            MockSvc.return_value.create = AsyncMock(
                side_effect=ValueError("Gateway with name 'kong-standalone' already exists")
            )

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    "/v1/admin/gateways",
                    json={
                        "name": "kong-standalone",
                        "display_name": "Kong",
                        "gateway_type": "kong",
                        "base_url": "https://kong.gostoa.dev",
                        "environment": "production",
                    },
                )

        assert response.status_code == 400

    def test_register_gateway_403_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        """POST / returns 403 for tenant-admin (cpi-admin only)."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.post(
                "/v1/admin/gateways",
                json={
                    "name": "test",
                    "display_name": "Test",
                    "gateway_type": "kong",
                    "base_url": "https://test.gostoa.dev",
                    "environment": "staging",
                },
            )

        assert response.status_code == 403

    # ============== GET / (list) ==============

    def test_list_gateways_success(self, app_with_cpi_admin, mock_db_session):
        """GET / returns paginated list of gateways."""
        mock_items = [self._mock_gateway_instance()]

        with patch("src.routers.gateway_instances.GatewayInstanceService") as MockSvc:
            MockSvc.return_value.list = AsyncMock(return_value=(mock_items, 1))

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/gateways")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    def test_list_gateways_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        """GET / is accessible to tenant-admin."""
        with patch("src.routers.gateway_instances.GatewayInstanceService") as MockSvc:
            MockSvc.return_value.list = AsyncMock(return_value=([], 0))

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/admin/gateways")

        assert response.status_code == 200

    # ============== GET /{gateway_id} ==============

    def test_get_gateway_success(self, app_with_cpi_admin, mock_db_session):
        """GET /{id} returns gateway details."""
        gw_id = uuid4()
        mock_instance = self._mock_gateway_instance(id=gw_id)

        with patch("src.routers.gateway_instances.GatewayInstanceService") as MockSvc:
            MockSvc.return_value.get_by_id = AsyncMock(return_value=mock_instance)

            with TestClient(app_with_cpi_admin) as client:
                response = client.get(f"/v1/admin/gateways/{gw_id}")

        assert response.status_code == 200

    def test_get_gateway_404(self, app_with_cpi_admin, mock_db_session):
        """GET /{id} returns 404 when gateway not found."""
        gw_id = uuid4()

        with patch("src.routers.gateway_instances.GatewayInstanceService") as MockSvc:
            MockSvc.return_value.get_by_id = AsyncMock(return_value=None)

            with TestClient(app_with_cpi_admin) as client:
                response = client.get(f"/v1/admin/gateways/{gw_id}")

        assert response.status_code == 404

    # ============== DELETE /{gateway_id} ==============

    def test_delete_gateway_success(self, app_with_cpi_admin, mock_db_session):
        """DELETE /{id} removes gateway (204)."""
        gw_id = uuid4()

        with patch("src.routers.gateway_instances.GatewayInstanceService") as MockSvc:
            MockSvc.return_value.delete = AsyncMock()

            with TestClient(app_with_cpi_admin) as client:
                response = client.delete(f"/v1/admin/gateways/{gw_id}")

        assert response.status_code == 204
        mock_db_session.commit.assert_awaited_once()

    def test_delete_gateway_404(self, app_with_cpi_admin, mock_db_session):
        """DELETE /{id} returns 404 when gateway not found."""
        gw_id = uuid4()

        with patch("src.routers.gateway_instances.GatewayInstanceService") as MockSvc:
            MockSvc.return_value.delete = AsyncMock(
                side_effect=ValueError("Gateway not found")
            )

            with TestClient(app_with_cpi_admin) as client:
                response = client.delete(f"/v1/admin/gateways/{gw_id}")

        assert response.status_code == 404

    # ============== POST /{gateway_id}/health ==============

    def test_health_check_success(self, app_with_cpi_admin, mock_db_session):
        """POST /{id}/health triggers health check."""
        gw_id = uuid4()
        mock_result = self._mock_health_check_response()

        with patch("src.routers.gateway_instances.GatewayInstanceService") as MockSvc:
            MockSvc.return_value.health_check = AsyncMock(return_value=mock_result)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(f"/v1/admin/gateways/{gw_id}/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "online"

    def test_health_check_404(self, app_with_cpi_admin, mock_db_session):
        """POST /{id}/health returns 404 when gateway not found."""
        gw_id = uuid4()

        with patch("src.routers.gateway_instances.GatewayInstanceService") as MockSvc:
            MockSvc.return_value.health_check = AsyncMock(
                side_effect=ValueError("Gateway not found")
            )

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(f"/v1/admin/gateways/{gw_id}/health")

        assert response.status_code == 404
