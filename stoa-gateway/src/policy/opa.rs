//! OPA Policy Engine
//!
//! Pure-Rust OPA evaluator using `regorus` crate.
//! Evaluates Rego policies for scope-based access control.

use regorus::{Engine, Value};
use serde::{Deserialize, Serialize};
use std::path::Path;
use std::sync::Arc;
use parking_lot::RwLock;
use tracing::{debug, error, info, warn};

use crate::uac::Action;

// ============================================
// Configuration
// ============================================

/// Policy engine configuration
#[derive(Debug, Clone)]
pub struct PolicyEngineConfig {
    /// Path to Rego policy files (e.g., "/etc/stoa/policies")
    pub policy_path: Option<String>,
    /// Default policy (inline Rego) if no file path
    pub default_policy: String,
    /// Whether to enable policy enforcement (false = allow all)
    pub enabled: bool,
}

impl Default for PolicyEngineConfig {
    fn default() -> Self {
        Self {
            policy_path: None,
            default_policy: DEFAULT_POLICY.to_string(),
            enabled: true,
        }
    }
}

// ============================================
// Policy Input/Output
// ============================================

/// Input to policy evaluation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PolicyInput {
    /// User identifier
    pub user_id: Option<String>,
    /// User email
    pub user_email: Option<String>,
    /// Tenant identifier
    pub tenant_id: String,
    /// Tool being invoked
    pub tool_name: String,
    /// Action required by the tool
    pub action: String,
    /// OAuth scopes from JWT
    pub scopes: Vec<String>,
    /// User roles from JWT
    pub roles: Vec<String>,
}

impl PolicyInput {
    /// Create a new policy input
    pub fn new(
        user_id: Option<String>,
        user_email: Option<String>,
        tenant_id: String,
        tool_name: String,
        action: Action,
        scopes: Vec<String>,
        roles: Vec<String>,
    ) -> Self {
        Self {
            user_id,
            user_email,
            tenant_id,
            tool_name,
            action: format!("{:?}", action),
            scopes,
            roles,
        }
    }
}

/// Result of policy evaluation
#[derive(Debug, Clone)]
pub enum PolicyDecision {
    /// Access allowed
    Allow,
    /// Access denied with reason
    Deny { reason: String },
}

impl PolicyDecision {
    pub fn is_allowed(&self) -> bool {
        matches!(self, PolicyDecision::Allow)
    }
}

// ============================================
// Policy Engine
// ============================================

/// OPA Policy Engine using regorus
pub struct PolicyEngine {
    /// Rego engine instance
    engine: Arc<RwLock<Engine>>,
    /// Configuration
    config: PolicyEngineConfig,
}

impl PolicyEngine {
    /// Create a new policy engine with configuration
    pub fn new(config: PolicyEngineConfig) -> Result<Self, String> {
        let mut engine = Engine::new();

        // Load policy from file or default
        let policy_source = if let Some(ref path) = config.policy_path {
            if Path::new(path).exists() {
                info!(path = %path, "Loading Rego policies from file");
                std::fs::read_to_string(path)
                    .map_err(|e| format!("Failed to read policy file: {}", e))?
            } else {
                warn!(path = %path, "Policy file not found, using default policy");
                config.default_policy.clone()
            }
        } else {
            debug!("Using default inline policy");
            config.default_policy.clone()
        };

        // Add policy to engine
        engine
            .add_policy("stoa".to_string(), policy_source)
            .map_err(|e| format!("Failed to add policy: {}", e))?;

        info!("OPA policy engine initialized");

        Ok(Self {
            engine: Arc::new(RwLock::new(engine)),
            config,
        })
    }

    /// Create with default configuration
    pub fn default_config() -> Result<Self, String> {
        Self::new(PolicyEngineConfig::default())
    }

    /// Evaluate policy for a given input
    pub fn evaluate(&self, input: &PolicyInput) -> PolicyDecision {
        // If disabled, allow all
        if !self.config.enabled {
            debug!("Policy engine disabled — allowing access");
            return PolicyDecision::Allow;
        }

        // Convert input to regorus Value
        let input_json = match serde_json::to_string(input) {
            Ok(j) => j,
            Err(e) => {
                error!(error = %e, "Failed to serialize policy input");
                return PolicyDecision::Deny {
                    reason: "Internal error: failed to serialize policy input".to_string(),
                };
            }
        };

        let input_value = match Value::from_json_str(&input_json) {
            Ok(v) => v,
            Err(e) => {
                error!(error = %e, "Failed to parse policy input as Value");
                return PolicyDecision::Deny {
                    reason: "Internal error: failed to parse policy input".to_string(),
                };
            }
        };

        // Set input and evaluate
        let mut engine = self.engine.write();
        engine.set_input(input_value);

        // Evaluate the allow rule
        let result = engine.eval_rule("data.stoa.authz.allow".to_string());

        match result {
            Ok(value) => {
                // Check if allow is true
                let allowed = matches!(value, Value::Bool(true));

                if allowed {
                    debug!(
                        user = ?input.user_id,
                        tool = %input.tool_name,
                        action = %input.action,
                        "Policy evaluation: ALLOW"
                    );
                    PolicyDecision::Allow
                } else {
                    // Try to get denial reason
                    let reason = self.get_denial_reason(&mut engine, input);
                    debug!(
                        user = ?input.user_id,
                        tool = %input.tool_name,
                        action = %input.action,
                        reason = %reason,
                        "Policy evaluation: DENY"
                    );
                    PolicyDecision::Deny { reason }
                }
            }
            Err(e) => {
                error!(error = %e, "Policy evaluation failed");
                PolicyDecision::Deny {
                    reason: format!("Policy evaluation error: {}", e),
                }
            }
        }
    }

    /// Get denial reason from policy
    fn get_denial_reason(&self, engine: &mut Engine, input: &PolicyInput) -> String {
        // Try to evaluate a denial_reason rule if it exists
        if let Ok(value) = engine.eval_rule("data.stoa.authz.denial_reason".to_string()) {
            if let Value::String(s) = value {
                return s.to_string();
            }
        }

        // Default reason based on action and scopes
        format!(
            "Action '{}' not permitted for user. Required scope not present. Available scopes: {:?}",
            input.action, input.scopes
        )
    }

    /// Reload policies from file (hot-reload)
    pub fn reload(&self) -> Result<(), String> {
        if let Some(ref path) = self.config.policy_path {
            if Path::new(path).exists() {
                let policy_source = std::fs::read_to_string(path)
                    .map_err(|e| format!("Failed to read policy file: {}", e))?;

                let mut engine = self.engine.write();
                // Clear and reload
                *engine = Engine::new();
                engine
                    .add_policy("stoa".to_string(), policy_source)
                    .map_err(|e| format!("Failed to reload policy: {}", e))?;

                info!(path = %path, "Policies reloaded successfully");
                Ok(())
            } else {
                Err(format!("Policy file not found: {}", path))
            }
        } else {
            Ok(()) // No file path, nothing to reload
        }
    }

    /// Check if engine is enabled
    pub fn is_enabled(&self) -> bool {
        self.config.enabled
    }
}

// ============================================
// Default Policy
// ============================================

/// Default Rego policy for STOA scope-based access control
///
/// Scopes follow ADR-012 12-Scope Model:
/// - stoa:read     — Read operations (list, get, view metrics)
/// - stoa:write    — Write operations (create, update, delete APIs)
/// - stoa:admin    — Admin operations (manage tenants, users, config)
/// - stoa:execute  — Tool execution (invoke MCP tools)
/// - stoa:deploy   — Deployment operations (promote, manage versions)
/// - stoa:audit    — Audit operations (view audit log, export metrics)
const DEFAULT_POLICY: &str = r#"
package stoa.authz

import future.keywords.if
import future.keywords.in

# Default deny
default allow := false

# Admin scope grants full access
allow if {
    "stoa:admin" in input.scopes
}

# cpi-admin role grants full access (backwards compatibility)
allow if {
    "cpi-admin" in input.roles
}

# Read actions allowed with stoa:read scope
allow if {
    action_is_read
    "stoa:read" in input.scopes
}

# Write actions allowed with stoa:write scope
allow if {
    action_is_write
    "stoa:write" in input.scopes
}

# Execute actions (tool invocation) allowed with stoa:execute or stoa:read
allow if {
    action_is_execute
    scope_allows_execute
}

# Metrics/logs viewing allowed with stoa:read or stoa:audit
allow if {
    action_is_view
    scope_allows_view
}

# Deployment actions allowed with stoa:deploy
allow if {
    action_is_deploy
    "stoa:deploy" in input.scopes
}

# Audit actions allowed with stoa:audit
allow if {
    action_is_audit
    "stoa:audit" in input.scopes
}

# ─── Action Categories ────────────────────────────────

action_is_read if {
    input.action in ["Read", "List", "Search"]
}

action_is_write if {
    input.action in ["Create", "Update", "Delete", "CreateApi", "UpdateApi", "DeleteApi", "PublishApi", "DeprecateApi"]
}

action_is_execute if {
    input.action in ["Read", "List", "Search", "Subscribe", "Unsubscribe", "ManageSubscription"]
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

# ─── Scope Helpers ────────────────────────────────────

scope_allows_execute if {
    "stoa:execute" in input.scopes
}

scope_allows_execute if {
    "stoa:read" in input.scopes
}

scope_allows_view if {
    "stoa:read" in input.scopes
}

scope_allows_view if {
    "stoa:audit" in input.scopes
}

# ─── Denial Reason ────────────────────────────────────

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
    reason := sprintf("Action '%s' not permitted. Check your scopes.", [input.action])
}

action_is_admin if {
    input.action in ["ManageUsers", "ManageTenants", "ManageContracts"]
}
"#;

// ============================================
// Tests
// ============================================

#[cfg(test)]
mod tests {
    use super::*;

    fn make_engine() -> PolicyEngine {
        PolicyEngine::new(PolicyEngineConfig::default()).unwrap()
    }

    fn make_input(action: Action, scopes: Vec<&str>, roles: Vec<&str>) -> PolicyInput {
        PolicyInput {
            user_id: Some("user-123".to_string()),
            user_email: Some("user@test.com".to_string()),
            tenant_id: "tenant-acme".to_string(),
            tool_name: "stoa_catalog".to_string(),
            action: format!("{:?}", action),
            scopes: scopes.iter().map(|s| s.to_string()).collect(),
            roles: roles.iter().map(|s| s.to_string()).collect(),
        }
    }

    #[test]
    fn test_admin_scope_allows_all() {
        let engine = make_engine();
        let input = make_input(Action::ManageTenants, vec!["stoa:admin"], vec![]);
        let decision = engine.evaluate(&input);
        assert!(decision.is_allowed());
    }

    #[test]
    fn test_cpi_admin_role_allows_all() {
        let engine = make_engine();
        let input = make_input(Action::ManageTenants, vec![], vec!["cpi-admin"]);
        let decision = engine.evaluate(&input);
        assert!(decision.is_allowed());
    }

    #[test]
    fn test_read_scope_allows_read() {
        let engine = make_engine();
        let input = make_input(Action::Read, vec!["stoa:read"], vec![]);
        let decision = engine.evaluate(&input);
        assert!(decision.is_allowed());
    }

    #[test]
    fn test_read_scope_denies_write() {
        let engine = make_engine();
        let input = make_input(Action::CreateApi, vec!["stoa:read"], vec![]);
        let decision = engine.evaluate(&input);
        assert!(!decision.is_allowed());
    }

    #[test]
    fn test_write_scope_allows_create() {
        let engine = make_engine();
        let input = make_input(Action::CreateApi, vec!["stoa:write"], vec![]);
        let decision = engine.evaluate(&input);
        assert!(decision.is_allowed());
    }

    #[test]
    fn test_no_scopes_denied() {
        let engine = make_engine();
        let input = make_input(Action::Read, vec![], vec![]);
        let decision = engine.evaluate(&input);
        assert!(!decision.is_allowed());
    }

    #[test]
    fn test_disabled_engine_allows_all() {
        let config = PolicyEngineConfig {
            enabled: false,
            ..Default::default()
        };
        let engine = PolicyEngine::new(config).unwrap();
        let input = make_input(Action::ManageTenants, vec![], vec![]);
        let decision = engine.evaluate(&input);
        assert!(decision.is_allowed());
    }

    #[test]
    fn test_view_metrics_with_read_scope() {
        let engine = make_engine();
        let input = make_input(Action::ViewMetrics, vec!["stoa:read"], vec![]);
        let decision = engine.evaluate(&input);
        assert!(decision.is_allowed());
    }

    #[test]
    fn test_view_audit_requires_audit_scope() {
        let engine = make_engine();
        let input = make_input(Action::ViewAudit, vec!["stoa:read"], vec![]);
        let decision = engine.evaluate(&input);
        // stoa:read doesn't include ViewAudit
        assert!(!decision.is_allowed());

        let input = make_input(Action::ViewAudit, vec!["stoa:audit"], vec![]);
        let decision = engine.evaluate(&input);
        assert!(decision.is_allowed());
    }
}
