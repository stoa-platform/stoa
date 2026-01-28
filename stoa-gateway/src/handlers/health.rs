// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
use axum::{
    extract::State,
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde::Serialize;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

/// Shared application state for health endpoints.
#[derive(Clone)]
pub struct AppState {
    /// webMethods health state (true = healthy)
    pub webmethods_healthy: Arc<AtomicBool>,
    /// Flag indicating if we're shutting down
    pub shutting_down: Arc<AtomicBool>,
}

/// Health check response body.
#[derive(Serialize)]
struct HealthResponse {
    status: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    webmethods_status: Option<&'static str>,
}

/// Kubernetes liveness probe endpoint.
///
/// Returns 200 OK if the process is alive.
/// This endpoint should always return success unless the process is deadlocked.
///
/// # Endpoint
/// `GET /health/live`
pub async fn health_live() -> Response {
    let response = HealthResponse {
        status: "ok",
        webmethods_status: None,
    };
    (StatusCode::OK, Json(response)).into_response()
}

/// Kubernetes readiness probe endpoint.
///
/// Returns 200 OK if the gateway is ready to accept traffic.
/// Returns 503 if:
/// - The gateway is shutting down
/// - webMethods is unhealthy (in failover mode)
///
/// # Endpoint
/// `GET /health/ready`
pub async fn health_ready(State(state): State<AppState>) -> Response {
    // Not ready if shutting down
    if state.shutting_down.load(Ordering::SeqCst) {
        let response = HealthResponse {
            status: "shutting_down",
            webmethods_status: None,
        };
        return (StatusCode::SERVICE_UNAVAILABLE, Json(response)).into_response();
    }

    let webmethods_healthy = state.webmethods_healthy.load(Ordering::SeqCst);
    let webmethods_status = if webmethods_healthy {
        "healthy"
    } else {
        "unhealthy"
    };

    let response = HealthResponse {
        status: if webmethods_healthy { "ok" } else { "degraded" },
        webmethods_status: Some(webmethods_status),
    };

    // Still return 200 even in degraded mode - we can still proxy to webMethods
    // or return 503 ourselves. The gateway itself is operational.
    (StatusCode::OK, Json(response)).into_response()
}

/// Kubernetes startup probe endpoint.
///
/// Returns 200 OK once the gateway has completed initialization.
/// Currently same as liveness, but can be extended for slow startup scenarios.
///
/// # Endpoint
/// `GET /health/startup`
pub async fn health_startup() -> Response {
    let response = HealthResponse {
        status: "ok",
        webmethods_status: None,
    };
    (StatusCode::OK, Json(response)).into_response()
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{
        body::Body,
        http::{Request, StatusCode},
        routing::get,
        Router,
    };
    use tower::ServiceExt;

    fn create_test_state(webmethods_healthy: bool, shutting_down: bool) -> AppState {
        AppState {
            webmethods_healthy: Arc::new(AtomicBool::new(webmethods_healthy)),
            shutting_down: Arc::new(AtomicBool::new(shutting_down)),
        }
    }

    #[tokio::test]
    async fn test_health_live() {
        let app = Router::new().route("/health/live", get(health_live));

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/health/live")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_health_ready_healthy() {
        let state = create_test_state(true, false);
        let app = Router::new()
            .route("/health/ready", get(health_ready))
            .with_state(state);

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/health/ready")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_health_ready_shutting_down() {
        let state = create_test_state(true, true);
        let app = Router::new()
            .route("/health/ready", get(health_ready))
            .with_state(state);

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/health/ready")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
    }
}
