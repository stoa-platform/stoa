//! Auth pipeline integration tests.
//!
//! Tests authentication and authorization across the full request pipeline:
//! - Health/ready endpoints (no auth required)
//! - Admin endpoints (Bearer token auth)
//! - MCP endpoints (JWT auth context)

use axum::http::StatusCode;

use crate::common::{config_with_admin_token, TestApp};

// ========================================================================
// Health / Ready — no auth required
// ========================================================================

#[tokio::test]
async fn test_health_no_auth_required() {
    let app = TestApp::new();
    let (status, body) = app.get("/health").await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body, "OK");
}

#[tokio::test]
async fn test_ready_no_cp_configured() {
    // Without a control_plane_url, ready should succeed (no CP check)
    let app = TestApp::new();
    let (status, body) = app.get("/ready").await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body, "READY");
}

#[tokio::test]
async fn test_metrics_no_auth_required() {
    let app = TestApp::new();
    let (status, _body) = app.get("/metrics").await;
    assert_eq!(status, StatusCode::OK);
    // Metrics endpoint accessible without auth (body may be empty if no metrics recorded)
}

// ========================================================================
// Admin API — Bearer token auth
// ========================================================================

#[tokio::test]
async fn test_admin_no_token_configured_returns_503() {
    // Config without admin_api_token → admin API disabled → 503
    let app = TestApp::new();
    let (status, _body) = app.get_with_bearer("/admin/health", "any-token").await;
    assert_eq!(status, StatusCode::SERVICE_UNAVAILABLE);
}

#[tokio::test]
async fn test_admin_wrong_token_returns_401() {
    let config = config_with_admin_token("correct-token");
    let app = TestApp::with_config(config);
    let (status, _body) = app.get_with_bearer("/admin/health", "wrong-token").await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn test_admin_missing_header_returns_401() {
    let config = config_with_admin_token("correct-token");
    let app = TestApp::with_config(config);
    // GET without Authorization header
    let (status, _body) = app.get("/admin/health").await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn test_admin_valid_token_returns_200() {
    let config = config_with_admin_token("test-admin-token");
    let app = TestApp::with_config(config);
    let (status, body) = app
        .get_with_bearer("/admin/health", "test-admin-token")
        .await;
    assert_eq!(status, StatusCode::OK);
    // Admin health returns JSON
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert_eq!(json["status"], "ok");
    assert!(json["version"].is_string());
}

#[tokio::test]
async fn test_admin_list_apis_empty() {
    let config = config_with_admin_token("test-admin-token");
    let app = TestApp::with_config(config);
    let (status, body) = app.get_with_bearer("/admin/apis", "test-admin-token").await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert!(json.as_array().expect("array").is_empty());
}

#[tokio::test]
async fn test_admin_list_policies_empty() {
    let config = config_with_admin_token("test-admin-token");
    let app = TestApp::with_config(config);
    let (status, body) = app
        .get_with_bearer("/admin/policies", "test-admin-token")
        .await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert!(json.as_array().expect("array").is_empty());
}

#[tokio::test]
async fn test_admin_cache_stats() {
    let config = config_with_admin_token("test-admin-token");
    let app = TestApp::with_config(config);
    let (status, body) = app
        .get_with_bearer("/admin/cache/stats", "test-admin-token")
        .await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert_eq!(json["hits"], 0);
    assert_eq!(json["misses"], 0);
}
