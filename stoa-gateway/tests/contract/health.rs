//! Contract tests for health and readiness endpoints.
//!
//! Snapshots lock the response shape for /health, /ready, /admin/health.

use insta::assert_snapshot;

use crate::common::{config_with_admin_token, TestApp};

#[tokio::test]
async fn test_health_shape() {
    let app = TestApp::new();
    let (status, body) = app.get("/health").await;
    assert_eq!(status, axum::http::StatusCode::OK);
    // /health returns plain text "OK"
    assert_snapshot!("health-response", body);
}

#[tokio::test]
async fn test_ready_shape() {
    let app = TestApp::new();
    let (status, body) = app.get("/ready").await;
    assert_eq!(status, axum::http::StatusCode::OK);
    // /ready returns plain text "READY"
    assert_snapshot!("ready-response", body);
}

#[tokio::test]
async fn test_admin_health_shape() {
    let config = config_with_admin_token("test-admin-token");
    let app = TestApp::with_config(config);
    let (status, body) = app
        .get_with_bearer("/admin/health", "test-admin-token")
        .await;
    assert_eq!(status, axum::http::StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    insta::assert_json_snapshot!("admin-health", json, {
        ".version" => "[version]",
    });
}
