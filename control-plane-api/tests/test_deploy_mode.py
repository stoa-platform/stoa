"""Tests for DEPLOY_MODE config, EventBus gateway filtering, and SSE deploy emission (ADR-059)."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.events.event_bus import EventBus, Subscriber

# --- DEPLOY_MODE config properties ---


class TestDeployModeConfig:
    """Tests for DEPLOY_MODE settings properties."""

    def test_default_is_legacy(self):
        from src.config import settings

        assert settings.DEPLOY_MODE == "legacy"

    @pytest.mark.parametrize(
        "mode,sse,sync,inline",
        [
            ("sse_only", True, False, False),
            ("dual", True, True, False),
            ("legacy", False, True, True),
        ],
    )
    def test_mode_properties(self, mode, sse, sync, inline):
        from src.config import settings

        original = settings.DEPLOY_MODE
        try:
            settings.DEPLOY_MODE = mode
            assert settings.is_sse_enabled is sse
            assert settings.is_sync_engine_enabled is sync
            assert settings.is_inline_sync_enabled is inline
        finally:
            settings.DEPLOY_MODE = original


# --- EventBus gateway_id filtering ---


class TestEventBusGatewayFilter:
    """Tests for EventBus gateway_id routing (ADR-059)."""

    def test_subscriber_accepts_matching_gateway_id(self):
        sub = Subscriber(gateway_id="gw-1")
        assert sub.accepts("tenant-1", "sync-deployment", gateway_id="gw-1")

    def test_subscriber_rejects_non_matching_gateway_id(self):
        sub = Subscriber(gateway_id="gw-1")
        assert not sub.accepts("tenant-1", "sync-deployment", gateway_id="gw-2")

    def test_subscriber_without_gateway_accepts_all(self):
        sub = Subscriber()
        assert sub.accepts("tenant-1", "sync-deployment", gateway_id="gw-1")
        assert sub.accepts("tenant-1", "sync-deployment", gateway_id="gw-2")
        assert sub.accepts("tenant-1", "sync-deployment")

    @pytest.mark.asyncio
    async def test_publish_routes_to_correct_gateway(self):
        bus = EventBus()
        sub1 = bus.subscribe(gateway_id="gw-1", event_types=["sync-deployment"])
        sub2 = bus.subscribe(gateway_id="gw-2", event_types=["sync-deployment"])

        delivered = await bus.publish("t1", "sync-deployment", {"id": "dep-1"}, gateway_id="gw-1")
        assert delivered == 1
        assert not sub1.queue.empty()
        assert sub2.queue.empty()


# --- SSE emission in deploy flow ---


class TestDeploySSEEmission:
    """Tests for SSE event emission during deployment."""

    def _make_deployment(self, **overrides):
        defaults = {
            "id": uuid4(),
            "api_catalog_id": uuid4(),
            "gateway_instance_id": uuid4(),
            "sync_status": MagicMock(value="pending"),
            "desired_state": {"api_name": "test", "tenant_id": "acme"},
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    @pytest.mark.asyncio
    async def test_emit_sse_events_publishes_to_event_bus(self):
        from src.services.gateway_deployment_service import GatewayDeploymentService

        dep = self._make_deployment()
        db = AsyncMock()
        svc = GatewayDeploymentService(db)

        with patch("src.events.event_bus.event_bus") as mock_bus:
            mock_bus.publish = AsyncMock(return_value=1)
            await svc._emit_sse_events([dep], "acme")

            mock_bus.publish.assert_called_once()
            call_kwargs = mock_bus.publish.call_args
            assert call_kwargs.kwargs["event_type"] == "sync-deployment"
            assert call_kwargs.kwargs["gateway_id"] == str(dep.gateway_instance_id)
            assert call_kwargs.kwargs["data"]["deployment_id"] == str(dep.id)

    @pytest.mark.asyncio
    async def test_deploy_api_emits_sse_in_sse_only_mode(self):
        from src.services.gateway_deployment_service import GatewayDeploymentService

        dep = self._make_deployment()
        db = AsyncMock()
        svc = GatewayDeploymentService(db)
        svc._emit_sse_events = AsyncMock()
        svc._emit_sync_requests = AsyncMock()

        with patch("src.services.gateway_deployment_service.settings") as mock_settings:
            mock_settings.is_sse_enabled = True
            mock_settings.is_sync_engine_enabled = False
            mock_settings.DEPLOY_MODE = "sse_only"

            catalog = MagicMock(id=uuid4(), api_name="test", tenant_id="acme")
            svc.deploy_repo = AsyncMock()
            svc.deploy_repo.get_by_api_and_gateway = AsyncMock(return_value=None)
            svc.deploy_repo.create = AsyncMock(return_value=dep)
            svc.gw_repo = AsyncMock()
            svc.gw_repo.get_by_id = AsyncMock(return_value=MagicMock(id=dep.gateway_instance_id))

            with (
                patch.object(svc, "build_desired_state", return_value={"api": "test"}),
                patch("src.services.gateway_deployment_service.select"),
                patch.object(db, "execute") as mock_exec,
            ):
                mock_exec.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=catalog))
                await svc.deploy_api(catalog.id, [dep.gateway_instance_id])

            svc._emit_sse_events.assert_called_once()
            svc._emit_sync_requests.assert_not_called()

    @pytest.mark.asyncio
    async def test_deploy_api_skips_sse_in_legacy_mode(self):
        from src.services.gateway_deployment_service import GatewayDeploymentService

        dep = self._make_deployment()
        db = AsyncMock()
        svc = GatewayDeploymentService(db)
        svc._emit_sse_events = AsyncMock()
        svc._emit_sync_requests = AsyncMock()

        with patch("src.services.gateway_deployment_service.settings") as mock_settings:
            mock_settings.is_sse_enabled = False
            mock_settings.is_sync_engine_enabled = True
            mock_settings.DEPLOY_MODE = "legacy"

            catalog = MagicMock(id=uuid4(), api_name="test", tenant_id="acme")
            svc.deploy_repo = AsyncMock()
            svc.deploy_repo.get_by_api_and_gateway = AsyncMock(return_value=None)
            svc.deploy_repo.create = AsyncMock(return_value=dep)
            svc.gw_repo = AsyncMock()
            svc.gw_repo.get_by_id = AsyncMock(return_value=MagicMock(id=dep.gateway_instance_id))

            with (
                patch.object(svc, "build_desired_state", return_value={"api": "test"}),
                patch("src.services.gateway_deployment_service.select"),
                patch.object(db, "execute") as mock_exec,
            ):
                mock_exec.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=catalog))
                await svc.deploy_api(catalog.id, [dep.gateway_instance_id])

            svc._emit_sse_events.assert_not_called()
            svc._emit_sync_requests.assert_called_once()


# --- Orchestration inline sync gating ---


class TestOrchestrationInlineSyncGating:
    """Tests for _try_inline_sync gating by DEPLOY_MODE."""

    @pytest.mark.asyncio
    async def test_skips_inline_sync_in_sse_mode(self):
        from src.services.deployment_orchestration_service import DeploymentOrchestrationService

        db = AsyncMock()
        svc = DeploymentOrchestrationService(db)
        svc._resolve_api_catalog = AsyncMock(
            return_value=MagicMock(id=uuid4(), api_name="test", api_id="test-v1", tenant_id="acme")
        )
        svc._try_inline_sync = AsyncMock()
        svc.deploy_svc = AsyncMock()
        svc.deploy_svc.deploy_api = AsyncMock(return_value=[MagicMock()])
        svc.assignment_repo = AsyncMock()
        svc.assignment_repo.list_auto_deploy = AsyncMock(return_value=[MagicMock(gateway_id=uuid4())])

        with patch("src.services.deployment_orchestration_service.settings") as mock_settings:
            mock_settings.is_inline_sync_enabled = False
            await svc.deploy_api_to_env("acme", "test-v1", "dev")

        svc._try_inline_sync.assert_not_called()

    @pytest.mark.asyncio
    async def test_calls_inline_sync_in_legacy_mode(self):
        from src.services.deployment_orchestration_service import DeploymentOrchestrationService

        db = AsyncMock()
        svc = DeploymentOrchestrationService(db)
        svc._resolve_api_catalog = AsyncMock(
            return_value=MagicMock(id=uuid4(), api_name="test", api_id="test-v1", tenant_id="acme")
        )
        svc._try_inline_sync = AsyncMock()
        svc.deploy_svc = AsyncMock()
        svc.deploy_svc.deploy_api = AsyncMock(return_value=[MagicMock()])
        svc.assignment_repo = AsyncMock()
        svc.assignment_repo.list_auto_deploy = AsyncMock(return_value=[MagicMock(gateway_id=uuid4())])

        with patch("src.services.deployment_orchestration_service.settings") as mock_settings:
            mock_settings.is_inline_sync_enabled = True
            await svc.deploy_api_to_env("acme", "test-v1", "dev")

        svc._try_inline_sync.assert_called_once()
