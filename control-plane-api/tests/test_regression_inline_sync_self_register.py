"""Regression: _try_inline_sync must skip agent-managed (self_register) gateways.

Before this fix, inline sync attempted HTTP calls to agent-managed gateways
whose base_url is a Docker-internal hostname (e.g. http://connect-webmethods:8090),
causing [Errno -2] DNS resolution failures from the CP API pod.

Now handled by the centralized AgentManagedGatewayError guard in
create_adapter_with_credentials() (credential_resolver.py).
"""
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.services.credential_resolver import AgentManagedGatewayError


@pytest.mark.asyncio
async def test_regression_inline_sync_skips_self_register_gateways():
    from src.services.deployment_orchestration_service import DeploymentOrchestrationService

    db = AsyncMock()
    svc = DeploymentOrchestrationService(db)

    dep = MagicMock()
    dep.id = uuid4()
    dep.gateway_instance_id = uuid4()
    dep.desired_state = {"tenant_id": "free-aech"}
    dep.sync_status = "pending"
    dep.sync_error = None
    dep.sync_attempts = 0

    gw = MagicMock()
    gw.id = uuid4()
    gw.name = "connect-webmethods"
    gw.environment = "dev"
    gw.gateway_type = MagicMock(value="stoa")
    gw.base_url = "http://connect-webmethods:8090"
    gw.auth_config = {}
    gw.source = "self_register"
    gw.status = MagicMock(value="online")
    gw.deployment_mode = "connect"
    gw.topology = "remote-agent"

    with patch(
        "src.repositories.gateway_instance.GatewayInstanceRepository"
    ) as MockRepo:
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = gw
        MockRepo.return_value = mock_repo

        with patch(
            "src.services.credential_resolver.create_adapter_with_credentials",
            new_callable=AsyncMock,
            side_effect=AgentManagedGatewayError("connect-webmethods"),
        ) as mock_adapter:
            await svc._try_inline_sync([dep])

            # Adapter factory is called but raises AgentManagedGatewayError,
            # which _try_inline_sync catches and skips (continue)
            mock_adapter.assert_awaited_once()
            # Verify source was passed to the centralized guard
            assert mock_adapter.call_args.kwargs["source"] == "self_register"
            assert mock_adapter.call_args.kwargs["deployment_mode"] == "connect"


@pytest.mark.asyncio
async def test_regression_self_registered_connect_topology_is_agent_managed():
    """self_register + deployment_mode=connect must wait for agent ack, not CP push."""
    from src.services.credential_resolver import create_adapter_with_credentials

    with pytest.raises(AgentManagedGatewayError):
        await create_adapter_with_credentials(
            "stoa_sidecar",
            "http://stoa-link-wm-dev:8080",
            {},
            source="self_register",
            gateway_name="stoa-link-wm-dev-sidecar-dev",
            deployment_mode="connect",
            topology="remote-agent",
        )


@pytest.mark.asyncio
async def test_regression_self_registered_edge_topology_remains_push_capable():
    """self_register STOA edge gateways are still push-capable native edge targets."""
    from src.services.credential_resolver import create_adapter_with_credentials

    with patch("src.services.credential_resolver.AdapterRegistry.create") as mock_create:
        await create_adapter_with_credentials(
            "stoa_edge_mcp",
            "http://stoa-gateway-dev:8080",
            {},
            source="self_register",
            gateway_name="stoa-gateway-dev-edge-mcp-dev",
            deployment_mode="edge",
            topology="native-edge",
        )

    mock_create.assert_called_once()
