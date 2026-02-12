//! Contract tests for OAuth discovery endpoints (RFC 9728, RFC 8414, OIDC).
//!
//! Snapshots lock the well-known metadata response shapes.

use insta::assert_json_snapshot;

use crate::common::TestApp;

#[tokio::test]
async fn test_oauth_protected_resource_shape() {
    let app = TestApp::new();
    let (status, body) = app.get("/.well-known/oauth-protected-resource").await;
    assert_eq!(status, axum::http::StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert_json_snapshot!("oauth-protected-resource", json);
}

#[tokio::test]
async fn test_oauth_authorization_server_shape() {
    let app = TestApp::new();
    let (status, body) = app.get("/.well-known/oauth-authorization-server").await;
    assert_eq!(status, axum::http::StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert_json_snapshot!("oauth-authorization-server", json);
}

#[tokio::test]
async fn test_openid_configuration_unavailable() {
    let app = TestApp::new();
    let (status, body) = app.get("/.well-known/openid-configuration").await;
    assert_eq!(status, axum::http::StatusCode::SERVICE_UNAVAILABLE);
    // OIDC returns plain text error when Keycloak URL is not configured
    insta::assert_snapshot!("openid-configuration-unavailable", body);
}
