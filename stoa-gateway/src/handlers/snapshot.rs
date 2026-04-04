//! Snapshot admin endpoints (CAB-1645)
//!
//! CRUD for error snapshots captured by the observability module.

use axum::extract::{Path, Query, State};
use axum::Json;
use serde::{Deserialize, Serialize};

use crate::observability::snapshot::ErrorSnapshot;
use crate::state::AppState;

/// Query parameters for listing snapshots.
#[derive(Debug, Deserialize)]
pub struct ListParams {
    #[serde(default = "default_limit")]
    pub limit: usize,
    #[serde(default)]
    pub offset: usize,
}

fn default_limit() -> usize {
    20
}

/// Response for snapshot listing.
#[derive(Serialize, Deserialize)]
pub struct SnapshotListResponse {
    pub snapshots: Vec<ErrorSnapshot>,
    pub total: usize,
    pub limit: usize,
    pub offset: usize,
}

/// Response for clearing snapshots.
#[derive(Serialize, Deserialize)]
pub struct ClearResponse {
    pub cleared: usize,
}

/// GET /admin/snapshots — list error snapshots with pagination.
pub async fn list_snapshots(
    State(state): State<AppState>,
    Query(params): Query<ListParams>,
) -> Json<SnapshotListResponse> {
    let (snapshots, total) = state.snapshot_store.list(params.limit, params.offset);
    Json(SnapshotListResponse {
        snapshots,
        total,
        limit: params.limit,
        offset: params.offset,
    })
}

/// GET /admin/snapshots/:request_id — get a specific snapshot.
pub async fn get_snapshot(
    State(state): State<AppState>,
    Path(request_id): Path<String>,
) -> axum::response::Response {
    use axum::http::StatusCode;
    use axum::response::IntoResponse;

    match state.snapshot_store.get(&request_id) {
        Some(snapshot) => Json(snapshot).into_response(),
        None => (
            StatusCode::NOT_FOUND,
            Json(serde_json::json!({
                "error": "snapshot not found",
                "request_id": request_id,
            })),
        )
            .into_response(),
    }
}

/// DELETE /admin/snapshots — clear all snapshots.
pub async fn clear_snapshots(State(state): State<AppState>) -> Json<ClearResponse> {
    let cleared = state.snapshot_store.clear();
    Json(ClearResponse { cleared })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::Config;
    use crate::state::AppState;
    use axum::{body::Body, http::Request, routing::get, Router};
    use tower::ServiceExt;

    fn test_state() -> AppState {
        let config = Config {
            snapshot_enabled: true,
            snapshot_max_count: 100,
            snapshot_max_age_secs: 3600,
            ..Config::default()
        };
        AppState::new(config)
    }

    #[tokio::test]
    async fn test_list_empty() {
        let state = test_state();
        let app = Router::new()
            .route("/admin/snapshots", get(list_snapshots))
            .with_state(state);

        let resp = app
            .oneshot(
                Request::builder()
                    .uri("/admin/snapshots")
                    .body(Body::empty())
                    .expect("request"),
            )
            .await
            .expect("response");

        assert_eq!(resp.status(), 200);
        let body = axum::body::to_bytes(resp.into_body(), 1024 * 1024)
            .await
            .expect("body");
        let data: SnapshotListResponse = serde_json::from_slice(&body).expect("json");
        assert_eq!(data.total, 0);
        assert!(data.snapshots.is_empty());
    }

    #[tokio::test]
    async fn test_list_with_items() {
        let state = test_state();

        // Push snapshots directly
        use crate::observability::snapshot::ErrorSnapshot;
        use std::collections::HashMap;
        state.snapshot_store.push(ErrorSnapshot {
            request_id: "req-1".to_string(),
            captured_at: Some(std::time::Instant::now()),
            timestamp: "2026-03-18T12:00:00Z".to_string(),
            method: "POST".to_string(),
            path: "/api/test".to_string(),
            status_code: 500,
            error_category: "backend".to_string(),
            duration_ms: 42.0,
            request_headers: HashMap::new(),
            request_body_excerpt: None,
            response_headers: HashMap::new(),
            response_body_excerpt: None,
            pii_found: false,
        });

        let app = Router::new()
            .route("/admin/snapshots", get(list_snapshots))
            .with_state(state);

        let resp = app
            .oneshot(
                Request::builder()
                    .uri("/admin/snapshots")
                    .body(Body::empty())
                    .expect("request"),
            )
            .await
            .expect("response");

        assert_eq!(resp.status(), 200);
        let body = axum::body::to_bytes(resp.into_body(), 1024 * 1024)
            .await
            .expect("body");
        let data: SnapshotListResponse = serde_json::from_slice(&body).expect("json");
        assert_eq!(data.total, 1);
        assert_eq!(data.snapshots[0].request_id, "req-1");
    }

    #[tokio::test]
    async fn test_list_with_pagination() {
        let state = test_state();

        use crate::observability::snapshot::ErrorSnapshot;
        use std::collections::HashMap;
        for i in 0..5 {
            state.snapshot_store.push(ErrorSnapshot {
                request_id: format!("req-{}", i),
                captured_at: Some(std::time::Instant::now()),
                timestamp: "2026-03-18T12:00:00Z".to_string(),
                method: "GET".to_string(),
                path: "/api/test".to_string(),
                status_code: 500,
                error_category: "backend".to_string(),
                duration_ms: 10.0,
                request_headers: HashMap::new(),
                request_body_excerpt: None,
                response_headers: HashMap::new(),
                response_body_excerpt: None,
                pii_found: false,
            });
        }

        let app = Router::new()
            .route("/admin/snapshots", get(list_snapshots))
            .with_state(state);

        let resp = app
            .oneshot(
                Request::builder()
                    .uri("/admin/snapshots?limit=2&offset=0")
                    .body(Body::empty())
                    .expect("request"),
            )
            .await
            .expect("response");

        let body = axum::body::to_bytes(resp.into_body(), 1024 * 1024)
            .await
            .expect("body");
        let data: SnapshotListResponse = serde_json::from_slice(&body).expect("json");
        assert_eq!(data.total, 5);
        assert_eq!(data.snapshots.len(), 2);
    }

    #[tokio::test]
    async fn test_get_found() {
        let state = test_state();

        use crate::observability::snapshot::ErrorSnapshot;
        use std::collections::HashMap;
        state.snapshot_store.push(ErrorSnapshot {
            request_id: "req-abc".to_string(),
            captured_at: Some(std::time::Instant::now()),
            timestamp: "2026-03-18T12:00:00Z".to_string(),
            method: "POST".to_string(),
            path: "/api/fail".to_string(),
            status_code: 502,
            error_category: "network".to_string(),
            duration_ms: 100.0,
            request_headers: HashMap::new(),
            request_body_excerpt: Some("test body".to_string()),
            response_headers: HashMap::new(),
            response_body_excerpt: None,
            pii_found: false,
        });

        let app = Router::new()
            .route("/admin/snapshots/:request_id", get(get_snapshot))
            .with_state(state);

        let resp = app
            .oneshot(
                Request::builder()
                    .uri("/admin/snapshots/req-abc")
                    .body(Body::empty())
                    .expect("request"),
            )
            .await
            .expect("response");

        assert_eq!(resp.status(), 200);
        let body = axum::body::to_bytes(resp.into_body(), 1024 * 1024)
            .await
            .expect("body");
        let snap: ErrorSnapshot = serde_json::from_slice(&body).expect("json");
        assert_eq!(snap.request_id, "req-abc");
        assert_eq!(snap.status_code, 502);
    }

    #[tokio::test]
    async fn test_get_not_found() {
        let state = test_state();
        let app = Router::new()
            .route("/admin/snapshots/:request_id", get(get_snapshot))
            .with_state(state);

        let resp = app
            .oneshot(
                Request::builder()
                    .uri("/admin/snapshots/nonexistent")
                    .body(Body::empty())
                    .expect("request"),
            )
            .await
            .expect("response");

        assert_eq!(resp.status(), 404);
    }

    #[tokio::test]
    async fn test_clear() {
        let state = test_state();

        use crate::observability::snapshot::ErrorSnapshot;
        use std::collections::HashMap;
        state.snapshot_store.push(ErrorSnapshot {
            request_id: "req-1".to_string(),
            captured_at: Some(std::time::Instant::now()),
            timestamp: "2026-03-18T12:00:00Z".to_string(),
            method: "POST".to_string(),
            path: "/api/test".to_string(),
            status_code: 500,
            error_category: "backend".to_string(),
            duration_ms: 42.0,
            request_headers: HashMap::new(),
            request_body_excerpt: None,
            response_headers: HashMap::new(),
            response_body_excerpt: None,
            pii_found: false,
        });

        let app = Router::new()
            .route("/admin/snapshots", axum::routing::delete(clear_snapshots))
            .with_state(state);

        let resp = app
            .oneshot(
                Request::builder()
                    .method("DELETE")
                    .uri("/admin/snapshots")
                    .body(Body::empty())
                    .expect("request"),
            )
            .await
            .expect("response");

        assert_eq!(resp.status(), 200);
        let body = axum::body::to_bytes(resp.into_body(), 1024 * 1024)
            .await
            .expect("body");
        let data: ClearResponse = serde_json::from_slice(&body).expect("json");
        assert_eq!(data.cleared, 1);
    }
}
