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
pub async fn access_log_middleware(request: Request, next: Next) -> Response {
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

    let start = Instant::now();
    let response = next.run(request).await;
    let duration_ms = start.elapsed().as_secs_f64() * 1000.0;
    let status = response.status().as_u16();

    tracing::info!(
        target: "access_log",
        method = %method,
        path = %path,
        status = status,
        duration_ms = format!("{:.2}", duration_ms),
        tenant_id = %tenant_id,
        consumer_id = %consumer_id,
        user_agent = %user_agent,
        log_type = "access_log",
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
