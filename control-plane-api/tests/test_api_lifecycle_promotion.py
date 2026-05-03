"""Promotion tests for the canonical API lifecycle service, Slice 5."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from src.models.catalog import APICatalog
from src.models.gateway_deployment import DeploymentSyncStatus, GatewayDeployment
from src.models.promotion import Promotion, PromotionStatus
from src.services.api_lifecycle.errors import (
    ApiLifecycleGatewayAmbiguousError,
    ApiLifecycleGatewayNotFoundError,
    ApiLifecycleNotFoundError,
    ApiLifecycleTransitionError,
    ApiLifecycleValidationError,
)
from src.services.api_lifecycle.portal import CatalogPortalPublisher
from src.services.api_lifecycle.ports import (
    CreateApiDraftCommand,
    DeployApiCommand,
    GatewayDeploymentSnapshot,
    GatewayTarget,
    LifecycleActor,
    PortalPublicationState,
    PromoteApiCommand,
    PromotionSnapshot,
    PublishApiCommand,
    ValidateApiDraftCommand,
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
    promotions: dict[UUID, Promotion] = field(default_factory=dict)

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
        return [
            PromotionSnapshot(
                id=promotion.id,
                source_environment=promotion.source_environment,
                target_environment=promotion.target_environment,
                status=promotion.status,
                message=promotion.message,
                requested_by=promotion.requested_by,
                approved_by=promotion.approved_by,
                completed_at=promotion.completed_at,
            )
            for promotion in self.promotions.values()
            if promotion.tenant_id == tenant_id and promotion.api_id == api_id
        ]

    async def get_active_promotion(
        self,
        tenant_id: str,
        api_id: str,
        source_environment: str,
        target_environment: str,
    ) -> Promotion | None:
        return next(
            (
                promotion
                for promotion in self.promotions.values()
                if promotion.tenant_id == tenant_id
                and promotion.api_id == api_id
                and promotion.source_environment == source_environment
                and promotion.target_environment == target_environment
                and promotion.status in {PromotionStatus.PENDING.value, PromotionStatus.PROMOTING.value}
            ),
            None,
        )

    async def get_latest_promoted_promotion(
        self,
        tenant_id: str,
        api_id: str,
        source_environment: str,
        target_environment: str,
    ) -> Promotion | None:
        promoted = [
            promotion
            for promotion in self.promotions.values()
            if promotion.tenant_id == tenant_id
            and promotion.api_id == api_id
            and promotion.source_environment == source_environment
            and promotion.target_environment == target_environment
            and promotion.status == PromotionStatus.PROMOTED.value
        ]
        return promoted[-1] if promoted else None

    async def get_active_promotion_for_target_deployment(
        self,
        tenant_id: str,
        api_id: str,
        target_environment: str,
        target_deployment_id: UUID,
    ) -> Promotion | None:
        return next(
            (
                promotion
                for promotion in self.promotions.values()
                if promotion.tenant_id == tenant_id
                and promotion.api_id == api_id
                and promotion.target_environment == target_environment
                and promotion.target_deployment_id == target_deployment_id
                and promotion.status in {PromotionStatus.PENDING.value, PromotionStatus.PROMOTING.value}
            ),
            None,
        )

    async def create_promotion(self, promotion: Promotion) -> Promotion:
        self.promotions[promotion.id] = promotion
        return promotion

    async def save_promotion(self, promotion: Promotion) -> Promotion:
        self.promotions[promotion.id] = promotion
        return promotion


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


@dataclass
class FakePortalPublisher:
    calls: list[PortalPublicationState] = field(default_factory=list)
    adapter: CatalogPortalPublisher = field(default_factory=CatalogPortalPublisher)

    async def publish(self, *, api: APICatalog, publication: PortalPublicationState) -> APICatalog:
        self.calls.append(publication)
        return await self.adapter.publish(api=api, publication=publication)


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
        public_url=f"https://gateway.{environment}.example",
    )


def _service(
    *,
    api: APICatalog | None = None,
    gateways: list[GatewayTarget] | None = None,
) -> tuple[ApiLifecycleService, InMemoryApiLifecycleRepository, InMemoryAuditSink, FakePortalPublisher]:
    repository = InMemoryApiLifecycleRepository()
    if api:
        repository.apis[(api.tenant_id, api.api_id)] = api
    for gateway in gateways or []:
        repository.gateways[gateway.id] = gateway
    audit = InMemoryAuditSink()
    portal = FakePortalPublisher()
    return (
        ApiLifecycleService(repository=repository, audit_sink=audit, portal_publisher=portal),
        repository,
        audit,
        portal,
    )


def _promote_command(**overrides) -> PromoteApiCommand:
    values = {
        "tenant_id": "acme",
        "api_id": "payments-api",
        "source_environment": "dev",
        "target_environment": "staging",
        "source_gateway_instance_id": None,
        "target_gateway_instance_id": None,
        "force": False,
    }
    values.update(overrides)
    return PromoteApiCommand(**values)


async def _deploy_sync_publish_source(
    service: ApiLifecycleService,
    repository: InMemoryApiLifecycleRepository,
    api_id: str = "payments-api",
) -> GatewayDeployment:
    await service.deploy_to_environment(
        DeployApiCommand(tenant_id="acme", api_id=api_id, environment="dev"),
        _actor(),
    )
    source_deployment = next(
        deployment
        for (api_catalog_id, gateway_id), deployment in repository.deployments.items()
        if repository.gateways[gateway_id].environment == "dev"
    )
    source_deployment.sync_status = DeploymentSyncStatus.SYNCED
    source_deployment.synced_generation = source_deployment.desired_generation
    source_deployment.last_sync_success = datetime.now(UTC)
    await service.publish_to_portal(PublishApiCommand(tenant_id="acme", api_id=api_id, environment="dev"), _actor())
    return source_deployment


@pytest.mark.asyncio
async def test_e2e_promote_dev_to_staging_then_publish_target_completes_promotion() -> None:
    dev_gateway = _gateway(environment="dev", name="stoa-dev")
    staging_gateway = _gateway(environment="staging", name="stoa-staging")
    service, repository, _, _ = _service(gateways=[dev_gateway, staging_gateway])

    draft = await service.create_draft(
        CreateApiDraftCommand(
            tenant_id="acme",
            name="Payments API",
            display_name="Payments API",
            version="1.0.0",
            description="Payment operations",
            backend_url="https://payments.internal",
            openapi_spec=OPENAPI_SPEC,
        ),
        _actor(),
    )
    await service.validate_draft(ValidateApiDraftCommand(tenant_id="acme", api_id=draft.api_id), _actor())
    await _deploy_sync_publish_source(service, repository, draft.api_id)

    promotion = await service.promote_to_environment(_promote_command(api_id=draft.api_id), _actor())

    target_deployment = repository.deployments[(draft.catalog_id, staging_gateway.id)]
    assert promotion.result == "requested"
    assert promotion.promotion_status == PromotionStatus.PROMOTING.value
    assert promotion.target_deployment_id == target_deployment.id
    assert target_deployment.sync_status == DeploymentSyncStatus.PENDING
    assert target_deployment.promotion_id == promotion.promotion_id
    assert repository.apis[("acme", draft.api_id)].status == "ready"

    target_deployment.sync_status = DeploymentSyncStatus.SYNCED
    target_deployment.synced_generation = target_deployment.desired_generation
    target_deployment.last_sync_success = datetime.now(UTC)
    await service.publish_to_portal(
        PublishApiCommand(tenant_id="acme", api_id=draft.api_id, environment="staging"),
        _actor(),
    )
    state = await service.get_lifecycle_state("acme", draft.api_id)

    assert {deployment.environment for deployment in state.deployments} == {"dev", "staging"}
    assert state.portal.last_environment == "staging"
    assert state.promotions[0].status == PromotionStatus.PROMOTED.value
    assert state.lifecycle_phase == "promoted"


@pytest.mark.asyncio
async def test_promote_draft_api_is_refused() -> None:
    service, _, _, _ = _service(api=_api(status="draft"), gateways=[_gateway(), _gateway(environment="staging")])

    with pytest.raises(ApiLifecycleTransitionError, match="cannot be promoted"):
        await service.promote_to_environment(_promote_command(), _actor())


@pytest.mark.asyncio
async def test_promote_archived_api_is_refused() -> None:
    service, _, _, _ = _service(api=_api(status="archived"), gateways=[_gateway(), _gateway(environment="staging")])

    with pytest.raises(ApiLifecycleTransitionError, match="cannot be promoted"):
        await service.promote_to_environment(_promote_command(), _actor())


@pytest.mark.asyncio
async def test_missing_api_returns_not_found() -> None:
    service, _, _, _ = _service(gateways=[_gateway(), _gateway(environment="staging")])

    with pytest.raises(ApiLifecycleNotFoundError):
        await service.promote_to_environment(_promote_command(), _actor())


@pytest.mark.asyncio
async def test_other_tenant_api_cannot_be_promoted() -> None:
    service, repository, _, _ = _service(
        api=_api(tenant_id="other"), gateways=[_gateway(), _gateway(environment="staging")]
    )

    with pytest.raises(ApiLifecycleNotFoundError):
        await service.promote_to_environment(_promote_command(), _actor())

    assert repository.promotions == {}


@pytest.mark.asyncio
async def test_missing_source_gateway_returns_clear_error() -> None:
    service, _, _, _ = _service(api=_api(), gateways=[_gateway(environment="staging")])

    with pytest.raises(ApiLifecycleGatewayNotFoundError, match="No gateway target"):
        await service.promote_to_environment(_promote_command(), _actor())


@pytest.mark.asyncio
async def test_missing_target_gateway_returns_clear_error() -> None:
    dev_gateway = _gateway(environment="dev")
    service, repository, _, _ = _service(api=_api(), gateways=[dev_gateway])
    await _deploy_sync_publish_source(service, repository)

    with pytest.raises(ApiLifecycleGatewayNotFoundError, match="No gateway target"):
        await service.promote_to_environment(_promote_command(), _actor())


@pytest.mark.asyncio
async def test_ambiguous_target_gateway_is_refused_without_explicit_id() -> None:
    dev_gateway = _gateway(environment="dev")
    service, repository, _, _ = _service(
        api=_api(),
        gateways=[
            dev_gateway,
            _gateway(environment="staging", name="staging-a"),
            _gateway(environment="staging", name="staging-b"),
        ],
    )
    await _deploy_sync_publish_source(service, repository)

    with pytest.raises(ApiLifecycleGatewayAmbiguousError, match="Multiple gateway targets"):
        await service.promote_to_environment(_promote_command(), _actor())


@pytest.mark.asyncio
async def test_missing_source_deployment_is_refused() -> None:
    service, _, _, _ = _service(api=_api(), gateways=[_gateway(), _gateway(environment="staging")])

    with pytest.raises(ApiLifecycleNotFoundError, match="No source GatewayDeployment"):
        await service.promote_to_environment(_promote_command(), _actor())


@pytest.mark.asyncio
async def test_unsynced_source_deployment_is_refused() -> None:
    service, _, _, _ = _service(api=_api(), gateways=[_gateway(), _gateway(environment="staging")])
    await service.deploy_to_environment(
        DeployApiCommand(tenant_id="acme", api_id="payments-api", environment="dev"), _actor()
    )

    with pytest.raises(ApiLifecycleTransitionError, match="not 'synced'"):
        await service.promote_to_environment(_promote_command(), _actor())


@pytest.mark.asyncio
async def test_unpublished_source_is_refused() -> None:
    service, repository, _, _ = _service(api=_api(), gateways=[_gateway(), _gateway(environment="staging")])
    await service.deploy_to_environment(
        DeployApiCommand(tenant_id="acme", api_id="payments-api", environment="dev"), _actor()
    )
    deployment = next(iter(repository.deployments.values()))
    deployment.sync_status = DeploymentSyncStatus.SYNCED
    deployment.synced_generation = deployment.desired_generation

    with pytest.raises(ApiLifecycleTransitionError, match="not published"):
        await service.promote_to_environment(_promote_command(), _actor())


@pytest.mark.asyncio
async def test_invalid_promotion_chain_is_refused() -> None:
    service, _, _, _ = _service(api=_api(), gateways=[_gateway(), _gateway(environment="staging")])

    with pytest.raises(ApiLifecycleValidationError, match="Invalid promotion chain"):
        await service.promote_to_environment(
            _promote_command(source_environment="dev", target_environment="production"),
            _actor(),
        )


@pytest.mark.asyncio
async def test_repeated_promotion_is_idempotent_without_duplicate_promotion_or_deployment() -> None:
    dev_gateway = _gateway(environment="dev")
    staging_gateway = _gateway(environment="staging")
    service, repository, audit, _ = _service(api=_api(), gateways=[dev_gateway, staging_gateway])
    await _deploy_sync_publish_source(service, repository)

    first = await service.promote_to_environment(_promote_command(), _actor())
    second = await service.promote_to_environment(_promote_command(), _actor())

    assert first.result == "requested"
    assert second.result == "unchanged"
    assert len(repository.promotions) == 1
    assert len([gateway for (_api_id, gateway) in repository.deployments if gateway == staging_gateway.id]) == 1
    assert audit.events[-1]["action"] == "api_lifecycle.promotion_idempotent"


@pytest.mark.asyncio
async def test_get_lifecycle_exposes_promotion_and_target_deployment() -> None:
    service, repository, _, _ = _service(api=_api(), gateways=[_gateway(), _gateway(environment="staging")])
    await _deploy_sync_publish_source(service, repository)
    await service.promote_to_environment(_promote_command(), _actor())

    state = await service.get_lifecycle_state("acme", "payments-api")

    assert state.catalog_status == "ready"
    assert len(state.deployments) == 2
    assert state.promotions[0].status == PromotionStatus.PROMOTING.value
    assert state.lifecycle_phase == "promoting"
