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
#   "tenant_id": "tenant-acme",
#   "tool_name": "stoa_catalog",
#   "action": "Read",
#   "scopes": ["stoa:read", "stoa:write"],
#   "roles": ["tenant-admin"]
# }

package stoa.authz

import future.keywords.if
import future.keywords.in

# ─── Default Deny ─────────────────────────────────────

default allow := false

# ─── Admin Access ─────────────────────────────────────

# Admin scope grants full access
allow if {
    "stoa:admin" in input.scopes
}

# cpi-admin role grants full access (backwards compatibility with Keycloak roles)
allow if {
    "cpi-admin" in input.roles
}

# tenant-admin role with stoa:write scope grants write access for their tenant
allow if {
    "tenant-admin" in input.roles
    "stoa:write" in input.scopes
}

# ─── Read Operations ──────────────────────────────────

# Read actions allowed with stoa:read scope
allow if {
    action_is_read
    "stoa:read" in input.scopes
}

# ─── Write Operations ─────────────────────────────────

# Write actions allowed with stoa:write scope
allow if {
    action_is_write
    "stoa:write" in input.scopes
}

# ─── Tool Execution ───────────────────────────────────

# Tool execution allowed with stoa:execute scope
allow if {
    action_is_execute
    "stoa:execute" in input.scopes
}

# Tool execution also allowed with stoa:read for read-only tools
allow if {
    action_is_execute
    action_is_read
    "stoa:read" in input.scopes
}

# ─── View Operations ──────────────────────────────────

# Metrics/logs viewing allowed with stoa:read or stoa:audit
allow if {
    action_is_view
    scope_allows_view
}

# ─── Deploy Operations ────────────────────────────────

# Deployment actions allowed with stoa:deploy
allow if {
    action_is_deploy
    "stoa:deploy" in input.scopes
}

# DevOps role with stoa:deploy scope
allow if {
    "devops" in input.roles
    "stoa:deploy" in input.scopes
}

# ─── Audit Operations ─────────────────────────────────

# Audit actions allowed with stoa:audit
allow if {
    action_is_audit
    "stoa:audit" in input.scopes
}

# ═══════════════════════════════════════════════════════
# Action Categories
# ═══════════════════════════════════════════════════════

action_is_read if {
    input.action in ["Read", "List", "Search"]
}

action_is_write if {
    input.action in [
        "Create", "Update", "Delete",
        "CreateApi", "UpdateApi", "DeleteApi",
        "PublishApi", "DeprecateApi"
    ]
}

action_is_execute if {
    input.action in [
        "Read", "List", "Search",
        "Subscribe", "Unsubscribe", "ManageSubscription"
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

denial_reason := reason if {
    not allow
    action_is_write
    not "stoa:write" in input.scopes
    reason := "Write operations require 'stoa:write' scope"
}

denial_reason := reason if {
    not allow
    action_is_admin
    not "stoa:admin" in input.scopes
    reason := "Admin operations require 'stoa:admin' scope"
}

denial_reason := reason if {
    not allow
    action_is_deploy
    not "stoa:deploy" in input.scopes
    reason := "Deploy operations require 'stoa:deploy' scope"
}

denial_reason := reason if {
    not allow
    action_is_audit
    not "stoa:audit" in input.scopes
    reason := "Audit operations require 'stoa:audit' scope"
}

denial_reason := reason if {
    not allow
    reason := sprintf("Action '%s' not permitted for scopes %v", [input.action, input.scopes])
}
