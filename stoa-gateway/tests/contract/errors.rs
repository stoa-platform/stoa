//! Contract tests for error responses.
//!
//! Snapshots lock the error response shapes for 404 and 401 scenarios.

use insta::assert_snapshot;

use crate::common::{config_with_admin_token, TestApp};

#[tokio::test]
async fn test_404_shape() {
    let app = TestApp::new();
    let (status, body) = app.get("/nonexistent-path").await;
    // Dynamic proxy fallback may return various statuses — snapshot the body
    assert_snapshot!("error-404", format!("status: {}\nbody: {}", status, body));
}

#[tokio::test]
async fn test_admin_401_shape() {
    let config = config_with_admin_token("correct-token");
    let app = TestApp::with_config(config);
    let (status, body) = app.get("/admin/health").await;
    assert_eq!(status, axum::http::StatusCode::UNAUTHORIZED);
    assert_snapshot!("error-admin-401", body);
}
