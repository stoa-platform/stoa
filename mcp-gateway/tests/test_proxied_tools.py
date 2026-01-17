"""Tests for Proxied Tools (CAB-603).

Tests ProxiedTool model and namespace format {tenant}__{api}__{operation}.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.models import (
    ProxiedTool,
    ToolType,
    ToolInputSchema,
)
from src.services.tool_registry import ToolRegistry


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_proxied_tool() -> ProxiedTool:
    """Create a sample proxied tool for testing."""
    return ProxiedTool(
        name="Get Customer",
        description="Retrieve customer information from CRM",
        tenant_id="acme",
        api_id="crm-api",
        operation="get_customer",
        endpoint="https://api.acme.com/crm/customer",
        method="GET",
        input_schema=ToolInputSchema(
            properties={
                "customer_id": {"type": "string", "description": "Customer ID"},
            },
            required=["customer_id"],
        ),
        category="CRM",
        tags=["crm", "customer"],
    )


@pytest.fixture
def proxied_tool_with_headers() -> ProxiedTool:
    """Create a proxied tool with custom headers."""
    return ProxiedTool(
        name="Create Invoice",
        description="Create a new invoice in billing system",
        tenant_id="contoso",
        api_id="billing",
        operation="create_invoice",
        endpoint="https://api.contoso.com/billing/invoices",
        method="POST",
        headers={
            "X-API-Version": "2.0",
            "X-Request-Source": "mcp-gateway",
        },
        input_schema=ToolInputSchema(
            properties={
                "amount": {"type": "number", "description": "Invoice amount"},
                "currency": {"type": "string", "description": "Currency code"},
            },
            required=["amount"],
        ),
        category="Finance",
        tags=["billing", "invoice"],
    )


# =============================================================================
# ProxiedTool Model Tests
# =============================================================================


class TestProxiedToolModel:
    """Tests for ProxiedTool model."""

    def test_proxied_tool_creation(self, sample_proxied_tool: ProxiedTool):
        """Test creating a ProxiedTool."""
        assert sample_proxied_tool.name == "Get Customer"
        assert sample_proxied_tool.tenant_id == "acme"
        assert sample_proxied_tool.api_id == "crm-api"
        assert sample_proxied_tool.operation == "get_customer"

    def test_proxied_tool_type(self, sample_proxied_tool: ProxiedTool):
        """Test that ProxiedTool returns PROXIED type."""
        assert sample_proxied_tool.tool_type == ToolType.PROXIED

    def test_namespaced_name_format(self, sample_proxied_tool: ProxiedTool):
        """Test namespaced_name follows {tenant}__{api}__{operation} format."""
        assert sample_proxied_tool.namespaced_name == "acme__crm-api__get_customer"

    def test_namespaced_name_with_different_values(self):
        """Test namespaced_name with various tenant/api/operation values."""
        tool = ProxiedTool(
            name="Test Tool",
            description="Test",
            tenant_id="my-tenant",
            api_id="my-api",
            operation="my-operation",
            endpoint="https://example.com",
        )
        assert tool.namespaced_name == "my-tenant__my-api__my-operation"

    def test_proxied_tool_with_headers(self, proxied_tool_with_headers: ProxiedTool):
        """Test ProxiedTool with custom headers."""
        assert proxied_tool_with_headers.headers == {
            "X-API-Version": "2.0",
            "X-Request-Source": "mcp-gateway",
        }

    def test_proxied_tool_default_method(self):
        """Test ProxiedTool defaults to POST method."""
        tool = ProxiedTool(
            name="Test",
            description="Test",
            tenant_id="tenant",
            api_id="api",
            operation="op",
            endpoint="https://example.com",
        )
        assert tool.method == "POST"

    def test_proxied_tool_default_headers(self):
        """Test ProxiedTool defaults to empty headers."""
        tool = ProxiedTool(
            name="Test",
            description="Test",
            tenant_id="tenant",
            api_id="api",
            operation="op",
            endpoint="https://example.com",
        )
        assert tool.headers == {}


# =============================================================================
# ProxiedTool Namespace Parsing Tests
# =============================================================================


class TestProxiedToolNamespace:
    """Tests for namespace parsing and generation."""

    def test_namespace_with_simple_names(self):
        """Test namespace with simple alphanumeric names."""
        tool = ProxiedTool(
            name="Tool",
            description="Test",
            tenant_id="acme",
            api_id="api1",
            operation="get",
            endpoint="https://example.com",
        )
        assert tool.namespaced_name == "acme__api1__get"

    def test_namespace_with_hyphens(self):
        """Test namespace with hyphenated names."""
        tool = ProxiedTool(
            name="Tool",
            description="Test",
            tenant_id="acme-corp",
            api_id="crm-api",
            operation="get-customer",
            endpoint="https://example.com",
        )
        assert tool.namespaced_name == "acme-corp__crm-api__get-customer"

    def test_namespace_with_underscores(self):
        """Test namespace with underscored names."""
        tool = ProxiedTool(
            name="Tool",
            description="Test",
            tenant_id="acme_corp",
            api_id="crm_api",
            operation="get_customer",
            endpoint="https://example.com",
        )
        assert tool.namespaced_name == "acme_corp__crm_api__get_customer"

    def test_namespace_is_unique_per_tool(self):
        """Test that different tools have different namespaces."""
        tool1 = ProxiedTool(
            name="Tool1",
            description="Test",
            tenant_id="tenant1",
            api_id="api",
            operation="op",
            endpoint="https://example.com",
        )
        tool2 = ProxiedTool(
            name="Tool2",
            description="Test",
            tenant_id="tenant2",
            api_id="api",
            operation="op",
            endpoint="https://example.com",
        )
        assert tool1.namespaced_name != tool2.namespaced_name


# =============================================================================
# ProxiedTool Registry Tests
# =============================================================================


class TestProxiedToolRegistry:
    """Tests for ProxiedTool registration in ToolRegistry."""

    @pytest.fixture
    def registry(self) -> ToolRegistry:
        """Create a fresh tool registry instance."""
        return ToolRegistry()

    def test_register_proxied_tool(
        self, registry: ToolRegistry, sample_proxied_tool: ProxiedTool
    ):
        """Test registering a ProxiedTool."""
        registry.register_proxied_tool(sample_proxied_tool)
        assert sample_proxied_tool.namespaced_name in registry._proxied_tools

    def test_unregister_proxied_tool(
        self, registry: ToolRegistry, sample_proxied_tool: ProxiedTool
    ):
        """Test unregistering a ProxiedTool."""
        registry.register_proxied_tool(sample_proxied_tool)
        result = registry.unregister_proxied_tool(sample_proxied_tool.namespaced_name)
        assert result is True
        assert sample_proxied_tool.namespaced_name not in registry._proxied_tools

    def test_unregister_nonexistent_proxied_tool(self, registry: ToolRegistry):
        """Test unregistering non-existent ProxiedTool returns False."""
        result = registry.unregister_proxied_tool("nonexistent__api__op")
        assert result is False

    def test_get_proxied_tool_by_namespace(
        self, registry: ToolRegistry, sample_proxied_tool: ProxiedTool
    ):
        """Test getting ProxiedTool by namespaced name."""
        registry.register_proxied_tool(sample_proxied_tool)
        tool = registry.get_proxied_tool("acme__crm-api__get_customer")
        assert tool is not None
        assert tool.name == sample_proxied_tool.name

    def test_get_proxied_tool_by_operation_with_tenant(
        self, registry: ToolRegistry, sample_proxied_tool: ProxiedTool
    ):
        """Test getting ProxiedTool by operation name with tenant context."""
        registry.register_proxied_tool(sample_proxied_tool)
        tool = registry.get_proxied_tool("get_customer", tenant_id="acme")
        assert tool is not None
        assert tool.tenant_id == "acme"

    def test_get_proxied_tool_not_found(self, registry: ToolRegistry):
        """Test getting non-existent ProxiedTool returns None."""
        tool = registry.get_proxied_tool("nonexistent__api__op")
        assert tool is None

    def test_smart_routing_for_proxied_tool(
        self, registry: ToolRegistry, sample_proxied_tool: ProxiedTool
    ):
        """Test smart routing via get() method for proxied tools."""
        registry.register_proxied_tool(sample_proxied_tool)
        # Get using namespaced name should route to proxied tools
        tool = registry.get("acme__crm-api__get_customer")
        assert tool is not None


# =============================================================================
# ProxiedTool Listing Tests
# =============================================================================


class TestProxiedToolListing:
    """Tests for listing ProxiedTools with filtering."""

    @pytest.fixture
    def registry_with_tools(self) -> ToolRegistry:
        """Create a registry with multiple proxied tools."""
        registry = ToolRegistry()

        # Register tools for different tenants
        registry.register_proxied_tool(ProxiedTool(
            name="Tool A",
            description="Tenant A tool",
            tenant_id="tenant-a",
            api_id="api1",
            operation="op1",
            endpoint="https://a.com",
            tags=["tag1"],
        ))
        registry.register_proxied_tool(ProxiedTool(
            name="Tool B",
            description="Tenant A tool 2",
            tenant_id="tenant-a",
            api_id="api2",
            operation="op2",
            endpoint="https://a.com",
            tags=["tag2"],
        ))
        registry.register_proxied_tool(ProxiedTool(
            name="Tool C",
            description="Tenant B tool",
            tenant_id="tenant-b",
            api_id="api1",
            operation="op1",
            endpoint="https://b.com",
            tags=["tag1"],
        ))

        return registry

    def test_list_all_proxied_tools(self, registry_with_tools: ToolRegistry):
        """Test listing all proxied tools without tenant filter."""
        result = registry_with_tools.list_tools(include_core=False, include_legacy=False)
        assert result.total_count == 3

    def test_list_proxied_tools_by_tenant(self, registry_with_tools: ToolRegistry):
        """Test listing proxied tools filtered by tenant."""
        result = registry_with_tools.list_tools(
            tenant_id="tenant-a",
            include_core=False,
            include_legacy=False,
        )
        assert result.total_count == 2
        for tool in result.tools:
            assert "tenant-a" in tool.name  # Namespaced name contains tenant

    def test_list_excludes_other_tenant_tools(self, registry_with_tools: ToolRegistry):
        """Test that listing excludes tools from other tenants."""
        result = registry_with_tools.list_tools(
            tenant_id="tenant-a",
            include_core=False,
            include_legacy=False,
        )
        for tool in result.tools:
            assert "tenant-b" not in tool.name


# =============================================================================
# ProxiedTool Invocation Tests
# =============================================================================


class TestProxiedToolInvocation:
    """Tests for ProxiedTool invocation."""

    @pytest.fixture
    def registry(self) -> ToolRegistry:
        return ToolRegistry()

    @pytest.mark.asyncio
    async def test_invoke_proxied_tool_success(
        self, registry: ToolRegistry, sample_proxied_tool: ProxiedTool
    ):
        """Test successful ProxiedTool invocation."""
        await registry.startup()
        registry.register_proxied_tool(sample_proxied_tool)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"customer_id": "123", "name": "John Doe"}'

        with patch.object(registry._http_client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            from src.models import ToolInvocation
            invocation = ToolInvocation(
                name=sample_proxied_tool.namespaced_name,
                arguments={"customer_id": "123"},
            )
            result = await registry.invoke(invocation)

            assert result.is_error is False
            assert result.backend_status == 200
            mock_get.assert_called_once()

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_invoke_proxied_tool_includes_headers(
        self, registry: ToolRegistry, proxied_tool_with_headers: ProxiedTool
    ):
        """Test that ProxiedTool invocation includes custom headers."""
        await registry.startup()
        registry.register_proxied_tool(proxied_tool_with_headers)

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.text = '{"invoice_id": "INV-001"}'

        with patch.object(registry._http_client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            from src.models import ToolInvocation
            invocation = ToolInvocation(
                name=proxied_tool_with_headers.namespaced_name,
                arguments={"amount": 100, "currency": "USD"},
            )
            await registry.invoke(invocation)

            # Verify headers were included
            call_kwargs = mock_post.call_args
            headers = call_kwargs.kwargs.get("headers", {})
            assert headers.get("X-API-Version") == "2.0"
            assert headers.get("X-STOA-Tenant-ID") == "contoso"

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_invoke_proxied_tool_error(
        self, registry: ToolRegistry, sample_proxied_tool: ProxiedTool
    ):
        """Test ProxiedTool invocation with backend error."""
        await registry.startup()
        registry.register_proxied_tool(sample_proxied_tool)

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = '{"error": "Internal server error"}'

        with patch.object(registry._http_client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            from src.models import ToolInvocation
            invocation = ToolInvocation(
                name=sample_proxied_tool.namespaced_name,
                arguments={"customer_id": "123"},
            )
            result = await registry.invoke(invocation)

            assert result.is_error is True
            assert result.backend_status == 500

        await registry.shutdown()


# =============================================================================
# Tenant Isolation Tests
# =============================================================================


class TestProxiedToolTenantIsolation:
    """Tests for tenant isolation with ProxiedTools."""

    @pytest.fixture
    def registry_multi_tenant(self) -> ToolRegistry:
        """Create a registry with tools from multiple tenants."""
        registry = ToolRegistry()

        registry.register_proxied_tool(ProxiedTool(
            name="Tenant A Tool",
            description="Belongs to tenant A",
            tenant_id="tenant-a",
            api_id="api",
            operation="get",
            endpoint="https://a.com",
        ))
        registry.register_proxied_tool(ProxiedTool(
            name="Tenant B Tool",
            description="Belongs to tenant B",
            tenant_id="tenant-b",
            api_id="api",
            operation="get",
            endpoint="https://b.com",
        ))

        return registry

    def test_tenant_cannot_see_other_tenant_tools(
        self, registry_multi_tenant: ToolRegistry
    ):
        """Test that tenant A cannot see tenant B's tools."""
        result = registry_multi_tenant.list_tools(
            tenant_id="tenant-a",
            include_core=False,
            include_legacy=False,
        )

        # Should only see tenant-a's tools
        assert result.total_count == 1
        assert "tenant-a" in result.tools[0].name

    def test_get_proxied_tool_respects_tenant(
        self, registry_multi_tenant: ToolRegistry
    ):
        """Test that getting tool by operation respects tenant context."""
        # Get "get" operation for tenant-a
        tool = registry_multi_tenant.get_proxied_tool("get", tenant_id="tenant-a")
        assert tool is not None
        assert tool.tenant_id == "tenant-a"

    def test_namespaced_lookup_works_cross_tenant(
        self, registry_multi_tenant: ToolRegistry
    ):
        """Test that fully namespaced lookup works regardless of context."""
        # Can look up tenant-b tool by full namespace even if context is tenant-a
        tool = registry_multi_tenant.get("tenant-b__api__get")
        assert tool is not None
