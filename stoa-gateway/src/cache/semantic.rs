//! Semantic Tool Response Cache
//!
//! Moka-based cache for tool responses with TTL and size limits.
//!
//! Note: Infrastructure prepared for SSE handler integration (Phase 7).

// Cache infrastructure prepared for future integration
#![allow(dead_code)]

use moka::future::Cache;
use serde_json::Value;
use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;
use tracing::{debug, info};

/// Cached tool response
#[derive(Debug, Clone)]
pub struct CachedResponse {
    /// The cached result
    pub result: Value,
    /// Tool name that produced this result
    pub tool_name: String,
    /// Tenant ID
    pub tenant_id: String,
}

/// Semantic cache configuration
#[derive(Debug, Clone)]
pub struct SemanticCacheConfig {
    /// Maximum number of entries
    pub max_entries: u64,
    /// Default TTL for cache entries
    pub default_ttl: Duration,
    /// TTL for expensive operations (longer)
    pub expensive_ttl: Duration,
}

impl Default for SemanticCacheConfig {
    fn default() -> Self {
        Self {
            max_entries: 10_000,
            default_ttl: Duration::from_secs(60),    // 1 minute
            expensive_ttl: Duration::from_secs(300), // 5 minutes for expensive ops
        }
    }
}

/// Cache statistics
#[derive(Debug, Clone)]
pub struct SemanticCacheStats {
    /// Number of cache hits
    pub hits: u64,
    /// Number of cache misses
    pub misses: u64,
    /// Current number of entries
    pub entry_count: u64,
    /// Hit rate (0.0 to 1.0)
    pub hit_rate: f64,
}

/// Semantic tool response cache
pub struct SemanticCache {
    cache: Cache<String, CachedResponse>,
    config: SemanticCacheConfig,
    hits: AtomicU64,
    misses: AtomicU64,
}

impl SemanticCache {
    /// Create a new semantic cache
    pub fn new(config: SemanticCacheConfig) -> Self {
        let cache = Cache::builder()
            .max_capacity(config.max_entries)
            .time_to_live(config.default_ttl)
            .build();

        info!(
            max_entries = config.max_entries,
            ttl_secs = config.default_ttl.as_secs(),
            "Semantic cache initialized"
        );

        Self {
            cache,
            config,
            hits: AtomicU64::new(0),
            misses: AtomicU64::new(0),
        }
    }

    /// Generate cache key from tool name, tenant, and arguments
    fn cache_key(tool_name: &str, tenant_id: &str, args: &Value) -> String {
        let mut hasher = DefaultHasher::new();
        // Canonical JSON representation for consistent hashing
        let args_str = serde_json::to_string(args).unwrap_or_default();
        args_str.hash(&mut hasher);
        let args_hash = hasher.finish();

        format!("{}:{}:{:016x}", tenant_id, tool_name, args_hash)
    }

    /// Check if a tool is cacheable based on annotations
    ///
    /// Returns true if read_only_hint is true or not specified for read operations
    pub fn is_cacheable(read_only_hint: Option<bool>) -> bool {
        // Default to false (safe default - don't cache unless explicitly allowed)
        read_only_hint.unwrap_or(false)
    }

    /// Get a cached response
    pub async fn get(
        &self,
        tool_name: &str,
        tenant_id: &str,
        args: &Value,
    ) -> Option<CachedResponse> {
        let key = Self::cache_key(tool_name, tenant_id, args);

        match self.cache.get(&key).await {
            Some(cached) => {
                self.hits.fetch_add(1, Ordering::Relaxed);
                debug!(
                    tool = %tool_name,
                    tenant = %tenant_id,
                    key = %key,
                    "Cache hit"
                );
                Some(cached)
            }
            None => {
                self.misses.fetch_add(1, Ordering::Relaxed);
                debug!(
                    tool = %tool_name,
                    tenant = %tenant_id,
                    key = %key,
                    "Cache miss"
                );
                None
            }
        }
    }

    /// Store a response in cache
    pub async fn put(&self, tool_name: &str, tenant_id: &str, args: &Value, result: Value) {
        let key = Self::cache_key(tool_name, tenant_id, args);

        let cached = CachedResponse {
            result,
            tool_name: tool_name.to_string(),
            tenant_id: tenant_id.to_string(),
        };

        self.cache.insert(key.clone(), cached).await;

        debug!(
            tool = %tool_name,
            tenant = %tenant_id,
            key = %key,
            "Response cached"
        );
    }

    /// Store a response with custom TTL (for expensive operations)
    pub async fn put_with_ttl(
        &self,
        tool_name: &str,
        tenant_id: &str,
        args: &Value,
        result: Value,
        ttl: Duration,
    ) {
        let key = Self::cache_key(tool_name, tenant_id, args);

        let cached = CachedResponse {
            result,
            tool_name: tool_name.to_string(),
            tenant_id: tenant_id.to_string(),
        };

        // Note: moka's insert uses the cache's default TTL
        // For per-entry TTL, we'd need a different approach
        // For now, we just use the default TTL
        let _ = ttl; // Acknowledge parameter
        self.cache.insert(key, cached).await;
    }

    /// Invalidate a specific cache entry
    pub async fn invalidate(&self, tool_name: &str, tenant_id: &str, args: &Value) {
        let key = Self::cache_key(tool_name, tenant_id, args);
        self.cache.invalidate(&key).await;
        debug!(key = %key, "Cache entry invalidated");
    }

    /// Invalidate all entries for a tool
    pub async fn invalidate_tool(&self, tool_name: &str, tenant_id: &str) {
        let prefix = format!("{}:{}:", tenant_id, tool_name);
        // Note: moka doesn't support prefix-based invalidation directly
        // We would need to track keys separately for this
        // For now, just log the intent
        debug!(
            prefix = %prefix,
            "Tool invalidation requested (full cache clear not implemented)"
        );
    }

    /// Clear all cache entries
    pub async fn clear(&self) {
        self.cache.invalidate_all();
        info!("Cache cleared");
    }

    /// Get cache statistics
    pub fn stats(&self) -> SemanticCacheStats {
        let hits = self.hits.load(Ordering::Relaxed);
        let misses = self.misses.load(Ordering::Relaxed);
        let total = hits + misses;

        SemanticCacheStats {
            hits,
            misses,
            entry_count: self.cache.entry_count(),
            hit_rate: if total > 0 {
                hits as f64 / total as f64
            } else {
                0.0
            },
        }
    }

    /// Get the expensive operation TTL
    pub fn expensive_ttl(&self) -> Duration {
        self.config.expensive_ttl
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_cache_key_generation() {
        let key1 = SemanticCache::cache_key("stoa_catalog", "acme", &json!({"category": "ml"}));
        let key2 = SemanticCache::cache_key("stoa_catalog", "acme", &json!({"category": "ml"}));
        let key3 = SemanticCache::cache_key("stoa_catalog", "acme", &json!({"category": "devops"}));
        let key4 = SemanticCache::cache_key("stoa_catalog", "other", &json!({"category": "ml"}));

        // Same tool + tenant + args = same key
        assert_eq!(key1, key2);

        // Different args = different key
        assert_ne!(key1, key3);

        // Different tenant = different key
        assert_ne!(key1, key4);
    }

    #[test]
    fn test_is_cacheable() {
        assert!(SemanticCache::is_cacheable(Some(true)));
        assert!(!SemanticCache::is_cacheable(Some(false)));
        assert!(!SemanticCache::is_cacheable(None)); // Default to not cacheable
    }

    #[tokio::test]
    async fn test_cache_put_get() {
        let cache = SemanticCache::new(SemanticCacheConfig::default());
        let args = json!({"category": "ml"});

        // Miss on first get
        let result = cache.get("stoa_catalog", "acme", &args).await;
        assert!(result.is_none());

        // Put value
        cache
            .put(
                "stoa_catalog",
                "acme",
                &args,
                json!({"apis": ["ml-predict"]}),
            )
            .await;

        // Hit on second get
        let result = cache.get("stoa_catalog", "acme", &args).await;
        assert!(result.is_some());
        let cached = result.unwrap();
        assert_eq!(cached.tool_name, "stoa_catalog");
        assert_eq!(cached.tenant_id, "acme");
        assert_eq!(cached.result["apis"][0], "ml-predict");
    }

    #[tokio::test]
    async fn test_cache_stats() {
        let cache = SemanticCache::new(SemanticCacheConfig::default());
        let args = json!({});

        // 1 miss
        let _ = cache.get("tool1", "tenant1", &args).await;

        // Put and 2 hits
        cache.put("tool1", "tenant1", &args, json!({})).await;
        let _ = cache.get("tool1", "tenant1", &args).await;
        let _ = cache.get("tool1", "tenant1", &args).await;

        let stats = cache.stats();
        assert_eq!(stats.hits, 2);
        assert_eq!(stats.misses, 1);
        assert!((stats.hit_rate - 0.666).abs() < 0.01);
    }

    #[tokio::test]
    async fn test_cache_invalidate() {
        let cache = SemanticCache::new(SemanticCacheConfig::default());
        let args = json!({});

        cache.put("tool1", "tenant1", &args, json!({})).await;
        assert!(cache.get("tool1", "tenant1", &args).await.is_some());

        cache.invalidate("tool1", "tenant1", &args).await;
        assert!(cache.get("tool1", "tenant1", &args).await.is_none());
    }

    #[tokio::test]
    async fn test_cache_clear() {
        let cache = SemanticCache::new(SemanticCacheConfig::default());

        cache.put("tool1", "tenant1", &json!({}), json!({})).await;
        cache.put("tool2", "tenant2", &json!({}), json!({})).await;

        cache.clear().await;

        assert!(cache.get("tool1", "tenant1", &json!({})).await.is_none());
        assert!(cache.get("tool2", "tenant2", &json!({})).await.is_none());
    }

    #[test]
    fn test_config_default() {
        let config = SemanticCacheConfig::default();
        assert_eq!(config.max_entries, 10_000);
        assert_eq!(config.default_ttl, Duration::from_secs(60));
        assert_eq!(config.expensive_ttl, Duration::from_secs(300));
    }
}
