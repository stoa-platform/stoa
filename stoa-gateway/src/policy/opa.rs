//! OPA Policy Engine
//!
//! Pure-Rust OPA evaluator using `regorus` crate.
//! Evaluates Rego policies for scope-based access control.
#![allow(dead_code)]

use parking_lot::RwLock;
use regorus::{Engine, Value};
use serde::{Deserialize, Serialize};
use std::path::Path;
use std::sync::Arc;
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
    /// Owning tenant from the trusted tool registry; None means global.
    pub resource_tenant_id: Option<String>,
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
            resource_tenant_id: None,
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
        // Missing caller tenant is always denied, including development mode.
        if input.tenant_id.trim().is_empty() || input.tenant_id.trim() != input.tenant_id {
            return PolicyDecision::Deny {
                reason: "Missing or invalid tenant context".to_string(),
            };
        }

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
        if let Ok(Value::String(s)) = engine.eval_rule("data.stoa.authz.denial_reason".to_string())
        {
            return s.to_string();
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
const DEFAULT_POLICY: &str = include_str!("../../policies/default.rego");

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
            tenant_id: "acme".to_string(),
            resource_tenant_id: Some("acme".to_string()),
            tool_name: "stoa_catalog".to_string(),
            action: format!("{:?}", action),
            scopes: scopes.iter().map(|s| s.to_string()).collect(),
            roles: roles.iter().map(|s| s.to_string()).collect(),
        }
    }

    #[test]
    fn test_missing_tenant_denied_even_when_disabled_or_admin() {
        for enabled in [true, false] {
            let engine = PolicyEngine::new(PolicyEngineConfig {
                enabled,
                ..Default::default()
            })
            .unwrap();
            let mut input = make_input(Action::Read, vec!["stoa:admin"], vec!["cpi-admin"]);
            for tenant in ["", " ", " acme "] {
                input.tenant_id = tenant.to_string();
                assert!(!engine.evaluate(&input).is_allowed());
            }
        }
    }

    #[test]
    fn test_resource_tenant_is_checked() {
        let engine = make_engine();
        let mut input = make_input(Action::Read, vec!["stoa:read"], vec![]);
        input.resource_tenant_id = Some("beta".to_string());
        assert!(!engine.evaluate(&input).is_allowed());
        input.resource_tenant_id = Some("tenant-acme".to_string());
        assert!(!engine.evaluate(&input).is_allowed());
        input.resource_tenant_id = None;
        assert!(engine.evaluate(&input).is_allowed());
    }

    #[test]
    fn test_read_only_roles_follow_action_and_owner_matrix() {
        let engine = make_engine();
        for role in ["viewer", "read-only", "readonly"] {
            for owner in [Some("acme"), Some("beta"), None] {
                for action in [
                    Action::Read,
                    Action::List,
                    Action::Search,
                    Action::Create,
                    Action::Update,
                    Action::Delete,
                    Action::CreateApi,
                    Action::UpdateApi,
                    Action::DeleteApi,
                    Action::PublishApi,
                    Action::DeprecateApi,
                    Action::Subscribe,
                    Action::Unsubscribe,
                    Action::ManageSubscription,
                    Action::ManageUsers,
                    Action::ManageTenants,
                    Action::ManageContracts,
                    Action::ViewMetrics,
                    Action::ViewLogs,
                    Action::ViewAudit,
                ] {
                    let mut input = make_input(action, vec!["stoa:read"], vec![role]);
                    input.resource_tenant_id = owner.map(str::to_string);
                    let expected = owner != Some("beta")
                        && matches!(
                            action,
                            Action::Read
                                | Action::List
                                | Action::Search
                                | Action::ViewMetrics
                                | Action::ViewLogs
                        );
                    assert_eq!(
                        engine.evaluate(&input).is_allowed(),
                        expected,
                        "role={role}, owner={owner:?}, action={action:?}"
                    );
                    input.tenant_id.clear();
                    assert!(!engine.evaluate(&input).is_allowed());
                }
            }
        }
    }

    #[test]
    fn test_platform_admin_requires_known_action() {
        let engine = make_engine();
        for (scopes, roles) in [(vec!["stoa:admin"], vec!["cpi-admin"])] {
            let mut input = make_input(Action::ManageTenants, scopes, roles);
            input.resource_tenant_id = Some("beta".to_string());
            assert!(engine.evaluate(&input).is_allowed());
            for action in ["", "UnknownAction"] {
                input.action = action.to_string();
                assert!(!engine.evaluate(&input).is_allowed());
            }
        }
    }

    #[test]
    fn test_denial_reason_precedence() {
        let engine = make_engine();
        let mut input = make_input(Action::Read, vec!["stoa:read"], vec!["viewer"]);
        for (tenant, owner, expected) in [
            ("", "", "Missing or invalid tenant context"),
            ("acme", " beta ", "Missing or invalid resource tenant"),
            ("acme", "beta", "Cross-tenant access denied"),
        ] {
            input.tenant_id = tenant.to_string();
            input.resource_tenant_id = Some(owner.to_string());
            match engine.evaluate(&input) {
                PolicyDecision::Deny { reason } => assert_eq!(reason, expected),
                PolicyDecision::Allow => {
                    panic!("expected denial for tenant={tenant}, owner={owner}")
                }
            }
        }
    }

    #[test]
    fn test_admin_scope_without_role_denied() {
        let engine = make_engine();
        let input = make_input(Action::ManageTenants, vec!["stoa:admin"], vec![]);
        let decision = engine.evaluate(&input);
        assert!(!decision.is_allowed());
    }

    #[test]
    fn test_cpi_admin_without_scope_denied() {
        let engine = make_engine();
        let input = make_input(Action::ManageTenants, vec![], vec!["cpi-admin"]);
        let decision = engine.evaluate(&input);
        assert!(!decision.is_allowed());
    }

    #[test]
    fn regression_privileged_admin_conjunction() {
        let engine = make_engine();
        let mut input = make_input(Action::ManageTenants, vec!["stoa:admin"], vec!["cpi-admin"]);
        assert!(engine.evaluate(&input).is_allowed());
        for tenant in ["", " ", " alpha "] {
            input.tenant_id = tenant.to_string();
            assert!(!engine.evaluate(&input).is_allowed());
        }
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
