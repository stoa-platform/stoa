"""Tests for deployment lifecycle API (CAB-1353 + CAB-1354)"""
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.models.deployment import Deployment, DeploymentStatus


def _mock_deployment(**overrides):
    """Create a mock Deployment object with sensible defaults."""
    defaults = {
        "id": uuid4(),
        "tenant_id": "acme",
        "api_id": "petstore",
        "api_name": "Petstore API",
        "environment": "dev",
        "version": "1.0.0",
        "status": DeploymentStatus.PENDING.value,
        "deployed_by": "admin",
        "gateway_id": None,
        "error_message": None,
        "spec_hash": None,
        "commit_sha": None,
        "attempt_count": 0,
        "rollback_of": None,
        "rollback_version": None,
        "created_at": "2026-02-16T10:00:00",
        "updated_at": "2026-02-16T10:00:00",
        "completed_at": None,
    }
    defaults.update(overrides)
    m = MagicMock(spec=Deployment)
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


# ===========================================================
# Router Tests
# ===========================================================

SERVICE_PATH = "src.routers.deployments.DeploymentService"
GIT_PATH = "src.routers.deployments.git_service"


class TestListDeployments:
    @pytest.mark.asyncio
    async def test_list_empty(self, client_as_tenant_admin):
        with patch(SERVICE_PATH) as MockSvc:
            MockSvc.return_value.list_deployments = AsyncMock(return_value=([], 0))
            resp = client_as_tenant_admin.get("/v1/tenants/acme/deployments")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0

    @pytest.mark.asyncio
    async def test_list_with_results(self, client_as_tenant_admin):
        dep = _mock_deployment()
        with patch(SERVICE_PATH) as MockSvc:
            MockSvc.return_value.list_deployments = AsyncMock(return_value=([dep], 1))
            resp = client_as_tenant_admin.get("/v1/tenants/acme/deployments")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    @pytest.mark.asyncio
    async def test_list_filter_by_api(self, client_as_tenant_admin):
        with patch(SERVICE_PATH) as MockSvc:
            MockSvc.return_value.list_deployments = AsyncMock(return_value=([], 0))
            resp = client_as_tenant_admin.get(
                "/v1/tenants/acme/deployments?api_id=petstore"
            )
        assert resp.status_code == 200
        MockSvc.return_value.list_deployments.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_pagination(self, client_as_tenant_admin):
        with patch(SERVICE_PATH) as MockSvc:
            MockSvc.return_value.list_deployments = AsyncMock(return_value=([], 0))
            resp = client_as_tenant_admin.get(
                "/v1/tenants/acme/deployments?page=2&page_size=10"
            )
        assert resp.status_code == 200


class TestGetDeployment:
    @pytest.mark.asyncio
    async def test_found(self, client_as_tenant_admin):
        dep = _mock_deployment()
        with patch(SERVICE_PATH) as MockSvc:
            MockSvc.return_value.get_deployment = AsyncMock(return_value=dep)
            resp = client_as_tenant_admin.get(
                f"/v1/tenants/acme/deployments/{dep.id}"
            )
        assert resp.status_code == 200
        assert resp.json()["api_id"] == "petstore"

    @pytest.mark.asyncio
    async def test_not_found(self, client_as_tenant_admin):
        with patch(SERVICE_PATH) as MockSvc:
            MockSvc.return_value.get_deployment = AsyncMock(return_value=None)
            resp = client_as_tenant_admin.get(
                f"/v1/tenants/acme/deployments/{uuid4()}"
            )
        assert resp.status_code == 404


class TestCreateDeployment:
    @pytest.mark.asyncio
    async def test_success(self, client_as_tenant_admin):
        dep = _mock_deployment()
        with (
            patch(SERVICE_PATH) as MockSvc,
            patch(GIT_PATH) as mock_git,
        ):
            mock_git.get_api = AsyncMock(return_value=None)
            MockSvc.return_value.create_deployment = AsyncMock(return_value=dep)
            resp = client_as_tenant_admin.post(
                "/v1/tenants/acme/deployments",
                json={"api_id": "petstore", "environment": "dev"},
            )
        assert resp.status_code == 201
        assert resp.json()["status"] == "pending"

    @pytest.mark.asyncio
    async def test_with_git_resolution(self, client_as_tenant_admin):
        dep = _mock_deployment(api_name="Resolved Name", version="2.0.0")
        with (
            patch(SERVICE_PATH) as MockSvc,
            patch(GIT_PATH) as mock_git,
        ):
            mock_git.get_api = AsyncMock(
                return_value={"name": "Resolved Name", "version": "2.0.0"}
            )
            MockSvc.return_value.create_deployment = AsyncMock(return_value=dep)
            resp = client_as_tenant_admin.post(
                "/v1/tenants/acme/deployments",
                json={"api_id": "petstore", "environment": "dev"},
            )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_git_failure_non_blocking(self, client_as_tenant_admin):
        dep = _mock_deployment()
        with (
            patch(SERVICE_PATH) as MockSvc,
            patch(GIT_PATH) as mock_git,
        ):
            mock_git.get_api = AsyncMock(side_effect=Exception("git down"))
            MockSvc.return_value.create_deployment = AsyncMock(return_value=dep)
            resp = client_as_tenant_admin.post(
                "/v1/tenants/acme/deployments",
                json={"api_id": "petstore", "environment": "staging"},
            )
        assert resp.status_code == 201


class TestRollbackDeployment:
    @pytest.mark.asyncio
    async def test_success(self, client_as_tenant_admin):
        dep = _mock_deployment(rollback_of=uuid4(), rollback_version="0.9.0")
        with patch(SERVICE_PATH) as MockSvc:
            MockSvc.return_value.rollback_deployment = AsyncMock(return_value=dep)
            resp = client_as_tenant_admin.post(
                f"/v1/tenants/acme/deployments/{uuid4()}/rollback",
                json={"target_version": "0.9.0"},
            )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_auto_version(self, client_as_tenant_admin):
        dep = _mock_deployment()
        with patch(SERVICE_PATH) as MockSvc:
            MockSvc.return_value.rollback_deployment = AsyncMock(return_value=dep)
            resp = client_as_tenant_admin.post(
                f"/v1/tenants/acme/deployments/{uuid4()}/rollback",
                json={},
            )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_not_found(self, client_as_tenant_admin):
        with patch(SERVICE_PATH) as MockSvc:
            MockSvc.return_value.rollback_deployment = AsyncMock(
                side_effect=ValueError("Deployment not found")
            )
            resp = client_as_tenant_admin.post(
                f"/v1/tenants/acme/deployments/{uuid4()}/rollback",
                json={},
            )
        assert resp.status_code == 404


class TestUpdateStatus:
    @pytest.mark.asyncio
    async def test_in_progress(self, client_as_tenant_admin):
        dep = _mock_deployment(status="in_progress", attempt_count=1)
        with patch(SERVICE_PATH) as MockSvc:
            MockSvc.return_value.update_status = AsyncMock(return_value=dep)
            resp = client_as_tenant_admin.patch(
                f"/v1/tenants/acme/deployments/{dep.id}/status",
                json={"status": "in_progress"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_success_with_metadata(self, client_as_tenant_admin):
        dep = _mock_deployment(status="success", spec_hash="abc123")
        with patch(SERVICE_PATH) as MockSvc:
            MockSvc.return_value.update_status = AsyncMock(return_value=dep)
            resp = client_as_tenant_admin.patch(
                f"/v1/tenants/acme/deployments/{dep.id}/status",
                json={"status": "success", "spec_hash": "abc123"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_failed_with_error(self, client_as_tenant_admin):
        dep = _mock_deployment(status="failed", error_message="Pod crash")
        with patch(SERVICE_PATH) as MockSvc:
            MockSvc.return_value.update_status = AsyncMock(return_value=dep)
            resp = client_as_tenant_admin.patch(
                f"/v1/tenants/acme/deployments/{dep.id}/status",
                json={"status": "failed", "error_message": "Pod crash"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_not_found(self, client_as_tenant_admin):
        with patch(SERVICE_PATH) as MockSvc:
            MockSvc.return_value.update_status = AsyncMock(
                side_effect=ValueError("not found")
            )
            resp = client_as_tenant_admin.patch(
                f"/v1/tenants/acme/deployments/{uuid4()}/status",
                json={"status": "success"},
            )
        assert resp.status_code == 404


class TestDeploymentLogs:
    @pytest.mark.asyncio
    async def test_found(self, client_as_tenant_admin):
        dep = _mock_deployment()
        with patch(SERVICE_PATH) as MockSvc:
            MockSvc.return_value.get_deployment = AsyncMock(return_value=dep)
            MockSvc.return_value.get_logs = AsyncMock(return_value=[])
            resp = client_as_tenant_admin.get(
                f"/v1/tenants/acme/deployments/{dep.id}/logs"
            )
        assert resp.status_code == 200
        assert "logs" in resp.json()

    @pytest.mark.asyncio
    async def test_not_found(self, client_as_tenant_admin):
        with patch(SERVICE_PATH) as MockSvc:
            MockSvc.return_value.get_deployment = AsyncMock(return_value=None)
            resp = client_as_tenant_admin.get(
                f"/v1/tenants/acme/deployments/{uuid4()}/logs"
            )
        assert resp.status_code == 404


class TestEnvironmentStatus:
    @pytest.mark.asyncio
    async def test_with_deployments(self, client_as_tenant_admin):
        dep = _mock_deployment(status="success")
        with patch(SERVICE_PATH) as MockSvc:
            MockSvc.return_value.get_environment_status = AsyncMock(
                return_value=([dep], True)
            )
            resp = client_as_tenant_admin.get(
                "/v1/tenants/acme/deployments/environments/dev/status"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["healthy"] is True

    @pytest.mark.asyncio
    async def test_no_deployments(self, client_as_tenant_admin):
        with patch(SERVICE_PATH) as MockSvc:
            MockSvc.return_value.get_environment_status = AsyncMock(
                return_value=([], True)
            )
            resp = client_as_tenant_admin.get(
                "/v1/tenants/acme/deployments/environments/staging/status"
            )
        assert resp.status_code == 200
        assert resp.json()["deployments"] == []


# ===========================================================
# Service Unit Tests
# ===========================================================


class TestDeploymentServiceCreate:
    @pytest.mark.asyncio
    async def test_create_emits_kafka_and_webhook(self):
        from src.services.deployment_service import DeploymentService

        mock_db = AsyncMock()
        with (
            patch("src.services.deployment_service.DeploymentRepository") as MockRepo,
            patch("src.services.deployment_service.DeploymentLogRepository") as MockLogRepo,
            patch("src.services.deployment_service.kafka_service") as mock_kafka,
            patch("src.services.webhook_service.emit_deployment_started") as mock_emit,
            patch("src.services.deployment_service.emit_deployment_started") as mock_event,
            patch("src.services.deployment_service.emit_deployment_log") as mock_log_event,
        ):
            dep = _mock_deployment()
            MockRepo.return_value.create = AsyncMock(return_value=dep)
            MockLogRepo.return_value.next_seq = AsyncMock(return_value=1)
            MockLogRepo.return_value.create = AsyncMock(return_value=MagicMock())
            mock_kafka.publish = AsyncMock()
            mock_kafka.emit_audit_event = AsyncMock()
            mock_emit.return_value = None
            mock_event.return_value = ""
            mock_log_event.return_value = ""

            svc = DeploymentService(mock_db)
            result = await svc.create_deployment(
                "acme", "petstore", "Petstore API", "dev",
                "1.0.0", "admin", "user-123",
            )

            assert result == dep
            mock_kafka.publish.assert_called_once()
            mock_kafka.emit_audit_event.assert_called_once()
            mock_emit.assert_called_once()


class TestDeploymentServiceUpdateStatus:
    @pytest.mark.asyncio
    async def test_success_emits_webhook(self):
        from src.services.deployment_service import DeploymentService

        mock_db = AsyncMock()
        dep = _mock_deployment(status="success")
        with (
            patch("src.services.deployment_service.DeploymentRepository") as MockRepo,
            patch("src.services.deployment_service.DeploymentLogRepository") as MockLogRepo,
            patch("src.services.webhook_service.emit_deployment_succeeded") as mock_emit,
            patch("src.services.deployment_service.emit_deployment_completed") as mock_event,
            patch("src.services.deployment_service.emit_deployment_log") as mock_log_event,
        ):
            MockRepo.return_value.get_by_id_and_tenant = AsyncMock(return_value=dep)
            MockRepo.return_value.update = AsyncMock(return_value=dep)
            MockLogRepo.return_value.next_seq = AsyncMock(return_value=1)
            MockLogRepo.return_value.create = AsyncMock(return_value=MagicMock())
            mock_emit.return_value = None
            mock_event.return_value = ""
            mock_log_event.return_value = ""

            svc = DeploymentService(mock_db)
            await svc.update_status("acme", dep.id, "success")
            mock_emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_failed_emits_webhook(self):
        from src.services.deployment_service import DeploymentService

        mock_db = AsyncMock()
        dep = _mock_deployment(status="failed")
        with (
            patch("src.services.deployment_service.DeploymentRepository") as MockRepo,
            patch("src.services.deployment_service.DeploymentLogRepository") as MockLogRepo,
            patch("src.services.webhook_service.emit_deployment_failed") as mock_emit,
            patch("src.services.deployment_service.emit_deployment_failed") as mock_event,
            patch("src.services.deployment_service.emit_deployment_log") as mock_log_event,
        ):
            MockRepo.return_value.get_by_id_and_tenant = AsyncMock(return_value=dep)
            MockRepo.return_value.update = AsyncMock(return_value=dep)
            MockLogRepo.return_value.next_seq = AsyncMock(return_value=1)
            MockLogRepo.return_value.create = AsyncMock(return_value=MagicMock())
            mock_emit.return_value = None
            mock_event.return_value = ""
            mock_log_event.return_value = ""

            svc = DeploymentService(mock_db)
            await svc.update_status("acme", dep.id, "failed", error_message="crash")
            mock_emit.assert_called_once()


class TestDeploymentServiceRollback:
    @pytest.mark.asyncio
    async def test_rollback_creates_new_deployment(self):
        from src.services.deployment_service import DeploymentService

        mock_db = AsyncMock()
        original = _mock_deployment(status="success")
        rollback = _mock_deployment(rollback_of=original.id, rollback_version="0.9.0")
        with (
            patch("src.services.deployment_service.DeploymentRepository") as MockRepo,
            patch("src.services.deployment_service.kafka_service") as mock_kafka,
        ):
            MockRepo.return_value.get_by_id_and_tenant = AsyncMock(return_value=original)
            MockRepo.return_value.create = AsyncMock(return_value=rollback)
            mock_kafka.publish = AsyncMock()
            mock_kafka.emit_audit_event = AsyncMock()

            svc = DeploymentService(mock_db)
            result = await svc.rollback_deployment(
                "acme", original.id, "0.9.0", "admin", "user-123",
            )
            assert result == rollback

    @pytest.mark.asyncio
    async def test_rollback_not_found(self):
        from src.services.deployment_service import DeploymentService

        mock_db = AsyncMock()
        with patch("src.services.deployment_service.DeploymentRepository") as MockRepo:
            MockRepo.return_value.get_by_id_and_tenant = AsyncMock(return_value=None)

            svc = DeploymentService(mock_db)
            with pytest.raises(ValueError, match="not found"):
                await svc.rollback_deployment(
                    "acme", uuid4(), None, "admin", "user-123",
                )
