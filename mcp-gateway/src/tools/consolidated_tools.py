# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""CAB-605 Phase 3: Consolidated Action-Based Tools.

Reduces tool count by using action enum parameters instead of separate tools.
Each consolidated tool handles multiple related operations.

Consolidation Summary:
- Catalog: 8 → 2 tools (stoa_catalog, stoa_api_spec)
- Subscription: 6 → 1 tool (stoa_subscription)
- Observability: 8 → 3 tools (stoa_metrics, stoa_logs, stoa_alerts)
- Platform: 6 → 4 tools (keep stoa_platform_info, stoa_platform_health; consolidate tools)
- UAC: 4 → 1 tool (stoa_uac)
- Security: 3 → 1 tool (stoa_security)
"""

from src.models.mcp import CoreTool, ToolDomain, ToolInputSchema


# =============================================================================
# Consolidated Catalog Tools (8 → 2)
# =============================================================================

CONSOLIDATED_CATALOG_TOOLS: list[CoreTool] = [
    CoreTool(
        name="stoa_catalog",
        description="""API catalog operations for browsing, searching, and managing APIs.

Actions:
- list: List all APIs with optional filtering by status, category
- get: Get detailed information about a specific API (requires: api_id)
- search: Search APIs by query, tags, or categories (requires: query)
- versions: List all versions of an API (requires: api_id)
- categories: List all API categories with counts

Examples:
- {"action": "list", "status": "active", "page": 1}
- {"action": "get", "api_id": "billing-api-v2"}
- {"action": "search", "query": "payment", "tags": ["finance"]}
- {"action": "versions", "api_id": "billing-api"}
- {"action": "categories"}
""",
        domain=ToolDomain.CATALOG,
        action="catalog",
        handler="catalog.dispatch",
        category="API Catalog",
        tags=["catalog", "api", "list", "search", "versions"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "action": {
                    "type": "string",
                    "enum": ["list", "get", "search", "versions", "categories"],
                    "description": "Operation to perform",
                },
                "api_id": {
                    "type": "string",
                    "description": "API identifier (required for: get, versions)",
                },
                "query": {
                    "type": "string",
                    "description": "Search query (required for: search)",
                },
                "status": {
                    "type": "string",
                    "enum": ["active", "deprecated", "draft"],
                    "description": "Filter by status (for: list)",
                },
                "category": {
                    "type": "string",
                    "description": "Filter by category (for: list, search)",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter by tags (for: list, search)",
                },
                "page": {
                    "type": "integer",
                    "default": 1,
                    "description": "Page number (for: list, search)",
                },
                "page_size": {
                    "type": "integer",
                    "default": 20,
                    "description": "Results per page (for: list, search)",
                },
            },
            required=["action"],
        ),
    ),
    CoreTool(
        name="stoa_api_spec",
        description="""API specification and documentation retrieval.

Actions:
- openapi: Get OpenAPI/Swagger specification (requires: api_id)
- docs: Get human-readable documentation (requires: api_id)
- endpoints: List all endpoints with methods (requires: api_id)

Examples:
- {"action": "openapi", "api_id": "billing-api", "format": "json"}
- {"action": "docs", "api_id": "billing-api", "section": "authentication"}
- {"action": "endpoints", "api_id": "billing-api", "method": "POST"}
""",
        domain=ToolDomain.CATALOG,
        action="api_spec",
        handler="catalog.spec_dispatch",
        category="API Catalog",
        tags=["catalog", "api", "openapi", "documentation", "endpoints"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "action": {
                    "type": "string",
                    "enum": ["openapi", "docs", "endpoints"],
                    "description": "Operation to perform",
                },
                "api_id": {
                    "type": "string",
                    "description": "API identifier (required for all actions)",
                },
                "version": {
                    "type": "string",
                    "description": "API version (optional, latest if omitted)",
                },
                "format": {
                    "type": "string",
                    "enum": ["json", "yaml"],
                    "default": "json",
                    "description": "Output format (for: openapi)",
                },
                "section": {
                    "type": "string",
                    "description": "Documentation section (for: docs)",
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                    "description": "Filter by HTTP method (for: endpoints)",
                },
            },
            required=["action", "api_id"],
        ),
    ),
]


# =============================================================================
# Consolidated Subscription Tool (6 → 1)
# =============================================================================

CONSOLIDATED_SUBSCRIPTION_TOOLS: list[CoreTool] = [
    CoreTool(
        name="stoa_subscription",
        description="""API subscription management for subscribing, credentials, and lifecycle.

Actions:
- list: List user's subscriptions with optional filters
- get: Get subscription details (requires: subscription_id)
- create: Subscribe to an API (requires: api_id)
- cancel: Cancel a subscription (requires: subscription_id)
- credentials: Get API credentials for a subscription (requires: subscription_id)
- rotate_key: Rotate API key with grace period (requires: subscription_id)

Examples:
- {"action": "list", "status": "active"}
- {"action": "get", "subscription_id": "sub-123"}
- {"action": "create", "api_id": "billing-api", "plan": "standard"}
- {"action": "cancel", "subscription_id": "sub-123", "reason": "No longer needed"}
- {"action": "credentials", "subscription_id": "sub-123"}
- {"action": "rotate_key", "subscription_id": "sub-123", "grace_period_hours": 24}
""",
        domain=ToolDomain.SUBSCRIPTION,
        action="subscription",
        handler="subscription.dispatch",
        category="Subscriptions & Access",
        tags=["subscription", "access", "credentials", "api-key"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "action": {
                    "type": "string",
                    "enum": ["list", "get", "create", "cancel", "credentials", "rotate_key"],
                    "description": "Operation to perform",
                },
                "subscription_id": {
                    "type": "string",
                    "description": "Subscription identifier (for: get, cancel, credentials, rotate_key)",
                },
                "api_id": {
                    "type": "string",
                    "description": "API to subscribe to (for: create, list filter)",
                },
                "status": {
                    "type": "string",
                    "enum": ["active", "pending", "suspended", "cancelled"],
                    "description": "Filter by subscription status (for: list)",
                },
                "plan": {
                    "type": "string",
                    "description": "Subscription plan (for: create)",
                },
                "application_name": {
                    "type": "string",
                    "description": "Application name (for: create)",
                },
                "reason": {
                    "type": "string",
                    "description": "Cancellation reason (for: cancel)",
                },
                "grace_period_hours": {
                    "type": "integer",
                    "default": 24,
                    "description": "Hours to keep old key valid (for: rotate_key)",
                },
            },
            required=["action"],
        ),
    ),
]


# =============================================================================
# Consolidated Observability Tools (8 → 3)
# =============================================================================

CONSOLIDATED_OBSERVABILITY_TOOLS: list[CoreTool] = [
    CoreTool(
        name="stoa_metrics",
        description="""API metrics retrieval for usage, latency, errors, and quotas.

Actions:
- usage: Get API usage metrics (requests, data volume)
- latency: Get latency statistics (p50, p95, p99) (requires: api_id)
- errors: Get error rates and breakdown (requires: api_id)
- quota: Get quota usage for subscription (requires: subscription_id)

Examples:
- {"action": "usage", "api_id": "billing-api", "time_range": "24h"}
- {"action": "latency", "api_id": "billing-api", "endpoint": "/invoices"}
- {"action": "errors", "api_id": "billing-api", "error_code": 500}
- {"action": "quota", "subscription_id": "sub-123"}
""",
        domain=ToolDomain.OBSERVABILITY,
        action="metrics",
        handler="observability.metrics_dispatch",
        category="Observability & Metrics",
        tags=["metrics", "usage", "latency", "errors", "quota"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "action": {
                    "type": "string",
                    "enum": ["usage", "latency", "errors", "quota"],
                    "description": "Metric type to retrieve",
                },
                "api_id": {
                    "type": "string",
                    "description": "API identifier (for: usage, latency, errors)",
                },
                "subscription_id": {
                    "type": "string",
                    "description": "Subscription identifier (for: usage, quota)",
                },
                "endpoint": {
                    "type": "string",
                    "description": "Specific endpoint (for: latency)",
                },
                "error_code": {
                    "type": "integer",
                    "description": "Filter by HTTP error code (for: errors)",
                },
                "time_range": {
                    "type": "string",
                    "enum": ["1h", "24h", "7d", "30d", "custom"],
                    "default": "24h",
                    "description": "Time range for metrics",
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
            required=["action"],
        ),
    ),
    CoreTool(
        name="stoa_logs",
        description="""API log search and retrieval for debugging and analysis.

Actions:
- search: Search logs with filters and Lucene query syntax (requires: api_id)
- recent: Get recent API call logs

Examples:
- {"action": "search", "api_id": "billing-api", "query": "error", "level": "error"}
- {"action": "recent", "api_id": "billing-api", "limit": 50}
""",
        domain=ToolDomain.OBSERVABILITY,
        action="logs",
        handler="observability.logs_dispatch",
        category="Observability & Metrics",
        tags=["logs", "search", "debugging"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "action": {
                    "type": "string",
                    "enum": ["search", "recent"],
                    "description": "Operation to perform",
                },
                "api_id": {
                    "type": "string",
                    "description": "API identifier",
                },
                "subscription_id": {
                    "type": "string",
                    "description": "Filter by subscription",
                },
                "query": {
                    "type": "string",
                    "description": "Search query (Lucene syntax, for: search)",
                },
                "level": {
                    "type": "string",
                    "enum": ["debug", "info", "warn", "error"],
                    "description": "Log level filter",
                },
                "time_range": {
                    "type": "string",
                    "enum": ["1h", "24h", "7d"],
                    "default": "24h",
                    "description": "Time range",
                },
                "limit": {
                    "type": "integer",
                    "default": 100,
                    "description": "Maximum results to return",
                },
            },
            required=["action"],
        ),
    ),
    CoreTool(
        name="stoa_alerts",
        description="""API alert management for monitoring and incident response.

Actions:
- list: List active alerts with optional filters
- acknowledge: Acknowledge an alert (requires: alert_id)

Examples:
- {"action": "list", "api_id": "billing-api", "severity": "critical"}
- {"action": "acknowledge", "alert_id": "alert-123", "comment": "Investigating"}
""",
        domain=ToolDomain.OBSERVABILITY,
        action="alerts",
        handler="observability.alerts_dispatch",
        category="Observability & Metrics",
        tags=["alerts", "monitoring", "incidents"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "action": {
                    "type": "string",
                    "enum": ["list", "acknowledge"],
                    "description": "Operation to perform",
                },
                "alert_id": {
                    "type": "string",
                    "description": "Alert identifier (for: acknowledge)",
                },
                "api_id": {
                    "type": "string",
                    "description": "Filter by API (for: list)",
                },
                "severity": {
                    "type": "string",
                    "enum": ["info", "warning", "critical"],
                    "description": "Filter by severity (for: list)",
                },
                "status": {
                    "type": "string",
                    "enum": ["active", "acknowledged", "resolved"],
                    "default": "active",
                    "description": "Filter by status (for: list)",
                },
                "comment": {
                    "type": "string",
                    "description": "Acknowledgement comment (for: acknowledge)",
                },
            },
            required=["action"],
        ),
    ),
]


# =============================================================================
# Consolidated Platform Tools (6 → 4)
# Keep: stoa_platform_info, stoa_platform_health, stoa_list_tenants
# Consolidate: stoa_list_tools, stoa_get_tool_schema, stoa_search_tools → stoa_tools
# =============================================================================

CONSOLIDATED_PLATFORM_TOOLS: list[CoreTool] = [
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
        name="stoa_tools",
        description="""Tool discovery and schema retrieval for exploring available MCP tools.

Actions:
- list: List all available tools with optional filtering
- schema: Get the input schema for a specific tool (requires: tool_name)
- search: Search tools by name, description, or tags (requires: query)

Examples:
- {"action": "list", "category": "API Catalog", "include_proxied": true}
- {"action": "schema", "tool_name": "stoa_catalog"}
- {"action": "search", "query": "subscription", "limit": 10}
""",
        domain=ToolDomain.PLATFORM,
        action="tools",
        handler="platform.tools_dispatch",
        category="Platform & Discovery",
        tags=["platform", "tools", "discovery", "schema"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "action": {
                    "type": "string",
                    "enum": ["list", "schema", "search"],
                    "description": "Operation to perform",
                },
                "tool_name": {
                    "type": "string",
                    "description": "Tool name to get schema for (for: schema)",
                },
                "query": {
                    "type": "string",
                    "description": "Search query (for: search)",
                },
                "category": {
                    "type": "string",
                    "description": "Filter by category (for: list)",
                },
                "tag": {
                    "type": "string",
                    "description": "Filter by tag (for: list)",
                },
                "include_proxied": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include proxied tenant tools (for: list)",
                },
                "limit": {
                    "type": "integer",
                    "default": 20,
                    "description": "Maximum results (for: search)",
                },
            },
            required=["action"],
        ),
    ),
    CoreTool(
        name="stoa_tenants",
        description="List accessible tenants (admin only)",
        domain=ToolDomain.PLATFORM,
        action="tenants",
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
# Consolidated UAC Tool (4 → 1)
# =============================================================================

CONSOLIDATED_UAC_TOOLS: list[CoreTool] = [
    CoreTool(
        name="stoa_uac",
        description="""UAC (Usage and Access Control) contract management.

Actions:
- list: List UAC contracts with optional filters
- get: Get contract details (requires: contract_id)
- validate: Validate compliance with a contract (requires: contract_id)
- sla: Get SLA metrics for a contract (requires: contract_id)

Examples:
- {"action": "list", "api_id": "billing-api", "status": "active"}
- {"action": "get", "contract_id": "uac-123"}
- {"action": "validate", "contract_id": "uac-123", "subscription_id": "sub-456"}
- {"action": "sla", "contract_id": "uac-123", "time_range": "30d"}
""",
        domain=ToolDomain.UAC,
        action="uac",
        handler="uac.dispatch",
        category="UAC Contracts",
        tags=["uac", "contracts", "sla", "compliance"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "action": {
                    "type": "string",
                    "enum": ["list", "get", "validate", "sla"],
                    "description": "Operation to perform",
                },
                "contract_id": {
                    "type": "string",
                    "description": "Contract identifier (for: get, validate, sla)",
                },
                "api_id": {
                    "type": "string",
                    "description": "Filter by API (for: list)",
                },
                "subscription_id": {
                    "type": "string",
                    "description": "Subscription to check (for: validate)",
                },
                "status": {
                    "type": "string",
                    "enum": ["active", "expired", "pending"],
                    "description": "Filter by contract status (for: list)",
                },
                "time_range": {
                    "type": "string",
                    "enum": ["7d", "30d", "90d"],
                    "default": "30d",
                    "description": "Time range for SLA metrics (for: sla)",
                },
            },
            required=["action"],
        ),
    ),
]


# =============================================================================
# Consolidated Security Tool (3 → 1)
# =============================================================================

CONSOLIDATED_SECURITY_TOOLS: list[CoreTool] = [
    CoreTool(
        name="stoa_security",
        description="""Security and compliance operations for audit, permissions, and policies.

Actions:
- audit_log: Get security audit log entries
- check_permissions: Check user permissions for an API or action (requires: api_id, action_type)
- list_policies: List active security policies

Examples:
- {"action": "audit_log", "api_id": "billing-api", "time_range": "7d"}
- {"action": "check_permissions", "api_id": "billing-api", "action_type": "write"}
- {"action": "list_policies", "policy_type": "rate_limit"}
""",
        domain=ToolDomain.SECURITY,
        action="security",
        handler="security.dispatch",
        category="Security & Compliance",
        tags=["security", "audit", "permissions", "policies"],
        input_schema=ToolInputSchema(
            type="object",
            properties={
                "action": {
                    "type": "string",
                    "enum": ["audit_log", "check_permissions", "list_policies"],
                    "description": "Operation to perform",
                },
                "api_id": {
                    "type": "string",
                    "description": "API identifier (for: audit_log, check_permissions)",
                },
                "user_id": {
                    "type": "string",
                    "description": "User identifier (for: audit_log, check_permissions)",
                },
                "action_type": {
                    "type": "string",
                    "enum": ["read", "write", "admin"],
                    "description": "Action type to check (for: check_permissions)",
                },
                "policy_type": {
                    "type": "string",
                    "enum": ["rate_limit", "ip_whitelist", "oauth", "jwt"],
                    "description": "Policy type filter (for: list_policies)",
                },
                "time_range": {
                    "type": "string",
                    "enum": ["24h", "7d", "30d", "90d"],
                    "default": "7d",
                    "description": "Time range (for: audit_log)",
                },
                "limit": {
                    "type": "integer",
                    "default": 100,
                    "description": "Maximum entries (for: audit_log)",
                },
            },
            required=["action"],
        ),
    ),
]


# =============================================================================
# Aggregated Consolidated Tools
# =============================================================================

# All consolidated tools as a flat list
CONSOLIDATED_CORE_TOOLS: list[CoreTool] = (
    CONSOLIDATED_PLATFORM_TOOLS
    + CONSOLIDATED_CATALOG_TOOLS
    + CONSOLIDATED_SUBSCRIPTION_TOOLS
    + CONSOLIDATED_OBSERVABILITY_TOOLS
    + CONSOLIDATED_UAC_TOOLS
    + CONSOLIDATED_SECURITY_TOOLS
)

# Indexed by name for fast lookup
CONSOLIDATED_TOOLS_BY_NAME: dict[str, CoreTool] = {
    tool.name: tool for tool in CONSOLIDATED_CORE_TOOLS
}


# =============================================================================
# Deprecation Mappings
# Maps old tool names to (new_name, injected_args)
# =============================================================================

DEPRECATION_MAPPINGS: dict[str, tuple[str, dict]] = {
    # Catalog tools → stoa_catalog
    "stoa_catalog_list_apis": ("stoa_catalog", {"action": "list"}),
    "stoa_catalog_get_api": ("stoa_catalog", {"action": "get"}),
    "stoa_catalog_search_apis": ("stoa_catalog", {"action": "search"}),
    "stoa_catalog_list_versions": ("stoa_catalog", {"action": "versions"}),
    "stoa_catalog_list_categories": ("stoa_catalog", {"action": "categories"}),
    # Catalog tools → stoa_api_spec
    "stoa_catalog_get_openapi": ("stoa_api_spec", {"action": "openapi"}),
    "stoa_catalog_get_documentation": ("stoa_api_spec", {"action": "docs"}),
    "stoa_catalog_get_endpoints": ("stoa_api_spec", {"action": "endpoints"}),
    # Subscription tools → stoa_subscription
    "stoa_subscription_list": ("stoa_subscription", {"action": "list"}),
    "stoa_subscription_get": ("stoa_subscription", {"action": "get"}),
    "stoa_subscription_create": ("stoa_subscription", {"action": "create"}),
    "stoa_subscription_cancel": ("stoa_subscription", {"action": "cancel"}),
    "stoa_subscription_get_credentials": ("stoa_subscription", {"action": "credentials"}),
    "stoa_subscription_rotate_key": ("stoa_subscription", {"action": "rotate_key"}),
    # Observability tools → stoa_metrics
    "stoa_metrics_get_usage": ("stoa_metrics", {"action": "usage"}),
    "stoa_metrics_get_latency": ("stoa_metrics", {"action": "latency"}),
    "stoa_metrics_get_errors": ("stoa_metrics", {"action": "errors"}),
    "stoa_metrics_get_quota": ("stoa_metrics", {"action": "quota"}),
    # Observability tools → stoa_logs
    "stoa_logs_search": ("stoa_logs", {"action": "search"}),
    "stoa_logs_get_recent": ("stoa_logs", {"action": "recent"}),
    # Observability tools → stoa_alerts
    "stoa_alerts_list": ("stoa_alerts", {"action": "list"}),
    "stoa_alerts_acknowledge": ("stoa_alerts", {"action": "acknowledge"}),
    # Platform tools → stoa_tools
    "stoa_list_tools": ("stoa_tools", {"action": "list"}),
    "stoa_get_tool_schema": ("stoa_tools", {"action": "schema"}),
    "stoa_search_tools": ("stoa_tools", {"action": "search"}),
    # Platform tools → stoa_tenants (renamed)
    "stoa_list_tenants": ("stoa_tenants", {}),
    # UAC tools → stoa_uac
    "stoa_uac_list_contracts": ("stoa_uac", {"action": "list"}),
    "stoa_uac_get_contract": ("stoa_uac", {"action": "get"}),
    "stoa_uac_validate_contract": ("stoa_uac", {"action": "validate"}),
    "stoa_uac_get_sla": ("stoa_uac", {"action": "sla"}),
    # Security tools → stoa_security
    "stoa_security_audit_log": ("stoa_security", {"action": "audit_log"}),
    "stoa_security_check_permissions": ("stoa_security", {"action": "check_permissions"}),
    "stoa_security_list_policies": ("stoa_security", {"action": "list_policies"}),
}
