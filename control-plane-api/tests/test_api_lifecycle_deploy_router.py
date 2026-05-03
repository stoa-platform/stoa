"""Router tests for API lifecycle deployment requests."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from src.services.api_lifecycle.errors import (
    ApiLifecycleGatewayAmbiguousError,
    ApiLifecycleGatewayNotFoundError,
    ApiLifecycleTransitionError,
    ApiLifecycleValidationError,
)
from src.services.api_lifecycle.ports import (
    ApiDeploymentRequestOutcome,
    ApiLifecycleState,
    ApiSpecState,
)


@dataclass
class FakeDeployService:
    outcome: ApiDeploymentRequestOutcome | None = None
    exc: Exception | None = None

    async def deploy_to_environment(self, command, actor):
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
        lifecycle_phase="ready",
        portal_published=False,
        tags=[],
        spec=ApiSpecState(source="inline", has_openapi_spec=True),
        deployments=[],
        promotions=[],
    )


def _outcome() -> ApiDeploymentRequestOutcome:
    return ApiDeploymentRequestOutcome(
        tenant_id="acme",
        api_id="payments-api",
        environment="dev",
        gateway_instance_id=uuid4(),
        deployment_id=uuid4(),
        deployment_status="pending",
        action="created",
        lifecycle_state=_lifecycle_state(),
    )


def _patch_service(monkeypatch, service: FakeDeployService) -> None:
    import src.routers.api_lifecycle as router_module

    def build_service(_db):
        return service

    monkeypatch.setattr(router_module, "_build_service", build_service)


def test_deploy_lifecycle_endpoint_returns_deployment_response(client_as_tenant_admin, monkeypatch) -> None:
    _patch_service(monkeypatch, FakeDeployService(outcome=_outcome()))

    response = client_as_tenant_admin.post(
        "/v1/tenants/acme/apis/payments-api/lifecycle/deployments",
        json={"environment": "dev"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["api_id"] == "payments-api"
    assert data["environment"] == "dev"
    assert data["deployment_status"] == "pending"
    assert data["action"] == "created"
    assert data["lifecycle"]["catalog_status"] == "ready"


def test_deploy_lifecycle_endpoint_maps_transition_error_to_409(client_as_tenant_admin, monkeypatch) -> None:
    _patch_service(
        monkeypatch, FakeDeployService(exc=ApiLifecycleTransitionError("API status 'draft' cannot be deployed"))
    )

    response = client_as_tenant_admin.post(
        "/v1/tenants/acme/apis/payments-api/lifecycle/deployments",
        json={"environment": "dev"},
    )

    assert response.status_code == 409


def test_deploy_lifecycle_endpoint_maps_missing_gateway_to_404(client_as_tenant_admin, monkeypatch) -> None:
    _patch_service(monkeypatch, FakeDeployService(exc=ApiLifecycleGatewayNotFoundError("Gateway not found")))

    response = client_as_tenant_admin.post(
        "/v1/tenants/acme/apis/payments-api/lifecycle/deployments",
        json={"environment": "dev", "gateway_instance_id": str(uuid4())},
    )

    assert response.status_code == 404


def test_deploy_lifecycle_endpoint_maps_ambiguous_gateway_to_409(client_as_tenant_admin, monkeypatch) -> None:
    _patch_service(monkeypatch, FakeDeployService(exc=ApiLifecycleGatewayAmbiguousError("Multiple gateway targets")))

    response = client_as_tenant_admin.post(
        "/v1/tenants/acme/apis/payments-api/lifecycle/deployments",
        json={"environment": "dev"},
    )

    assert response.status_code == 409


def test_deploy_lifecycle_endpoint_maps_invalid_environment_to_422(client_as_tenant_admin, monkeypatch) -> None:
    _patch_service(
        monkeypatch, FakeDeployService(exc=ApiLifecycleValidationError("Invalid deployment environment: qa"))
    )

    response = client_as_tenant_admin.post(
        "/v1/tenants/acme/apis/payments-api/lifecycle/deployments",
        json={"environment": "qa"},
    )

    assert response.status_code == 422
