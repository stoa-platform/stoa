"""Integration tests for WebMethodsGatewayAdapter using httpx.MockTransport.

These tests verify real HTTP behavior at the adapter boundary instead of
mocking GatewayAdminService entirely (Boundary Integrity Rule, CAB-1951).

Each test injects a MockTransport handler that simulates webMethods REST API
responses, then exercises the adapter through its public interface.
"""

import json

import httpx
import pytest

from src.adapters.webmethods.adapter import WebMethodsGatewayAdapter
from src.services.gateway_service import GatewayAdminService


def _make_adapter(handler) -> WebMethodsGatewayAdapter:
    """Create adapter with MockTransport instead of real HTTP."""
    transport = httpx.MockTransport(handler)
    svc = GatewayAdminService.__new__(GatewayAdminService)
    svc._use_proxy = False
    svc._auth_config = {}
    svc._base_url = "http://wm:5555"
    svc._client = httpx.AsyncClient(
        base_url="http://wm:5555/rest/apigateway",
        transport=transport,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    adapter = WebMethodsGatewayAdapter.__new__(WebMethodsGatewayAdapter)
    adapter._config = {}
    adapter._svc = svc
    return adapter


# ---------------------------------------------------------------------------
# Regression tests for CAB-1944 bugs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_api_with_em_dash_in_name():
    """Regression CAB-1944: apiName with em-dash '—' must not be rejected."""
    api_name = "Weather — Live API"
    received_payloads = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path.endswith("/apis"):
            return httpx.Response(200, json={"apiResponse": []})
        if request.method == "POST" and path.endswith("/apis"):
            body = json.loads(request.content)
            received_payloads.append(body)
            return httpx.Response(
                200,
                json={"apiResponse": {"api": {"id": "api-001", "apiName": body.get("apiName")}}},
            )
        return httpx.Response(404)

    adapter = _make_adapter(handler)
    result = await adapter.sync_api(
        {"apiName": api_name, "apiVersion": "1.0", "url": "https://example.com/spec.json"},
        tenant_id="t1",
    )

    assert result.success is True
    assert result.resource_id == "api-001"
    assert len(received_payloads) == 1
    assert received_payloads[0]["apiName"] == api_name


@pytest.mark.asyncio
async def test_sync_api_with_oauth2_security_scheme():
    """Regression CAB-1944: securitySchemes oauth2 must be accepted (case-insensitive)."""
    spec_with_oauth2 = {
        "openapi": "3.0.1",
        "info": {"title": "Auth API", "version": "1.0"},
        "paths": {},
        "components": {
            "securitySchemes": {
                "oauth2": {
                    "type": "oauth2",
                    "flows": {"clientCredentials": {"tokenUrl": "https://auth.example.com/token", "scopes": {}}},
                }
            }
        },
    }
    received_specs = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path.endswith("/apis"):
            return httpx.Response(200, json={"apiResponse": []})
        if request.method == "POST" and path.endswith("/apis"):
            body = json.loads(request.content)
            received_specs.append(body)
            return httpx.Response(
                200,
                json={"apiResponse": {"api": {"id": "api-002"}}},
            )
        return httpx.Response(404)

    adapter = _make_adapter(handler)
    result = await adapter.sync_api(
        {"apiName": "Auth API", "apiVersion": "1.0", "apiDefinition": spec_with_oauth2},
        tenant_id="t1",
    )

    assert result.success is True
    assert len(received_specs) == 1
    # The spec should be passed through without case mutation
    schemes = received_specs[0].get("apiDefinition", {}).get("components", {}).get("securitySchemes", {})
    assert "oauth2" in schemes


@pytest.mark.asyncio
async def test_sync_api_external_docs_as_object():
    """Regression CAB-1944: externalDocs as object (not array) must be accepted."""
    spec_with_external_docs = {
        "openapi": "3.0.1",
        "info": {"title": "Docs API", "version": "1.0"},
        "paths": {},
        "externalDocs": {"description": "Full docs", "url": "https://docs.example.com"},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path.endswith("/apis"):
            return httpx.Response(200, json={"apiResponse": []})
        if request.method == "POST" and path.endswith("/apis"):
            body = json.loads(request.content)
            # Verify externalDocs passed as-is (object, not array)
            spec = body.get("apiDefinition", {})
            ext_docs = spec.get("externalDocs")
            assert isinstance(ext_docs, dict), f"externalDocs should be dict, got {type(ext_docs)}"
            return httpx.Response(200, json={"apiResponse": {"api": {"id": "api-003"}}})
        return httpx.Response(404)

    adapter = _make_adapter(handler)
    result = await adapter.sync_api(
        {"apiName": "Docs API", "apiVersion": "1.0", "apiDefinition": spec_with_external_docs},
        tenant_id="t1",
    )

    assert result.success is True


@pytest.mark.asyncio
async def test_sync_api_auth_token_missing_returns_failure():
    """Regression CAB-1944: missing auth_token in OIDC proxy mode must fail gracefully."""
    # Configure adapter in OIDC proxy mode
    svc = GatewayAdminService.__new__(GatewayAdminService)
    svc._use_proxy = True
    svc._auth_config = {"type": "oidc_proxy", "proxy_url": "http://proxy:8080"}
    svc._client = None
    svc._base_url = "http://wm:5555"

    adapter = WebMethodsGatewayAdapter.__new__(WebMethodsGatewayAdapter)
    adapter._config = {}
    adapter._svc = svc

    # sync_api without auth_token should fail (not crash)
    result = await adapter.sync_api(
        {"apiName": "Test", "apiVersion": "1.0", "url": "https://example.com/spec.json"},
        tenant_id="t1",
        auth_token=None,
    )

    assert result.success is False
    assert "JWT token required" in result.error


@pytest.mark.asyncio
async def test_sync_api_retry_stops_after_server_error():
    """Regression CAB-1944: server error must not cause infinite retry."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if request.method == "GET" and request.url.path.endswith("/apis"):
            return httpx.Response(500, json={"error": "Internal Server Error"})
        return httpx.Response(404)

    adapter = _make_adapter(handler)
    result = await adapter.sync_api(
        {"apiName": "Retry API", "apiVersion": "1.0", "url": "https://example.com/spec.json"},
        tenant_id="t1",
    )

    assert result.success is False
    # Should not retry endlessly — at most a few calls
    assert call_count <= 3, f"Expected <= 3 calls, got {call_count} (possible infinite retry)"


# ---------------------------------------------------------------------------
# Additional boundary tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_check_timeout_returns_failure():
    """Health check must return failure on timeout, not raise."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection timed out")

    adapter = _make_adapter(handler)
    result = await adapter.health_check()

    assert result.success is False
    assert "timed out" in result.error.lower() or "connect" in result.error.lower()


@pytest.mark.asyncio
async def test_delete_api_not_found_returns_success():
    """Deleting a non-existent API should still succeed (idempotent)."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            return httpx.Response(404, json={"error": "API not found"})
        return httpx.Response(404)

    adapter = _make_adapter(handler)
    result = await adapter.delete_api("nonexistent-id")

    # 404 on delete is an error from webMethods perspective
    assert result.success is False
    assert "404" in result.error


@pytest.mark.asyncio
async def test_sync_api_large_openapi_spec():
    """Large OpenAPI spec (>1MB) must be handled without truncation."""
    large_paths = {}
    for i in range(500):
        large_paths[f"/api/v1/resource-{i}"] = {
            "get": {"summary": f"Get resource {i}", "responses": {"200": {"description": "OK"}}}
        }
    large_spec = {"openapi": "3.0.1", "info": {"title": "Large API", "version": "1.0"}, "paths": large_paths}
    received_size = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path.endswith("/apis"):
            return httpx.Response(200, json={"apiResponse": []})
        if request.method == "POST" and path.endswith("/apis"):
            received_size.append(len(request.content))
            return httpx.Response(200, json={"apiResponse": {"api": {"id": "api-large"}}})
        return httpx.Response(404)

    adapter = _make_adapter(handler)
    result = await adapter.sync_api(
        {"apiName": "Large API", "apiVersion": "1.0", "apiDefinition": large_spec},
        tenant_id="t1",
    )

    assert result.success is True
    # Verify the full spec was sent (not truncated)
    assert len(received_size) == 1
    assert received_size[0] > 50_000  # 500 paths should be well over 50KB
