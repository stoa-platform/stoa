"""Tests for SyncEngine — reconciliation and drift detection."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone

from src.adapters.gateway_adapter_interface import AdapterResult
from src.models.gateway_deployment import DeploymentSyncStatus
from src.models.gateway_instance import GatewayInstanceStatus


class TestSyncEngine:
    """Tests for the sync engine reconciliation logic."""

    def _make_deployment(self, **overrides):
        """Create a mock GatewayDeployment."""
        defaults = {
            "id": uuid4(),
            "api_catalog_id": uuid4(),
            "gateway_instance_id": uuid4(),
            "desired_state": {"spec_hash": "abc123", "tenant_id": "acme", "api_name": "Test"},
            "actual_state": None,
            "sync_status": DeploymentSyncStatus.PENDING,
            "sync_attempts": 0,
            "sync_error": None,
            "gateway_resource_id": None,
            "last_sync_attempt": None,
            "last_sync_success": None,
            "desired_at": datetime.now(timezone.utc),
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
            "status": GatewayInstanceStatus.ONLINE,
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    def _make_adapter(self, sync_result=None, delete_result=None, list_apis_result=None):
        """Create a mock adapter with configured responses."""
        adapter = MagicMock()
        adapter.connect = AsyncMock()
        adapter.disconnect = AsyncMock()
        adapter.sync_api = AsyncMock(
            return_value=sync_result or AdapterResult(success=True, resource_id="gw-api-1", data={"spec_hash": "abc123"})
        )
        adapter.delete_api = AsyncMock(
            return_value=delete_result or AdapterResult(success=True)
        )
        adapter.list_apis = AsyncMock(
            return_value=list_apis_result or []
        )
        return adapter

    @pytest.mark.asyncio
    async def test_reconcile_pending_to_synced(self):
        """PENDING deployment is synced to SYNCED on adapter success."""
        deployment = self._make_deployment(sync_status=DeploymentSyncStatus.PENDING)
        gateway = self._make_gateway(id=deployment.gateway_instance_id)
        adapter = self._make_adapter()

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=deployment)
        mock_repo.update = AsyncMock(return_value=deployment)

        mock_gw_repo = MagicMock()
        mock_gw_repo.get_by_id = AsyncMock(return_value=gateway)

        mock_factory = MagicMock(return_value=MagicMock(
            __aenter__=AsyncMock(return_value=mock_session),
            __aexit__=AsyncMock(return_value=False),
        ))

        with patch("src.workers.sync_engine._get_session_factory", return_value=mock_factory), \
             patch("src.workers.sync_engine.GatewayDeploymentRepository", return_value=mock_repo), \
             patch("src.workers.sync_engine.GatewayInstanceRepository", return_value=mock_gw_repo), \
             patch("src.workers.sync_engine.AdapterRegistry") as mock_registry:

            mock_registry.create.return_value = adapter

            from src.workers.sync_engine import SyncEngine

            engine = SyncEngine()
            engine._semaphore = MagicMock()
            engine._semaphore.__aenter__ = AsyncMock()
            engine._semaphore.__aexit__ = AsyncMock()

            await engine._reconcile_one(deployment.id)

            adapter.sync_api.assert_awaited_once()
            adapter.connect.assert_awaited_once()
            adapter.disconnect.assert_awaited_once()
            assert deployment.sync_status == DeploymentSyncStatus.SYNCED
            assert deployment.gateway_resource_id == "gw-api-1"

    @pytest.mark.asyncio
    async def test_reconcile_sync_failure(self):
        """Adapter sync failure marks deployment as ERROR."""
        deployment = self._make_deployment(sync_status=DeploymentSyncStatus.PENDING)
        gateway = self._make_gateway(id=deployment.gateway_instance_id)
        adapter = self._make_adapter(
            sync_result=AdapterResult(success=False, error="Connection refused")
        )

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=deployment)
        mock_repo.update = AsyncMock(return_value=deployment)

        mock_gw_repo = MagicMock()
        mock_gw_repo.get_by_id = AsyncMock(return_value=gateway)

        mock_factory = MagicMock(return_value=MagicMock(
            __aenter__=AsyncMock(return_value=mock_session),
            __aexit__=AsyncMock(return_value=False),
        ))

        with patch("src.workers.sync_engine._get_session_factory", return_value=mock_factory), \
             patch("src.workers.sync_engine.GatewayDeploymentRepository", return_value=mock_repo), \
             patch("src.workers.sync_engine.GatewayInstanceRepository", return_value=mock_gw_repo), \
             patch("src.workers.sync_engine.AdapterRegistry") as mock_registry:

            mock_registry.create.return_value = adapter

            from src.workers.sync_engine import SyncEngine

            engine = SyncEngine()
            engine._semaphore = MagicMock()
            engine._semaphore.__aenter__ = AsyncMock()
            engine._semaphore.__aexit__ = AsyncMock()

            await engine._reconcile_one(deployment.id)

            assert deployment.sync_status == DeploymentSyncStatus.ERROR
            assert deployment.sync_error == "Connection refused"
            assert deployment.sync_attempts == 1

    @pytest.mark.asyncio
    async def test_reconcile_delete_success(self):
        """DELETING deployment is deleted from DB on adapter success."""
        deployment = self._make_deployment(
            sync_status=DeploymentSyncStatus.DELETING,
            gateway_resource_id="gw-api-99",
        )
        gateway = self._make_gateway(id=deployment.gateway_instance_id)
        adapter = self._make_adapter(delete_result=AdapterResult(success=True))

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=deployment)
        mock_repo.delete = AsyncMock()
        mock_repo.update = AsyncMock(return_value=deployment)

        mock_gw_repo = MagicMock()
        mock_gw_repo.get_by_id = AsyncMock(return_value=gateway)

        mock_factory = MagicMock(return_value=MagicMock(
            __aenter__=AsyncMock(return_value=mock_session),
            __aexit__=AsyncMock(return_value=False),
        ))

        with patch("src.workers.sync_engine._get_session_factory", return_value=mock_factory), \
             patch("src.workers.sync_engine.GatewayDeploymentRepository", return_value=mock_repo), \
             patch("src.workers.sync_engine.GatewayInstanceRepository", return_value=mock_gw_repo), \
             patch("src.workers.sync_engine.AdapterRegistry") as mock_registry:

            mock_registry.create.return_value = adapter

            from src.workers.sync_engine import SyncEngine

            engine = SyncEngine()
            engine._semaphore = MagicMock()
            engine._semaphore.__aenter__ = AsyncMock()
            engine._semaphore.__aexit__ = AsyncMock()

            await engine._reconcile_one(deployment.id)

            adapter.delete_api.assert_awaited_once_with("gw-api-99")
            mock_repo.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reconcile_delete_failure(self):
        """DELETING deployment failure increments attempts."""
        deployment = self._make_deployment(
            sync_status=DeploymentSyncStatus.DELETING,
            gateway_resource_id="gw-api-99",
        )
        gateway = self._make_gateway(id=deployment.gateway_instance_id)
        adapter = self._make_adapter(
            delete_result=AdapterResult(success=False, error="Gateway timeout")
        )

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=deployment)
        mock_repo.update = AsyncMock(return_value=deployment)

        mock_gw_repo = MagicMock()
        mock_gw_repo.get_by_id = AsyncMock(return_value=gateway)

        mock_factory = MagicMock(return_value=MagicMock(
            __aenter__=AsyncMock(return_value=mock_session),
            __aexit__=AsyncMock(return_value=False),
        ))

        with patch("src.workers.sync_engine._get_session_factory", return_value=mock_factory), \
             patch("src.workers.sync_engine.GatewayDeploymentRepository", return_value=mock_repo), \
             patch("src.workers.sync_engine.GatewayInstanceRepository", return_value=mock_gw_repo), \
             patch("src.workers.sync_engine.AdapterRegistry") as mock_registry:

            mock_registry.create.return_value = adapter

            from src.workers.sync_engine import SyncEngine

            engine = SyncEngine()
            engine._semaphore = MagicMock()
            engine._semaphore.__aenter__ = AsyncMock()
            engine._semaphore.__aexit__ = AsyncMock()

            await engine._reconcile_one(deployment.id)

            assert deployment.sync_attempts == 1
            assert deployment.sync_error == "Gateway timeout"

    @pytest.mark.asyncio
    async def test_reconcile_skips_max_retries(self):
        """ERROR deployment with max retries is skipped."""
        deployment = self._make_deployment(
            sync_status=DeploymentSyncStatus.ERROR,
            sync_attempts=3,
        )

        mock_session = AsyncMock()
        mock_repo = MagicMock()
        mock_repo.list_by_statuses = AsyncMock(return_value=[deployment])

        mock_factory = MagicMock(return_value=MagicMock(
            __aenter__=AsyncMock(return_value=mock_session),
            __aexit__=AsyncMock(return_value=False),
        ))

        with patch("src.workers.sync_engine._get_session_factory", return_value=mock_factory), \
             patch("src.workers.sync_engine.GatewayDeploymentRepository", return_value=mock_repo), \
             patch("src.workers.sync_engine.settings") as mock_settings:

            mock_settings.SYNC_ENGINE_RETRY_MAX = 3

            from src.workers.sync_engine import SyncEngine

            engine = SyncEngine()
            engine._reconcile_one = AsyncMock()

            await engine._reconcile_all()

            # _reconcile_one should NOT be called since deployment exceeded retries
            engine._reconcile_one.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_drift_detect_hash_mismatch(self):
        """SYNCED deployment with spec hash mismatch is marked DRIFTED."""
        deployment = self._make_deployment(
            sync_status=DeploymentSyncStatus.SYNCED,
            gateway_resource_id="gw-api-1",
            desired_state={"spec_hash": "desired-hash", "tenant_id": "acme"},
        )
        gateway = self._make_gateway(id=deployment.gateway_instance_id)

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_repo = MagicMock()
        mock_repo.list_synced = AsyncMock(return_value=[deployment])
        mock_repo.update = AsyncMock(return_value=deployment)

        mock_gw_repo = MagicMock()
        mock_gw_repo.get_by_id = AsyncMock(return_value=gateway)

        # Gateway reports a different spec_hash
        adapter = self._make_adapter(
            list_apis_result=[{"id": "gw-api-1", "spec_hash": "actual-different-hash"}]
        )

        mock_factory = MagicMock(return_value=MagicMock(
            __aenter__=AsyncMock(return_value=mock_session),
            __aexit__=AsyncMock(return_value=False),
        ))

        with patch("src.workers.sync_engine._get_session_factory", return_value=mock_factory), \
             patch("src.workers.sync_engine.GatewayDeploymentRepository", return_value=mock_repo), \
             patch("src.workers.sync_engine.GatewayInstanceRepository", return_value=mock_gw_repo), \
             patch("src.workers.sync_engine.AdapterRegistry") as mock_registry, \
             patch("src.workers.sync_engine.kafka_service") as mock_kafka:

            mock_registry.create.return_value = adapter
            mock_kafka.publish = AsyncMock()

            from src.workers.sync_engine import SyncEngine

            engine = SyncEngine()

            await engine._detect_drift()

            assert deployment.sync_status == DeploymentSyncStatus.DRIFTED
            assert "mismatch" in deployment.sync_error

    @pytest.mark.asyncio
    async def test_drift_detect_api_missing(self):
        """SYNCED deployment whose API is gone from gateway is marked DRIFTED."""
        deployment = self._make_deployment(
            sync_status=DeploymentSyncStatus.SYNCED,
            gateway_resource_id="gw-api-gone",
            desired_state={"spec_hash": "abc123", "tenant_id": "acme"},
        )
        gateway = self._make_gateway(id=deployment.gateway_instance_id)

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_repo = MagicMock()
        mock_repo.list_synced = AsyncMock(return_value=[deployment])
        mock_repo.update = AsyncMock(return_value=deployment)

        mock_gw_repo = MagicMock()
        mock_gw_repo.get_by_id = AsyncMock(return_value=gateway)

        # Gateway returns empty list — API was deleted externally
        adapter = self._make_adapter(list_apis_result=[])

        mock_factory = MagicMock(return_value=MagicMock(
            __aenter__=AsyncMock(return_value=mock_session),
            __aexit__=AsyncMock(return_value=False),
        ))

        with patch("src.workers.sync_engine._get_session_factory", return_value=mock_factory), \
             patch("src.workers.sync_engine.GatewayDeploymentRepository", return_value=mock_repo), \
             patch("src.workers.sync_engine.GatewayInstanceRepository", return_value=mock_gw_repo), \
             patch("src.workers.sync_engine.AdapterRegistry") as mock_registry, \
             patch("src.workers.sync_engine.kafka_service") as mock_kafka:

            mock_registry.create.return_value = adapter
            mock_kafka.publish = AsyncMock()

            from src.workers.sync_engine import SyncEngine

            engine = SyncEngine()

            await engine._detect_drift()

            assert deployment.sync_status == DeploymentSyncStatus.DRIFTED
            assert "not found on gateway" in deployment.sync_error

    @pytest.mark.asyncio
    async def test_reconcile_skips_offline_gateway(self):
        """Deployment targeting offline gateway is skipped (no adapter calls)."""
        deployment = self._make_deployment(sync_status=DeploymentSyncStatus.PENDING)
        gateway = self._make_gateway(
            id=deployment.gateway_instance_id,
            status=GatewayInstanceStatus.OFFLINE,
        )

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=deployment)

        mock_gw_repo = MagicMock()
        mock_gw_repo.get_by_id = AsyncMock(return_value=gateway)

        mock_factory = MagicMock(return_value=MagicMock(
            __aenter__=AsyncMock(return_value=mock_session),
            __aexit__=AsyncMock(return_value=False),
        ))

        with patch("src.workers.sync_engine._get_session_factory", return_value=mock_factory), \
             patch("src.workers.sync_engine.GatewayDeploymentRepository", return_value=mock_repo), \
             patch("src.workers.sync_engine.GatewayInstanceRepository", return_value=mock_gw_repo), \
             patch("src.workers.sync_engine.AdapterRegistry") as mock_registry:

            from src.workers.sync_engine import SyncEngine

            engine = SyncEngine()
            engine._semaphore = MagicMock()
            engine._semaphore.__aenter__ = AsyncMock()
            engine._semaphore.__aexit__ = AsyncMock()

            await engine._reconcile_one(deployment.id)

            # AdapterRegistry.create should NOT be called for offline gateway
            mock_registry.create.assert_not_called()
