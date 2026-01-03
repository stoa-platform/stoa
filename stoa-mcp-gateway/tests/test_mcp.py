"""Tests for MCP endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

from src.main import app
from src.middleware.auth import TokenClaims


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

    def test_get_tool_not_found(self, client: TestClient):
        """Test getting non-existent tool returns 404."""
        response = client.get("/mcp/v1/tools/nonexistent-tool")
        assert response.status_code == 404

    def test_invoke_tool_requires_auth(self, client: TestClient):
        """Test tool invocation requires authentication."""
        response = client.post(
            "/mcp/v1/tools/stoa_platform_info/invoke",
            json={"name": "stoa_platform_info", "arguments": {}},
        )
        # Should return 401 Unauthorized
        assert response.status_code == 401


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
