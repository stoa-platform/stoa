//! Diagnostic endpoint for gateway self-reporting (CAB-1316).
//!
//! Returns in-memory state: circuit breaker stats, route counts, uptime,
//! error classification summary, and recent diagnostic reports.

use axum::extract::{Path, State};
use axum::Json;
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

/// Error category count for summary.
#[derive(Serialize, Deserialize)]
pub struct ErrorCategorySummary {
    pub category: String,
    pub count: usize,
}

/// Full diagnostic response.
#[derive(Serialize, Deserialize)]
pub struct DiagnosticResponse {
    pub circuit_breakers: Vec<CircuitBreakerDiag>,
    pub uptime_seconds: u64,
    pub routes_active: usize,
    pub last_error: Option<LastErrorInfo>,
    pub error_summary: Vec<ErrorCategorySummary>,
    pub recent_errors: usize,
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

    // Aggregate error summary from diagnostic engine
    let summary = state.diagnostic_engine.summary();
    let mut error_summary: Vec<ErrorCategorySummary> = summary
        .into_iter()
        .map(|(cat, count)| ErrorCategorySummary {
            category: format!("{:?}", cat).to_lowercase(),
            count,
        })
        .collect();
    error_summary.sort_by(|a, b| b.count.cmp(&a.count));

    let recent_errors = state.diagnostic_engine.recent_reports(1).len();

    Json(DiagnosticResponse {
        circuit_breakers: cb_stats,
        uptime_seconds: uptime,
        routes_active,
        last_error: None,
        error_summary,
        recent_errors,
    })
}

/// GET /admin/diagnostics/{request_id} — look up a specific diagnostic report.
pub async fn diagnostic_report_handler(
    State(state): State<AppState>,
    Path(request_id): Path<String>,
) -> axum::response::Response {
    use axum::http::StatusCode;
    use axum::response::IntoResponse;

    match state.diagnostic_engine.get_report(&request_id) {
        Some(report) => Json(report).into_response(),
        None => (
            StatusCode::NOT_FOUND,
            Json(serde_json::json!({"error": "diagnostic report not found", "request_id": request_id})),
        )
            .into_response(),
    }
}

/// GET /admin/diagnostics/summary — aggregated error stats.
pub async fn diagnostic_summary_handler(State(state): State<AppState>) -> Json<serde_json::Value> {
    let summary = state.diagnostic_engine.summary();
    let recent = state.diagnostic_engine.recent_reports(20);

    let categories: Vec<serde_json::Value> = summary
        .iter()
        .map(|(cat, count)| {
            serde_json::json!({
                "category": format!("{:?}", cat).to_lowercase(),
                "count": count,
                "display_name": cat.display_name(),
                "suggested_action": cat.suggested_action(),
            })
        })
        .collect();

    let recent_reports: Vec<serde_json::Value> = recent
        .iter()
        .map(|r| {
            serde_json::json!({
                "request_id": r.request_id,
                "category": format!("{:?}", r.error_category).to_lowercase(),
                "status_code": r.request_meta.status_code,
                "path": r.request_meta.path,
                "timestamp": r.request_meta.timestamp,
            })
        })
        .collect();

    Json(serde_json::json!({
        "error_categories": categories,
        "recent_reports": recent_reports,
        "total_reports": summary.values().sum::<usize>(),
    }))
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
        assert!(diag.error_summary.is_empty());
    }

    #[tokio::test]
    async fn test_diagnostic_report_not_found() {
        let state = AppState::new(Config::default());
        let app = Router::new()
            .route(
                "/admin/diagnostics/:request_id",
                get(diagnostic_report_handler),
            )
            .with_state(state);

        let resp = app
            .oneshot(
                Request::builder()
                    .uri("/admin/diagnostics/nonexistent")
                    .body(Body::empty())
                    .expect("request"),
            )
            .await
            .expect("response");

        assert_eq!(resp.status(), 404);
    }

    #[tokio::test]
    async fn test_diagnostic_summary_empty() {
        let state = AppState::new(Config::default());
        let app = Router::new()
            .route(
                "/admin/diagnostics/summary",
                get(diagnostic_summary_handler),
            )
            .with_state(state);

        let resp = app
            .oneshot(
                Request::builder()
                    .uri("/admin/diagnostics/summary")
                    .body(Body::empty())
                    .expect("request"),
            )
            .await
            .expect("response");

        assert_eq!(resp.status(), 200);

        let body = axum::body::to_bytes(resp.into_body(), 1024 * 1024)
            .await
            .expect("body");
        let data: serde_json::Value = serde_json::from_slice(&body).expect("json");
        assert_eq!(data["total_reports"], 0);
    }
}
