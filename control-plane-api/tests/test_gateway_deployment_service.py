"""Tests for GatewayDeploymentService — deploy, undeploy, force_sync."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone


class TestGatewayDeploymentService:
    """Tests for gateway deployment service business logic."""

    def _make_catalog(self, **overrides):
        """Create a mock APICatalog."""
        defaults = {
            "id": uuid4(),
            "api_name": "payments",
            "api_id": "payments-v2",
            "tenant_id": "acme",
            "version": "2.0.0",
            "openapi_spec": {"openapi": "3.0.0", "info": {"title": "Payments"}},
            "api_metadata": None,
            "status": "active",
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    def _make_gateway(self, **overrides):
        """Create a mock GatewayInstance."""
        defaults = {
            "id": uuid4(),
            "name": "webmethods-prod",
            "gateway_type": MagicMock(value="webmethods"),
            "base_url": "https://gw.example.com",
            "auth_config": {},
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    def _make_deployment(self, **overrides):
        """Create a mock GatewayDeployment."""
        from src.models.gateway_deployment import DeploymentSyncStatus

        defaults = {
            "id": uuid4(),
            "api_catalog_id": uuid4(),
            "gateway_instance_id": uuid4(),
            "desired_state": {"spec_hash": "abc123", "tenant_id": "acme"},
            "sync_status": DeploymentSyncStatus.PENDING,
            "sync_error": None,
            "sync_attempts": 0,
            "gateway_resource_id": None,
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    @pytest.mark.asyncio
    async def test_deploy_single_gateway(self):
        """Deploy API to a single gateway creates one PENDING deployment."""
        db = AsyncMock()
        catalog = self._make_catalog()
        gateway = self._make_gateway()

        with patch("src.services.gateway_deployment_service.GatewayDeploymentRepository") as MockDeployRepo, \
             patch("src.services.gateway_deployment_service.GatewayInstanceRepository") as MockGwRepo, \
             patch("src.services.gateway_deployment_service.kafka_service") as mock_kafka:

            mock_deploy_repo = MockDeployRepo.return_value
            mock_deploy_repo.get_by_api_and_gateway = AsyncMock(return_value=None)
            mock_deploy_repo.create = AsyncMock(side_effect=lambda d: d)

            mock_gw_repo = MockGwRepo.return_value
            mock_gw_repo.get_by_id = AsyncMock(return_value=gateway)

            mock_kafka.publish = AsyncMock()

            # Mock the SQLAlchemy select for APICatalog
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = catalog
            db.execute = AsyncMock(return_value=mock_result)

            from src.services.gateway_deployment_service import GatewayDeploymentService

            svc = GatewayDeploymentService(db)
            svc.deploy_repo = mock_deploy_repo
            svc.gw_repo = mock_gw_repo

            deployments = await svc.deploy_api(catalog.id, [gateway.id])

            assert len(deployments) == 1
            mock_deploy_repo.create.assert_awaited_once()
            mock_kafka.publish.assert_awaited()

    @pytest.mark.asyncio
    async def test_deploy_multiple_gateways(self):
        """Deploy API to multiple gateways creates multiple deployments."""
        db = AsyncMock()
        catalog = self._make_catalog()
        gw1 = self._make_gateway(name="gw-1")
        gw2 = self._make_gateway(name="gw-2")

        with patch("src.services.gateway_deployment_service.GatewayDeploymentRepository") as MockDeployRepo, \
             patch("src.services.gateway_deployment_service.GatewayInstanceRepository") as MockGwRepo, \
             patch("src.services.gateway_deployment_service.kafka_service") as mock_kafka:

            mock_deploy_repo = MockDeployRepo.return_value
            mock_deploy_repo.get_by_api_and_gateway = AsyncMock(return_value=None)
            mock_deploy_repo.create = AsyncMock(side_effect=lambda d: d)

            mock_gw_repo = MockGwRepo.return_value
            mock_gw_repo.get_by_id = AsyncMock(side_effect=lambda gid: gw1 if gid == gw1.id else gw2)

            mock_kafka.publish = AsyncMock()

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = catalog
            db.execute = AsyncMock(return_value=mock_result)

            from src.services.gateway_deployment_service import GatewayDeploymentService

            svc = GatewayDeploymentService(db)
            svc.deploy_repo = mock_deploy_repo
            svc.gw_repo = mock_gw_repo

            deployments = await svc.deploy_api(catalog.id, [gw1.id, gw2.id])

            assert len(deployments) == 2
            assert mock_deploy_repo.create.await_count == 2

    @pytest.mark.asyncio
    async def test_deploy_updates_existing(self):
        """Re-deploying an API to same gateway updates existing deployment."""
        from src.models.gateway_deployment import DeploymentSyncStatus

        db = AsyncMock()
        catalog = self._make_catalog()
        gateway = self._make_gateway()
        existing = self._make_deployment(
            sync_status=DeploymentSyncStatus.SYNCED,
            sync_attempts=2,
            sync_error="old error",
        )

        with patch("src.services.gateway_deployment_service.GatewayDeploymentRepository") as MockDeployRepo, \
             patch("src.services.gateway_deployment_service.GatewayInstanceRepository") as MockGwRepo, \
             patch("src.services.gateway_deployment_service.kafka_service") as mock_kafka:

            mock_deploy_repo = MockDeployRepo.return_value
            mock_deploy_repo.get_by_api_and_gateway = AsyncMock(return_value=existing)
            mock_deploy_repo.update = AsyncMock(return_value=existing)

            mock_gw_repo = MockGwRepo.return_value
            mock_gw_repo.get_by_id = AsyncMock(return_value=gateway)

            mock_kafka.publish = AsyncMock()

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = catalog
            db.execute = AsyncMock(return_value=mock_result)

            from src.services.gateway_deployment_service import GatewayDeploymentService

            svc = GatewayDeploymentService(db)
            svc.deploy_repo = mock_deploy_repo
            svc.gw_repo = mock_gw_repo

            deployments = await svc.deploy_api(catalog.id, [gateway.id])

            assert len(deployments) == 1
            assert existing.sync_status == DeploymentSyncStatus.PENDING
            assert existing.sync_error is None
            assert existing.sync_attempts == 0

    @pytest.mark.asyncio
    async def test_deploy_invalid_catalog_raises(self):
        """ValueError raised when API catalog not found."""
        db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        with patch("src.services.gateway_deployment_service.GatewayDeploymentRepository"), \
             patch("src.services.gateway_deployment_service.GatewayInstanceRepository"):

            from src.services.gateway_deployment_service import GatewayDeploymentService

            svc = GatewayDeploymentService(db)

            with pytest.raises(ValueError, match="API catalog entry not found"):
                await svc.deploy_api(uuid4(), [uuid4()])

    @pytest.mark.asyncio
    async def test_undeploy_with_resource_id_marks_deleting(self):
        """Undeploy with gateway_resource_id sets DELETING status."""
        from src.models.gateway_deployment import DeploymentSyncStatus

        db = AsyncMock()
        deployment = self._make_deployment(
            gateway_resource_id="gw-api-123",
            sync_status=DeploymentSyncStatus.SYNCED,
        )

        with patch("src.services.gateway_deployment_service.GatewayDeploymentRepository") as MockDeployRepo, \
             patch("src.services.gateway_deployment_service.GatewayInstanceRepository"), \
             patch("src.services.gateway_deployment_service.kafka_service") as mock_kafka:

            mock_deploy_repo = MockDeployRepo.return_value
            mock_deploy_repo.get_by_id = AsyncMock(return_value=deployment)
            mock_deploy_repo.update = AsyncMock(return_value=deployment)

            mock_kafka.publish = AsyncMock()

            from src.services.gateway_deployment_service import GatewayDeploymentService

            svc = GatewayDeploymentService(db)
            svc.deploy_repo = mock_deploy_repo

            await svc.undeploy(deployment.id)

            assert deployment.sync_status == DeploymentSyncStatus.DELETING
            mock_deploy_repo.update.assert_awaited_once()
            mock_deploy_repo.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_undeploy_without_resource_id_deletes(self):
        """Undeploy without gateway_resource_id deletes the record."""
        db = AsyncMock()
        deployment = self._make_deployment(gateway_resource_id=None)

        with patch("src.services.gateway_deployment_service.GatewayDeploymentRepository") as MockDeployRepo, \
             patch("src.services.gateway_deployment_service.GatewayInstanceRepository"), \
             patch("src.services.gateway_deployment_service.kafka_service"):

            mock_deploy_repo = MockDeployRepo.return_value
            mock_deploy_repo.get_by_id = AsyncMock(return_value=deployment)
            mock_deploy_repo.delete = AsyncMock()

            from src.services.gateway_deployment_service import GatewayDeploymentService

            svc = GatewayDeploymentService(db)
            svc.deploy_repo = mock_deploy_repo

            await svc.undeploy(deployment.id)

            mock_deploy_repo.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_force_sync_resets_to_pending(self):
        """Force sync resets status to PENDING, clears error/attempts."""
        from src.models.gateway_deployment import DeploymentSyncStatus

        db = AsyncMock()
        deployment = self._make_deployment(
            sync_status=DeploymentSyncStatus.ERROR,
            sync_error="some error",
            sync_attempts=3,
        )

        with patch("src.services.gateway_deployment_service.GatewayDeploymentRepository") as MockDeployRepo, \
             patch("src.services.gateway_deployment_service.GatewayInstanceRepository"), \
             patch("src.services.gateway_deployment_service.kafka_service") as mock_kafka:

            mock_deploy_repo = MockDeployRepo.return_value
            mock_deploy_repo.get_by_id = AsyncMock(return_value=deployment)
            mock_deploy_repo.update = AsyncMock(return_value=deployment)

            mock_kafka.publish = AsyncMock()

            from src.services.gateway_deployment_service import GatewayDeploymentService

            svc = GatewayDeploymentService(db)
            svc.deploy_repo = mock_deploy_repo

            result = await svc.force_sync(deployment.id)

            assert result.sync_status == DeploymentSyncStatus.PENDING
            assert result.sync_error is None
            assert result.sync_attempts == 0

    @pytest.mark.asyncio
    async def test_build_desired_state_deterministic_hash(self):
        """build_desired_state produces deterministic SHA256 hash."""
        catalog = self._make_catalog(
            openapi_spec={"openapi": "3.0.0", "info": {"title": "Test"}},
        )

        from src.services.gateway_deployment_service import GatewayDeploymentService

        state1 = GatewayDeploymentService.build_desired_state(catalog)
        state2 = GatewayDeploymentService.build_desired_state(catalog)

        assert state1["spec_hash"] == state2["spec_hash"]
        assert len(state1["spec_hash"]) == 64  # SHA256 hex length
        assert state1["api_name"] == "payments"
        assert state1["tenant_id"] == "acme"
        assert state1["activated"] is True
