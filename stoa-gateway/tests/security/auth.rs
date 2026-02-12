//! Authentication and authorization security tests.
//!
//! Tests JWT forgery, expired tokens, missing auth, and admin RBAC.

use axum::body::Body;
use axum::http::{Request, StatusCode};
use tower::ServiceExt;

use stoa_gateway::config::Config;
use stoa_gateway::state::AppState;

fn router_with_admin_token(token: &str) -> axum::Router {
    let config = Config {
        admin_api_token: Some(token.to_string()),
        auto_register: false,
        ..Config::default()
    };
    let state = AppState::new(config);
    stoa_gateway::build_router(state)
}

/// DoD #9: Missing auth on /admin/* returns 401.
#[tokio::test]
async fn test_missing_auth_on_admin() {
    let router = router_with_admin_token("super-secret-token");

    let request = Request::builder()
        .method("GET")
        .uri("/admin/health")
        .body(Body::empty())
        .expect("valid request");

    let response = router.oneshot(request).await.expect("ok");
    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
}

/// Invalid bearer token on /admin/* returns 401.
#[tokio::test]
async fn test_invalid_bearer_on_admin() {
    let router = router_with_admin_token("correct-token");

    let request = Request::builder()
        .method("GET")
        .uri("/admin/health")
        .header("Authorization", "Bearer wrong-token")
        .body(Body::empty())
        .expect("valid request");

    let response = router.oneshot(request).await.expect("ok");
    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
}

/// Admin token with different case is rejected (case-sensitive).
#[tokio::test]
async fn test_admin_token_case_sensitive() {
    let router = router_with_admin_token("MySecret");

    let request = Request::builder()
        .method("GET")
        .uri("/admin/health")
        .header("Authorization", "Bearer mysecret")
        .body(Body::empty())
        .expect("valid request");

    let response = router.oneshot(request).await.expect("ok");
    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
}

/// Empty Authorization header is rejected.
#[tokio::test]
async fn test_empty_auth_header() {
    let router = router_with_admin_token("my-token");

    let request = Request::builder()
        .method("GET")
        .uri("/admin/health")
        .header("Authorization", "")
        .body(Body::empty())
        .expect("valid request");

    let response = router.oneshot(request).await.expect("ok");
    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
}

/// "Basic" auth scheme is rejected (only Bearer accepted).
#[tokio::test]
async fn test_basic_auth_rejected() {
    let router = router_with_admin_token("my-token");

    let request = Request::builder()
        .method("GET")
        .uri("/admin/health")
        .header("Authorization", "Basic dXNlcjpwYXNz")
        .body(Body::empty())
        .expect("valid request");

    let response = router.oneshot(request).await.expect("ok");
    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
}
