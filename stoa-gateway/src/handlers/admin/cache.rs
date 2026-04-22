//! Cache admin endpoints: semantic cache (Phase 6) + prompt cache (CAB-1123).

use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::IntoResponse,
    Json,
};
use serde::{Deserialize, Serialize};

use crate::state::AppState;

// -----------------------------------------------------------------------------
// Semantic Cache (Phase 6)
// -----------------------------------------------------------------------------

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

// -----------------------------------------------------------------------------
// Prompt Cache (CAB-1123)
// -----------------------------------------------------------------------------

pub async fn prompt_cache_stats(State(state): State<AppState>) -> Json<serde_json::Value> {
    let stats = state.prompt_cache.stats();
    Json(serde_json::json!({
        "hits": stats.hits,
        "misses": stats.misses,
        "entry_count": stats.entry_count,
        "hit_rate": stats.hit_rate,
    }))
}

#[derive(Deserialize)]
pub struct PromptCacheLoadEntry {
    pub key: String,
    pub value: String,
}

#[derive(Deserialize)]
pub struct PromptCacheLoadPayload {
    pub entries: Vec<PromptCacheLoadEntry>,
}

pub async fn prompt_cache_load(
    State(state): State<AppState>,
    Json(payload): Json<PromptCacheLoadPayload>,
) -> Json<serde_json::Value> {
    let patterns: Vec<(String, String)> = payload
        .entries
        .into_iter()
        .map(|e| (e.key, e.value))
        .collect();
    let count = state.prompt_cache.load_patterns(patterns);
    Json(serde_json::json!({"loaded": count, "status": "ok"}))
}

pub async fn prompt_cache_get(
    State(state): State<AppState>,
    Path(key): Path<String>,
) -> impl IntoResponse {
    match state.prompt_cache.get(&key) {
        Some(value) => (
            StatusCode::OK,
            Json(serde_json::json!({"key": key, "value": value})),
        ),
        None => (
            StatusCode::NOT_FOUND,
            Json(serde_json::json!({"error": "Pattern not found", "key": key})),
        ),
    }
}

pub async fn prompt_cache_invalidate(State(state): State<AppState>) -> Json<serde_json::Value> {
    state.prompt_cache.clear();
    Json(serde_json::json!({"status": "cleared"}))
}

pub async fn prompt_cache_patterns(State(state): State<AppState>) -> Json<serde_json::Value> {
    let keys = state.prompt_cache.list_keys();
    Json(serde_json::json!({"keys": keys, "count": keys.len()}))
}

#[cfg(test)]
mod tests {
    use axum::http::StatusCode;
    use tower::ServiceExt;

    use crate::handlers::admin::test_helpers::{
        auth_json_req, auth_req, build_full_admin_router, create_test_state,
    };

    // ─── Semantic Cache ───────────────────────────────────────────

    #[tokio::test]
    async fn test_cache_stats() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app.oneshot(auth_req("GET", "/cache/stats")).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["hits"], 0);
        assert_eq!(data["misses"], 0);
    }

    #[tokio::test]
    async fn test_cache_clear() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app.oneshot(auth_req("POST", "/cache/clear")).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

    // ─── Prompt Cache (CAB-1123) ──────────────────────────────────

    #[tokio::test]
    async fn test_prompt_cache_stats_empty() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("GET", "/prompt-cache/stats"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["entry_count"], 0);
        assert_eq!(data["hits"], 0);
        assert_eq!(data["misses"], 0);
    }

    #[tokio::test]
    async fn test_prompt_cache_load() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_json_req(
                "POST",
                "/prompt-cache/load",
                serde_json::json!({
                    "entries": [
                        {"key": "greet", "value": "Hello!"},
                        {"key": "bye", "value": "Goodbye!"}
                    ]
                }),
            ))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["loaded"], 2);
    }

    #[tokio::test]
    async fn test_prompt_cache_get_miss() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("GET", "/prompt-cache/get/nonexistent"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn test_prompt_cache_load_then_get() {
        let state = create_test_state(Some("secret"));
        // Load first
        state
            .prompt_cache
            .load_patterns(vec![("hello".into(), "world".into())]);
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("GET", "/prompt-cache/get/hello"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["value"], "world");
    }

    #[tokio::test]
    async fn test_prompt_cache_invalidate() {
        let state = create_test_state(Some("secret"));
        state
            .prompt_cache
            .load_patterns(vec![("x".into(), "y".into())]);
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_json_req(
                "POST",
                "/prompt-cache/invalidate",
                serde_json::json!({}),
            ))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["status"], "cleared");
    }
}
