//! Prompt Cache (CAB-1123 Phase 2)
//!
//! In-memory cache for AI agent prompt patterns (HEGEMON knowledge base).
//! Amortizes redundant pattern reads across N concurrent agent sessions.
//!
//! Uses moka::sync::Cache (same backend as SemanticCache).
//! Key tracking via parking_lot::RwLock<HashSet> (moka doesn't expose iteration).

use std::collections::HashSet;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;

use moka::sync::Cache;
use parking_lot::RwLock;
use serde::Serialize;

/// Configuration for the prompt cache.
pub struct PromptCacheConfig {
    pub max_entries: u64,
    pub default_ttl: Duration,
}

impl Default for PromptCacheConfig {
    fn default() -> Self {
        Self {
            max_entries: 1000,
            default_ttl: Duration::from_secs(3600),
        }
    }
}

/// Cache statistics.
#[derive(Debug, Clone, Serialize)]
pub struct PromptCacheStats {
    pub hits: u64,
    pub misses: u64,
    pub entry_count: u64,
    pub hit_rate: f64,
}

/// In-memory prompt pattern cache backed by moka.
pub struct PromptCache {
    cache: Cache<String, String>,
    keys: RwLock<HashSet<String>>,
    hits: AtomicU64,
    misses: AtomicU64,
}

impl PromptCache {
    pub fn new(config: PromptCacheConfig) -> Self {
        let cache = Cache::builder()
            .max_capacity(config.max_entries)
            .time_to_live(config.default_ttl)
            .build();
        Self {
            cache,
            keys: RwLock::new(HashSet::new()),
            hits: AtomicU64::new(0),
            misses: AtomicU64::new(0),
        }
    }

    /// Get a cached prompt pattern by key.
    pub fn get(&self, key: &str) -> Option<String> {
        match self.cache.get(&key.to_string()) {
            Some(value) => {
                self.hits.fetch_add(1, Ordering::Relaxed);
                Some(value)
            }
            None => {
                self.misses.fetch_add(1, Ordering::Relaxed);
                None
            }
        }
    }

    /// Insert or update a prompt pattern.
    pub fn put(&self, key: String, value: String) {
        self.cache.insert(key.clone(), value);
        self.keys.write().insert(key);
    }

    /// Remove a single key.
    pub fn remove(&self, key: &str) {
        self.cache.invalidate(&key.to_string());
        self.keys.write().remove(key);
    }

    /// Clear all cached entries.
    pub fn clear(&self) {
        self.cache.invalidate_all();
        self.keys.write().clear();
    }

    /// Return current cache statistics.
    pub fn stats(&self) -> PromptCacheStats {
        let hits = self.hits.load(Ordering::Relaxed);
        let misses = self.misses.load(Ordering::Relaxed);
        let total = hits + misses;
        PromptCacheStats {
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

    /// List all tracked keys.
    pub fn list_keys(&self) -> Vec<String> {
        self.keys.read().iter().cloned().collect()
    }

    /// Bulk-load prompt patterns. Returns the number of entries loaded.
    pub fn load_patterns(&self, entries: Vec<(String, String)>) -> usize {
        let count = entries.len();
        let mut keys = self.keys.write();
        for (key, value) in entries {
            self.cache.insert(key.clone(), value);
            keys.insert(key);
        }
        count
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_cache() -> PromptCache {
        PromptCache::new(PromptCacheConfig::default())
    }

    #[test]
    fn get_returns_none_for_missing_key() {
        let cache = make_cache();
        assert!(cache.get("nonexistent").is_none());
    }

    #[test]
    fn put_then_get_returns_value() {
        let cache = make_cache();
        cache.put("greeting".into(), "Hello, {name}!".into());
        assert_eq!(cache.get("greeting").unwrap(), "Hello, {name}!");
    }

    #[test]
    fn remove_deletes_entry() {
        let cache = make_cache();
        cache.put("k1".into(), "v1".into());
        cache.remove("k1");
        assert!(cache.get("k1").is_none());
    }

    #[test]
    fn clear_removes_all_entries() {
        let cache = make_cache();
        cache.put("a".into(), "1".into());
        cache.put("b".into(), "2".into());
        cache.clear();
        assert_eq!(cache.stats().entry_count, 0);
        assert!(cache.list_keys().is_empty());
    }

    #[test]
    fn stats_tracks_hits_and_misses() {
        let cache = make_cache();
        cache.put("x".into(), "val".into());
        let _ = cache.get("x"); // hit
        let _ = cache.get("y"); // miss
        let stats = cache.stats();
        assert_eq!(stats.hits, 1);
        assert_eq!(stats.misses, 1);
        assert!((stats.hit_rate - 0.5).abs() < f64::EPSILON);
    }

    #[test]
    fn list_keys_returns_all_inserted_keys() {
        let cache = make_cache();
        cache.put("alpha".into(), "a".into());
        cache.put("beta".into(), "b".into());
        let mut keys = cache.list_keys();
        keys.sort();
        assert_eq!(keys, vec!["alpha", "beta"]);
    }

    #[test]
    fn load_patterns_bulk_inserts() {
        let cache = make_cache();
        let entries = vec![
            ("p1".into(), "pattern-1".into()),
            ("p2".into(), "pattern-2".into()),
            ("p3".into(), "pattern-3".into()),
        ];
        let count = cache.load_patterns(entries);
        assert_eq!(count, 3);
        assert_eq!(cache.get("p2").unwrap(), "pattern-2");
    }

    #[test]
    fn stats_hit_rate_zero_when_no_access() {
        let cache = make_cache();
        let stats = cache.stats();
        assert_eq!(stats.hits, 0);
        assert_eq!(stats.misses, 0);
        assert!((stats.hit_rate - 0.0).abs() < f64::EPSILON);
    }
}
