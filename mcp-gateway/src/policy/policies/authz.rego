# STOA MCP Gateway - Authorization Policy
# Package: stoa.authz
#
# This policy controls access to MCP tools based on:
# - User scopes (stoa:admin, stoa:write, stoa:read)
# - User roles (cpi-admin, tenant-admin, devops, viewer)
# - Tenant isolation

package stoa.authz

import future.keywords.if
import future.keywords.in

default allow := false

# =============================================================================
# Tool Classifications
# =============================================================================

# Read-only tools - require stoa:read scope
read_only_tools := {
    "stoa_platform_info",
    "stoa_list_apis",
    "stoa_list_tools",
    "stoa_health_check",
    "stoa_search_apis",
    "stoa_get_tool_schema",
    "stoa_get_api_details",
}

# Write tools - require stoa:write scope
write_tools := {
    "stoa_create_api",
    "stoa_update_api",
    "stoa_deploy_api",
}

# Destructive tools - require stoa:admin scope
admin_tools := {
    "stoa_delete_api",
    "stoa_delete_tool",
}

# =============================================================================
# Role to Scope Mapping
# =============================================================================

role_scopes := {
    "cpi-admin": {"stoa:admin", "stoa:write", "stoa:read"},
    "tenant-admin": {"stoa:write", "stoa:read"},
    "devops": {"stoa:write", "stoa:read"},
    "viewer": {"stoa:read"},
}

# =============================================================================
# Helper Functions
# =============================================================================

# Extract scopes from user claims
user_scopes[scope] {
    # From explicit scope claim
    scope := split(input.user.scope, " ")[_]
}

user_scopes[scope] {
    # From role mapping
    some role in input.user.realm_access.roles
    scope := role_scopes[role][_]
}

user_scopes[scope] {
    # From roles array
    some role in input.user.roles
    scope := role_scopes[role][_]
}

# Check if user has a specific scope
has_scope(s) if s in user_scopes

# =============================================================================
# Authorization Rules
# =============================================================================

# Admin can do everything
allow if {
    has_scope("stoa:admin")
}

# Read-only tools with read scope
allow if {
    input.tool.name in read_only_tools
    has_scope("stoa:read")
    tenant_allowed
}

# Write tools with write scope
allow if {
    input.tool.name in write_tools
    has_scope("stoa:write")
    tenant_allowed
}

# Dynamic/unknown tools - allow with read scope
# This allows API-backed tools registered at runtime
allow if {
    not input.tool.name in read_only_tools
    not input.tool.name in write_tools
    not input.tool.name in admin_tools
    has_scope("stoa:read")
    tenant_allowed
}

# =============================================================================
# Tenant Isolation
# =============================================================================

# Global tools (no tenant_id) are accessible to all
tenant_allowed if {
    not input.tool.tenant_id
}

# Admin bypass tenant isolation
tenant_allowed if {
    has_scope("stoa:admin")
}

# Tenant must match
tenant_allowed if {
    input.user.tenant_id == input.tool.tenant_id
}

# =============================================================================
# Denial Reasons (for debugging)
# =============================================================================

denial_reason := reason if {
    not allow
    input.tool.name in admin_tools
    not has_scope("stoa:admin")
    reason := sprintf("Tool %s requires admin scope", [input.tool.name])
}

denial_reason := reason if {
    not allow
    input.tool.name in write_tools
    not has_scope("stoa:write")
    reason := sprintf("Tool %s requires write scope", [input.tool.name])
}

denial_reason := reason if {
    not allow
    not has_scope("stoa:read")
    reason := "No valid scope for tool access"
}

denial_reason := reason if {
    not allow
    not tenant_allowed
    reason := sprintf("Tenant mismatch: user=%s, tool=%s", [input.user.tenant_id, input.tool.tenant_id])
}
