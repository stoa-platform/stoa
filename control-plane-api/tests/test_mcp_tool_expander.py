"""Tests for MCP tool expander (CAB-2113 Phase 0).

The expander turns a catalog API (with optional OpenAPI spec) into a list of
MCP tool descriptors. Two modes:
- Per-operation: iterate OpenAPI paths, emit one tool per operation.
- Coarse fallback (no openapi_spec): emit one tool with the legacy
  ``{action, params}`` schema so the expanded endpoint stays a drop-in
  replacement for ``/v1/internal/catalog/apis`` when a spec isn't available.

Router integration test lives below and exercises
``GET /v1/internal/catalog/apis/expanded`` end-to-end through a TestClient
with the CatalogRepository boundary mocked.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.mcp_tool_expander import ExpandedTool, expand_api

BANKING_OPENAPI: dict[str, Any] = {
    "openapi": "3.0.3",
    "info": {"title": "Banking", "version": "1.0.0"},
    "paths": {
        "/customers": {
            "get": {
                "operationId": "listCustomers",
                "summary": "List all customers",
                "responses": {"200": {"description": "ok"}},
            },
            "post": {
                "operationId": "createCustomer",
                "summary": "Create a customer",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {"name": {"type": "string"}},
                                "required": ["name"],
                            }
                        }
                    },
                },
                "responses": {"201": {"description": "created"}},
            },
        },
        "/customers/{number}": {
            "get": {
                "operationId": "getCustomerByNumber",
                "summary": "Get a customer by number",
                "parameters": [
                    {"name": "number", "in": "path", "required": True, "schema": {"type": "string"}},
                ],
                "responses": {"200": {"description": "ok"}},
            },
        },
    },
}


class TestExpandApiPerOperation:
    """Per-operation expansion when openapi_spec is present."""

    def test_emits_one_tool_per_operation(self) -> None:
        tools = expand_api(
            api_id="banking",
            tenant_id="oasis",
            api_name="Banking API",
            backend_url="http://banking.svc:8080",
            openapi_spec=BANKING_OPENAPI,
        )
        assert len(tools) == 3
        names = {t.name for t in tools}
        assert "oasis:banking:listcustomers" in names
        assert "oasis:banking:createcustomer" in names
        assert "oasis:banking:getcustomerbynumber" in names

    def test_tool_carries_http_method(self) -> None:
        tools = {t.name: t for t in expand_api("banking", "oasis", "Banking", "http://b", BANKING_OPENAPI)}
        assert tools["oasis:banking:listcustomers"].http_method == "GET"
        assert tools["oasis:banking:createcustomer"].http_method == "POST"

    def test_path_pattern_surfaces_params(self) -> None:
        tools = {t.name: t for t in expand_api("banking", "oasis", "Banking", "http://b", BANKING_OPENAPI)}
        by_number = tools["oasis:banking:getcustomerbynumber"]
        assert by_number.path_pattern == "/customers/{number}"
        assert by_number.input_schema is not None
        assert "number" in (by_number.input_schema.get("properties") or {})

    def test_tenant_id_propagated(self) -> None:
        tools = expand_api("banking", "oasis", "Banking", "http://b", BANKING_OPENAPI)
        assert all(t.tenant_id == "oasis" for t in tools)

    def test_backend_url_in_every_tool(self) -> None:
        tools = expand_api("banking", "oasis", "Banking", "http://banking.svc:8080", BANKING_OPENAPI)
        # Backend URL is the API-level base; path info travels via path_pattern.
        assert all(t.backend_url == "http://banking.svc:8080" for t in tools)

    def test_scales_to_fifty_operations(self) -> None:
        """CAB-2113 challenger callout: sanity-check on a ≥50-op spec."""
        paths: dict[str, Any] = {}
        for i in range(50):
            paths[f"/op{i}"] = {
                "get": {
                    "operationId": f"op{i}",
                    "summary": f"Operation {i}",
                    "responses": {"200": {"description": "ok"}},
                }
            }
        spec = {"openapi": "3.0.3", "info": {"title": "Large", "version": "1"}, "paths": paths}

        tools = expand_api("large", "oasis", "Large", "http://x", spec)

        assert len(tools) == 50
        assert len({t.name for t in tools}) == 50, "tool names must be unique"

    def test_empty_paths_yields_empty_list(self) -> None:
        spec = {"openapi": "3.0.3", "info": {"title": "Empty", "version": "1"}, "paths": {}}
        assert expand_api("empty", "oasis", "Empty", "http://x", spec) == []


class TestExpandApiCoarseFallback:
    """Fallback when openapi_spec is missing — mirrors today's gateway coarse tool."""

    def test_emits_single_coarse_tool_when_spec_is_none(self) -> None:
        tools = expand_api(
            api_id="petstore",
            tenant_id="oasis",
            api_name="Petstore",
            backend_url="http://petstore.svc:80",
            openapi_spec=None,
        )
        assert len(tools) == 1

    def test_coarse_tool_has_legacy_action_params_schema(self) -> None:
        """Ship-safe fallback must preserve the today's gateway input shape so
        MCP clients seeing a mix of coarse + expanded tools don't observe a
        regression on APIs that lack a spec."""
        (coarse,) = expand_api("petstore", "oasis", "Petstore", "http://x", None)
        assert coarse.input_schema is not None
        props = coarse.input_schema.get("properties") or {}
        assert "action" in props
        assert "params" in props

    def test_coarse_tool_name_is_plain_api_id(self) -> None:
        """Matches api_bridge.rs today — tool name == api slug."""
        (coarse,) = expand_api("petstore", "oasis", "Petstore", "http://x", None)
        assert coarse.name == "petstore"


class TestInternalCatalogExpandedRouter:
    """Router smoke test for GET /v1/internal/catalog/apis/expanded."""

    @pytest.fixture
    def mock_repo(self):
        """Mock CatalogRepository but keep the expander real — boundary integrity."""
        with patch("src.routers.portal.CatalogRepository") as cls:
            repo = MagicMock()
            repo.get_portal_apis = AsyncMock(return_value=([], 0))
            cls.return_value = repo
            yield repo

    def test_empty_catalog_returns_empty_tool_list(self, client, mock_repo) -> None:
        resp = client.get("/v1/internal/catalog/apis/expanded")
        assert resp.status_code == 200
        assert resp.json() == {"tools": []}

    def test_catalog_with_spec_expands_to_per_operation_tools(self, client, mock_repo) -> None:
        api = MagicMock()
        api.api_id = "banking"
        api.api_name = "Banking API"
        api.tenant_id = "oasis"
        api.version = "1.0.0"
        api.api_metadata = {"backend_url": "http://banking.svc:8080"}
        api.openapi_spec = BANKING_OPENAPI
        mock_repo.get_portal_apis = AsyncMock(return_value=([api], 1))

        resp = client.get("/v1/internal/catalog/apis/expanded")

        assert resp.status_code == 200
        names = [t["name"] for t in resp.json()["tools"]]
        assert "oasis:banking:listcustomers" in names
        assert "oasis:banking:createcustomer" in names
        assert "oasis:banking:getcustomerbynumber" in names

    def test_catalog_without_spec_falls_back_to_coarse_tool(self, client, mock_repo) -> None:
        api = MagicMock()
        api.api_id = "petstore"
        api.api_name = "Petstore"
        api.tenant_id = "oasis"
        api.version = "1.0.0"
        api.api_metadata = {"backend_url": "http://petstore.svc:80"}
        api.openapi_spec = None
        mock_repo.get_portal_apis = AsyncMock(return_value=([api], 1))

        resp = client.get("/v1/internal/catalog/apis/expanded")

        assert resp.status_code == 200
        tools = resp.json()["tools"]
        assert len(tools) == 1
        assert tools[0]["name"] == "petstore"

    def test_gateway_id_filter_passed_through(self, client, mock_repo) -> None:
        import uuid as _uuid

        gw = _uuid.uuid4()
        client.get(f"/v1/internal/catalog/apis/expanded?gateway_id={gw}")
        kwargs = mock_repo.get_portal_apis.await_args.kwargs
        assert kwargs.get("gateway_id") == gw


def test_expanded_tool_is_immutable() -> None:
    """Regression guard against mutable tool defs leaking state across refreshes."""
    t = ExpandedTool(
        name="x",
        description="y",
        input_schema=None,
        backend_url="http://z",
        http_method="GET",
        tenant_id="oasis",
    )
    with pytest.raises(FrozenInstanceError):
        t.name = "other"  # type: ignore[misc]
