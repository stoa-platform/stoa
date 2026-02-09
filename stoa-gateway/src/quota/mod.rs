//! Quota Enforcement Module (Phase 4: CAB-1121)
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
#[allow(unused_imports)]
pub use quota_manager::{QuotaState, QuotaStats};
#[allow(unused_imports)]
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
