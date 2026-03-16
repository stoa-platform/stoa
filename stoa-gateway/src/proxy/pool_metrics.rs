//! Connection pool metrics tracking (CAB-1832).
//!
//! Since reqwest does not expose pool internals, this module tracks
//! connection reuse heuristically: each request increments a total
//! counter; when the response `connection` header indicates a new
//! connection was established (or no keep-alive), we count it as new.
//! The reuse ratio is `1 - (new / total)`.

use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;

use parking_lot::Mutex;

/// Per-upstream connection tracking counters.
struct UpstreamCounters {
    total_requests: AtomicU64,
    new_connections: AtomicU64,
    active: AtomicU64,
}

impl UpstreamCounters {
    fn new() -> Self {
        Self {
            total_requests: AtomicU64::new(0),
            new_connections: AtomicU64::new(0),
            active: AtomicU64::new(0),
        }
    }
}

/// Tracks connection pool metrics across all upstreams.
///
/// Thread-safe: uses atomic counters per upstream with a mutex only
/// for inserting new upstream entries (rare path).
pub struct PoolMetrics {
    upstreams: Mutex<HashMap<String, Arc<UpstreamCounters>>>,
}

impl Default for PoolMetrics {
    fn default() -> Self {
        Self::new()
    }
}

impl PoolMetrics {
    /// Create a new empty pool metrics tracker.
    pub fn new() -> Self {
        Self {
            upstreams: Mutex::new(HashMap::new()),
        }
    }

    /// Get or create counters for an upstream.
    fn get_counters(&self, upstream: &str) -> Arc<UpstreamCounters> {
        // Fast path: check if already exists
        {
            let map = self.upstreams.lock();
            if let Some(c) = map.get(upstream) {
                return Arc::clone(c);
            }
        }
        // Slow path: insert new
        let mut map = self.upstreams.lock();
        Arc::clone(
            map.entry(upstream.to_string())
                .or_insert_with(|| Arc::new(UpstreamCounters::new())),
        )
    }

    /// Record the start of a request to an upstream.
    /// Returns a guard that decrements active count on drop.
    pub fn request_start(&self, upstream: &str) -> PoolRequestGuard {
        let counters = self.get_counters(upstream);
        counters.total_requests.fetch_add(1, Ordering::Relaxed);
        counters.active.fetch_add(1, Ordering::Relaxed);

        let upstream_name = upstream.to_string();
        crate::metrics::POOL_CONNECTIONS_ACTIVE
            .with_label_values(&[&upstream_name])
            .inc();

        PoolRequestGuard {
            counters,
            upstream_name,
        }
    }

    /// Record that a new connection was opened (not reused from pool).
    pub fn record_new_connection(&self, upstream: &str) {
        let counters = self.get_counters(upstream);
        counters.new_connections.fetch_add(1, Ordering::Relaxed);

        crate::metrics::POOL_NEW_CONNECTIONS
            .with_label_values(&[upstream])
            .inc();
    }

    /// Publish current reuse ratio to Prometheus for a given upstream.
    pub fn publish_reuse_ratio(&self, upstream: &str) {
        let counters = self.get_counters(upstream);
        let total = counters.total_requests.load(Ordering::Relaxed);
        let new = counters.new_connections.load(Ordering::Relaxed);
        let ratio = if total == 0 {
            0.0
        } else {
            1.0 - (new as f64 / total as f64)
        };
        crate::metrics::POOL_REUSE_RATIO
            .with_label_values(&[upstream])
            .set(ratio);
    }
}

/// RAII guard that decrements active connection count when dropped.
pub struct PoolRequestGuard {
    counters: Arc<UpstreamCounters>,
    upstream_name: String,
}

impl Drop for PoolRequestGuard {
    fn drop(&mut self) {
        self.counters.active.fetch_sub(1, Ordering::Relaxed);
        crate::metrics::POOL_CONNECTIONS_ACTIVE
            .with_label_values(&[&self.upstream_name])
            .dec();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_request_start_increments_counters() {
        let pm = PoolMetrics::new();
        let _guard = pm.request_start("echo-backend:8888");
        let counters = pm.get_counters("echo-backend:8888");
        assert_eq!(counters.total_requests.load(Ordering::Relaxed), 1);
        assert_eq!(counters.active.load(Ordering::Relaxed), 1);
    }

    #[test]
    fn test_guard_drop_decrements_active() {
        let pm = PoolMetrics::new();
        {
            let _guard = pm.request_start("echo-backend:8888");
            let counters = pm.get_counters("echo-backend:8888");
            assert_eq!(counters.active.load(Ordering::Relaxed), 1);
        }
        // Guard dropped
        let counters = pm.get_counters("echo-backend:8888");
        assert_eq!(counters.active.load(Ordering::Relaxed), 0);
    }

    #[test]
    fn test_new_connection_tracking() {
        let pm = PoolMetrics::new();
        let _g1 = pm.request_start("backend-a");
        pm.record_new_connection("backend-a");
        let _g2 = pm.request_start("backend-a");
        // Second request reused connection (no record_new_connection)

        let counters = pm.get_counters("backend-a");
        assert_eq!(counters.total_requests.load(Ordering::Relaxed), 2);
        assert_eq!(counters.new_connections.load(Ordering::Relaxed), 1);
    }

    #[test]
    fn test_reuse_ratio_calculation() {
        let pm = PoolMetrics::new();
        // 4 requests, 1 new connection => reuse ratio = 0.75
        for _ in 0..4 {
            let _g = pm.request_start("backend-ratio");
        }
        pm.record_new_connection("backend-ratio");

        pm.publish_reuse_ratio("backend-ratio");
        let counters = pm.get_counters("backend-ratio");
        let total = counters.total_requests.load(Ordering::Relaxed);
        let new = counters.new_connections.load(Ordering::Relaxed);
        let ratio = 1.0 - (new as f64 / total as f64);
        assert!((ratio - 0.75).abs() < f64::EPSILON);
    }

    #[test]
    fn test_reuse_ratio_zero_requests() {
        let pm = PoolMetrics::new();
        pm.publish_reuse_ratio("empty-upstream");
        // Should not panic — ratio is 0.0 when no requests
    }

    #[test]
    fn test_multiple_upstreams_isolated() {
        let pm = PoolMetrics::new();
        let _g1 = pm.request_start("upstream-a");
        let _g2 = pm.request_start("upstream-b");
        pm.record_new_connection("upstream-a");

        let ca = pm.get_counters("upstream-a");
        let cb = pm.get_counters("upstream-b");
        assert_eq!(ca.new_connections.load(Ordering::Relaxed), 1);
        assert_eq!(cb.new_connections.load(Ordering::Relaxed), 0);
    }
}
