//! Pull-Based Budget Cache (CAB-1456)
//!
//! Periodically fetches department budget status from the Control Plane API
//! and caches the result in-memory. Fail-open: if the CP API is unreachable,
//! requests are allowed (never block on budget system downtime).

use parking_lot::RwLock;
use std::collections::HashMap;
use std::sync::Arc;
use std::time::Instant;
use tokio::time::{interval, Duration};
use tracing::{debug, info, warn};

/// Configuration for the budget cache.
#[derive(Debug, Clone)]
pub struct BudgetCacheConfig {
    /// URL of the billing API (e.g. "http://control-plane-api:8000")
    pub billing_api_url: String,
    /// Cache TTL in seconds (how often to refresh from CP API)
    pub cache_ttl_secs: u64,
}

/// Per-department budget state.
#[derive(Debug, Clone)]
struct BudgetState {
    /// Whether the department is over budget
    over_budget: bool,
    /// When this entry was last updated
    last_updated: Instant,
}

/// Pull-based budget cache that periodically fetches budget status from CP API.
///
/// Uses `parking_lot::RwLock<HashMap>` (same pattern as `QuotaManager`).
/// Fail-open: returns `false` (not over budget) on cache miss or API failure.
pub struct BudgetCache {
    states: Arc<RwLock<HashMap<String, BudgetState>>>,
    config: BudgetCacheConfig,
}

impl BudgetCache {
    /// Create a new budget cache.
    pub fn new(config: BudgetCacheConfig) -> Self {
        Self {
            states: Arc::new(RwLock::new(HashMap::new())),
            config,
        }
    }

    /// Check if a department is over budget.
    ///
    /// Returns `false` (fail-open) if:
    /// - Department not in cache (cache miss)
    /// - Cache entry is stale (older than 2x TTL)
    /// - Any error occurred during fetch
    pub fn is_over_budget(&self, department_id: &str) -> bool {
        let states = self.states.read();
        match states.get(department_id) {
            Some(state) => {
                let age = state.last_updated.elapsed();
                if age.as_secs() > self.config.cache_ttl_secs * 2 {
                    debug!(
                        department_id = %department_id,
                        age_secs = age.as_secs(),
                        "Budget cache entry stale, fail-open"
                    );
                    false
                } else {
                    state.over_budget
                }
            }
            None => {
                debug!(
                    department_id = %department_id,
                    "Budget cache miss, fail-open"
                );
                false
            }
        }
    }

    /// Update budget state for a department (called by background refresh).
    fn update(&self, department_id: &str, over_budget: bool) {
        let mut states = self.states.write();
        states.insert(
            department_id.to_string(),
            BudgetState {
                over_budget,
                last_updated: Instant::now(),
            },
        );
    }

    /// Get the number of cached departments (for metrics).
    pub fn department_count(&self) -> usize {
        self.states.read().len()
    }

    /// Get all tracked department IDs (for background refresh).
    fn tracked_departments(&self) -> Vec<String> {
        self.states.read().keys().cloned().collect()
    }

    /// Register a department for tracking (called when a request arrives).
    pub fn track_department(&self, department_id: &str) {
        let states = self.states.read();
        if states.contains_key(department_id) {
            return;
        }
        drop(states);

        let mut states = self.states.write();
        states
            .entry(department_id.to_string())
            .or_insert(BudgetState {
                over_budget: false,
                last_updated: Instant::now(),
            });
    }

    /// Start background refresh task that periodically fetches budget status.
    pub fn start_refresh_task(self: Arc<Self>) {
        let cache = self.clone();
        let refresh_secs = self.config.cache_ttl_secs;
        tokio::spawn(async move {
            let mut refresh_interval = interval(Duration::from_secs(refresh_secs));
            loop {
                refresh_interval.tick().await;
                cache.refresh_all().await;
            }
        });
        info!(
            interval_secs = refresh_secs,
            billing_api_url = %self.config.billing_api_url,
            "Budget cache refresh task started"
        );
    }

    /// Refresh budget status for all tracked departments.
    async fn refresh_all(&self) {
        let departments = self.tracked_departments();
        if departments.is_empty() {
            return;
        }

        let client = match reqwest::Client::builder()
            .timeout(Duration::from_secs(5))
            .build()
        {
            Ok(c) => c,
            Err(e) => {
                warn!(error = %e, "Failed to create HTTP client for budget refresh");
                return;
            }
        };

        for dept_id in &departments {
            let url = format!(
                "{}/internal/budgets/{}/check",
                self.config.billing_api_url.trim_end_matches('/'),
                dept_id,
            );

            match client.get(&url).send().await {
                Ok(resp) => {
                    if resp.status().is_success() {
                        match resp.json::<BudgetCheckResponse>().await {
                            Ok(body) => {
                                let was_over = self.is_over_budget(dept_id);
                                self.update(dept_id, body.over_budget);
                                if body.over_budget && !was_over {
                                    warn!(
                                        department_id = %dept_id,
                                        "Department is now over budget"
                                    );
                                }
                            }
                            Err(e) => {
                                debug!(
                                    department_id = %dept_id,
                                    error = %e,
                                    "Failed to parse budget response, keeping cached value"
                                );
                            }
                        }
                    } else {
                        debug!(
                            department_id = %dept_id,
                            status = %resp.status(),
                            "Budget API returned non-success, fail-open"
                        );
                    }
                }
                Err(e) => {
                    debug!(
                        department_id = %dept_id,
                        error = %e,
                        "Budget API unreachable, fail-open"
                    );
                }
            }
        }
    }
}

/// CP API response for budget check
#[derive(Debug, serde::Deserialize)]
struct BudgetCheckResponse {
    over_budget: bool,
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_config() -> BudgetCacheConfig {
        BudgetCacheConfig {
            billing_api_url: "http://localhost:8000".to_string(),
            cache_ttl_secs: 60,
        }
    }

    #[test]
    fn test_cache_miss_returns_false() {
        let cache = BudgetCache::new(test_config());
        assert!(!cache.is_over_budget("dept-unknown"));
    }

    #[test]
    fn test_cache_hit_returns_state() {
        let cache = BudgetCache::new(test_config());
        cache.update("dept-1", true);
        assert!(cache.is_over_budget("dept-1"));

        cache.update("dept-2", false);
        assert!(!cache.is_over_budget("dept-2"));
    }

    #[test]
    fn test_track_department() {
        let cache = BudgetCache::new(test_config());
        assert_eq!(cache.department_count(), 0);

        cache.track_department("dept-1");
        assert_eq!(cache.department_count(), 1);

        cache.track_department("dept-1");
        assert_eq!(cache.department_count(), 1);
    }

    #[test]
    fn test_tracked_departments() {
        let cache = BudgetCache::new(test_config());
        cache.track_department("dept-a");
        cache.track_department("dept-b");

        let tracked = cache.tracked_departments();
        assert_eq!(tracked.len(), 2);
        assert!(tracked.contains(&"dept-a".to_string()));
        assert!(tracked.contains(&"dept-b".to_string()));
    }

    #[test]
    fn test_update_overwrites_state() {
        let cache = BudgetCache::new(test_config());
        cache.update("dept-1", false);
        assert!(!cache.is_over_budget("dept-1"));

        cache.update("dept-1", true);
        assert!(cache.is_over_budget("dept-1"));
    }

    #[test]
    fn test_separate_departments_independent() {
        let cache = BudgetCache::new(test_config());
        cache.update("dept-1", true);
        cache.update("dept-2", false);

        assert!(cache.is_over_budget("dept-1"));
        assert!(!cache.is_over_budget("dept-2"));
    }

    #[test]
    fn test_department_count() {
        let cache = BudgetCache::new(test_config());
        assert_eq!(cache.department_count(), 0);

        cache.update("dept-1", false);
        assert_eq!(cache.department_count(), 1);

        cache.update("dept-2", true);
        assert_eq!(cache.department_count(), 2);
    }

    #[test]
    fn test_fail_open_on_fresh_entry() {
        let cache = BudgetCache::new(test_config());
        cache.track_department("dept-new");
        assert!(!cache.is_over_budget("dept-new"));
    }
}
