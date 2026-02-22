//! GuardrailPolicy Store — CAB-1337 Phase 3
//!
//! Per-tenant guardrail configuration loaded from `GuardrailPolicy` CRDs.
//! Falls back to global config when no tenant-specific policy exists.
//!
//! Architecture:
//! - `GuardrailPolicyStore` holds an in-memory map keyed by tenant_id
//! - Populated by the K8s CRD watcher (k8s feature) or can be empty
//! - Empty store = all tenants use global config (graceful fallback)
//! - `resolve()` merges global defaults with tenant overrides (tenant wins)
//!
//! Thread safety: uses `parking_lot::RwLock<HashMap>` — consistent with the
//! existing `PolicyEngine` in `policy/opa.rs`.

use parking_lot::RwLock;
use std::collections::HashMap;

use crate::guardrails::GuardrailsConfig;

// ============================================================================
// Per-tenant policy (loaded from GuardrailPolicy CRD)
// ============================================================================

/// Tenant-scoped guardrail overrides.
///
/// All fields are optional: `None` means "inherit from global config".
#[derive(Debug, Clone, Default)]
pub struct TenantGuardrailPolicy {
    /// Override PII scanning enable
    pub pii_enabled: Option<bool>,
    /// Override PII redact mode (true = redact, false = reject)
    pub pii_redact: Option<bool>,
    /// Override prompt injection scanning
    pub injection_enabled: Option<bool>,
    /// Override content filtering
    pub content_filter_enabled: Option<bool>,
    /// Per-tenant token budget limit in tokens/window (0 = use global default)
    pub token_budget_limit: Option<u64>,
    /// Additional regex patterns added on top of global blocked rules
    pub extra_blocked_patterns: Vec<String>,
    /// Restrict to specific tools (None = all tools allowed)
    pub allowed_tools: Option<Vec<String>>,
}

// ============================================================================
// Policy Store
// ============================================================================

/// Thread-safe store for per-tenant guardrail policies.
///
/// Always available (no `k8s` feature required). Starts empty and is populated
/// by the K8s CRD watcher when the `k8s` feature is enabled.
#[derive(Default)]
pub struct GuardrailPolicyStore {
    policies: RwLock<HashMap<String, TenantGuardrailPolicy>>,
}

impl GuardrailPolicyStore {
    pub fn new() -> Self {
        Default::default()
    }

    /// Upsert a tenant policy (called by K8s CRD watcher on Apply events).
    pub fn upsert(&self, tenant_id: String, policy: TenantGuardrailPolicy) {
        self.policies.write().insert(tenant_id, policy);
    }

    /// Remove a tenant policy (called by K8s CRD watcher on Delete events).
    /// Returns `true` if a policy was removed.
    pub fn remove(&self, tenant_id: &str) -> bool {
        self.policies.write().remove(tenant_id).is_some()
    }

    /// Return the number of active tenant policies.
    pub fn count(&self) -> usize {
        self.policies.read().len()
    }

    /// Resolve `GuardrailsConfig` for a tenant.
    ///
    /// Tenant overrides take precedence; absent overrides fall back to `global`.
    pub fn resolve(&self, tenant_id: &str, global: &GuardrailsConfig) -> GuardrailsConfig {
        let guard = self.policies.read();
        match guard.get(tenant_id) {
            None => GuardrailsConfig {
                pii_enabled: global.pii_enabled,
                pii_redact: global.pii_redact,
                injection_enabled: global.injection_enabled,
                content_filter_enabled: global.content_filter_enabled,
            },
            Some(t) => GuardrailsConfig {
                pii_enabled: t.pii_enabled.unwrap_or(global.pii_enabled),
                pii_redact: t.pii_redact.unwrap_or(global.pii_redact),
                injection_enabled: t.injection_enabled.unwrap_or(global.injection_enabled),
                content_filter_enabled: t
                    .content_filter_enabled
                    .unwrap_or(global.content_filter_enabled),
            },
        }
    }

    /// Resolve the token budget limit for a tenant.
    ///
    /// Returns the tenant override if set, otherwise falls back to `global_default`.
    pub fn token_budget_limit(&self, tenant_id: &str, global_default: u64) -> u64 {
        self.policies
            .read()
            .get(tenant_id)
            .and_then(|t| t.token_budget_limit)
            .filter(|&v| v > 0)
            .unwrap_or(global_default)
    }

    /// Check whether a tool is allowed for a tenant.
    ///
    /// Returns `true` when:
    /// - No tenant policy exists (no restriction)
    /// - Policy exists but `allowed_tools` is `None` (no restriction)
    /// - Policy exists, `allowed_tools` is `Some`, and the tool is in the list
    pub fn is_tool_allowed(&self, tenant_id: &str, tool_name: &str) -> bool {
        let guard = self.policies.read();
        match guard.get(tenant_id) {
            None => true,
            Some(t) => match &t.allowed_tools {
                None => true,
                Some(tools) => tools.iter().any(|t| t == tool_name),
            },
        }
    }
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    fn global() -> GuardrailsConfig {
        GuardrailsConfig {
            pii_enabled: false,
            pii_redact: true,
            injection_enabled: false,
            content_filter_enabled: false,
        }
    }

    #[test]
    fn test_empty_store_returns_global() {
        let store = GuardrailPolicyStore::new();
        let cfg = store.resolve("tenant-a", &global());
        assert!(!cfg.pii_enabled);
        assert!(!cfg.injection_enabled);
    }

    #[test]
    fn test_tenant_override_wins() {
        let store = GuardrailPolicyStore::new();
        store.upsert(
            "tenant-a".into(),
            TenantGuardrailPolicy {
                pii_enabled: Some(true),
                injection_enabled: Some(true),
                content_filter_enabled: Some(true),
                ..Default::default()
            },
        );
        let cfg = store.resolve("tenant-a", &global());
        assert!(cfg.pii_enabled);
        assert!(cfg.injection_enabled);
        assert!(cfg.content_filter_enabled);
        // pii_redact not overridden → inherits global (true)
        assert!(cfg.pii_redact);
    }

    #[test]
    fn test_unknown_tenant_uses_global() {
        let store = GuardrailPolicyStore::new();
        store.upsert(
            "tenant-b".into(),
            TenantGuardrailPolicy {
                pii_enabled: Some(true),
                ..Default::default()
            },
        );
        let cfg = store.resolve("tenant-c", &global());
        assert!(!cfg.pii_enabled); // falls back to global
    }

    #[test]
    fn test_token_budget_limit_override() {
        let store = GuardrailPolicyStore::new();
        store.upsert(
            "tenant-a".into(),
            TenantGuardrailPolicy {
                token_budget_limit: Some(100_000),
                ..Default::default()
            },
        );
        assert_eq!(store.token_budget_limit("tenant-a", 500_000), 100_000);
        assert_eq!(store.token_budget_limit("tenant-b", 500_000), 500_000);
    }

    #[test]
    fn test_token_budget_zero_falls_back_to_global() {
        let store = GuardrailPolicyStore::new();
        store.upsert(
            "tenant-a".into(),
            TenantGuardrailPolicy {
                token_budget_limit: Some(0), // 0 = use global
                ..Default::default()
            },
        );
        assert_eq!(store.token_budget_limit("tenant-a", 500_000), 500_000);
    }

    #[test]
    fn test_tool_allowed_no_restriction() {
        let store = GuardrailPolicyStore::new();
        store.upsert("tenant-a".into(), TenantGuardrailPolicy::default());
        assert!(store.is_tool_allowed("tenant-a", "any_tool"));
        assert!(store.is_tool_allowed("tenant-b", "any_tool")); // no policy
    }

    #[test]
    fn test_tool_allowed_allowlist() {
        let store = GuardrailPolicyStore::new();
        store.upsert(
            "tenant-a".into(),
            TenantGuardrailPolicy {
                allowed_tools: Some(vec!["catalog".into(), "search".into()]),
                ..Default::default()
            },
        );
        assert!(store.is_tool_allowed("tenant-a", "catalog"));
        assert!(store.is_tool_allowed("tenant-a", "search"));
        assert!(!store.is_tool_allowed("tenant-a", "admin_tool"));
    }

    #[test]
    fn test_remove_policy() {
        let store = GuardrailPolicyStore::new();
        store.upsert("tenant-a".into(), TenantGuardrailPolicy::default());
        assert_eq!(store.count(), 1);
        assert!(store.remove("tenant-a"));
        assert_eq!(store.count(), 0);
        assert!(!store.remove("tenant-a")); // already removed
    }
}
