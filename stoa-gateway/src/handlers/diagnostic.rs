//! Diagnostic endpoint for gateway self-reporting (CAB-1316).
//!
//! Returns in-memory state: circuit breaker stats, route counts, uptime,
//! and last error. No database — purely in-memory introspection.

use axum::{extract::State, Json};
use serde::{Deserialize, Serialize};

use crate::state::AppState;

/// Per-circuit-breaker status in the diagnostic response.
#[derive(Serialize, Deserialize)]
pub struct CircuitBreakerDiag {
    pub name: String,
    pub state: String,
    pub failure_count: u64,
    pub success_count: u64,
    pub failures_in_window: u32,
    pub rejected_count: u64,
}

/// Last error seen by the gateway.
#[derive(Serialize, Deserialize)]
pub struct LastErrorInfo {
    pub error_type: String,
    pub message: String,
}

/// Full diagnostic response.
#[derive(Serialize, Deserialize)]
pub struct DiagnosticResponse {
    pub circuit_breakers: Vec<CircuitBreakerDiag>,
    pub uptime_seconds: u64,
    pub routes_active: usize,
    pub last_error: Option<LastErrorInfo>,
}

/// GET /admin/diagnostic — gateway self-diagnostic snapshot.
pub async fn diagnostic_handler(State(state): State<AppState>) -> Json<DiagnosticResponse> {
    let cb_stats: Vec<CircuitBreakerDiag> = state
        .circuit_breakers
        .stats_all()
        .into_iter()
        .map(|entry| CircuitBreakerDiag {
            name: entry.name,
            state: entry.state,
            failure_count: entry.failure_count,
            success_count: entry.success_count,
            failures_in_window: entry.failures_in_window,
            rejected_count: entry.rejected_count,
        })
        .collect();

    let uptime = state.start_time.elapsed().as_secs();
    let routes_active = state.route_registry.count();

    Json(DiagnosticResponse {
        circuit_breakers: cb_stats,
        uptime_seconds: uptime,
        routes_active,
        last_error: None, // Populated from error ring buffer when available
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::Config;
    use crate::state::AppState;
    use axum::{body::Body, http::Request, routing::get, Router};
    use tower::ServiceExt;

    #[tokio::test]
    async fn test_diagnostic_returns_ok() {
        let state = AppState::new(Config::default());
        let app = Router::new()
            .route("/admin/diagnostic", get(diagnostic_handler))
            .with_state(state);

        let resp = app
            .oneshot(
                Request::builder()
                    .uri("/admin/diagnostic")
                    .body(Body::empty())
                    .expect("request"),
            )
            .await
            .expect("response");

        assert_eq!(resp.status(), 200);

        let body = axum::body::to_bytes(resp.into_body(), 1024 * 1024)
            .await
            .expect("body");
        let diag: DiagnosticResponse = serde_json::from_slice(&body).expect("json");
        assert!(diag.uptime_seconds < 5);
        assert_eq!(diag.routes_active, 0);
        assert!(diag.last_error.is_none());
    }
}
