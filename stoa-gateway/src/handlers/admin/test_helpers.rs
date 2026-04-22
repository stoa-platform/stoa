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
    admin_auth, admin_health, cache_clear, cache_stats, circuit_breaker_reset,
    circuit_breaker_reset_by_name, circuit_breaker_stats, circuit_breakers_list, delete_api,
    delete_backend_credential, delete_consumer_credential, delete_contract, delete_policy,
    federation_cache_invalidate, federation_cache_stats, federation_status, federation_upstreams,
    get_api, get_consumer_quota, get_contract, list_apis, list_backend_credentials,
    list_consumer_credentials, list_contracts, list_policies, list_quotas, mtls_config, mtls_stats,
    prompt_cache_get, prompt_cache_invalidate, prompt_cache_load, prompt_cache_patterns,
    prompt_cache_stats, reset_consumer_quota, session_stats, tracing_status, upsert_api,
    upsert_backend_credential, upsert_consumer_credential, upsert_contract, upsert_policy,
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

pub(super) fn build_full_admin_router(state: AppState) -> Router {
    Router::new()
        .route("/health", get(admin_health))
        .route("/apis", get(list_apis).post(upsert_api))
        .route("/apis/:id", get(get_api).delete(delete_api))
        .route("/policies", get(list_policies).post(upsert_policy))
        .route("/policies/:id", delete(delete_policy))
        .route("/circuit-breaker/stats", get(circuit_breaker_stats))
        .route(
            "/circuit-breaker/reset",
            axum::routing::post(circuit_breaker_reset),
        )
        .route("/cache/stats", get(cache_stats))
        .route("/cache/clear", axum::routing::post(cache_clear))
        .route("/sessions/stats", get(session_stats))
        .route("/circuit-breakers", get(circuit_breakers_list))
        .route(
            "/circuit-breakers/:name/reset",
            axum::routing::post(circuit_breaker_reset_by_name),
        )
        .route("/quotas", get(list_quotas))
        .route("/quotas/:consumer_id", get(get_consumer_quota))
        .route(
            "/quotas/:consumer_id/reset",
            axum::routing::post(reset_consumer_quota),
        )
        .route("/mtls/config", get(mtls_config))
        .route("/mtls/stats", get(mtls_stats))
        .route(
            "/backend-credentials",
            get(list_backend_credentials).post(upsert_backend_credential),
        )
        .route(
            "/backend-credentials/:route_id",
            delete(delete_backend_credential),
        )
        .route(
            "/consumer-credentials",
            get(list_consumer_credentials).post(upsert_consumer_credential),
        )
        .route(
            "/consumer-credentials/:route_id/:consumer_id",
            delete(delete_consumer_credential),
        )
        .route("/contracts", get(list_contracts).post(upsert_contract))
        .route("/contracts/:key", get(get_contract).delete(delete_contract))
        .route("/federation/status", get(federation_status))
        .route("/federation/cache", get(federation_cache_stats))
        .route(
            "/federation/cache/:sub_account_id",
            delete(federation_cache_invalidate),
        )
        .route("/prompt-cache/stats", get(prompt_cache_stats))
        .route("/prompt-cache/load", axum::routing::post(prompt_cache_load))
        .route("/prompt-cache/get/:key", get(prompt_cache_get))
        .route(
            "/prompt-cache/invalidate",
            axum::routing::post(prompt_cache_invalidate),
        )
        .route("/prompt-cache/patterns", get(prompt_cache_patterns))
        .route("/tracing/status", get(tracing_status))
        .route("/federation/upstreams", get(federation_upstreams))
        .layer(middleware::from_fn_with_state(state.clone(), admin_auth))
        .with_state(state)
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
