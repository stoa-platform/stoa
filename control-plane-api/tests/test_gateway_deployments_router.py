"""Tests for gateway deployments router — /v1/admin/deployments"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

SVC_PATH = "src.routers.gateway_deployments.GatewayDeploymentService"
REPO_PATH = "src.routers.gateway_deployments.GatewayDeploymentRepository"


def _mock_deployment(**overrides):
    """Build a mock deployment object matching GatewayDeploymentResponse schema."""
    dep = MagicMock()
    dep.id = overrides.get("id", uuid4())
    dep.api_catalog_id = overrides.get("api_catalog_id", uuid4())
    dep.gateway_instance_id = overrides.get("gateway_instance_id", uuid4())
    dep.desired_state = overrides.get("desired_state", {"spec": {}})
    dep.desired_at = overrides.get("desired_at", "2026-01-01T00:00:00")
    dep.actual_state = overrides.get("actual_state")
    dep.actual_at = overrides.get("actual_at")
    dep.sync_status = overrides.get("sync_status", "pending")
    dep.last_sync_attempt = overrides.get("last_sync_attempt")
    dep.last_sync_success = overrides.get("last_sync_success")
    dep.sync_error = overrides.get("sync_error")
    dep.sync_attempts = overrides.get("sync_attempts", 0)
    dep.gateway_resource_id = overrides.get("gateway_resource_id")
    dep.created_at = overrides.get("created_at", "2026-01-01T00:00:00")
    dep.updated_at = overrides.get("updated_at", "2026-01-01T00:00:00")
    return dep


class TestDeployAPI:
    def test_deploy_success(self, client_as_cpi_admin, mock_db_session):
        dep = _mock_deployment()
        with patch(SVC_PATH) as MockSvc:
            instance = MockSvc.return_value
            instance.deploy_api = AsyncMock(return_value=[dep])
            resp = client_as_cpi_admin.post(
                "/v1/admin/deployments",
                json={
                    "api_catalog_id": str(uuid4()),
                    "gateway_instance_ids": [str(uuid4())],
                },
            )

        assert resp.status_code == 201

    def test_deploy_not_found(self, client_as_cpi_admin, mock_db_session):
        with patch(SVC_PATH) as MockSvc:
            instance = MockSvc.return_value
            instance.deploy_api = AsyncMock(side_effect=ValueError("API not found"))
            resp = client_as_cpi_admin.post(
                "/v1/admin/deployments",
                json={
                    "api_catalog_id": str(uuid4()),
                    "gateway_instance_ids": [str(uuid4())],
                },
            )

        assert resp.status_code == 404

    def test_deploy_forbidden_for_tenant_admin(self, client_as_tenant_admin):
        resp = client_as_tenant_admin.post(
            "/v1/admin/deployments",
            json={
                "api_catalog_id": str(uuid4()),
                "gateway_instance_ids": [str(uuid4())],
            },
        )
        assert resp.status_code == 403


class TestListDeployments:
    def test_list_returns_paginated(self, client_as_cpi_admin, mock_db_session):
        dep = _mock_deployment()
        with patch(REPO_PATH) as MockRepo:
            instance = MockRepo.return_value
            instance.list_all = AsyncMock(return_value=([dep], 1))
            resp = client_as_cpi_admin.get("/v1/admin/deployments")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["page"] == 1

    def test_list_allowed_for_tenant_admin(self, client_as_tenant_admin, mock_db_session):
        with patch(REPO_PATH) as MockRepo:
            instance = MockRepo.return_value
            instance.list_all = AsyncMock(return_value=([], 0))
            resp = client_as_tenant_admin.get("/v1/admin/deployments")

        assert resp.status_code == 200

    def test_list_forbidden_for_viewer(self, client_as_no_tenant_user):
        resp = client_as_no_tenant_user.get("/v1/admin/deployments")
        assert resp.status_code == 403


class TestGetDeploymentStatus:
    def test_status_summary(self, client_as_cpi_admin, mock_db_session):
        counts = {"pending": 2, "synced": 5, "failed": 1}
        with patch(REPO_PATH) as MockRepo:
            instance = MockRepo.return_value
            instance.get_status_summary = AsyncMock(return_value=counts)
            resp = client_as_cpi_admin.get("/v1/admin/deployments/status")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 8


class TestGetSingleDeployment:
    def test_get_success(self, client_as_cpi_admin, mock_db_session):
        dep = _mock_deployment()
        with patch(REPO_PATH) as MockRepo:
            instance = MockRepo.return_value
            instance.get_by_id = AsyncMock(return_value=dep)
            resp = client_as_cpi_admin.get(f"/v1/admin/deployments/{uuid4()}")

        assert resp.status_code == 200

    def test_get_not_found(self, client_as_cpi_admin, mock_db_session):
        with patch(REPO_PATH) as MockRepo:
            instance = MockRepo.return_value
            instance.get_by_id = AsyncMock(return_value=None)
            resp = client_as_cpi_admin.get(f"/v1/admin/deployments/{uuid4()}")

        assert resp.status_code == 404


class TestUndeploy:
    def test_undeploy_success(self, client_as_cpi_admin, mock_db_session):
        with patch(SVC_PATH) as MockSvc:
            instance = MockSvc.return_value
            instance.undeploy = AsyncMock(return_value=None)
            resp = client_as_cpi_admin.delete(f"/v1/admin/deployments/{uuid4()}")

        assert resp.status_code == 204

    def test_undeploy_not_found(self, client_as_cpi_admin, mock_db_session):
        with patch(SVC_PATH) as MockSvc:
            instance = MockSvc.return_value
            instance.undeploy = AsyncMock(side_effect=ValueError("Not found"))
            resp = client_as_cpi_admin.delete(f"/v1/admin/deployments/{uuid4()}")

        assert resp.status_code == 404


class TestForceSync:
    def test_force_sync_success(self, client_as_cpi_admin, mock_db_session):
        dep = _mock_deployment()
        with patch(SVC_PATH) as MockSvc:
            instance = MockSvc.return_value
            instance.force_sync = AsyncMock(return_value=dep)
            resp = client_as_cpi_admin.post(f"/v1/admin/deployments/{uuid4()}/sync")

        assert resp.status_code == 200
