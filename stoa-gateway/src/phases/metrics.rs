//! Metrics Phase — logging implementation (CAB-1834)
//!
//! Demonstrates the ProxyPhase trait by recording request metrics in the
//! logging callback. Populates the per-request store with timing data
//! and records structured log output.

use async_trait::async_trait;
use axum::http::StatusCode;

use super::{PhaseContext, PhaseResult, ProxyPhase};

/// Metrics phase that records request timing and status in the logging callback.
pub struct MetricsPhase;

impl MetricsPhase {
    pub fn new() -> Self {
        Self
    }
}

impl Default for MetricsPhase {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl ProxyPhase for MetricsPhase {
    fn name(&self) -> &str {
        "metrics"
    }

    async fn logging(&self, ctx: &mut PhaseContext) -> PhaseResult {
        let elapsed = ctx.elapsed_ms();
        let status = ctx
            .response_status
            .unwrap_or(StatusCode::OK)
            .as_u16()
            .to_string();
        let method = ctx.method.as_str().to_string();
        let path = ctx.path.clone();
        let tenant = ctx.tenant_id.clone().unwrap_or_default();

        ctx.store_set("metrics_latency_ms", format!("{elapsed:.2}"));
        ctx.store_set("metrics_status", status.clone());

        tracing::info!(
            phase = "metrics",
            method = %method,
            path = %path,
            status = %status,
            tenant = %tenant,
            latency_ms = %format!("{elapsed:.2}"),
            "request completed"
        );

        PhaseResult::Continue
    }

    async fn error_handler(&self, ctx: &mut PhaseContext) -> PhaseResult {
        if let Some(ref error) = ctx.error {
            let elapsed = ctx.elapsed_ms();
            let tenant = ctx.tenant_id.clone().unwrap_or_default();

            tracing::error!(
                phase = "metrics",
                method = %ctx.method,
                path = %ctx.path,
                tenant = %tenant,
                error = %error,
                latency_ms = %format!("{elapsed:.2}"),
                "request error"
            );

            ctx.store_set("metrics_error", error.clone());
        }

        PhaseResult::Continue
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::{HeaderMap, Method};

    fn make_ctx() -> PhaseContext {
        let mut ctx = PhaseContext::new(
            Method::POST,
            "/api/v1/tools/call".to_string(),
            HeaderMap::new(),
        );
        ctx.tenant_id = Some("acme".to_string());
        ctx.response_status = Some(StatusCode::OK);
        ctx
    }

    #[tokio::test]
    async fn test_logging_records_metrics() {
        let phase = MetricsPhase::new();
        let mut ctx = make_ctx();

        let result = phase.logging(&mut ctx).await;
        assert!(matches!(result, PhaseResult::Continue));
        assert!(ctx.store_get("metrics_latency_ms").is_some());
        assert_eq!(ctx.store_get("metrics_status"), Some("200"));
    }

    #[tokio::test]
    async fn test_logging_default_status() {
        let phase = MetricsPhase::new();
        let mut ctx = PhaseContext::new(Method::GET, "/test".to_string(), HeaderMap::new());
        // No response_status set — defaults to 200

        let result = phase.logging(&mut ctx).await;
        assert!(matches!(result, PhaseResult::Continue));
        assert_eq!(ctx.store_get("metrics_status"), Some("200"));
    }

    #[tokio::test]
    async fn test_error_handler_records_error() {
        let phase = MetricsPhase::new();
        let mut ctx = make_ctx();
        ctx.error = Some("connection refused".to_string());

        let result = phase.error_handler(&mut ctx).await;
        assert!(matches!(result, PhaseResult::Continue));
        assert_eq!(ctx.store_get("metrics_error"), Some("connection refused"));
    }

    #[tokio::test]
    async fn test_error_handler_noop_without_error() {
        let phase = MetricsPhase::new();
        let mut ctx = make_ctx();

        let result = phase.error_handler(&mut ctx).await;
        assert!(matches!(result, PhaseResult::Continue));
        assert!(ctx.store_get("metrics_error").is_none());
    }
}
