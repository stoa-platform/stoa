//! Circuit breaker admin endpoints: legacy CP (Phase 6) + per-upstream (CAB-362).

use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::IntoResponse,
    Json,
};
use serde::Serialize;

use crate::state::AppState;

// -----------------------------------------------------------------------------
// Legacy Control Plane circuit breaker (Phase 6)
// -----------------------------------------------------------------------------

#[derive(Serialize)]
pub struct CircuitBreakerStatsResponse {
    pub name: String,
    pub state: String,
    pub success_count: u64,
    pub failure_count: u64,
    pub failures_in_window: u32,
    pub open_count: u64,
    pub rejected_count: u64,
}

/// GET /admin/circuit-breaker/stats
pub async fn circuit_breaker_stats(
    State(state): State<AppState>,
) -> Json<CircuitBreakerStatsResponse> {
    let stats = state.cp_circuit_breaker.stats();
    Json(CircuitBreakerStatsResponse {
        name: state.cp_circuit_breaker.name().to_string(),
        state: stats.state.to_string(),
        success_count: stats.success_count,
        failure_count: stats.failure_count,
        failures_in_window: stats.failures_in_window,
        open_count: stats.open_count,
        rejected_count: stats.rejected_count,
    })
}

/// POST /admin/circuit-breaker/reset
///
/// GW-1 P2-6: the response now carries `previous_state` + `new_state`
/// so admins can tell whether the reset actually changed anything
/// (`closed` → `closed` reset is a no-op; `open` → `closed` is a real
/// action). The capture is atomic under the CB write lock — no TOCTOU
/// between reading the previous state and clearing it.
pub async fn circuit_breaker_reset(State(state): State<AppState>) -> impl IntoResponse {
    let previous = state.cp_circuit_breaker.reset_with_previous();
    (
        StatusCode::OK,
        Json(serde_json::json!({
            "status": "ok",
            "previous_state": previous.to_string(),
            "new_state": "closed",
            "message": "Circuit breaker reset to closed",
        })),
    )
}

// -----------------------------------------------------------------------------
// Per-upstream circuit breakers (CAB-362)
// -----------------------------------------------------------------------------

/// GET /admin/circuit-breakers
pub async fn circuit_breakers_list(
    State(state): State<AppState>,
) -> Json<Vec<crate::resilience::CircuitBreakerStatsEntry>> {
    Json(state.circuit_breakers.stats_all())
}

/// POST /admin/circuit-breakers/:name/reset
///
/// GW-1 P2-6: returns `previous_state` + `new_state` on success so the
/// caller knows whether the reset actually changed anything. The
/// registry lookup + reset are atomic under the registry read lock,
/// avoiding the TOCTOU a separate `state_for` + `reset` pair would
/// introduce.
pub async fn circuit_breaker_reset_by_name(
    State(state): State<AppState>,
    Path(name): Path<String>,
) -> impl IntoResponse {
    match state.circuit_breakers.reset_with_previous(&name) {
        Some(previous) => (
            StatusCode::OK,
            Json(serde_json::json!({
                "status": "ok",
                "name": name,
                "previous_state": previous.to_string(),
                "new_state": "closed",
                "message": format!("Circuit breaker '{}' reset", name),
            })),
        ),
        None => (
            StatusCode::NOT_FOUND,
            Json(serde_json::json!({
                "status": "error",
                "name": name,
                "message": format!("Circuit breaker '{}' not found", name),
            })),
        ),
    }
}

#[cfg(test)]
mod tests {
    use axum::http::StatusCode;
    use tower::ServiceExt;

    use crate::handlers::admin::test_helpers::{
        auth_req, build_full_admin_router, create_test_state,
    };

    #[tokio::test]
    async fn test_circuit_breaker_stats() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("GET", "/circuit-breaker/stats"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["state"], "closed");
        assert_eq!(data["success_count"], 0);
    }

    #[tokio::test]
    async fn test_circuit_breaker_reset() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("POST", "/circuit-breaker/reset"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["status"], "ok");
    }

    // GW-1 P2-6: the legacy CP reset response carries previous_state /
    // new_state so admins can tell whether the reset actually changed
    // anything. A closed-to-closed reset is a documented no-op; the
    // fields must still be emitted.
    #[tokio::test]
    async fn regression_circuit_breaker_reset_reports_previous_state() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("POST", "/circuit-breaker/reset"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["new_state"], "closed");
        assert!(
            data["previous_state"].is_string(),
            "previous_state must be serialised, got {:?}",
            data["previous_state"]
        );
    }

    // GW-1 P2-6: per-upstream reset reports previous_state + new_state,
    // and the 404 path carries the name on the error body (the admin
    // can distinguish "no such CB" from any other failure mode).
    #[tokio::test]
    async fn regression_circuit_breaker_reset_by_name_reports_previous_state() {
        use crate::resilience::CircuitBreakerConfig;

        let state = create_test_state(Some("secret"));
        // Seed a breaker so the path is the "found" branch.
        let _cb = state
            .circuit_breakers
            .get_or_create_with_config("my-upstream", CircuitBreakerConfig::default());

        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("POST", "/circuit-breakers/my-upstream/reset"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["name"], "my-upstream");
        assert_eq!(data["new_state"], "closed");
        assert!(data["previous_state"].is_string());
    }

    #[tokio::test]
    async fn test_circuit_breaker_reset_by_name_not_found_carries_name() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("POST", "/circuit-breakers/unknown-cb/reset"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["name"], "unknown-cb");
    }

    #[tokio::test]
    async fn test_circuit_breakers_list_empty() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("GET", "/circuit-breakers"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: Vec<serde_json::Value> = serde_json::from_slice(&body).unwrap();
        assert!(data.is_empty());
    }

    #[tokio::test]
    async fn test_circuit_breaker_reset_by_name_not_found() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("POST", "/circuit-breakers/unknown/reset"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }
}
