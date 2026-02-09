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
/// (admin API disabled — no token configured).
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
                "Admin API disabled — no admin_api_token configured",
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
// Circuit Breaker (Phase 6 + CAB-362 per-upstream)
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

/// GET /admin/circuit-breaker/stats — backward compat (returns "cp-api" CB stats)
pub async fn circuit_breaker_stats(
    State(state): State<AppState>,
) -> Json<CircuitBreakerStatsResponse> {
    let cb = state.get_or_create_cb("cp-api");
    let stats = cb.stats();
    Json(CircuitBreakerStatsResponse {
        name: cb.name().to_string(),
        state: stats.state.to_string(),
        success_count: stats.success_count,
        failure_count: stats.failure_count,
        consecutive_failures: stats.consecutive_failures,
        open_count: stats.open_count,
        rejected_count: stats.rejected_count,
    })
}

/// POST /admin/circuit-breaker/reset — backward compat (resets "cp-api" CB)
pub async fn circuit_breaker_reset(State(state): State<AppState>) -> impl IntoResponse {
    let cb = state.get_or_create_cb("cp-api");
    cb.reset();
    (
        StatusCode::OK,
        Json(serde_json::json!({"status": "ok", "message": "Circuit breaker reset to closed"})),
    )
}

/// GET /admin/circuit-breakers — list all per-upstream circuit breakers
pub async fn list_circuit_breakers(
    State(state): State<AppState>,
) -> Json<Vec<CircuitBreakerStatsResponse>> {
    let breakers = state.circuit_breakers.read();
    let mut results: Vec<CircuitBreakerStatsResponse> = breakers
        .values()
        .map(|cb| {
            let stats = cb.stats();
            CircuitBreakerStatsResponse {
                name: cb.name().to_string(),
                state: stats.state.to_string(),
                success_count: stats.success_count,
                failure_count: stats.failure_count,
                consecutive_failures: stats.consecutive_failures,
                open_count: stats.open_count,
                rejected_count: stats.rejected_count,
            }
        })
        .collect();
    // Sort by name for deterministic output
    results.sort_by(|a, b| a.name.cmp(&b.name));
    Json(results)
}

/// POST /admin/circuit-breakers/:upstream_id/reset — reset a specific upstream CB
pub async fn reset_upstream_circuit_breaker(
    State(state): State<AppState>,
    Path(upstream_id): Path<String>,
) -> impl IntoResponse {
    let breakers = state.circuit_breakers.read();
    if let Some(cb) = breakers.get(&upstream_id) {
        cb.reset();
        (
            StatusCode::OK,
            Json(serde_json::json!({
                "status": "ok",
                "message": format!("Circuit breaker '{}' reset to closed", upstream_id)
            })),
        )
            .into_response()
    } else {
        (
            StatusCode::NOT_FOUND,
            Json(serde_json::json!({
                "status": "error",
                "message": format!("Circuit breaker '{}' not found", upstream_id)
            })),
        )
            .into_response()
    }
}

// =============================================================================
// Zombie Detector (CAB-362, ADR-012)
// =============================================================================

/// GET /admin/zombies/stats
pub async fn zombie_stats(State(state): State<AppState>) -> Json<serde_json::Value> {
    let stats = state.zombie_detector.stats().await;
    Json(serde_json::json!({
        "total_sessions": stats.total_sessions,
        "healthy": stats.healthy,
        "warning": stats.warning,
        "expired": stats.expired,
        "zombie": stats.zombie,
        "revoked": stats.revoked,
        "alerts_total": stats.alerts_total,
    }))
}

/// GET /admin/zombies/alerts
pub async fn zombie_alerts(
    State(state): State<AppState>,
    axum::extract::Query(params): axum::extract::Query<std::collections::HashMap<String, String>>,
) -> Json<serde_json::Value> {
    let limit: usize = params
        .get("limit")
        .and_then(|v| v.parse().ok())
        .unwrap_or(50);
    let alerts = state.zombie_detector.recent_alerts(limit).await;
    Json(serde_json::json!({
        "count": alerts.len(),
        "alerts": alerts,
    }))
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
// Quota Admin (Phase 4: CAB-1121)
// =============================================================================

/// GET /admin/quotas — list all consumer quota states
pub async fn list_quotas(State(state): State<AppState>) -> Json<serde_json::Value> {
    let stats = state.quota_manager.list_all_stats();
    Json(serde_json::json!({
        "count": stats.len(),
        "consumers": stats,
        "rate_limiter_buckets": state.consumer_rate_limiter.bucket_count(),
        "quota_enforcement_enabled": state.config.quota_enforcement_enabled,
    }))
}

/// GET /admin/quotas/:consumer_id — specific consumer quota stats
pub async fn get_consumer_quota(
    State(state): State<AppState>,
    Path(consumer_id): Path<String>,
) -> impl IntoResponse {
    match state.quota_manager.get_stats(&consumer_id) {
        Some(stats) => {
            let rate_info = state
                .consumer_rate_limiter
                .get_rate_limit_info(&consumer_id);
            Json(serde_json::json!({
                "consumer_id": consumer_id,
                "quota": stats,
                "rate_limit": {
                    "limit": rate_info.limit,
                    "remaining": rate_info.remaining,
                    "reset_epoch": rate_info.reset_epoch,
                },
            }))
            .into_response()
        }
        None => (
            StatusCode::NOT_FOUND,
            Json(serde_json::json!({"error": "Consumer not found"})),
        )
            .into_response(),
    }
}

/// POST /admin/quotas/:consumer_id/reset — reset quota counters
pub async fn reset_consumer_quota(
    State(state): State<AppState>,
    Path(consumer_id): Path<String>,
) -> impl IntoResponse {
    if state.quota_manager.reset_consumer(&consumer_id) {
        (
            StatusCode::OK,
            Json(serde_json::json!({
                "status": "ok",
                "message": format!("Quota counters reset for consumer '{}'", consumer_id),
            })),
        )
            .into_response()
    } else {
        (
            StatusCode::NOT_FOUND,
            Json(serde_json::json!({
                "status": "error",
                "message": format!("Consumer '{}' not found", consumer_id),
            })),
        )
            .into_response()
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
        use axum::routing::post;

        Router::new()
            .route("/health", get(admin_health))
            .route("/apis", get(list_apis).post(upsert_api))
            .route("/apis/:id", get(get_api).delete(delete_api))
            .route("/policies", get(list_policies).post(upsert_policy))
            .route("/policies/:id", delete(delete_policy))
            // Circuit breaker endpoints (backward compat + per-upstream)
            .route("/circuit-breaker/stats", get(circuit_breaker_stats))
            .route("/circuit-breaker/reset", post(circuit_breaker_reset))
            .route("/circuit-breakers", get(list_circuit_breakers))
            .route(
                "/circuit-breakers/:upstream_id/reset",
                post(reset_upstream_circuit_breaker),
            )
            // Zombie endpoints
            .route("/zombies/stats", get(zombie_stats))
            .route("/zombies/alerts", get(zombie_alerts))
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

    // =========================================================================
    // Circuit Breaker Admin Tests (CAB-362)
    // =========================================================================

    #[tokio::test]
    async fn test_circuit_breaker_stats_backward_compat() {
        let state = create_test_state(Some("secret"));
        let app = build_admin_router(state);

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/circuit-breaker/stats")
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
        assert_eq!(data["name"], "cp-api");
        assert_eq!(data["state"], "closed");
    }

    #[tokio::test]
    async fn test_list_circuit_breakers() {
        let state = create_test_state(Some("secret"));

        // Create a second CB for upstream-payments
        state.get_or_create_cb("upstream-payments");

        let app = build_admin_router(state);

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/circuit-breakers")
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
        assert!(data.len() >= 2); // cp-api + upstream-payments

        // Sorted by name — cp-api first
        assert_eq!(data[0]["name"], "cp-api");
        assert_eq!(data[1]["name"], "upstream-payments");
    }

    #[tokio::test]
    async fn test_reset_upstream_circuit_breaker() {
        let state = create_test_state(Some("secret"));

        // Create and trip a CB
        let cb = state.get_or_create_cb("test-upstream");
        for _ in 0..5 {
            cb.record_failure();
        }
        assert_eq!(cb.stats().state.to_string(), "open");

        let app = build_admin_router(state);

        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/circuit-breakers/test-upstream/reset")
                    .header("Authorization", "Bearer secret")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);

        // Verify it's now closed
        assert_eq!(cb.stats().state.to_string(), "closed");
    }

    #[tokio::test]
    async fn test_reset_upstream_circuit_breaker_not_found() {
        let state = create_test_state(Some("secret"));
        let app = build_admin_router(state);

        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/circuit-breakers/nonexistent/reset")
                    .header("Authorization", "Bearer secret")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    // =========================================================================
    // Zombie Admin Tests (CAB-362)
    // =========================================================================

    #[tokio::test]
    async fn test_zombie_stats_endpoint() {
        let state = create_test_state(Some("secret"));

        // Start some sessions via zombie detector
        state
            .zombie_detector
            .start_session("sess-1", Some("user-1".to_string()), None)
            .await;
        state
            .zombie_detector
            .start_session("sess-2", Some("user-2".to_string()), None)
            .await;

        let app = build_admin_router(state);

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/zombies/stats")
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
        assert_eq!(data["total_sessions"], 2);
        assert_eq!(data["healthy"], 2);
    }

    #[tokio::test]
    async fn test_zombie_alerts_endpoint() {
        let state = create_test_state(Some("secret"));
        let app = build_admin_router(state);

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/zombies/alerts?limit=10")
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
        assert_eq!(data["count"], 0); // No alerts initially
        assert!(data["alerts"].is_array());
    }
}
