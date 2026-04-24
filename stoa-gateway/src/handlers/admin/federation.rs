//! Federation admin endpoints: status/cache (CAB-1362, CAB-1371) + upstreams (CAB-1752).

use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::IntoResponse,
    Json,
};
use serde::Serialize;

use crate::state::AppState;

// -----------------------------------------------------------------------------
// Status + cache (CAB-1362)
// -----------------------------------------------------------------------------

#[derive(Serialize)]
pub struct FederationStatusResponse {
    pub enabled: bool,
    pub cache_size: u64,
    pub cache_ttl_secs: u64,
}

/// GET /admin/federation/status
pub async fn federation_status(State(state): State<AppState>) -> Json<FederationStatusResponse> {
    Json(FederationStatusResponse {
        enabled: state.config.federation_enabled,
        cache_size: state.federation_cache.entry_count(),
        cache_ttl_secs: state.config.federation_cache_ttl_secs,
    })
}

/// GET /admin/federation/cache
pub async fn federation_cache_stats(
    State(state): State<AppState>,
) -> Json<crate::federation::cache::FederationCacheStats> {
    Json(state.federation_cache.stats())
}

/// DELETE /admin/federation/cache/:sub_account_id -- invalidate cache for a sub-account (CAB-1371)
///
/// GW-1 P2-5: the response reports whether an entry was actually
/// purged. The admin caller previously received a blanket 200 OK with a
/// generic message, so typos or already-evicted ids were indistinguish-
/// able from real invalidations. `invalidated` is computed from a
/// pre-purge `contains` probe; the `status` + `message` fields stay
/// backward-compatible with older tooling.
pub async fn federation_cache_invalidate(
    State(state): State<AppState>,
    Path(sub_account_id): Path<String>,
) -> impl IntoResponse {
    let existed = state.federation_cache.contains(&sub_account_id);
    state.federation_cache.invalidate(&sub_account_id).await;
    (
        StatusCode::OK,
        Json(serde_json::json!({
            "status": "ok",
            "sub_account_id": sub_account_id,
            "invalidated": existed,
            "message": if existed {
                format!("Cache invalidated for sub-account '{}'", sub_account_id)
            } else {
                format!("Cache had no entry for sub-account '{}'", sub_account_id)
            }
        })),
    )
}

// -----------------------------------------------------------------------------
// Upstreams (CAB-1752)
// -----------------------------------------------------------------------------

/// GET /admin/federation/upstreams — list configured upstream MCP servers.
#[derive(Serialize)]
pub struct FederationUpstreamEntry {
    pub url: String,
    pub transport: String,
    pub has_auth: bool,
    pub timeout_secs: u64,
}

pub async fn federation_upstreams(
    State(state): State<AppState>,
) -> Json<FederationUpstreamsResponse> {
    let upstreams: Vec<FederationUpstreamEntry> = state
        .config
        .federation_upstreams
        .iter()
        .map(|u| FederationUpstreamEntry {
            url: u.url.clone(),
            transport: u.transport.clone().unwrap_or_else(|| "sse".to_string()),
            has_auth: u.auth_token.is_some(),
            timeout_secs: u.timeout_secs.unwrap_or(30),
        })
        .collect();

    Json(FederationUpstreamsResponse {
        enabled: state.config.federation_enabled,
        upstream_count: upstreams.len(),
        upstreams,
    })
}

#[derive(Serialize)]
pub struct FederationUpstreamsResponse {
    pub enabled: bool,
    pub upstream_count: usize,
    pub upstreams: Vec<FederationUpstreamEntry>,
}

#[cfg(test)]
mod tests {
    use axum::http::StatusCode;
    use tower::ServiceExt;

    use crate::config::Config;
    use crate::handlers::admin::test_helpers::{
        auth_req, build_full_admin_router, create_test_state,
    };
    use crate::state::AppState;

    #[tokio::test]
    async fn test_federation_cache_invalidate() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("DELETE", "/federation/cache/sub-acct-123"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["status"], "ok");
        assert!(data["message"].as_str().unwrap().contains("sub-acct-123"));
    }

    // GW-1 P2-5: the admin invalidation response must distinguish "entry
    // purged" from "cache had no such key" so operators don't silently
    // accept typos or no-op calls.
    #[tokio::test]
    async fn regression_federation_cache_invalidate_reports_false_when_missing() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("DELETE", "/federation/cache/never-seen"))
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["status"], "ok");
        assert_eq!(data["invalidated"], false);
        assert_eq!(data["sub_account_id"], "never-seen");
        assert!(
            data["message"]
                .as_str()
                .unwrap_or_default()
                .contains("no entry"),
            "message should distinguish 'no entry' from a real purge, got {:?}",
            data["message"]
        );
    }

    #[tokio::test]
    async fn test_federation_status_disabled() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("GET", "/federation/status"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["enabled"], false);
        assert_eq!(data["cache_size"], 0);
        assert_eq!(data["cache_ttl_secs"], 300);
    }

    #[tokio::test]
    async fn test_federation_status_enabled() {
        let config = Config {
            admin_api_token: Some("secret".to_string()),
            federation_enabled: true,
            federation_cache_ttl_secs: 600,
            ..Config::default()
        };
        let state = AppState::new(config);
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("GET", "/federation/status"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["enabled"], true);
        assert_eq!(data["cache_ttl_secs"], 600);
    }

    #[tokio::test]
    async fn test_federation_cache_stats() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("GET", "/federation/cache"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["entries"], 0);
        assert_eq!(data["hits"], 0);
        assert_eq!(data["misses"], 0);
        assert_eq!(data["hit_rate"], 0.0);
    }

    // CAB-1752: Federation upstreams endpoint
    #[tokio::test]
    async fn test_federation_upstreams_empty() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("GET", "/federation/upstreams"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["enabled"], false);
        assert_eq!(data["upstream_count"], 0);
        assert!(data["upstreams"].as_array().unwrap().is_empty());
    }
}
