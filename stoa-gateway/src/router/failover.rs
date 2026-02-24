// P0 failover router - kept for non-shadow mode deployments
#![allow(dead_code)]

use crate::proxy::WebMethodsProxy;
use axum::{
    body::Body,
    extract::{Request, State},
    http::StatusCode,
    response::{IntoResponse, Response},
};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

/// Failover router that routes requests based on webMethods health.
///
/// When webMethods is healthy, requests are proxied to webMethods.
/// When webMethods is unhealthy, requests return 503 (P0) or route to Rust handler (P1).
#[derive(Clone)]
pub struct FailoverRouter {
    /// webMethods health state
    health_state: Arc<AtomicBool>,
    /// Proxy for forwarding requests to webMethods
    proxy: WebMethodsProxy,
}

impl FailoverRouter {
    /// Create a new failover router.
    ///
    /// # Arguments
    /// * `health_state` - Shared health state from HealthChecker
    /// * `webmethods_url` - Base URL of the webMethods gateway
    pub fn new(health_state: Arc<AtomicBool>, webmethods_url: String) -> Self {
        Self {
            health_state,
            proxy: WebMethodsProxy::new(webmethods_url),
        }
    }

    /// Check if webMethods is currently healthy.
    pub fn is_webmethods_healthy(&self) -> bool {
        self.health_state.load(Ordering::SeqCst)
    }
}

/// Handler for routing requests through the failover router.
///
/// This is the main entry point for API requests.
pub async fn route_request(
    State(router): State<FailoverRouter>,
    request: Request<Body>,
) -> Response {
    if router.is_webmethods_healthy() {
        // Normal mode: proxy to webMethods
        tracing::debug!(
            method = %request.method(),
            uri = %request.uri(),
            "routing to webmethods (healthy)"
        );
        router.proxy.forward(request).await
    } else {
        // Failover mode: return 503 (P0)
        // P1: Route to native Rust handler instead
        tracing::warn!(
            method = %request.method(),
            uri = %request.uri(),
            "webmethods down, returning 503"
        );
        (
            StatusCode::SERVICE_UNAVAILABLE,
            "Service temporarily unavailable - webMethods is down",
        )
            .into_response()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::to_bytes;

    fn make_router(healthy: bool) -> FailoverRouter {
        let health_state = Arc::new(AtomicBool::new(healthy));
        FailoverRouter::new(health_state, "http://localhost:8080".to_string())
    }

    #[test]
    fn test_failover_router_healthy() {
        let router = make_router(true);
        assert!(router.is_webmethods_healthy());
    }

    #[test]
    fn test_failover_router_unhealthy() {
        let router = make_router(false);
        assert!(!router.is_webmethods_healthy());
    }

    #[test]
    fn test_health_state_toggle() {
        let router = make_router(true);
        assert!(router.is_webmethods_healthy());
        router.health_state.store(false, Ordering::SeqCst);
        assert!(!router.is_webmethods_healthy());
        router.health_state.store(true, Ordering::SeqCst);
        assert!(router.is_webmethods_healthy());
    }

    #[test]
    fn test_router_clone_shares_state() {
        let router = make_router(true);
        let cloned = router.clone();
        router.health_state.store(false, Ordering::SeqCst);
        assert!(!cloned.is_webmethods_healthy());
    }

    #[tokio::test]
    async fn test_route_request_unhealthy_returns_503() {
        let router = make_router(false);
        let request = Request::builder()
            .uri("/api/test")
            .body(Body::empty())
            .unwrap();
        let response = route_request(State(router), request).await;
        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
    }

    #[tokio::test]
    async fn test_route_request_unhealthy_body_contains_message() {
        let router = make_router(false);
        let request = Request::builder()
            .uri("/api/test")
            .body(Body::empty())
            .unwrap();
        let response = route_request(State(router), request).await;
        let body = to_bytes(response.into_body(), 1024).await.unwrap();
        let text = std::str::from_utf8(&body).unwrap();
        assert!(text.contains("webMethods is down"));
    }

    #[test]
    fn test_router_with_different_urls() {
        let state = Arc::new(AtomicBool::new(true));
        let r1 = FailoverRouter::new(state.clone(), "http://host-a:5555".to_string());
        let r2 = FailoverRouter::new(state, "http://host-b:5555".to_string());
        assert!(r1.is_webmethods_healthy());
        assert!(r2.is_webmethods_healthy());
    }

    #[tokio::test]
    async fn test_route_request_unhealthy_with_post_method() {
        let router = make_router(false);
        let request = Request::builder()
            .method("POST")
            .uri("/api/submit")
            .body(Body::empty())
            .unwrap();
        let response = route_request(State(router), request).await;
        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
    }

    #[test]
    fn test_concurrent_health_state_access() {
        let router = make_router(true);
        let handles: Vec<_> = (0..10)
            .map(|i| {
                let r = router.clone();
                std::thread::spawn(move || {
                    if i % 2 == 0 {
                        r.health_state.store(false, Ordering::SeqCst);
                    } else {
                        r.health_state.store(true, Ordering::SeqCst);
                    }
                    r.is_webmethods_healthy()
                })
            })
            .collect();
        for h in handles {
            let _ = h.join().unwrap();
        }
    }
}
