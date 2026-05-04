"""Portal publication tests for the canonical API lifecycle service, Slice 4."""

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
    ApiLifecycleSpecValidationError,
    ApiLifecycleTransitionError,
)
from src.services.api_lifecycle.portal import CatalogPortalPublisher
from src.services.api_lifecycle.ports import (
    CreateApiDraftCommand,
    DeployApiCommand,
    GatewayDeploymentSnapshot,
    GatewayTarget,
    LifecycleActor,
    PortalPublicationState,
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
                    last_sync_attempt=deployment.last_sync_attempt,
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


def _api(
    status: str = "ready",
    tenant_id: str = "acme",
    api_id: str = "payments-api",
    openapi_spec: dict[str, Any] | None = OPENAPI_SPEC,
    spec_reference: str | None = None,
) -> APICatalog:
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
            "lifecycle": {
                "catalog_status": status,
                "spec_source": "reference" if spec_reference else "inline",
                "spec_reference": spec_reference,
            },
        },
        openapi_spec=openapi_spec,
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


def _deployment(
    api: APICatalog,
    gateway: GatewayTarget,
    status: DeploymentSyncStatus = DeploymentSyncStatus.SYNCED,
) -> GatewayDeployment:
    return GatewayDeployment(
        id=uuid4(),
        api_catalog_id=api.id,
        gateway_instance_id=gateway.id,
        desired_state={"api_id": api.api_id, "spec_hash": "abc123"},
        desired_at=datetime.now(UTC),
        desired_generation=1,
        synced_generation=1 if status == DeploymentSyncStatus.SYNCED else 0,
        attempted_generation=1,
        sync_status=status,
        sync_attempts=1,
        last_sync_success=datetime.now(UTC) if status == DeploymentSyncStatus.SYNCED else None,
    )


def _service(
    *,
    api: APICatalog | None = None,
    gateways: list[GatewayTarget] | None = None,
    deployments: list[GatewayDeployment] | None = None,
) -> tuple[ApiLifecycleService, InMemoryApiLifecycleRepository, InMemoryAuditSink, FakePortalPublisher]:
    repository = InMemoryApiLifecycleRepository()
    if api:
        repository.apis[(api.tenant_id, api.api_id)] = api
    for gateway in gateways or []:
        repository.gateways[gateway.id] = gateway
    for deployment in deployments or []:
        repository.deployments[(deployment.api_catalog_id, deployment.gateway_instance_id)] = deployment
    audit = InMemoryAuditSink()
    portal = FakePortalPublisher()
    return (
        ApiLifecycleService(repository=repository, audit_sink=audit, portal_publisher=portal),
        repository,
        audit,
        portal,
    )


def _publish_command(**overrides) -> PublishApiCommand:
    values = {
        "tenant_id": "acme",
        "api_id": "payments-api",
        "environment": "dev",
        "gateway_instance_id": None,
        "force": False,
    }
    values.update(overrides)
    return PublishApiCommand(**values)


@pytest.mark.asyncio
async def test_ready_api_with_synced_deployment_publishes_to_portal() -> None:
    api = _api()
    gateway = _gateway()
    service, repository, _, portal = _service(api=api, gateways=[gateway], deployments=[_deployment(api, gateway)])

    outcome = await service.publish_to_portal(_publish_command(), _actor())

    assert outcome.result == "published"
    assert outcome.publication_status == "published"
    assert outcome.portal_published is True
    assert repository.apis[("acme", "payments-api")].portal_published is True
    assert len(portal.calls) == 1


@pytest.mark.asyncio
async def test_publish_keeps_catalog_status_ready() -> None:
    api = _api()
    gateway = _gateway()
    service, repository, _, _ = _service(api=api, gateways=[gateway], deployments=[_deployment(api, gateway)])

    await service.publish_to_portal(_publish_command(), _actor())

    assert repository.apis[("acme", "payments-api")].status == "ready"


@pytest.mark.asyncio
async def test_get_lifecycle_after_publish_returns_portal_state() -> None:
    api = _api()
    gateway = _gateway()
    service, _, _, _ = _service(api=api, gateways=[gateway], deployments=[_deployment(api, gateway)])
    await service.publish_to_portal(_publish_command(), _actor())

    state = await service.get_lifecycle_state("acme", "payments-api")

    assert state.catalog_status == "ready"
    assert state.portal_published is True
    assert state.portal.published is True
    assert state.portal.status == "published"
    assert state.portal.last_environment == "dev"
    assert state.portal.publications[0].gateway_instance_id == gateway.id


@pytest.mark.asyncio
async def test_repeated_publish_same_context_is_idempotent_without_duplicate() -> None:
    api = _api()
    gateway = _gateway()
    service, repository, audit, portal = _service(api=api, gateways=[gateway], deployments=[_deployment(api, gateway)])

    first = await service.publish_to_portal(_publish_command(), _actor())
    second = await service.publish_to_portal(_publish_command(), _actor())

    publications = repository.apis[("acme", "payments-api")].api_metadata["lifecycle"]["portal_publications"]
    assert first.result == "published"
    assert second.result == "unchanged"
    assert len(publications) == 1
    assert len(portal.calls) == 1
    assert audit.events[-1]["action"] == "api_lifecycle.publish_idempotent"


@pytest.mark.asyncio
async def test_force_republishes_same_context_without_duplicate() -> None:
    api = _api()
    gateway = _gateway()
    service, repository, _, portal = _service(api=api, gateways=[gateway], deployments=[_deployment(api, gateway)])

    await service.publish_to_portal(_publish_command(), _actor())
    second = await service.publish_to_portal(_publish_command(force=True), _actor())

    publications = repository.apis[("acme", "payments-api")].api_metadata["lifecycle"]["portal_publications"]
    assert second.result == "republished"
    assert len(publications) == 1
    assert len(portal.calls) == 2


@pytest.mark.asyncio
async def test_pending_deployment_cannot_be_published() -> None:
    api = _api()
    gateway = _gateway()
    service, _, audit, _ = _service(
        api=api,
        gateways=[gateway],
        deployments=[_deployment(api, gateway, DeploymentSyncStatus.PENDING)],
    )

    with pytest.raises(ApiLifecycleTransitionError, match="not 'synced'"):
        await service.publish_to_portal(_publish_command(), _actor())

    assert audit.events[-1]["action"] == "api_lifecycle.publish_failed"
    assert audit.events[-1]["details"]["publication"]["code"] == "deployment_not_synced"


@pytest.mark.asyncio
async def test_missing_deployment_cannot_be_published() -> None:
    service, _, _, _ = _service(api=_api(), gateways=[_gateway()])

    with pytest.raises(ApiLifecycleNotFoundError, match="No GatewayDeployment"):
        await service.publish_to_portal(_publish_command(), _actor())


@pytest.mark.asyncio
async def test_draft_api_cannot_be_published() -> None:
    api = _api(status="draft")
    gateway = _gateway()
    service, _, _, _ = _service(api=api, gateways=[gateway], deployments=[_deployment(api, gateway)])

    with pytest.raises(ApiLifecycleTransitionError, match="cannot be published"):
        await service.publish_to_portal(_publish_command(), _actor())


@pytest.mark.asyncio
async def test_archived_api_cannot_be_published() -> None:
    api = _api(status="archived")
    gateway = _gateway()
    service, _, _, _ = _service(api=api, gateways=[gateway], deployments=[_deployment(api, gateway)])

    with pytest.raises(ApiLifecycleTransitionError, match="cannot be published"):
        await service.publish_to_portal(_publish_command(), _actor())


@pytest.mark.asyncio
async def test_missing_api_returns_not_found() -> None:
    service, _, _, _ = _service(gateways=[_gateway()])

    with pytest.raises(ApiLifecycleNotFoundError):
        await service.publish_to_portal(_publish_command(), _actor())


@pytest.mark.asyncio
async def test_other_tenant_api_cannot_be_published() -> None:
    api = _api(tenant_id="other")
    gateway = _gateway()
    service, repository, _, portal = _service(api=api, gateways=[gateway], deployments=[_deployment(api, gateway)])

    with pytest.raises(ApiLifecycleNotFoundError):
        await service.publish_to_portal(_publish_command(), _actor())

    assert repository.apis[("other", "payments-api")].portal_published is False
    assert portal.calls == []


@pytest.mark.asyncio
async def test_explicit_missing_gateway_returns_clear_error() -> None:
    service, _, _, _ = _service(api=_api())

    with pytest.raises(ApiLifecycleGatewayNotFoundError, match="Gateway"):
        await service.publish_to_portal(_publish_command(gateway_instance_id=uuid4()), _actor())


@pytest.mark.asyncio
async def test_multiple_gateways_without_gateway_id_is_ambiguous() -> None:
    service, _, _, _ = _service(api=_api(), gateways=[_gateway(name="dev-a"), _gateway(name="dev-b")])

    with pytest.raises(ApiLifecycleGatewayAmbiguousError, match="Multiple gateway targets"):
        await service.publish_to_portal(_publish_command(), _actor())


@pytest.mark.asyncio
async def test_spec_reference_without_resolved_spec_is_refused() -> None:
    api = _api(openapi_spec=None, spec_reference="git://catalog/apis/payments/openapi.yaml")
    gateway = _gateway()
    service, _, audit, _ = _service(api=api, gateways=[gateway], deployments=[_deployment(api, gateway)])

    with pytest.raises(ApiLifecycleSpecValidationError) as exc:
        await service.publish_to_portal(_publish_command(), _actor())

    assert exc.value.code == "spec_reference_unresolved"
    assert audit.events[-1]["details"]["publication"]["code"] == "spec_reference_unresolved"


@pytest.mark.asyncio
async def test_success_audit_event_is_written() -> None:
    api = _api()
    gateway = _gateway()
    service, _, audit, _ = _service(api=api, gateways=[gateway], deployments=[_deployment(api, gateway)])

    outcome = await service.publish_to_portal(_publish_command(), _actor())

    assert audit.events[-1]["action"] == "api_lifecycle.publish_requested"
    assert audit.events[-1]["details"]["deployment_id"] == str(outcome.deployment_id)
    assert audit.events[-1]["details"]["result"] == "published"


@pytest.mark.asyncio
async def test_e2e_create_validate_deploy_sync_publish_get_lifecycle() -> None:
    gateway = _gateway()
    service, repository, _, _ = _service(gateways=[gateway])

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
    validation = await service.validate_draft(
        ValidateApiDraftCommand(tenant_id="acme", api_id=draft.api_id),
        _actor(),
    )
    deployment_outcome = await service.deploy_to_environment(
        DeployApiCommand(
            tenant_id="acme",
            api_id=draft.api_id,
            environment="dev",
        ),
        _actor(),
    )
    deployment = next(iter(repository.deployments.values()))
    deployment.sync_status = DeploymentSyncStatus.SYNCED
    deployment.synced_generation = deployment.desired_generation
    deployment.last_sync_success = datetime.now(UTC)

    publication = await service.publish_to_portal(_publish_command(api_id=draft.api_id), _actor())
    state = await service.get_lifecycle_state("acme", draft.api_id)

    assert validation.status == "ready"
    assert deployment_outcome.deployment_status == "pending"
    assert publication.result == "published"
    assert state.catalog_status == "ready"
    assert state.deployments[0].sync_status == "synced"
    assert state.portal.published is True
    assert state.promotions == []
