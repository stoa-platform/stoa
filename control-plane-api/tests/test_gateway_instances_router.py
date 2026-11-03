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

import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import get_args
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.database import get_db
from src.models.gateway_instance import GatewayInstance, GatewayInstanceStatus, GatewayType
from src.schemas.gateway import (
    GatewayInstanceResponse,
    GatewayModeLiteral,
    GatewaySourceLiteral,
    GatewayStatusLiteral,
    GatewayTypeLiteral,
)


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
            "target_gateway_url": None,
            "public_url": None,
            "ui_url": None,
            "endpoints": {},
            "deployment_mode": "connect",
            "target_gateway_type": "kong",
            "topology": "remote-agent",
            "protected": False,
            "enabled": True,
            "visibility": None,
            "source": "self_register",
            "deleted_at": None,
            "deleted_by": None,
            "created_at": datetime(2026, 2, 1, tzinfo=UTC),
            "updated_at": datetime(2026, 2, 1, tzinfo=UTC),
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
            MockSvc.return_value.delete = AsyncMock(side_effect=ValueError("Gateway not found"))

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
            MockSvc.return_value.health_check = AsyncMock(side_effect=ValueError("Gateway not found"))

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(f"/v1/admin/gateways/{gw_id}/health")

        assert response.status_code == 404

    # ============== GET /modes/stats ==============

    def test_get_mode_stats_all_modes_present(self, app_with_cpi_admin, mock_db_session):
        """GET /modes/stats returns all 5 modes with zero counts when no data."""
        # The /modes/stats endpoint queries the DB directly (no service layer).
        # Mock db.execute to return an empty result set.
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with TestClient(app_with_cpi_admin) as client:
            response = client.get("/v1/admin/gateways/modes/stats")

        assert response.status_code == 200
        data = response.json()
        assert "modes" in data
        assert "total_gateways" in data
        assert len(data["modes"]) == 5
        mode_names = [m["mode"] for m in data["modes"]]
        assert "edge-mcp" in mode_names
        assert "sidecar" in mode_names
        assert "proxy" in mode_names
        assert "shadow" in mode_names
        assert "connect" in mode_names
        assert data["total_gateways"] == 0

    def test_get_mode_stats_with_data(self, app_with_cpi_admin, mock_db_session):
        """GET /modes/stats aggregates online/offline/degraded counts per mode."""
        row = MagicMock()
        row.mode = "edge-mcp"
        row.total = 2
        row.online = 1
        row.offline = 1
        row.degraded = 0

        mock_result = MagicMock()
        mock_result.all.return_value = [row]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with TestClient(app_with_cpi_admin) as client:
            response = client.get("/v1/admin/gateways/modes/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["total_gateways"] == 2
        edge_mcp = next(m for m in data["modes"] if m["mode"] == "edge-mcp")
        assert edge_mcp["total"] == 2
        assert edge_mcp["online"] == 1
        assert edge_mcp["offline"] == 1

    def test_get_mode_stats_tenant_admin_allowed(self, app_with_tenant_admin, mock_db_session):
        """GET /modes/stats is accessible to tenant-admin."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with TestClient(app_with_tenant_admin) as client:
            response = client.get("/v1/admin/gateways/modes/stats")

        assert response.status_code == 200

    # ============== PUT /{gateway_id} ==============

    def test_update_gateway_success(self, app_with_cpi_admin, mock_db_session):
        """PUT /{id} updates gateway configuration (200)."""
        gw_id = uuid4()
        updated = self._mock_gateway_instance(id=gw_id, display_name="Updated Gateway")

        with patch("src.routers.gateway_instances.GatewayInstanceService") as MockSvc:
            MockSvc.return_value.update = AsyncMock(return_value=updated)

            with TestClient(app_with_cpi_admin) as client:
                response = client.put(
                    f"/v1/admin/gateways/{gw_id}",
                    json={"display_name": "Updated Gateway"},
                )

        assert response.status_code == 200
        mock_db_session.commit.assert_awaited_once()

    def test_update_gateway_not_found(self, app_with_cpi_admin, mock_db_session):
        """PUT /{id} returns 404 when gateway not found."""
        with patch("src.routers.gateway_instances.GatewayInstanceService") as MockSvc:
            MockSvc.return_value.update = AsyncMock(side_effect=ValueError("Gateway instance not found"))

            with TestClient(app_with_cpi_admin) as client:
                response = client.put(f"/v1/admin/gateways/{uuid4()}", json={"display_name": "X"})

        assert response.status_code == 404

    def test_update_gateway_403_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        """PUT /{id} returns 403 for tenant-admin (cpi-admin only)."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.put(f"/v1/admin/gateways/{uuid4()}", json={"display_name": "X"})

        assert response.status_code == 403

    # ============== POST /{gateway_id}/import/preview ==============

    def test_preview_import(self, app_with_cpi_admin, mock_db_session):
        """POST /{id}/import/preview returns list of APIs to be imported (200)."""
        gateway_id = uuid4()
        preview_item = MagicMock()
        preview_item.api_id = "api-ext-001"
        preview_item.api_name = "External API"
        preview_item.tenant_id = "acme"
        preview_item.gateway_resource_id = "svc-001"
        preview_item.action = "create"
        preview_item.reason = "New API discovered"

        with patch("src.routers.gateway_instances.GatewayImportService") as MockImportSvc:
            MockImportSvc.return_value.preview_import = AsyncMock(return_value=[preview_item])

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(f"/v1/admin/gateways/{gateway_id}/import/preview")

        assert response.status_code == 200
        MockImportSvc.return_value.preview_import.assert_called_once()

    def test_preview_import_empty(self, app_with_cpi_admin, mock_db_session):
        """POST /{id}/import/preview returns empty list when no new APIs found."""
        gateway_id = uuid4()

        with patch("src.routers.gateway_instances.GatewayImportService") as MockImportSvc:
            MockImportSvc.return_value.preview_import = AsyncMock(return_value=[])

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(f"/v1/admin/gateways/{gateway_id}/import/preview")

        assert response.status_code == 200
        assert response.json() == []

    def test_preview_import_not_found(self, app_with_cpi_admin, mock_db_session):
        """POST /{id}/import/preview returns 404 when gateway not found."""
        with patch("src.routers.gateway_instances.GatewayImportService") as MockImportSvc:
            MockImportSvc.return_value.preview_import = AsyncMock(side_effect=ValueError("Gateway instance not found"))

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(f"/v1/admin/gateways/{uuid4()}/import/preview")

        assert response.status_code == 404

    def test_preview_import_403_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        """POST /{id}/import/preview returns 403 for tenant-admin (cpi-admin only)."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.post(f"/v1/admin/gateways/{uuid4()}/import/preview")

        assert response.status_code == 403

    # ============== POST /{gateway_id}/import ==============

    def test_import_from_gateway(self, app_with_cpi_admin, mock_db_session):
        """POST /{id}/import imports APIs from gateway into catalog (200)."""
        gateway_id = uuid4()
        import_result = MagicMock()
        import_result.created = 3
        import_result.skipped = 1
        import_result.errors = []
        import_result.details = []

        with patch("src.routers.gateway_instances.GatewayImportService") as MockImportSvc:
            MockImportSvc.return_value.import_from_gateway = AsyncMock(return_value=import_result)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(f"/v1/admin/gateways/{gateway_id}/import")

        assert response.status_code == 200
        MockImportSvc.return_value.import_from_gateway.assert_called_once()

    def test_import_not_found(self, app_with_cpi_admin, mock_db_session):
        """POST /{id}/import returns 404 when gateway not found."""
        with patch("src.routers.gateway_instances.GatewayImportService") as MockImportSvc:
            MockImportSvc.return_value.import_from_gateway = AsyncMock(
                side_effect=ValueError("Gateway instance not found")
            )

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(f"/v1/admin/gateways/{uuid4()}/import")

        assert response.status_code == 404

    def test_import_403_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        """POST /{id}/import returns 403 for tenant-admin (cpi-admin only)."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.post(f"/v1/admin/gateways/{uuid4()}/import")

        assert response.status_code == 403

    # ============== GET /{gateway_id} — tenant-admin allowed ==============

    def test_get_gateway_tenant_admin_allowed(self, app_with_tenant_admin, mock_db_session):
        """GET /{id} is accessible to tenant-admin."""
        instance = self._mock_gateway_instance()

        with patch("src.routers.gateway_instances.GatewayInstanceService") as MockSvc:
            MockSvc.return_value.get_by_id = AsyncMock(return_value=instance)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(f"/v1/admin/gateways/{instance.id}")

        assert response.status_code == 200

    def test_list_gateways_with_filters(self, app_with_cpi_admin, mock_db_session):
        """GET / passes all filter query params to the service."""
        with patch("src.routers.gateway_instances.GatewayInstanceService") as MockSvc:
            MockSvc.return_value.list = AsyncMock(return_value=([], 0))

            with TestClient(app_with_cpi_admin) as client:
                response = client.get(
                    "/v1/admin/gateways?gateway_type=stoa_edge_mcp&environment=dev&tenant_id=acme&page=2&page_size=10"
                )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["page"] == 2
        assert data["page_size"] == 10
        MockSvc.return_value.list.assert_called_once_with(
            gateway_type="stoa_edge_mcp",
            environment="dev",
            tenant_id="acme",
            include_deleted=False,
            page=2,
            page_size=10,
        )

    def test_health_check_tenant_admin_allowed(self, app_with_tenant_admin, mock_db_session):
        """POST /{id}/health is accessible to tenant-admin."""
        mock_result = self._mock_health_check_response()

        with patch("src.routers.gateway_instances.GatewayInstanceService") as MockSvc:
            MockSvc.return_value.health_check = AsyncMock(return_value=mock_result)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(f"/v1/admin/gateways/{uuid4()}/health")

        assert response.status_code == 200

    def test_delete_gateway_403_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        """DELETE /{id} returns 403 for tenant-admin (cpi-admin only)."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.delete(f"/v1/admin/gateways/{uuid4()}")

        assert response.status_code == 403

    # ============== CAB-1979: enabled flag ==============

    def test_update_gateway_enable_disable(self, app_with_cpi_admin, mock_db_session):
        """PUT /{id} can toggle enabled flag."""
        gw_id = uuid4()
        updated = self._mock_gateway_instance(id=gw_id, enabled=False)

        with patch("src.routers.gateway_instances.GatewayInstanceService") as MockSvc:
            MockSvc.return_value.update = AsyncMock(return_value=updated)

            with TestClient(app_with_cpi_admin) as client:
                response = client.put(
                    f"/v1/admin/gateways/{gw_id}",
                    json={"enabled": False},
                )

        assert response.status_code == 200
        assert response.json()["enabled"] is False
        MockSvc.return_value.update.assert_called_once()

    def test_update_gateway_visibility(self, app_with_cpi_admin, mock_db_session):
        """PUT /{id} can set visibility to restrict to specific tenants."""
        gw_id = uuid4()
        visibility = {"tenant_ids": ["acme", "partner-co"]}
        updated = self._mock_gateway_instance(id=gw_id, visibility=visibility)

        with patch("src.routers.gateway_instances.GatewayInstanceService") as MockSvc:
            MockSvc.return_value.update = AsyncMock(return_value=updated)

            with TestClient(app_with_cpi_admin) as client:
                response = client.put(
                    f"/v1/admin/gateways/{gw_id}",
                    json={"visibility": visibility},
                )

        assert response.status_code == 200
        assert response.json()["visibility"] == visibility

    def test_response_includes_enabled_and_visibility(self, app_with_cpi_admin, mock_db_session):
        """GET /{id} response includes enabled and visibility fields."""
        gw_id = uuid4()
        instance = self._mock_gateway_instance(id=gw_id, enabled=True, visibility={"tenant_ids": ["acme"]})

        with patch("src.routers.gateway_instances.GatewayInstanceService") as MockSvc:
            MockSvc.return_value.get_by_id = AsyncMock(return_value=instance)

            with TestClient(app_with_cpi_admin) as client:
                response = client.get(f"/v1/admin/gateways/{gw_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        assert data["visibility"] == {"tenant_ids": ["acme"]}

    # ============== CAB-1979: visibility filtering ==============

    def test_list_gateways_visibility_cpi_admin_sees_all(self, app_with_cpi_admin, mock_db_session):
        """GET / — cpi-admin sees all gateways regardless of visibility."""
        gw_public = self._mock_gateway_instance(name="gw-public", visibility=None)
        gw_restricted = self._mock_gateway_instance(name="gw-restricted", visibility={"tenant_ids": ["other-tenant"]})

        with patch("src.routers.gateway_instances.GatewayInstanceService") as MockSvc:
            MockSvc.return_value.list = AsyncMock(return_value=([gw_public, gw_restricted], 2))

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/gateways")

        assert response.status_code == 200
        assert response.json()["total"] == 2

    def test_list_gateways_visibility_tenant_admin_filtered(self, app_with_tenant_admin, mock_db_session):
        """GET / — tenant-admin only sees gateways visible to their tenant."""
        gw_public = self._mock_gateway_instance(name="gw-public", visibility=None)
        gw_for_acme = self._mock_gateway_instance(name="gw-acme", visibility={"tenant_ids": ["acme"]})
        gw_for_other = self._mock_gateway_instance(name="gw-other", visibility={"tenant_ids": ["other-tenant"]})

        with patch("src.routers.gateway_instances.GatewayInstanceService") as MockSvc:
            MockSvc.return_value.list = AsyncMock(return_value=([gw_public, gw_for_acme, gw_for_other], 3))

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/admin/gateways")

        assert response.status_code == 200
        data = response.json()
        # tenant-admin for "acme" sees gw_public (null visibility) + gw_for_acme
        assert data["total"] == 2
        names = [gw["name"] for gw in data["items"]]
        assert "gw-public" in names
        assert "gw-acme" in names
        assert "gw-other" not in names


def _drift_gateway(**overrides: object) -> GatewayInstance:
    """Build a real ORM row with explicit defaults, including before persistence."""
    return GatewayInstance(
        **{
            "id": uuid4(),
            "name": "drift-guard",
            "display_name": "Drift guard",
            "gateway_type": GatewayType.KONG,
            "environment": "test",
            "tenant_id": None,
            "base_url": "https://gateway.example.test",
            "auth_config": {},
            "status": GatewayInstanceStatus.ONLINE,
            "last_health_check": None,
            "health_details": None,
            "capabilities": [],
            "version": None,
            "tags": [],
            "mode": None,
            "protected": False,
            "enabled": True,
            "source": "self_register",
            "created_at": datetime(2026, 2, 1, tzinfo=UTC),
            "updated_at": datetime(2026, 2, 1, tzinfo=UTC),
            **overrides,
        }
    )


@pytest.fixture
async def persisted_gateway_client(
    app_with_cpi_admin: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[tuple[AsyncClient, AsyncSession], None]:
    """Exercise the real router, service and repository against an isolated database."""
    table = GatewayInstance.__table__
    for column in table.columns:
        if isinstance(column.type, JSONB):
            monkeypatch.setattr(column, "type", column.type.with_variant(JSON(), "sqlite"))
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    previous_override = app_with_cpi_admin.dependency_overrides[get_db]
    try:
        async with engine.begin() as connection:
            await connection.run_sync(table.create)
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:

            async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
                yield session

            app_with_cpi_admin.dependency_overrides[get_db] = override_get_db
            async with AsyncClient(transport=ASGITransport(app=app_with_cpi_admin), base_url="http://test") as client:
                yield client, session
    finally:
        app_with_cpi_admin.dependency_overrides[get_db] = previous_override
        await engine.dispose()


class TestGatewayLiteralDriftGuard:
    """CAB-2169: ORM enum changes must not break gateway response serialization."""

    def test_gateway_type_literal_matches_orm(self) -> None:
        assert set(get_args(GatewayTypeLiteral)) == {value.value for value in GatewayType}

    def test_gateway_status_literal_matches_orm(self) -> None:
        assert set(get_args(GatewayStatusLiteral)) == {value.value for value in GatewayInstanceStatus}

    @pytest.mark.parametrize("gateway_type", list(GatewayType))
    def test_response_accepts_every_gateway_type(self, gateway_type: GatewayType) -> None:
        response = GatewayInstanceResponse.model_validate(_drift_gateway(gateway_type=gateway_type))
        assert response.model_dump(mode="json")["gateway_type"] == gateway_type.value

    @pytest.mark.parametrize("status", list(GatewayInstanceStatus))
    def test_response_accepts_every_status(self, status: GatewayInstanceStatus) -> None:
        response = GatewayInstanceResponse.model_validate(_drift_gateway(status=status))
        assert response.model_dump(mode="json")["status"] == status.value

    @pytest.mark.parametrize("gateway_type", list(GatewayType))
    async def test_list_gateways_succeeds_for_every_gateway_type(
        self, gateway_type: GatewayType, persisted_gateway_client: tuple[AsyncClient, AsyncSession]
    ) -> None:
        client, session = persisted_gateway_client
        session.add(_drift_gateway(gateway_type=gateway_type))
        await session.commit()
        response = await client.get("/v1/admin/gateways", params={"gateway_type": gateway_type.value})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["gateway_type"] == gateway_type.value

    @pytest.mark.parametrize(
        ("field", "value", "expected"),
        [("mode", "future-mode", None), ("source", "legacy-source", "manual"), ("source", None, "manual")],
    )
    def test_unknown_values_warn_without_logging_input(
        self, field: str, value: str | None, expected: str | None, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="src.schemas.gateway"):
            response = GatewayInstanceResponse.model_validate(_drift_gateway(**{field: value}))
        assert getattr(response, field) == expected
        warnings = [record for record in caplog.records if record.name == "src.schemas.gateway"]
        assert len(warnings) == 1
        assert warnings[0].levelno == logging.WARNING
        assert field in warnings[0].getMessage()
        if value is not None:
            assert value not in warnings[0].getMessage()
        assert not warnings[0].args

    @pytest.mark.parametrize("mode", [None, *get_args(GatewayModeLiteral)])
    def test_valid_mode_is_unchanged(self, mode: str | None, caplog: pytest.LogCaptureFixture) -> None:
        response = GatewayInstanceResponse.model_validate(_drift_gateway(mode=mode))
        assert response.mode == mode
        assert not caplog.records

    @pytest.mark.parametrize("source", get_args(GatewaySourceLiteral))
    def test_valid_source_is_unchanged(self, source: str, caplog: pytest.LogCaptureFixture) -> None:
        response = GatewayInstanceResponse.model_validate(_drift_gateway(source=source))
        assert response.source == source
        assert not caplog.records

    @pytest.mark.parametrize(
        ("field", "value", "expected"),
        [("mode", "future-mode", None), ("source", "legacy-source", "manual")],
    )
    async def test_list_gateways_coerces_unknown_values(
        self, field: str, value: str, expected: str | None, persisted_gateway_client: tuple[AsyncClient, AsyncSession]
    ) -> None:
        client, session = persisted_gateway_client
        session.add_all([_drift_gateway(**{field: value}), _drift_gateway(name="valid-gateway")])
        await session.commit()
        response = await client.get("/v1/admin/gateways")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        items = {item["name"]: item for item in data["items"]}
        assert items["drift-guard"][field] == expected
        assert items["valid-gateway"][field] == (None if field == "mode" else "self_register")


@pytest.mark.parametrize("operation", ["health", "import/preview", "import"])
async def test_regression_cab_2282_gateway_admin_refuses_unavailable_secret_store(
    operation: str,
    persisted_gateway_client: tuple[AsyncClient, AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from src.features.error_snapshots.middleware import ErrorSnapshotMiddleware
    from src.services import credential_resolver
    from src.services.vault_client import VaultClient

    client, session = persisted_gateway_client
    marker = "cab-2282-synthetic-credential"
    gateway = _drift_gateway(source="manual", auth_config={"vault_path": "gateways/test", "api_key": marker})
    session.add(gateway)
    await session.commit()
    await session.refresh(gateway)
    original_state = {column.name: getattr(gateway, column.name) for column in GatewayInstance.__table__.columns}
    vault = VaultClient(vault_addr="https://vault.example.test", enabled=False)
    monkeypatch.setattr(credential_resolver, "get_vault_client", lambda: vault)
    monkeypatch.setattr(ErrorSnapshotMiddleware, "_should_skip_path", lambda *_: True)
    monkeypatch.setattr(credential_resolver.AdapterRegistry, "create", lambda *_, **__: pytest.fail("Adapter created"))
    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        response = await client.post(f"/v1/admin/gateways/{gateway.id}/{operation}")

    assert response.status_code == 503
    assert response.json() == {"detail": "Required read failed; no fallback credentials allowed; operation refused."}
    assert marker not in caplog.text
    await session.refresh(gateway)
    assert {c.name: getattr(gateway, c.name) for c in GatewayInstance.__table__.columns} == original_state
