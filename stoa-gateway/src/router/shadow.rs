// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
use crate::metrics::Metrics;
use crate::proxy::WebMethodsProxy;
use axum::{
    body::Body,
    extract::{Request, State},
    http::StatusCode,
    response::{IntoResponse, Response},
};
use bytes::Bytes;
use http_body_util::BodyExt;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

/// Maximum body size to buffer for shadow mode (10MB).
const MAX_BODY_SIZE: usize = 10 * 1024 * 1024;

/// Shadow router that duplicates requests to both webMethods and Rust.
///
/// - Primary: webMethods (blocking, response returned to client)
/// - Shadow: Rust native handler (fire-and-forget, metrics only)
#[derive(Clone)]
pub struct ShadowRouter {
    /// webMethods health state
    health_state: Arc<AtomicBool>,
    /// Proxy for forwarding requests to webMethods
    proxy: WebMethodsProxy,
    /// Metrics registry
    metrics: Metrics,
    /// Shadow request timeout
    shadow_timeout: Duration,
    /// Whether shadow mode is enabled
    shadow_enabled: bool,
}

impl ShadowRouter {
    /// Create a new shadow router.
    pub fn new(
        health_state: Arc<AtomicBool>,
        webmethods_url: String,
        metrics: Metrics,
        shadow_timeout: Duration,
        shadow_enabled: bool,
    ) -> Self {
        Self {
            health_state,
            proxy: WebMethodsProxy::new(webmethods_url),
            metrics,
            shadow_timeout,
            shadow_enabled,
        }
    }

    /// Check if webMethods is currently healthy.
    pub fn is_webmethods_healthy(&self) -> bool {
        self.health_state.load(Ordering::SeqCst)
    }
}

/// Handler for routing requests through the shadow router.
///
/// When webMethods is healthy and shadow mode is enabled:
/// 1. Buffer the request body
/// 2. Spawn shadow call to Rust (fire-and-forget)
/// 3. Forward to webMethods (blocking)
/// 4. Return webMethods response
///
/// When webMethods is unhealthy:
/// - Return 503 (P0 behavior, P2 will add native Rust handling)
pub async fn shadow_route_request(
    State(router): State<ShadowRouter>,
    request: Request<Body>,
) -> Response {
    let method = request.method().clone();
    let uri = request.uri().clone();

    if !router.is_webmethods_healthy() {
        // Failover mode: return 503 (P0 behavior)
        tracing::warn!(
            method = %method,
            uri = %uri,
            "webmethods down, returning 503"
        );
        router.metrics.record_failover("webmethods", "rust");
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            "Service temporarily unavailable - webMethods is down",
        )
            .into_response();
    }

    // If shadow mode is disabled, just forward to webMethods
    if !router.shadow_enabled {
        tracing::debug!(
            method = %method,
            uri = %uri,
            "shadow mode disabled, forwarding to webmethods"
        );
        let start = Instant::now();
        let response = router.proxy.forward(request).await;
        let elapsed = start.elapsed();

        let status = response.status().as_u16();
        router
            .metrics
            .record_primary_request("webmethods", elapsed, status);

        return response;
    }

    // Shadow mode enabled: buffer body for cloning
    let (parts, body) = request.into_parts();

    // Collect body bytes with size limit
    let body_bytes: Bytes = match body.collect().await {
        Ok(collected) => {
            let bytes = collected.to_bytes();
            if bytes.len() > MAX_BODY_SIZE {
                tracing::warn!(
                    method = %method,
                    uri = %uri,
                    size = bytes.len(),
                    max = MAX_BODY_SIZE,
                    "request body too large for shadow mode, skipping shadow"
                );
                // Just forward without shadow
                let primary_req = Request::from_parts(parts, Body::from(bytes));
                let start = Instant::now();
                let response = router.proxy.forward(primary_req).await;
                let status = response.status().as_u16();
                router
                    .metrics
                    .record_primary_request("webmethods", start.elapsed(), status);
                return response;
            }
            bytes
        }
        Err(e) => {
            tracing::error!(error = %e, "failed to buffer request body");
            return (StatusCode::BAD_REQUEST, "Failed to read request body").into_response();
        }
    };

    // Clone for shadow request
    let shadow_parts = parts.clone();
    let shadow_body = body_bytes.clone();
    let shadow_uri = uri.clone();
    let shadow_method = method.clone();

    // Spawn shadow call (fire-and-forget)
    let metrics = router.metrics.clone();
    let shadow_timeout = router.shadow_timeout;
    tokio::spawn(async move {
        let shadow_req = Request::from_parts(shadow_parts, Body::from(shadow_body));
        let start = Instant::now();

        // Run shadow request with timeout
        let result = tokio::time::timeout(shadow_timeout, handle_rust_native(shadow_req)).await;

        let elapsed = start.elapsed();
        match result {
            Ok(Ok(response)) => {
                let status = response.status().as_u16();
                tracing::debug!(
                    method = %shadow_method,
                    uri = %shadow_uri,
                    status = status,
                    latency_ms = elapsed.as_millis(),
                    "shadow request completed"
                );
                metrics.record_shadow_request("rust", elapsed, status);
            }
            Ok(Err(e)) => {
                tracing::warn!(
                    method = %shadow_method,
                    uri = %shadow_uri,
                    error = %e,
                    "shadow request failed"
                );
                metrics.record_shadow_request("rust", elapsed, 500);
            }
            Err(_) => {
                tracing::warn!(
                    method = %shadow_method,
                    uri = %shadow_uri,
                    timeout_secs = shadow_timeout.as_secs(),
                    "shadow request timed out"
                );
                metrics.record_shadow_request("rust", elapsed, 504);
            }
        }
    });

    // Primary call (webMethods) - blocking for response
    let primary_req = Request::from_parts(parts, Body::from(body_bytes));
    let start = Instant::now();
    let response = router.proxy.forward(primary_req).await;
    let elapsed = start.elapsed();

    let status = response.status().as_u16();
    tracing::debug!(
        method = %method,
        uri = %uri,
        status = status,
        latency_ms = elapsed.as_millis(),
        "primary request completed"
    );
    router
        .metrics
        .record_primary_request("webmethods", elapsed, status);

    response
}

/// Native Rust handler (placeholder for P2).
///
/// Currently just returns 200 OK with a marker header.
/// P2 will implement actual MCP protocol handling.
async fn handle_rust_native(req: Request<Body>) -> Result<Response<Body>, anyhow::Error> {
    let method = req.method().clone();
    let uri = req.uri().clone();

    tracing::trace!(
        method = %method,
        uri = %uri,
        "handling request with rust native"
    );

    // P2: Implement actual MCP handling
    // For now, just echo back with 200 OK
    Ok(Response::builder()
        .status(200)
        .header("X-Gateway", "rust")
        .header("X-Shadow-Mode", "true")
        .body(Body::from(r#"{"status":"ok","gateway":"rust"}"#))
        .expect("failed to build response"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_shadow_router_healthy() {
        let health_state = Arc::new(AtomicBool::new(true));
        let metrics = Metrics::new();
        let router = ShadowRouter::new(
            health_state,
            "http://localhost:8080".to_string(),
            metrics,
            Duration::from_secs(5),
            true,
        );

        assert!(router.is_webmethods_healthy());
        assert!(router.shadow_enabled);
    }

    #[test]
    fn test_shadow_router_unhealthy() {
        let health_state = Arc::new(AtomicBool::new(false));
        let metrics = Metrics::new();
        let router = ShadowRouter::new(
            health_state,
            "http://localhost:8080".to_string(),
            metrics,
            Duration::from_secs(5),
            true,
        );

        assert!(!router.is_webmethods_healthy());
    }

    #[tokio::test]
    async fn test_rust_native_handler() {
        let req = Request::builder()
            .method("GET")
            .uri("/test")
            .body(Body::empty())
            .unwrap();

        let response = handle_rust_native(req).await.unwrap();
        assert_eq!(response.status(), 200);
        assert_eq!(response.headers().get("X-Gateway").unwrap(), "rust");
    }
}
