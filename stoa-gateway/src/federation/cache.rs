//! Federation allow-list cache (CAB-1362)
//!
//! moka-based async cache for sub-account tool allow-lists.
//! Populated lazily from CP API on cache miss.

use std::collections::HashSet;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;

use moka::future::Cache;
use serde::{Deserialize, Serialize};
use tracing::{debug, warn};

use crate::control_plane::ToolProxyClient;

/// Federation cache stats for admin endpoint.
#[derive(Debug, Clone, Serialize)]
pub struct FederationCacheStats {
    pub entries: u64,
    pub hits: u64,
    pub misses: u64,
    pub hit_rate: f64,
}

/// Sub-account tool response from CP API.
#[derive(Deserialize)]
struct SubAccountResponse {
    tools: Vec<SubAccountToolRef>,
}

/// Tool reference in sub-account response.
#[derive(Deserialize)]
struct SubAccountToolRef {
    tool_name: String,
}

/// Cache for federation sub-account tool allow-lists.
///
/// Keyed by sub_account_id, values are sets of allowed tool names.
/// Populated lazily from CP API on first request per sub-account.
pub struct FederationCache {
    cache: Cache<String, HashSet<String>>,
    control_plane: Arc<ToolProxyClient>,
    hits: AtomicU64,
    misses: AtomicU64,
}

impl FederationCache {
    /// Create a new federation cache.
    pub fn new(ttl_secs: u64, max_entries: u64, control_plane: Arc<ToolProxyClient>) -> Self {
        let cache = Cache::builder()
            .max_capacity(max_entries)
            .time_to_live(std::time::Duration::from_secs(ttl_secs))
            .build();

        Self {
            cache,
            control_plane,
            hits: AtomicU64::new(0),
            misses: AtomicU64::new(0),
        }
    }

    /// Get allowed tools for a sub-account.
    ///
    /// Returns `Some(tools)` on cache hit or successful CP fetch.
    /// Returns `None` on fetch error (permissive — log warning).
    pub async fn get_allowed_tools(
        &self,
        sub_account_id: &str,
        tenant_id: &str,
        master_account_id: &str,
    ) -> Option<HashSet<String>> {
        // Cache hit
        if let Some(tools) = self.cache.get(sub_account_id).await {
            self.hits.fetch_add(1, Ordering::Relaxed);
            return Some(tools);
        }

        self.misses.fetch_add(1, Ordering::Relaxed);
        debug!(
            sub_account_id,
            "Federation cache miss, fetching from CP API"
        );

        // Fetch from CP API
        match self
            .fetch_from_cp(sub_account_id, tenant_id, master_account_id)
            .await
        {
            Ok(tools) => {
                self.cache
                    .insert(sub_account_id.to_string(), tools.clone())
                    .await;
                Some(tools)
            }
            Err(e) => {
                warn!(
                    sub_account_id,
                    error = %e,
                    "Failed to fetch federation allow-list from CP API, using permissive mode"
                );
                None
            }
        }
    }

    /// Manually invalidate a sub-account's cached allow-list.
    pub async fn invalidate(&self, sub_account_id: &str) {
        self.cache.invalidate(sub_account_id).await;
    }

    /// Get cache statistics.
    pub fn stats(&self) -> FederationCacheStats {
        let hits = self.hits.load(Ordering::Relaxed);
        let misses = self.misses.load(Ordering::Relaxed);
        let total = hits + misses;
        FederationCacheStats {
            entries: self.entry_count(),
            hits,
            misses,
            hit_rate: if total > 0 {
                hits as f64 / total as f64
            } else {
                0.0
            },
        }
    }

    /// Number of entries in the cache.
    pub fn entry_count(&self) -> u64 {
        self.cache.entry_count()
    }

    /// Fetch sub-account tools from CP API.
    async fn fetch_from_cp(
        &self,
        sub_account_id: &str,
        tenant_id: &str,
        master_account_id: &str,
    ) -> Result<HashSet<String>, String> {
        let base_url = self.control_plane.base_url();
        let url = format!(
            "{}/v1/tenants/{}/federation/accounts/{}/sub-accounts/{}",
            base_url, tenant_id, master_account_id, sub_account_id
        );

        let response = self
            .control_plane
            .http_client()
            .get(&url)
            .send()
            .await
            .map_err(|e| format!("HTTP request failed: {}", e))?;

        if !response.status().is_success() {
            return Err(format!("CP API returned status {}", response.status()));
        }

        let sub_account: SubAccountResponse = response
            .json()
            .await
            .map_err(|e| format!("Failed to parse response: {}", e))?;

        Ok(sub_account.tools.into_iter().map(|t| t.tool_name).collect())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_cache_stats_initial() {
        let cp = Arc::new(ToolProxyClient::new("http://localhost:8000", None));
        let cache = FederationCache::new(300, 1000, cp);

        let stats = cache.stats();
        assert_eq!(stats.entries, 0);
        assert_eq!(stats.hits, 0);
        assert_eq!(stats.misses, 0);
        assert_eq!(stats.hit_rate, 0.0);
    }

    #[tokio::test]
    async fn test_cache_insert_and_hit() {
        let cp = Arc::new(ToolProxyClient::new("http://localhost:8000", None));
        let cache = FederationCache::new(300, 1000, cp);

        let tools: HashSet<String> = vec!["tool_a".to_string(), "tool_b".to_string()]
            .into_iter()
            .collect();
        cache.cache.insert("sub-1".to_string(), tools.clone()).await;

        // Should hit
        let result = cache.get_allowed_tools("sub-1", "acme", "master-1").await;
        assert_eq!(result, Some(tools));
        assert_eq!(cache.stats().hits, 1);
    }

    #[tokio::test]
    async fn test_cache_invalidate() {
        let cp = Arc::new(ToolProxyClient::new("http://localhost:8000", None));
        let cache = FederationCache::new(300, 1000, cp);

        let tools: HashSet<String> = vec!["tool_a".to_string()].into_iter().collect();
        cache.cache.insert("sub-1".to_string(), tools).await;
        cache.cache.run_pending_tasks().await;
        assert_eq!(cache.entry_count(), 1);

        cache.invalidate("sub-1").await;
        cache.cache.run_pending_tasks().await;
        assert_eq!(cache.entry_count(), 0);
    }
}
