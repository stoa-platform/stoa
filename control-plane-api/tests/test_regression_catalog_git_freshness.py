"""Regression tests for catalog Git freshness on gateway deployments."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


def test_regression_cab_2583_git_commit_marks_desired_state_as_git_backed():
    """A runtime deployment must carry the catalog commit when Git is current."""
    from src.services.gateway_deployment_service import GatewayDeploymentService

    catalog = SimpleNamespace(
        id=uuid4(),
        api_name="payments",
        api_id="payments",
        tenant_id="acme",
        version="1.0.0",
        openapi_spec={"openapi": "3.0.0"},
        api_metadata={},
        git_path="tenants/acme/apis/payments",
        git_commit_sha="abc123def456",
    )

    desired = GatewayDeploymentService.build_desired_state(catalog)

    assert desired["desired_source"] == "git"
    assert desired["git_sync_status"] == "up_to_date"
    assert desired["desired_commit_sha"] == "abc123def456"


@pytest.mark.asyncio
async def test_regression_cab_2583_production_rejects_db_only_desired_state():
    """Production must not accept a direct gateway deployment without a catalog commit."""
    from src.services.gateway_deployment_service import GatewayDeploymentService

    catalog = SimpleNamespace(id=uuid4(), git_commit_sha=None)
    gateway = SimpleNamespace(id=uuid4(), name="webmethods-prod", environment="production", enabled=True)
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = catalog
    db.execute = AsyncMock(return_value=result)

    with patch("src.services.gateway_deployment_service.GatewayDeploymentRepository") as MockDeployRepo, \
         patch("src.services.gateway_deployment_service.GatewayInstanceRepository") as MockGwRepo:
        deploy_repo = MockDeployRepo.return_value
        deploy_repo.create = AsyncMock()
        gw_repo = MockGwRepo.return_value
        gw_repo.get_by_id = AsyncMock(return_value=gateway)
        svc = GatewayDeploymentService(db)
        svc.deploy_repo = deploy_repo
        svc.gw_repo = gw_repo

        with pytest.raises(PermissionError, match="Production deployment requires"):
            await svc.deploy_api(catalog.id, [gateway.id])

        deploy_repo.create.assert_not_awaited()
