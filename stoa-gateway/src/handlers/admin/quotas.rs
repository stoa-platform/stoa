//! Quota enforcement admin endpoints (CAB-1121 P4).

use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::IntoResponse,
    Json,
};

use crate::state::AppState;

/// GET /admin/quotas — list all consumer quota stats
pub async fn list_quotas(State(state): State<AppState>) -> Json<Vec<crate::quota::QuotaStats>> {
    Json(state.quota_manager.list_all_stats())
}

/// GET /admin/quotas/:consumer_id — get quota stats for a specific consumer
pub async fn get_consumer_quota(
    State(state): State<AppState>,
    Path(consumer_id): Path<String>,
) -> impl IntoResponse {
    match state.quota_manager.get_stats(&consumer_id) {
        Some(stats) => Json(serde_json::json!(stats)).into_response(),
        None => StatusCode::NOT_FOUND.into_response(),
    }
}

/// POST /admin/quotas/:consumer_id/reset — reset quota counters for a consumer
pub async fn reset_consumer_quota(
    State(state): State<AppState>,
    Path(consumer_id): Path<String>,
) -> impl IntoResponse {
    if state.quota_manager.reset_consumer(&consumer_id) {
        (
            StatusCode::OK,
            Json(
                serde_json::json!({"status": "ok", "message": format!("Quota reset for consumer '{}'", consumer_id)}),
            ),
        )
    } else {
        (
            StatusCode::NOT_FOUND,
            Json(
                serde_json::json!({"status": "error", "message": format!("Consumer '{}' not found", consumer_id)}),
            ),
        )
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
    async fn test_list_quotas_empty() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app.oneshot(auth_req("GET", "/quotas")).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: Vec<serde_json::Value> = serde_json::from_slice(&body).unwrap();
        assert!(data.is_empty());
    }

    #[tokio::test]
    async fn test_get_consumer_quota_not_found() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("GET", "/quotas/unknown-consumer"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn test_reset_consumer_quota_not_found() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("POST", "/quotas/unknown-consumer/reset"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }
}
