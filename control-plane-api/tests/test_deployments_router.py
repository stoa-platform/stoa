"""Tests for Deployments Router — CAB-1353

Covers: GET/POST/PATCH /v1/tenants/{tenant_id}/deployments
        POST /{deployment_id}/rollback
        GET /{deployment_id}/logs
        GET /environments/{environment}/status

RBAC: @require_tenant_access (cpi-admin or own tenant).
Permissions: APIS_DEPLOY via @require_permission on create/rollback.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

DEPLOY_SVC_PATH = "src.routers.deployments.DeploymentService"
GIT_SVC_PATH = "src.routers.deployments.git_service"


def _mock_deployment(**overrides):
    """Build a MagicMock that mimics a Deployment ORM object.

    All fields match DeploymentResponse (from_attributes=True).
    """
    did = uuid4()
    now = datetime.utcnow()
    mock = MagicMock()
    defaults = {
        "id": did,
        "tenant_id": "acme",
        "api_id": "api-1",
        "api_name": "Test API",
        "environment": "staging",
        "version": "1.0.0",
        "status": "pending",
        "deployed_by": "admin@acme.com",
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
        "error_message": None,
        "rollback_of": None,
        "rollback_version": None,
        "gateway_id": None,
        "spec_hash": None,
        "commit_sha": None,
        "attempt_count": 0,
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _mock_log(**overrides):
    """Build a MagicMock that mimics a DeploymentLog ORM object."""
    lid = uuid4()
    did = uuid4()
    now = datetime.utcnow()
    mock = MagicMock()
    defaults = {
        "id": lid,
        "deployment_id": did,
        "seq": 1,
        "level": "info",
        "step": "deploy",
        "message": "Deployment started",
        "created_at": now,
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


_VALID_DEPLOY_PAYLOAD = {
    "api_id": "api-1",
    "api_name": "Test API",
    "environment": "staging",
    "version": "1.0.0",
}


# ============== RBAC ==============


class TestDeploymentsRBAC:
    """@require_tenant_access: cpi-admin passes; wrong tenant gets 403."""

    def test_list_403_wrong_tenant(self, app_with_other_tenant, mock_db_session):
        with TestClient(app_with_other_tenant) as client:
            resp = client.get("/v1/tenants/acme/deployments")

        assert resp.status_code == 403
        assert "denied" in resp.json()["detail"].lower()

    def test_get_403_wrong_tenant(self, app_with_other_tenant, mock_db_session):
        with TestClient(app_with_other_tenant) as client:
            resp = client.get(f"/v1/tenants/acme/deployments/{uuid4()}")

        assert resp.status_code == 403

    def test_list_200_own_tenant(self, app_with_tenant_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.list_deployments = AsyncMock(return_value=([], 0))

        with (
            patch(DEPLOY_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get("/v1/tenants/acme/deployments")

        assert resp.status_code == 200

    def test_list_200_as_cpi_admin(self, app_with_cpi_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.list_deployments = AsyncMock(return_value=([], 0))

        with (
            patch(DEPLOY_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.get("/v1/tenants/acme/deployments")

        assert resp.status_code == 200


# ============== List Deployments ==============


class TestListDeployments:
    """GET /v1/tenants/{tenant_id}/deployments"""

    def test_list_empty(self, app_with_tenant_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.list_deployments = AsyncMock(return_value=([], 0))

        with (
            patch(DEPLOY_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get("/v1/tenants/acme/deployments")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_list_with_results(self, app_with_tenant_admin, mock_db_session):
        deployment = _mock_deployment()
        mock_svc = MagicMock()
        mock_svc.list_deployments = AsyncMock(return_value=([deployment], 1))

        with (
            patch(DEPLOY_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get("/v1/tenants/acme/deployments")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    def test_list_passes_filters(self, app_with_tenant_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.list_deployments = AsyncMock(return_value=([], 0))

        with (
            patch(DEPLOY_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get(
                "/v1/tenants/acme/deployments" "?api_id=api-1&environment=staging&status=pending&page=2&page_size=10"
            )

        assert resp.status_code == 200
        call_kwargs = mock_svc.list_deployments.call_args.kwargs
        assert call_kwargs["api_id"] == "api-1"
        assert call_kwargs["environment"] == "staging"
        assert call_kwargs["status"] == "pending"
        assert call_kwargs["page"] == 2
        assert call_kwargs["page_size"] == 10

    def test_list_invalid_environment(self, app_with_tenant_admin, mock_db_session):
        with TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/tenants/acme/deployments?environment=invalid")

        assert resp.status_code == 422


# ============== Get Deployment ==============


class TestGetDeployment:
    """GET /v1/tenants/{tenant_id}/deployments/{deployment_id}"""

    def test_get_success(self, app_with_tenant_admin, mock_db_session):
        did = uuid4()
        deployment = _mock_deployment(id=did)
        mock_svc = MagicMock()
        mock_svc.get_deployment = AsyncMock(return_value=deployment)

        with (
            patch(DEPLOY_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get(f"/v1/tenants/acme/deployments/{did}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["api_id"] == "api-1"
        assert data["environment"] == "staging"

    def test_get_404_not_found(self, app_with_tenant_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.get_deployment = AsyncMock(return_value=None)

        with (
            patch(DEPLOY_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get(f"/v1/tenants/acme/deployments/{uuid4()}")

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_get_invalid_uuid(self, app_with_tenant_admin, mock_db_session):
        with TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/tenants/acme/deployments/not-a-uuid")

        assert resp.status_code == 422


# ============== Create Deployment ==============


class TestCreateDeployment:
    """POST /v1/tenants/{tenant_id}/deployments"""

    def test_create_success(self, app_with_tenant_admin, mock_db_session):
        deployment = _mock_deployment()
        mock_svc = MagicMock()
        mock_svc.create_deployment = AsyncMock(return_value=deployment)

        with (
            patch(DEPLOY_SVC_PATH, return_value=mock_svc),
            patch(f"{GIT_SVC_PATH}.get_api", new=AsyncMock(return_value=None)),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.post("/v1/tenants/acme/deployments", json=_VALID_DEPLOY_PAYLOAD)

        assert resp.status_code == 201
        data = resp.json()
        assert data["api_id"] == "api-1"
        assert data["environment"] == "staging"

    def test_create_403_wrong_tenant(self, app_with_other_tenant, mock_db_session):
        with TestClient(app_with_other_tenant) as client:
            resp = client.post("/v1/tenants/acme/deployments", json=_VALID_DEPLOY_PAYLOAD)

        assert resp.status_code == 403

    def test_create_validates_required_fields(self, app_with_tenant_admin, mock_db_session):
        with TestClient(app_with_tenant_admin) as client:
            resp = client.post("/v1/tenants/acme/deployments", json={})

        assert resp.status_code == 422

    def test_create_invalid_environment(self, app_with_tenant_admin, mock_db_session):
        payload = {**_VALID_DEPLOY_PAYLOAD, "environment": "production-extreme"}
        with TestClient(app_with_tenant_admin) as client:
            resp = client.post("/v1/tenants/acme/deployments", json=payload)

        assert resp.status_code == 422

    def test_create_uses_git_service_api_info(self, app_with_tenant_admin, mock_db_session):
        """When git_service returns API info, api_name and version are enriched."""
        deployment = _mock_deployment(api_name="Git API Name", version="2.0.0")
        mock_svc = MagicMock()
        mock_svc.create_deployment = AsyncMock(return_value=deployment)
        git_info = {"name": "Git API Name", "version": "2.0.0"}

        with (
            patch(DEPLOY_SVC_PATH, return_value=mock_svc),
            patch(f"{GIT_SVC_PATH}.get_api", new=AsyncMock(return_value=git_info)),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.post(
                "/v1/tenants/acme/deployments",
                json={"api_id": "api-1", "environment": "staging"},
            )

        assert resp.status_code == 201
        call_kwargs = mock_svc.create_deployment.call_args.kwargs
        assert call_kwargs["api_name"] == "Git API Name"
        assert call_kwargs["version"] == "2.0.0"


# ============== Rollback Deployment ==============


class TestRollbackDeployment:
    """POST /v1/tenants/{tenant_id}/deployments/{deployment_id}/rollback"""

    def test_rollback_success(self, app_with_tenant_admin, mock_db_session):
        did = uuid4()
        rollback = _mock_deployment(id=uuid4(), rollback_of=did, version="0.9.0")
        mock_svc = MagicMock()
        mock_svc.rollback_deployment = AsyncMock(return_value=rollback)

        with (
            patch(DEPLOY_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.post(
                f"/v1/tenants/acme/deployments/{did}/rollback",
                json={"target_version": "0.9.0"},
            )

        assert resp.status_code == 201

    def test_rollback_404_not_found(self, app_with_tenant_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.rollback_deployment = AsyncMock(side_effect=ValueError("Deployment not found"))

        with (
            patch(DEPLOY_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.post(
                f"/v1/tenants/acme/deployments/{uuid4()}/rollback",
                json={},
            )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_rollback_403_wrong_tenant(self, app_with_other_tenant, mock_db_session):
        with TestClient(app_with_other_tenant) as client:
            resp = client.post(
                f"/v1/tenants/acme/deployments/{uuid4()}/rollback",
                json={},
            )

        assert resp.status_code == 403


# ============== Update Deployment Status ==============


class TestUpdateDeploymentStatus:
    """PATCH /v1/tenants/{tenant_id}/deployments/{deployment_id}/status"""

    def test_update_status_success(self, app_with_tenant_admin, mock_db_session):
        did = uuid4()
        deployment = _mock_deployment(id=did, status="success")
        mock_svc = MagicMock()
        mock_svc.update_status = AsyncMock(return_value=deployment)

        with (
            patch(DEPLOY_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.patch(
                f"/v1/tenants/acme/deployments/{did}/status",
                json={"status": "success"},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    def test_update_status_404_not_found(self, app_with_tenant_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.update_status = AsyncMock(side_effect=ValueError("Deployment not found"))

        with (
            patch(DEPLOY_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.patch(
                f"/v1/tenants/acme/deployments/{uuid4()}/status",
                json={"status": "failed", "error_message": "Gateway unreachable"},
            )

        assert resp.status_code == 404

    def test_update_status_invalid_enum(self, app_with_tenant_admin, mock_db_session):
        with TestClient(app_with_tenant_admin) as client:
            resp = client.patch(
                f"/v1/tenants/acme/deployments/{uuid4()}/status",
                json={"status": "unknown_status"},
            )

        assert resp.status_code == 422

    def test_update_status_with_metadata(self, app_with_tenant_admin, mock_db_session):
        did = uuid4()
        deployment = _mock_deployment(id=did, status="success", spec_hash="abc123")
        mock_svc = MagicMock()
        mock_svc.update_status = AsyncMock(return_value=deployment)

        with (
            patch(DEPLOY_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.patch(
                f"/v1/tenants/acme/deployments/{did}/status",
                json={
                    "status": "success",
                    "spec_hash": "abc123",
                    "commit_sha": "deadbeef",
                    "metadata": {"gateway": "stoa-k8s"},
                },
            )

        assert resp.status_code == 200
        call_kwargs = mock_svc.update_status.call_args.kwargs
        assert call_kwargs["spec_hash"] == "abc123"
        assert call_kwargs["commit_sha"] == "deadbeef"
        assert call_kwargs["metadata"] == {"gateway": "stoa-k8s"}


# ============== Deployment Logs ==============


class TestGetDeploymentLogs:
    """GET /v1/tenants/{tenant_id}/deployments/{deployment_id}/logs"""

    def test_get_logs_success(self, app_with_tenant_admin, mock_db_session):
        did = uuid4()
        deployment = _mock_deployment(id=did)
        log1 = _mock_log(deployment_id=did, seq=1, message="Starting")
        log2 = _mock_log(deployment_id=did, seq=2, message="Deploying")
        mock_svc = MagicMock()
        mock_svc.get_deployment = AsyncMock(return_value=deployment)
        mock_svc.get_logs = AsyncMock(return_value=[log1, log2])

        with (
            patch(DEPLOY_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get(f"/v1/tenants/acme/deployments/{did}/logs")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["logs"]) == 2

    def test_get_logs_empty(self, app_with_tenant_admin, mock_db_session):
        did = uuid4()
        deployment = _mock_deployment(id=did)
        mock_svc = MagicMock()
        mock_svc.get_deployment = AsyncMock(return_value=deployment)
        mock_svc.get_logs = AsyncMock(return_value=[])

        with (
            patch(DEPLOY_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get(f"/v1/tenants/acme/deployments/{did}/logs")

        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_get_logs_404_deployment_not_found(self, app_with_tenant_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.get_deployment = AsyncMock(return_value=None)

        with (
            patch(DEPLOY_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get(f"/v1/tenants/acme/deployments/{uuid4()}/logs")

        assert resp.status_code == 404

    def test_get_logs_passes_cursor_params(self, app_with_tenant_admin, mock_db_session):
        did = uuid4()
        deployment = _mock_deployment(id=did)
        mock_svc = MagicMock()
        mock_svc.get_deployment = AsyncMock(return_value=deployment)
        mock_svc.get_logs = AsyncMock(return_value=[])

        with (
            patch(DEPLOY_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get(f"/v1/tenants/acme/deployments/{did}/logs?after_seq=10&limit=50")

        assert resp.status_code == 200
        call_kwargs = mock_svc.get_logs.call_args.kwargs
        assert call_kwargs["after_seq"] == 10
        assert call_kwargs["limit"] == 50


# ============== Environment Status ==============


class TestGetEnvironmentStatus:
    """GET /v1/tenants/{tenant_id}/deployments/environments/{environment}/status"""

    def test_environment_status_success(self, app_with_tenant_admin, mock_db_session):
        dep1 = _mock_deployment(api_id="api-1", api_name="API One", status="success")
        dep1.completed_at = dep1.created_at  # provide non-None completed_at
        mock_svc = MagicMock()
        mock_svc.get_environment_status = AsyncMock(return_value=([dep1], True))

        with (
            patch(DEPLOY_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get("/v1/tenants/acme/deployments/environments/staging/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["environment"] == "staging"
        assert data["healthy"] is True
        assert len(data["deployments"]) == 1

    def test_environment_status_unhealthy(self, app_with_tenant_admin, mock_db_session):
        dep1 = _mock_deployment(status="failed")
        dep1.completed_at = None
        mock_svc = MagicMock()
        mock_svc.get_environment_status = AsyncMock(return_value=([dep1], False))

        with (
            patch(DEPLOY_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get("/v1/tenants/acme/deployments/environments/production/status")

        assert resp.status_code == 200
        assert resp.json()["healthy"] is False

    def test_environment_status_empty(self, app_with_tenant_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.get_environment_status = AsyncMock(return_value=([], True))

        with (
            patch(DEPLOY_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get("/v1/tenants/acme/deployments/environments/dev/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["deployments"] == []

    def test_environment_status_invalid_env(self, app_with_tenant_admin, mock_db_session):
        with TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/tenants/acme/deployments/environments/invalid-env/status")

        assert resp.status_code == 422

    def test_environment_status_403_wrong_tenant(self, app_with_other_tenant, mock_db_session):
        with TestClient(app_with_other_tenant) as client:
            resp = client.get("/v1/tenants/acme/deployments/environments/staging/status")

        assert resp.status_code == 403
