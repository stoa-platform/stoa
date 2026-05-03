"""DB persistence checks for lifecycle portal publication."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.database import Base
from src.models.catalog import APICatalog
from src.models.gateway_deployment import DeploymentSyncStatus, GatewayDeployment
from src.models.gateway_instance import GatewayInstance, GatewayType
from src.models.promotion import Promotion  # noqa: F401 - registers FK target for create_all
from src.services.api_lifecycle.ports import LifecycleActor, PublishApiCommand
from src.services.api_lifecycle.repository import SqlAlchemyApiLifecycleRepository
from src.services.api_lifecycle.service import ApiLifecycleService

OPENAPI_SPEC: dict[str, Any] = {
    "openapi": "3.0.3",
    "info": {"title": "Payments API", "version": "1.0.0"},
    "paths": {"/payments": {"get": {"responses": {"200": {"description": "ok"}}}}},
}


@dataclass
class InMemoryAuditSink:
    events: list[dict[str, Any]] = field(default_factory=list)

    async def record_transition(
        self,
        *,
        tenant_id: str,
        actor: LifecycleActor,
        action: str,
        resource_id: str,
        resource_name: str,
        details: dict[str, Any],
        outcome: str = "success",
        status_code: int = 200,
        method: str = "POST",
        path: str | None = None,
    ) -> None:
        self.events.append(
            {
                "tenant_id": tenant_id,
                "actor": actor,
                "action": action,
                "resource_id": resource_id,
                "resource_name": resource_name,
                "details": details,
                "outcome": outcome,
                "status_code": status_code,
                "method": method,
                "path": path,
            }
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_publication_metadata_persists_after_commit_and_reload() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not set")

    engine = create_async_engine(database_url, echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS stoa"))
        await conn.run_sync(Base.metadata.create_all)

    tenant_id = f"slice45-{uuid4().hex}"
    api_id = "payments-api"
    gateway_name = f"slice45-dev-{uuid4().hex}"
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        api: APICatalog | None = None
        try:
            api = APICatalog(
                tenant_id=tenant_id,
                api_id=api_id,
                api_name="Payments API",
                version="1.0.0",
                status="ready",
                tags=[],
                portal_published=False,
                api_metadata={
                    "display_name": "Payments API",
                    "description": "Payment operations",
                    "backend_url": "https://payments.internal",
                    "lifecycle": {"catalog_status": "ready", "spec_source": "inline"},
                },
                openapi_spec=OPENAPI_SPEC,
            )
            gateway = GatewayInstance(
                name=gateway_name,
                display_name="Slice45 Dev",
                gateway_type=GatewayType.STOA,
                environment="dev",
                tenant_id=tenant_id,
                base_url="https://gateway.dev.example/admin",
                public_url="https://gateway.dev.example",
                enabled=True,
            )
            session.add_all([api, gateway])
            await session.flush()

            deployment = GatewayDeployment(
                api_catalog_id=api.id,
                gateway_instance_id=gateway.id,
                desired_state={"api_id": api.api_id},
                desired_at=datetime.now(UTC),
                desired_generation=1,
                synced_generation=1,
                attempted_generation=1,
                sync_status=DeploymentSyncStatus.SYNCED,
                sync_attempts=1,
                last_sync_success=datetime.now(UTC),
            )
            session.add(deployment)
            await session.commit()
            gateway_id = gateway.id
            deployment_id = deployment.id

            service = ApiLifecycleService(
                repository=SqlAlchemyApiLifecycleRepository(session),
                audit_sink=InMemoryAuditSink(),
            )
            outcome = await service.publish_to_portal(
                PublishApiCommand(
                    tenant_id=tenant_id,
                    api_id=api_id,
                    environment="dev",
                    gateway_instance_id=gateway.id,
                ),
                LifecycleActor(actor_id="user-1", email="owner@acme.test", username="owner"),
            )
            await session.commit()

            session.expire_all()
            result = await session.execute(
                select(APICatalog).where(APICatalog.tenant_id == tenant_id, APICatalog.api_id == api_id)
            )
            reloaded = result.scalar_one()
            publication = reloaded.api_metadata["lifecycle"]["portal_publications"][f"dev:{gateway_id}"]
            assert outcome.result == "published"
            assert reloaded.portal_published is True
            assert publication["deployment_id"] == str(deployment_id)
            assert publication["publication_status"] == "published"
            assert publication["source"] == "api_lifecycle"
        finally:
            if api is not None and api.id is not None:
                await session.execute(delete(GatewayDeployment).where(GatewayDeployment.api_catalog_id == api.id))
            await session.execute(delete(GatewayInstance).where(GatewayInstance.name == gateway_name))
            await session.execute(delete(APICatalog).where(APICatalog.tenant_id == tenant_id))
            await session.commit()

    await engine.dispose()
