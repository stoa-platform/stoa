"""Regression test: build_desired_state must include openapi_spec.

webMethods rejects API creation when apiDefinition is empty (400).
The root cause was build_desired_state() reading openapi_spec to compute
hash/methods but not including it in the returned dict.
"""

from types import SimpleNamespace
from uuid import uuid4

from src.services.gateway_deployment_service import GatewayDeploymentService


def _make_catalog(openapi_spec=None, api_metadata=None):
    return SimpleNamespace(
        id=uuid4(),
        api_id="test-api",
        api_name="test-api",
        version="1.0.0",
        tenant_id="tenant-a",
        openapi_spec=openapi_spec,
        api_metadata=api_metadata,
    )


def test_regression_desired_state_includes_openapi_spec():
    """desired_state must contain openapi_spec when catalog has one."""
    spec = {
        "openapi": "3.0.3",
        "info": {"title": "Petstore", "version": "1.0.0"},
        "servers": [{"url": "https://petstore.swagger.io/v2"}],
        "paths": {"/pets": {"get": {"summary": "List pets"}}},
    }
    catalog = _make_catalog(openapi_spec=spec)
    state = GatewayDeploymentService.build_desired_state(catalog)

    assert "openapi_spec" in state, "openapi_spec missing from desired_state"
    assert state["openapi_spec"] == spec
    assert state["openapi_spec"]["openapi"] == "3.0.3"


def test_regression_desired_state_no_spec_is_none():
    """desired_state.openapi_spec is None when catalog has no spec."""
    catalog = _make_catalog(openapi_spec=None, api_metadata=None)
    state = GatewayDeploymentService.build_desired_state(catalog)

    assert state["openapi_spec"] is None


def test_regression_desired_state_falls_back_to_metadata():
    """desired_state uses api_metadata when openapi_spec is absent."""
    metadata = {"backend_url": "https://example.com", "description": "test"}
    catalog = _make_catalog(openapi_spec=None, api_metadata=metadata)
    state = GatewayDeploymentService.build_desired_state(catalog)

    assert state["openapi_spec"] == metadata
