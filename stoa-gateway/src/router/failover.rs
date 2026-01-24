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

    #[test]
    fn test_failover_router_healthy() {
        let health_state = Arc::new(AtomicBool::new(true));
        let router = FailoverRouter::new(health_state, "http://localhost:8080".to_string());

        assert!(router.is_webmethods_healthy());
    }

    #[test]
    fn test_failover_router_unhealthy() {
        let health_state = Arc::new(AtomicBool::new(false));
        let router = FailoverRouter::new(health_state, "http://localhost:8080".to_string());

        assert!(!router.is_webmethods_healthy());
    }
}
