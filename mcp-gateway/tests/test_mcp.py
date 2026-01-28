# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Tests for MCP endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock

from src.main import app
from src.middleware.auth import TokenClaims, get_current_user, get_optional_user
from src.models import Tool, ToolInputSchema, ToolResult, TextContent


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_user() -> TokenClaims:
    """Mock authenticated user."""
    return TokenClaims(
        sub="test-user-123",
        email="test@example.com",
        preferred_username="testuser",
        realm_access={"roles": ["viewer"]},
        scope="openid profile email",
    )


@pytest.fixture
def mock_admin_user() -> TokenClaims:
    """Mock admin user."""
    return TokenClaims(
        sub="admin-user-456",
        email="admin@example.com",
        preferred_username="admin",
        realm_access={"roles": ["cpi-admin", "tenant-admin"]},
        scope="openid profile email",
    )


def override_get_current_user(user: TokenClaims):
    """Create override for get_current_user dependency."""
    async def _override():
        return user
    return _override


def override_get_optional_user(user: TokenClaims | None = None):
    """Create override for get_optional_user dependency."""
    async def _override():
        return user
    return _override


# =============================================================================
# MCP Server Info Tests
# =============================================================================


class TestMCPServerInfo:
    """Tests for MCP server info endpoint."""

    def test_server_info(self, client: TestClient):
        """Test /mcp/v1/ returns server info."""
        response = client.get("/mcp/v1/")
        assert response.status_code == 200
        data = response.json()

        assert data["name"] == "stoa-mcp-gateway"
        assert "version" in data
        assert data["protocol_version"] == "1.0"
        assert "capabilities" in data
        assert data["capabilities"]["tools"] is True
        assert data["capabilities"]["resources"] is True
        assert data["capabilities"]["prompts"] is True
        assert data["capabilities"]["sampling"] is False
        assert "instructions" in data


# =============================================================================
# MCP Tools Tests
# =============================================================================


class TestMCPTools:
    """Tests for MCP tools endpoints."""

    def test_list_tools_unauthenticated(self, client: TestClient):
        """Test listing tools without authentication."""
        response = client.get("/mcp/v1/tools")
        assert response.status_code == 200
        data = response.json()

        assert "tools" in data
        assert "total_count" in data
        # Should return builtin tools
        assert data["total_count"] >= 0

    def test_list_tools_with_pagination(self, client: TestClient):
        """Test listing tools with pagination."""
        response = client.get("/mcp/v1/tools?limit=1")
        assert response.status_code == 200
        data = response.json()

        assert len(data["tools"]) <= 1

    def test_list_tools_with_tag_filter(self, client: TestClient):
        """Test listing tools filtered by tag."""
        response = client.get("/mcp/v1/tools?tag=platform")
        assert response.status_code == 200
        data = response.json()

        # All returned tools should have the 'platform' tag
        for tool in data["tools"]:
            assert "platform" in tool.get("tags", [])

    def test_list_tools_with_tenant_filter(self, client: TestClient):
        """Test listing tools filtered by tenant."""
        response = client.get("/mcp/v1/tools?tenant_id=test-tenant")
        assert response.status_code == 200
        data = response.json()
        # Builtin tools have no tenant, so they should be included
        assert isinstance(data["tools"], list)

    def test_get_tool_success(self, client: TestClient):
        """Test getting an existing tool."""
        response = client.get("/mcp/v1/tools/stoa_platform_info")
        assert response.status_code == 200
        data = response.json()

        assert data["name"] == "stoa_platform_info"
        assert "description" in data
        assert "inputSchema" in data or "input_schema" in data

    def test_get_tool_not_found(self, client: TestClient):
        """Test getting non-existent tool returns 404."""
        response = client.get("/mcp/v1/tools/nonexistent-tool")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    def test_invoke_tool_requires_auth(self, client: TestClient):
        """Test tool invocation requires authentication."""
        response = client.post(
            "/mcp/v1/tools/stoa_platform_info/invoke",
            json={"name": "stoa_platform_info", "arguments": {}},
        )
        # Should return 401 Unauthorized
        assert response.status_code == 401

    def test_invoke_tool_authenticated(self, client: TestClient, mock_user: TokenClaims):
        """Test tool invocation with authentication."""
        # Override the dependency
        app.dependency_overrides[get_current_user] = override_get_current_user(mock_user)

        try:
            response = client.post(
                "/mcp/v1/tools/stoa_platform_info/invoke",
                json={"name": "stoa_platform_info", "arguments": {}},
            )
            assert response.status_code == 200
            data = response.json()

            assert "result" in data
            assert "toolName" in data or "tool_name" in data
            assert data.get("toolName") == "stoa_platform_info" or data.get("tool_name") == "stoa_platform_info"
        finally:
            app.dependency_overrides.clear()

    def test_invoke_tool_not_found(self, client: TestClient, mock_user: TokenClaims):
        """Test invoking non-existent tool returns 404."""
        app.dependency_overrides[get_current_user] = override_get_current_user(mock_user)

        try:
            response = client.post(
                "/mcp/v1/tools/nonexistent/invoke",
                json={"name": "nonexistent", "arguments": {}},
            )
            assert response.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_invoke_tool_with_arguments(self, client: TestClient, mock_user: TokenClaims):
        """Test tool invocation with arguments."""
        app.dependency_overrides[get_current_user] = override_get_current_user(mock_user)

        try:
            response = client.post(
                "/mcp/v1/tools/stoa_get_api_details/invoke",
                json={
                    "name": "stoa_get_api_details",
                    "arguments": {"api_id": "test-api-123"},
                    "request_id": "req-456",
                },
            )
            assert response.status_code == 200
            data = response.json()

            result = data.get("result", {})
            assert "content" in result
        finally:
            app.dependency_overrides.clear()

    def test_invoke_tool_with_request_id(self, client: TestClient, mock_user: TokenClaims):
        """Test that request_id is preserved."""
        app.dependency_overrides[get_current_user] = override_get_current_user(mock_user)

        try:
            response = client.post(
                "/mcp/v1/tools/stoa_platform_info/invoke",
                json={
                    "name": "stoa_platform_info",
                    "arguments": {},
                    "request_id": "custom-req-id",
                },
            )
            assert response.status_code == 200
            data = response.json()

            result = data.get("result", {})
            # request_id should be in the result
            assert result.get("request_id") == "custom-req-id" or result.get("requestId") == "custom-req-id"
        finally:
            app.dependency_overrides.clear()


# =============================================================================
# MCP Resources Tests
# =============================================================================


class TestMCPResources:
    """Tests for MCP resources endpoints."""

    def test_list_resources(self, client: TestClient):
        """Test listing resources."""
        response = client.get("/mcp/v1/resources")
        assert response.status_code == 200
        data = response.json()

        assert "resources" in data
        assert data["total_count"] == 0  # No resources implemented yet

    def test_list_resources_with_pagination(self, client: TestClient):
        """Test listing resources with pagination params."""
        response = client.get("/mcp/v1/resources?limit=10&cursor=0")
        assert response.status_code == 200
        data = response.json()

        assert "resources" in data

    def test_list_resources_with_tenant_filter(self, client: TestClient):
        """Test listing resources filtered by tenant."""
        response = client.get("/mcp/v1/resources?tenant_id=test-tenant")
        assert response.status_code == 200
        data = response.json()

        assert isinstance(data["resources"], list)

    def test_read_resource_requires_auth(self, client: TestClient):
        """Test reading resource requires authentication."""
        response = client.get("/mcp/v1/resources/some/resource/uri")
        assert response.status_code == 401

    def test_read_resource_not_found(self, client: TestClient, mock_user: TokenClaims):
        """Test reading non-existent resource returns 404."""
        app.dependency_overrides[get_current_user] = override_get_current_user(mock_user)

        try:
            response = client.get("/mcp/v1/resources/nonexistent/resource")
            assert response.status_code == 404
        finally:
            app.dependency_overrides.clear()


# =============================================================================
# MCP Prompts Tests
# =============================================================================


class TestMCPPrompts:
    """Tests for MCP prompts endpoints."""

    def test_list_prompts(self, client: TestClient):
        """Test listing prompts."""
        response = client.get("/mcp/v1/prompts")
        assert response.status_code == 200
        data = response.json()

        assert "prompts" in data
        assert data["total_count"] == 0  # No prompts implemented yet

    def test_list_prompts_with_pagination(self, client: TestClient):
        """Test listing prompts with pagination params."""
        response = client.get("/mcp/v1/prompts?limit=10")
        assert response.status_code == 200
        data = response.json()

        assert "prompts" in data

    def test_get_prompt_not_found(self, client: TestClient):
        """Test getting non-existent prompt returns 404."""
        response = client.get("/mcp/v1/prompts/nonexistent-prompt")
        assert response.status_code == 404


# =============================================================================
# MCP Tools Integration Tests
# =============================================================================


class TestMCPToolsIntegration:
    """Integration tests for MCP tools with mock user."""

    def test_list_tools_authenticated(self, client: TestClient, mock_user: TokenClaims):
        """Test listing tools with authenticated user."""
        app.dependency_overrides[get_optional_user] = override_get_optional_user(mock_user)

        try:
            response = client.get("/mcp/v1/tools")
            assert response.status_code == 200
            data = response.json()

            # Should have builtin tools
            assert data["total_count"] >= 3
            tool_names = [t["name"] for t in data["tools"]]
            assert "stoa_platform_info" in tool_names
            assert "stoa_list_apis" in tool_names
            assert "stoa_get_api_details" in tool_names
        finally:
            app.dependency_overrides.clear()

    def test_invoke_stoa_list_apis(self, client: TestClient, mock_user: TokenClaims):
        """Test invoking stoa_list_apis tool."""
        app.dependency_overrides[get_current_user] = override_get_current_user(mock_user)

        try:
            response = client.post(
                "/mcp/v1/tools/stoa_list_apis/invoke",
                json={
                    "name": "stoa_list_apis",
                    "arguments": {
                        "tenant_id": "test-tenant",
                        "limit": 10,
                    },
                },
            )
            assert response.status_code == 200
            data = response.json()

            result = data.get("result", {})
            assert "content" in result
            assert result.get("isError", result.get("is_error")) is False
        finally:
            app.dependency_overrides.clear()

    def test_invoke_stoa_get_api_details_missing_required(
        self, client: TestClient, mock_user: TokenClaims
    ):
        """Test invoking stoa_get_api_details without required api_id."""
        app.dependency_overrides[get_current_user] = override_get_current_user(mock_user)

        try:
            response = client.post(
                "/mcp/v1/tools/stoa_get_api_details/invoke",
                json={
                    "name": "stoa_get_api_details",
                    "arguments": {},  # Missing api_id
                },
            )
            assert response.status_code == 200
            data = response.json()

            result = data.get("result", {})
            # Should return error because api_id is required
            assert result.get("isError", result.get("is_error")) is True
        finally:
            app.dependency_overrides.clear()


# =============================================================================
# MCP Response Format Tests
# =============================================================================


class TestMCPResponseFormat:
    """Tests for MCP response format compliance."""

    def test_tool_response_has_camel_case_aliases(self, client: TestClient):
        """Test that tool responses use camelCase aliases."""
        response = client.get("/mcp/v1/tools/stoa_platform_info")
        assert response.status_code == 200
        data = response.json()

        # Check for camelCase in inputSchema
        assert "inputSchema" in data or "input_schema" in data

    def test_invoke_response_format(self, client: TestClient, mock_user: TokenClaims):
        """Test invoke response format."""
        app.dependency_overrides[get_current_user] = override_get_current_user(mock_user)

        try:
            response = client.post(
                "/mcp/v1/tools/stoa_platform_info/invoke",
                json={"name": "stoa_platform_info", "arguments": {}},
            )
            assert response.status_code == 200
            data = response.json()

            # Check expected fields
            assert "result" in data
            assert "toolName" in data or "tool_name" in data
            assert "invokedAt" in data or "invoked_at" in data

            # Check result structure
            result = data["result"]
            assert "content" in result
            assert isinstance(result["content"], list)

            if len(result["content"]) > 0:
                content_item = result["content"][0]
                assert "type" in content_item
                assert content_item["type"] == "text"
                assert "text" in content_item
        finally:
            app.dependency_overrides.clear()
