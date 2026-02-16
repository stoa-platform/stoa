"""Tests for DeploymentService (CAB-1291)"""
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.deployment import Deployment, DeploymentStatus
from src.services.deployment_service import DeploymentService


def _make_deployment(**overrides) -> Deployment:
    """Create a Deployment instance with sane defaults."""
    defaults = {
        "id": uuid.uuid4(),
        "tenant_id": "acme",
        "api_id": "api-1",
        "api_name": "Weather API",
        "environment": "staging",
        "version": "1.0.0",
        "status": DeploymentStatus.PENDING.value,
        "deployed_by": "alice",
        "attempt_count": 0,
        "created_at": datetime(2026, 2, 1),
        "updated_at": datetime(2026, 2, 1),
    }
    defaults.update(overrides)
    deployment = MagicMock(spec=Deployment)
    for k, v in defaults.items():
        setattr(deployment, k, v)
    return deployment


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def service(mock_db):
    svc = DeploymentService(mock_db)
    svc.repo = AsyncMock()
    return svc


def _mock_kafka():
    """Create a mock kafka_service with async methods."""
    mock = MagicMock()
    mock.publish = AsyncMock()
    mock.emit_audit_event = AsyncMock()
    return mock


class TestCreateDeployment:
    @pytest.mark.asyncio
    async def test_creates_and_publishes_events(self, service):
        created = _make_deployment()
        service.repo.create.return_value = created

        with (
            patch("src.services.deployment_service.kafka_service", _mock_kafka()) as mock_kafka,
            patch("src.services.webhook_service.emit_deployment_started", new_callable=AsyncMock) as mock_webhook,
        ):
            result = await service.create_deployment(
                tenant_id="acme", api_id="api-1", api_name="Weather API",
                environment="staging", version="1.0.0",
                deployed_by="alice", user_id="user-1",
            )

        assert result == created
        service.repo.create.assert_called_once()
        assert mock_kafka.publish.call_count == 1
        assert mock_kafka.emit_audit_event.call_count == 1
        mock_webhook.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_with_gateway_id(self, service):
        created = _make_deployment(gateway_id="gw-1")
        service.repo.create.return_value = created

        with (
            patch("src.services.deployment_service.kafka_service", _mock_kafka()),
            patch("src.services.webhook_service.emit_deployment_started", new_callable=AsyncMock),
        ):
            result = await service.create_deployment(
                tenant_id="acme", api_id="api-1", api_name="Test",
                environment="dev", version="2.0.0",
                deployed_by="bob", user_id="user-2", gateway_id="gw-1",
            )

        # Verify the Deployment object passed to repo.create has gateway_id
        call_args = service.repo.create.call_args[0][0]
        assert call_args.gateway_id == "gw-1"


class TestRollbackDeployment:
    @pytest.mark.asyncio
    async def test_rollback_with_explicit_version(self, service):
        original = _make_deployment(version="2.0.0")
        service.repo.get_by_id_and_tenant.return_value = original
        rollback = _make_deployment(version="1.0.0", rollback_of=original.id)
        service.repo.create.return_value = rollback

        with patch("src.services.deployment_service.kafka_service", _mock_kafka()) as mock_kafka:
            result = await service.rollback_deployment(
                tenant_id="acme", deployment_id=original.id,
                target_version="1.0.0", deployed_by="alice", user_id="user-1",
            )

        assert result == rollback
        assert mock_kafka.publish.call_count == 1
        assert mock_kafka.emit_audit_event.call_count == 1

    @pytest.mark.asyncio
    async def test_rollback_auto_detects_version(self, service):
        original = _make_deployment(version="3.0.0")
        prev_success = _make_deployment(version="2.0.0")
        service.repo.get_by_id_and_tenant.return_value = original
        service.repo.get_latest_success.return_value = prev_success
        service.repo.create.return_value = _make_deployment(version="2.0.0")

        with patch("src.services.deployment_service.kafka_service", _mock_kafka()):
            result = await service.rollback_deployment(
                tenant_id="acme", deployment_id=original.id,
                target_version=None, deployed_by="alice", user_id="user-1",
            )

        # Should use prev_success.version
        call_args = service.repo.create.call_args[0][0]
        assert call_args.version == "2.0.0"

    @pytest.mark.asyncio
    async def test_rollback_no_previous_uses_fallback(self, service):
        original = _make_deployment()
        service.repo.get_by_id_and_tenant.return_value = original
        service.repo.get_latest_success.return_value = None
        service.repo.create.return_value = _make_deployment(version="previous")

        with patch("src.services.deployment_service.kafka_service", _mock_kafka()):
            result = await service.rollback_deployment(
                tenant_id="acme", deployment_id=original.id,
                target_version=None, deployed_by="alice", user_id="user-1",
            )

        call_args = service.repo.create.call_args[0][0]
        assert call_args.version == "previous"

    @pytest.mark.asyncio
    async def test_rollback_not_found_raises(self, service):
        service.repo.get_by_id_and_tenant.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await service.rollback_deployment(
                tenant_id="acme", deployment_id=uuid.uuid4(),
                target_version="1.0.0", deployed_by="alice", user_id="user-1",
            )


class TestUpdateStatus:
    @pytest.mark.asyncio
    async def test_update_to_success(self, service):
        deployment = _make_deployment(status=DeploymentStatus.IN_PROGRESS.value)
        service.repo.get_by_id_and_tenant.return_value = deployment
        service.repo.update.return_value = deployment

        with patch("src.services.webhook_service.emit_deployment_succeeded", new_callable=AsyncMock) as mock_webhook:
            result = await service.update_status(
                tenant_id="acme", deployment_id=deployment.id,
                status=DeploymentStatus.SUCCESS.value,
            )

        assert deployment.status == DeploymentStatus.SUCCESS.value
        assert deployment.completed_at is not None
        mock_webhook.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_to_failed(self, service):
        deployment = _make_deployment(status=DeploymentStatus.IN_PROGRESS.value)
        service.repo.get_by_id_and_tenant.return_value = deployment
        service.repo.update.return_value = deployment

        with patch("src.services.webhook_service.emit_deployment_failed", new_callable=AsyncMock) as mock_webhook:
            result = await service.update_status(
                tenant_id="acme", deployment_id=deployment.id,
                status=DeploymentStatus.FAILED.value,
                error_message="Pod CrashLoopBackOff",
            )

        assert deployment.status == DeploymentStatus.FAILED.value
        assert deployment.error_message == "Pod CrashLoopBackOff"
        assert deployment.completed_at is not None
        mock_webhook.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_to_rolled_back(self, service):
        deployment = _make_deployment(status=DeploymentStatus.FAILED.value)
        service.repo.get_by_id_and_tenant.return_value = deployment
        service.repo.update.return_value = deployment

        with patch("src.services.webhook_service.emit_deployment_rolled_back", new_callable=AsyncMock) as mock_webhook:
            result = await service.update_status(
                tenant_id="acme", deployment_id=deployment.id,
                status=DeploymentStatus.ROLLED_BACK.value,
            )

        assert deployment.completed_at is not None
        mock_webhook.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_to_in_progress_increments_attempt(self, service):
        deployment = _make_deployment(status=DeploymentStatus.PENDING.value, attempt_count=0)
        service.repo.get_by_id_and_tenant.return_value = deployment
        service.repo.update.return_value = deployment

        await service.update_status(
            tenant_id="acme", deployment_id=deployment.id,
            status=DeploymentStatus.IN_PROGRESS.value,
        )

        assert deployment.attempt_count == 1

    @pytest.mark.asyncio
    async def test_update_with_spec_hash_and_commit(self, service):
        deployment = _make_deployment()
        service.repo.get_by_id_and_tenant.return_value = deployment
        service.repo.update.return_value = deployment

        await service.update_status(
            tenant_id="acme", deployment_id=deployment.id,
            status=DeploymentStatus.IN_PROGRESS.value,
            spec_hash="abc123", commit_sha="def456",
        )

        assert deployment.spec_hash == "abc123"
        assert deployment.commit_sha == "def456"

    @pytest.mark.asyncio
    async def test_update_not_found_raises(self, service):
        service.repo.get_by_id_and_tenant.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await service.update_status(
                tenant_id="acme", deployment_id=uuid.uuid4(),
                status=DeploymentStatus.SUCCESS.value,
            )


class TestListAndGet:
    @pytest.mark.asyncio
    async def test_list_deployments(self, service):
        deployments = [_make_deployment(), _make_deployment()]
        service.repo.list_by_tenant.return_value = (deployments, 2)

        result, total = await service.list_deployments("acme")

        assert total == 2
        service.repo.list_by_tenant.assert_called_once_with(
            "acme", api_id=None, environment=None, status=None, page=1, page_size=50,
        )

    @pytest.mark.asyncio
    async def test_list_with_filters(self, service):
        service.repo.list_by_tenant.return_value = ([], 0)

        await service.list_deployments(
            "acme", api_id="api-1", environment="prod", status="success", page=2, page_size=10,
        )

        service.repo.list_by_tenant.assert_called_once_with(
            "acme", api_id="api-1", environment="prod", status="success", page=2, page_size=10,
        )

    @pytest.mark.asyncio
    async def test_get_deployment(self, service):
        dep = _make_deployment()
        service.repo.get_by_id_and_tenant.return_value = dep

        result = await service.get_deployment("acme", dep.id)

        assert result == dep

    @pytest.mark.asyncio
    async def test_get_deployment_not_found(self, service):
        service.repo.get_by_id_and_tenant.return_value = None
        result = await service.get_deployment("acme", uuid.uuid4())
        assert result is None


class TestEnvironmentStatus:
    @pytest.mark.asyncio
    async def test_healthy_when_all_success(self, service):
        deps = [
            _make_deployment(status=DeploymentStatus.SUCCESS.value),
            _make_deployment(status=DeploymentStatus.SUCCESS.value),
        ]
        service.repo.get_environment_summary.return_value = deps

        result, healthy = await service.get_environment_status("acme", "prod")

        assert healthy is True
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_unhealthy_when_one_failed(self, service):
        deps = [
            _make_deployment(status=DeploymentStatus.SUCCESS.value),
            _make_deployment(status=DeploymentStatus.FAILED.value),
        ]
        service.repo.get_environment_summary.return_value = deps

        result, healthy = await service.get_environment_status("acme", "staging")

        assert healthy is False

    @pytest.mark.asyncio
    async def test_healthy_when_empty(self, service):
        service.repo.get_environment_summary.return_value = []
        result, healthy = await service.get_environment_status("acme", "dev")
        assert healthy is True
        assert result == []
