//! Quota and rate limiting integration tests.
//!
//! Tests per-consumer quota enforcement, rate limiting, and admin quota endpoints.

use axum::http::StatusCode;

use crate::common::{config_with_admin_token, config_with_quota, TestApp};

// ========================================================================
// Quota disabled (default)
// ========================================================================

#[tokio::test]
async fn test_quota_disabled_health_always_200() {
    // Default config has quota disabled — health always succeeds
    let app = TestApp::new();
    let (status, _body) = app.get("/health").await;
    assert_eq!(status, StatusCode::OK);
}

#[tokio::test]
async fn test_quota_disabled_mcp_accessible() {
    // With quota disabled, MCP endpoints should work without consumer identity
    let app = TestApp::new();
    let (status, _body) = app.get("/mcp").await;
    assert_eq!(status, StatusCode::OK);
}

// ========================================================================
// Admin Quota endpoints
// ========================================================================

#[tokio::test]
async fn test_admin_list_quotas() {
    let config = config_with_admin_token("test-admin-token");
    let app = TestApp::with_config(config);
    let (status, body) = app
        .get_with_bearer("/admin/quotas", "test-admin-token")
        .await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    // Should return a quota summary object
    assert!(json.is_object() || json.is_array());
}

#[tokio::test]
async fn test_admin_get_consumer_quota_not_found() {
    let config = config_with_admin_token("test-admin-token");
    let app = TestApp::with_config(config);
    let (status, _body) = app
        .get_with_bearer("/admin/quotas/unknown-consumer", "test-admin-token")
        .await;
    // Should return 200 with empty/default quota or 404
    assert!(status == StatusCode::OK || status == StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn test_admin_reset_consumer_quota() {
    let config = config_with_admin_token("test-admin-token");
    let app = TestApp::with_config(config);
    let (status, _body) = app
        .post_json_with_bearer("/admin/quotas/consumer-1/reset", "{}", "test-admin-token")
        .await;
    // Reset returns 200 if consumer exists, 404 if not registered
    assert!(status == StatusCode::OK || status == StatusCode::NOT_FOUND);
}

// ========================================================================
// Quota enforcement enabled
// ========================================================================

#[tokio::test]
async fn test_quota_enabled_health_bypassed() {
    // Health endpoints should bypass quota enforcement
    let config = config_with_quota(10, 100);
    let app = TestApp::with_config(config);
    let (status, body) = app.get("/health").await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body, "OK");
}

#[tokio::test]
async fn test_quota_enabled_metrics_bypassed() {
    // Metrics endpoint should bypass quota enforcement
    let config = config_with_quota(10, 100);
    let app = TestApp::with_config(config);
    let (status, _body) = app.get("/metrics").await;
    assert_eq!(status, StatusCode::OK);
}

#[tokio::test]
async fn test_quota_enabled_mcp_discovery_works() {
    // Discovery endpoints should work even with quota enabled
    // (quota checks consumer identity from auth context, anonymous gets default)
    let config = config_with_quota(60, 10_000);
    let app = TestApp::with_config(config);
    let (status, _body) = app.get("/mcp").await;
    assert_eq!(status, StatusCode::OK);
}
