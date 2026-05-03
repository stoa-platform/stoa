"""Deployment tests for the canonical API lifecycle service, Slice 3."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from src.models.catalog import APICatalog
from src.models.gateway_deployment import DeploymentSyncStatus, GatewayDeployment
from src.services.api_lifecycle.errors import (
    ApiLifecycleGatewayAmbiguousError,
    ApiLifecycleGatewayNotFoundError,
    ApiLifecycleNotFoundError,
    ApiLifecycleTransitionError,
)
from src.services.api_lifecycle.ports import (
    DeployApiCommand,
    GatewayDeploymentSnapshot,
    GatewayTarget,
    LifecycleActor,
    PromotionSnapshot,
)
from src.services.api_lifecycle.service import ApiLifecycleService

OPENAPI_SPEC: dict[str, Any] = {
    "openapi": "3.0.3",
    "info": {"title": "Payments API", "version": "1.0.0"},
    "paths": {"/payments": {"get": {"responses": {"200": {"description": "ok"}}}}},
}


@dataclass
class InMemoryApiLifecycleRepository:
    apis: dict[tuple[str, str], APICatalog] = field(default_factory=dict)
    gateways: dict[UUID, GatewayTarget] = field(default_factory=dict)
    deployments: dict[tuple[UUID, UUID], GatewayDeployment] = field(default_factory=dict)

    async def get_api_by_id(self, tenant_id: str, api_id: str) -> APICatalog | None:
        return self.apis.get((tenant_id, api_id))

    async def get_api_by_name_version(self, tenant_id: str, api_name: str, version: str) -> APICatalog | None:
        return next(
            (
                row
                for (row_tenant_id, _), row in self.apis.items()
                if row_tenant_id == tenant_id and row.api_name == api_name and row.version == version
            ),
            None,
        )

    async def create_api_catalog(self, api: APICatalog) -> APICatalog:
        self.apis[(api.tenant_id, api.api_id)] = api
        return api

    async def save_api_catalog(self, api: APICatalog) -> APICatalog:
        self.apis[(api.tenant_id, api.api_id)] = api
        return api

    async def list_gateway_deployments(self, api_catalog_id: UUID) -> list[GatewayDeploymentSnapshot]:
        snapshots: list[GatewayDeploymentSnapshot] = []
        for (row_api_catalog_id, gateway_id), deployment in self.deployments.items():
            if row_api_catalog_id != api_catalog_id:
                continue
            gateway = self.gateways[gateway_id]
            snapshots.append(
                GatewayDeploymentSnapshot(
                    id=deployment.id,
                    environment=gateway.environment,
                    gateway_instance_id=gateway.id,
                    gateway_name=gateway.name,
                    gateway_type=gateway.gateway_type,
                    sync_status=str(deployment.sync_status),
                    desired_generation=deployment.desired_generation,
                    synced_generation=deployment.synced_generation,
                    gateway_resource_id=deployment.gateway_resource_id,
                    public_url=gateway.public_url,
                    sync_error=deployment.sync_error,
                    last_sync_success=deployment.last_sync_success,
                )
            )
        return snapshots

    async def get_gateway_target(self, tenant_id: str, gateway_instance_id: UUID) -> GatewayTarget | None:
        gateway = self.gateways.get(gateway_instance_id)
        if not gateway or gateway.tenant_id not in (None, tenant_id):
            return None
        return gateway

    async def list_gateway_targets(self, tenant_id: str, environment: str) -> list[GatewayTarget]:
        return [
            gateway
            for gateway in self.gateways.values()
            if gateway.enabled and gateway.environment == environment and gateway.tenant_id in (None, tenant_id)
        ]

    async def get_gateway_deployment(self, api_catalog_id: UUID, gateway_instance_id: UUID) -> GatewayDeployment | None:
        return self.deployments.get((api_catalog_id, gateway_instance_id))

    async def create_gateway_deployment(self, deployment: GatewayDeployment) -> GatewayDeployment:
        self.deployments[(deployment.api_catalog_id, deployment.gateway_instance_id)] = deployment
        return deployment

    async def save_gateway_deployment(self, deployment: GatewayDeployment) -> GatewayDeployment:
        self.deployments[(deployment.api_catalog_id, deployment.gateway_instance_id)] = deployment
        return deployment

    async def list_promotions(self, tenant_id: str, api_id: str) -> list[PromotionSnapshot]:
        return []


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


def _actor() -> LifecycleActor:
    return LifecycleActor(actor_id="user-1", email="owner@acme.test", username="owner")


def _api(status: str = "ready", tenant_id: str = "acme", api_id: str = "payments-api") -> APICatalog:
    return APICatalog(
        id=uuid4(),
        tenant_id=tenant_id,
        api_id=api_id,
        api_name="Payments API",
        version="1.0.0",
        status=status,
        tags=[],
        portal_published=False,
        api_metadata={
            "display_name": "Payments API",
            "description": "Payment operations",
            "backend_url": "https://payments.internal",
            "status": status,
            "lifecycle": {"catalog_status": status, "spec_source": "inline"},
        },
        openapi_spec=OPENAPI_SPEC,
    )


def _gateway(
    *,
    gateway_id: UUID | None = None,
    tenant_id: str | None = None,
    environment: str = "dev",
    name: str = "stoa-dev",
) -> GatewayTarget:
    return GatewayTarget(
        id=gateway_id or uuid4(),
        name=name,
        display_name=name,
        gateway_type="stoa",
        environment=environment,
        tenant_id=tenant_id,
        enabled=True,
        public_url="https://gateway.dev.example",
    )


def _service(
    *,
    api: APICatalog | None = None,
    gateways: list[GatewayTarget] | None = None,
) -> tuple[ApiLifecycleService, InMemoryApiLifecycleRepository, InMemoryAuditSink]:
    repository = InMemoryApiLifecycleRepository()
    if api:
        repository.apis[(api.tenant_id, api.api_id)] = api
    for gateway in gateways or []:
        repository.gateways[gateway.id] = gateway
    audit = InMemoryAuditSink()
    return ApiLifecycleService(repository=repository, audit_sink=audit), repository, audit


def _deploy_command(**overrides) -> DeployApiCommand:
    values = {
        "tenant_id": "acme",
        "api_id": "payments-api",
        "environment": "dev",
        "gateway_instance_id": None,
        "force": False,
    }
    values.update(overrides)
    return DeployApiCommand(**values)


@pytest.mark.asyncio
async def test_ready_api_with_unique_dev_gateway_creates_gateway_deployment() -> None:
    service, repository, _ = _service(api=_api(), gateways=[_gateway()])

    outcome = await service.deploy_to_environment(_deploy_command(), _actor())

    assert outcome.action == "created"
    assert outcome.deployment_status == "pending"
    assert len(repository.deployments) == 1
    deployment = next(iter(repository.deployments.values()))
    assert deployment.sync_status == DeploymentSyncStatus.PENDING
    assert deployment.desired_state["api_id"] == "payments-api"
    assert deployment.desired_state["target_environment"] == "dev"


@pytest.mark.asyncio
async def test_deploy_keeps_catalog_status_ready() -> None:
    api = _api()
    service, repository, _ = _service(api=api, gateways=[_gateway()])

    await service.deploy_to_environment(_deploy_command(), _actor())

    assert repository.apis[("acme", "payments-api")].status == "ready"


@pytest.mark.asyncio
async def test_get_lifecycle_after_deploy_returns_gateway_deployment() -> None:
    service, _, _ = _service(api=_api(), gateways=[_gateway()])
    await service.deploy_to_environment(_deploy_command(), _actor())

    state = await service.get_lifecycle_state("acme", "payments-api")

    assert state.catalog_status == "ready"
    assert len(state.deployments) == 1
    assert state.deployments[0].environment == "dev"
    assert state.deployments[0].sync_status == "pending"


@pytest.mark.asyncio
async def test_draft_api_cannot_be_deployed() -> None:
    service, _, audit = _service(api=_api(status="draft"), gateways=[_gateway()])

    with pytest.raises(ApiLifecycleTransitionError, match="cannot be deployed"):
        await service.deploy_to_environment(_deploy_command(), _actor())

    assert audit.events[-1]["action"] == "api_lifecycle.deploy_failed"


@pytest.mark.asyncio
async def test_archived_api_cannot_be_deployed() -> None:
    service, _, _ = _service(api=_api(status="archived"), gateways=[_gateway()])

    with pytest.raises(ApiLifecycleTransitionError, match="cannot be deployed"):
        await service.deploy_to_environment(_deploy_command(), _actor())


@pytest.mark.asyncio
async def test_missing_api_returns_not_found() -> None:
    service, _, _ = _service(gateways=[_gateway()])

    with pytest.raises(ApiLifecycleNotFoundError):
        await service.deploy_to_environment(_deploy_command(), _actor())


@pytest.mark.asyncio
async def test_other_tenant_api_cannot_be_deployed() -> None:
    service, repository, _ = _service(api=_api(tenant_id="other"), gateways=[_gateway()])

    with pytest.raises(ApiLifecycleNotFoundError):
        await service.deploy_to_environment(_deploy_command(), _actor())

    assert repository.apis[("other", "payments-api")].status == "ready"
    assert repository.deployments == {}


@pytest.mark.asyncio
async def test_explicit_missing_gateway_returns_clear_error() -> None:
    service, _, _ = _service(api=_api())

    with pytest.raises(ApiLifecycleGatewayNotFoundError, match="Gateway"):
        await service.deploy_to_environment(_deploy_command(gateway_instance_id=uuid4()), _actor())


@pytest.mark.asyncio
async def test_multiple_gateways_without_gateway_id_is_ambiguous() -> None:
    service, _, _ = _service(api=_api(), gateways=[_gateway(name="dev-a"), _gateway(name="dev-b")])

    with pytest.raises(ApiLifecycleGatewayAmbiguousError, match="Multiple gateway targets"):
        await service.deploy_to_environment(_deploy_command(), _actor())


@pytest.mark.asyncio
async def test_identical_pending_deployment_is_idempotent_without_duplicate() -> None:
    service, repository, audit = _service(api=_api(), gateways=[_gateway()])
    first = await service.deploy_to_environment(_deploy_command(), _actor())

    second = await service.deploy_to_environment(_deploy_command(), _actor())

    assert first.action == "created"
    assert second.action == "unchanged"
    assert second.deployment_status == "pending"
    assert len(repository.deployments) == 1
    assert audit.events[-1]["action"] == "api_lifecycle.deploy_idempotent"


@pytest.mark.asyncio
async def test_identical_synced_deployment_is_idempotent_and_stays_synced() -> None:
    service, repository, _ = _service(api=_api(), gateways=[_gateway()])
    first = await service.deploy_to_environment(_deploy_command(), _actor())
    deployment = next(iter(repository.deployments.values()))
    deployment.sync_status = DeploymentSyncStatus.SYNCED
    deployment.synced_generation = deployment.desired_generation
    deployment.last_sync_success = datetime.now(UTC)

    second = await service.deploy_to_environment(_deploy_command(), _actor())

    assert first.deployment_status == "pending"
    assert second.action == "unchanged"
    assert second.deployment_id == deployment.id
    assert next(iter(repository.deployments.values())).sync_status == DeploymentSyncStatus.SYNCED


@pytest.mark.asyncio
async def test_success_audit_event_is_written() -> None:
    service, _, audit = _service(api=_api(), gateways=[_gateway()])

    outcome = await service.deploy_to_environment(_deploy_command(), _actor())

    assert audit.events[-1]["action"] == "api_lifecycle.deploy_requested"
    assert audit.events[-1]["details"]["deployment_id"] == str(outcome.deployment_id)
    assert audit.events[-1]["details"]["action"] == "created"
