//! Admin API handlers for Control Plane → Gateway communication.
//!
//! Endpoints:
//!   GET    /admin/health           - Gateway health + stats
//!   POST   /admin/apis             - Register/update an API route
//!   GET    /admin/apis             - List all API routes
//!   GET    /admin/apis/:id         - Get a single API route
//!   DELETE /admin/apis/:id         - Remove an API route
//!   POST   /admin/policies         - Register/update a policy
//!   GET    /admin/policies         - List all policies
//!   DELETE /admin/policies/:id     - Remove a policy
//!
//! All endpoints are protected by bearer token auth (admin_auth middleware).

use axum::{
    body::Body,
    extract::{Path, State},
    http::{header::AUTHORIZATION, Request, StatusCode},
    middleware::Next,
    response::{IntoResponse, Response},
    Json,
};
use serde::Serialize;
use tracing::warn;

use crate::routes::{ApiRoute, PolicyEntry};
use crate::state::AppState;

// =============================================================================
// Admin Auth Middleware
// =============================================================================

/// Bearer token authentication for admin API.
///
/// Validates the `Authorization: Bearer <token>` header against
/// `config.admin_api_token`. If no token is configured, returns 403
/// (admin API disabled).
pub async fn admin_auth(
    State(state): State<AppState>,
    request: Request<Body>,
    next: Next,
) -> Result<Response, StatusCode> {
    let expected = match state.config.admin_api_token.as_deref() {
        Some(token) if !token.is_empty() => token,
        _ => {
            warn!("Admin API request rejected: no admin_api_token configured");
            return Err(StatusCode::FORBIDDEN);
        }
    };

    let auth_header = request
        .headers()
        .get(AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");

    let expected_header = format!("Bearer {}", expected);
    if auth_header == expected_header {
        Ok(next.run(request).await)
    } else {
        warn!("Admin API request rejected: invalid bearer token");
        Err(StatusCode::UNAUTHORIZED)
    }
}

// =============================================================================
// Health
// =============================================================================

#[derive(Serialize)]
pub struct AdminHealthResponse {
    pub status: String,
    pub version: String,
    pub routes_count: usize,
    pub policies_count: usize,
}

pub async fn admin_health(State(state): State<AppState>) -> Json<AdminHealthResponse> {
    Json(AdminHealthResponse {
        status: "ok".to_string(),
        version: env!("CARGO_PKG_VERSION").to_string(),
        routes_count: state.route_registry.count(),
        policies_count: state.policy_registry.count(),
    })
}

// =============================================================================
// API Routes CRUD
// =============================================================================

pub async fn upsert_api(
    State(state): State<AppState>,
    Json(route): Json<ApiRoute>,
) -> impl IntoResponse {
    let id = route.id.clone();
    let existed = state.route_registry.upsert(route).is_some();
    let status = if existed {
        StatusCode::OK
    } else {
        StatusCode::CREATED
    };
    (status, Json(serde_json::json!({"id": id, "status": "ok"})))
}

pub async fn list_apis(State(state): State<AppState>) -> Json<Vec<ApiRoute>> {
    Json(state.route_registry.list())
}

pub async fn get_api(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> impl IntoResponse {
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

// =============================================================================
// Policies CRUD
// =============================================================================

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

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::Config;
    use axum::{
        body::Body,
        http::{Request, StatusCode},
        middleware,
        routing::{delete, get, post},
        Router,
    };
    use tower::ServiceExt;

    fn create_test_state(admin_token: Option<&str>) -> AppState {
        let mut config = Config::default();
        config.admin_api_token = admin_token.map(|s| s.to_string());
        AppState::new(config)
    }

    fn build_admin_router(state: AppState) -> Router {
        Router::new()
            .route("/health", get(admin_health))
            .route("/apis", get(list_apis).post(upsert_api))
            .route("/apis/:id", get(get_api).delete(delete_api))
            .route("/policies", get(list_policies).post(upsert_policy))
            .route("/policies/:id", delete(delete_policy))
            .layer(middleware::from_fn_with_state(state.clone(), admin_auth))
            .with_state(state)
    }

    #[tokio::test]
    async fn test_admin_auth_valid_token() {
        let state = create_test_state(Some("test-secret"));
        let app = build_admin_router(state);

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/health")
                    .header("Authorization", "Bearer test-secret")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_admin_auth_invalid_token() {
        let state = create_test_state(Some("test-secret"));
        let app = build_admin_router(state);

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/health")
                    .header("Authorization", "Bearer wrong-token")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn test_admin_auth_no_token_configured() {
        let state = create_test_state(None);
        let app = build_admin_router(state);

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/health")
                    .header("Authorization", "Bearer anything")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::FORBIDDEN);
    }

    #[tokio::test]
    async fn test_admin_health() {
        let state = create_test_state(Some("secret"));
        let app = build_admin_router(state);

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/health")
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
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["status"], "ok");
        assert!(data["version"].is_string());
        assert_eq!(data["routes_count"], 0);
        assert_eq!(data["policies_count"], 0);
    }

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
