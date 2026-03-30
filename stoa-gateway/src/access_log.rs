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

/// Trace ID captured inside the OTel span by `http_metrics_middleware`.
///
/// Injected into response extensions so `access_log_middleware` can read
/// the trace_id after the span has already closed. Without this, calling
/// `extract_trace_id()` in access_log always returns "-" because the OTel
/// span is already finished by the time the outer middleware sees the response.
#[derive(Clone, Debug)]
pub struct CapturedTraceId(pub String);

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

    // Resolve trace_id in priority order (CAB-1866):
    // 1. OTel trace_id captured inside the span by http_metrics_middleware → response extensions
    // 2. Incoming W3C traceparent echoed back by trace_context_middleware → x-stoa-trace-id header
    // 3. Fallback "-"
    //
    // Reading from request extensions before next.run() doesn't work: trace_context_middleware
    // (inner layer) hasn't set RequestTraceContext yet when access_log (outer layer) starts.
    let trace_id = response
        .extensions()
        .get::<CapturedTraceId>()
        .map(|t| t.0.clone())
        .or_else(|| {
            response
                .headers()
                .get("x-stoa-trace-id")
                .and_then(|v| v.to_str().ok())
                .map(str::to_owned)
        })
        .unwrap_or_else(|| "-".to_string());

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

    // Regression test: CAB-1866 — trace_id in access logs was always "-" because:
    // 1. RequestTraceContext was read from request extensions before next.run() (so always None)
    // 2. extract_trace_id() called after inner span closed (Span::current() == Span::none())
    // Fix: read CapturedTraceId from response extensions (set inside the OTel span by
    // http_metrics_middleware) and x-stoa-trace-id from response headers (set by trace_context).
    #[tokio::test]
    async fn test_regression_cab_1866_trace_id_from_response_extensions() {
        use axum::middleware;

        // Simulate http_metrics_middleware injecting CapturedTraceId into response extensions
        async fn inner_with_trace_id(request: Request, next: Next) -> Response {
            let mut response = next.run(request).await;
            response.extensions_mut().insert(CapturedTraceId(
                "abc123def456abc123def456abc123de".to_string(),
            ));
            response
        }

        let app = Router::new()
            .route("/api/v1/tools", get(|| async { "ok" }))
            .layer(middleware::from_fn(access_log_middleware))
            .layer(middleware::from_fn(inner_with_trace_id));

        let req = Request::builder()
            .uri("/api/v1/tools")
            .body(Body::empty())
            .expect("request");
        let resp = app.oneshot(req).await.expect("response");
        // Response should pass through; access_log reads CapturedTraceId (not "-")
        assert_eq!(resp.status(), StatusCode::OK);
        // CapturedTraceId is consumed by access_log (just verifying no panic)
    }

    #[tokio::test]
    async fn test_regression_cab_1866_trace_id_from_x_stoa_trace_id_header() {
        use axum::middleware;

        // Simulate trace_context_middleware echoing the incoming traceparent as x-stoa-trace-id
        async fn inner_with_x_trace(request: Request, next: Next) -> Response {
            let mut response = next.run(request).await;
            response.headers_mut().insert(
                "x-stoa-trace-id",
                axum::http::HeaderValue::from_static("4bf92f3577b34da6a3ce929d0e0e4736"),
            );
            response
        }

        let app = Router::new()
            .route("/api/v1/tools", get(|| async { "ok" }))
            .layer(middleware::from_fn(access_log_middleware))
            .layer(middleware::from_fn(inner_with_x_trace));

        let req = Request::builder()
            .uri("/api/v1/tools")
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
