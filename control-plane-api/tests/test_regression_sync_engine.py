"""Regression tests for sync engine — agent-managed gateway guard (CAB-1921 + CAB-2039).

The guard blocks only gateway_type="stoa" (pull-model, stoa-connect Go agent).
stoa_sidecar and stoa_edge_mcp are push-capable and must NOT be blocked,
even when source="self_register".
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.gateway_instance import GatewayInstanceStatus
from src.services.credential_resolver import AgentManagedGatewayError


@pytest.mark.asyncio
async def test_regression_sync_engine_skips_stoa_pull_model():
    """Sync engine must skip gateway_type=stoa + self_register gateways.

    These are stoa-connect Go agents that use a pull model. The centralized
    guard in create_adapter_with_credentials() raises AgentManagedGatewayError,
    which _reconcile_one() catches and skips.
    """
    from src.workers.sync_engine import SyncEngine

    engine = SyncEngine()
    engine._semaphore = MagicMock()
    engine._semaphore.__aenter__ = AsyncMock()
    engine._semaphore.__aexit__ = AsyncMock()

    # Mock a self_register gateway with type=stoa (pull model)
    mock_gateway = MagicMock()
    mock_gateway.status = GatewayInstanceStatus.ONLINE
    mock_gateway.source = "self_register"
    mock_gateway.name = "connect-webmethods-dev"
    mock_gateway.base_url = "http://connect-webmethods-dev:8090"
    mock_gateway.auth_config = {}
    mock_gateway.gateway_type.value = "stoa"

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

        mock_create_adapter.assert_awaited_once()
        call_kwargs = mock_create_adapter.call_args
        assert call_kwargs.kwargs["source"] == "self_register"


@pytest.mark.asyncio
async def test_regression_guard_raises_for_stoa_pull_model():
    """create_adapter_with_credentials() raises for type=stoa + self_register."""
    from src.services.credential_resolver import create_adapter_with_credentials

    with pytest.raises(AgentManagedGatewayError, match="agent-managed"):
        await create_adapter_with_credentials(
            "stoa",
            "http://connect-dev:8090",
            {},
            source="self_register",
            gateway_name="connect-dev",
        )


@pytest.mark.asyncio
async def test_regression_guard_allows_self_register_sidecar():
    """create_adapter_with_credentials() must NOT block stoa_sidecar even with self_register."""
    from src.services.credential_resolver import create_adapter_with_credentials

    with patch("src.services.credential_resolver.AdapterRegistry") as mock_registry:
        mock_registry.create.return_value = MagicMock()
        adapter = await create_adapter_with_credentials(
            "stoa_sidecar",
            "http://sidecar-dev:8090",
            {},
            source="self_register",
            gateway_name="sidecar-webmethods-dev",
        )
        assert adapter is not None
        mock_registry.create.assert_called_once()


@pytest.mark.asyncio
async def test_regression_guard_allows_self_register_edge_mcp():
    """create_adapter_with_credentials() must NOT block stoa_edge_mcp even with self_register."""
    from src.services.credential_resolver import create_adapter_with_credentials

    with patch("src.services.credential_resolver.AdapterRegistry") as mock_registry:
        mock_registry.create.return_value = MagicMock()
        adapter = await create_adapter_with_credentials(
            "stoa_edge_mcp",
            "http://edge-mcp-dev:8090",
            {},
            source="self_register",
            gateway_name="stoa-gateway-edge-mcp-dev",
        )
        assert adapter is not None
        mock_registry.create.assert_called_once()


@pytest.mark.asyncio
async def test_regression_guard_allows_self_register_webmethods():
    """create_adapter_with_credentials() must NOT block webmethods even with self_register.

    webMethods gateways registered via stoa-connect use push-based sync
    (the API pushes config to them). Only type=stoa uses the pull model.
    """
    from src.services.credential_resolver import create_adapter_with_credentials

    with patch("src.services.credential_resolver.AdapterRegistry") as mock_registry:
        mock_registry.create.return_value = MagicMock()
        adapter = await create_adapter_with_credentials(
            "webmethods",
            "http://connect-webmethods-dev:8090",
            {},
            source="self_register",
            gateway_name="connect-webmethods-dev",
        )
        assert adapter is not None
        mock_registry.create.assert_called_once()


@pytest.mark.asyncio
async def test_regression_guard_allows_non_self_register():
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
