"""Regression tests for route sync ack stability."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from src.models.gateway_deployment import DeploymentSyncStatus
from tests.test_gateway_internal import GW_KEY_HEADER, VALID_KEY, _make_deployment


def test_regression_route_sync_ack_failed_does_not_downgrade_stable_synced_deployment(client):
    """A transient failed re-ack must not turn an already applied route red."""
    last_success = datetime.now(UTC)
    successful_steps = [
        {"name": "event_emitted", "status": "success", "detail": "deployment dispatched to agent"},
        {"name": "agent_received", "status": "success"},
        {"name": "adapter_connected", "status": "success"},
        {"name": "api_synced", "status": "success"},
    ]
    failed_reack_steps = [
        {"name": "agent_received", "status": "success"},
        {"name": "adapter_connected", "status": "success"},
        {
            "name": "api_synced",
            "status": "failed",
            "detail": "webmethods rebooting",
        },
    ]
    dep = _make_deployment(
        sync_status=DeploymentSyncStatus.SYNCED,
        last_sync_success=last_success,
        sync_error=None,
        sync_steps=successful_steps,
        sync_attempts=0,
    )
    dep.desired_generation = 3
    dep.synced_generation = 3
    dep.attempted_generation = 3

    with (
        patch("src.routers.gateway_internal.settings") as mock_settings,
        patch("src.routers.gateway_internal.GatewayDeploymentRepository") as MockDeployRepo,
    ):
        mock_settings.gateway_api_keys_list = [VALID_KEY]
        mock_deploy_repo = MockDeployRepo.return_value
        mock_deploy_repo.get_by_id = AsyncMock(return_value=dep)
        mock_deploy_repo.update = AsyncMock()

        resp = client.post(
            f"/v1/internal/gateways/{dep.gateway_instance_id}/route-sync-ack",
            json={
                "synced_routes": [
                    {
                        "deployment_id": str(dep.id),
                        "status": "failed",
                        "error": "webmethods rebooting",
                        "steps": failed_reack_steps,
                        "generation": 3,
                    },
                ],
                "sync_timestamp": "2026-03-27T12:00:00Z",
            },
            headers={GW_KEY_HEADER: VALID_KEY},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["processed"] == 1
        assert dep.sync_status == DeploymentSyncStatus.SYNCED
        assert dep.last_sync_success == last_success
        assert dep.sync_error is None
        assert dep.sync_steps == successful_steps
        assert dep.sync_attempts == 0
        mock_deploy_repo.update.assert_awaited_once()


def test_regression_route_sync_ack_connectivity_failure_preserves_forced_resync(client):
    """A gateway outage during force-sync is health, not proof the deployed API vanished."""
    last_success = datetime.now(UTC)
    successful_steps = [
        {"name": "event_emitted", "status": "success", "detail": "deployment dispatched to agent"},
        {"name": "agent_received", "status": "success"},
        {"name": "adapter_connected", "status": "success"},
        {"name": "api_synced", "status": "success"},
    ]
    outage_steps = [
        {"name": "agent_received", "status": "success"},
        {"name": "adapter_connected", "status": "success"},
        {
            "name": "api_synced",
            "status": "failed",
            "detail": 'list existing apis: Get "http://localhost:5555/rest/apigateway/apis": EOF',
        },
    ]
    dep = _make_deployment(
        sync_status=DeploymentSyncStatus.SYNCED,
        last_sync_success=last_success,
        sync_error=None,
        sync_steps=successful_steps,
        sync_attempts=0,
    )
    dep.desired_generation = 9
    dep.synced_generation = 2
    dep.attempted_generation = 8

    with (
        patch("src.routers.gateway_internal.settings") as mock_settings,
        patch("src.routers.gateway_internal.GatewayDeploymentRepository") as MockDeployRepo,
    ):
        mock_settings.gateway_api_keys_list = [VALID_KEY]
        mock_deploy_repo = MockDeployRepo.return_value
        mock_deploy_repo.get_by_id = AsyncMock(return_value=dep)
        mock_deploy_repo.update = AsyncMock()

        resp = client.post(
            f"/v1/internal/gateways/{dep.gateway_instance_id}/route-sync-ack",
            json={
                "synced_routes": [
                    {
                        "deployment_id": str(dep.id),
                        "status": "failed",
                        "error": 'list existing apis: Get "http://localhost:5555/rest/apigateway/apis": EOF',
                        "steps": outage_steps,
                        "generation": 9,
                    },
                ],
                "sync_timestamp": "2026-05-02T13:02:15Z",
            },
            headers={GW_KEY_HEADER: VALID_KEY},
        )

        assert resp.status_code == 200
        assert dep.sync_status == DeploymentSyncStatus.SYNCED
        assert dep.last_sync_success == last_success
        assert dep.sync_error is None
        assert dep.sync_steps == successful_steps
        assert dep.synced_generation == 2
        assert dep.attempted_generation == 9
        mock_deploy_repo.update.assert_awaited_once()


def test_regression_route_sync_ack_contradictory_applied_reack_preserves_stable_synced_deployment(client):
    """A bad applied ack trace must not overwrite an already stable synced route."""
    last_success = datetime.now(UTC)
    successful_steps = [
        {"name": "event_emitted", "status": "success", "detail": "deployment dispatched to agent"},
        {"name": "agent_received", "status": "success"},
        {"name": "adapter_connected", "status": "success"},
        {"name": "api_synced", "status": "success"},
    ]
    failed_applied_steps = [
        {"name": "agent_received", "status": "success"},
        {"name": "adapter_connected", "status": "success"},
        {
            "name": "api_synced",
            "status": "failed",
            "detail": "batch contained another failed route",
        },
    ]
    dep = _make_deployment(
        sync_status=DeploymentSyncStatus.SYNCED,
        last_sync_success=last_success,
        sync_error=None,
        sync_steps=successful_steps,
        sync_attempts=0,
    )
    dep.desired_generation = 3
    dep.synced_generation = 3
    dep.attempted_generation = 3

    with (
        patch("src.routers.gateway_internal.settings") as mock_settings,
        patch("src.routers.gateway_internal.GatewayDeploymentRepository") as MockDeployRepo,
    ):
        mock_settings.gateway_api_keys_list = [VALID_KEY]
        mock_deploy_repo = MockDeployRepo.return_value
        mock_deploy_repo.get_by_id = AsyncMock(return_value=dep)
        mock_deploy_repo.update = AsyncMock()

        resp = client.post(
            f"/v1/internal/gateways/{dep.gateway_instance_id}/route-sync-ack",
            json={
                "synced_routes": [
                    {
                        "deployment_id": str(dep.id),
                        "status": "applied",
                        "steps": failed_applied_steps,
                        "generation": 3,
                    },
                ],
                "sync_timestamp": "2026-03-27T12:00:00Z",
            },
            headers={GW_KEY_HEADER: VALID_KEY},
        )

        assert resp.status_code == 200
        assert dep.sync_status == DeploymentSyncStatus.SYNCED
        assert dep.last_sync_success == last_success
        assert dep.sync_error is None
        assert dep.sync_steps == successful_steps
        mock_deploy_repo.update.assert_awaited_once()
