"""Tests for SyncEngine — reconciliation and drift detection."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

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
            "sync_steps": None,
            "gateway_resource_id": None,
            "last_sync_attempt": None,
            "last_sync_success": None,
            "desired_at": datetime.now(UTC),
            "desired_generation": 1,
            "attempted_generation": 0,
            "synced_generation": 0,
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
            return_value=sync_result
            or AdapterResult(success=True, resource_id="gw-api-1", data={"spec_hash": "abc123"})
        )
        adapter.delete_api = AsyncMock(return_value=delete_result or AdapterResult(success=True))
        adapter.list_apis = AsyncMock(return_value=list_apis_result or [])
        adapter.upsert_policy = AsyncMock()
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

        mock_factory = MagicMock(
            return_value=MagicMock(
                __aenter__=AsyncMock(return_value=mock_session),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        with (
            patch("src.workers.sync_engine._get_session_factory", return_value=mock_factory),
            patch("src.workers.sync_engine.GatewayDeploymentRepository", return_value=mock_repo),
            patch("src.workers.sync_engine.GatewayInstanceRepository", return_value=mock_gw_repo),
            patch(
                "src.workers.sync_engine.create_adapter_with_credentials", new_callable=AsyncMock, return_value=adapter
            ),
        ):

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
        adapter = self._make_adapter(sync_result=AdapterResult(success=False, error="Connection refused"))

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=deployment)
        mock_repo.update = AsyncMock(return_value=deployment)

        mock_gw_repo = MagicMock()
        mock_gw_repo.get_by_id = AsyncMock(return_value=gateway)

        mock_factory = MagicMock(
            return_value=MagicMock(
                __aenter__=AsyncMock(return_value=mock_session),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        with (
            patch("src.workers.sync_engine._get_session_factory", return_value=mock_factory),
            patch("src.workers.sync_engine.GatewayDeploymentRepository", return_value=mock_repo),
            patch("src.workers.sync_engine.GatewayInstanceRepository", return_value=mock_gw_repo),
            patch(
                "src.workers.sync_engine.create_adapter_with_credentials", new_callable=AsyncMock, return_value=adapter
            ),
        ):

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
    async def test_reconcile_error_retries_same_generation_before_max_retries(self):
        """ERROR deployments must retry even when the current generation was already attempted."""
        deployment = self._make_deployment(
            sync_status=DeploymentSyncStatus.ERROR,
            sync_attempts=1,
            desired_generation=3,
            attempted_generation=3,
        )
        gateway = self._make_gateway(id=deployment.gateway_instance_id)
        adapter = self._make_adapter()

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=deployment)
        mock_repo.update = AsyncMock(return_value=deployment)

        mock_gw_repo = MagicMock()
        mock_gw_repo.get_by_id = AsyncMock(return_value=gateway)

        mock_factory = MagicMock(
            return_value=MagicMock(
                __aenter__=AsyncMock(return_value=mock_session),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        with (
            patch("src.workers.sync_engine._get_session_factory", return_value=mock_factory),
            patch("src.workers.sync_engine.GatewayDeploymentRepository", return_value=mock_repo),
            patch("src.workers.sync_engine.GatewayInstanceRepository", return_value=mock_gw_repo),
            patch(
                "src.workers.sync_engine.create_adapter_with_credentials", new_callable=AsyncMock, return_value=adapter
            ),
        ):
            from src.workers.sync_engine import SyncEngine

            engine = SyncEngine()
            engine._semaphore = MagicMock()
            engine._semaphore.__aenter__ = AsyncMock()
            engine._semaphore.__aexit__ = AsyncMock()

            await engine._reconcile_one(deployment.id)

        adapter.sync_api.assert_awaited_once()
        assert deployment.sync_status == DeploymentSyncStatus.SYNCED

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

        mock_factory = MagicMock(
            return_value=MagicMock(
                __aenter__=AsyncMock(return_value=mock_session),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        with (
            patch("src.workers.sync_engine._get_session_factory", return_value=mock_factory),
            patch("src.workers.sync_engine.GatewayDeploymentRepository", return_value=mock_repo),
            patch("src.workers.sync_engine.GatewayInstanceRepository", return_value=mock_gw_repo),
            patch(
                "src.workers.sync_engine.create_adapter_with_credentials", new_callable=AsyncMock, return_value=adapter
            ),
        ):

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
        adapter = self._make_adapter(delete_result=AdapterResult(success=False, error="Gateway timeout"))

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=deployment)
        mock_repo.update = AsyncMock(return_value=deployment)

        mock_gw_repo = MagicMock()
        mock_gw_repo.get_by_id = AsyncMock(return_value=gateway)

        mock_factory = MagicMock(
            return_value=MagicMock(
                __aenter__=AsyncMock(return_value=mock_session),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        with (
            patch("src.workers.sync_engine._get_session_factory", return_value=mock_factory),
            patch("src.workers.sync_engine.GatewayDeploymentRepository", return_value=mock_repo),
            patch("src.workers.sync_engine.GatewayInstanceRepository", return_value=mock_gw_repo),
            patch(
                "src.workers.sync_engine.create_adapter_with_credentials", new_callable=AsyncMock, return_value=adapter
            ),
        ):

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

        mock_factory = MagicMock(
            return_value=MagicMock(
                __aenter__=AsyncMock(return_value=mock_session),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        with (
            patch("src.workers.sync_engine._get_session_factory", return_value=mock_factory),
            patch("src.workers.sync_engine.GatewayDeploymentRepository", return_value=mock_repo),
            patch("src.workers.sync_engine.settings") as mock_settings,
        ):

            mock_settings.SYNC_ENGINE_RETRY_MAX = 3
            mock_settings.SYNC_ENGINE_INTERVAL_SECONDS = 300

            from src.workers.sync_engine import SyncEngine

            engine = SyncEngine()
            engine._reconcile_one = AsyncMock()

            await engine._reconcile_all()

            # _reconcile_one should NOT be called since deployment exceeded retries
            engine._reconcile_one.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reconcile_all_expires_stale_pending_deployment(self):
        """PENDING/SYNCING deployments must not stay pending forever."""
        deployment = self._make_deployment(
            sync_status=DeploymentSyncStatus.PENDING,
            sync_attempts=0,
            last_sync_attempt=datetime.now(UTC) - timedelta(seconds=7200),
        )

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_repo = MagicMock()
        mock_repo.list_by_statuses = AsyncMock(return_value=[deployment])
        mock_repo.update = AsyncMock(return_value=deployment)

        mock_factory = MagicMock(
            return_value=MagicMock(
                __aenter__=AsyncMock(return_value=mock_session),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        with (
            patch("src.workers.sync_engine._get_session_factory", return_value=mock_factory),
            patch("src.workers.sync_engine.GatewayDeploymentRepository", return_value=mock_repo),
            patch("src.workers.sync_engine.settings") as mock_settings,
        ):
            mock_settings.SYNC_ENGINE_RETRY_MAX = 3
            mock_settings.SYNC_ENGINE_INTERVAL_SECONDS = 300
            mock_settings.SYNC_ENGINE_PENDING_TIMEOUT_SECONDS = 3600

            from src.workers.sync_engine import SyncEngine

            engine = SyncEngine()
            engine._reconcile_one = AsyncMock()

            await engine._reconcile_all()

        assert deployment.sync_status == DeploymentSyncStatus.ERROR
        assert "did not acknowledge" in deployment.sync_error
        assert deployment.sync_attempts == 3
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
        adapter = self._make_adapter(list_apis_result=[{"id": "gw-api-1", "spec_hash": "actual-different-hash"}])

        mock_factory = MagicMock(
            return_value=MagicMock(
                __aenter__=AsyncMock(return_value=mock_session),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        with (
            patch("src.workers.sync_engine._get_session_factory", return_value=mock_factory),
            patch("src.workers.sync_engine.GatewayDeploymentRepository", return_value=mock_repo),
            patch("src.workers.sync_engine.GatewayInstanceRepository", return_value=mock_gw_repo),
            patch(
                "src.workers.sync_engine.create_adapter_with_credentials", new_callable=AsyncMock, return_value=adapter
            ),
            patch("src.workers.sync_engine.kafka_service") as mock_kafka,
        ):

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

        mock_factory = MagicMock(
            return_value=MagicMock(
                __aenter__=AsyncMock(return_value=mock_session),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        with (
            patch("src.workers.sync_engine._get_session_factory", return_value=mock_factory),
            patch("src.workers.sync_engine.GatewayDeploymentRepository", return_value=mock_repo),
            patch("src.workers.sync_engine.GatewayInstanceRepository", return_value=mock_gw_repo),
            patch(
                "src.workers.sync_engine.create_adapter_with_credentials", new_callable=AsyncMock, return_value=adapter
            ),
            patch("src.workers.sync_engine.kafka_service") as mock_kafka,
        ):

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

        mock_factory = MagicMock(
            return_value=MagicMock(
                __aenter__=AsyncMock(return_value=mock_session),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        with (
            patch("src.workers.sync_engine._get_session_factory", return_value=mock_factory),
            patch("src.workers.sync_engine.GatewayDeploymentRepository", return_value=mock_repo),
            patch("src.workers.sync_engine.GatewayInstanceRepository", return_value=mock_gw_repo),
            patch("src.workers.sync_engine.create_adapter_with_credentials", new_callable=AsyncMock) as mock_create,
        ):

            from src.workers.sync_engine import SyncEngine

            engine = SyncEngine()
            engine._semaphore = MagicMock()
            engine._semaphore.__aenter__ = AsyncMock()
            engine._semaphore.__aexit__ = AsyncMock()

            await engine._reconcile_one(deployment.id)

            # create_adapter_with_credentials should NOT be called for offline gateway
            mock_create.assert_not_awaited()


class TestSyncStepInstrumentation(TestSyncEngine):
    """Tests for sync step tracing in the reconciliation pipeline (CAB-1946)."""

    def _make_policy(self, **overrides):
        """Create a mock GatewayPolicy."""
        defaults = {
            "id": uuid4(),
            "name": "rate-limit",
            "policy_type": MagicMock(value="rate_limit"),
            "config": {"limit": 100},
            "priority": 1,
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    async def _run_reconcile(self, deployment, gateway, adapter, policy_repo=None):
        """Run _reconcile_one with standard mocks and return the deployment."""
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=deployment)
        mock_repo.update = AsyncMock(return_value=deployment)

        mock_gw_repo = MagicMock()
        mock_gw_repo.get_by_id = AsyncMock(return_value=gateway)

        if policy_repo is None:
            policy_repo = MagicMock()
            policy_repo.get_policies_for_deployment = AsyncMock(return_value=[])

        mock_factory = MagicMock(
            return_value=MagicMock(
                __aenter__=AsyncMock(return_value=mock_session),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        with (
            patch("src.workers.sync_engine._get_session_factory", return_value=mock_factory),
            patch("src.workers.sync_engine.GatewayDeploymentRepository", return_value=mock_repo),
            patch("src.workers.sync_engine.GatewayInstanceRepository", return_value=mock_gw_repo),
            patch(
                "src.workers.sync_engine.create_adapter_with_credentials", new_callable=AsyncMock, return_value=adapter
            ),
            patch("src.repositories.gateway_policy.GatewayPolicyRepository", return_value=policy_repo),
        ):

            from src.workers.sync_engine import SyncEngine

            engine = SyncEngine()
            engine._semaphore = MagicMock()
            engine._semaphore.__aenter__ = AsyncMock()
            engine._semaphore.__aexit__ = AsyncMock()

            await engine._reconcile_one(deployment.id)
            return deployment

    @pytest.mark.asyncio
    async def test_reconcile_produces_success_trace(self):
        """Successful sync produces 3-step trace: adapter_connected, api_synced, policies_applied."""
        deployment = self._make_deployment(sync_status=DeploymentSyncStatus.PENDING)
        gateway = self._make_gateway(id=deployment.gateway_instance_id)
        adapter = self._make_adapter()

        await self._run_reconcile(deployment, gateway, adapter)

        assert deployment.sync_status == DeploymentSyncStatus.SYNCED
        assert deployment.sync_steps is not None
        steps = deployment.sync_steps
        assert len(steps) == 3
        assert steps[0]["name"] == "adapter_connected"
        assert steps[0]["status"] == "success"
        assert steps[1]["name"] == "api_synced"
        assert steps[1]["status"] == "success"
        assert steps[2]["name"] == "policies_applied"
        assert steps[2]["status"] == "success"
        assert deployment.sync_error is None

    @pytest.mark.asyncio
    async def test_reconcile_adapter_failure_trace(self):
        """Adapter connect failure produces failed adapter_connected + skipped remaining steps."""
        deployment = self._make_deployment(sync_status=DeploymentSyncStatus.PENDING)
        gateway = self._make_gateway(id=deployment.gateway_instance_id)
        adapter = self._make_adapter()
        adapter.connect = AsyncMock(side_effect=ConnectionError("Connection refused"))

        await self._run_reconcile(deployment, gateway, adapter)

        assert deployment.sync_status == DeploymentSyncStatus.ERROR
        steps = deployment.sync_steps
        assert len(steps) == 3
        assert steps[0]["name"] == "adapter_connected"
        assert steps[0]["status"] == "failed"
        assert "Connection refused" in steps[0]["detail"]
        assert steps[1]["name"] == "api_synced"
        assert steps[1]["status"] == "skipped"
        assert steps[2]["name"] == "policies_applied"
        assert steps[2]["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_reconcile_sync_failure_trace(self):
        """sync_api failure produces failed api_synced + skipped policies_applied."""
        deployment = self._make_deployment(sync_status=DeploymentSyncStatus.PENDING)
        gateway = self._make_gateway(id=deployment.gateway_instance_id)
        adapter = self._make_adapter(sync_result=AdapterResult(success=False, error="Gateway timeout"))

        await self._run_reconcile(deployment, gateway, adapter)

        assert deployment.sync_status == DeploymentSyncStatus.ERROR
        steps = deployment.sync_steps
        assert len(steps) == 3
        assert steps[0]["name"] == "adapter_connected"
        assert steps[0]["status"] == "success"
        assert steps[1]["name"] == "api_synced"
        assert steps[1]["status"] == "failed"
        assert "Gateway timeout" in steps[1]["detail"]
        assert steps[2]["name"] == "policies_applied"
        assert steps[2]["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_reconcile_partial_policy_failure_trace(self):
        """Partial policy failure produces failed policies_applied with detail."""
        deployment = self._make_deployment(sync_status=DeploymentSyncStatus.PENDING)
        gateway = self._make_gateway(id=deployment.gateway_instance_id)
        adapter = self._make_adapter()
        adapter.upsert_policy = AsyncMock(side_effect=Exception("rate-limit rejected"))

        policy = self._make_policy()
        mock_policy_repo = MagicMock()
        mock_policy_repo.get_policies_for_deployment = AsyncMock(return_value=[policy])

        await self._run_reconcile(deployment, gateway, adapter, policy_repo=mock_policy_repo)

        assert deployment.sync_status == DeploymentSyncStatus.SYNCED
        steps = deployment.sync_steps
        assert len(steps) == 3
        assert steps[2]["name"] == "policies_applied"
        assert steps[2]["status"] == "failed"
        assert "rate-limit rejected" in steps[2]["detail"]

    @pytest.mark.asyncio
    async def test_sync_error_backward_compat(self):
        """sync_error is derived from tracker.first_error() for backward compatibility."""
        deployment = self._make_deployment(sync_status=DeploymentSyncStatus.PENDING)
        gateway = self._make_gateway(id=deployment.gateway_instance_id)
        adapter = self._make_adapter(sync_result=AdapterResult(success=False, error="502 Bad Gateway"))

        await self._run_reconcile(deployment, gateway, adapter)

        assert deployment.sync_error == "502 Bad Gateway"
        failed_steps = [s for s in deployment.sync_steps if s["status"] == "failed"]
        assert len(failed_steps) == 1
        assert failed_steps[0]["detail"] == deployment.sync_error
