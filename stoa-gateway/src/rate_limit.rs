// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
//! Rate Limiting
//!
//! CAB-912: Per-tenant and per-classification rate limiting.
//!
//! Rate limits:
//! - Per tenant: 10 requests/minute (global)
//! - H classification: 50 requests/hour
//! - VH classification: 10 requests/hour
//! - VVH classification: 2 requests/hour

use chrono::{DateTime, Duration, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::RwLock;

use crate::uac::Classification;

// =============================================================================
// Rate Limit Result
// =============================================================================

/// Result of a rate limit check.
#[derive(Debug, Clone, Serialize)]
pub struct RateLimitResult {
    /// Whether the request is allowed
    pub allowed: bool,

    /// Current count in the window
    pub current: u32,

    /// Maximum allowed in the window
    pub limit: u32,

    /// When the window resets
    pub reset_at: DateTime<Utc>,

    /// Time until reset in seconds
    pub retry_after_seconds: i64,
}

impl RateLimitResult {
    fn allowed(current: u32, limit: u32, reset_at: DateTime<Utc>) -> Self {
        Self {
            allowed: true,
            current,
            limit,
            reset_at,
            retry_after_seconds: 0,
        }
    }

    fn denied(current: u32, limit: u32, reset_at: DateTime<Utc>) -> Self {
        let retry_after = (reset_at - Utc::now()).num_seconds().max(0);
        Self {
            allowed: false,
            current,
            limit,
            reset_at,
            retry_after_seconds: retry_after,
        }
    }
}

// =============================================================================
// Rate Limit Bucket
// =============================================================================

/// A sliding window rate limit bucket.
#[derive(Debug, Clone)]
struct RateBucket {
    /// Request timestamps in the current window
    timestamps: Vec<DateTime<Utc>>,

    /// Window duration
    window: Duration,

    /// Maximum requests in window
    limit: u32,
}

impl RateBucket {
    fn new(limit: u32, window: Duration) -> Self {
        Self {
            timestamps: Vec::new(),
            window,
            limit,
        }
    }

    /// Check if a request is allowed and record it if so.
    fn check_and_record(&mut self) -> RateLimitResult {
        let now = Utc::now();
        let window_start = now - self.window;

        // Remove expired entries
        self.timestamps.retain(|t| *t > window_start);

        let current = self.timestamps.len() as u32;
        let reset_at = self
            .timestamps
            .first()
            .map(|t| *t + self.window)
            .unwrap_or(now + self.window);

        if current >= self.limit {
            return RateLimitResult::denied(current, self.limit, reset_at);
        }

        // Record this request
        self.timestamps.push(now);

        RateLimitResult::allowed(current + 1, self.limit, reset_at)
    }

    /// Check without recording (peek).
    fn check(&self) -> RateLimitResult {
        let now = Utc::now();
        let window_start = now - self.window;

        let current = self
            .timestamps
            .iter()
            .filter(|t| **t > window_start)
            .count() as u32;
        let reset_at = self
            .timestamps
            .iter()
            .find(|t| **t > window_start)
            .map(|t| *t + self.window)
            .unwrap_or(now + self.window);

        if current >= self.limit {
            RateLimitResult::denied(current, self.limit, reset_at)
        } else {
            RateLimitResult::allowed(current, self.limit, reset_at)
        }
    }
}

// =============================================================================
// Rate Limiter
// =============================================================================

/// Rate limiter with per-tenant and per-classification limits.
pub struct RateLimiter {
    /// Per-tenant buckets (tenant_id -> bucket)
    tenant_buckets: RwLock<HashMap<String, RateBucket>>,

    /// Per-tenant-classification buckets (tenant_id:classification -> bucket)
    classification_buckets: RwLock<HashMap<String, RateBucket>>,

    /// Configuration
    config: RateLimitConfig,
}

/// Rate limiter configuration.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RateLimitConfig {
    /// Per-tenant limit per minute
    pub tenant_limit_per_minute: u32,

    /// H classification limit per hour
    pub h_limit_per_hour: u32,

    /// VH classification limit per hour
    pub vh_limit_per_hour: u32,

    /// VVH classification limit per hour
    pub vvh_limit_per_hour: u32,
}

impl Default for RateLimitConfig {
    fn default() -> Self {
        Self {
            tenant_limit_per_minute: 10,
            h_limit_per_hour: 50,
            vh_limit_per_hour: 10,
            vvh_limit_per_hour: 2,
        }
    }
}

impl RateLimitConfig {
    /// Get the per-hour limit for a classification.
    pub fn limit_for(&self, classification: Classification) -> u32 {
        match classification {
            Classification::H => self.h_limit_per_hour,
            Classification::VH => self.vh_limit_per_hour,
            Classification::VVH => self.vvh_limit_per_hour,
        }
    }
}

impl RateLimiter {
    /// Create a new rate limiter with default config.
    pub fn new() -> Self {
        Self::with_config(RateLimitConfig::default())
    }

    /// Create a rate limiter with custom config.
    pub fn with_config(config: RateLimitConfig) -> Self {
        Self {
            tenant_buckets: RwLock::new(HashMap::new()),
            classification_buckets: RwLock::new(HashMap::new()),
            config,
        }
    }

    /// Check tenant-level rate limit.
    pub fn check_tenant(&self, tenant_id: &str) -> RateLimitResult {
        let mut buckets = self.tenant_buckets.write().unwrap();
        let bucket = buckets.entry(tenant_id.to_string()).or_insert_with(|| {
            RateBucket::new(self.config.tenant_limit_per_minute, Duration::minutes(1))
        });
        bucket.check_and_record()
    }

    /// Check classification-level rate limit.
    pub fn check_classification(
        &self,
        tenant_id: &str,
        classification: Classification,
    ) -> RateLimitResult {
        let key = format!("{}:{}", tenant_id, classification);
        let limit = self.config.limit_for(classification);

        let mut buckets = self.classification_buckets.write().unwrap();
        let bucket = buckets
            .entry(key)
            .or_insert_with(|| RateBucket::new(limit, Duration::hours(1)));
        bucket.check_and_record()
    }

    /// Check both tenant and classification limits.
    ///
    /// Returns the most restrictive result.
    pub fn check(&self, tenant_id: &str, classification: Classification) -> RateLimitResult {
        // Check tenant limit first
        let tenant_result = self.check_tenant(tenant_id);
        if !tenant_result.allowed {
            return tenant_result;
        }

        // Check classification limit
        self.check_classification(tenant_id, classification)
    }

    /// Peek at current limits without recording.
    pub fn peek(
        &self,
        tenant_id: &str,
        classification: Classification,
    ) -> (RateLimitResult, RateLimitResult) {
        let tenant_result = {
            let buckets = self.tenant_buckets.read().unwrap();
            buckets
                .get(tenant_id)
                .map(|b| b.check())
                .unwrap_or_else(|| {
                    RateLimitResult::allowed(
                        0,
                        self.config.tenant_limit_per_minute,
                        Utc::now() + Duration::minutes(1),
                    )
                })
        };

        let class_result = {
            let key = format!("{}:{}", tenant_id, classification);
            let limit = self.config.limit_for(classification);
            let buckets = self.classification_buckets.read().unwrap();
            buckets.get(&key).map(|b| b.check()).unwrap_or_else(|| {
                RateLimitResult::allowed(0, limit, Utc::now() + Duration::hours(1))
            })
        };

        (tenant_result, class_result)
    }

    /// Get the current configuration.
    pub fn config(&self) -> &RateLimitConfig {
        &self.config
    }

    /// Clear all rate limit buckets (for testing).
    #[cfg(test)]
    pub fn clear(&self) {
        self.tenant_buckets.write().unwrap().clear();
        self.classification_buckets.write().unwrap().clear();
    }
}

impl Default for RateLimiter {
    fn default() -> Self {
        Self::new()
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tenant_rate_limit() {
        let limiter = RateLimiter::new();

        // First 10 requests should succeed
        for i in 0..10 {
            let result = limiter.check_tenant("tenant-1");
            assert!(result.allowed, "Request {} should be allowed", i + 1);
        }

        // 11th request should be denied
        let result = limiter.check_tenant("tenant-1");
        assert!(!result.allowed);
        assert_eq!(result.current, 10);
        assert!(result.retry_after_seconds > 0);
    }

    #[test]
    fn test_classification_rate_limit_vvh() {
        let limiter = RateLimiter::new();

        // VVH allows only 2 per hour
        let result1 = limiter.check_classification("tenant-1", Classification::VVH);
        assert!(result1.allowed);

        let result2 = limiter.check_classification("tenant-1", Classification::VVH);
        assert!(result2.allowed);

        let result3 = limiter.check_classification("tenant-1", Classification::VVH);
        assert!(!result3.allowed);
        assert_eq!(result3.current, 2);
    }

    #[test]
    fn test_different_tenants_separate_limits() {
        let limiter = RateLimiter::new();

        // Exhaust tenant-1's VVH limit
        limiter.check_classification("tenant-1", Classification::VVH);
        limiter.check_classification("tenant-1", Classification::VVH);
        let result = limiter.check_classification("tenant-1", Classification::VVH);
        assert!(!result.allowed);

        // tenant-2 should still have quota
        let result = limiter.check_classification("tenant-2", Classification::VVH);
        assert!(result.allowed);
    }

    #[test]
    fn test_combined_check() {
        let limiter = RateLimiter::new();

        // VVH should hit classification limit before tenant limit
        let result1 = limiter.check("tenant-1", Classification::VVH);
        assert!(result1.allowed);

        let result2 = limiter.check("tenant-1", Classification::VVH);
        assert!(result2.allowed);

        let result3 = limiter.check("tenant-1", Classification::VVH);
        assert!(!result3.allowed);
    }

    #[test]
    fn test_h_classification_limit() {
        let config = RateLimitConfig {
            h_limit_per_hour: 3, // Low limit for testing
            ..Default::default()
        };
        let limiter = RateLimiter::with_config(config);

        for _ in 0..3 {
            let result = limiter.check_classification("tenant-1", Classification::H);
            assert!(result.allowed);
        }

        let result = limiter.check_classification("tenant-1", Classification::H);
        assert!(!result.allowed);
    }

    #[test]
    fn test_peek_does_not_consume() {
        let limiter = RateLimiter::new();

        // Peek should not affect counts
        let (tenant, class) = limiter.peek("tenant-1", Classification::H);
        assert!(tenant.allowed);
        assert!(class.allowed);
        assert_eq!(tenant.current, 0);
        assert_eq!(class.current, 0);

        // Actual check should show 1
        let result = limiter.check("tenant-1", Classification::H);
        assert!(result.allowed);

        // Peek again should show 1 (not 2)
        let (tenant, class) = limiter.peek("tenant-1", Classification::H);
        assert_eq!(tenant.current, 1);
        assert_eq!(class.current, 1);
    }
}
