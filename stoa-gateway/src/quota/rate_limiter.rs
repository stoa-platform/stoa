//! Token Bucket Rate Limiter (Phase 4: CAB-1121)
//!
//! Per-consumer rate limiting based on plan quota fields.
//! Uses a token bucket algorithm with per-second and per-minute windows.
//!
//! Thread-safe via `parking_lot::RwLock` (non-poisoning).

use parking_lot::RwLock;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use std::time::Instant;
use tokio::time::{interval, Duration as TokioDuration};
use tracing::{debug, info};

use super::QuotaError;

/// Plan-level quota configuration pushed from Control Plane.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlanQuota {
    /// Maximum requests per second (0 = unlimited).
    #[serde(default)]
    pub rate_limit_per_second: u32,

    /// Maximum requests per minute (0 = unlimited).
    #[serde(default)]
    pub rate_limit_per_minute: u32,

    /// Maximum burst size (0 = use rate_limit_per_second).
    #[serde(default)]
    pub burst_limit: u32,

    /// Maximum requests per day (0 = unlimited).
    #[serde(default)]
    pub daily_request_limit: u32,

    /// Maximum requests per month (0 = unlimited).
    #[serde(default)]
    pub monthly_request_limit: u32,
}

impl Default for PlanQuota {
    fn default() -> Self {
        Self {
            rate_limit_per_second: 0,
            rate_limit_per_minute: 60,
            burst_limit: 0,
            daily_request_limit: 10_000,
            monthly_request_limit: 0,
        }
    }
}

/// Configuration for the consumer rate limiter.
#[derive(Debug, Clone)]
pub struct RateLimiterConfig {
    /// Default rate per minute when no plan quota is set.
    pub default_rate_per_minute: u32,

    /// Cleanup interval for stale buckets in seconds.
    pub cleanup_interval_secs: u64,

    /// How long before a bucket is considered stale (seconds).
    pub stale_threshold_secs: u64,
}

impl Default for RateLimiterConfig {
    fn default() -> Self {
        Self {
            default_rate_per_minute: 60,
            cleanup_interval_secs: 120,
            stale_threshold_secs: 3600,
        }
    }
}

/// Internal token bucket state for a single consumer.
#[derive(Debug)]
struct TokenBucket {
    /// Available tokens for per-second limiting.
    second_tokens: f64,
    /// Maximum tokens for per-second bucket.
    second_max: f64,
    /// Last refill time for per-second bucket.
    second_last_refill: Instant,

    /// Available tokens for per-minute limiting.
    minute_tokens: f64,
    /// Maximum tokens for per-minute bucket.
    minute_max: f64,
    /// Last refill time for per-minute bucket.
    minute_last_refill: Instant,

    /// Last activity time (for stale cleanup).
    last_activity: Instant,
}

impl TokenBucket {
    fn new(quota: &PlanQuota) -> Self {
        let now = Instant::now();
        let second_max = if quota.burst_limit > 0 {
            quota.burst_limit as f64
        } else if quota.rate_limit_per_second > 0 {
            quota.rate_limit_per_second as f64
        } else {
            f64::MAX
        };
        let minute_max = if quota.rate_limit_per_minute > 0 {
            quota.rate_limit_per_minute as f64
        } else {
            f64::MAX
        };

        Self {
            second_tokens: second_max,
            second_max,
            second_last_refill: now,
            minute_tokens: minute_max,
            minute_max,
            minute_last_refill: now,
            last_activity: now,
        }
    }

    /// Refill tokens based on elapsed time.
    fn refill(&mut self, quota: &PlanQuota) {
        let now = Instant::now();

        // Per-second refill
        if quota.rate_limit_per_second > 0 {
            let elapsed = now.duration_since(self.second_last_refill).as_secs_f64();
            let new_tokens = elapsed * quota.rate_limit_per_second as f64;
            self.second_tokens = (self.second_tokens + new_tokens).min(self.second_max);
            self.second_last_refill = now;
        }

        // Per-minute refill
        if quota.rate_limit_per_minute > 0 {
            let elapsed = now.duration_since(self.minute_last_refill).as_secs_f64();
            let refill_rate = quota.rate_limit_per_minute as f64 / 60.0;
            let new_tokens = elapsed * refill_rate;
            self.minute_tokens = (self.minute_tokens + new_tokens).min(self.minute_max);
            self.minute_last_refill = now;
        }
    }

    /// Try to consume one token. Returns Ok(()) or Err with the violated limit.
    fn try_consume(&mut self, quota: &PlanQuota) -> Result<(), QuotaError> {
        self.refill(quota);
        self.last_activity = Instant::now();

        // Check per-second limit
        if quota.rate_limit_per_second > 0 && self.second_tokens < 1.0 {
            return Err(QuotaError::RateLimit {
                limit_type: "per_second".to_string(),
                limit: quota.rate_limit_per_second,
                retry_after_secs: 1, // Retry after 1 second for per-second limits
            });
        }

        // Check per-minute limit
        if quota.rate_limit_per_minute > 0 && self.minute_tokens < 1.0 {
            let retry_after = 60 / quota.rate_limit_per_minute.max(1) as u64;
            return Err(QuotaError::RateLimit {
                limit_type: "per_minute".to_string(),
                limit: quota.rate_limit_per_minute,
                retry_after_secs: retry_after.max(1),
            });
        }

        // Consume tokens
        if quota.rate_limit_per_second > 0 {
            self.second_tokens -= 1.0;
        }
        if quota.rate_limit_per_minute > 0 {
            self.minute_tokens -= 1.0;
        }

        Ok(())
    }

    /// Get remaining tokens for the most restrictive limit.
    fn remaining(&self, quota: &PlanQuota) -> u32 {
        let second_remaining = if quota.rate_limit_per_second > 0 {
            self.second_tokens.max(0.0) as u32
        } else {
            u32::MAX
        };
        let minute_remaining = if quota.rate_limit_per_minute > 0 {
            self.minute_tokens.max(0.0) as u32
        } else {
            u32::MAX
        };
        second_remaining.min(minute_remaining)
    }

    /// Get the effective limit (most restrictive).
    fn effective_limit(&self, quota: &PlanQuota) -> u32 {
        if quota.rate_limit_per_second > 0 {
            let burst = if quota.burst_limit > 0 {
                quota.burst_limit
            } else {
                quota.rate_limit_per_second
            };
            if quota.rate_limit_per_minute > 0 {
                burst.min(quota.rate_limit_per_minute)
            } else {
                burst
            }
        } else if quota.rate_limit_per_minute > 0 {
            quota.rate_limit_per_minute
        } else {
            0 // unlimited
        }
    }

    /// Get reset time in epoch seconds for the most restrictive limit.
    fn reset_epoch(&self, quota: &PlanQuota) -> i64 {
        let now = chrono::Utc::now().timestamp();
        if quota.rate_limit_per_second > 0 && self.second_tokens < 1.0 {
            return now + 1;
        }
        if quota.rate_limit_per_minute > 0 && self.minute_tokens < 1.0 {
            let secs_per_token = 60.0 / quota.rate_limit_per_minute.max(1) as f64;
            return now + secs_per_token.ceil() as i64;
        }
        now + 60 // Default: next minute
    }
}

/// Result of a rate limit check with header information.
#[derive(Debug, Clone)]
pub struct RateLimitInfo {
    /// Maximum requests in the current window.
    pub limit: u32,
    /// Remaining requests in the current window.
    pub remaining: u32,
    /// Unix timestamp when the rate limit resets.
    pub reset_epoch: i64,
}

/// Per-consumer rate limiter using token bucket algorithm.
///
/// Manages separate token buckets for each consumer, keyed by consumer_id.
/// Plan quotas are looked up from an in-memory cache.
pub struct ConsumerRateLimiter {
    buckets: Arc<RwLock<HashMap<String, TokenBucket>>>,
    plan_quotas: Arc<RwLock<HashMap<String, PlanQuota>>>,
    config: RateLimiterConfig,
}

impl ConsumerRateLimiter {
    /// Create a new consumer rate limiter.
    pub fn new(config: RateLimiterConfig) -> Self {
        Self {
            buckets: Arc::new(RwLock::new(HashMap::new())),
            plan_quotas: Arc::new(RwLock::new(HashMap::new())),
            config,
        }
    }

    /// Set the plan quota for a consumer.
    /// Called by admin API when CP pushes plan context via `upsert_policy`.
    #[allow(dead_code)]
    pub fn set_plan_quota(&self, consumer_id: &str, quota: PlanQuota) {
        self.plan_quotas
            .write()
            .insert(consumer_id.to_string(), quota);
    }

    /// Remove plan quota for a consumer.
    #[allow(dead_code)]
    pub fn remove_plan_quota(&self, consumer_id: &str) {
        self.plan_quotas.write().remove(consumer_id);
        self.buckets.write().remove(consumer_id);
    }

    /// Check rate limit for a consumer. Returns rate limit info on success.
    pub fn check_rate_limit(&self, consumer_id: &str) -> Result<RateLimitInfo, QuotaError> {
        let quotas = self.plan_quotas.read();
        let default_quota = PlanQuota {
            rate_limit_per_minute: self.config.default_rate_per_minute,
            ..PlanQuota::default()
        };
        let quota = quotas.get(consumer_id).unwrap_or(&default_quota);

        // Skip if unlimited
        if quota.rate_limit_per_second == 0 && quota.rate_limit_per_minute == 0 {
            return Ok(RateLimitInfo {
                limit: 0,
                remaining: 0,
                reset_epoch: 0,
            });
        }

        let mut buckets = self.buckets.write();
        let bucket = buckets
            .entry(consumer_id.to_string())
            .or_insert_with(|| TokenBucket::new(quota));

        // Try to consume a token
        bucket.try_consume(quota)?;

        Ok(RateLimitInfo {
            limit: bucket.effective_limit(quota),
            remaining: bucket.remaining(quota),
            reset_epoch: bucket.reset_epoch(quota),
        })
    }

    /// Get rate limit info without consuming a token (for headers on already-checked requests).
    #[allow(dead_code)]
    pub fn get_rate_limit_info(&self, consumer_id: &str) -> RateLimitInfo {
        let quotas = self.plan_quotas.read();
        let default_quota = PlanQuota {
            rate_limit_per_minute: self.config.default_rate_per_minute,
            ..PlanQuota::default()
        };
        let quota = quotas.get(consumer_id).unwrap_or(&default_quota);

        let buckets = self.buckets.read();
        match buckets.get(consumer_id) {
            Some(bucket) => RateLimitInfo {
                limit: bucket.effective_limit(quota),
                remaining: bucket.remaining(quota),
                reset_epoch: bucket.reset_epoch(quota),
            },
            None => RateLimitInfo {
                limit: bucket_effective_limit_from_quota(quota),
                remaining: bucket_effective_limit_from_quota(quota),
                reset_epoch: chrono::Utc::now().timestamp() + 60,
            },
        }
    }

    /// Cleanup stale consumer buckets.
    pub fn cleanup_stale_buckets(&self) {
        let stale_threshold = std::time::Duration::from_secs(self.config.stale_threshold_secs);
        let mut buckets = self.buckets.write();

        let before = buckets.len();
        buckets.retain(|consumer_id, bucket| {
            let keep = bucket.last_activity.elapsed() < stale_threshold;
            if !keep {
                debug!(consumer_id = %consumer_id, "Removing stale consumer rate limit bucket");
            }
            keep
        });

        let removed = before - buckets.len();
        if removed > 0 {
            info!(
                removed = removed,
                remaining = buckets.len(),
                "Cleaned up stale consumer rate limit buckets"
            );
        }
    }

    /// Start background cleanup task.
    pub fn start_cleanup_task(self: Arc<Self>) {
        let limiter = self.clone();
        let interval_secs = self.config.cleanup_interval_secs;
        tokio::spawn(async move {
            let mut cleanup_interval = interval(TokioDuration::from_secs(interval_secs));
            loop {
                cleanup_interval.tick().await;
                limiter.cleanup_stale_buckets();
            }
        });
        info!(
            interval_secs = interval_secs,
            "Consumer rate limiter cleanup task started"
        );
    }

    /// Get current bucket count (for metrics/admin).
    #[allow(dead_code)]
    pub fn bucket_count(&self) -> usize {
        self.buckets.read().len()
    }

    /// Get quota count (for metrics/admin).
    #[allow(dead_code)]
    pub fn quota_count(&self) -> usize {
        self.plan_quotas.read().len()
    }
}

/// Helper to compute effective limit from a quota without a bucket.
#[allow(dead_code)]
fn bucket_effective_limit_from_quota(quota: &PlanQuota) -> u32 {
    if quota.rate_limit_per_second > 0 {
        let burst = if quota.burst_limit > 0 {
            quota.burst_limit
        } else {
            quota.rate_limit_per_second
        };
        if quota.rate_limit_per_minute > 0 {
            burst.min(quota.rate_limit_per_minute)
        } else {
            burst
        }
    } else if quota.rate_limit_per_minute > 0 {
        quota.rate_limit_per_minute
    } else {
        0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_config() -> RateLimiterConfig {
        RateLimiterConfig {
            default_rate_per_minute: 60,
            cleanup_interval_secs: 60,
            stale_threshold_secs: 3600,
        }
    }

    #[test]
    fn test_rate_limiter_allows_within_limit() {
        let limiter = ConsumerRateLimiter::new(test_config());
        limiter.set_plan_quota(
            "consumer-1",
            PlanQuota {
                rate_limit_per_minute: 5,
                ..Default::default()
            },
        );

        for i in 0..5 {
            let result = limiter.check_rate_limit("consumer-1");
            assert!(
                result.is_ok(),
                "Request {} should be allowed, got {:?}",
                i + 1,
                result
            );
        }
    }

    #[test]
    fn test_rate_limiter_blocks_over_limit() {
        let limiter = ConsumerRateLimiter::new(test_config());
        limiter.set_plan_quota(
            "consumer-1",
            PlanQuota {
                rate_limit_per_minute: 3,
                rate_limit_per_second: 0,
                ..Default::default()
            },
        );

        // Exhaust limit
        for _ in 0..3 {
            let result = limiter.check_rate_limit("consumer-1");
            assert!(result.is_ok());
        }

        // Should be blocked
        let result = limiter.check_rate_limit("consumer-1");
        assert!(result.is_err());
        match result.unwrap_err() {
            QuotaError::RateLimit { limit_type, .. } => {
                assert_eq!(limit_type, "per_minute");
            }
            other => panic!("Expected RateLimit, got {:?}", other),
        }
    }

    #[test]
    fn test_separate_consumer_buckets() {
        let limiter = ConsumerRateLimiter::new(test_config());
        limiter.set_plan_quota(
            "consumer-1",
            PlanQuota {
                rate_limit_per_minute: 2,
                rate_limit_per_second: 0,
                ..Default::default()
            },
        );
        limiter.set_plan_quota(
            "consumer-2",
            PlanQuota {
                rate_limit_per_minute: 2,
                rate_limit_per_second: 0,
                ..Default::default()
            },
        );

        // Exhaust consumer-1
        for _ in 0..2 {
            limiter.check_rate_limit("consumer-1").unwrap();
        }
        assert!(limiter.check_rate_limit("consumer-1").is_err());

        // consumer-2 should still be allowed
        assert!(limiter.check_rate_limit("consumer-2").is_ok());
    }

    #[test]
    fn test_per_second_limit() {
        let limiter = ConsumerRateLimiter::new(test_config());
        limiter.set_plan_quota(
            "consumer-1",
            PlanQuota {
                rate_limit_per_second: 2,
                rate_limit_per_minute: 0,
                burst_limit: 2,
                ..Default::default()
            },
        );

        // Allow 2 (burst)
        assert!(limiter.check_rate_limit("consumer-1").is_ok());
        assert!(limiter.check_rate_limit("consumer-1").is_ok());

        // Block 3rd
        let result = limiter.check_rate_limit("consumer-1");
        assert!(result.is_err());
        match result.unwrap_err() {
            QuotaError::RateLimit { limit_type, .. } => {
                assert_eq!(limit_type, "per_second");
            }
            other => panic!("Expected RateLimit, got {:?}", other),
        }
    }

    #[test]
    fn test_unlimited_quota() {
        let limiter = ConsumerRateLimiter::new(test_config());
        limiter.set_plan_quota(
            "consumer-1",
            PlanQuota {
                rate_limit_per_second: 0,
                rate_limit_per_minute: 0,
                ..Default::default()
            },
        );

        // Should always pass
        for _ in 0..100 {
            assert!(limiter.check_rate_limit("consumer-1").is_ok());
        }
    }

    #[test]
    fn test_default_quota_for_unknown_consumer() {
        let config = RateLimiterConfig {
            default_rate_per_minute: 5,
            ..Default::default()
        };
        let limiter = ConsumerRateLimiter::new(config);

        // No explicit quota set — uses default
        for _ in 0..5 {
            assert!(limiter.check_rate_limit("unknown-consumer").is_ok());
        }
        assert!(limiter.check_rate_limit("unknown-consumer").is_err());
    }

    #[test]
    fn test_rate_limit_info_headers() {
        let limiter = ConsumerRateLimiter::new(test_config());
        limiter.set_plan_quota(
            "consumer-1",
            PlanQuota {
                rate_limit_per_minute: 10,
                rate_limit_per_second: 0,
                ..Default::default()
            },
        );

        let info = limiter.check_rate_limit("consumer-1").unwrap();
        assert_eq!(info.limit, 10);
        assert_eq!(info.remaining, 9);
        assert!(info.reset_epoch > 0);
    }

    #[test]
    fn test_cleanup_stale_buckets() {
        let limiter = ConsumerRateLimiter::new(test_config());
        limiter.set_plan_quota(
            "consumer-1",
            PlanQuota {
                rate_limit_per_minute: 100,
                ..Default::default()
            },
        );

        // Create some buckets
        limiter.check_rate_limit("consumer-1").unwrap();

        assert_eq!(limiter.bucket_count(), 1);

        // Cleanup (none should be removed — not stale yet)
        limiter.cleanup_stale_buckets();
        assert_eq!(limiter.bucket_count(), 1);
    }

    #[test]
    fn test_set_and_remove_quota() {
        let limiter = ConsumerRateLimiter::new(test_config());
        limiter.set_plan_quota(
            "consumer-1",
            PlanQuota {
                rate_limit_per_minute: 5,
                ..Default::default()
            },
        );
        assert_eq!(limiter.quota_count(), 1);

        // Create a bucket by checking
        limiter.check_rate_limit("consumer-1").unwrap();
        assert_eq!(limiter.bucket_count(), 1);

        // Remove
        limiter.remove_plan_quota("consumer-1");
        assert_eq!(limiter.quota_count(), 0);
        assert_eq!(limiter.bucket_count(), 0);
    }

    #[test]
    fn test_get_rate_limit_info_no_bucket() {
        let limiter = ConsumerRateLimiter::new(test_config());
        limiter.set_plan_quota(
            "consumer-1",
            PlanQuota {
                rate_limit_per_minute: 100,
                rate_limit_per_second: 0,
                ..Default::default()
            },
        );

        // No bucket yet — should return full quota
        let info = limiter.get_rate_limit_info("consumer-1");
        assert_eq!(info.limit, 100);
        assert_eq!(info.remaining, 100);
    }
}
