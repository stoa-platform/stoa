# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""STOA Core Tools Definitions.

Defines the 35 built-in STOA platform tools organized by domain.
Each tool follows the naming convention: stoa_{domain}_{action}

CAB-603: MCP RBAC Phase 1 - Tool Registry Restructure
"""

from src.models.mcp import CoreTool, ToolDomain, ToolInputSchema


# =============================================================================
# Category 1: Platform & Discovery (6 tools)
# =============================================================================

PLATFORM_TOOLS: list[CoreTool] = [
    CoreTool(
        name="stoa_platform_info",
        description="Get STOA platform version, status, and available features",
        domain=ToolDomain.PLATFORM,
        action="info",
        handler="platform.get_info",
        category="Platform & Discovery",
        tags=["platform", "info", "version"],
        input_schema=ToolInputSchema(
            type="object",
            properties={},
            required=[],
        ),
    ),
    CoreTool(
        name="stoa_platform_health",
        description="Health check all platform components (Gateway, Keycloak, Database, Kafka)",
        domain=ToolDomain.PLATFORM,
        action="health",
        handler="platform.health_check",
        category="Platform & Discovery",
        tags=["platform", "health", "monitoring"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "components": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific components to check (optional, all if empty)",
                },
            },
            required=[],
        ),
    ),
    CoreTool(
        name="stoa_list_tools",
        description="List all available tools for the current user with optional filtering",
        domain=ToolDomain.PLATFORM,
        action="list_tools",
        handler="platform.list_tools",
        category="Platform & Discovery",
        tags=["platform", "tools", "discovery"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "category": {
                    "type": "string",
                    "description": "Filter by category",
                },
                "tag": {
                    "type": "string",
                    "description": "Filter by tag",
                },
                "search": {
                    "type": "string",
                    "description": "Search in tool names and descriptions",
                },
                "include_proxied": {
                    "type": "boolean",
                    "description": "Include proxied tenant tools (default: true)",
                    "default": True,
                },
            },
            required=[],
        ),
    ),
    CoreTool(
        name="stoa_get_tool_schema",
        description="Get the input schema for a specific tool",
        domain=ToolDomain.PLATFORM,
        action="get_tool_schema",
        handler="platform.get_tool_schema",
        category="Platform & Discovery",
        tags=["platform", "tools", "schema"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "tool_name": {
                    "type": "string",
                    "description": "Name of the tool to get schema for",
                },
            },
            required=["tool_name"],
        ),
    ),
    CoreTool(
        name="stoa_search_tools",
        description="Search tools by name, tag, category, or description",
        domain=ToolDomain.PLATFORM,
        action="search_tools",
        handler="platform.search_tools",
        category="Platform & Discovery",
        tags=["platform", "tools", "search"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return",
                    "default": 20,
                },
            },
            required=["query"],
        ),
    ),
    CoreTool(
        name="stoa_list_tenants",
        description="List accessible tenants (admin only)",
        domain=ToolDomain.PLATFORM,
        action="list_tenants",
        handler="platform.list_tenants",
        category="Platform & Discovery",
        tags=["platform", "tenants", "admin"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "include_inactive": {
                    "type": "boolean",
                    "description": "Include inactive tenants",
                    "default": False,
                },
            },
            required=[],
        ),
    ),
]


# =============================================================================
# Category 2: API Catalog (8 tools)
# =============================================================================

CATALOG_TOOLS: list[CoreTool] = [
    CoreTool(
        name="stoa_catalog_list_apis",
        description="List APIs in the catalog with optional filtering",
        domain=ToolDomain.CATALOG,
        action="list_apis",
        handler="catalog.list_apis",
        category="API Catalog",
        tags=["catalog", "api", "list"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "category": {
                    "type": "string",
                    "description": "Filter by API category",
                },
                "status": {
                    "type": "string",
                    "enum": ["active", "deprecated", "draft"],
                    "description": "Filter by API status",
                },
                "search": {
                    "type": "string",
                    "description": "Search in API names and descriptions",
                },
                "page": {
                    "type": "integer",
                    "description": "Page number for pagination",
                    "default": 1,
                },
                "page_size": {
                    "type": "integer",
                    "description": "Items per page",
                    "default": 20,
                },
            },
            required=[],
        ),
    ),
    CoreTool(
        name="stoa_catalog_get_api",
        description="Get detailed information about a specific API",
        domain=ToolDomain.CATALOG,
        action="get_api",
        handler="catalog.get_api",
        category="API Catalog",
        tags=["catalog", "api", "details"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "api_id": {
                    "type": "string",
                    "description": "Unique API identifier",
                },
            },
            required=["api_id"],
        ),
    ),
    CoreTool(
        name="stoa_catalog_search_apis",
        description="Advanced search for APIs with multiple criteria",
        domain=ToolDomain.CATALOG,
        action="search_apis",
        handler="catalog.search_apis",
        category="API Catalog",
        tags=["catalog", "api", "search"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "query": {
                    "type": "string",
                    "description": "Free-text search query",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter by tags (AND logic)",
                },
                "categories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter by categories (OR logic)",
                },
                "min_version": {
                    "type": "string",
                    "description": "Minimum API version",
                },
            },
            required=["query"],
        ),
    ),
    CoreTool(
        name="stoa_catalog_get_openapi",
        description="Get the OpenAPI specification for an API",
        domain=ToolDomain.CATALOG,
        action="get_openapi",
        handler="catalog.get_openapi",
        category="API Catalog",
        tags=["catalog", "api", "openapi", "spec"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "api_id": {
                    "type": "string",
                    "description": "Unique API identifier",
                },
                "version": {
                    "type": "string",
                    "description": "Specific API version (optional, latest if omitted)",
                },
                "format": {
                    "type": "string",
                    "enum": ["json", "yaml"],
                    "description": "Output format",
                    "default": "json",
                },
            },
            required=["api_id"],
        ),
    ),
    CoreTool(
        name="stoa_catalog_list_versions",
        description="List all versions of an API",
        domain=ToolDomain.CATALOG,
        action="list_versions",
        handler="catalog.list_versions",
        category="API Catalog",
        tags=["catalog", "api", "versions"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "api_id": {
                    "type": "string",
                    "description": "Unique API identifier",
                },
            },
            required=["api_id"],
        ),
    ),
    CoreTool(
        name="stoa_catalog_get_documentation",
        description="Get documentation for an API",
        domain=ToolDomain.CATALOG,
        action="get_documentation",
        handler="catalog.get_documentation",
        category="API Catalog",
        tags=["catalog", "api", "documentation"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "api_id": {
                    "type": "string",
                    "description": "Unique API identifier",
                },
                "section": {
                    "type": "string",
                    "description": "Specific documentation section (optional)",
                },
            },
            required=["api_id"],
        ),
    ),
    CoreTool(
        name="stoa_catalog_list_categories",
        description="List all API categories with counts",
        domain=ToolDomain.CATALOG,
        action="list_categories",
        handler="catalog.list_categories",
        category="API Catalog",
        tags=["catalog", "categories"],
        input_schema=ToolInputSchema(
            type="object",
            properties={},
            required=[],
        ),
    ),
    CoreTool(
        name="stoa_catalog_get_endpoints",
        description="List all endpoints for an API with their methods and descriptions",
        domain=ToolDomain.CATALOG,
        action="get_endpoints",
        handler="catalog.get_endpoints",
        category="API Catalog",
        tags=["catalog", "api", "endpoints"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "api_id": {
                    "type": "string",
                    "description": "Unique API identifier",
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                    "description": "Filter by HTTP method",
                },
            },
            required=["api_id"],
        ),
    ),
]


# =============================================================================
# Category 3: Subscriptions & Access (6 tools)
# =============================================================================

SUBSCRIPTION_TOOLS: list[CoreTool] = [
    CoreTool(
        name="stoa_subscription_list",
        description="List user's API subscriptions",
        domain=ToolDomain.SUBSCRIPTION,
        action="list",
        handler="subscription.list_subscriptions",
        category="Subscriptions & Access",
        tags=["subscription", "list"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "status": {
                    "type": "string",
                    "enum": ["active", "pending", "suspended", "cancelled"],
                    "description": "Filter by subscription status",
                },
                "api_id": {
                    "type": "string",
                    "description": "Filter by specific API",
                },
            },
            required=[],
        ),
    ),
    CoreTool(
        name="stoa_subscription_get",
        description="Get details of a specific subscription",
        domain=ToolDomain.SUBSCRIPTION,
        action="get",
        handler="subscription.get_subscription",
        category="Subscriptions & Access",
        tags=["subscription", "details"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "subscription_id": {
                    "type": "string",
                    "description": "Unique subscription identifier",
                },
            },
            required=["subscription_id"],
        ),
    ),
    CoreTool(
        name="stoa_subscription_create",
        description="Subscribe to an API",
        domain=ToolDomain.SUBSCRIPTION,
        action="create",
        handler="subscription.create_subscription",
        category="Subscriptions & Access",
        tags=["subscription", "create"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "api_id": {
                    "type": "string",
                    "description": "API to subscribe to",
                },
                "plan": {
                    "type": "string",
                    "description": "Subscription plan (if applicable)",
                },
                "application_name": {
                    "type": "string",
                    "description": "Name of the application using the API",
                },
            },
            required=["api_id"],
        ),
    ),
    CoreTool(
        name="stoa_subscription_cancel",
        description="Cancel an API subscription",
        domain=ToolDomain.SUBSCRIPTION,
        action="cancel",
        handler="subscription.cancel_subscription",
        category="Subscriptions & Access",
        tags=["subscription", "cancel"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "subscription_id": {
                    "type": "string",
                    "description": "Subscription to cancel",
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for cancellation (optional)",
                },
            },
            required=["subscription_id"],
        ),
    ),
    CoreTool(
        name="stoa_subscription_get_credentials",
        description="Get API credentials for a subscription (API key, client ID)",
        domain=ToolDomain.SUBSCRIPTION,
        action="get_credentials",
        handler="subscription.get_credentials",
        category="Subscriptions & Access",
        tags=["subscription", "credentials", "api-key"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "subscription_id": {
                    "type": "string",
                    "description": "Subscription identifier",
                },
            },
            required=["subscription_id"],
        ),
    ),
    CoreTool(
        name="stoa_subscription_rotate_key",
        description="Rotate the API key for a subscription",
        domain=ToolDomain.SUBSCRIPTION,
        action="rotate_key",
        handler="subscription.rotate_key",
        category="Subscriptions & Access",
        tags=["subscription", "credentials", "security"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "subscription_id": {
                    "type": "string",
                    "description": "Subscription identifier",
                },
                "grace_period_hours": {
                    "type": "integer",
                    "description": "Hours to keep old key valid (default: 24)",
                    "default": 24,
                },
            },
            required=["subscription_id"],
        ),
    ),
]


# =============================================================================
# Category 4: Observability & Metrics (8 tools)
# =============================================================================

OBSERVABILITY_TOOLS: list[CoreTool] = [
    CoreTool(
        name="stoa_metrics_get_usage",
        description="Get API usage metrics (requests, data volume)",
        domain=ToolDomain.OBSERVABILITY,
        action="get_usage",
        handler="observability.get_usage",
        category="Observability & Metrics",
        tags=["metrics", "usage", "analytics"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "api_id": {
                    "type": "string",
                    "description": "API to get metrics for (optional, all APIs if omitted)",
                },
                "subscription_id": {
                    "type": "string",
                    "description": "Filter by subscription",
                },
                "time_range": {
                    "type": "string",
                    "enum": ["1h", "24h", "7d", "30d", "custom"],
                    "description": "Time range for metrics",
                    "default": "24h",
                },
                "start_time": {
                    "type": "string",
                    "format": "date-time",
                    "description": "Start time for custom range (ISO 8601)",
                },
                "end_time": {
                    "type": "string",
                    "format": "date-time",
                    "description": "End time for custom range (ISO 8601)",
                },
            },
            required=[],
        ),
    ),
    CoreTool(
        name="stoa_metrics_get_latency",
        description="Get API latency statistics (p50, p95, p99)",
        domain=ToolDomain.OBSERVABILITY,
        action="get_latency",
        handler="observability.get_latency",
        category="Observability & Metrics",
        tags=["metrics", "latency", "performance"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "api_id": {
                    "type": "string",
                    "description": "API to get latency for",
                },
                "endpoint": {
                    "type": "string",
                    "description": "Specific endpoint (optional)",
                },
                "time_range": {
                    "type": "string",
                    "enum": ["1h", "24h", "7d", "30d"],
                    "description": "Time range",
                    "default": "24h",
                },
            },
            required=["api_id"],
        ),
    ),
    CoreTool(
        name="stoa_metrics_get_errors",
        description="Get API error rates and breakdown by error type",
        domain=ToolDomain.OBSERVABILITY,
        action="get_errors",
        handler="observability.get_errors",
        category="Observability & Metrics",
        tags=["metrics", "errors", "debugging"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "api_id": {
                    "type": "string",
                    "description": "API to get errors for",
                },
                "time_range": {
                    "type": "string",
                    "enum": ["1h", "24h", "7d", "30d"],
                    "description": "Time range",
                    "default": "24h",
                },
                "error_code": {
                    "type": "integer",
                    "description": "Filter by specific HTTP error code",
                },
            },
            required=["api_id"],
        ),
    ),
    CoreTool(
        name="stoa_metrics_get_quota",
        description="Get quota usage for a subscription",
        domain=ToolDomain.OBSERVABILITY,
        action="get_quota",
        handler="observability.get_quota",
        category="Observability & Metrics",
        tags=["metrics", "quota", "limits"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "subscription_id": {
                    "type": "string",
                    "description": "Subscription to check quota for",
                },
            },
            required=["subscription_id"],
        ),
    ),
    CoreTool(
        name="stoa_logs_search",
        description="Search API logs with filters",
        domain=ToolDomain.OBSERVABILITY,
        action="logs_search",
        handler="observability.search_logs",
        category="Observability & Metrics",
        tags=["logs", "search", "debugging"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "api_id": {
                    "type": "string",
                    "description": "API to search logs for",
                },
                "query": {
                    "type": "string",
                    "description": "Search query (supports Lucene syntax)",
                },
                "level": {
                    "type": "string",
                    "enum": ["debug", "info", "warn", "error"],
                    "description": "Log level filter",
                },
                "time_range": {
                    "type": "string",
                    "enum": ["1h", "24h", "7d"],
                    "description": "Time range",
                    "default": "24h",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum logs to return",
                    "default": 100,
                },
            },
            required=["api_id"],
        ),
    ),
    CoreTool(
        name="stoa_logs_get_recent",
        description="Get recent API call logs",
        domain=ToolDomain.OBSERVABILITY,
        action="logs_recent",
        handler="observability.get_recent_logs",
        category="Observability & Metrics",
        tags=["logs", "recent"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "api_id": {
                    "type": "string",
                    "description": "API to get logs for",
                },
                "subscription_id": {
                    "type": "string",
                    "description": "Filter by subscription",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of logs to return",
                    "default": 50,
                },
            },
            required=[],
        ),
    ),
    CoreTool(
        name="stoa_alerts_list",
        description="List active alerts for APIs",
        domain=ToolDomain.OBSERVABILITY,
        action="alerts_list",
        handler="observability.list_alerts",
        category="Observability & Metrics",
        tags=["alerts", "monitoring"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "api_id": {
                    "type": "string",
                    "description": "Filter by API",
                },
                "severity": {
                    "type": "string",
                    "enum": ["info", "warning", "critical"],
                    "description": "Filter by severity",
                },
                "status": {
                    "type": "string",
                    "enum": ["active", "acknowledged", "resolved"],
                    "description": "Filter by status",
                    "default": "active",
                },
            },
            required=[],
        ),
    ),
    CoreTool(
        name="stoa_alerts_acknowledge",
        description="Acknowledge an alert",
        domain=ToolDomain.OBSERVABILITY,
        action="alerts_acknowledge",
        handler="observability.acknowledge_alert",
        category="Observability & Metrics",
        tags=["alerts", "acknowledge"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "alert_id": {
                    "type": "string",
                    "description": "Alert to acknowledge",
                },
                "comment": {
                    "type": "string",
                    "description": "Acknowledgement comment",
                },
            },
            required=["alert_id"],
        ),
    ),
]


# =============================================================================
# Category 5: UAC Contracts (4 tools)
# =============================================================================

UAC_TOOLS: list[CoreTool] = [
    CoreTool(
        name="stoa_uac_list_contracts",
        description="List UAC (Usage and Access Control) contracts",
        domain=ToolDomain.UAC,
        action="list_contracts",
        handler="uac.list_contracts",
        category="UAC Contracts",
        tags=["uac", "contracts", "list"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "api_id": {
                    "type": "string",
                    "description": "Filter by API",
                },
                "status": {
                    "type": "string",
                    "enum": ["active", "expired", "pending"],
                    "description": "Filter by contract status",
                },
            },
            required=[],
        ),
    ),
    CoreTool(
        name="stoa_uac_get_contract",
        description="Get details of a specific UAC contract",
        domain=ToolDomain.UAC,
        action="get_contract",
        handler="uac.get_contract",
        category="UAC Contracts",
        tags=["uac", "contracts", "details"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "contract_id": {
                    "type": "string",
                    "description": "Contract identifier",
                },
            },
            required=["contract_id"],
        ),
    ),
    CoreTool(
        name="stoa_uac_validate_contract",
        description="Validate compliance with a UAC contract",
        domain=ToolDomain.UAC,
        action="validate_contract",
        handler="uac.validate_contract",
        category="UAC Contracts",
        tags=["uac", "contracts", "compliance"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "contract_id": {
                    "type": "string",
                    "description": "Contract to validate",
                },
                "subscription_id": {
                    "type": "string",
                    "description": "Subscription to check compliance for",
                },
            },
            required=["contract_id"],
        ),
    ),
    CoreTool(
        name="stoa_uac_get_sla",
        description="Get SLA metrics for a UAC contract",
        domain=ToolDomain.UAC,
        action="get_sla",
        handler="uac.get_sla",
        category="UAC Contracts",
        tags=["uac", "sla", "metrics"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "contract_id": {
                    "type": "string",
                    "description": "Contract identifier",
                },
                "time_range": {
                    "type": "string",
                    "enum": ["7d", "30d", "90d"],
                    "description": "Time range for SLA metrics",
                    "default": "30d",
                },
            },
            required=["contract_id"],
        ),
    ),
]


# =============================================================================
# Category 6: Security & Compliance (3 tools)
# =============================================================================

SECURITY_TOOLS: list[CoreTool] = [
    CoreTool(
        name="stoa_security_audit_log",
        description="Get security audit log entries",
        domain=ToolDomain.SECURITY,
        action="audit_log",
        handler="security.get_audit_log",
        category="Security & Compliance",
        tags=["security", "audit", "compliance"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "api_id": {
                    "type": "string",
                    "description": "Filter by API",
                },
                "user_id": {
                    "type": "string",
                    "description": "Filter by user",
                },
                "action": {
                    "type": "string",
                    "description": "Filter by action type",
                },
                "time_range": {
                    "type": "string",
                    "enum": ["24h", "7d", "30d", "90d"],
                    "description": "Time range",
                    "default": "7d",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum entries to return",
                    "default": 100,
                },
            },
            required=[],
        ),
    ),
    CoreTool(
        name="stoa_security_check_permissions",
        description="Check user permissions for an API or action",
        domain=ToolDomain.SECURITY,
        action="check_permissions",
        handler="security.check_permissions",
        category="Security & Compliance",
        tags=["security", "permissions", "rbac"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "api_id": {
                    "type": "string",
                    "description": "API to check permissions for",
                },
                "action": {
                    "type": "string",
                    "description": "Action to check (read, write, admin)",
                },
                "user_id": {
                    "type": "string",
                    "description": "User to check (optional, current user if omitted)",
                },
            },
            required=["api_id", "action"],
        ),
    ),
    CoreTool(
        name="stoa_security_list_policies",
        description="List active security policies",
        domain=ToolDomain.SECURITY,
        action="list_policies",
        handler="security.list_policies",
        category="Security & Compliance",
        tags=["security", "policies"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "api_id": {
                    "type": "string",
                    "description": "Filter by API",
                },
                "policy_type": {
                    "type": "string",
                    "enum": ["rate_limit", "ip_whitelist", "oauth", "jwt"],
                    "description": "Filter by policy type",
                },
            },
            required=[],
        ),
    ),
]


# =============================================================================
# Aggregated Collections
# =============================================================================

# All core tools as a flat list
CORE_TOOLS: list[CoreTool] = (
    PLATFORM_TOOLS
    + CATALOG_TOOLS
    + SUBSCRIPTION_TOOLS
    + OBSERVABILITY_TOOLS
    + UAC_TOOLS
    + SECURITY_TOOLS
)

# Core tools indexed by domain
CORE_TOOLS_BY_DOMAIN: dict[ToolDomain, list[CoreTool]] = {
    ToolDomain.PLATFORM: PLATFORM_TOOLS,
    ToolDomain.CATALOG: CATALOG_TOOLS,
    ToolDomain.SUBSCRIPTION: SUBSCRIPTION_TOOLS,
    ToolDomain.OBSERVABILITY: OBSERVABILITY_TOOLS,
    ToolDomain.UAC: UAC_TOOLS,
    ToolDomain.SECURITY: SECURITY_TOOLS,
}

# Core tools indexed by name for fast lookup
CORE_TOOLS_BY_NAME: dict[str, CoreTool] = {tool.name: tool for tool in CORE_TOOLS}


# =============================================================================
# Helper Functions
# =============================================================================


def get_core_tool(name: str) -> CoreTool | None:
    """Get a core tool by name.

    Args:
        name: Tool name (e.g., 'stoa_platform_info')

    Returns:
        CoreTool if found, None otherwise
    """
    return CORE_TOOLS_BY_NAME.get(name)


def get_core_tools_by_domain(domain: ToolDomain) -> list[CoreTool]:
    """Get all core tools for a specific domain.

    Args:
        domain: Tool domain

    Returns:
        List of CoreTool instances for the domain
    """
    return CORE_TOOLS_BY_DOMAIN.get(domain, [])


def list_all_core_tools() -> list[CoreTool]:
    """Get all core tools.

    Returns:
        List of all 35 CoreTool instances
    """
    return CORE_TOOLS.copy()
