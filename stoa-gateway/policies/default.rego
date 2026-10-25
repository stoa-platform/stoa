# STOA Gateway Authorization Policy
#
# CAB-1094 Phase 2: Scope-based access control
#
# Scopes follow ADR-012 12-Scope Model:
#   - stoa:read     — Read operations (list, get, view metrics)
#   - stoa:write    — Write operations (create, update, delete APIs)
#   - stoa:admin    — Admin operations (manage tenants, users, config)
#   - stoa:execute  — Tool execution (invoke MCP tools)
#   - stoa:deploy   — Deployment operations (promote, manage versions)
#   - stoa:audit    — Audit operations (view audit log, export metrics)
#
# Input format:
# {
#   "user_id": "user-123",
#   "user_email": "user@example.com",
#   "tenant_id": "acme",
#   "resource_tenant_id": "acme",
#   "tool_name": "stoa_catalog",
#   "action": "Read",
#   "scopes": ["stoa:read", "stoa:write"],
#   "roles": ["tenant-admin"]
# }

# tenant_id comes only from a verified JWT. resource_tenant_id comes from the
# tool registry, never request arguments; explicit null denotes a global tool.
# IDs are opaque: do not strip "tenant-" from either identifier.
package stoa.authz

import future.keywords.if
import future.keywords.in

# ─── Default Deny ─────────────────────────────────────

default allow := false

# Every authorization branch, including platform admins, requires tenant context.
tenant_present if {
	is_string(input.tenant_id)
	input.tenant_id != ""
	input.tenant_id == trim_space(input.tenant_id)
}

target_valid if {
	input.resource_tenant_id == null
}

target_valid if {
	is_string(input.resource_tenant_id)
	input.resource_tenant_id != ""
	input.resource_tenant_id == trim_space(input.resource_tenant_id)
}

platform_admin if {
	"stoa:admin" in input.scopes
	"cpi-admin" in input.roles
}

tenant_access if {
	tenant_present
	target_valid
	input.resource_tenant_id == null
}

tenant_access if {
	tenant_present
	target_valid
	input.tenant_id == input.resource_tenant_id
}

# Explicit platform administration requires valid tenant context.
tenant_access if {
	tenant_present
	target_valid
	platform_admin
}

# ─── Admin Access ─────────────────────────────────────

# Administrative authority requires both scope and role; tenant_access
# retains the existing isolation patch's tenant and resource-owner guards.
allow if {
	tenant_access
	action_known
	platform_admin
}

# ─── Read Operations ──────────────────────────────────

# Read actions allowed with stoa:read scope
allow if {
	tenant_access
	action_is_read
	"stoa:read" in input.scopes
}

# ─── Write Operations ─────────────────────────────────

# Write actions allowed with stoa:write scope
allow if {
	tenant_access
	action_is_write
	"stoa:write" in input.scopes
}

# ─── Tool Execution ───────────────────────────────────

# Tool execution allowed with stoa:execute scope
allow if {
	tenant_access
	action_is_execute
	"stoa:execute" in input.scopes
}

# Tool execution also allowed with stoa:read for read-only tools
allow if {
	tenant_access
	action_is_execute
	action_is_read
	"stoa:read" in input.scopes
}

# ─── View Operations ──────────────────────────────────

# Metrics/logs viewing allowed with stoa:read or stoa:audit
allow if {
	tenant_access
	action_is_view
	scope_allows_view
}

# ─── Deploy Operations ────────────────────────────────

# Deployment actions allowed with stoa:deploy
allow if {
	tenant_access
	action_is_deploy
	"stoa:deploy" in input.scopes
}

# ─── Audit Operations ─────────────────────────────────

# Audit actions allowed with stoa:audit
allow if {
	tenant_access
	action_is_audit
	"stoa:audit" in input.scopes
}

# ═══════════════════════════════════════════════════════
# Action Categories
# ═══════════════════════════════════════════════════════

# Reject missing/unknown operations even for platform administrators.
action_known if {
	input.action in [
		"Read", "List", "Search", "Create", "Update", "Delete",
		"CreateApi", "UpdateApi", "DeleteApi", "PublishApi", "DeprecateApi",
		"Subscribe", "Unsubscribe", "ManageSubscription",
		"ManageUsers", "ManageTenants", "ManageContracts",
		"ViewMetrics", "ViewLogs", "ViewAudit",
	]
}

action_is_read if {
	input.action in ["Read", "List", "Search"]
}

action_is_write if {
	input.action in [
		"Create", "Update", "Delete",
		"CreateApi", "UpdateApi", "DeleteApi",
		"PublishApi", "DeprecateApi",
	]
}

action_is_execute if {
	input.action in [
		"Read", "List", "Search",
		"Subscribe", "Unsubscribe", "ManageSubscription",
	]
}

action_is_view if {
	input.action in ["ViewMetrics", "ViewLogs"]
}

action_is_deploy if {
	input.action in ["PublishApi", "DeprecateApi"]
}

action_is_audit if {
	input.action in ["ViewAudit"]
}

action_is_admin if {
	input.action in ["ManageUsers", "ManageTenants", "ManageContracts"]
}

# ═══════════════════════════════════════════════════════
# Scope Helpers
# ═══════════════════════════════════════════════════════

scope_allows_view if {
	"stoa:read" in input.scopes
}

scope_allows_view if {
	"stoa:audit" in input.scopes
}

# ═══════════════════════════════════════════════════════
# Denial Reasons (for debugging/logging)
# ═══════════════════════════════════════════════════════

# Ordered branches avoid conflicting complete-rule outputs on a denial.
denial_reason := "Missing or invalid tenant context" if {
	not tenant_present
} else := "Missing or invalid resource tenant" if {
	not target_valid
} else := "Cross-tenant access denied" if {
	not tenant_access
} else := reason if {
	not allow
	reason := sprintf("Action '%s' not permitted for scopes %v", [input.action, input.scopes])
}
