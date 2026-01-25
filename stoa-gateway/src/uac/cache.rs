//! Versioned Policy Cache
//!
//! CAB-912: Cache for UAC policies with Git version checking.
//!
//! The cache ensures we NEVER use stale policies by:
//! 1. Storing the Git commit hash with each cached policy
//! 2. Invalidating cache when Git version changes
//! 3. TTL-based expiration for automatic refresh

use chrono::{DateTime, Duration, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::RwLock;

use super::classifications::Classification;

// =============================================================================
// Policy Definition
// =============================================================================

/// A policy definition with metadata.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PolicyDefinition {
    /// Unique policy name (e.g., "rate-limit", "auth-jwt")
    pub name: String,

    /// Policy version
    pub version: String,

    /// Whether the policy is enabled
    pub enabled: bool,

    /// Policy configuration (opaque JSON)
    #[serde(default)]
    pub config: serde_json::Value,

    /// Required classifications for this policy to apply
    #[serde(default)]
    pub required_for: Vec<Classification>,
}

// =============================================================================
// Cache Entry
// =============================================================================

/// A cached policy entry with version and expiration.
#[derive(Debug, Clone)]
struct CacheEntry {
    /// The cached policy
    policy: PolicyDefinition,

    /// Git commit hash when this was cached
    git_version: String,

    /// When this entry was cached
    cached_at: DateTime<Utc>,

    /// When this entry expires
    expires_at: DateTime<Utc>,
}

impl CacheEntry {
    fn new(policy: PolicyDefinition, git_version: String, ttl: Duration) -> Self {
        let now = Utc::now();
        Self {
            policy,
            git_version,
            cached_at: now,
            expires_at: now + ttl,
        }
    }

    fn is_expired(&self) -> bool {
        Utc::now() > self.expires_at
    }

    fn is_stale(&self, current_git_version: &str) -> bool {
        self.git_version != current_git_version
    }
}

// =============================================================================
// Versioned Policy Cache
// =============================================================================

/// Thread-safe cache for UAC policies with Git version validation.
pub struct VersionedPolicyCache {
    /// Cached policies by name
    cache: RwLock<HashMap<String, CacheEntry>>,

    /// Current Git version (updated by GitSyncService)
    current_version: RwLock<String>,

    /// Cache TTL
    ttl: Duration,
}

impl VersionedPolicyCache {
    /// Create a new cache with the given TTL in seconds.
    pub fn new(ttl_seconds: i64) -> Self {
        Self {
            cache: RwLock::new(HashMap::new()),
            current_version: RwLock::new(String::new()),
            ttl: Duration::seconds(ttl_seconds),
        }
    }

    /// Update the current Git version (called when Git sync completes).
    pub fn set_version(&self, version: String) {
        let mut current = self.current_version.write().unwrap();
        *current = version;
    }

    /// Get the current Git version.
    pub fn get_version(&self) -> String {
        self.current_version.read().unwrap().clone()
    }

    /// Get a policy from cache if valid.
    ///
    /// Returns None if:
    /// - Policy not in cache
    /// - Policy is expired (TTL)
    /// - Policy is stale (Git version mismatch)
    pub fn get(&self, name: &str) -> Option<PolicyDefinition> {
        let cache = self.cache.read().unwrap();
        let current_version = self.current_version.read().unwrap();

        if let Some(entry) = cache.get(name) {
            if entry.is_expired() {
                return None;
            }
            if entry.is_stale(&current_version) {
                return None;
            }
            return Some(entry.policy.clone());
        }

        None
    }

    /// Get a policy, returning the Git version it was cached with.
    ///
    /// This is used for audit logging - we need to know which version
    /// of the policy was used for each decision.
    pub fn get_with_version(&self, name: &str) -> Option<(PolicyDefinition, String)> {
        let cache = self.cache.read().unwrap();
        let current_version = self.current_version.read().unwrap();

        if let Some(entry) = cache.get(name) {
            if entry.is_expired() {
                return None;
            }
            if entry.is_stale(&current_version) {
                return None;
            }
            return Some((entry.policy.clone(), entry.git_version.clone()));
        }

        None
    }

    /// Put a policy in the cache.
    pub fn put(&self, policy: PolicyDefinition, git_version: String) {
        let mut cache = self.cache.write().unwrap();
        let name = policy.name.clone();
        cache.insert(name, CacheEntry::new(policy, git_version, self.ttl));
    }

    /// Put multiple policies in the cache.
    pub fn put_all(&self, policies: Vec<PolicyDefinition>, git_version: String) {
        let mut cache = self.cache.write().unwrap();
        for policy in policies {
            let name = policy.name.clone();
            cache.insert(name, CacheEntry::new(policy, git_version.clone(), self.ttl));
        }
    }

    /// Invalidate all cached entries.
    pub fn invalidate_all(&self) {
        let mut cache = self.cache.write().unwrap();
        cache.clear();
    }

    /// Invalidate a specific policy.
    pub fn invalidate(&self, name: &str) {
        let mut cache = self.cache.write().unwrap();
        cache.remove(name);
    }

    /// Get cache statistics.
    pub fn stats(&self) -> CacheStats {
        let cache = self.cache.read().unwrap();
        let current_version = self.current_version.read().unwrap();

        let total = cache.len();
        let expired = cache.values().filter(|e| e.is_expired()).count();
        let stale = cache
            .values()
            .filter(|e| e.is_stale(&current_version))
            .count();

        CacheStats {
            total,
            valid: total - expired - stale,
            expired,
            stale,
            git_version: current_version.clone(),
        }
    }
}

impl Default for VersionedPolicyCache {
    fn default() -> Self {
        // Default TTL: 5 minutes
        Self::new(300)
    }
}

/// Cache statistics for monitoring.
#[derive(Debug, Clone, Serialize)]
pub struct CacheStats {
    /// Total entries in cache
    pub total: usize,
    /// Valid (not expired, not stale) entries
    pub valid: usize,
    /// Expired entries (TTL)
    pub expired: usize,
    /// Stale entries (Git version mismatch)
    pub stale: usize,
    /// Current Git version
    pub git_version: String,
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    fn make_policy(name: &str) -> PolicyDefinition {
        PolicyDefinition {
            name: name.to_string(),
            version: "1.0.0".to_string(),
            enabled: true,
            config: serde_json::json!({}),
            required_for: vec![],
        }
    }

    #[test]
    fn test_cache_put_get() {
        let cache = VersionedPolicyCache::new(3600); // 1 hour TTL
        cache.set_version("abc123".to_string());

        let policy = make_policy("rate-limit");
        cache.put(policy.clone(), "abc123".to_string());

        let result = cache.get("rate-limit");
        assert!(result.is_some());
        assert_eq!(result.unwrap().name, "rate-limit");
    }

    #[test]
    fn test_cache_miss() {
        let cache = VersionedPolicyCache::new(3600);
        cache.set_version("abc123".to_string());

        let result = cache.get("nonexistent");
        assert!(result.is_none());
    }

    #[test]
    fn test_cache_stale_on_version_change() {
        let cache = VersionedPolicyCache::new(3600);
        cache.set_version("abc123".to_string());

        let policy = make_policy("rate-limit");
        cache.put(policy, "abc123".to_string());

        // Verify it's cached
        assert!(cache.get("rate-limit").is_some());

        // Change version
        cache.set_version("def456".to_string());

        // Now it should be stale
        assert!(cache.get("rate-limit").is_none());
    }

    #[test]
    fn test_cache_get_with_version() {
        let cache = VersionedPolicyCache::new(3600);
        cache.set_version("abc123".to_string());

        let policy = make_policy("auth-jwt");
        cache.put(policy, "abc123".to_string());

        let result = cache.get_with_version("auth-jwt");
        assert!(result.is_some());
        let (policy, version) = result.unwrap();
        assert_eq!(policy.name, "auth-jwt");
        assert_eq!(version, "abc123");
    }

    #[test]
    fn test_cache_put_all() {
        let cache = VersionedPolicyCache::new(3600);
        cache.set_version("abc123".to_string());

        let policies = vec![
            make_policy("rate-limit"),
            make_policy("auth-jwt"),
            make_policy("mtls"),
        ];
        cache.put_all(policies, "abc123".to_string());

        assert!(cache.get("rate-limit").is_some());
        assert!(cache.get("auth-jwt").is_some());
        assert!(cache.get("mtls").is_some());
    }

    #[test]
    fn test_cache_invalidate() {
        let cache = VersionedPolicyCache::new(3600);
        cache.set_version("abc123".to_string());

        cache.put(make_policy("rate-limit"), "abc123".to_string());
        assert!(cache.get("rate-limit").is_some());

        cache.invalidate("rate-limit");
        assert!(cache.get("rate-limit").is_none());
    }

    #[test]
    fn test_cache_invalidate_all() {
        let cache = VersionedPolicyCache::new(3600);
        cache.set_version("abc123".to_string());

        cache.put(make_policy("rate-limit"), "abc123".to_string());
        cache.put(make_policy("auth-jwt"), "abc123".to_string());

        cache.invalidate_all();

        assert!(cache.get("rate-limit").is_none());
        assert!(cache.get("auth-jwt").is_none());
    }

    #[test]
    fn test_cache_stats() {
        let cache = VersionedPolicyCache::new(3600);
        cache.set_version("abc123".to_string());

        cache.put(make_policy("rate-limit"), "abc123".to_string());
        cache.put(make_policy("auth-jwt"), "abc123".to_string());

        let stats = cache.stats();
        assert_eq!(stats.total, 2);
        assert_eq!(stats.valid, 2);
        assert_eq!(stats.expired, 0);
        assert_eq!(stats.stale, 0);
        assert_eq!(stats.git_version, "abc123");
    }
}
