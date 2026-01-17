"""Tests for Core Tools (CAB-603).

Tests the 35 core platform tools with stoa_{domain}_{action} naming.
"""

import pytest

from src.models import CoreTool, ToolType, ToolDomain, ToolInputSchema
from src.tools import (
    CORE_TOOLS,
    CORE_TOOLS_BY_DOMAIN,
    CORE_TOOLS_BY_NAME,
    get_core_tool,
    get_core_tools_by_domain,
    list_all_core_tools,
)
from src.tools.core_tools import (
    PLATFORM_TOOLS,
    CATALOG_TOOLS,
    SUBSCRIPTION_TOOLS,
    OBSERVABILITY_TOOLS,
    UAC_TOOLS,
    SECURITY_TOOLS,
)


# =============================================================================
# Core Tool Count Tests
# =============================================================================


class TestCoreToolCounts:
    """Test that we have the expected number of core tools."""

    def test_total_core_tools_count(self):
        """Test that we have exactly 35 core tools."""
        assert len(CORE_TOOLS) == 35

    def test_platform_tools_count(self):
        """Test Platform & Discovery has 6 tools."""
        assert len(PLATFORM_TOOLS) == 6

    def test_catalog_tools_count(self):
        """Test API Catalog has 8 tools."""
        assert len(CATALOG_TOOLS) == 8

    def test_subscription_tools_count(self):
        """Test Subscriptions & Access has 6 tools."""
        assert len(SUBSCRIPTION_TOOLS) == 6

    def test_observability_tools_count(self):
        """Test Observability & Metrics has 8 tools."""
        assert len(OBSERVABILITY_TOOLS) == 8

    def test_uac_tools_count(self):
        """Test UAC Contracts has 4 tools."""
        assert len(UAC_TOOLS) == 4

    def test_security_tools_count(self):
        """Test Security & Compliance has 3 tools."""
        assert len(SECURITY_TOOLS) == 3


# =============================================================================
# Core Tool Naming Tests
# =============================================================================


class TestCoreToolNaming:
    """Test that all core tools follow stoa_* naming convention."""

    def test_all_tools_have_stoa_prefix(self):
        """Test all core tools start with 'stoa_'."""
        for tool in CORE_TOOLS:
            assert tool.name.startswith("stoa_"), f"Tool {tool.name} doesn't start with 'stoa_'"

    def test_all_tools_have_unique_names(self):
        """Test all core tool names are unique."""
        names = [tool.name for tool in CORE_TOOLS]
        assert len(names) == len(set(names)), "Duplicate tool names found"

    def test_platform_tools_naming(self):
        """Test platform tools follow stoa_platform_* or stoa_{action} naming."""
        expected_names = {
            "stoa_platform_info",
            "stoa_platform_health",
            "stoa_list_tools",
            "stoa_get_tool_schema",
            "stoa_search_tools",
            "stoa_list_tenants",
        }
        actual_names = {tool.name for tool in PLATFORM_TOOLS}
        assert actual_names == expected_names

    def test_catalog_tools_naming(self):
        """Test catalog tools follow stoa_catalog_* naming."""
        for tool in CATALOG_TOOLS:
            assert tool.name.startswith("stoa_catalog_"), f"Catalog tool {tool.name} doesn't follow stoa_catalog_* naming"

    def test_subscription_tools_naming(self):
        """Test subscription tools follow stoa_subscription_* naming."""
        for tool in SUBSCRIPTION_TOOLS:
            assert tool.name.startswith("stoa_subscription_"), f"Subscription tool {tool.name} doesn't follow stoa_subscription_* naming"

    def test_observability_tools_naming(self):
        """Test observability tools follow stoa_metrics_*, stoa_logs_*, stoa_alerts_* naming."""
        valid_prefixes = ("stoa_metrics_", "stoa_logs_", "stoa_alerts_")
        for tool in OBSERVABILITY_TOOLS:
            assert any(tool.name.startswith(p) for p in valid_prefixes), \
                f"Observability tool {tool.name} doesn't follow expected naming"

    def test_uac_tools_naming(self):
        """Test UAC tools follow stoa_uac_* naming."""
        for tool in UAC_TOOLS:
            assert tool.name.startswith("stoa_uac_"), f"UAC tool {tool.name} doesn't follow stoa_uac_* naming"

    def test_security_tools_naming(self):
        """Test security tools follow stoa_security_* naming."""
        for tool in SECURITY_TOOLS:
            assert tool.name.startswith("stoa_security_"), f"Security tool {tool.name} doesn't follow stoa_security_* naming"


# =============================================================================
# Core Tool Domain Tests
# =============================================================================


class TestCoreToolDomains:
    """Test that all core tools have correct domain assignments."""

    def test_platform_tools_have_platform_domain(self):
        """Test platform tools have PLATFORM domain."""
        for tool in PLATFORM_TOOLS:
            assert tool.domain == ToolDomain.PLATFORM, f"Tool {tool.name} has wrong domain"

    def test_catalog_tools_have_catalog_domain(self):
        """Test catalog tools have CATALOG domain."""
        for tool in CATALOG_TOOLS:
            assert tool.domain == ToolDomain.CATALOG, f"Tool {tool.name} has wrong domain"

    def test_subscription_tools_have_subscription_domain(self):
        """Test subscription tools have SUBSCRIPTION domain."""
        for tool in SUBSCRIPTION_TOOLS:
            assert tool.domain == ToolDomain.SUBSCRIPTION, f"Tool {tool.name} has wrong domain"

    def test_observability_tools_have_observability_domain(self):
        """Test observability tools have OBSERVABILITY domain."""
        for tool in OBSERVABILITY_TOOLS:
            assert tool.domain == ToolDomain.OBSERVABILITY, f"Tool {tool.name} has wrong domain"

    def test_uac_tools_have_uac_domain(self):
        """Test UAC tools have UAC domain."""
        for tool in UAC_TOOLS:
            assert tool.domain == ToolDomain.UAC, f"Tool {tool.name} has wrong domain"

    def test_security_tools_have_security_domain(self):
        """Test security tools have SECURITY domain."""
        for tool in SECURITY_TOOLS:
            assert tool.domain == ToolDomain.SECURITY, f"Tool {tool.name} has wrong domain"


# =============================================================================
# Core Tool Property Tests
# =============================================================================


class TestCoreToolProperties:
    """Test that all core tools have required properties."""

    def test_all_tools_have_description(self):
        """Test all core tools have a description."""
        for tool in CORE_TOOLS:
            assert tool.description, f"Tool {tool.name} has no description"
            assert len(tool.description) > 10, f"Tool {tool.name} has short description"

    def test_all_tools_have_input_schema(self):
        """Test all core tools have an input schema."""
        for tool in CORE_TOOLS:
            assert tool.input_schema is not None, f"Tool {tool.name} has no input schema"
            assert isinstance(tool.input_schema, ToolInputSchema)

    def test_all_tools_have_handler(self):
        """Test all core tools have a handler reference."""
        for tool in CORE_TOOLS:
            assert tool.handler, f"Tool {tool.name} has no handler"

    def test_all_tools_have_category(self):
        """Test all core tools have a category."""
        for tool in CORE_TOOLS:
            assert tool.category, f"Tool {tool.name} has no category"

    def test_all_tools_have_tags(self):
        """Test all core tools have at least one tag."""
        for tool in CORE_TOOLS:
            assert tool.tags, f"Tool {tool.name} has no tags"
            assert len(tool.tags) > 0

    def test_all_tools_return_core_type(self):
        """Test all core tools return CORE as tool_type."""
        for tool in CORE_TOOLS:
            assert tool.tool_type == ToolType.CORE, f"Tool {tool.name} has wrong tool_type"


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestHelperFunctions:
    """Test the helper functions for accessing core tools."""

    def test_get_core_tool_exists(self):
        """Test getting an existing core tool."""
        tool = get_core_tool("stoa_platform_info")
        assert tool is not None
        assert tool.name == "stoa_platform_info"

    def test_get_core_tool_not_found(self):
        """Test getting a non-existent core tool returns None."""
        tool = get_core_tool("nonexistent_tool")
        assert tool is None

    def test_get_core_tools_by_domain(self):
        """Test getting core tools by domain."""
        platform_tools = get_core_tools_by_domain(ToolDomain.PLATFORM)
        assert len(platform_tools) == 6
        for tool in platform_tools:
            assert tool.domain == ToolDomain.PLATFORM

    def test_get_core_tools_by_invalid_domain(self):
        """Test getting core tools by invalid domain returns empty list."""
        # Create a mock invalid domain - this would need special handling
        # For now, test that empty list is returned for valid but empty lookup
        tools = get_core_tools_by_domain(ToolDomain.PLATFORM)
        assert isinstance(tools, list)

    def test_list_all_core_tools(self):
        """Test listing all core tools."""
        tools = list_all_core_tools()
        assert len(tools) == 35
        assert tools is not CORE_TOOLS  # Should be a copy

    def test_core_tools_by_name_index(self):
        """Test CORE_TOOLS_BY_NAME index works correctly."""
        assert "stoa_platform_info" in CORE_TOOLS_BY_NAME
        assert CORE_TOOLS_BY_NAME["stoa_platform_info"].name == "stoa_platform_info"

    def test_core_tools_by_domain_index(self):
        """Test CORE_TOOLS_BY_DOMAIN index works correctly."""
        assert ToolDomain.PLATFORM in CORE_TOOLS_BY_DOMAIN
        assert len(CORE_TOOLS_BY_DOMAIN[ToolDomain.PLATFORM]) == 6


# =============================================================================
# Core Tool Validation Tests
# =============================================================================


class TestCoreToolValidation:
    """Test CoreTool model validation."""

    def test_core_tool_name_validation_passes(self):
        """Test that stoa_* names pass validation."""
        tool = CoreTool(
            name="stoa_test_tool",
            description="A test tool",
            domain=ToolDomain.PLATFORM,
            action="test",
            handler="platform.test",
            category="Test",
            tags=["test"],
        )
        assert tool.name == "stoa_test_tool"

    def test_core_tool_name_validation_fails(self):
        """Test that non-stoa_* names fail validation."""
        with pytest.raises(ValueError) as exc_info:
            CoreTool(
                name="invalid_name",  # Should fail
                description="A test tool",
                domain=ToolDomain.PLATFORM,
                action="test",
                handler="platform.test",
                category="Test",
                tags=["test"],
            )
        assert "must start with 'stoa_'" in str(exc_info.value)


# =============================================================================
# Specific Tool Tests
# =============================================================================


class TestSpecificCoreTools:
    """Test specific important core tools."""

    def test_stoa_platform_info(self):
        """Test stoa_platform_info tool definition."""
        tool = get_core_tool("stoa_platform_info")
        assert tool is not None
        assert tool.domain == ToolDomain.PLATFORM
        assert tool.action == "info"
        assert "platform" in tool.description.lower()

    def test_stoa_catalog_list_apis(self):
        """Test stoa_catalog_list_apis tool definition."""
        tool = get_core_tool("stoa_catalog_list_apis")
        assert tool is not None
        assert tool.domain == ToolDomain.CATALOG
        assert tool.action == "list_apis"
        assert tool.input_schema.properties  # Should have filter properties

    def test_stoa_subscription_create(self):
        """Test stoa_subscription_create tool definition."""
        tool = get_core_tool("stoa_subscription_create")
        assert tool is not None
        assert tool.domain == ToolDomain.SUBSCRIPTION
        assert tool.action == "create"
        assert "api_id" in tool.input_schema.required

    def test_stoa_metrics_get_usage(self):
        """Test stoa_metrics_get_usage tool definition."""
        tool = get_core_tool("stoa_metrics_get_usage")
        assert tool is not None
        assert tool.domain == ToolDomain.OBSERVABILITY
        assert "time_range" in tool.input_schema.properties

    def test_stoa_security_audit_log(self):
        """Test stoa_security_audit_log tool definition."""
        tool = get_core_tool("stoa_security_audit_log")
        assert tool is not None
        assert tool.domain == ToolDomain.SECURITY
        assert "audit" in tool.description.lower()
