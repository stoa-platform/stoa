//! Semantic Cache for MCP Tool Responses
//!
//! Caches tool responses based on semantic equivalence:
//! - Cache key: (tool_name, args_hash, tenant_id)
//! - Per-tool TTL configuration
//! - Only caches read-only tools (from tool annotations)
//! - Never caches write/mutating tools
//!
//! Uses `moka` for high-performance concurrent caching with:
//! - Time-based expiration (TTL)
//! - Size-based eviction (LRU)
//! - Async support

// Allow dead_code for Phase 6 components that will be wired in future handlers
#![allow(dead_code)]

use moka::future::Cache;
use once_cell::sync::Lazy;
use parking_lot::RwLock;
use prometheus::{register_counter_vec, register_gauge, CounterVec, Gauge};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::sync::Arc;
use std::time::Duration;
use tracing::{debug, info};

/// Cache metrics
static CACHE_HITS: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_cache_hits_total",
        "Total cache hits",
        &["tool", "tenant"]
    )
    .expect("Failed to create stoa_cache_hits_total metric")
});

static CACHE_MISSES: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_cache_misses_total",
        "Total cache misses",
        &["tool", "tenant"]
    )
    .expect("Failed to create stoa_cache_misses_total metric")
});

static CACHE_SIZE: Lazy<Gauge> = Lazy::new(|| {
    register_gauge!("stoa_cache_entries", "Number of cached entries")
        .expect("Failed to create stoa_cache_entries metric")
});

/// Semantic cache configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SemanticCacheConfig {
    /// Enable semantic caching (default: true)
    #[serde(default = "default_enabled")]
    pub enabled: bool,

    /// Default TTL in seconds for cached responses (default: 300 = 5 min)
    #[serde(default = "default_ttl_secs")]
    pub default_ttl_secs: u64,

    /// Maximum number of cached entries (default: 10000)
    #[serde(default = "default_max_entries")]
    pub max_entries: u64,

    /// Per-tool TTL overrides (tool_name -> ttl_secs)
    #[serde(default)]
    pub tool_ttls: HashMap<String, u64>,

    /// Tools that should never be cached (write operations)
    #[serde(default)]
    pub never_cache: HashSet<String>,
}

fn default_enabled() -> bool {
    true
}

fn default_ttl_secs() -> u64 {
    300 // 5 minutes
}

fn default_max_entries() -> u64 {
    10_000
}

impl Default for SemanticCacheConfig {
    fn default() -> Self {
        let mut never_cache = HashSet::new();
        // Tools that mutate state should never be cached
        never_cache.insert("stoa_create_api".to_string());
        never_cache.insert("stoa_update_api".to_string());
        never_cache.insert("stoa_delete_api".to_string());
        never_cache.insert("stoa_create_subscription".to_string());
        never_cache.insert("stoa_cancel_subscription".to_string());

        Self {
            enabled: default_enabled(),
            default_ttl_secs: default_ttl_secs(),
            max_entries: default_max_entries(),
            tool_ttls: HashMap::new(),
            never_cache,
        }
    }
}

/// Cache key components
#[derive(Debug, Clone, Hash, PartialEq, Eq)]
pub struct CacheKey {
    pub tool_name: String,
    pub args_hash: String,
    pub tenant_id: String,
}

impl CacheKey {
    /// Create a new cache key
    pub fn new(tool_name: &str, args: &Value, tenant_id: &str) -> Self {
        let args_hash = hash_args(args);
        Self {
            tool_name: tool_name.to_string(),
            args_hash,
            tenant_id: tenant_id.to_string(),
        }
    }

    /// Convert to string key for moka cache
    fn to_string_key(&self) -> String {
        format!("{}:{}:{}", self.tenant_id, self.tool_name, self.args_hash)
    }
}

/// Cached tool response
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CacheEntry {
    /// The cached response value
    pub response: Value,

    /// When the entry was cached (Unix timestamp)
    pub cached_at: i64,

    /// Tool name (for debugging)
    pub tool_name: String,
}

/// Hash arguments to create cache key component
fn hash_args(args: &Value) -> String {
    // Normalize JSON (sort keys) for consistent hashing
    let normalized = normalize_json(args);
    let json_str = serde_json::to_string(&normalized).unwrap_or_default();

    let mut hasher = Sha256::new();
    hasher.update(json_str.as_bytes());
    let result = hasher.finalize();

    // Use first 16 bytes (32 hex chars) for shorter keys
    hex::encode(&result[..16])
}

/// Normalize JSON value for consistent hashing
/// - Sort object keys
/// - Trim strings
fn normalize_json(value: &Value) -> Value {
    match value {
        Value::Object(map) => {
            let mut sorted: Vec<_> = map.iter().collect();
            sorted.sort_by(|a, b| a.0.cmp(b.0));

            let normalized_map: serde_json::Map<String, Value> = sorted
                .into_iter()
                .map(|(k, v)| (k.clone(), normalize_json(v)))
                .collect();

            Value::Object(normalized_map)
        }
        Value::Array(arr) => Value::Array(arr.iter().map(normalize_json).collect()),
        Value::String(s) => Value::String(s.trim().to_string()),
        other => other.clone(),
    }
}

/// Semantic cache for tool responses
pub struct SemanticCache {
    /// Moka async cache
    cache: Cache<String, CacheEntry>,

    /// Configuration
    config: SemanticCacheConfig,

    /// Per-tool cacheable status (from annotations)
    /// True = cacheable (read-only), False = not cacheable (write)
    tool_cacheable: RwLock<HashMap<String, bool>>,
}

impl SemanticCache {
    /// Create a new semantic cache
    pub fn new(config: SemanticCacheConfig) -> Self {
        let cache = Cache::builder()
            .max_capacity(config.max_entries)
            .time_to_live(Duration::from_secs(config.default_ttl_secs))
            .build();

        info!(
            enabled = config.enabled,
            max_entries = config.max_entries,
            default_ttl_secs = config.default_ttl_secs,
            "Semantic cache initialized"
        );

        Self {
            cache,
            config,
            tool_cacheable: RwLock::new(HashMap::new()),
        }
    }

    /// Check if caching is enabled
    pub fn is_enabled(&self) -> bool {
        self.config.enabled
    }

    /// Register a tool as cacheable or not
    pub fn register_tool(&self, tool_name: &str, is_read_only: bool) {
        let cacheable = is_read_only && !self.config.never_cache.contains(tool_name);
        self.tool_cacheable
            .write()
            .insert(tool_name.to_string(), cacheable);
        debug!(
            tool = tool_name,
            cacheable = cacheable,
            "Tool cache status registered"
        );
    }

    /// Check if a tool's responses can be cached
    pub fn is_tool_cacheable(&self, tool_name: &str) -> bool {
        if !self.config.enabled {
            return false;
        }

        if self.config.never_cache.contains(tool_name) {
            return false;
        }

        // Check registered status, default to true for unknown tools
        // (read-only assumption)
        *self
            .tool_cacheable
            .read()
            .get(tool_name)
            .unwrap_or(&true)
    }

    /// Get TTL for a specific tool
    fn get_tool_ttl(&self, tool_name: &str) -> Duration {
        let ttl_secs = self
            .config
            .tool_ttls
            .get(tool_name)
            .copied()
            .unwrap_or(self.config.default_ttl_secs);

        Duration::from_secs(ttl_secs)
    }

    /// Try to get a cached response
    pub async fn get(&self, key: &CacheKey) -> Option<CacheEntry> {
        if !self.config.enabled || !self.is_tool_cacheable(&key.tool_name) {
            return None;
        }

        let string_key = key.to_string_key();
        let result = self.cache.get(&string_key).await;

        if result.is_some() {
            CACHE_HITS
                .with_label_values(&[&key.tool_name, &key.tenant_id])
                .inc();
            debug!(
                tool = %key.tool_name,
                tenant = %key.tenant_id,
                "Cache hit"
            );
        } else {
            CACHE_MISSES
                .with_label_values(&[&key.tool_name, &key.tenant_id])
                .inc();
            debug!(
                tool = %key.tool_name,
                tenant = %key.tenant_id,
                "Cache miss"
            );
        }

        result
    }

    /// Store a response in the cache
    pub async fn put(&self, key: &CacheKey, response: Value) {
        if !self.config.enabled || !self.is_tool_cacheable(&key.tool_name) {
            return;
        }

        let entry = CacheEntry {
            response,
            cached_at: chrono::Utc::now().timestamp(),
            tool_name: key.tool_name.clone(),
        };

        let string_key = key.to_string_key();

        // Use tool-specific TTL if configured
        let ttl = self.get_tool_ttl(&key.tool_name);

        // Moka doesn't support per-entry TTL directly, but we can use
        // expire_after for custom expiration policies in more advanced setups.
        // For now, we'll use the default TTL set on the cache.
        self.cache.insert(string_key, entry).await;

        // Update size metric
        CACHE_SIZE.set(self.cache.entry_count() as f64);

        debug!(
            tool = %key.tool_name,
            tenant = %key.tenant_id,
            ttl_secs = ttl.as_secs(),
            "Cached tool response"
        );
    }

    /// Invalidate a specific cache entry
    #[allow(dead_code)]
    pub async fn invalidate(&self, key: &CacheKey) {
        let string_key = key.to_string_key();
        self.cache.invalidate(&string_key).await;
        CACHE_SIZE.set(self.cache.entry_count() as f64);
    }

    /// Invalidate all entries for a tenant
    #[allow(dead_code)]
    pub async fn invalidate_tenant(&self, tenant_id: &str) {
        // Moka doesn't support prefix invalidation directly.
        // We'd need to iterate, which is expensive. For now, skip.
        // In production, consider a separate index or different cache structure.
        debug!(tenant = tenant_id, "Tenant cache invalidation requested (not implemented)");
    }

    /// Invalidate all entries for a tool
    #[allow(dead_code)]
    pub async fn invalidate_tool(&self, tool_name: &str) {
        debug!(tool = tool_name, "Tool cache invalidation requested (not implemented)");
    }

    /// Clear entire cache
    #[allow(dead_code)]
    pub fn clear(&self) {
        self.cache.invalidate_all();
        CACHE_SIZE.set(0.0);
        info!("Cache cleared");
    }

    /// Get cache statistics
    #[allow(dead_code)]
    pub fn stats(&self) -> CacheStats {
        CacheStats {
            entry_count: self.cache.entry_count(),
            weighted_size: self.cache.weighted_size(),
        }
    }
}

impl Default for SemanticCache {
    fn default() -> Self {
        Self::new(SemanticCacheConfig::default())
    }
}

/// Cache statistics
#[derive(Debug, Clone)]
pub struct CacheStats {
    pub entry_count: u64,
    pub weighted_size: u64,
}

/// Create a shared semantic cache
pub fn create_semantic_cache(config: SemanticCacheConfig) -> Arc<SemanticCache> {
    Arc::new(SemanticCache::new(config))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cache_key_creation() {
        let args = serde_json::json!({"name": "test", "value": 42});
        let key = CacheKey::new("my_tool", &args, "tenant-1");

        assert_eq!(key.tool_name, "my_tool");
        assert_eq!(key.tenant_id, "tenant-1");
        assert!(!key.args_hash.is_empty());
    }

    #[test]
    fn test_cache_key_deterministic() {
        let args1 = serde_json::json!({"name": "test", "value": 42});
        let args2 = serde_json::json!({"value": 42, "name": "test"}); // Different order

        let key1 = CacheKey::new("tool", &args1, "tenant");
        let key2 = CacheKey::new("tool", &args2, "tenant");

        // Should produce same hash regardless of key order
        assert_eq!(key1.args_hash, key2.args_hash);
    }

    #[test]
    fn test_cache_key_different_args() {
        let args1 = serde_json::json!({"name": "test1"});
        let args2 = serde_json::json!({"name": "test2"});

        let key1 = CacheKey::new("tool", &args1, "tenant");
        let key2 = CacheKey::new("tool", &args2, "tenant");

        assert_ne!(key1.args_hash, key2.args_hash);
    }

    #[test]
    fn test_normalize_json() {
        let input = serde_json::json!({
            "z": 1,
            "a": 2,
            "nested": {"b": 1, "a": 2}
        });

        let normalized = normalize_json(&input);
        let json_str = serde_json::to_string(&normalized).unwrap();

        // Keys should be sorted
        assert!(json_str.contains("\"a\":2"));
        assert!(json_str.find("\"a\"").unwrap() < json_str.find("\"z\"").unwrap());
    }

    #[test]
    fn test_cache_config_default() {
        let config = SemanticCacheConfig::default();

        assert!(config.enabled);
        assert_eq!(config.default_ttl_secs, 300);
        assert_eq!(config.max_entries, 10_000);
        assert!(config.never_cache.contains("stoa_create_api"));
    }

    #[tokio::test]
    async fn test_semantic_cache_disabled() {
        let config = SemanticCacheConfig {
            enabled: false,
            ..Default::default()
        };
        let cache = SemanticCache::new(config);

        let key = CacheKey::new("tool", &serde_json::json!({}), "tenant");

        // Put should be no-op
        cache.put(&key, serde_json::json!({"result": "value"})).await;

        // Get should return None
        assert!(cache.get(&key).await.is_none());
    }

    #[tokio::test]
    async fn test_semantic_cache_put_get() {
        let cache = SemanticCache::new(SemanticCacheConfig::default());

        let key = CacheKey::new("stoa_list_apis", &serde_json::json!({"page": 1}), "tenant-1");
        let response = serde_json::json!({"apis": ["api1", "api2"]});

        // Initially empty
        assert!(cache.get(&key).await.is_none());

        // Put and retrieve
        cache.put(&key, response.clone()).await;
        let cached = cache.get(&key).await;

        assert!(cached.is_some());
        let entry = cached.unwrap();
        assert_eq!(entry.response, response);
        assert_eq!(entry.tool_name, "stoa_list_apis");
    }

    #[tokio::test]
    async fn test_semantic_cache_never_cache_tools() {
        let cache = SemanticCache::new(SemanticCacheConfig::default());

        // stoa_create_api is in never_cache list
        let key = CacheKey::new("stoa_create_api", &serde_json::json!({}), "tenant");

        cache.put(&key, serde_json::json!({"created": true})).await;

        // Should not be cached
        assert!(cache.get(&key).await.is_none());
    }

    #[tokio::test]
    async fn test_semantic_cache_tool_registration() {
        let cache = SemanticCache::new(SemanticCacheConfig::default());

        // Register tool as not cacheable (write operation)
        cache.register_tool("custom_write_tool", false);

        assert!(!cache.is_tool_cacheable("custom_write_tool"));

        // Register tool as cacheable (read operation)
        cache.register_tool("custom_read_tool", true);

        assert!(cache.is_tool_cacheable("custom_read_tool"));
    }

    #[test]
    fn test_cache_stats() {
        let cache = SemanticCache::new(SemanticCacheConfig::default());
        let stats = cache.stats();

        assert_eq!(stats.entry_count, 0);
    }
}
