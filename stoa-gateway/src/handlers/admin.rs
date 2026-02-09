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
/// `config.admin_api_token`. If no token is configured, returns 503
/// (admin API disabled -- no token configured).
pub async fn admin_auth(
    State(state): State<AppState>,
    request: Request<Body>,
    next: Next,
) -> Result<Response, Response> {
    let expected = match state.config.admin_api_token.as_deref() {
        Some(token) if !token.is_empty() => token,
        _ => {
            warn!("Admin API request rejected: no admin_api_token configured");
            return Err((
                StatusCode::SERVICE_UNAVAILABLE,
                "Admin API disabled - no admin_api_token configured",
            )
                .into_response());
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
        Err(StatusCode::UNAUTHORIZED.into_response())
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
// Circuit Breaker (Phase 6)
// =============================================================================

#[derive(Serialize)]
pub struct CircuitBreakerStatsResponse {
    pub name: String,
    pub state: String,
    pub success_count: u64,
    pub failure_count: u64,
    pub consecutive_failures: u32,
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
        consecutive_failures: stats.consecutive_failures,
        open_count: stats.open_count,
        rejected_count: stats.rejected_count,
    })
}

/// POST /admin/circuit-breaker/reset
pub async fn circuit_breaker_reset(State(state): State<AppState>) -> impl IntoResponse {
    state.cp_circuit_breaker.reset();
    (
        StatusCode::OK,
        Json(serde_json::json!({"status": "ok", "message": "Circuit breaker reset to closed"})),
    )
}

// =============================================================================
// Semantic Cache (Phase 6)
// =============================================================================

#[derive(Serialize)]
pub struct CacheStatsResponse {
    pub hits: u64,
    pub misses: u64,
    pub entry_count: u64,
    pub hit_rate: f64,
}

/// GET /admin/cache/stats
pub async fn cache_stats(State(state): State<AppState>) -> Json<CacheStatsResponse> {
    let stats = state.semantic_cache.stats();
    Json(CacheStatsResponse {
        hits: stats.hits,
        misses: stats.misses,
        entry_count: stats.entry_count,
        hit_rate: stats.hit_rate,
    })
}

/// POST /admin/cache/clear
pub async fn cache_clear(State(state): State<AppState>) -> impl IntoResponse {
    state.semantic_cache.clear().await;
    (
        StatusCode::OK,
        Json(serde_json::json!({"status": "ok", "message": "Cache cleared"})),
    )
}

// =============================================================================
// Session Stats (CAB-362)
// =============================================================================

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

// =============================================================================
// Per-Upstream Circuit Breakers (CAB-362)
// =============================================================================

/// GET /admin/circuit-breakers
pub async fn circuit_breakers_list(
    State(state): State<AppState>,
) -> Json<Vec<crate::resilience::CircuitBreakerStatsEntry>> {
    Json(state.circuit_breakers.stats_all())
}

/// POST /admin/circuit-breakers/:name/reset
pub async fn circuit_breaker_reset_by_name(
    State(state): State<AppState>,
    Path(name): Path<String>,
) -> impl IntoResponse {
    if state.circuit_breakers.reset(&name) {
        (
            StatusCode::OK,
            Json(
                serde_json::json!({"status": "ok", "message": format!("Circuit breaker '{}' reset", name)}),
            ),
        )
    } else {
        (
            StatusCode::NOT_FOUND,
            Json(
                serde_json::json!({"status": "error", "message": format!("Circuit breaker '{}' not found", name)}),
            ),
        )
    }
}

// =============================================================================
// mTLS Admin (CAB-864)
// =============================================================================

/// GET /admin/mtls/config — current mTLS configuration (trusted_proxies redacted)
pub async fn mtls_config(
    State(state): State<AppState>,
) -> Json<crate::auth::mtls::MtlsConfigResponse> {
    Json(crate::auth::mtls::MtlsConfigResponse::from(
        &state.config.mtls,
    ))
}

/// GET /admin/mtls/stats — mTLS validation stats
pub async fn mtls_stats(
    State(state): State<AppState>,
) -> Json<crate::auth::mtls::MtlsStatsSnapshot> {
    Json(state.mtls_stats.snapshot())
}

// =============================================================================
// Quota Enforcement (CAB-1121 P4)
// =============================================================================

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
        routing::{delete, get},
        Router,
    };
    use tower::ServiceExt;

    fn create_test_state(admin_token: Option<&str>) -> AppState {
        let config = Config {
            admin_api_token: admin_token.map(|s| s.to_string()),
            ..Config::default()
        };
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

        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
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
