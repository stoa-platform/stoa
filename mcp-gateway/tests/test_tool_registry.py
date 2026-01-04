"""Tests for Tool Registry service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from src.services.tool_registry import ToolRegistry, get_tool_registry, shutdown_tool_registry
from src.models import (
    Tool,
    ToolInputSchema,
    ToolInvocation,
    ToolResult,
    TextContent,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def registry() -> ToolRegistry:
    """Create a fresh tool registry instance."""
    return ToolRegistry()


@pytest.fixture
def sample_tool() -> Tool:
    """Create a sample tool for testing."""
    return Tool(
        name="test_tool",
        description="A test tool for unit tests",
        input_schema=ToolInputSchema(
            properties={
                "param1": {"type": "string", "description": "First parameter"},
                "param2": {"type": "integer", "description": "Second parameter"},
            },
            required=["param1"],
        ),
        tags=["test", "sample"],
        tenant_id="tenant-123",
    )


@pytest.fixture
def api_backed_tool() -> Tool:
    """Create an API-backed tool for testing."""
    return Tool(
        name="api_tool",
        description="A tool backed by an API",
        input_schema=ToolInputSchema(
            properties={
                "query": {"type": "string", "description": "Search query"},
            },
            required=["query"],
        ),
        endpoint="https://api.example.com/search",
        method="GET",
        tags=["api", "search"],
    )


# =============================================================================
# ToolRegistry Basic Tests
# =============================================================================


class TestToolRegistryBasic:
    """Basic tests for ToolRegistry."""

    def test_init_creates_empty_registry(self, registry: ToolRegistry):
        """Test that a new registry is empty."""
        assert len(registry._tools) == 0

    def test_register_tool(self, registry: ToolRegistry, sample_tool: Tool):
        """Test registering a tool."""
        registry.register(sample_tool)
        assert sample_tool.name in registry._tools
        assert registry.get(sample_tool.name) == sample_tool

    def test_register_overwrites_existing(self, registry: ToolRegistry):
        """Test that registering with same name overwrites."""
        tool1 = Tool(name="test", description="First version")
        tool2 = Tool(name="test", description="Second version")

        registry.register(tool1)
        registry.register(tool2)

        assert registry.get("test").description == "Second version"

    def test_unregister_tool(self, registry: ToolRegistry, sample_tool: Tool):
        """Test unregistering a tool."""
        registry.register(sample_tool)
        assert registry.unregister(sample_tool.name) is True
        assert registry.get(sample_tool.name) is None

    def test_unregister_nonexistent(self, registry: ToolRegistry):
        """Test unregistering non-existent tool returns False."""
        assert registry.unregister("nonexistent") is False

    def test_get_nonexistent(self, registry: ToolRegistry):
        """Test getting non-existent tool returns None."""
        assert registry.get("nonexistent") is None


# =============================================================================
# ToolRegistry List Tests
# =============================================================================


class TestToolRegistryList:
    """Tests for listing tools with filtering."""

    def test_list_empty_registry(self, registry: ToolRegistry):
        """Test listing from empty registry."""
        result = registry.list_tools()
        assert result.tools == []
        assert result.total_count == 0
        assert result.next_cursor is None

    def test_list_all_tools(self, registry: ToolRegistry, sample_tool: Tool):
        """Test listing all tools."""
        registry.register(sample_tool)
        result = registry.list_tools()

        assert len(result.tools) == 1
        assert result.tools[0].name == sample_tool.name
        assert result.total_count == 1

    def test_list_filter_by_tenant(self, registry: ToolRegistry):
        """Test filtering tools by tenant."""
        tool1 = Tool(name="tool1", description="Tenant A", tenant_id="tenant-a")
        tool2 = Tool(name="tool2", description="Tenant B", tenant_id="tenant-b")
        tool3 = Tool(name="tool3", description="Global", tenant_id=None)

        registry.register(tool1)
        registry.register(tool2)
        registry.register(tool3)

        # Filter by tenant-a should return tool1 and global tool3
        result = registry.list_tools(tenant_id="tenant-a")
        names = [t.name for t in result.tools]
        assert "tool1" in names
        assert "tool3" in names  # Global tools always included
        assert "tool2" not in names

    def test_list_filter_by_tag(self, registry: ToolRegistry):
        """Test filtering tools by tag."""
        tool1 = Tool(name="tool1", description="Test", tags=["api", "rest"])
        tool2 = Tool(name="tool2", description="Test", tags=["grpc"])
        tool3 = Tool(name="tool3", description="Test", tags=["api", "graphql"])

        registry.register(tool1)
        registry.register(tool2)
        registry.register(tool3)

        result = registry.list_tools(tag="api")
        names = [t.name for t in result.tools]
        assert "tool1" in names
        assert "tool3" in names
        assert "tool2" not in names

    def test_list_pagination(self, registry: ToolRegistry):
        """Test pagination."""
        for i in range(5):
            registry.register(Tool(name=f"tool{i}", description=f"Tool {i}"))

        # First page
        result1 = registry.list_tools(limit=2)
        assert len(result1.tools) == 2
        assert result1.next_cursor == "2"
        assert result1.total_count == 5

        # Second page
        result2 = registry.list_tools(cursor="2", limit=2)
        assert len(result2.tools) == 2
        assert result2.next_cursor == "4"

        # Last page
        result3 = registry.list_tools(cursor="4", limit=2)
        assert len(result3.tools) == 1
        assert result3.next_cursor is None

    def test_list_invalid_cursor(self, registry: ToolRegistry, sample_tool: Tool):
        """Test with invalid cursor defaults to start."""
        registry.register(sample_tool)
        result = registry.list_tools(cursor="invalid")
        assert len(result.tools) == 1


# =============================================================================
# ToolRegistry Startup/Shutdown Tests
# =============================================================================


class TestToolRegistryLifecycle:
    """Tests for registry lifecycle."""

    @pytest.mark.asyncio
    async def test_startup_initializes_http_client(self, registry: ToolRegistry):
        """Test startup initializes HTTP client."""
        await registry.startup()
        assert registry._http_client is not None
        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_startup_registers_builtin_tools(self, registry: ToolRegistry):
        """Test startup registers built-in tools."""
        await registry.startup()

        assert registry.get("stoa_platform_info") is not None
        assert registry.get("stoa_list_apis") is not None
        assert registry.get("stoa_get_api_details") is not None

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_closes_http_client(self, registry: ToolRegistry):
        """Test shutdown closes HTTP client."""
        await registry.startup()
        await registry.shutdown()
        # After shutdown, client should be closed
        # (we don't check internal state, just that it doesn't error)


# =============================================================================
# Tool Invocation Tests
# =============================================================================


class TestToolInvocation:
    """Tests for tool invocation."""

    @pytest.mark.asyncio
    async def test_invoke_nonexistent_tool(self, registry: ToolRegistry):
        """Test invoking non-existent tool returns error."""
        invocation = ToolInvocation(name="nonexistent", arguments={})
        result = await registry.invoke(invocation)

        assert result.is_error is True
        assert "not found" in result.content[0].text.lower()

    @pytest.mark.asyncio
    async def test_invoke_builtin_platform_info(self, registry: ToolRegistry):
        """Test invoking stoa_platform_info."""
        await registry.startup()

        invocation = ToolInvocation(
            name="stoa_platform_info",
            arguments={},
            request_id="test-123",
        )
        result = await registry.invoke(invocation)

        assert result.is_error is False
        assert "STOA" in result.content[0].text
        assert result.request_id == "test-123"
        assert result.latency_ms is not None

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_invoke_builtin_list_apis(self, registry: ToolRegistry):
        """Test invoking stoa_list_apis."""
        await registry.startup()

        invocation = ToolInvocation(
            name="stoa_list_apis",
            arguments={"tenant_id": "test-tenant"},
        )
        result = await registry.invoke(invocation)

        assert result.is_error is False
        # Currently returns placeholder
        assert "coming soon" in result.content[0].text.lower()

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_invoke_builtin_get_api_details_missing_id(self, registry: ToolRegistry):
        """Test invoking stoa_get_api_details without api_id returns error."""
        await registry.startup()

        invocation = ToolInvocation(
            name="stoa_get_api_details",
            arguments={},
        )
        result = await registry.invoke(invocation)

        assert result.is_error is True
        assert "required" in result.content[0].text.lower()

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_invoke_builtin_get_api_details_with_id(self, registry: ToolRegistry):
        """Test invoking stoa_get_api_details with api_id."""
        await registry.startup()

        invocation = ToolInvocation(
            name="stoa_get_api_details",
            arguments={"api_id": "api-123"},
        )
        result = await registry.invoke(invocation)

        assert result.is_error is False
        assert "api-123" in result.content[0].text

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_invoke_tool_without_endpoint(self, registry: ToolRegistry, sample_tool: Tool):
        """Test invoking tool without endpoint configured."""
        await registry.startup()
        registry.register(sample_tool)

        invocation = ToolInvocation(name=sample_tool.name, arguments={"param1": "test"})
        result = await registry.invoke(invocation)

        assert result.is_error is True
        assert "no backend" in result.content[0].text.lower()

        await registry.shutdown()


# =============================================================================
# API Tool Invocation Tests
# =============================================================================


class TestAPIToolInvocation:
    """Tests for API-backed tool invocation."""

    @pytest.mark.asyncio
    async def test_invoke_api_get_success(self, registry: ToolRegistry, api_backed_tool: Tool):
        """Test successful GET API invocation."""
        await registry.startup()
        registry.register(api_backed_tool)

        # Mock HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"results": ["item1", "item2"]}'

        with patch.object(registry._http_client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            invocation = ToolInvocation(
                name="api_tool",
                arguments={"query": "test"},
            )
            result = await registry.invoke(invocation)

            assert result.is_error is False
            assert result.backend_status == 200
            mock_get.assert_called_once()

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_invoke_api_post_success(self, registry: ToolRegistry):
        """Test successful POST API invocation."""
        await registry.startup()

        post_tool = Tool(
            name="post_tool",
            description="POST tool",
            endpoint="https://api.example.com/create",
            method="POST",
        )
        registry.register(post_tool)

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.text = '{"id": "new-123"}'

        with patch.object(registry._http_client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            invocation = ToolInvocation(
                name="post_tool",
                arguments={"name": "test"},
            )
            result = await registry.invoke(invocation)

            assert result.is_error is False
            assert result.backend_status == 201

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_invoke_api_error_response(self, registry: ToolRegistry, api_backed_tool: Tool):
        """Test API invocation with error response."""
        await registry.startup()
        registry.register(api_backed_tool)

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = '{"error": "Internal server error"}'

        with patch.object(registry._http_client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            invocation = ToolInvocation(name="api_tool", arguments={"query": "test"})
            result = await registry.invoke(invocation)

            assert result.is_error is True
            assert result.backend_status == 500

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_invoke_api_request_error(self, registry: ToolRegistry, api_backed_tool: Tool):
        """Test API invocation with network error."""
        await registry.startup()
        registry.register(api_backed_tool)

        with patch.object(registry._http_client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.RequestError("Connection refused")

            invocation = ToolInvocation(name="api_tool", arguments={"query": "test"})
            result = await registry.invoke(invocation)

            assert result.is_error is True
            assert "failed" in result.content[0].text.lower()

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_invoke_api_with_user_token(self, registry: ToolRegistry, api_backed_tool: Tool):
        """Test API invocation passes user token."""
        await registry.startup()
        registry.register(api_backed_tool)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "{}"

        with patch.object(registry._http_client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            invocation = ToolInvocation(name="api_tool", arguments={"query": "test"})
            await registry.invoke(invocation, user_token="test-jwt-token")

            # Verify Authorization header was set
            call_kwargs = mock_get.call_args
            headers = call_kwargs.kwargs.get("headers", {})
            assert headers.get("Authorization") == "Bearer test-jwt-token"

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_invoke_unsupported_method(self, registry: ToolRegistry):
        """Test invoking tool with unsupported HTTP method."""
        await registry.startup()

        bad_tool = Tool(
            name="bad_tool",
            description="Tool with bad method",
            endpoint="https://api.example.com/bad",
            method="OPTIONS",  # Not supported
        )
        registry.register(bad_tool)

        invocation = ToolInvocation(name="bad_tool", arguments={})
        result = await registry.invoke(invocation)

        assert result.is_error is True
        assert "unsupported" in result.content[0].text.lower()

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_invoke_api_patch_success(self, registry: ToolRegistry):
        """Test successful PATCH API invocation."""
        await registry.startup()

        patch_tool = Tool(
            name="patch_tool",
            description="PATCH tool",
            endpoint="https://api.example.com/update",
            method="PATCH",
        )
        registry.register(patch_tool)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"updated": true}'

        with patch.object(registry._http_client, "patch", new_callable=AsyncMock) as mock_patch:
            mock_patch.return_value = mock_response

            invocation = ToolInvocation(name="patch_tool", arguments={"field": "value"})
            result = await registry.invoke(invocation)

            assert result.is_error is False
            assert result.backend_status == 200
            mock_patch.assert_called_once()

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_invoke_api_put_success(self, registry: ToolRegistry):
        """Test successful PUT API invocation."""
        await registry.startup()

        put_tool = Tool(
            name="put_tool",
            description="PUT tool",
            endpoint="https://api.example.com/replace",
            method="PUT",
        )
        registry.register(put_tool)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"replaced": true}'

        with patch.object(registry._http_client, "put", new_callable=AsyncMock) as mock_put:
            mock_put.return_value = mock_response

            invocation = ToolInvocation(name="put_tool", arguments={"data": "new"})
            result = await registry.invoke(invocation)

            assert result.is_error is False
            assert result.backend_status == 200
            mock_put.assert_called_once()

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_invoke_api_delete_success(self, registry: ToolRegistry):
        """Test successful DELETE API invocation."""
        await registry.startup()

        delete_tool = Tool(
            name="delete_tool",
            description="DELETE tool",
            endpoint="https://api.example.com/item",
            method="DELETE",
        )
        registry.register(delete_tool)

        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_response.text = ''

        with patch.object(registry._http_client, "delete", new_callable=AsyncMock) as mock_delete:
            mock_delete.return_value = mock_response

            invocation = ToolInvocation(name="delete_tool", arguments={"id": "123"})
            result = await registry.invoke(invocation)

            assert result.is_error is False
            assert result.backend_status == 204
            mock_delete.assert_called_once()

        await registry.shutdown()


# =============================================================================
# Singleton Tests
# =============================================================================


class TestSingleton:
    """Tests for singleton pattern."""

    @pytest.mark.asyncio
    async def test_get_tool_registry_returns_singleton(self):
        """Test get_tool_registry returns same instance."""
        # Shutdown any existing registry first
        await shutdown_tool_registry()

        registry1 = await get_tool_registry()
        registry2 = await get_tool_registry()

        assert registry1 is registry2

        await shutdown_tool_registry()

    @pytest.mark.asyncio
    async def test_shutdown_clears_singleton(self):
        """Test shutdown clears the singleton."""
        registry1 = await get_tool_registry()
        await shutdown_tool_registry()

        # After shutdown, should create new instance
        registry2 = await get_tool_registry()
        assert registry1 is not registry2

        await shutdown_tool_registry()


# =============================================================================
# New Built-in Tools Tests
# =============================================================================


class TestNewBuiltinTools:
    """Tests for newly added built-in tools."""

    @pytest.mark.asyncio
    async def test_startup_registers_all_builtin_tools(self, registry: ToolRegistry):
        """Test startup registers all built-in tools."""
        await registry.startup()

        # Check all expected built-in tools are registered
        expected_tools = [
            "stoa_platform_info",
            "stoa_list_apis",
            "stoa_get_api_details",
            "stoa_health_check",
            "stoa_list_tools",
            "stoa_get_tool_schema",
            "stoa_search_apis",
        ]

        for tool_name in expected_tools:
            assert registry.get(tool_name) is not None, f"Tool {tool_name} not registered"

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_invoke_health_check_default(self, registry: ToolRegistry):
        """Test invoking stoa_health_check with default (all) services."""
        await registry.startup()

        # Mock HTTP client to avoid actual network calls
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch.object(registry._http_client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            invocation = ToolInvocation(
                name="stoa_health_check",
                arguments={},
            )
            result = await registry.invoke(invocation)

            assert result.is_error is False
            assert "services" in result.content[0].text
            # Should check all 3 services
            assert mock_get.call_count == 3

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_invoke_health_check_single_service(self, registry: ToolRegistry):
        """Test invoking stoa_health_check for single service."""
        await registry.startup()

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch.object(registry._http_client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            invocation = ToolInvocation(
                name="stoa_health_check",
                arguments={"service": "api"},
            )
            result = await registry.invoke(invocation)

            assert result.is_error is False
            # Should only check 1 service
            assert mock_get.call_count == 1

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_invoke_health_check_unhealthy_service(self, registry: ToolRegistry):
        """Test stoa_health_check with unhealthy service."""
        await registry.startup()

        with patch.object(registry._http_client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = Exception("Connection refused")

            invocation = ToolInvocation(
                name="stoa_health_check",
                arguments={"service": "api"},
            )
            result = await registry.invoke(invocation)

            assert result.is_error is False  # Tool still returns result
            assert "degraded" in result.content[0].text.lower() or "unhealthy" in result.content[0].text.lower()

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_invoke_list_tools(self, registry: ToolRegistry):
        """Test invoking stoa_list_tools."""
        await registry.startup()

        invocation = ToolInvocation(
            name="stoa_list_tools",
            arguments={},
        )
        result = await registry.invoke(invocation)

        assert result.is_error is False
        assert "tools" in result.content[0].text
        assert "total" in result.content[0].text

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_invoke_list_tools_with_tag_filter(self, registry: ToolRegistry):
        """Test invoking stoa_list_tools with tag filter."""
        await registry.startup()

        invocation = ToolInvocation(
            name="stoa_list_tools",
            arguments={"tag": "platform"},
        )
        result = await registry.invoke(invocation)

        assert result.is_error is False
        # All platform tools should be in the result
        assert "stoa_platform_info" in result.content[0].text

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_invoke_list_tools_with_schema(self, registry: ToolRegistry):
        """Test invoking stoa_list_tools with include_schema=True."""
        await registry.startup()

        invocation = ToolInvocation(
            name="stoa_list_tools",
            arguments={"include_schema": True},
        )
        result = await registry.invoke(invocation)

        assert result.is_error is False
        # Schema should be included
        assert "input_schema" in result.content[0].text

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_invoke_get_tool_schema_success(self, registry: ToolRegistry):
        """Test invoking stoa_get_tool_schema with valid tool."""
        await registry.startup()

        invocation = ToolInvocation(
            name="stoa_get_tool_schema",
            arguments={"tool_name": "stoa_platform_info"},
        )
        result = await registry.invoke(invocation)

        assert result.is_error is False
        assert "stoa_platform_info" in result.content[0].text
        assert "input_schema" in result.content[0].text

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_invoke_get_tool_schema_missing_name(self, registry: ToolRegistry):
        """Test invoking stoa_get_tool_schema without tool_name."""
        await registry.startup()

        invocation = ToolInvocation(
            name="stoa_get_tool_schema",
            arguments={},
        )
        result = await registry.invoke(invocation)

        assert result.is_error is True
        assert "required" in result.content[0].text.lower()

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_invoke_get_tool_schema_not_found(self, registry: ToolRegistry):
        """Test invoking stoa_get_tool_schema with non-existent tool."""
        await registry.startup()

        invocation = ToolInvocation(
            name="stoa_get_tool_schema",
            arguments={"tool_name": "nonexistent_tool"},
        )
        result = await registry.invoke(invocation)

        assert result.is_error is True
        assert "not found" in result.content[0].text.lower()

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_invoke_search_apis_success(self, registry: ToolRegistry):
        """Test invoking stoa_search_apis with query."""
        await registry.startup()

        invocation = ToolInvocation(
            name="stoa_search_apis",
            arguments={"query": "payment"},
        )
        result = await registry.invoke(invocation)

        assert result.is_error is False
        assert "payment" in result.content[0].text
        # Currently returns placeholder
        assert "coming soon" in result.content[0].text.lower()

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_invoke_search_apis_missing_query(self, registry: ToolRegistry):
        """Test invoking stoa_search_apis without query."""
        await registry.startup()

        invocation = ToolInvocation(
            name="stoa_search_apis",
            arguments={},
        )
        result = await registry.invoke(invocation)

        assert result.is_error is True
        assert "required" in result.content[0].text.lower()

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_invoke_unknown_builtin_tool(self, registry: ToolRegistry):
        """Test invoking an unknown stoa_ prefixed tool."""
        await registry.startup()

        # Manually register a fake stoa_ tool
        fake_tool = Tool(
            name="stoa_unknown_builtin",
            description="A fake builtin tool",
        )
        registry.register(fake_tool)

        invocation = ToolInvocation(
            name="stoa_unknown_builtin",
            arguments={},
        )
        result = await registry.invoke(invocation)

        assert result.is_error is True
        assert "unknown" in result.content[0].text.lower()

        await registry.shutdown()
