"""Real repositories and bus: SSE deletion must survive a disconnected Link."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.config import settings
from src.events.event_bus import event_bus
from src.models.catalog import APICatalog
from src.models.gateway_deployment import DeploymentSyncStatus, GatewayDeployment
from src.models.gateway_instance import GatewayInstance, GatewayType
from src.routers.gateway_internal import RouteSyncAckPayload, SyncedRouteResult, get_gateway_config, route_sync_ack
from src.services.gateway_deployment_service import GatewayDeploymentService
from tests.o1_support import local_session


@pytest.mark.asyncio
async def test_regression_cab_2256_sse_deletion_tombstone(monkeypatch) -> None:
    monkeypatch.setattr(settings, "DEPLOY_MODE", "sse_only")
    monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "o1-local-test-key")
    async for db in local_session():
        catalog = APICatalog(
            id=uuid4(),
            api_id="orders",
            api_name="Orders",
            tenant_id="tenant",
            version="1",
            api_metadata={},
            git_path="orders/api.yaml",
        )
        gateway = GatewayInstance(
            id=uuid4(),
            name="local-link",
            display_name="Link",
            gateway_type=GatewayType.STOA,
            base_url="http://gateway.test",
            tenant_id="tenant",
            environment="test",
        )
        dep = GatewayDeployment(
            id=uuid4(),
            api_catalog_id=catalog.id,
            gateway_instance_id=gateway.id,
            desired_state={
                "api_id": "orders",
                "api_catalog_id": str(catalog.id),
                "tenant_id": "tenant",
                "backend_url": "http://backend.test",
                "activated": True,
            },
            desired_at=datetime.now(UTC),
            sync_status=DeploymentSyncStatus.SYNCED,
        )
        db.add_all([catalog, gateway, dep])
        await db.commit()
        sub = event_bus.subscribe(gateway_id=str(gateway.id), event_types=["undeploy"])
        try:
            sync_sub = event_bus.subscribe(gateway_id=str(gateway.id), event_types=["sync-deployment"])
            try:
                await GatewayDeploymentService(db).force_sync(dep.id)
                await db.commit()
                assert sync_sub.queue.get_nowait()["data"]["desired_generation"] == 2
            finally:
                event_bus.unsubscribe(sync_sub)
            await GatewayDeploymentService(db).undeploy(dep.id)
            await db.commit()
            assert dep.sync_status == DeploymentSyncStatus.DELETING
            event = sub.queue.get_nowait()
            assert event["data"]["deployment_id"] == str(dep.id)
            config = await get_gateway_config(gateway.id, x_gateway_key="o1-local-test-key", db=db)
            assert config["pending_deployments"][0]["sync_status"] == "deleting"
            generation = config["pending_deployments"][0]["desired_generation"]
            # A queued pre-delete ACK must neither resurrect nor reap the marker.
            for status, observed in (("applied", generation), ("removed", generation - 1), ("failed", generation)):
                stale = RouteSyncAckPayload(
                    sync_timestamp=datetime.now(UTC).isoformat(),
                    synced_routes=[SyncedRouteResult(deployment_id=str(dep.id), status=status, generation=observed)],
                )
                await route_sync_ack(gateway.id, stale, x_gateway_key="o1-local-test-key", db=db)
                assert dep.sync_status == DeploymentSyncStatus.DELETING
                assert await GatewayDeploymentService(db).deploy_repo.get_by_id(dep.id) is not None
            payload = RouteSyncAckPayload(
                sync_timestamp=datetime.now(UTC).isoformat(),
                synced_routes=[
                    SyncedRouteResult(
                        deployment_id=str(dep.id),
                        status="removed",
                        generation=generation,
                    )
                ],
            )
            await route_sync_ack(gateway.id, payload, x_gateway_key="o1-local-test-key", db=db)
            assert await GatewayDeploymentService(db).deploy_repo.get_by_id(dep.id) is None
        finally:
            event_bus.unsubscribe(sub)
