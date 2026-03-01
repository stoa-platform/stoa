//! LLM Completion Cache (CAB-1615)
//!
//! Caches non-streaming LLM completion responses by content hash.
//! Avoids redundant upstream calls for identical prompts within the TTL window.
//!
//! Cache key: `{subscription_id}:{model}:{hash(messages + temperature)}`
//!
//! Only caches:
//! - Non-streaming responses (streaming = no cache)
//! - Successful responses (HTTP 2xx)
//! - Responses with `stream: false` or no `stream` field in the request body

use moka::future::Cache;
use serde::Deserialize;
use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;
use tracing::{debug, info};

/// Cached LLM completion response.
#[derive(Debug, Clone)]
pub struct CachedCompletion {
    /// HTTP response body bytes.
    pub body: Vec<u8>,
    /// Content-Type header value.
    pub content_type: String,
    /// HTTP status code.
    pub status: u16,
}

/// Configuration for the LLM completion cache.
#[derive(Debug, Clone)]
pub struct LlmCacheConfig {
    /// Maximum number of cached entries.
    pub max_entries: u64,
    /// Default TTL for cached completions.
    pub default_ttl: Duration,
    /// Whether caching is enabled.
    pub enabled: bool,
}

impl Default for LlmCacheConfig {
    fn default() -> Self {
        Self {
            max_entries: 1_000,
            default_ttl: Duration::from_secs(300), // 5 minutes
            enabled: false,
        }
    }
}

/// LLM completion cache statistics.
#[derive(Debug, Clone)]
pub struct LlmCacheStats {
    pub hits: u64,
    pub misses: u64,
    pub entry_count: u64,
    pub hit_rate: f64,
}

/// Partial request body for extracting cache-relevant fields.
#[derive(Debug, Deserialize)]
struct ChatRequestFields {
    model: Option<String>,
    messages: Option<serde_json::Value>,
    temperature: Option<f64>,
    stream: Option<bool>,
}

/// LLM completion cache backed by moka.
pub struct LlmCompletionCache {
    cache: Cache<String, CachedCompletion>,
    enabled: bool,
    hits: AtomicU64,
    misses: AtomicU64,
}

impl LlmCompletionCache {
    /// Create a new LLM completion cache.
    pub fn new(config: LlmCacheConfig) -> Self {
        let cache = Cache::builder()
            .max_capacity(config.max_entries)
            .time_to_live(config.default_ttl)
            .build();

        if config.enabled {
            info!(
                max_entries = config.max_entries,
                ttl_secs = config.default_ttl.as_secs(),
                "LLM completion cache initialized"
            );
        }

        Self {
            cache,
            enabled: config.enabled,
            hits: AtomicU64::new(0),
            misses: AtomicU64::new(0),
        }
    }

    /// Check if the request body is cacheable (non-streaming).
    pub fn is_cacheable(body: &[u8]) -> bool {
        match serde_json::from_slice::<ChatRequestFields>(body) {
            Ok(fields) => !fields.stream.unwrap_or(false),
            Err(_) => false,
        }
    }

    /// Build cache key from subscription context and request body.
    ///
    /// Key format: `llm:{subscription_id}:{model}:{hash(messages+temperature)}`
    pub fn cache_key(subscription_id: &str, body: &[u8]) -> Option<String> {
        let fields: ChatRequestFields = serde_json::from_slice(body).ok()?;
        let model = fields.model.as_deref().unwrap_or("default");
        let messages = fields.messages.as_ref()?;

        let mut hasher = DefaultHasher::new();
        let messages_str = serde_json::to_string(messages).unwrap_or_default();
        messages_str.hash(&mut hasher);
        // Include temperature in hash (different temperatures = different results)
        let temp_bits = fields.temperature.unwrap_or(1.0).to_bits();
        temp_bits.hash(&mut hasher);
        let content_hash = hasher.finish();

        Some(format!(
            "llm:{}:{}:{:016x}",
            subscription_id, model, content_hash
        ))
    }

    /// Get a cached completion.
    pub async fn get(&self, subscription_id: &str, body: &[u8]) -> Option<CachedCompletion> {
        if !self.enabled {
            return None;
        }

        let key = Self::cache_key(subscription_id, body)?;

        match self.cache.get(&key).await {
            Some(cached) => {
                self.hits.fetch_add(1, Ordering::Relaxed);
                debug!(key = %key, "LLM cache hit");
                Some(cached)
            }
            None => {
                self.misses.fetch_add(1, Ordering::Relaxed);
                debug!(key = %key, "LLM cache miss");
                None
            }
        }
    }

    /// Store a completion in the cache.
    pub async fn put(
        &self,
        subscription_id: &str,
        request_body: &[u8],
        response_body: Vec<u8>,
        content_type: String,
        status: u16,
    ) {
        if !self.enabled {
            return;
        }

        // Only cache successful responses
        if !(200..300).contains(&status) {
            return;
        }

        let key = match Self::cache_key(subscription_id, request_body) {
            Some(k) => k,
            None => return,
        };

        let cached = CachedCompletion {
            body: response_body,
            content_type,
            status,
        };

        self.cache.insert(key.clone(), cached).await;
        debug!(key = %key, "LLM completion cached");
    }

    /// Get cache statistics.
    pub fn stats(&self) -> LlmCacheStats {
        let hits = self.hits.load(Ordering::Relaxed);
        let misses = self.misses.load(Ordering::Relaxed);
        let total = hits + misses;

        LlmCacheStats {
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

    /// Whether caching is enabled.
    pub fn is_enabled(&self) -> bool {
        self.enabled
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn cache_key_deterministic() {
        let body = serde_json::to_vec(&json!({
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hello"}],
            "temperature": 0.7
        }))
        .unwrap();

        let key1 = LlmCompletionCache::cache_key("sub-alpha", &body);
        let key2 = LlmCompletionCache::cache_key("sub-alpha", &body);
        assert_eq!(key1, key2);
        assert!(key1.unwrap().starts_with("llm:sub-alpha:gpt-4o:"));
    }

    #[test]
    fn cache_key_different_subscriptions() {
        let body = serde_json::to_vec(&json!({
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hello"}]
        }))
        .unwrap();

        let key_a = LlmCompletionCache::cache_key("sub-alpha", &body).unwrap();
        let key_b = LlmCompletionCache::cache_key("sub-beta", &body).unwrap();
        assert_ne!(key_a, key_b);
    }

    #[test]
    fn cache_key_different_messages() {
        let body1 = serde_json::to_vec(&json!({
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hello"}]
        }))
        .unwrap();
        let body2 = serde_json::to_vec(&json!({
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Goodbye"}]
        }))
        .unwrap();

        let key1 = LlmCompletionCache::cache_key("sub-1", &body1).unwrap();
        let key2 = LlmCompletionCache::cache_key("sub-1", &body2).unwrap();
        assert_ne!(key1, key2);
    }

    #[test]
    fn cache_key_different_temperatures() {
        let body1 = serde_json::to_vec(&json!({
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hello"}],
            "temperature": 0.0
        }))
        .unwrap();
        let body2 = serde_json::to_vec(&json!({
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hello"}],
            "temperature": 1.0
        }))
        .unwrap();

        let key1 = LlmCompletionCache::cache_key("sub-1", &body1).unwrap();
        let key2 = LlmCompletionCache::cache_key("sub-1", &body2).unwrap();
        assert_ne!(key1, key2);
    }

    #[test]
    fn cache_key_missing_messages_returns_none() {
        let body = serde_json::to_vec(&json!({"model": "gpt-4o"})).unwrap();
        assert!(LlmCompletionCache::cache_key("sub-1", &body).is_none());
    }

    #[test]
    fn cache_key_invalid_json_returns_none() {
        assert!(LlmCompletionCache::cache_key("sub-1", b"not json").is_none());
    }

    #[test]
    fn is_cacheable_non_streaming() {
        let body = serde_json::to_vec(&json!({
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hi"}]
        }))
        .unwrap();
        assert!(LlmCompletionCache::is_cacheable(&body));
    }

    #[test]
    fn is_cacheable_explicit_false() {
        let body = serde_json::to_vec(&json!({
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": false
        }))
        .unwrap();
        assert!(LlmCompletionCache::is_cacheable(&body));
    }

    #[test]
    fn not_cacheable_streaming() {
        let body = serde_json::to_vec(&json!({
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": true
        }))
        .unwrap();
        assert!(!LlmCompletionCache::is_cacheable(&body));
    }

    #[test]
    fn not_cacheable_invalid_json() {
        assert!(!LlmCompletionCache::is_cacheable(b"garbage"));
    }

    #[tokio::test]
    async fn cache_put_get_hit() {
        let cache = LlmCompletionCache::new(LlmCacheConfig {
            enabled: true,
            ..LlmCacheConfig::default()
        });

        let body = serde_json::to_vec(&json!({
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hello"}]
        }))
        .unwrap();

        // Miss
        assert!(cache.get("sub-1", &body).await.is_none());

        // Put
        cache
            .put(
                "sub-1",
                &body,
                b"response".to_vec(),
                "application/json".into(),
                200,
            )
            .await;

        // Hit
        let cached = cache.get("sub-1", &body).await.unwrap();
        assert_eq!(cached.body, b"response");
        assert_eq!(cached.status, 200);
        assert_eq!(cached.content_type, "application/json");
    }

    #[tokio::test]
    async fn cache_skips_error_responses() {
        let cache = LlmCompletionCache::new(LlmCacheConfig {
            enabled: true,
            ..LlmCacheConfig::default()
        });

        let body = serde_json::to_vec(&json!({
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hello"}]
        }))
        .unwrap();

        // Put with error status — should not cache
        cache
            .put(
                "sub-1",
                &body,
                b"error".to_vec(),
                "application/json".into(),
                429,
            )
            .await;

        assert!(cache.get("sub-1", &body).await.is_none());
    }

    #[tokio::test]
    async fn cache_disabled_returns_none() {
        let cache = LlmCompletionCache::new(LlmCacheConfig::default()); // enabled: false

        let body = serde_json::to_vec(&json!({
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hello"}]
        }))
        .unwrap();

        cache
            .put(
                "sub-1",
                &body,
                b"response".to_vec(),
                "application/json".into(),
                200,
            )
            .await;
        assert!(cache.get("sub-1", &body).await.is_none());
    }

    #[tokio::test]
    async fn cache_stats() {
        let cache = LlmCompletionCache::new(LlmCacheConfig {
            enabled: true,
            ..LlmCacheConfig::default()
        });

        let body = serde_json::to_vec(&json!({
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hello"}]
        }))
        .unwrap();

        // 1 miss
        let _ = cache.get("sub-1", &body).await;
        // Put + 2 hits
        cache
            .put(
                "sub-1",
                &body,
                b"ok".to_vec(),
                "application/json".into(),
                200,
            )
            .await;
        let _ = cache.get("sub-1", &body).await;
        let _ = cache.get("sub-1", &body).await;

        let stats = cache.stats();
        assert_eq!(stats.hits, 2);
        assert_eq!(stats.misses, 1);
        assert!((stats.hit_rate - 0.666).abs() < 0.01);
    }
}
