"""Router tests for API lifecycle portal publication requests."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from src.services.api_lifecycle.errors import (
    ApiLifecycleGatewayAmbiguousError,
    ApiLifecycleGatewayNotFoundError,
    ApiLifecycleNotFoundError,
    ApiLifecycleSpecValidationError,
    ApiLifecycleTransitionError,
    ApiLifecycleValidationError,
)
from src.services.api_lifecycle.ports import (
    ApiLifecycleState,
    ApiPortalPublicationOutcome,
    ApiSpecState,
)


@dataclass
class FakePublishService:
    outcome: ApiPortalPublicationOutcome | None = None
    exc: Exception | None = None

    async def publish_to_portal(self, command, actor):
        if self.exc:
            raise self.exc
        return self.outcome


def _lifecycle_state() -> ApiLifecycleState:
    return ApiLifecycleState(
        catalog_id=uuid4(),
        tenant_id="acme",
        api_id="payments-api",
        api_name="Payments API",
        display_name="Payments API",
        version="1.0.0",
        description="Payment operations",
        backend_url="https://payments.internal",
        catalog_status="ready",
        lifecycle_phase="published",
        portal_published=True,
        tags=[],
        spec=ApiSpecState(source="inline", has_openapi_spec=True),
        deployments=[],
        promotions=[],
    )


def _outcome() -> ApiPortalPublicationOutcome:
    return ApiPortalPublicationOutcome(
        tenant_id="acme",
        api_id="payments-api",
        environment="dev",
        gateway_instance_id=uuid4(),
        deployment_id=uuid4(),
        publication_status="published",
        portal_published=True,
        result="published",
        lifecycle_state=_lifecycle_state(),
    )


def _patch_service(monkeypatch, service: FakePublishService) -> None:
    import src.routers.api_lifecycle as router_module

    def build_service(_db):
        return service

    monkeypatch.setattr(router_module, "_build_service", build_service)


def test_publish_lifecycle_endpoint_returns_publication_response(client_as_tenant_admin, monkeypatch) -> None:
    _patch_service(monkeypatch, FakePublishService(outcome=_outcome()))

    response = client_as_tenant_admin.post(
        "/v1/tenants/acme/apis/payments-api/lifecycle/publications",
        json={"environment": "dev"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["api_id"] == "payments-api"
    assert data["environment"] == "dev"
    assert data["publication_status"] == "published"
    assert data["portal_published"] is True
    assert data["result"] == "published"
    assert data["lifecycle"]["catalog_status"] == "ready"


def test_publish_lifecycle_endpoint_maps_transition_error_to_409(client_as_tenant_admin, monkeypatch) -> None:
    _patch_service(
        monkeypatch, FakePublishService(exc=ApiLifecycleTransitionError("Deployment is 'pending', not 'synced'"))
    )

    response = client_as_tenant_admin.post(
        "/v1/tenants/acme/apis/payments-api/lifecycle/publications",
        json={"environment": "dev"},
    )

    assert response.status_code == 409


def test_publish_lifecycle_endpoint_maps_missing_api_to_404(client_as_tenant_admin, monkeypatch) -> None:
    _patch_service(monkeypatch, FakePublishService(exc=ApiLifecycleNotFoundError("API not found")))

    response = client_as_tenant_admin.post(
        "/v1/tenants/acme/apis/payments-api/lifecycle/publications",
        json={"environment": "dev"},
    )

    assert response.status_code == 404


def test_publish_lifecycle_endpoint_maps_missing_gateway_to_404(client_as_tenant_admin, monkeypatch) -> None:
    _patch_service(monkeypatch, FakePublishService(exc=ApiLifecycleGatewayNotFoundError("Gateway not found")))

    response = client_as_tenant_admin.post(
        "/v1/tenants/acme/apis/payments-api/lifecycle/publications",
        json={"environment": "dev", "gateway_instance_id": str(uuid4())},
    )

    assert response.status_code == 404


def test_publish_lifecycle_endpoint_maps_ambiguous_gateway_to_409(client_as_tenant_admin, monkeypatch) -> None:
    _patch_service(monkeypatch, FakePublishService(exc=ApiLifecycleGatewayAmbiguousError("Multiple gateway targets")))

    response = client_as_tenant_admin.post(
        "/v1/tenants/acme/apis/payments-api/lifecycle/publications",
        json={"environment": "dev"},
    )

    assert response.status_code == 409


def test_publish_lifecycle_endpoint_maps_invalid_spec_to_422(client_as_tenant_admin, monkeypatch) -> None:
    _patch_service(
        monkeypatch,
        FakePublishService(exc=ApiLifecycleSpecValidationError("openapi_spec_missing", "OpenAPI spec is required")),
    )

    response = client_as_tenant_admin.post(
        "/v1/tenants/acme/apis/payments-api/lifecycle/publications",
        json={"environment": "dev"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "openapi_spec_missing"


def test_publish_lifecycle_endpoint_maps_invalid_environment_to_422(client_as_tenant_admin, monkeypatch) -> None:
    _patch_service(
        monkeypatch, FakePublishService(exc=ApiLifecycleValidationError("Invalid deployment environment: qa"))
    )

    response = client_as_tenant_admin.post(
        "/v1/tenants/acme/apis/payments-api/lifecycle/publications",
        json={"environment": "qa"},
    )

    assert response.status_code == 422
