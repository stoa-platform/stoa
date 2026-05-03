"""Tests for the canonical API lifecycle service, Slice 1."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest

from src.models.catalog import APICatalog
from src.services.api_lifecycle.errors import (
    ApiLifecycleConflictError,
    ApiLifecycleNotFoundError,
    ApiLifecycleSpecValidationError,
    ApiLifecycleTransitionError,
    ApiLifecycleValidationError,
)
from src.services.api_lifecycle.ports import (
    CreateApiDraftCommand,
    GatewayDeploymentSnapshot,
    LifecycleActor,
    PromotionSnapshot,
    ValidateApiDraftCommand,
)
from src.services.api_lifecycle.service import ApiLifecycleService

OPENAPI_SPEC: dict[str, Any] = {
    "openapi": "3.0.3",
    "info": {"title": "Payments API", "version": "1.0.0"},
    "paths": {"/payments": {"get": {"responses": {"200": {"description": "ok"}}}}},
}

SWAGGER_SPEC: dict[str, Any] = {
    "swagger": "2.0",
    "info": {"title": "Pets API", "version": "1.0.0"},
    "paths": {"/pets": {"get": {"responses": {"200": {"description": "ok"}}}}},
}


@dataclass
class InMemoryApiLifecycleRepository:
    rows: dict[tuple[str, str], APICatalog] = field(default_factory=dict)

    async def get_api_by_id(self, tenant_id: str, api_id: str) -> APICatalog | None:
        return self.rows.get((tenant_id, api_id))

    async def get_api_by_name_version(self, tenant_id: str, api_name: str, version: str) -> APICatalog | None:
        return next(
            (
                row
                for (row_tenant_id, _), row in self.rows.items()
                if row_tenant_id == tenant_id and row.api_name == api_name and row.version == version
            ),
            None,
        )

    async def create_api_catalog(self, api: APICatalog) -> APICatalog:
        self.rows[(api.tenant_id, api.api_id)] = api
        return api

    async def save_api_catalog(self, api: APICatalog) -> APICatalog:
        self.rows[(api.tenant_id, api.api_id)] = api
        return api

    async def list_gateway_deployments(self, api_catalog_id: UUID) -> list[GatewayDeploymentSnapshot]:
        return []

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


def _service() -> tuple[ApiLifecycleService, InMemoryApiLifecycleRepository, InMemoryAuditSink]:
    repository = InMemoryApiLifecycleRepository()
    audit = InMemoryAuditSink()
    return ApiLifecycleService(repository=repository, audit_sink=audit), repository, audit


def _command(**overrides) -> CreateApiDraftCommand:
    values = {
        "tenant_id": "acme",
        "name": "Payments API",
        "display_name": "Payments API",
        "version": "1.0.0",
        "description": "Payment operations",
        "backend_url": "https://payments.internal",
        "openapi_spec": OPENAPI_SPEC,
        "tags": ("finance",),
        "owner_team": "payments",
    }
    values.update(overrides)
    return CreateApiDraftCommand(**values)


def _actor() -> LifecycleActor:
    return LifecycleActor(actor_id="user-1", email="owner@acme.test", username="owner")


def _direct_catalog(
    *,
    tenant_id: str = "acme",
    api_id: str = "payments-api",
    status: str = "draft",
    spec: Any = OPENAPI_SPEC,
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
                "spec_source": "inline" if spec else "reference",
                "spec_reference": spec_reference,
            },
        },
        openapi_spec=spec,
    )


@pytest.mark.asyncio
async def test_create_draft_persists_catalog_spec_and_audit_event() -> None:
    service, repository, audit = _service()

    state = await service.create_draft(_command(), _actor())

    assert state.api_id == "payments-api"
    assert state.catalog_status == "draft"
    assert state.lifecycle_phase == "draft"
    assert state.portal_published is False
    assert state.deployments == []
    assert state.promotions == []
    assert state.spec.source == "inline"
    assert state.spec.has_openapi_spec is True

    stored = repository.rows[("acme", "payments-api")]
    assert stored.status == "draft"
    assert stored.portal_published is False
    assert stored.openapi_spec == OPENAPI_SPEC
    assert stored.api_metadata["lifecycle"]["spec_source"] == "inline"

    assert audit.events == [
        {
            "tenant_id": "acme",
            "actor": _actor(),
            "action": "api_lifecycle.create_draft",
            "resource_id": "payments-api",
            "resource_name": "Payments API",
            "details": {
                "api_id": "payments-api",
                "api_name": "Payments API",
                "version": "1.0.0",
                "catalog_status": "draft",
                "spec_source": "inline",
                "portal_published": False,
            },
            "outcome": "success",
            "status_code": 201,
            "method": "POST",
            "path": "/v1/tenants/acme/apis/lifecycle/drafts",
        }
    ]


@pytest.mark.asyncio
async def test_get_lifecycle_state_returns_aggregate_draft_state() -> None:
    service, _, _ = _service()
    await service.create_draft(_command(), _actor())

    state = await service.get_lifecycle_state("acme", "payments-api")

    assert state.catalog_status == "draft"
    assert state.lifecycle_phase == "draft"
    assert state.spec.source == "inline"
    assert state.deployments == []
    assert state.promotions == []
    assert state.last_error is None


@pytest.mark.asyncio
@pytest.mark.parametrize("portal_tag", ["portal:published", "promoted:portal", "portal-promoted"])
async def test_create_draft_rejects_implicit_portal_publication_tag(portal_tag: str) -> None:
    service, repository, _ = _service()

    with pytest.raises(ApiLifecycleValidationError, match="Portal publication must use"):
        await service.create_draft(_command(tags=(portal_tag,)), _actor())

    assert repository.rows == {}


@pytest.mark.asyncio
async def test_create_draft_requires_spec_or_reference() -> None:
    service, repository, _ = _service()

    with pytest.raises(ApiLifecycleValidationError, match="OpenAPI spec or spec_reference is required"):
        await service.create_draft(_command(openapi_spec=None, spec_reference=None), _actor())

    assert repository.rows == {}


@pytest.mark.asyncio
async def test_create_draft_rejects_duplicate_name_version() -> None:
    service, _, _ = _service()
    await service.create_draft(_command(), _actor())

    with pytest.raises(ApiLifecycleConflictError, match="already exists"):
        await service.create_draft(_command(), _actor())


@pytest.mark.asyncio
async def test_validate_draft_openapi3_transitions_to_ready_and_audits_success() -> None:
    service, repository, audit = _service()
    await service.create_draft(_command(openapi_spec=OPENAPI_SPEC), _actor())

    outcome = await service.validate_draft(ValidateApiDraftCommand(tenant_id="acme", api_id="payments-api"), _actor())

    assert outcome.status == "ready"
    assert outcome.validation.valid is True
    assert outcome.validation.spec_format == "openapi"
    assert outcome.validation.spec_version == "3.0.3"
    assert outcome.validation.path_count == 1
    assert outcome.lifecycle_state.catalog_status == "ready"
    assert outcome.lifecycle_state.lifecycle_phase == "ready"
    stored = repository.rows[("acme", "payments-api")]
    assert stored.status == "ready"
    assert stored.api_metadata["lifecycle"]["validation_spec_hash"]
    assert audit.events[-1]["action"] == "api_lifecycle.validate_draft"
    assert audit.events[-1]["outcome"] == "success"


@pytest.mark.asyncio
async def test_validate_draft_swagger2_transitions_to_ready() -> None:
    service, _, _ = _service()
    await service.create_draft(_command(name="Pets API", display_name="Pets API", openapi_spec=SWAGGER_SPEC), _actor())

    outcome = await service.validate_draft(ValidateApiDraftCommand(tenant_id="acme", api_id="pets-api"), _actor())

    assert outcome.status == "ready"
    assert outcome.validation.spec_format == "swagger"
    assert outcome.validation.spec_version == "2.0"


@pytest.mark.asyncio
async def test_validate_invalid_spec_is_refused_and_status_stays_draft() -> None:
    service, repository, _ = _service()
    repository.rows[("acme", "payments-api")] = _direct_catalog(spec=["not-an-object"])

    with pytest.raises(ApiLifecycleSpecValidationError) as exc:
        await service.validate_draft(ValidateApiDraftCommand(tenant_id="acme", api_id="payments-api"), _actor())

    assert exc.value.code == "openapi_spec_invalid"
    assert repository.rows[("acme", "payments-api")].status == "draft"


@pytest.mark.asyncio
async def test_validate_spec_without_paths_is_refused() -> None:
    service, repository, _ = _service()
    await service.create_draft(
        _command(openapi_spec={"openapi": "3.0.3", "info": {"title": "API", "version": "1"}}), _actor()
    )

    with pytest.raises(ApiLifecycleSpecValidationError) as exc:
        await service.validate_draft(ValidateApiDraftCommand(tenant_id="acme", api_id="payments-api"), _actor())

    assert exc.value.code == "openapi_paths_missing"
    assert repository.rows[("acme", "payments-api")].status == "draft"


@pytest.mark.asyncio
async def test_validate_spec_without_info_title_is_refused() -> None:
    service, repository, _ = _service()
    await service.create_draft(
        _command(
            openapi_spec={
                "openapi": "3.0.3",
                "info": {"version": "1"},
                "paths": {"/payments": {"get": {"responses": {"200": {"description": "ok"}}}}},
            }
        ),
        _actor(),
    )

    with pytest.raises(ApiLifecycleSpecValidationError) as exc:
        await service.validate_draft(ValidateApiDraftCommand(tenant_id="acme", api_id="payments-api"), _actor())

    assert exc.value.code == "openapi_info_title_missing"
    assert repository.rows[("acme", "payments-api")].status == "draft"


@pytest.mark.asyncio
async def test_validate_spec_without_info_version_is_refused() -> None:
    service, repository, _ = _service()
    await service.create_draft(
        _command(
            openapi_spec={
                "openapi": "3.0.3",
                "info": {"title": "API"},
                "paths": {"/payments": {"get": {"responses": {"200": {"description": "ok"}}}}},
            }
        ),
        _actor(),
    )

    with pytest.raises(ApiLifecycleSpecValidationError) as exc:
        await service.validate_draft(ValidateApiDraftCommand(tenant_id="acme", api_id="payments-api"), _actor())

    assert exc.value.code == "openapi_info_version_missing"
    assert repository.rows[("acme", "payments-api")].status == "draft"


@pytest.mark.asyncio
async def test_validate_spec_with_empty_paths_is_refused() -> None:
    service, repository, _ = _service()
    await service.create_draft(
        _command(openapi_spec={"openapi": "3.0.3", "info": {"title": "API", "version": "1"}, "paths": {}}),
        _actor(),
    )

    with pytest.raises(ApiLifecycleSpecValidationError) as exc:
        await service.validate_draft(ValidateApiDraftCommand(tenant_id="acme", api_id="payments-api"), _actor())

    assert exc.value.code == "openapi_paths_empty"
    assert repository.rows[("acme", "payments-api")].status == "draft"


@pytest.mark.asyncio
async def test_validate_operation_without_responses_is_refused() -> None:
    service, repository, _ = _service()
    await service.create_draft(
        _command(
            openapi_spec={
                "openapi": "3.0.3",
                "info": {"title": "API", "version": "1"},
                "paths": {"/payments": {"get": {"operationId": "listPayments"}}},
            }
        ),
        _actor(),
    )

    with pytest.raises(ApiLifecycleSpecValidationError) as exc:
        await service.validate_draft(ValidateApiDraftCommand(tenant_id="acme", api_id="payments-api"), _actor())

    assert exc.value.code == "openapi_operation_responses_missing"
    assert repository.rows[("acme", "payments-api")].status == "draft"


@pytest.mark.asyncio
async def test_validate_missing_api_returns_not_found() -> None:
    service, _, _ = _service()

    with pytest.raises(ApiLifecycleNotFoundError, match="was not found"):
        await service.validate_draft(ValidateApiDraftCommand(tenant_id="acme", api_id="missing-api"), _actor())


@pytest.mark.asyncio
async def test_validate_other_tenant_api_returns_not_found_without_mutating() -> None:
    service, repository, _ = _service()
    repository.rows[("other", "payments-api")] = _direct_catalog(tenant_id="other")

    with pytest.raises(ApiLifecycleNotFoundError):
        await service.validate_draft(ValidateApiDraftCommand(tenant_id="acme", api_id="payments-api"), _actor())

    assert repository.rows[("other", "payments-api")].status == "draft"


@pytest.mark.asyncio
async def test_validate_ready_api_is_idempotent_when_spec_unchanged() -> None:
    service, repository, _ = _service()
    await service.create_draft(_command(), _actor())
    first = await service.validate_draft(ValidateApiDraftCommand(tenant_id="acme", api_id="payments-api"), _actor())

    second = await service.validate_draft(ValidateApiDraftCommand(tenant_id="acme", api_id="payments-api"), _actor())

    assert first.status == "ready"
    assert second.status == "ready"
    assert repository.rows[("acme", "payments-api")].status == "ready"


@pytest.mark.asyncio
async def test_validate_archived_api_is_refused() -> None:
    service, repository, audit = _service()
    repository.rows[("acme", "payments-api")] = _direct_catalog(status="archived")

    with pytest.raises(ApiLifecycleTransitionError, match="Archived APIs cannot be validated"):
        await service.validate_draft(ValidateApiDraftCommand(tenant_id="acme", api_id="payments-api"), _actor())

    assert repository.rows[("acme", "payments-api")].status == "archived"
    assert audit.events[-1]["action"] == "api_lifecycle.validate_draft_failed"
    assert audit.events[-1]["outcome"] == "failure"


@pytest.mark.asyncio
async def test_validate_spec_reference_without_resolver_is_refused() -> None:
    service, repository, _ = _service()
    await service.create_draft(_command(openapi_spec=None, spec_reference="apis/payments/openapi.yaml"), _actor())

    with pytest.raises(ApiLifecycleSpecValidationError) as exc:
        await service.validate_draft(ValidateApiDraftCommand(tenant_id="acme", api_id="payments-api"), _actor())

    assert exc.value.code == "spec_reference_unresolved"
    assert repository.rows[("acme", "payments-api")].status == "draft"


@pytest.mark.asyncio
async def test_get_lifecycle_after_validation_returns_ready_without_gateway_state() -> None:
    service, _, _ = _service()
    await service.create_draft(_command(), _actor())
    await service.validate_draft(ValidateApiDraftCommand(tenant_id="acme", api_id="payments-api"), _actor())

    state = await service.get_lifecycle_state("acme", "payments-api")

    assert state.catalog_status == "ready"
    assert state.lifecycle_phase == "ready"
    assert state.deployments == []
    assert state.promotions == []
