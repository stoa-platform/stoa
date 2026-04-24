//! Shared test helpers for the admin handler modules.
//!
//! These helpers are used by the per-module `#[cfg(test)] mod tests` blocks
//! across the `admin` module tree. They are visible to any module in the
//! `admin` subtree via `pub(super)`.

use axum::{
    body::Body,
    http::Request,
    middleware,
    routing::{delete, get},
    Router,
};

use super::{
    admin_auth, admin_health, delete_api, delete_policy, get_api, list_apis, list_policies, router,
    upsert_api, upsert_policy,
};
use crate::config::Config;
use crate::state::AppState;

pub(super) fn create_test_state(admin_token: Option<&str>) -> AppState {
    let config = Config {
        admin_api_token: admin_token.map(|s| s.to_string()),
        ..Config::default()
    };
    AppState::new(config)
}

/// Minimal admin router used by legacy tests that only need the
/// `/apis` + `/policies` + `/health` surface. Kept as a narrow harness
/// to avoid compiling every module's handler dependencies when a test
/// only touches the CRUD happy path on apis/policies/health.
pub(super) fn build_admin_router(state: AppState) -> Router {
    Router::new()
        .route("/health", get(admin_health))
        .route("/apis", get(list_apis).post(upsert_api))
        .route("/apis/:id", get(get_api).delete(delete_api))
        .route("/policies", get(list_policies).post(upsert_policy))
        .route("/policies/:id", delete(delete_policy))
        .layer(middleware::from_fn_with_state(state.clone(), admin_auth))
        .with_state(state)
}

/// Production-identical admin router (GW-1 P2-test-1). Delegates to the
/// single factory in `src/handlers/admin/router.rs` so tests exercise
/// the same route set and the same middleware chain (audit → rate-limit
/// → auth) that `lib.rs::build_router` mounts.
pub(super) fn build_full_admin_router(state: AppState) -> Router {
    router::build_admin_router(state.clone()).with_state(state)
}

pub(super) fn auth_req(method: &str, uri: &str) -> Request<Body> {
    Request::builder()
        .method(method)
        .uri(uri)
        .header("Authorization", "Bearer secret")
        .body(Body::empty())
        .unwrap()
}

pub(super) fn auth_json_req(method: &str, uri: &str, body: serde_json::Value) -> Request<Body> {
    Request::builder()
        .method(method)
        .uri(uri)
        .header("Authorization", "Bearer secret")
        .header("Content-Type", "application/json")
        .body(Body::from(serde_json::to_string(&body).unwrap()))
        .unwrap()
}
