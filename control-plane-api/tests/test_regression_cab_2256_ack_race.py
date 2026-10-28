"""An ACK read before undeploy must not overwrite its new generation."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.catalog import APICatalog
from src.models.gateway_deployment import DeploymentSyncStatus, GatewayDeployment
from src.models.gateway_instance import GatewayInstance, GatewayType
from src.repositories.gateway_deployment import GatewayDeploymentRepository
from src.routers.gateway_internal import RouteSyncAckPayload, SyncedRouteResult, route_sync_ack
from src.services.gateway_deployment_service import GatewayDeploymentService
from tests.o1_support import local_session


@pytest.mark.asyncio
@pytest.mark.parametrize("initial", [DeploymentSyncStatus.PENDING, DeploymentSyncStatus.SYNCED])
async def test_regression_cab_2256_ack_read_before_delete(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, initial: DeploymentSyncStatus
) -> None:
    monkeypatch.setattr(settings, "DEPLOY_MODE", "sse_only")
    monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "o1-local-test-key")
    async for seed in local_session(f"sqlite+aiosqlite:///{tmp_path / 'race.sqlite'}"):
        catalog = APICatalog(id=uuid4(), api_id="orders", api_name="Orders", tenant_id="tenant", api_metadata={})
        gateway = GatewayInstance(
            id=uuid4(),
            name="link",
            display_name="Link",
            gateway_type=GatewayType.STOA,
            base_url="http://gateway.test",
            tenant_id="tenant",
            environment="dev",
        )
        dep = GatewayDeployment(
            id=uuid4(),
            api_catalog_id=catalog.id,
            gateway_instance_id=gateway.id,
            desired_state={"tenant_id": "tenant"},
            desired_at=datetime.now(UTC),
            sync_status=initial,
            desired_generation=1,
        )
        seed.add_all([catalog, gateway, dep])
        await seed.commit()
        async with AsyncSession(seed.bind, expire_on_commit=False) as ack_db:
            read, resume = asyncio.Event(), asyncio.Event()
            get = GatewayDeploymentRepository.get_by_id

            async def paused_get(repo, identity, original=get, arrived=read, release=resume, target=ack_db):
                value = await original(repo, identity)
                if repo.session is target and not arrived.is_set():
                    arrived.set()
                    await release.wait()
                return value

            monkeypatch.setattr(GatewayDeploymentRepository, "get_by_id", paused_get)
            payload = RouteSyncAckPayload(
                sync_timestamp=datetime.now(UTC).isoformat(),
                synced_routes=[
                    SyncedRouteResult(deployment_id=str(dep.id), status="applied", generation=1),
                ],
            )
            ack = asyncio.create_task(route_sync_ack(gateway.id, payload, x_gateway_key="o1-local-test-key", db=ack_db))
            try:
                async with asyncio.timeout(5):
                    await read.wait()
                    await GatewayDeploymentService(seed).undeploy(dep.id)
                    await seed.commit()
                    resume.set()
                    await ack
                await seed.refresh(dep)
                assert dep.desired_generation == 2
                assert dep.sync_status == DeploymentSyncStatus.DELETING
            finally:
                resume.set()
                if not ack.done():
                    ack.cancel()
                await asyncio.gather(ack, return_exceptions=True)
