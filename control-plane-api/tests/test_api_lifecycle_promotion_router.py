"""Router tests for API lifecycle promotion requests."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from src.services.api_lifecycle.errors import (
    ApiLifecycleGatewayAmbiguousError,
    ApiLifecycleGatewayNotFoundError,
    ApiLifecycleNotFoundError,
    ApiLifecycleTransitionError,
    ApiLifecycleValidationError,
)
from src.services.api_lifecycle.ports import (
    ApiLifecycleState,
    ApiPromotionRequestOutcome,
    ApiSpecState,
)


@dataclass
class FakePromoteService:
    outcome: ApiPromotionRequestOutcome | None = None
    exc: Exception | None = None

    async def promote_to_environment(self, command, actor):
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
        lifecycle_phase="promoting",
        portal_published=True,
        tags=[],
        spec=ApiSpecState(source="inline", has_openapi_spec=True),
        deployments=[],
        promotions=[],
    )


def _outcome() -> ApiPromotionRequestOutcome:
    return ApiPromotionRequestOutcome(
        tenant_id="acme",
        api_id="payments-api",
        promotion_id=uuid4(),
        source_environment="dev",
        target_environment="staging",
        source_gateway_instance_id=uuid4(),
        target_gateway_instance_id=uuid4(),
        target_deployment_id=uuid4(),
        promotion_status="promoting",
        deployment_status="pending",
        result="requested",
        lifecycle_state=_lifecycle_state(),
    )


def _patch_service(monkeypatch, service: FakePromoteService) -> None:
    import src.routers.api_lifecycle as router_module

    def build_service(_db):
        return service

    monkeypatch.setattr(router_module, "_build_service", build_service)


def test_promote_lifecycle_endpoint_returns_promotion_response(client_as_tenant_admin, monkeypatch) -> None:
    _patch_service(monkeypatch, FakePromoteService(outcome=_outcome()))

    response = client_as_tenant_admin.post(
        "/v1/tenants/acme/apis/payments-api/lifecycle/promotions",
        json={"source_environment": "dev", "target_environment": "staging"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["api_id"] == "payments-api"
    assert data["source_environment"] == "dev"
    assert data["target_environment"] == "staging"
    assert data["promotion_status"] == "promoting"
    assert data["deployment_status"] == "pending"
    assert data["result"] == "requested"
    assert data["lifecycle"]["catalog_status"] == "ready"


def test_promote_lifecycle_endpoint_maps_transition_error_to_409(client_as_tenant_admin, monkeypatch) -> None:
    _patch_service(monkeypatch, FakePromoteService(exc=ApiLifecycleTransitionError("source is not synced")))

    response = client_as_tenant_admin.post(
        "/v1/tenants/acme/apis/payments-api/lifecycle/promotions",
        json={"source_environment": "dev", "target_environment": "staging"},
    )

    assert response.status_code == 409


def test_promote_lifecycle_endpoint_maps_missing_api_to_404(client_as_tenant_admin, monkeypatch) -> None:
    _patch_service(monkeypatch, FakePromoteService(exc=ApiLifecycleNotFoundError("API not found")))

    response = client_as_tenant_admin.post(
        "/v1/tenants/acme/apis/payments-api/lifecycle/promotions",
        json={"source_environment": "dev", "target_environment": "staging"},
    )

    assert response.status_code == 404


def test_promote_lifecycle_endpoint_maps_missing_gateway_to_404(client_as_tenant_admin, monkeypatch) -> None:
    _patch_service(monkeypatch, FakePromoteService(exc=ApiLifecycleGatewayNotFoundError("Gateway not found")))

    response = client_as_tenant_admin.post(
        "/v1/tenants/acme/apis/payments-api/lifecycle/promotions",
        json={"source_environment": "dev", "target_environment": "staging"},
    )

    assert response.status_code == 404


def test_promote_lifecycle_endpoint_maps_ambiguous_gateway_to_409(client_as_tenant_admin, monkeypatch) -> None:
    _patch_service(monkeypatch, FakePromoteService(exc=ApiLifecycleGatewayAmbiguousError("Multiple gateway targets")))

    response = client_as_tenant_admin.post(
        "/v1/tenants/acme/apis/payments-api/lifecycle/promotions",
        json={"source_environment": "dev", "target_environment": "staging"},
    )

    assert response.status_code == 409


def test_promote_lifecycle_endpoint_maps_invalid_chain_to_422(client_as_tenant_admin, monkeypatch) -> None:
    _patch_service(monkeypatch, FakePromoteService(exc=ApiLifecycleValidationError("Invalid promotion chain")))

    response = client_as_tenant_admin.post(
        "/v1/tenants/acme/apis/payments-api/lifecycle/promotions",
        json={"source_environment": "dev", "target_environment": "production"},
    )

    assert response.status_code == 422
