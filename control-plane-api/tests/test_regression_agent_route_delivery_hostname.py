"""Regression tests for self-registered agent route delivery."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


def test_regression_agent_route_polling_uses_registration_hostname(client):
    """Existing stoa-connect agents poll routes with their registration hostname."""
    gateway = MagicMock()
    gateway.id = uuid4()

    deployment = MagicMock()
    deployment.id = uuid4()
    deployment.desired_generation = 1
    deployment.desired_state = {
        "api_catalog_id": "cat-fapi",
        "api_name": "fapi-banking",
        "backend_url": "http://banking-mock:8080",
        "methods": ["GET", "POST"],
        "spec_hash": "sha-banking",
        "activated": True,
        "tenant_id": "banking-demo",
    }

    with (
        patch("src.routers.gateway_internal.settings") as mock_settings,
        patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockGatewayRepo,
        patch("src.routers.gateway_internal.GatewayDeploymentRepository") as MockDeploymentRepo,
    ):
        mock_settings.GATEWAY_ADMIN_KEY = None
        gw_repo = MockGatewayRepo.return_value
        gw_repo.get_by_name = AsyncMock(return_value=None)
        gw_repo.get_self_registered_by_hostname = AsyncMock(return_value=gateway)
        deploy_repo = MockDeploymentRepo.return_value
        deploy_repo.list_by_statuses_and_gateway = AsyncMock(return_value=[deployment])

        resp = client.get("/v1/internal/gateways/routes?gateway_name=connect-webmethods-dev")

    assert resp.status_code == 200
    routes = resp.json()
    assert len(routes) == 1
    assert routes[0]["name"] == "fapi-banking"
    gw_repo.get_self_registered_by_hostname.assert_awaited_once_with("connect-webmethods-dev")
    deploy_repo.list_by_statuses_and_gateway.assert_awaited_once()
