# STOA MCP Gateway - Tool Access Policy
# Package: stoa.tools
#
# This policy controls tool-specific access rules:
# - Tenant isolation for tool access
# - Rate limiting per role
# - Tool-specific restrictions

package stoa.tools

import future.keywords.if
import future.keywords.in

# =============================================================================
# Tenant Isolation
# =============================================================================

default allow_tool_access := false

# Global tools (no tenant) are accessible to all
allow_tool_access if {
    not input.tool.tenant_id
}

# Admin can access any tenant's tools
allow_tool_access if {
    "cpi-admin" in input.user.realm_access.roles
}

# User can access their own tenant's tools
allow_tool_access if {
    input.tool.tenant_id == input.user.tenant_id
}

# =============================================================================
# Rate Limiting (requests per minute)
# =============================================================================

rate_limit := limit if {
    "cpi-admin" in input.user.realm_access.roles
    limit := {"requests_per_minute": 1000, "burst": 100}
}

rate_limit := limit if {
    "tenant-admin" in input.user.realm_access.roles
    not "cpi-admin" in input.user.realm_access.roles
    limit := {"requests_per_minute": 500, "burst": 50}
}

rate_limit := limit if {
    "devops" in input.user.realm_access.roles
    not "tenant-admin" in input.user.realm_access.roles
    not "cpi-admin" in input.user.realm_access.roles
    limit := {"requests_per_minute": 200, "burst": 20}
}

rate_limit := limit if {
    "viewer" in input.user.realm_access.roles
    not "devops" in input.user.realm_access.roles
    not "tenant-admin" in input.user.realm_access.roles
    not "cpi-admin" in input.user.realm_access.roles
    limit := {"requests_per_minute": 60, "burst": 10}
}

# Default rate limit for unknown roles
rate_limit := {"requests_per_minute": 30, "burst": 5} if {
    not "cpi-admin" in input.user.realm_access.roles
    not "tenant-admin" in input.user.realm_access.roles
    not "devops" in input.user.realm_access.roles
    not "viewer" in input.user.realm_access.roles
}

# =============================================================================
# Tool-Specific Restrictions
# =============================================================================

# Sensitive operations require confirmation
requires_confirmation := true if {
    input.tool.name in {"stoa_delete_api", "stoa_delete_tool"}
}

requires_confirmation := false if {
    not input.tool.name in {"stoa_delete_api", "stoa_delete_tool"}
}

# Production environment restrictions
production_restricted := true if {
    input.environment == "prod"
    input.tool.name in {"stoa_delete_api", "stoa_delete_tool"}
    not "cpi-admin" in input.user.realm_access.roles
}

production_restricted := false if {
    not input.environment == "prod"
}

production_restricted := false if {
    input.environment == "prod"
    "cpi-admin" in input.user.realm_access.roles
}
