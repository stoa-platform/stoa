"""Link notifications must not race ahead of committed desired state."""

import pytest
from sqlalchemy import text

from src.events.event_bus import event_bus
from src.events.transactional import queue_link_event
from src.models.gateway_deployment import DeploymentSyncStatus, GatewayDeployment
from src.services.gateway_deployment_service import GatewayDeploymentService
from tests.o1_support import local_session


@pytest.mark.asyncio
async def test_regression_cab_2256_notification_after_commit() -> None:
    async for db in local_session():
        sub = event_bus.subscribe(gateway_id="own")
        dep = GatewayDeployment(
            id="dep",
            api_catalog_id="catalog",
            gateway_instance_id="own",
            desired_generation=2,
            desired_state={},
            sync_status=DeploymentSyncStatus.DELETING,
        )
        try:
            await db.execute(text("SELECT 1"))
            await GatewayDeploymentService(db)._emit_sse_events([dep], "tenant")
            assert sub.queue.empty(), "Link can ACK before deletion is committed"
            await db.commit()
            assert sub.queue.get_nowait()["data"]["desired_generation"] == 2
            await db.execute(text("SELECT 1"))
            await GatewayDeploymentService(db)._emit_sse_events([dep], "tenant")
            await db.rollback()
            assert sub.queue.empty(), "rolled-back desired state was published"
            await db.execute(text("SELECT 1"))
            await GatewayDeploymentService(db)._emit_sse_events([dep], "tenant")
            nested = await db.begin_nested()
            with pytest.raises(ValueError, match="top-level"):
                queue_link_event(db, tenant_id="tenant", event_type="undeploy", data={}, gateway_id="own")
            await nested.rollback()
            assert sub.queue.empty()
            await db.commit()
            assert sub.queue.qsize() == 1, "savepoint rollback discarded the outer notification"
        finally:
            event_bus.unsubscribe(sub)
