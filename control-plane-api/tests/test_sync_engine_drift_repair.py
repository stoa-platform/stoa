"""Tests for SyncEngine drift auto-repair (CAB-2016)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.models.gateway_deployment import DeploymentSyncStatus
from src.models.gateway_instance import GatewayInstanceStatus


class TestDriftAutoRepair:
    """Tests for drift detection + auto-repair modes."""

    def _make_deployment(self, **overrides):
        defaults = {
            "id": uuid4(),
            "api_catalog_id": uuid4(),
            "gateway_instance_id": uuid4(),
            "desired_state": {"spec_hash": "desired-hash", "tenant_id": "acme", "api_name": "my-api"},
            "actual_state": None,
            "sync_status": DeploymentSyncStatus.SYNCED,
            "sync_attempts": 0,
            "sync_error": None,
            "sync_steps": None,
            "gateway_resource_id": "gw-api-1",
            "last_sync_attempt": None,
            "last_sync_success": None,
            "desired_at": datetime.now(UTC),
            "desired_generation": 1,
            "attempted_generation": 1,
            "synced_generation": 1,
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    def _make_gateway(self, **overrides):
        defaults = {
            "id": uuid4(),
            "name": "kong-prod",
            "gateway_type": MagicMock(value="kong"),
            "base_url": "http://kong:8001",
            "auth_config": {},
            "status": GatewayInstanceStatus.ONLINE,
            "source": None,
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    def _make_adapter(self, list_apis_result=None):
        adapter = MagicMock()
        adapter.connect = AsyncMock()
        adapter.disconnect = AsyncMock()
        adapter.list_apis = AsyncMock(return_value=list_apis_result or [])
        return adapter

    def _setup_detect_drift_mocks(self, deployment, gateway, adapter):
        """Return context managers for _detect_drift."""
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_repo = MagicMock()
        mock_repo.list_synced = AsyncMock(return_value=[deployment])
        mock_repo.update = AsyncMock(return_value=deployment)

        mock_gw_repo = MagicMock()
        mock_gw_repo.get_by_id = AsyncMock(return_value=gateway)

        mock_factory = MagicMock(
            return_value=MagicMock(
                __aenter__=AsyncMock(return_value=mock_session),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        return mock_factory, mock_repo, mock_gw_repo

    @pytest.mark.asyncio
    async def test_drift_no_repair_mode_none(self):
        """DRIFT_AUTO_REPAIR=none: drift detected, Kafka event emitted, no Git write."""
        deployment = self._make_deployment()
        gateway = self._make_gateway(id=deployment.gateway_instance_id)
        adapter = self._make_adapter(list_apis_result=[{"id": "gw-api-1", "spec_hash": "actual-different-hash"}])
        mock_factory, mock_repo, mock_gw_repo = self._setup_detect_drift_mocks(deployment, gateway, adapter)

        mock_gh = MagicMock()
        mock_gh.connect = AsyncMock()
        mock_gh.batch_commit = AsyncMock()
        mock_gh.disconnect = AsyncMock()

        with (
            patch("src.workers.sync_engine._get_session_factory", return_value=mock_factory),
            patch("src.workers.sync_engine.GatewayDeploymentRepository", return_value=mock_repo),
            patch("src.workers.sync_engine.GatewayInstanceRepository", return_value=mock_gw_repo),
            patch(
                "src.workers.sync_engine.create_adapter_with_credentials", new_callable=AsyncMock, return_value=adapter
            ),
            patch("src.workers.sync_engine.kafka_service") as mock_kafka,
            patch("src.workers.sync_engine.settings") as mock_settings,
            patch("src.services.github_service.GitHubService", return_value=mock_gh),
        ):
            mock_kafka.publish = AsyncMock()
            mock_settings.DRIFT_AUTO_REPAIR = "none"

            from src.workers.sync_engine import SyncEngine

            engine = SyncEngine()
            await engine._detect_drift()

            assert deployment.sync_status == DeploymentSyncStatus.DRIFTED
            mock_kafka.publish.assert_awaited()  # drift-detected event
            mock_gh.batch_commit.assert_not_awaited()  # no Git write

    @pytest.mark.asyncio
    async def test_drift_auto_commit(self):
        """DRIFT_AUTO_REPAIR=commit: drift detected → auto-commit to Git."""
        deployment = self._make_deployment()
        gateway = self._make_gateway(id=deployment.gateway_instance_id)
        adapter = self._make_adapter(list_apis_result=[{"id": "gw-api-1", "spec_hash": "actual-different-hash"}])
        mock_factory, mock_repo, mock_gw_repo = self._setup_detect_drift_mocks(deployment, gateway, adapter)

        mock_gh = MagicMock()
        mock_gh.connect = AsyncMock()
        mock_gh.batch_commit = AsyncMock(return_value={"sha": "abc123", "url": "http://..."})
        mock_gh.disconnect = AsyncMock()
        mock_gh._catalog_project_id = MagicMock(return_value="stoa-platform/stoa-catalog")

        with (
            patch("src.workers.sync_engine._get_session_factory", return_value=mock_factory),
            patch("src.workers.sync_engine.GatewayDeploymentRepository", return_value=mock_repo),
            patch("src.workers.sync_engine.GatewayInstanceRepository", return_value=mock_gw_repo),
            patch(
                "src.workers.sync_engine.create_adapter_with_credentials", new_callable=AsyncMock, return_value=adapter
            ),
            patch("src.workers.sync_engine.kafka_service") as mock_kafka,
            patch("src.workers.sync_engine.settings") as mock_settings,
            patch("src.services.github_service.GitHubService", return_value=mock_gh),
        ):
            mock_kafka.publish = AsyncMock()
            mock_settings.DRIFT_AUTO_REPAIR = "commit"

            from src.workers.sync_engine import SyncEngine

            engine = SyncEngine()
            await engine._detect_drift()

            assert deployment.sync_status == DeploymentSyncStatus.DRIFTED
            mock_gh.batch_commit.assert_awaited_once()
            # Verify the commit message contains the API name
            call_args = mock_gh.batch_commit.call_args
            assert "my-api" in call_args[0][2]  # commit message

    @pytest.mark.asyncio
    async def test_drift_auto_pr(self):
        """DRIFT_AUTO_REPAIR=pr: drift detected → PR created."""
        deployment = self._make_deployment()
        gateway = self._make_gateway(id=deployment.gateway_instance_id)
        adapter = self._make_adapter(list_apis_result=[{"id": "gw-api-1", "spec_hash": "actual-different-hash"}])
        mock_factory, mock_repo, mock_gw_repo = self._setup_detect_drift_mocks(deployment, gateway, adapter)

        mock_gh = MagicMock()
        mock_gh.connect = AsyncMock()
        mock_gh.create_pull_request = AsyncMock(return_value={"pr_number": 42, "url": "http://..."})
        mock_gh.disconnect = AsyncMock()
        mock_gh._catalog_project_id = MagicMock(return_value="stoa-platform/stoa-catalog")

        with (
            patch("src.workers.sync_engine._get_session_factory", return_value=mock_factory),
            patch("src.workers.sync_engine.GatewayDeploymentRepository", return_value=mock_repo),
            patch("src.workers.sync_engine.GatewayInstanceRepository", return_value=mock_gw_repo),
            patch(
                "src.workers.sync_engine.create_adapter_with_credentials", new_callable=AsyncMock, return_value=adapter
            ),
            patch("src.workers.sync_engine.kafka_service") as mock_kafka,
            patch("src.workers.sync_engine.settings") as mock_settings,
            patch("src.services.github_service.GitHubService", return_value=mock_gh),
        ):
            mock_kafka.publish = AsyncMock()
            mock_settings.DRIFT_AUTO_REPAIR = "pr"

            from src.workers.sync_engine import SyncEngine

            engine = SyncEngine()
            await engine._detect_drift()

            assert deployment.sync_status == DeploymentSyncStatus.DRIFTED
            mock_gh.create_pull_request.assert_awaited_once()
            call_kwargs = mock_gh.create_pull_request.call_args
            assert "drift/" in call_kwargs[1]["branch"] or "drift/" in call_kwargs[0][1]

    @pytest.mark.asyncio
    async def test_drift_repair_git_error_graceful(self):
        """Git error during repair is logged but doesn't crash the engine."""
        deployment = self._make_deployment()
        gateway = self._make_gateway(id=deployment.gateway_instance_id)
        adapter = self._make_adapter(list_apis_result=[{"id": "gw-api-1", "spec_hash": "actual-different-hash"}])
        mock_factory, mock_repo, mock_gw_repo = self._setup_detect_drift_mocks(deployment, gateway, adapter)

        mock_gh = MagicMock()
        mock_gh.connect = AsyncMock(side_effect=ConnectionError("GitHub unreachable"))

        with (
            patch("src.workers.sync_engine._get_session_factory", return_value=mock_factory),
            patch("src.workers.sync_engine.GatewayDeploymentRepository", return_value=mock_repo),
            patch("src.workers.sync_engine.GatewayInstanceRepository", return_value=mock_gw_repo),
            patch(
                "src.workers.sync_engine.create_adapter_with_credentials", new_callable=AsyncMock, return_value=adapter
            ),
            patch("src.workers.sync_engine.kafka_service") as mock_kafka,
            patch("src.workers.sync_engine.settings") as mock_settings,
            patch("src.services.github_service.GitHubService", return_value=mock_gh),
        ):
            mock_kafka.publish = AsyncMock()
            mock_settings.DRIFT_AUTO_REPAIR = "commit"

            from src.workers.sync_engine import SyncEngine

            engine = SyncEngine()
            # Should NOT raise — error is caught and logged
            await engine._detect_drift()

            # Drift is still detected even though repair failed
            assert deployment.sync_status == DeploymentSyncStatus.DRIFTED

    @pytest.mark.asyncio
    async def test_drift_repair_emits_repaired_event(self):
        """Successful repair emits a drift-repaired Kafka event."""
        deployment = self._make_deployment()
        gateway = self._make_gateway(id=deployment.gateway_instance_id)
        adapter = self._make_adapter(list_apis_result=[{"id": "gw-api-1", "spec_hash": "actual-different-hash"}])
        mock_factory, mock_repo, mock_gw_repo = self._setup_detect_drift_mocks(deployment, gateway, adapter)

        mock_gh = MagicMock()
        mock_gh.connect = AsyncMock()
        mock_gh.batch_commit = AsyncMock(return_value={"sha": "abc", "url": "http://..."})
        mock_gh.disconnect = AsyncMock()
        mock_gh._catalog_project_id = MagicMock(return_value="stoa-platform/stoa-catalog")

        with (
            patch("src.workers.sync_engine._get_session_factory", return_value=mock_factory),
            patch("src.workers.sync_engine.GatewayDeploymentRepository", return_value=mock_repo),
            patch("src.workers.sync_engine.GatewayInstanceRepository", return_value=mock_gw_repo),
            patch(
                "src.workers.sync_engine.create_adapter_with_credentials", new_callable=AsyncMock, return_value=adapter
            ),
            patch("src.workers.sync_engine.kafka_service") as mock_kafka,
            patch("src.workers.sync_engine.settings") as mock_settings,
            patch("src.services.github_service.GitHubService", return_value=mock_gh),
        ):
            mock_kafka.publish = AsyncMock()
            mock_settings.DRIFT_AUTO_REPAIR = "commit"

            from src.workers.sync_engine import SyncEngine

            engine = SyncEngine()
            await engine._detect_drift()

            # Should have 2 publish calls: drift-detected + drift-repaired
            publish_calls = mock_kafka.publish.call_args_list
            event_types = [call.kwargs.get("event_type") or call[1].get("event_type") for call in publish_calls]
            assert "drift-detected" in event_types
            assert "drift-repaired" in event_types
