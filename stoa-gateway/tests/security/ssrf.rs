//! SSRF protection tests — verify private IP ranges are blocked in dynamic proxy.

use axum::body::Body;
use axum::http::{Request, StatusCode};
use tower::ServiceExt;

use stoa_gateway::config::Config;
use stoa_gateway::proxy::is_blocked_url;
use stoa_gateway::routes::ApiRoute;
use stoa_gateway::state::AppState;

// === Unit tests for is_blocked_url ===

#[test]
fn test_blocked_localhost() {
    assert!(is_blocked_url("http://127.0.0.1:8080/secret"));
    assert!(is_blocked_url("http://localhost:8080/secret"));
    assert!(is_blocked_url("http://127.0.0.1/"));
}

#[test]
fn test_blocked_private_10() {
    assert!(is_blocked_url("http://10.0.0.1/internal"));
    assert!(is_blocked_url("http://10.255.255.255:9200/"));
}

#[test]
fn test_blocked_private_172() {
    assert!(is_blocked_url("http://172.16.0.1/internal"));
    assert!(is_blocked_url("http://172.31.255.255/"));
}

#[test]
fn test_blocked_private_192() {
    assert!(is_blocked_url("http://192.168.0.1/admin"));
    assert!(is_blocked_url("http://192.168.255.255/"));
}

#[test]
fn test_blocked_metadata() {
    // AWS EC2 metadata endpoint
    assert!(is_blocked_url("http://169.254.169.254/latest/meta-data/"));
    // Azure IMDS
    assert!(is_blocked_url("http://169.254.169.254/metadata/instance"));
}

#[test]
fn test_blocked_ipv6_loopback() {
    assert!(is_blocked_url("http://[::1]:8080/"));
}

#[test]
fn test_allowed_public_ip() {
    assert!(!is_blocked_url("http://93.184.216.34/get"));
    assert!(!is_blocked_url("https://httpbin.org/get"));
    assert!(!is_blocked_url("https://api.example.com/v1/data"));
}

#[test]
fn test_blocked_unparseable() {
    assert!(is_blocked_url("not-a-url"));
    assert!(is_blocked_url(""));
}

// === Integration test through the proxy handler ===

fn build_router_with_ssrf_route(backend_url: &str) -> (axum::Router, AppState) {
    let config = Config {
        admin_api_token: Some("test-token".to_string()),
        auto_register: false,
        ..Config::default()
    };
    let state = AppState::new(config);
    state.route_registry.upsert(ApiRoute {
        id: "ssrf-test".to_string(),
        name: "ssrf-api".to_string(),
        tenant_id: "acme".to_string(),
        path_prefix: "/apis/ssrf".to_string(),
        backend_url: backend_url.to_string(),
        methods: vec![],
        spec_hash: "abc".to_string(),
        activated: true,
    });
    let router = stoa_gateway::build_router(state.clone());
    (router, state)
}

/// DoD #10: SSRF blocked — AWS metadata endpoint.
#[tokio::test]
async fn test_ssrf_metadata_blocked() {
    let (router, _) = build_router_with_ssrf_route("http://169.254.169.254/latest/meta-data");

    let request = Request::builder()
        .method("GET")
        .uri("/apis/ssrf/iam/info")
        .body(Body::empty())
        .expect("valid request");

    let response = router.oneshot(request).await.expect("ok");
    assert_eq!(response.status(), StatusCode::FORBIDDEN);

    let body = axum::body::to_bytes(response.into_body(), 1_048_576)
        .await
        .expect("body");
    let body_str = String::from_utf8_lossy(&body);
    assert!(
        body_str.contains("blocked"),
        "Expected blocked message, got: {}",
        body_str
    );
}

/// SSRF blocked — localhost.
#[tokio::test]
async fn test_ssrf_localhost_blocked() {
    let (router, _) = build_router_with_ssrf_route("http://127.0.0.1:8080");

    let request = Request::builder()
        .method("GET")
        .uri("/apis/ssrf/admin")
        .body(Body::empty())
        .expect("valid request");

    let response = router.oneshot(request).await.expect("ok");
    assert_eq!(response.status(), StatusCode::FORBIDDEN);
}

/// SSRF blocked — private IP (10.x).
#[tokio::test]
async fn test_ssrf_private_ip_blocked() {
    let (router, _) = build_router_with_ssrf_route("http://10.0.0.1");

    let request = Request::builder()
        .method("GET")
        .uri("/apis/ssrf/internal")
        .body(Body::empty())
        .expect("valid request");

    let response = router.oneshot(request).await.expect("ok");
    assert_eq!(response.status(), StatusCode::FORBIDDEN);
}
