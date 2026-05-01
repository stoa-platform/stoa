from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.models.gateway_deployment import DeploymentSyncStatus
from src.services.catalog_deployment_reconciler import CatalogDeploymentReconciler


async def test_regression_catalog_gateway_targets_rebuild_pending_deployment() -> None:
    db = AsyncMock()
    catalog_entry = MagicMock(
        id=uuid4(),
        tenant_id="acme",
        api_id="billing-api",
        target_gateways=[],
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = catalog_entry
    db.execute = AsyncMock(return_value=result)

    gateway = MagicMock(id=uuid4(), name="connect-webmethods-dev", environment="dev")
    gw_repo = MagicMock()
    gw_repo.get_by_name = AsyncMock(return_value=gateway)
    gw_repo.get_self_registered_by_hostname = AsyncMock(return_value=None)

    created = []
    deploy_repo = MagicMock()
    deploy_repo.get_by_api_and_gateway = AsyncMock(return_value=None)
    deploy_repo.create = AsyncMock(side_effect=lambda deployment: created.append(deployment))

    api_content = {
        "name": "Billing API",
        "deployments": {
            "dev": {
                "gateways": [{"instance": "connect-webmethods-dev"}],
            }
        },
    }

    with (
        patch("src.services.catalog_deployment_reconciler.GatewayInstanceRepository", return_value=gw_repo),
        patch("src.services.catalog_deployment_reconciler.GatewayDeploymentRepository", return_value=deploy_repo),
        patch(
            "src.services.catalog_deployment_reconciler.GatewayDeploymentService.build_desired_state",
            return_value={"spec": "v1"},
        ),
    ):
        changed = await CatalogDeploymentReconciler(db).reconcile_api(
            tenant_id="acme",
            api_id="billing-api",
            api_content=api_content,
        )

    assert changed is True
    assert catalog_entry.target_gateways == ["connect-webmethods-dev"]
    assert len(created) == 1
    assert created[0].api_catalog_id == catalog_entry.id
    assert created[0].gateway_instance_id == gateway.id
    assert created[0].sync_status == DeploymentSyncStatus.PENDING
    assert created[0].desired_state["target_environment"] == "dev"
    db.flush.assert_awaited_once()
