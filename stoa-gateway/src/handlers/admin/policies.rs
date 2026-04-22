//! Policies CRUD admin endpoints.

use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::IntoResponse,
    Json,
};

use crate::routes::PolicyEntry;
use crate::state::AppState;

pub async fn upsert_policy(
    State(state): State<AppState>,
    Json(policy): Json<PolicyEntry>,
) -> impl IntoResponse {
    let id = policy.id.clone();
    let existed = state.policy_registry.upsert(policy).is_some();
    let status = if existed {
        StatusCode::OK
    } else {
        StatusCode::CREATED
    };
    (status, Json(serde_json::json!({"id": id, "status": "ok"})))
}

pub async fn list_policies(State(state): State<AppState>) -> Json<Vec<PolicyEntry>> {
    Json(state.policy_registry.list())
}

pub async fn delete_policy(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> impl IntoResponse {
    match state.policy_registry.remove(&id) {
        Some(_) => StatusCode::NO_CONTENT.into_response(),
        None => (StatusCode::NOT_FOUND, "Policy not found").into_response(),
    }
}

#[cfg(test)]
mod tests {
    use axum::http::StatusCode;
    use tower::ServiceExt;

    use crate::handlers::admin::test_helpers::{
        auth_json_req, auth_req, build_full_admin_router, create_test_state,
    };

    #[tokio::test]
    async fn test_upsert_and_list_policies() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let policy = serde_json::json!({
            "id": "p1", "name": "rate-limit",
            "policy_type": "rate_limit", "config": {"limit": 100},
            "priority": 1, "api_id": "r1"
        });
        let response = app
            .clone()
            .oneshot(auth_json_req("POST", "/policies", policy))
            .await
            .unwrap();
        assert!(response.status() == StatusCode::CREATED || response.status() == StatusCode::OK);
        let response = app.oneshot(auth_req("GET", "/policies")).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: Vec<serde_json::Value> = serde_json::from_slice(&body).unwrap();
        assert_eq!(data.len(), 1);
    }

    #[tokio::test]
    async fn test_delete_policy_not_found() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("DELETE", "/policies/ghost"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }
}
