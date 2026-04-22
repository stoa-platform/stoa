//! Session stats admin endpoint (CAB-362).

use axum::{extract::State, Json};
use serde::Serialize;

use crate::state::AppState;

#[derive(Serialize)]
pub struct SessionStatsResponse {
    pub active_sessions: usize,
    pub zombie_count: usize,
    pub tracked_sessions: usize,
}

/// GET /admin/sessions/stats
pub async fn session_stats(State(state): State<AppState>) -> Json<SessionStatsResponse> {
    if let Some(ref zd) = state.zombie_detector {
        let stats = zd.stats().await;
        Json(SessionStatsResponse {
            active_sessions: stats.healthy + stats.warning,
            zombie_count: stats.zombie,
            tracked_sessions: stats.total_sessions,
        })
    } else {
        Json(SessionStatsResponse {
            active_sessions: state.session_manager.count(),
            zombie_count: 0,
            tracked_sessions: 0,
        })
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
    async fn test_session_stats() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("GET", "/sessions/stats"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["active_sessions"], 0);
    }
}
