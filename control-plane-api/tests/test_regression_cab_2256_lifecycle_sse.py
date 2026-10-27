"""Canonical methods + real SQL repository/session/bus; never a runtime qualification."""

from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select

from src.config import settings
from src.events.event_bus import event_bus
from src.models.gateway_deployment import GatewayDeployment
from src.models.gateway_instance import GatewayInstance, GatewayType
from src.models.promotion import Promotion
from src.routers.api_lifecycle import _build_service
from src.routers.gateway_internal import RouteSyncAckPayload, SyncedRouteResult, route_sync_ack
from src.services.api_lifecycle.errors import (
    ApiLifecycleGatewayNotFoundError,
    ApiLifecycleNotFoundError,
    ApiLifecycleTransitionError,
    ApiLifecycleValidationError,
)
from src.services.api_lifecycle.ports import (
    CreateApiDraftCommand,
    DeployApiCommand,
    LifecycleActor,
    PublishApiCommand,
    ValidateApiDraftCommand,
)
from tests.o1_support import local_session

ACTOR = LifecycleActor(actor_id="operator", email="operator@example.test", username="operator")
SPEC = {
    "openapi": "3.0.3",
    "info": {"title": "Orders", "version": "1.0.0"},
    "paths": {"/orders": {"get": {"responses": {"200": {"description": "ok"}}}}},
}


class AuditRecorder:
    """Only unrelated audit storage is replaced; SQL/event boundaries stay real."""

    async def record_transition(self, **_details):
        pass


@asynccontextmanager
async def scenario(monkeypatch, environment="dev"):
    monkeypatch.setattr(settings, "DEPLOY_MODE", "sse_only")
    monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "regression-local-key")
    async for db in local_session():
        await (await db.connection()).run_sync(Promotion.__table__.create, checkfirst=True)
        gateway = GatewayInstance(
            id=uuid4(),
            name="local-envoy-connect-dev",
            display_name="Local Envoy",
            gateway_type=GatewayType.STOA,
            base_url="http://gateway.example.test",
            tenant_id="tenant-a",
            environment=environment,
            enabled=True,
        )
        db.add(gateway)
        await db.commit()
        service = _build_service(db)
        service.audit_sink = AuditRecorder()
        draft = await service.create_draft(
            CreateApiDraftCommand(
                tenant_id="tenant-a",
                name="orders",
                display_name="Orders",
                version="1.0.0",
                description="",
                backend_url="http://backend.example.test:18100",
                openapi_spec=deepcopy(SPEC),
            ),
            ACTOR,
        )
        await service.validate_draft(ValidateApiDraftCommand("tenant-a", draft.api_id), ACTOR)
        await db.commit()
        api = await service.repository.get_api_by_id("tenant-a", draft.api_id)
        sub = event_bus.subscribe(tenant_id="tenant-a", gateway_id=str(gateway.id))
        try:
            yield db, service, api, gateway, sub
        finally:
            event_bus.unsubscribe(sub)


def command(api, gateway, *, force=False):
    return DeployApiCommand(api.tenant_id, api.api_id, gateway.environment, gateway.id, force)


async def ack(db, deployment, gateway):
    await route_sync_ack(
        gateway.id,
        RouteSyncAckPayload(
            sync_timestamp=datetime.now(UTC).isoformat(),
            synced_routes=[
                SyncedRouteResult(
                    deployment_id=str(deployment.id), status="applied", generation=deployment.desired_generation
                )
            ],
        ),
        x_gateway_key="regression-local-key",
        db=db,
    )
    await db.commit()
    await db.refresh(deployment)


@pytest.mark.asyncio
async def test_regression_canonical_payload_is_targeted_and_published_only_after_commit(monkeypatch):
    async with scenario(monkeypatch) as (db, service, api, gateway, sub):
        foreign_gateway = event_bus.subscribe(tenant_id="tenant-a", gateway_id=str(uuid4()))
        foreign_tenant = event_bus.subscribe(tenant_id="tenant-b", gateway_id=str(gateway.id))
        try:
            outcome = await service.deploy_to_environment(command(api, gateway), ACTOR)
            assert sub.queue.empty(), "SSE must not expose uncommitted desired state"
            await db.commit()
            payload = sub.queue.get_nowait()
            assert payload["event"] == "sync-deployment"
            data = payload["data"]
            assert data["deployment_id"] == str(outcome.deployment_id)
            assert data["api_catalog_id"] == str(api.id)
            assert data["gateway_instance_id"] == str(gateway.id)
            assert data["desired_generation"] == 1
            desired = data["desired_state"]
            assert desired["tenant_id"] == "tenant-a" and desired["api_catalog_id"] == str(api.id)
            assert desired["api_id"] == "orders" and desired["version"] == "1.0.0"
            assert desired["backend_url"] == "http://backend.example.test:18100"
            assert desired["desired_source"] == "db_shortcut" and desired["spec_hash"]
            assert foreign_gateway.queue.empty() and foreign_tenant.queue.empty()
        finally:
            event_bus.unsubscribe(foreign_gateway)
            event_bus.unsubscribe(foreign_tenant)


@pytest.mark.asyncio
async def test_regression_replay_is_unchanged_but_force_and_catalog_change_advance_generation(monkeypatch):
    async with scenario(monkeypatch) as (db, service, api, gateway, sub):
        original = await service.deploy_to_environment(command(api, gateway), ACTOR)
        await db.commit()
        sub.queue.get_nowait()
        replay = await service.deploy_to_environment(command(api, gateway), ACTOR)
        await db.commit()
        assert replay.action == "unchanged" and replay.deployment_id == original.deployment_id
        assert sub.queue.empty()
        await service.deploy_to_environment(command(api, gateway, force=True), ACTOR)
        assert sub.queue.empty()
        await db.commit()
        assert sub.queue.get_nowait()["data"]["desired_generation"] == 2
        api.version = "2.0.0"
        api.api_metadata = {**api.api_metadata, "backend_url": "http://backend.example.test:18101"}
        await db.commit()
        await service.deploy_to_environment(command(api, gateway), ACTOR)
        await db.commit()
        changed = sub.queue.get_nowait()["data"]
        assert changed["desired_generation"] == 3
        assert changed["desired_state"]["version"] == "2.0.0"
        assert changed["desired_state"]["backend_url"].endswith(":18101")


@pytest.mark.asyncio
async def test_regression_rollback_discards_row_and_notification(monkeypatch):
    async with scenario(monkeypatch) as (db, service, api, gateway, sub):
        await service.deploy_to_environment(command(api, gateway), ACTOR)
        await db.rollback()
        await db.commit()
        assert sub.queue.empty()
        assert (await db.execute(select(GatewayDeployment))).scalars().all() == []


@pytest.mark.asyncio
async def test_regression_nested_notification_fails_closed(monkeypatch):
    async with scenario(monkeypatch) as (db, service, api, gateway, sub):
        nested = await db.begin_nested()
        with pytest.raises(ValueError, match="top-level"):
            await service.deploy_to_environment(command(api, gateway), ACTOR)
        await nested.rollback()
        await db.rollback()
        await db.commit()
        assert sub.queue.empty()


@pytest.mark.asyncio
@pytest.mark.parametrize("refusal", ["tenant", "foreign-gateway", "disabled", "environment", "production"])
async def test_regression_refusal_never_queues_or_creates_a_deployment(monkeypatch, refusal):
    env = "production" if refusal == "production" else "dev"
    async with scenario(monkeypatch, env) as (db, service, api, gateway, sub):
        cmd = command(api, gateway)
        expected = ApiLifecycleGatewayNotFoundError
        if refusal == "tenant":
            cmd = replace(cmd, tenant_id="tenant-b")
            expected = ApiLifecycleNotFoundError
        elif refusal == "foreign-gateway":
            gateway.tenant_id = "tenant-b"
        elif refusal == "disabled":
            gateway.enabled = False
        elif refusal == "environment":
            cmd = replace(cmd, environment="staging")
            expected = ApiLifecycleValidationError
        else:
            expected = ApiLifecycleTransitionError
        await db.commit()
        with pytest.raises(expected):
            await service.deploy_to_environment(cmd, ACTOR)
        await db.commit()  # The canonical router retains failure audits by committing known refusals.
        assert sub.queue.empty()
        assert (await db.execute(select(GatewayDeployment))).scalars().all() == []


@pytest.mark.asyncio
async def test_regression_real_ack_allows_publication_without_another_sse(monkeypatch):
    async with scenario(monkeypatch) as (db, service, api, gateway, sub):
        outcome = await service.deploy_to_environment(command(api, gateway), ACTOR)
        await db.commit()
        sub.queue.get_nowait()
        deployment = await db.get(GatewayDeployment, outcome.deployment_id)
        await ack(db, deployment, gateway)
        result = await service.publish_to_portal(PublishApiCommand("tenant-a", "orders", "dev", gateway.id), ACTOR)
        await db.commit()
        assert result.portal_published is True
        assert result.deployment_id == deployment.id and sub.queue.empty()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stale",
    [
        "generation",
        "future-generation",
        "version",
        "backend_url",
        "spec",
        "catalog-id",
        "tenant-id",
        "api-id",
        "missing-identity",
    ],
)
async def test_regression_stale_ack_cannot_publish_current_catalog(monkeypatch, stale):
    async with scenario(monkeypatch) as (db, service, api, gateway, sub):
        outcome = await service.deploy_to_environment(command(api, gateway), ACTOR)
        await db.commit()
        if not sub.queue.empty():
            sub.queue.get_nowait()
        deployment = await db.get(GatewayDeployment, outcome.deployment_id)
        await ack(db, deployment, gateway)
        if stale == "generation":
            deployment.desired_generation += 1
        elif stale == "future-generation":
            deployment.synced_generation += 1
        elif stale == "missing-identity":
            desired = dict(deployment.desired_state)
            desired.pop("api_catalog_id")
            deployment.desired_state = desired
        elif stale in {"catalog-id", "tenant-id", "api-id"}:
            key, value = {
                "catalog-id": ("api_catalog_id", str(uuid4())),
                "tenant-id": ("tenant_id", "tenant-b"),
                "api-id": ("api_id", "different-api"),
            }[stale]
            deployment.desired_state = {**deployment.desired_state, key: value}
        elif stale == "version":
            api.version = "2.0.0"
        elif stale == "backend_url":
            api.api_metadata = {**api.api_metadata, "backend_url": "http://backend.example.test:18101"}
        else:
            spec = deepcopy(api.openapi_spec)
            spec["info"]["version"] = "2.0.0"
            api.openapi_spec = spec
        await db.commit()
        with pytest.raises(ApiLifecycleTransitionError):
            await service.publish_to_portal(PublishApiCommand("tenant-a", "orders", "dev", gateway.id), ACTOR)
        await db.commit()
        assert not api.portal_published and sub.queue.empty()
