//! Security headers tests — verify X-Content-Type-Options, X-Frame-Options, etc.

use axum::body::Body;
use axum::http::{Request, StatusCode};
use tower::ServiceExt;

use stoa_gateway::config::Config;
use stoa_gateway::state::AppState;

/// Helper: send a GET and return the full response (headers accessible).
async fn get_response(router: &axum::Router, uri: &str) -> axum::response::Response {
    let request = Request::builder()
        .method("GET")
        .uri(uri)
        .body(Body::empty())
        .expect("valid request");

    router
        .clone()
        .oneshot(request)
        .await
        .expect("router should not error")
}

fn default_router() -> axum::Router {
    let config = Config {
        auto_register: false,
        ..Config::default()
    };
    let state = AppState::new(config);
    stoa_gateway::build_router(state)
}

/// DoD #15: Security headers present on /health.
#[tokio::test]
async fn test_security_headers_on_health() {
    let router = default_router();
    let response = get_response(&router, "/health").await;

    assert_eq!(response.status(), StatusCode::OK);
    let headers = response.headers();

    assert_eq!(
        headers
            .get("x-content-type-options")
            .map(|v| v.to_str().unwrap_or("")),
        Some("nosniff"),
    );
    assert_eq!(
        headers
            .get("x-frame-options")
            .map(|v| v.to_str().unwrap_or("")),
        Some("DENY"),
    );
    assert_eq!(
        headers
            .get("x-xss-protection")
            .map(|v| v.to_str().unwrap_or("")),
        Some("0"),
    );
    assert_eq!(
        headers
            .get("referrer-policy")
            .map(|v| v.to_str().unwrap_or("")),
        Some("strict-origin-when-cross-origin"),
    );
    assert!(
        headers.get("permissions-policy").is_some(),
        "permissions-policy header should be present"
    );
}

/// Security headers present on MCP endpoint.
#[tokio::test]
async fn test_security_headers_on_mcp() {
    let router = default_router();
    let response = get_response(&router, "/mcp").await;

    let headers = response.headers();
    assert_eq!(
        headers
            .get("x-content-type-options")
            .map(|v| v.to_str().unwrap_or("")),
        Some("nosniff"),
    );
    assert_eq!(
        headers
            .get("x-frame-options")
            .map(|v| v.to_str().unwrap_or("")),
        Some("DENY"),
    );
}

/// DoD #16: No Server header leak (or generic value).
#[tokio::test]
async fn test_no_server_header_leak() {
    let router = default_router();
    let response = get_response(&router, "/health").await;

    let server_header = response.headers().get("server");
    // Either absent or generic (no version info)
    if let Some(value) = server_header {
        let val = value.to_str().unwrap_or("");
        assert!(
            !val.contains("axum") && !val.contains("tokio") && !val.contains("hyper"),
            "Server header should not leak framework info, got: {}",
            val
        );
    }
    // Absent is also fine (preferred)
}

/// Security headers present even on error responses (404).
#[tokio::test]
async fn test_security_headers_on_error() {
    let router = default_router();
    let response = get_response(&router, "/nonexistent-path-xyz").await;

    // Should get 404 (no matching route) but still have security headers
    let headers = response.headers();
    assert_eq!(
        headers
            .get("x-content-type-options")
            .map(|v| v.to_str().unwrap_or("")),
        Some("nosniff"),
    );
    assert_eq!(
        headers
            .get("x-frame-options")
            .map(|v| v.to_str().unwrap_or("")),
        Some("DENY"),
    );
}
