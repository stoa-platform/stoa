"""Tests for MCP Policy Proxy Router — CAB-1378

Endpoints:
- POST /v1/mcp/policies/check
- GET /v1/mcp/policies/rules

Auth: get_current_user + HTTPBearer
Delegates to proxy_to_mcp from mcp_proxy module.
"""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


class TestMCPPolicyProxyRouter:
    """Test suite for MCP Policy Proxy endpoints."""

    # ============== POST /check ==============

    def test_check_policies_success(self, client_as_tenant_admin: TestClient):
        """POST /check proxies to MCP Gateway and returns result."""
        mock_response = {
            "allowed": True,
            "policy_name": "default-allow",
            "rule_index": 0,
            "message": "Allowed by default policy",
            "action": "allow",
        }

        with patch("src.routers.mcp_policy_proxy.proxy_to_mcp", new_callable=AsyncMock) as mock_proxy:
            mock_proxy.return_value = mock_response

            response = client_as_tenant_admin.post(
                "/v1/mcp/policies/check",
                json={
                    "tool_name": "Linear:create_issue",
                    "arguments": {"title": "Test issue"},
                },
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["allowed"] is True
        assert data["policy_name"] == "default-allow"
        mock_proxy.assert_awaited_once()

    def test_check_policies_denied(self, client_as_tenant_admin: TestClient):
        """POST /check returns denied result from MCP Gateway."""
        mock_response = {
            "allowed": False,
            "policy_name": "sensitive-tools",
            "rule_index": 1,
            "message": "Tool blocked by admin policy",
            "action": "deny",
        }

        with patch("src.routers.mcp_policy_proxy.proxy_to_mcp", new_callable=AsyncMock) as mock_proxy:
            mock_proxy.return_value = mock_response

            response = client_as_tenant_admin.post(
                "/v1/mcp/policies/check",
                json={
                    "tool_name": "Dangerous:delete_all",
                    "arguments": {},
                },
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["allowed"] is False
        assert data["action"] == "deny"

    def test_check_policies_forwards_token(self, client_as_tenant_admin: TestClient):
        """POST /check forwards Bearer token to MCP Gateway proxy.

        The HTTPBearer dep is overridden in client_as_tenant_admin to return
        credentials="mock-token". We verify the router forwards whatever token
        it received from the security dependency.
        """
        with patch("src.routers.mcp_policy_proxy.proxy_to_mcp", new_callable=AsyncMock) as mock_proxy:
            mock_proxy.return_value = {"allowed": True}

            client_as_tenant_admin.post(
                "/v1/mcp/policies/check",
                json={"tool_name": "test:tool", "arguments": {}},
                headers={"Authorization": "Bearer mock-token"},
            )

        # Verify token was forwarded (4th positional arg)
        call_args = mock_proxy.call_args
        assert call_args[0][3] == "mock-token"

    # ============== GET /rules ==============

    def test_list_policy_rules_success(self, client_as_tenant_admin: TestClient):
        """GET /rules returns active policy rules from MCP Gateway."""
        mock_response = {
            "rules": [
                {
                    "name": "rate-limit-policy",
                    "description": "Rate limit tool calls",
                    "tool": "*",
                    "enabled": True,
                    "priority": 1,
                    "rules_count": 3,
                },
            ],
            "total_count": 1,
            "engine_enabled": True,
        }

        with patch("src.routers.mcp_policy_proxy.proxy_to_mcp", new_callable=AsyncMock) as mock_proxy:
            mock_proxy.return_value = mock_response

            response = client_as_tenant_admin.get(
                "/v1/mcp/policies/rules",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["engine_enabled"] is True
        assert len(data["rules"]) == 1
        assert data["rules"][0]["name"] == "rate-limit-policy"

    def test_policy_endpoints_require_auth(self, app):
        """Policy endpoints require authentication (no override = 401/403)."""
        with TestClient(app, raise_server_exceptions=False) as client:
            check_resp = client.post(
                "/v1/mcp/policies/check",
                json={"tool_name": "test", "arguments": {}},
            )
            rules_resp = client.get("/v1/mcp/policies/rules")

        # Without auth, should fail
        assert check_resp.status_code in (401, 403)
        assert rules_resp.status_code in (401, 403)
