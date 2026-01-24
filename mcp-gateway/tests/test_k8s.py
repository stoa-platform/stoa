"""Tests for Kubernetes integration module."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.k8s.models import (
    ToolCR,
    ToolCRMetadata,
    ToolCRSpec,
    ToolCRStatus,
    ToolSetCR,
    ToolSetCRMetadata,
    ToolSetCRSpec,
    ToolSetSelectorSpec,
    OpenAPISpecSource,
)
from src.k8s.watcher import (
    ToolWatcher,
    get_tool_watcher,
    shutdown_tool_watcher,
)


# =============================================================================
# ToolCR Model Tests
# =============================================================================


class TestToolCRModels:
    """Tests for Tool custom resource models."""

    def test_tool_cr_spec_minimal(self):
        """Test creating ToolCRSpec with minimal fields."""
        spec = ToolCRSpec(
            displayName="Test Tool",
            description="A test tool for testing",
        )

        assert spec.displayName == "Test Tool"
        assert spec.description == "A test tool for testing"
        assert spec.method == "POST"
        assert spec.enabled is True
        assert spec.version == "1.0.0"

    def test_tool_cr_spec_full(self):
        """Test creating ToolCRSpec with all fields."""
        spec = ToolCRSpec(
            displayName="Payment Search",
            description="Search payment records",
            endpoint="https://api.example.com/payments/search",
            method="GET",
            inputSchema={
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
            tags=["payments", "search"],
            version="2.0.0",
            timeout="60s",
            enabled=True,
        )

        assert spec.endpoint == "https://api.example.com/payments/search"
        assert spec.method == "GET"
        assert "payments" in spec.tags
        assert spec.timeout == "60s"

    def test_tool_cr_metadata(self):
        """Test ToolCRMetadata model."""
        metadata = ToolCRMetadata(
            name="payment-search",
            namespace="tenant-acme",
            uid="abc-123",
            resourceVersion="12345",
            labels={"app": "test"},
            annotations={"description": "test tool"},
        )

        assert metadata.name == "payment-search"
        assert metadata.namespace == "tenant-acme"
        assert metadata.labels["app"] == "test"

    def test_tool_cr_status(self):
        """Test ToolCRStatus model."""
        status = ToolCRStatus(
            phase="Registered",
            invocationCount=100,
            errorCount=5,
        )

        assert status.phase == "Registered"
        assert status.invocationCount == 100

    def test_tool_cr_complete(self):
        """Test complete ToolCR model."""
        tool_cr = ToolCR(
            metadata=ToolCRMetadata(
                name="test-tool",
                namespace="default",
            ),
            spec=ToolCRSpec(
                displayName="Test Tool",
                description="A test tool",
            ),
        )

        assert tool_cr.kind == "Tool"
        assert tool_cr.apiVersion == "gostoa.dev/v1alpha1"
        assert tool_cr.metadata.name == "test-tool"


class TestToolSetCRModels:
    """Tests for ToolSet custom resource models."""

    def test_toolset_cr_spec_minimal(self):
        """Test creating ToolSetCRSpec with minimal fields."""
        spec = ToolSetCRSpec(displayName="API Tools")

        assert spec.displayName == "API Tools"
        assert spec.enabled is True

    def test_toolset_cr_spec_with_openapi(self):
        """Test creating ToolSetCRSpec with OpenAPI source."""
        spec = ToolSetCRSpec(
            displayName="Petstore API",
            openAPISpec=OpenAPISpecSource(
                url="https://petstore.swagger.io/v2/swagger.json",
                refreshInterval="1h",
            ),
            selector=ToolSetSelectorSpec(
                tags=["pet"],
                methods=["GET", "POST"],
            ),
        )

        assert spec.openAPISpec.url == "https://petstore.swagger.io/v2/swagger.json"
        assert spec.selector.tags == ["pet"]

    def test_toolset_cr_complete(self):
        """Test complete ToolSetCR model."""
        toolset_cr = ToolSetCR(
            metadata=ToolSetCRMetadata(
                name="petstore-tools",
                namespace="tenant-acme",
            ),
            spec=ToolSetCRSpec(
                displayName="Petstore API Tools",
            ),
        )

        assert toolset_cr.kind == "ToolSet"
        assert toolset_cr.metadata.name == "petstore-tools"


# =============================================================================
# ToolWatcher Tests
# =============================================================================


class TestToolWatcher:
    """Tests for ToolWatcher."""

    def test_watcher_init(self):
        """Test watcher initialization."""
        watcher = ToolWatcher(
            namespace="test-ns",
            enabled=True,
        )

        assert watcher.namespace == "test-ns"
        assert watcher.enabled is True
        assert watcher._running is False

    def test_watcher_disabled(self):
        """Test watcher when disabled."""
        watcher = ToolWatcher(enabled=False)
        assert watcher.enabled is False

    @pytest.mark.asyncio
    async def test_watcher_startup_disabled(self):
        """Test startup does nothing when disabled."""
        watcher = ToolWatcher(enabled=False)
        await watcher.startup()
        assert watcher._api_client is None

    @pytest.mark.asyncio
    async def test_watcher_startup_no_k8s(self):
        """Test startup when kubernetes-asyncio not installed."""
        watcher = ToolWatcher(enabled=True)

        # Patch import to fail
        with patch.dict("sys.modules", {"kubernetes_asyncio": None}):
            with patch("builtins.__import__", side_effect=ImportError):
                await watcher.startup()

        # Should gracefully disable
        assert watcher.enabled is False

    def test_set_callbacks(self):
        """Test setting callbacks."""
        watcher = ToolWatcher()

        async def on_added(tool):
            pass

        async def on_removed(name):
            pass

        watcher.set_callbacks(on_added=on_added, on_removed=on_removed)

        assert watcher._on_tool_added is on_added
        assert watcher._on_tool_removed is on_removed

    def test_generate_tool_name(self):
        """Test tool name generation.

        CAB-603: Tool names now use double underscore (__) separator:
        {tenant}__{api}__{operation}
        """
        watcher = ToolWatcher()

        # Basic case: tenant-acme, payment-search
        # Format: {tenant}__{api}__{operation} where api defaults to name
        name = watcher._generate_tool_name("tenant-acme", "payment-search")
        assert name == "tenant-acme__payment-search__payment-search"

        # Test special characters get sanitized
        name = watcher._generate_tool_name("my-ns", "my.tool.v1")
        assert name == "my-ns__my-tool-v1__my-tool-v1"

    def test_parse_tool_cr(self):
        """Test parsing Tool CR from dict."""
        watcher = ToolWatcher()

        obj = {
            "apiVersion": "gostoa.dev/v1alpha1",
            "kind": "Tool",
            "metadata": {
                "name": "test-tool",
                "namespace": "default",
            },
            "spec": {
                "displayName": "Test Tool",
                "description": "A test tool",
            },
        }

        tool_cr = watcher._parse_tool_cr(obj)

        assert tool_cr.metadata.name == "test-tool"
        assert tool_cr.spec.displayName == "Test Tool"

    def test_cr_to_tool(self):
        """Test converting Tool CR to MCP Tool.

        CAB-603: Tool names now use double underscore (__) separator:
        {tenant}__{api}__{operation}
        """
        watcher = ToolWatcher()

        tool_cr = ToolCR(
            metadata=ToolCRMetadata(
                name="payment-api",
                namespace="tenant-acme",
            ),
            spec=ToolCRSpec(
                displayName="Payment API",
                description="Payment API operations",
                endpoint="https://api.example.com/payments",
                method="POST",
                tags=["payments"],
                inputSchema={
                    "properties": {
                        "amount": {"type": "number"},
                    },
                    "required": ["amount"],
                },
            ),
        )

        tool = watcher._cr_to_tool(tool_cr)

        # CAB-603: New format {tenant}__{api}__{operation}
        assert tool.name == "tenant-acme__payment-api__payment-api"
        assert tool.description == "Payment API operations"
        assert tool.endpoint == "https://api.example.com/payments"
        assert tool.method == "POST"
        assert tool.tenant_id == "tenant-acme"
        assert "payments" in tool.tags

    @pytest.mark.asyncio
    async def test_handle_tool_event_added(self):
        """Test handling ADDED event.

        CAB-603: Tool names now use double underscore (__) separator.
        """
        watcher = ToolWatcher()

        added_tools = []

        async def on_added(tool):
            added_tools.append(tool)

        watcher.set_callbacks(on_added=on_added)

        tool_cr = ToolCR(
            metadata=ToolCRMetadata(
                name="test-tool",
                namespace="default",
            ),
            spec=ToolCRSpec(
                displayName="Test",
                description="Test tool",
                endpoint="https://api.example.com/test",  # Required field
            ),
        )

        await watcher._handle_tool_event("ADDED", tool_cr)

        assert len(added_tools) == 1
        # CAB-603: New format {tenant}__{api}__{operation}
        assert added_tools[0].name == "default__test-tool__test-tool"

    @pytest.mark.asyncio
    async def test_handle_tool_event_deleted(self):
        """Test handling DELETED event.

        CAB-603: Tool names now use double underscore (__) separator.
        """
        watcher = ToolWatcher()

        removed_tools = []

        async def on_removed(name):
            removed_tools.append(name)

        watcher.set_callbacks(on_removed=on_removed)

        # First add a tool
        tool_cr = ToolCR(
            metadata=ToolCRMetadata(
                name="test-tool",
                namespace="default",
            ),
            spec=ToolCRSpec(
                displayName="Test",
                description="Test tool",
                endpoint="https://api.example.com/test",  # Required field
            ),
        )
        # CAB-603: New format {tenant}__{api}__{operation}
        watcher._cr_to_tools["default/test-tool"] = ["default__test-tool__test-tool"]

        # Then delete it
        await watcher._handle_tool_event("DELETED", tool_cr)

        assert "default__test-tool__test-tool" in removed_tools

    @pytest.mark.asyncio
    async def test_handle_tool_event_disabled(self):
        """Test handling disabled tool."""
        watcher = ToolWatcher()

        removed_tools = []

        async def on_removed(name):
            removed_tools.append(name)

        watcher.set_callbacks(on_removed=on_removed)

        # Add tool first
        watcher._cr_to_tools["default/test-tool"] = ["default_test_tool"]

        # Disable it
        tool_cr = ToolCR(
            metadata=ToolCRMetadata(
                name="test-tool",
                namespace="default",
            ),
            spec=ToolCRSpec(
                displayName="Test",
                description="Test tool",
                enabled=False,  # Disabled
            ),
        )

        await watcher._handle_tool_event("MODIFIED", tool_cr)

        assert "default_test_tool" in removed_tools

    def test_apply_selector_tags(self):
        """Test applying tag selector."""
        from src.models import Tool, ToolInputSchema

        watcher = ToolWatcher()

        tools = [
            Tool(
                name="tool1",
                description="Tool 1",
                input_schema=ToolInputSchema(properties={}, required=[]),
                tags=["api", "public"],
            ),
            Tool(
                name="tool2",
                description="Tool 2",
                input_schema=ToolInputSchema(properties={}, required=[]),
                tags=["api", "internal"],
            ),
            Tool(
                name="tool3",
                description="Tool 3",
                input_schema=ToolInputSchema(properties={}, required=[]),
                tags=["admin"],
            ),
        ]

        selector = ToolSetSelectorSpec(tags=["api"])
        filtered = watcher._apply_selector(tools, selector)

        assert len(filtered) == 2
        assert all("api" in t.tags for t in filtered)

    def test_apply_selector_exclude_tags(self):
        """Test applying exclude tags selector."""
        from src.models import Tool, ToolInputSchema

        watcher = ToolWatcher()

        tools = [
            Tool(
                name="tool1",
                description="Tool 1",
                input_schema=ToolInputSchema(properties={}, required=[]),
                tags=["api", "public"],
            ),
            Tool(
                name="tool2",
                description="Tool 2",
                input_schema=ToolInputSchema(properties={}, required=[]),
                tags=["api", "internal"],
            ),
        ]

        selector = ToolSetSelectorSpec(excludeTags=["internal"])
        filtered = watcher._apply_selector(tools, selector)

        assert len(filtered) == 1
        assert filtered[0].name == "tool1"


# =============================================================================
# Singleton Tests
# =============================================================================


class TestToolWatcherSingleton:
    """Tests for tool watcher singleton."""

    @pytest.mark.asyncio
    async def test_get_tool_watcher_creates_singleton(self):
        """Test get_tool_watcher returns singleton."""
        await shutdown_tool_watcher()  # Clean up

        # Patch settings to disable K8s
        with patch("src.k8s.watcher.get_settings") as mock_settings:
            mock_settings.return_value.k8s_watcher_enabled = False
            mock_settings.return_value.k8s_watch_namespace = None
            mock_settings.return_value.kubeconfig_path = None

            watcher1 = await get_tool_watcher()
            watcher2 = await get_tool_watcher()

            assert watcher1 is watcher2

            await shutdown_tool_watcher()

    @pytest.mark.asyncio
    async def test_shutdown_clears_singleton(self):
        """Test shutdown clears the singleton."""
        with patch("src.k8s.watcher.get_settings") as mock_settings:
            mock_settings.return_value.k8s_watcher_enabled = False
            mock_settings.return_value.k8s_watch_namespace = None
            mock_settings.return_value.kubeconfig_path = None

            watcher1 = await get_tool_watcher()
            await shutdown_tool_watcher()

            watcher2 = await get_tool_watcher()
            assert watcher1 is not watcher2

            await shutdown_tool_watcher()


# =============================================================================
# Integration Tests
# =============================================================================


class TestToolWatcherIntegration:
    """Integration tests for tool watcher."""

    @pytest.mark.asyncio
    async def test_toolset_to_tools(self):
        """Test converting ToolSet to tools with mocked OpenAPI."""
        watcher = ToolWatcher()

        # Mock OpenAPI fetch
        openapi_spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/pets": {
                    "get": {
                        "operationId": "listPets",
                        "summary": "List all pets",
                        "tags": ["pets"],
                    },
                },
            },
        }

        with patch.object(
            watcher, "_fetch_openapi_spec", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.return_value = openapi_spec

            toolset_cr = ToolSetCR(
                metadata=ToolSetCRMetadata(
                    name="petstore",
                    namespace="tenant-test",
                ),
                spec=ToolSetCRSpec(
                    displayName="Petstore API",
                    openAPISpec=OpenAPISpecSource(
                        url="https://example.com/openapi.json",
                    ),
                ),
            )

            tools = await watcher._toolset_to_tools(toolset_cr)

            assert len(tools) >= 1
            # Tool should be created from the OpenAPI spec
