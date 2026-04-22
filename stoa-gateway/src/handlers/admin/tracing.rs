//! Distributed tracing admin endpoint (CAB-1752).

use axum::{extract::State, Json};
use serde::Serialize;

use crate::state::AppState;

/// GET /admin/tracing/status — OpenTelemetry tracing configuration status.
#[derive(Serialize)]
pub struct TracingStatusResponse {
    pub enabled: bool,
    pub endpoint: Option<String>,
    pub sample_rate: f64,
}

pub async fn tracing_status(State(state): State<AppState>) -> Json<TracingStatusResponse> {
    Json(TracingStatusResponse {
        enabled: state.config.otel_enabled,
        endpoint: state.config.otel_endpoint.clone(),
        sample_rate: state.config.otel_sample_rate,
    })
}

#[cfg(test)]
mod tests {
    use axum::http::StatusCode;
    use tower::ServiceExt;

    use crate::handlers::admin::test_helpers::{
        auth_req, build_full_admin_router, create_test_state,
    };

    // CAB-1752: Tracing status endpoint
    #[tokio::test]
    async fn test_tracing_status() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("GET", "/tracing/status"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["enabled"], true); // CAB-1831: otel_enabled defaults to true
        assert!(data["sample_rate"].is_number());
    }
}
