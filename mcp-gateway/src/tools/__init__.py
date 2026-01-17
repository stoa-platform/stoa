"""STOA Core Tools package.

This package contains the built-in STOA platform tools organized by domain.

CAB-605 Phase 3: Consolidated action-based tools (12 tools total):
- Platform & Discovery: stoa_platform_info, stoa_platform_health, stoa_tools, stoa_tenants
- API Catalog: stoa_catalog, stoa_api_spec
- Subscriptions & Access: stoa_subscription
- Observability & Metrics: stoa_metrics, stoa_logs, stoa_alerts
- UAC Contracts: stoa_uac
- Security & Compliance: stoa_security

Legacy tools (35 total) are available via LEGACY_CORE_TOOLS for deprecation period.
Core tools follow the naming convention: stoa_{domain}_{action}
"""

from .core_tools import (
    # Legacy exports (for deprecation period)
    CORE_TOOLS as LEGACY_CORE_TOOLS,
    CORE_TOOLS_BY_DOMAIN,  # Keep original name for backward compatibility
    CORE_TOOLS_BY_DOMAIN as LEGACY_CORE_TOOLS_BY_DOMAIN,
    CORE_TOOLS_BY_NAME as LEGACY_CORE_TOOLS_BY_NAME,
    get_core_tool as get_legacy_core_tool,
    get_core_tools_by_domain,
    list_all_core_tools,
)

from .consolidated_tools import (
    # CAB-605: Consolidated action-based tools
    CONSOLIDATED_CORE_TOOLS,
    CONSOLIDATED_TOOLS_BY_NAME,
    DEPRECATION_MAPPINGS,
    # Domain-specific exports
    CONSOLIDATED_PLATFORM_TOOLS,
    CONSOLIDATED_CATALOG_TOOLS,
    CONSOLIDATED_SUBSCRIPTION_TOOLS,
    CONSOLIDATED_OBSERVABILITY_TOOLS,
    CONSOLIDATED_UAC_TOOLS,
    CONSOLIDATED_SECURITY_TOOLS,
)

# CAB-605: Default to consolidated tools
CORE_TOOLS = CONSOLIDATED_CORE_TOOLS
CORE_TOOLS_BY_NAME = CONSOLIDATED_TOOLS_BY_NAME


def get_core_tool(name: str):
    """Get a core tool by name, checking consolidated tools first.

    Args:
        name: Tool name

    Returns:
        CoreTool if found, None otherwise
    """
    # Try consolidated tools first
    if name in CONSOLIDATED_TOOLS_BY_NAME:
        return CONSOLIDATED_TOOLS_BY_NAME[name]
    # Fall back to legacy tools (for deprecation period)
    return LEGACY_CORE_TOOLS_BY_NAME.get(name)


__all__ = [
    # Primary exports (consolidated)
    "CORE_TOOLS",
    "CORE_TOOLS_BY_NAME",
    "CORE_TOOLS_BY_DOMAIN",  # Backward compatibility
    "get_core_tool",
    "get_core_tools_by_domain",
    "list_all_core_tools",
    # Consolidated tools
    "CONSOLIDATED_CORE_TOOLS",
    "CONSOLIDATED_TOOLS_BY_NAME",
    "DEPRECATION_MAPPINGS",
    "CONSOLIDATED_PLATFORM_TOOLS",
    "CONSOLIDATED_CATALOG_TOOLS",
    "CONSOLIDATED_SUBSCRIPTION_TOOLS",
    "CONSOLIDATED_OBSERVABILITY_TOOLS",
    "CONSOLIDATED_UAC_TOOLS",
    "CONSOLIDATED_SECURITY_TOOLS",
    # Legacy exports (for deprecation)
    "LEGACY_CORE_TOOLS",
    "LEGACY_CORE_TOOLS_BY_DOMAIN",
    "LEGACY_CORE_TOOLS_BY_NAME",
    "get_legacy_core_tool",
]
