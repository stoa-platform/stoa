"""Regression tests for the demo smoke route-sync bridge."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.adapters.stoa.mappers import map_api_spec_to_stoa
from src.routers import deployments as deployments_router
from src.services.deployment_service import DeploymentService
from src.services.git_provider import GitProvider, get_git_provider
from tests.test_deployments_router import DEPLOY_SVC_PATH, _mock_deployment


def test_regression_demo_route_sync_exposes_api_id_for_smoke_polling() -> None:
    route = map_api_spec_to_stoa(
        {
            "api_catalog_id": "catalog-id",
            "api_id": "demo-api-smoke",
            "api_name": "demo-api-smoke",
            "backend_url": "http://mock-backend:9090",
        },
        tenant_id="demo",
    )

    assert route["api_id"] == "demo-api-smoke"
    assert route["path_prefix"] == "/apis/demo-api-smoke"


def test_regression_demo_route_sync_bridges_legacy_deployment_endpoint(
    app_with_tenant_admin, monkeypatch
) -> None:
    monkeypatch.setattr(deployments_router.settings, "STOA_DISABLE_AUTH", True)

    deployment = _mock_deployment(api_id="demo-api-smoke", api_name="demo-api-smoke", environment="dev")
    mock_svc = MagicMock()
    mock_svc.create_deployment = AsyncMock(return_value=deployment)
    mock_svc.ensure_demo_gateway_deployment = AsyncMock()

    mock_git = MagicMock(spec=GitProvider)
    mock_git._project = object()
    mock_git.get_api = AsyncMock(return_value=None)
    app_with_tenant_admin.dependency_overrides[get_git_provider] = lambda: mock_git

    with (
        patch(DEPLOY_SVC_PATH, return_value=mock_svc),
        TestClient(app_with_tenant_admin) as client,
    ):
        resp = client.post(
            "/v1/tenants/acme/deployments",
            headers={"X-Demo-Mode": "true"},
            json={"api_id": "demo-api-smoke", "environment": "dev", "gateway_id": "gateway-demo"},
        )

    app_with_tenant_admin.dependency_overrides.pop(get_git_provider, None)

    assert resp.status_code == 201
    mock_svc.ensure_demo_gateway_deployment.assert_awaited_once_with(
        tenant_id="acme",
        api_id="demo-api-smoke",
        api_name="demo-api-smoke",
        gateway_name="gateway-demo",
    )


@pytest.mark.asyncio
async def test_regression_demo_route_sync_does_not_emit_push_sync() -> None:
    db = AsyncMock()
    catalog = MagicMock()
    catalog.id = uuid4()
    gateway = MagicMock()
    gateway.id = uuid4()

    result = MagicMock()
    result.scalar_one_or_none.return_value = catalog
    db.execute = AsyncMock(return_value=result)

    with (
        patch("src.services.deployment_service.GatewayInstanceRepository") as MockGatewayRepo,
        patch("src.services.deployment_service.GatewayDeploymentService") as MockGatewayDeploySvc,
    ):
        MockGatewayRepo.return_value.get_by_name = AsyncMock(return_value=gateway)
        deploy_svc = MockGatewayDeploySvc.return_value
        deploy_svc.deploy_api = AsyncMock(return_value=[])

        await DeploymentService(db).ensure_demo_gateway_deployment(
            tenant_id="demo",
            api_id="demo-api-smoke",
            api_name="demo-api-smoke",
            gateway_name="gateway-demo",
        )

    deploy_svc.deploy_api.assert_awaited_once_with(
        catalog.id,
        [gateway.id],
        emit_sync_requests=False,
    )
