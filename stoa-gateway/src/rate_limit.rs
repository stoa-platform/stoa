//! Rate Limiter with parking_lot RwLock and automatic cleanup
//!
//! Replaces std::sync::RwLock to avoid poisoning panics.
//! Adds periodic cleanup of stale tenant buckets.

use chrono::{DateTime, Duration, Utc};
use parking_lot::RwLock;
use std::collections::HashMap;
use std::sync::Arc;
use tokio::time::{interval, Duration as TokioDuration};
use tracing::{debug, info};

use crate::config::Config;
use crate::metrics;

/// Sliding window rate limit bucket for a tenant
#[derive(Debug, Clone)]
struct TenantBucket {
    /// Timestamps of requests within the window
    timestamps: Vec<DateTime<Utc>>,
    /// Last activity time for cleanup
    last_activity: DateTime<Utc>,
}

impl TenantBucket {
    fn new() -> Self {
        Self {
            timestamps: Vec::with_capacity(100),
            last_activity: Utc::now(),
        }
    }

    /// Clean old timestamps outside the window
    fn cleanup_window(&mut self, window: Duration) {
        let cutoff = Utc::now() - window;
        self.timestamps.retain(|ts| *ts > cutoff);
    }

    /// Check if request is allowed and record it
    fn check_and_record(&mut self, limit: usize, window: Duration) -> bool {
        self.cleanup_window(window);
        self.last_activity = Utc::now();

        if self.timestamps.len() < limit {
            self.timestamps.push(Utc::now());
            true
        } else {
            false
        }
    }

    /// Get remaining requests in current window
    fn remaining(&self, limit: usize) -> usize {
        limit.saturating_sub(self.timestamps.len())
    }

    /// Get reset time (oldest timestamp + window)
    fn reset_at(&self, window: Duration) -> Option<DateTime<Utc>> {
        self.timestamps.first().map(|ts| *ts + window)
    }
}

/// Rate limiter with per-tenant sliding window
pub struct RateLimiter {
    buckets: Arc<RwLock<HashMap<String, TenantBucket>>>,
    default_limit: usize,
    window: Duration,
    /// How long before a bucket is considered stale
    stale_threshold: Duration,
}

impl RateLimiter {
    pub fn new(config: &Config) -> Self {
        Self {
            buckets: Arc::new(RwLock::new(HashMap::new())),
            default_limit: config.rate_limit_default.unwrap_or(1000),
            window: Duration::seconds(config.rate_limit_window_seconds.unwrap_or(60) as i64),
            stale_threshold: Duration::hours(1),
        }
    }

    /// Check if request is allowed for tenant
    pub fn check(&self, tenant_id: &str) -> RateLimitResult {
        let mut buckets = self.buckets.write();

        let bucket = buckets
            .entry(tenant_id.to_string())
            .or_insert_with(TenantBucket::new);

        let allowed = bucket.check_and_record(self.default_limit, self.window);
        let remaining = bucket.remaining(self.default_limit);
        let reset_at = bucket.reset_at(self.window);

        RateLimitResult {
            allowed,
            limit: self.default_limit,
            remaining,
            reset_at,
        }
    }

    /// Cleanup stale buckets (call periodically)
    pub fn cleanup_stale_buckets(&self) {
        let cutoff = Utc::now() - self.stale_threshold;
        let mut buckets = self.buckets.write();

        let before_count = buckets.len();
        buckets.retain(|tenant_id, bucket| {
            let keep = bucket.last_activity > cutoff;
            if !keep {
                debug!(tenant_id = %tenant_id, "Removing stale rate limit bucket");
            }
            keep
        });

        let removed = before_count - buckets.len();
        if removed > 0 {
            info!(
                removed = removed,
                remaining = buckets.len(),
                "Cleaned up stale rate limit buckets"
            );
        }
        metrics::update_rate_limit_buckets(buckets.len());
    }

    /// Start background cleanup task
    pub fn start_cleanup_task(self: Arc<Self>) {
        let limiter = self.clone();
        tokio::spawn(async move {
            let mut cleanup_interval = interval(TokioDuration::from_secs(60));
            loop {
                cleanup_interval.tick().await;
                limiter.cleanup_stale_buckets();
            }
        });
        info!("Rate limiter cleanup task started (60s interval)");
    }

    /// Get current bucket count (for metrics)
    #[allow(dead_code)]
    pub fn bucket_count(&self) -> usize {
        self.buckets.read().len()
    }
}

/// Result of a rate limit check
#[derive(Debug, Clone)]
#[allow(dead_code)]
pub struct RateLimitResult {
    pub allowed: bool,
    pub limit: usize,
    pub remaining: usize,
    pub reset_at: Option<DateTime<Utc>>,
}

impl RateLimitResult {
    /// Generate X-RateLimit-* headers
    #[allow(dead_code)]
    pub fn headers(&self) -> Vec<(&'static str, String)> {
        let mut headers = vec![
            ("X-RateLimit-Limit", self.limit.to_string()),
            ("X-RateLimit-Remaining", self.remaining.to_string()),
        ];

        if let Some(reset) = self.reset_at {
            headers.push(("X-RateLimit-Reset", reset.timestamp().to_string()));
        }

        headers
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_config() -> Config {
        Config {
            rate_limit_default: Some(5),
            rate_limit_window_seconds: Some(60),
            ..Default::default()
        }
    }

    #[test]
    fn test_rate_limit_allows_within_limit() {
        let limiter = RateLimiter::new(&test_config());

        for i in 0..5 {
            let result = limiter.check("tenant-1");
            assert!(result.allowed, "Request {} should be allowed", i + 1);
            assert_eq!(result.remaining, 4 - i);
        }
    }

    #[test]
    fn test_rate_limit_blocks_over_limit() {
        let limiter = RateLimiter::new(&test_config());

        // Exhaust limit
        for _ in 0..5 {
            limiter.check("tenant-1");
        }

        // Should be blocked
        let result = limiter.check("tenant-1");
        assert!(!result.allowed);
        assert_eq!(result.remaining, 0);
    }

    #[test]
    fn test_separate_tenant_buckets() {
        let limiter = RateLimiter::new(&test_config());

        // Exhaust tenant-1
        for _ in 0..5 {
            limiter.check("tenant-1");
        }

        // tenant-2 should still be allowed
        let result = limiter.check("tenant-2");
        assert!(result.allowed);
        assert_eq!(result.remaining, 4);
    }

    #[test]
    fn test_cleanup_stale_buckets() {
        let config = test_config();
        let limiter = RateLimiter::new(&config);

        // Add some buckets
        limiter.check("tenant-1");
        limiter.check("tenant-2");

        assert_eq!(limiter.bucket_count(), 2);

        // Cleanup (none should be removed - not stale yet)
        limiter.cleanup_stale_buckets();
        assert_eq!(limiter.bucket_count(), 2);
    }

    #[test]
    fn test_headers_generation() {
        let result = RateLimitResult {
            allowed: true,
            limit: 1000,
            remaining: 500,
            reset_at: Some(Utc::now()),
        };

        let headers = result.headers();
        assert_eq!(headers.len(), 3);
        assert_eq!(headers[0].0, "X-RateLimit-Limit");
        assert_eq!(headers[1].0, "X-RateLimit-Remaining");
        assert_eq!(headers[2].0, "X-RateLimit-Reset");
    }
}
