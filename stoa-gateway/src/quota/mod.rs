//! Quota Enforcement Module (Phase 4: CAB-1121)
//!
//! Per-consumer rate limiting and daily/monthly quota tracking.
//!
//! Per-consumer rate limiting and quota tracking for plan-based API access.
//!
//! # Architecture
//!
//! ```text
//! Request → Auth → QuotaMiddleware → Handler
//!                       │
//!              ┌────────┴────────┐
//!              │                 │
//!         RateLimiter      QuotaManager
//!        (token bucket)   (daily/monthly)
//!              │                 │
//!         per-second/min   daily/monthly
//!         burst limit      request limits
//! ```
//!
//! Both components use in-memory state with `parking_lot::RwLock` for
//! thread-safe access without poisoning risk.

mod middleware;
mod quota_manager;
mod rate_limiter;

pub use middleware::quota_middleware;
pub use quota_manager::{QuotaManager, QuotaManagerConfig};
pub use quota_manager::{QuotaState, QuotaStats};
pub use rate_limiter::PlanQuota;
pub use rate_limiter::{ConsumerRateLimiter, RateLimiterConfig};

/// Errors returned by quota enforcement.
///
/// Variant naming avoids the "Exceeded" postfix to satisfy clippy::enum_variant_names.
/// The error context (rate limit vs quota) is clear from the variant name + fields.
#[derive(Debug, thiserror::Error)]
pub enum QuotaError {
    /// Per-second or per-minute rate limit exceeded.
    #[error("rate limit exceeded: {limit_type} limit of {limit} reached")]
    RateLimit {
        limit_type: String,
        limit: u32,
        retry_after_secs: u64,
    },

    /// Daily request quota exhausted.
    #[error("daily quota exceeded: {used}/{limit} requests used")]
    DailyQuota { used: u64, limit: u32 },

    /// Monthly request quota exhausted.
    #[error("monthly quota exceeded: {used}/{limit} requests used")]
    MonthlyQuota { used: u64, limit: u32 },
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rate_limit_error_display() {
        let err = QuotaError::RateLimit {
            limit_type: "per_minute".to_string(),
            limit: 60,
            retry_after_secs: 5,
        };
        assert_eq!(
            err.to_string(),
            "rate limit exceeded: per_minute limit of 60 reached"
        );
    }

    #[test]
    fn daily_quota_error_display() {
        let err = QuotaError::DailyQuota {
            used: 1000,
            limit: 1000,
        };
        assert_eq!(
            err.to_string(),
            "daily quota exceeded: 1000/1000 requests used"
        );
    }

    #[test]
    fn monthly_quota_error_display() {
        let err = QuotaError::MonthlyQuota {
            used: 50000,
            limit: 50000,
        };
        assert_eq!(
            err.to_string(),
            "monthly quota exceeded: 50000/50000 requests used"
        );
    }
}
