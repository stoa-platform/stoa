//! In-memory policy registry for dynamically managed policies.
//!
//! Policies are pushed by the Control Plane via the admin API
//! and can be applied per-route by the dynamic proxy.

use parking_lot::RwLock;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// A policy entry managed by the Control Plane.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PolicyEntry {
    /// Policy ID (from Control Plane)
    pub id: String,
    /// Human-readable policy name
    pub name: String,
    /// Policy type: "cors", "rate_limit", "jwt_validation", etc.
    pub policy_type: String,
    /// Policy configuration (type-specific)
    pub config: serde_json::Value,
    /// Execution priority (lower = higher priority)
    pub priority: i32,
    /// Route ID this policy is bound to
    pub api_id: String,
}

/// Thread-safe in-memory registry of policies.
pub struct PolicyRegistry {
    policies: RwLock<HashMap<String, PolicyEntry>>,
}

impl Default for PolicyRegistry {
    fn default() -> Self {
        Self::new()
    }
}

impl PolicyRegistry {
    /// Create an empty registry.
    pub fn new() -> Self {
        Self {
            policies: RwLock::new(HashMap::new()),
        }
    }

    /// Insert or update a policy. Returns the previous value if it existed.
    pub fn upsert(&self, policy: PolicyEntry) -> Option<PolicyEntry> {
        self.policies.write().insert(policy.id.clone(), policy)
    }

    /// Remove a policy by ID. Returns the removed policy if it existed.
    pub fn remove(&self, id: &str) -> Option<PolicyEntry> {
        self.policies.write().remove(id)
    }

    /// List all registered policies.
    pub fn list(&self) -> Vec<PolicyEntry> {
        self.policies.read().values().cloned().collect()
    }

    /// List policies bound to a specific API route, sorted by priority.
    pub fn list_for_api(&self, api_id: &str) -> Vec<PolicyEntry> {
        let policies = self.policies.read();
        let mut matched: Vec<PolicyEntry> = policies
            .values()
            .filter(|p| p.api_id == api_id)
            .cloned()
            .collect();
        matched.sort_by_key(|p| p.priority);
        matched
    }

    /// Number of registered policies.
    pub fn count(&self) -> usize {
        self.policies.read().len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_policy(id: &str, api_id: &str, priority: i32) -> PolicyEntry {
        PolicyEntry {
            id: id.to_string(),
            name: format!("policy-{}", id),
            policy_type: "rate_limit".to_string(),
            config: serde_json::json!({"rate": 100}),
            priority,
            api_id: api_id.to_string(),
        }
    }

    #[test]
    fn test_upsert_policy() {
        let reg = PolicyRegistry::new();
        let prev = reg.upsert(make_policy("p1", "api-1", 50));
        assert!(prev.is_none());
        assert_eq!(reg.count(), 1);
    }

    #[test]
    fn test_list_for_api() {
        let reg = PolicyRegistry::new();
        reg.upsert(make_policy("p1", "api-A", 100));
        reg.upsert(make_policy("p2", "api-A", 50));
        reg.upsert(make_policy("p3", "api-B", 75));

        let for_a = reg.list_for_api("api-A");
        assert_eq!(for_a.len(), 2);
        // Sorted by priority ascending
        assert_eq!(for_a[0].id, "p2"); // priority 50
        assert_eq!(for_a[1].id, "p1"); // priority 100
    }

    #[test]
    fn test_remove_policy() {
        let reg = PolicyRegistry::new();
        reg.upsert(make_policy("p1", "api-1", 50));
        let removed = reg.remove("p1");
        assert!(removed.is_some());
        assert_eq!(reg.count(), 0);
    }
}
