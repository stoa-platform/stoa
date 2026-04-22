//! API Routes CRUD admin endpoints.

use std::sync::Arc;

use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::IntoResponse,
    Json,
};
use tracing::warn;
use uuid::Uuid;

use crate::proxy::dynamic::is_blocked_url;
use crate::routes::ApiRoute;
use crate::state::AppState;
use crate::telemetry::deploy::DeployStep;

pub async fn upsert_api(
    State(state): State<AppState>,
    Json(route): Json<ApiRoute>,
) -> impl IntoResponse {
    let deployment_id = Uuid::new_v4();
    let api_id = route.id.clone();
    let tenant = route.tenant_id.clone();
    let emitter = &state.deploy_progress;
    let aid = Some(api_id.as_str());
    let tid = Some(tenant.as_str());

    // Step 1: Validating — input validation + SSRF pre-check (CAB-1920)
    emitter.step_started(
        deployment_id,
        DeployStep::Validating,
        format!("Validating API route '{}'", api_id),
        aid,
        tid,
    );

    // Reject empty or blank required fields
    if route.name.trim().is_empty() {
        warn!(api_id = %api_id, "Admin API rejected: empty name");
        return (
            StatusCode::BAD_REQUEST,
            Json(serde_json::json!({"error": "name must not be empty"})),
        )
            .into_response();
    }
    if route.backend_url.trim().is_empty() {
        warn!(api_id = %api_id, "Admin API rejected: empty backend_url");
        return (
            StatusCode::BAD_REQUEST,
            Json(serde_json::json!({"error": "backend_url must not be empty"})),
        )
            .into_response();
    }

    // SSRF pre-check: block private/internal IPs at registration time,
    // even though trusted_backend bypasses the proxy-time check (CAB-1893).
    // Defense-in-depth: validate before storing, not just before proxying.
    if is_blocked_url(&route.backend_url) {
        warn!(
            api_id = %api_id,
            backend_url = %route.backend_url,
            "Admin API rejected: backend_url targets private/internal IP range"
        );
        return (
            StatusCode::BAD_REQUEST,
            Json(serde_json::json!({
                "error": "backend_url targets a private/internal IP range",
                "detail": "URLs pointing to localhost, RFC 1918, link-local, or IPv6 loopback are not allowed"
            })),
        )
            .into_response();
    }

    emitter.step_completed(
        deployment_id,
        DeployStep::Validating,
        format!("API route '{}' validated", api_id),
        aid,
        tid,
    );

    // Step 2: Applying routes
    emitter.step_started(
        deployment_id,
        DeployStep::ApplyingRoutes,
        format!("Applying route '{}'", api_id),
        aid,
        tid,
    );
    // Mark admin-registered routes as trusted — SSRF check skipped (CAB-1893)
    let mut route = route;
    route.trusted_backend = true;
    let existed = state.route_registry.upsert(route).is_some();
    emitter.step_completed(
        deployment_id,
        DeployStep::ApplyingRoutes,
        format!(
            "Route '{}' {}",
            api_id,
            if existed { "updated" } else { "created" }
        ),
        aid,
        tid,
    );

    // Step 3: Applying policies (no-op for direct route upsert, but signals step)
    emitter.step_started(
        deployment_id,
        DeployStep::ApplyingPolicies,
        "Checking associated policies",
        aid,
        tid,
    );
    emitter.step_completed(
        deployment_id,
        DeployStep::ApplyingPolicies,
        "Policy check complete",
        aid,
        tid,
    );

    // Step 4: Activating
    emitter.step_started(
        deployment_id,
        DeployStep::Activating,
        format!("Activating route '{}'", api_id),
        aid,
        tid,
    );
    emitter.step_completed(
        deployment_id,
        DeployStep::Activating,
        format!("Route '{}' active", api_id),
        aid,
        tid,
    );

    // Step 5: Done
    emitter.step_completed(
        deployment_id,
        DeployStep::Done,
        format!("API sync complete for '{}'", api_id),
        aid,
        tid,
    );

    let status = if existed {
        StatusCode::OK
    } else {
        StatusCode::CREATED
    };
    (
        status,
        Json(serde_json::json!({
            "id": api_id,
            "status": "ok",
            "deployment_id": deployment_id.to_string()
        })),
    )
        .into_response()
}

pub async fn list_apis(State(state): State<AppState>) -> Json<Vec<Arc<ApiRoute>>> {
    Json(state.route_registry.list())
}

pub async fn get_api(State(state): State<AppState>, Path(id): Path<String>) -> impl IntoResponse {
    match state.route_registry.get(&id) {
        Some(route) => Json(route).into_response(),
        None => StatusCode::NOT_FOUND.into_response(),
    }
}

pub async fn delete_api(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> impl IntoResponse {
    match state.route_registry.remove(&id) {
        Some(_) => StatusCode::NO_CONTENT.into_response(),
        None => (StatusCode::NOT_FOUND, "API not found").into_response(),
    }
}

#[cfg(test)]
mod tests {
    use axum::{
        body::Body,
        http::{Request, StatusCode},
    };
    use tower::ServiceExt;

    use crate::handlers::admin::test_helpers::{
        auth_json_req, auth_req, build_admin_router, create_test_state,
    };

    #[tokio::test]
    async fn test_upsert_and_list_api() {
        let state = create_test_state(Some("secret"));
        let app = build_admin_router(state);

        // Upsert a route
        let route = serde_json::json!({
            "id": "r1",
            "name": "payments",
            "tenant_id": "acme",
            "path_prefix": "/apis/acme/payments",
            "backend_url": "https://backend.test",
            "methods": ["GET", "POST"],
            "spec_hash": "abc123",
            "activated": true
        });

        let response = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/apis")
                    .header("Authorization", "Bearer secret")
                    .header("Content-Type", "application/json")
                    .body(Body::from(serde_json::to_string(&route).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::CREATED);

        // List routes
        let response = app
            .oneshot(
                Request::builder()
                    .uri("/apis")
                    .header("Authorization", "Bearer secret")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: Vec<serde_json::Value> = serde_json::from_slice(&body).unwrap();
        assert_eq!(data.len(), 1);
        assert_eq!(data[0]["name"], "payments");
    }

    #[tokio::test]
    async fn test_get_api_not_found() {
        let state = create_test_state(Some("secret"));
        let app = build_admin_router(state);
        let response = app
            .oneshot(auth_req("GET", "/apis/nonexistent"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn test_upsert_update_existing_returns_200() {
        let state = create_test_state(Some("secret"));
        let app = build_admin_router(state);
        let route = serde_json::json!({
            "id": "r1", "name": "payments", "tenant_id": "acme",
            "path_prefix": "/apis/acme/payments", "backend_url": "https://backend.test",
            "methods": ["GET"], "spec_hash": "abc", "activated": true
        });
        // First insert → CREATED
        let _ = app
            .clone()
            .oneshot(auth_json_req("POST", "/apis", route.clone()))
            .await
            .unwrap();
        // Second insert (update) → OK
        let response = app
            .oneshot(auth_json_req("POST", "/apis", route))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_delete_api_not_found() {
        let state = create_test_state(Some("secret"));
        let app = build_admin_router(state);
        let response = app
            .oneshot(auth_req("DELETE", "/apis/ghost"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn test_delete_api() {
        let state = create_test_state(Some("secret"));
        let app = build_admin_router(state);

        // Upsert a route first
        let route = serde_json::json!({
            "id": "r1",
            "name": "payments",
            "tenant_id": "acme",
            "path_prefix": "/apis/acme/payments",
            "backend_url": "https://backend.test",
            "methods": [],
            "spec_hash": "abc",
            "activated": true
        });

        let _ = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/apis")
                    .header("Authorization", "Bearer secret")
                    .header("Content-Type", "application/json")
                    .body(Body::from(serde_json::to_string(&route).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();

        // Delete it
        let response = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("DELETE")
                    .uri("/apis/r1")
                    .header("Authorization", "Bearer secret")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::NO_CONTENT);

        // Verify it's gone
        let response = app
            .oneshot(
                Request::builder()
                    .uri("/apis")
                    .header("Authorization", "Bearer secret")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: Vec<serde_json::Value> = serde_json::from_slice(&body).unwrap();
        assert_eq!(data.len(), 0);
    }
}
