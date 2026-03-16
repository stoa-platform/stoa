//! Rate Limit Phase — request_filter implementation (CAB-1834)
//!
//! Demonstrates the ProxyPhase trait by wrapping rate-limit logic into a
//! lifecycle phase. Uses a simple in-memory token bucket per tenant.

use async_trait::async_trait;
use axum::http::StatusCode;
use parking_lot::RwLock;
use std::collections::HashMap;
use std::time::Instant;

use super::{PhaseContext, PhaseResult, ProxyPhase};

/// Configuration for the rate limit phase.
#[derive(Debug, Clone)]
pub struct RateLimitPhaseConfig {
    /// Maximum requests per window per tenant.
    pub max_requests: u64,
    /// Window duration in seconds.
    pub window_secs: u64,
}

impl Default for RateLimitPhaseConfig {
    fn default() -> Self {
        Self {
            max_requests: 1000,
            window_secs: 60,
        }
    }
}

struct Bucket {
    count: u64,
    window_start: Instant,
}

/// Rate limiting phase using a per-tenant token bucket.
pub struct RateLimitPhase {
    config: RateLimitPhaseConfig,
    buckets: RwLock<HashMap<String, Bucket>>,
}

impl RateLimitPhase {
    pub fn new(config: RateLimitPhaseConfig) -> Self {
        Self {
            config,
            buckets: RwLock::new(HashMap::new()),
        }
    }
}

#[async_trait]
impl ProxyPhase for RateLimitPhase {
    fn name(&self) -> &str {
        "rate-limit"
    }

    async fn request_filter(&self, ctx: &mut PhaseContext) -> PhaseResult {
        let tenant = match &ctx.tenant_id {
            Some(t) => t.clone(),
            None => return PhaseResult::Continue,
        };

        let window = std::time::Duration::from_secs(self.config.window_secs);
        let mut buckets = self.buckets.write();
        let bucket = buckets.entry(tenant).or_insert_with(|| Bucket {
            count: 0,
            window_start: Instant::now(),
        });

        if bucket.window_start.elapsed() >= window {
            bucket.count = 0;
            bucket.window_start = Instant::now();
        }

        bucket.count += 1;

        if bucket.count > self.config.max_requests {
            let remaining_secs = window
                .checked_sub(bucket.window_start.elapsed())
                .map(|d| d.as_secs())
                .unwrap_or(0);
            ctx.store_set("rate_limit_retry_after", remaining_secs.to_string());
            PhaseResult::Reject {
                status: StatusCode::TOO_MANY_REQUESTS,
                body: "Rate limit exceeded".to_string(),
            }
        } else {
            ctx.store_set(
                "rate_limit_remaining",
                (self.config.max_requests - bucket.count).to_string(),
            );
            PhaseResult::Continue
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::{HeaderMap, Method};

    fn make_ctx(tenant: Option<&str>) -> PhaseContext {
        let mut ctx = PhaseContext::new(Method::GET, "/test".to_string(), HeaderMap::new());
        ctx.tenant_id = tenant.map(|t| t.to_string());
        ctx
    }

    #[tokio::test]
    async fn test_allows_under_limit() {
        let phase = RateLimitPhase::new(RateLimitPhaseConfig {
            max_requests: 5,
            window_secs: 60,
        });

        let mut ctx = make_ctx(Some("acme"));
        let result = phase.request_filter(&mut ctx).await;
        assert!(matches!(result, PhaseResult::Continue));
        assert_eq!(ctx.store_get("rate_limit_remaining"), Some("4"));
    }

    #[tokio::test]
    async fn test_rejects_over_limit() {
        let phase = RateLimitPhase::new(RateLimitPhaseConfig {
            max_requests: 2,
            window_secs: 60,
        });

        let mut ctx1 = make_ctx(Some("acme"));
        let _ = phase.request_filter(&mut ctx1).await;
        let mut ctx2 = make_ctx(Some("acme"));
        let _ = phase.request_filter(&mut ctx2).await;

        let mut ctx3 = make_ctx(Some("acme"));
        let result = phase.request_filter(&mut ctx3).await;
        match result {
            PhaseResult::Reject { status, .. } => {
                assert_eq!(status, StatusCode::TOO_MANY_REQUESTS);
            }
            _ => panic!("expected Reject"),
        }
    }

    #[tokio::test]
    async fn test_skips_without_tenant() {
        let phase = RateLimitPhase::new(RateLimitPhaseConfig::default());
        let mut ctx = make_ctx(None);
        let result = phase.request_filter(&mut ctx).await;
        assert!(matches!(result, PhaseResult::Continue));
    }

    #[tokio::test]
    async fn test_isolated_per_tenant() {
        let phase = RateLimitPhase::new(RateLimitPhaseConfig {
            max_requests: 1,
            window_secs: 60,
        });

        let mut ctx_a = make_ctx(Some("tenant-a"));
        assert!(matches!(
            phase.request_filter(&mut ctx_a).await,
            PhaseResult::Continue
        ));

        // tenant-a is now at limit, but tenant-b should still pass
        let mut ctx_b = make_ctx(Some("tenant-b"));
        assert!(matches!(
            phase.request_filter(&mut ctx_b).await,
            PhaseResult::Continue
        ));
    }
}
