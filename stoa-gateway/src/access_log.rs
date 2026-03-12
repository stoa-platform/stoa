//! Structured Access Log Middleware
//!
//! Emits structured JSON access logs for every request via `tracing::info!`.
//! Runs AFTER auth middleware so that tenant_id and consumer_id are available
//! from request extensions.
//!
//! Output target: `access_log` — can be filtered by Fluent Bit for shipping
//! to OpenSearch's `stoa-logs-*` index.

use axum::{extract::Request, middleware::Next, response::Response};
use std::time::Instant;

use crate::diagnostics::latency::{new_shared_tracker, to_server_timing, Stage};
use crate::telemetry::extract_trace_id;
use crate::trace_context::RequestTraceContext;

/// Paths to skip from access logging (noisy health/metrics endpoints).
const SKIP_PATHS: &[&str] = &[
    "/health",
    "/health/ready",
    "/health/live",
    "/ready",
    "/metrics",
];

/// Access log middleware — emits structured JSON for each request.
///
/// Extracts tenant_id and consumer_id from request extensions (set by auth
/// middleware) when available.
pub async fn access_log_middleware(mut request: Request, next: Next) -> Response {
    let path = request.uri().path().to_string();

    // Skip noisy endpoints
    if SKIP_PATHS.iter().any(|p| path.starts_with(p)) {
        return next.run(request).await;
    }

    let method = request.method().to_string();
    let user_agent = request
        .headers()
        .get("user-agent")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("-")
        .to_string();

    // Extract tenant_id and consumer_id from extensions (set by auth middleware)
    let tenant_id = request
        .extensions()
        .get::<TenantId>()
        .map(|t| t.0.clone())
        .unwrap_or_default();

    let consumer_id = request
        .extensions()
        .get::<ConsumerId>()
        .map(|c| c.0.clone())
        .unwrap_or_default();

    // Extract trace_id from incoming traceparent header (CAB-1455 Phase 2).
    // Priority: incoming traceparent > OTel span context > "-"
    let trace_id_from_header = request
        .extensions()
        .get::<RequestTraceContext>()
        .map(|ctx| ctx.trace_id.clone());

    // Inject a shared LatencyTracker for downstream middlewares to record per-layer timings.
    // Each middleware calls begin_stage()/end_stage() on this tracker via request extensions.
    let tracker = new_shared_tracker();
    request.extensions_mut().insert(tracker.clone());

    let start = Instant::now();
    let mut response = next.run(request).await;
    let duration_ms = start.elapsed().as_secs_f64() * 1000.0;
    let status = response.status().as_u16();

    // Finalize the tracker and emit Server-Timing header (CAB-1790)
    let server_timing = {
        let mut t = tracker.lock().unwrap_or_else(|e| e.into_inner());
        // Record the total transport overhead (access_log layer itself)
        t.record_stage(Stage::Transport, duration_ms);
        let breakdown = t.finalize();
        to_server_timing(&breakdown)
    };
    if let Ok(value) = axum::http::HeaderValue::from_str(&server_timing) {
        response.headers_mut().insert("server-timing", value);
    }

    // Use incoming trace_id if present, else fall back to OTel span context
    let trace_id = trace_id_from_header.unwrap_or_else(extract_trace_id);

    tracing::info!(
        target: "access_log",
        method = %method,
        path = %path,
        status = status,
        duration_ms = format!("{:.2}", duration_ms),
        tenant_id = %tenant_id,
        consumer_id = %consumer_id,
        user_agent = %user_agent,
        trace_id = %trace_id,
        log_type = "access_log",
        server_timing = %server_timing,
        "request completed"
    );

    response
}

/// Marker type for tenant ID stored in request extensions.
#[derive(Clone, Debug)]
pub struct TenantId(pub String);

/// Marker type for consumer ID stored in request extensions.
#[derive(Clone, Debug)]
pub struct ConsumerId(pub String);

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{body::Body, http::StatusCode, routing::get, Router};
    use tower::ServiceExt;

    #[tokio::test]
    async fn test_access_log_skips_health() {
        let app = Router::new()
            .route("/health", get(|| async { "OK" }))
            .layer(axum::middleware::from_fn(access_log_middleware));

        let req = Request::builder()
            .uri("/health")
            .body(Body::empty())
            .expect("request");
        let resp = app.oneshot(req).await.expect("response");
        assert_eq!(resp.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_access_log_passes_through() {
        let app = Router::new()
            .route("/mcp/tools/list", get(|| async { "tools" }))
            .layer(axum::middleware::from_fn(access_log_middleware));

        let req = Request::builder()
            .uri("/mcp/tools/list")
            .body(Body::empty())
            .expect("request");
        let resp = app.oneshot(req).await.expect("response");
        assert_eq!(resp.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_access_log_skips_metrics() {
        let app = Router::new()
            .route("/metrics", get(|| async { "prom" }))
            .layer(axum::middleware::from_fn(access_log_middleware));

        let req = Request::builder()
            .uri("/metrics")
            .body(Body::empty())
            .expect("request");
        let resp = app.oneshot(req).await.expect("response");
        assert_eq!(resp.status(), StatusCode::OK);
    }
}
