"""Tests for MCP Tools Proxy Router — CAB-1378

Endpoints:
- GET /v1/mcp/tools (list tools)
- GET /v1/mcp/tools/tags
- GET /v1/mcp/tools/categories
- GET /v1/mcp/tools/{name}
- GET /v1/mcp/tools/{name}/schema
- POST /v1/mcp/tools/{name}/invoke

Auth: get_current_user + HTTPBearer (all endpoints).
Delegates to proxy_to_mcp which proxies to MCP Gateway.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient


class TestMCPProxyRouter:
    """Test suite for MCP Tools Proxy endpoints."""

    # ============== GET / (list tools) ==============

    def test_list_tools_success(self, client_as_tenant_admin: TestClient):
        """GET / returns tool list from MCP Gateway."""
        mock_response = {
            "tools": [
                {"name": "Linear:create_issue", "description": "Create issue", "tags": ["pm"]},
            ],
            "cursor": None,
            "totalCount": 1,
        }

        with patch("src.routers.mcp_proxy.proxy_to_mcp", new_callable=AsyncMock) as mock_proxy:
            mock_proxy.return_value = mock_response

            response = client_as_tenant_admin.get(
                "/v1/mcp/tools",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["totalCount"] == 1
        assert len(data["tools"]) == 1
        assert data["tools"][0]["name"] == "Linear:create_issue"

    def test_list_tools_with_filters(self, client_as_tenant_admin: TestClient):
        """GET /?tag=x&search=y passes query params to proxy."""
        with patch("src.routers.mcp_proxy.proxy_to_mcp", new_callable=AsyncMock) as mock_proxy:
            mock_proxy.return_value = {"tools": [], "cursor": None, "totalCount": 0}

            client_as_tenant_admin.get(
                "/v1/mcp/tools?tag=finance&search=payment&limit=10",
                headers={"Authorization": "Bearer test-token"},
            )

        call_args = mock_proxy.call_args
        params = call_args[1]["params"]
        assert params["tag"] == "finance"
        assert params["search"] == "payment"
        assert params["limit"] == 10

    # ============== GET /tags ==============

    def test_get_tool_tags_success(self, client_as_tenant_admin: TestClient):
        """GET /tags returns tag list from MCP Gateway."""
        mock_response = {"tags": ["finance", "crm", "devops"], "tagCounts": {"finance": 3}}

        with patch("src.routers.mcp_proxy.proxy_to_mcp", new_callable=AsyncMock) as mock_proxy:
            mock_proxy.return_value = mock_response

            response = client_as_tenant_admin.get(
                "/v1/mcp/tools/tags",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "finance" in data["tags"]

    # ============== GET /categories ==============

    def test_get_tool_categories_success(self, client_as_tenant_admin: TestClient):
        """GET /categories returns category list from MCP Gateway."""
        mock_response = {"categories": [{"name": "API Management", "count": 5}]}

        with patch("src.routers.mcp_proxy.proxy_to_mcp", new_callable=AsyncMock) as mock_proxy:
            mock_proxy.return_value = mock_response

            response = client_as_tenant_admin.get(
                "/v1/mcp/tools/categories",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["categories"]) == 1

    # ============== GET /{tool_name} ==============

    def test_get_tool_success(self, client_as_tenant_admin: TestClient):
        """GET /{name} returns tool details."""
        mock_response = {
            "name": "Linear:create_issue",
            "description": "Create a Linear issue",
            "inputSchema": {"type": "object"},
            "tags": ["pm"],
        }

        with patch("src.routers.mcp_proxy.proxy_to_mcp", new_callable=AsyncMock) as mock_proxy:
            mock_proxy.return_value = mock_response

            response = client_as_tenant_admin.get(
                "/v1/mcp/tools/Linear:create_issue",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        assert response.json()["name"] == "Linear:create_issue"

    # ============== GET /{tool_name}/schema ==============

    def test_get_tool_schema_success(self, client_as_tenant_admin: TestClient):
        """GET /{name}/schema returns tool input schema."""
        mock_response = {"type": "object", "properties": {"title": {"type": "string"}}}

        with patch("src.routers.mcp_proxy.proxy_to_mcp", new_callable=AsyncMock) as mock_proxy:
            mock_proxy.return_value = mock_response

            response = client_as_tenant_admin.get(
                "/v1/mcp/tools/Linear:create_issue/schema",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200

    # ============== POST /{tool_name}/invoke ==============

    def test_invoke_tool_success(self, client_as_tenant_admin: TestClient):
        """POST /{name}/invoke invokes tool via MCP Gateway."""
        mock_response = {
            "content": [{"type": "text", "text": "Issue created"}],
            "isError": False,
        }

        with patch("src.routers.mcp_proxy.proxy_to_mcp", new_callable=AsyncMock) as mock_proxy:
            mock_proxy.return_value = mock_response

            response = client_as_tenant_admin.post(
                "/v1/mcp/tools/Linear:create_issue/invoke",
                json={"arguments": {"title": "Test issue"}},
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["isError"] is False
        mock_proxy.assert_awaited_once()

    # ============== MCP Gateway error ==============

    def test_mcp_gateway_unavailable_503(self, client_as_tenant_admin: TestClient):
        """Proxy returns 503 when MCP Gateway is unreachable."""
        from fastapi import HTTPException

        with patch("src.routers.mcp_proxy.proxy_to_mcp", new_callable=AsyncMock) as mock_proxy:
            mock_proxy.side_effect = HTTPException(status_code=503, detail="MCP Gateway unavailable")

            response = client_as_tenant_admin.get(
                "/v1/mcp/tools",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 503

    # ============== Token forwarding ==============

    def test_forwards_bearer_token(self, client_as_tenant_admin: TestClient):
        """Proxy forwards the Bearer token to MCP Gateway.

        The HTTPBearer dep is overridden in client_as_tenant_admin to return
        credentials="mock-token". We verify the router forwards whatever token
        it received from the security dependency.
        """
        with patch("src.routers.mcp_proxy.proxy_to_mcp", new_callable=AsyncMock) as mock_proxy:
            mock_proxy.return_value = {"tools": [], "cursor": None, "totalCount": 0}

            client_as_tenant_admin.get(
                "/v1/mcp/tools",
                headers={"Authorization": "Bearer mock-token"},
            )

        call_args = mock_proxy.call_args
        assert call_args[0][3] == "mock-token"

    # ============== Auth ==============

    def test_endpoints_require_auth(self, app):
        """MCP proxy endpoints require authentication."""
        with TestClient(app, raise_server_exceptions=False) as client:
            tools_resp = client.get("/v1/mcp/tools")
            tags_resp = client.get("/v1/mcp/tools/tags")
            invoke_resp = client.post(
                "/v1/mcp/tools/test/invoke",
                json={"arguments": {}},
            )

        assert tools_resp.status_code in (401, 403)
        assert tags_resp.status_code in (401, 403)
        assert invoke_resp.status_code in (401, 403)


# ============== proxy_to_mcp function unit tests ==============


class TestProxyToMCP:
    """Direct unit tests for the proxy_to_mcp function."""

    @pytest.mark.asyncio
    async def test_proxy_get_request(self):
        """proxy_to_mcp sends GET requests correctly."""
        from src.routers.mcp_proxy import proxy_to_mcp

        mock_user = MagicMock()
        mock_user.id = "user-1"
        mock_user.email = "user@test.com"
        mock_user.roles = ["viewer"]
        mock_user.tenant_id = "acme"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"tools": []}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("src.routers.mcp_proxy.get_http_client", return_value=mock_client):
            result = await proxy_to_mcp("GET", "/mcp/v1/tools", mock_user, "test-token", params={"limit": 10})

        assert result == {"tools": []}
        mock_client.get.assert_awaited_once()
        call_kwargs = mock_client.get.call_args
        assert call_kwargs[1]["params"] == {"limit": 10}
        assert "Bearer test-token" in call_kwargs[1]["headers"]["Authorization"]

    @pytest.mark.asyncio
    async def test_proxy_post_request(self):
        """proxy_to_mcp sends POST requests with JSON body."""
        from src.routers.mcp_proxy import proxy_to_mcp

        mock_user = MagicMock()
        mock_user.id = "user-1"
        mock_user.email = "user@test.com"
        mock_user.roles = ["cpi-admin"]
        mock_user.tenant_id = "acme"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"content": [], "isError": False}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("src.routers.mcp_proxy.get_http_client", return_value=mock_client):
            result = await proxy_to_mcp(
                "POST", "/mcp/v1/tools/test/invoke", mock_user, "tok", json_body={"name": "test"}
            )

        assert result == {"content": [], "isError": False}
        mock_client.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_proxy_unsupported_method_405(self):
        """proxy_to_mcp raises 405 for unsupported HTTP methods."""
        from fastapi import HTTPException

        from src.routers.mcp_proxy import proxy_to_mcp

        mock_user = MagicMock()
        mock_user.id = "u"
        mock_user.email = "u@t.com"
        mock_user.roles = []
        mock_user.tenant_id = None

        mock_client = AsyncMock()

        with (
            patch("src.routers.mcp_proxy.get_http_client", return_value=mock_client),
            pytest.raises(HTTPException) as exc_info,
        ):
            await proxy_to_mcp("DELETE", "/path", mock_user, "tok")

        assert exc_info.value.status_code == 405

    @pytest.mark.asyncio
    async def test_proxy_gateway_error_passthrough(self):
        """proxy_to_mcp passes through error status from MCP Gateway."""
        from fastapi import HTTPException

        from src.routers.mcp_proxy import proxy_to_mcp

        mock_user = MagicMock()
        mock_user.id = "u"
        mock_user.email = "u@t.com"
        mock_user.roles = []
        mock_user.tenant_id = None

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"detail": "Tool not found"}
        mock_response.text = "Tool not found"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with (
            patch("src.routers.mcp_proxy.get_http_client", return_value=mock_client),
            pytest.raises(HTTPException) as exc_info,
        ):
            await proxy_to_mcp("GET", "/mcp/v1/tools/missing", mock_user, "tok")

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_proxy_gateway_error_json_parse_failure(self):
        """proxy_to_mcp falls back to response.text when JSON parsing fails."""
        from fastapi import HTTPException

        from src.routers.mcp_proxy import proxy_to_mcp

        mock_user = MagicMock()
        mock_user.id = "u"
        mock_user.email = "u@t.com"
        mock_user.roles = []
        mock_user.tenant_id = None

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.side_effect = ValueError("not json")
        mock_response.text = "Internal Server Error"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with (
            patch("src.routers.mcp_proxy.get_http_client", return_value=mock_client),
            pytest.raises(HTTPException) as exc_info,
        ):
            await proxy_to_mcp("GET", "/path", mock_user, "tok")

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Internal Server Error"

    @pytest.mark.asyncio
    async def test_proxy_httpx_error_returns_503(self):
        """proxy_to_mcp returns 503 when httpx raises HTTPError."""
        from fastapi import HTTPException

        from src.routers.mcp_proxy import proxy_to_mcp

        mock_user = MagicMock()
        mock_user.id = "u"
        mock_user.email = "u@t.com"
        mock_user.roles = []
        mock_user.tenant_id = None

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

        with (
            patch("src.routers.mcp_proxy.get_http_client", return_value=mock_client),
            pytest.raises(HTTPException) as exc_info,
        ):
            await proxy_to_mcp("GET", "/path", mock_user, "tok")

        assert exc_info.value.status_code == 503
        assert "MCP Gateway unavailable" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_proxy_forwards_user_context_headers(self):
        """proxy_to_mcp includes user context in request headers."""
        from src.routers.mcp_proxy import proxy_to_mcp

        mock_user = MagicMock()
        mock_user.id = "user-42"
        mock_user.email = "dev@gostoa.dev"
        mock_user.roles = ["cpi-admin", "tenant-admin"]
        mock_user.tenant_id = "acme"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("src.routers.mcp_proxy.get_http_client", return_value=mock_client):
            await proxy_to_mcp("GET", "/path", mock_user, "my-token")

        headers = mock_client.get.call_args[1]["headers"]
        assert headers["X-User-Id"] == "user-42"
        assert headers["X-User-Email"] == "dev@gostoa.dev"
        assert headers["X-User-Roles"] == "cpi-admin,tenant-admin"
        assert headers["X-Tenant-Id"] == "acme"


# ============== get_http_client tests ==============


class TestGetHTTPClient:
    """Tests for the HTTP client singleton."""

    @pytest.mark.asyncio
    async def test_get_http_client_creates_client(self):
        """get_http_client creates a new client when none exists."""
        import src.routers.mcp_proxy as mod

        old_client = mod._http_client
        mod._http_client = None
        try:
            client = await mod.get_http_client()
            assert client is not None
            assert isinstance(client, httpx.AsyncClient)
        finally:
            if mod._http_client and not mod._http_client.is_closed:
                await mod._http_client.aclose()
            mod._http_client = old_client

    @pytest.mark.asyncio
    async def test_get_http_client_reuses_existing(self):
        """get_http_client reuses existing open client."""
        import src.routers.mcp_proxy as mod

        old_client = mod._http_client
        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        mod._http_client = mock_client
        try:
            client = await mod.get_http_client()
            assert client is mock_client
        finally:
            mod._http_client = old_client

    @pytest.mark.asyncio
    async def test_get_http_client_recreates_if_closed(self):
        """get_http_client creates new client when existing one is closed."""
        import src.routers.mcp_proxy as mod

        old_client = mod._http_client
        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_client.is_closed = True
        mod._http_client = mock_client
        try:
            client = await mod.get_http_client()
            assert client is not mock_client
            assert isinstance(client, httpx.AsyncClient)
        finally:
            if mod._http_client and not mod._http_client.is_closed:
                await mod._http_client.aclose()
            mod._http_client = old_client
