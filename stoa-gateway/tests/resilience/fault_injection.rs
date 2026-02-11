//! Fault injection tests — verify gateway behavior when dependencies are down.
//!
//! Tests that the gateway handles CP/Keycloak unavailability gracefully
//! (no panics, correct status codes).

use crate::common::TestApp;

use axum::body::Body;
use axum::http::{Request, StatusCode};
use stoa_gateway::config::Config;
use stoa_gateway::routes::ApiRoute;
use stoa_gateway::state::AppState;
use tower::ServiceExt;

/// DoD #2: /health returns 200 even when CP is unreachable.
///
/// The health endpoint is a liveness probe — it should always return 200
/// as long as the gateway process is running, regardless of backend health.
#[tokio::test]
async fn test_health_when_cp_down() {
    // Default TestApp has no CP URL configured
    let app = TestApp::new();
    let (status, body) = app.get("/health").await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body, "OK");
}

/// DoD #3 (partial): /ready returns 503 when CP is unreachable.
///
/// The readiness probe checks CP connectivity. If CP is down,
/// the gateway should report NOT READY (not crash).
#[tokio::test]
async fn test_ready_when_cp_down() {
    // Point CP URL to a non-existent endpoint
    let config = Config {
        control_plane_url: Some("http://127.0.0.1:19998".to_string()),
        auto_register: false,
        ..Config::default()
    };
    let state = AppState::new(config);
    let router = stoa_gateway::build_router(state);

    let request = Request::builder()
        .method("GET")
        .uri("/ready")
        .body(Body::empty())
        .expect("valid request");

    let response = router.oneshot(request).await.expect("should not panic");
    assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);

    let body = axum::body::to_bytes(response.into_body(), 1_048_576)
        .await
        .expect("read body");
    let body_str = String::from_utf8_lossy(&body);
    assert!(
        body_str.contains("NOT READY"),
        "Expected NOT READY message, got: {}",
        body_str
    );
}

/// DoD #3 (partial): /ready returns 503 when Keycloak is unreachable.
///
/// If Keycloak OIDC discovery fails, the gateway should report NOT READY.
#[tokio::test]
async fn test_ready_when_keycloak_down() {
    let config = Config {
        // Point to unreachable Keycloak
        keycloak_url: Some("http://127.0.0.1:19997".to_string()),
        keycloak_realm: Some("stoa".to_string()),
        keycloak_client_id: Some("test-client".to_string()),
        keycloak_client_secret: Some("test-secret".to_string()),
        auto_register: false,
        ..Config::default()
    };
    let state = AppState::new(config);
    let router = stoa_gateway::build_router(state);

    let request = Request::builder()
        .method("GET")
        .uri("/ready")
        .body(Body::empty())
        .expect("valid request");

    let response = router.oneshot(request).await.expect("should not panic");
    assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);

    let body = axum::body::to_bytes(response.into_body(), 1_048_576)
        .await
        .expect("read body");
    let body_str = String::from_utf8_lossy(&body);
    assert!(
        body_str.contains("NOT READY"),
        "Expected NOT READY message, got: {}",
        body_str
    );
}

/// Dynamic proxy returns 504 when backend never responds (timeout).
#[tokio::test]
async fn test_proxy_timeout() {
    // Register a route pointing to a host that accepts TCP but never responds.
    // Using a non-routable IP (10.255.255.1) — connect_timeout will fire.
    let config = Config {
        admin_api_token: Some("test-token".to_string()),
        auto_register: false,
        ..Config::default()
    };
    let state = AppState::new(config);
    state.route_registry.upsert(ApiRoute {
        id: "timeout-route".to_string(),
        name: "timeout-api".to_string(),
        tenant_id: "acme".to_string(),
        path_prefix: "/apis/timeout".to_string(),
        backend_url: "http://10.255.255.1:9999".to_string(),
        methods: vec![],
        spec_hash: "abc".to_string(),
        activated: true,
    });
    let router = stoa_gateway::build_router(state);

    let request = Request::builder()
        .method("GET")
        .uri("/apis/timeout/test")
        .body(Body::empty())
        .expect("valid request");

    let response = router.oneshot(request).await.expect("should not panic");
    // Connection timeout → 504 Gateway Timeout or 502 Bad Gateway
    assert!(
        response.status() == StatusCode::GATEWAY_TIMEOUT
            || response.status() == StatusCode::BAD_GATEWAY,
        "Expected 504/502, got {}",
        response.status()
    );
}

/// Dynamic proxy returns 503 for a deactivated route.
#[tokio::test]
async fn test_deactivated_route_returns_503() {
    let config = Config {
        auto_register: false,
        ..Config::default()
    };
    let state = AppState::new(config);
    state.route_registry.upsert(ApiRoute {
        id: "inactive-route".to_string(),
        name: "inactive-api".to_string(),
        tenant_id: "acme".to_string(),
        path_prefix: "/apis/inactive".to_string(),
        backend_url: "http://127.0.0.1:19999".to_string(),
        methods: vec![],
        spec_hash: "abc".to_string(),
        activated: false,
    });
    let router = stoa_gateway::build_router(state);

    let request = Request::builder()
        .method("GET")
        .uri("/apis/inactive/test")
        .body(Body::empty())
        .expect("valid request");

    let response = router.oneshot(request).await.expect("should not panic");
    assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
}

/// Dynamic proxy returns 404 for unknown paths.
#[tokio::test]
async fn test_unknown_route_returns_404() {
    let app = TestApp::new();
    let (status, body) = app.get("/apis/nonexistent/test").await;
    assert_eq!(status, StatusCode::NOT_FOUND);
    assert!(body.contains("No matching API route"));
}
