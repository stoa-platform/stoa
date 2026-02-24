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

from unittest.mock import AsyncMock, patch

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
