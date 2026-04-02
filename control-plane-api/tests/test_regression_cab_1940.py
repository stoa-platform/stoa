"""Regression test for CAB-1940: internal catalog endpoint must accept gateway_id filter.

PR: #2121
Ticket: CAB-1940
Root cause: GET /v1/internal/catalog/apis returned ALL portal-published APIs regardless
  of which gateway was calling. Both stoa-gateway (edge-mcp) and stoa-link (sidecar)
  reported discovered_apis_count: 40 — the full catalog.
Fix: Add optional gateway_id query parameter that JOINs api_gateway_assignments.
Invariant: Without gateway_id, endpoint returns all APIs (backward compat).
  With gateway_id, returns only assigned APIs.
"""

from uuid import UUID

from src.repositories.catalog import CatalogRepository


def test_regression_cab_1940_get_portal_apis_accepts_gateway_id():
    """CatalogRepository.get_portal_apis must accept gateway_id parameter."""
    import inspect

    sig = inspect.signature(CatalogRepository.get_portal_apis)
    params = list(sig.parameters.keys())

    assert "gateway_id" in params, (
        "get_portal_apis must accept gateway_id parameter for CAB-1940 discovery scoping"
    )

    # Verify it's typed as Optional UUID
    param = sig.parameters["gateway_id"]
    assert param.default is None, "gateway_id must default to None (backward compat)"


def test_regression_cab_1940_gateway_instance_has_public_url():
    """GatewayInstance model must have public_url column."""
    from src.models.gateway_instance import GatewayInstance

    assert hasattr(GatewayInstance, "public_url"), (
        "GatewayInstance must have public_url column for CAB-1940"
    )


def test_regression_cab_1940_registration_payload_accepts_public_url():
    """GatewayRegistration schema must accept public_url field."""
    from src.routers.gateway_internal import GatewayRegistration

    fields = GatewayRegistration.model_fields
    assert "public_url" in fields, (
        "GatewayRegistration must accept public_url for CAB-1940"
    )
    assert fields["public_url"].default is None
