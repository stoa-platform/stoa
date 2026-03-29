"""Regression tests for sync engine — agent-managed gateway skip (CAB-1921).

The sync engine must skip self_register gateways because stoa-connect
agents handle sync themselves (pull-based). Without this, the engine
tries to connect to internal/unreachable base_urls and causes 500 errors.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.gateway_instance import GatewayInstanceStatus
from src.services.credential_resolver import AgentManagedGatewayError


@pytest.mark.asyncio
async def test_regression_sync_engine_skips_self_register_gateways():
    """Sync engine must skip self_register gateways (stoa-connect agents).

    Regression: sync engine called sync_api() on agent-managed gateways
    with unreachable base_urls (e.g. http://connect-webmethods-dev:8090),
    causing DNS resolution errors and 500s on /v1/admin/deployments.

    The centralized guard in create_adapter_with_credentials() raises
    AgentManagedGatewayError, which _reconcile_one() catches and skips.
    """
    from src.workers.sync_engine import SyncEngine

    engine = SyncEngine()
    engine._semaphore = MagicMock()
    engine._semaphore.__aenter__ = AsyncMock()
    engine._semaphore.__aexit__ = AsyncMock()

    # Mock a self_register gateway (stoa-connect agent)
    mock_gateway = MagicMock()
    mock_gateway.status = GatewayInstanceStatus.ONLINE
    mock_gateway.source = "self_register"
    mock_gateway.name = "connect-webmethods-dev"
    mock_gateway.base_url = "http://connect-webmethods-dev:8090"
    mock_gateway.auth_config = {}
    mock_gateway.gateway_type.value = "webmethods"

    # Mock a pending deployment
    mock_deployment = MagicMock()
    mock_deployment.id = "04e092cb-cdfa-4f56-9ad9-67b90cbf5ae1"
    mock_deployment.gateway_instance_id = "16f562ca-b2c3-46cb-93ed-d01ba6d46e18"
    mock_deployment.sync_status = "pending"

    with (
        patch("src.workers.sync_engine._get_session_factory") as mock_sf,
        patch("src.workers.sync_engine.GatewayDeploymentRepository") as mock_dep_repo_cls,
        patch("src.workers.sync_engine.GatewayInstanceRepository") as mock_gw_repo_cls,
        patch(
            "src.workers.sync_engine.create_adapter_with_credentials",
            new_callable=AsyncMock,
            side_effect=AgentManagedGatewayError("connect-webmethods-dev"),
        ) as mock_create_adapter,
    ):
        # Set up async context manager for session
        mock_session = AsyncMock()
        mock_session_factory = MagicMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock()
        mock_session_factory.return_value = mock_session_ctx
        mock_sf.return_value = mock_session_factory

        mock_dep_repo = AsyncMock()
        mock_dep_repo.get_by_id.return_value = mock_deployment
        mock_dep_repo_cls.return_value = mock_dep_repo

        mock_gw_repo = AsyncMock()
        mock_gw_repo.get_by_id.return_value = mock_gateway
        mock_gw_repo_cls.return_value = mock_gw_repo

        await engine._reconcile_one(mock_deployment.id)

        # The adapter factory is called but raises AgentManagedGatewayError,
        # which _reconcile_one catches and skips — no sync_api() call
        mock_create_adapter.assert_awaited_once()
        # Verify source was passed to the centralized guard
        call_kwargs = mock_create_adapter.call_args
        assert call_kwargs.kwargs["source"] == "self_register"


@pytest.mark.asyncio
async def test_regression_centralized_guard_raises_for_self_register():
    """create_adapter_with_credentials() raises AgentManagedGatewayError for self_register."""
    from src.services.credential_resolver import create_adapter_with_credentials

    with pytest.raises(AgentManagedGatewayError, match="agent-managed"):
        await create_adapter_with_credentials(
            "webmethods",
            "http://connect-webmethods-dev:8090",
            {},
            source="self_register",
            gateway_name="connect-webmethods-dev",
        )


@pytest.mark.asyncio
async def test_regression_centralized_guard_allows_non_self_register():
    """create_adapter_with_credentials() proceeds normally for non-self_register gateways."""
    from src.services.credential_resolver import create_adapter_with_credentials

    with patch("src.services.credential_resolver.AdapterRegistry") as mock_registry:
        mock_registry.create.return_value = MagicMock()
        adapter = await create_adapter_with_credentials(
            "kong",
            "http://kong:8001",
            {"token": "secret"},
            source="manual",
            gateway_name="kong-prod",
        )
        assert adapter is not None
        mock_registry.create.assert_called_once()
