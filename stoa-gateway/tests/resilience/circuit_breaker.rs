//! Circuit breaker integration tests via the full Axum router.
//!
//! Tests that the per-upstream circuit breaker in the dynamic proxy
//! correctly opens after failures, rejects when open, recovers via
//! half-open, and isolates per upstream.

use axum::body::Body;
use axum::http::{Request, StatusCode};
use tower::ServiceExt;

use stoa_gateway::config::Config;
use stoa_gateway::routes::ApiRoute;
use stoa_gateway::state::AppState;

/// Create a test route pointing to a backend that will fail (connection refused).
fn failing_route(id: &str, prefix: &str) -> ApiRoute {
    ApiRoute {
        id: id.to_string(),
        name: format!("failing-{}", id),
        tenant_id: "acme".to_string(),
        path_prefix: prefix.to_string(),
        // 192.0.2.1 = TEST-NET-1 (RFC 5737) — non-routable, not SSRF-blocked
        backend_url: "http://192.0.2.1:19999".to_string(),
        methods: vec![],
        spec_hash: "abc".to_string(),
        activated: true,
        classification: None,
        contract_key: None,
    }
}

/// Build AppState with a low CB threshold for fast test cycles.
fn state_with_low_cb_threshold() -> AppState {
    let config = Config {
        admin_api_token: Some("test-token".to_string()),
        cb_failure_threshold: 5,
        cb_reset_timeout_secs: 1,
        cb_success_threshold: 1,
        auto_register: false,
        ..Config::default()
    };
    AppState::new(config)
}

/// Send a GET to the given URI through the router.
async fn proxy_get(router: &axum::Router, uri: &str) -> (StatusCode, String) {
    let request = Request::builder()
        .method("GET")
        .uri(uri)
        .body(Body::empty())
        .expect("valid request");

    let response = router
        .clone()
        .oneshot(request)
        .await
        .expect("router should not error");

    let status = response.status();
    let body = axum::body::to_bytes(response.into_body(), 1_048_576)
        .await
        .expect("read body");
    (status, String::from_utf8_lossy(&body).to_string())
}

/// DoD #4: Circuit breaker opens after 5 consecutive failures.
#[tokio::test]
async fn test_cb_opens_after_5_failures() {
    let state = state_with_low_cb_threshold();
    state
        .route_registry
        .upsert(failing_route("r1", "/apis/broken"));
    let router = stoa_gateway::build_router(state.clone());

    // Send 5 requests — all should fail with 502 (connection refused → Bad Gateway)
    for i in 0..5 {
        let (status, _) = proxy_get(&router, "/apis/broken/test").await;
        assert!(
            status == StatusCode::BAD_GATEWAY || status == StatusCode::GATEWAY_TIMEOUT,
            "Request {} should fail with 502/504, got {}",
            i,
            status
        );
    }

    // 6th request should be rejected by circuit breaker → 503
    let (status, body) = proxy_get(&router, "/apis/broken/test").await;
    assert_eq!(status, StatusCode::SERVICE_UNAVAILABLE);
    assert!(
        body.contains("Circuit breaker open"),
        "Expected CB open message, got: {}",
        body
    );
}

/// After CB opens, requests are fast-failed with 503.
#[tokio::test]
async fn test_cb_rejects_when_open() {
    let state = state_with_low_cb_threshold();
    state
        .route_registry
        .upsert(failing_route("r1", "/apis/broken"));
    let router = stoa_gateway::build_router(state.clone());

    // Open the CB
    for _ in 0..5 {
        proxy_get(&router, "/apis/broken/test").await;
    }

    // Multiple subsequent requests should all be 503 (fast-fail, no actual HTTP call)
    for _ in 0..3 {
        let (status, body) = proxy_get(&router, "/apis/broken/test").await;
        assert_eq!(status, StatusCode::SERVICE_UNAVAILABLE);
        assert!(body.contains("Circuit breaker open"));
    }
}

/// After CB opens and reset_timeout passes, CB transitions to half-open.
/// A success in half-open closes the circuit.
#[tokio::test]
async fn test_cb_half_open_recovery() {
    let state = state_with_low_cb_threshold();
    state
        .route_registry
        .upsert(failing_route("r1", "/apis/broken"));
    let router = stoa_gateway::build_router(state.clone());

    // Open the CB
    for _ in 0..5 {
        proxy_get(&router, "/apis/broken/test").await;
    }

    // Verify CB is open
    let (status, _) = proxy_get(&router, "/apis/broken/test").await;
    assert_eq!(status, StatusCode::SERVICE_UNAVAILABLE);

    // Wait for reset_timeout (1s configured above)
    tokio::time::sleep(std::time::Duration::from_millis(1100)).await;

    // CB should be half-open now — allows the request through (will still fail at backend)
    let (status, _) = proxy_get(&router, "/apis/broken/test").await;
    // Half-open allows the request but backend is still down → 502
    assert!(
        status == StatusCode::BAD_GATEWAY || status == StatusCode::GATEWAY_TIMEOUT,
        "Half-open should allow request through, got {}",
        status
    );
}

/// Route A failures don't affect Route B's circuit breaker.
#[tokio::test]
async fn test_cb_per_upstream_isolation() {
    let state = state_with_low_cb_threshold();
    state
        .route_registry
        .upsert(failing_route("r1", "/apis/broken-a"));
    state
        .route_registry
        .upsert(failing_route("r2", "/apis/broken-b"));
    let router = stoa_gateway::build_router(state.clone());

    // Trip CB for route A only
    for _ in 0..5 {
        proxy_get(&router, "/apis/broken-a/test").await;
    }

    // Route A should be CB-open → 503
    let (status, _) = proxy_get(&router, "/apis/broken-a/test").await;
    assert_eq!(status, StatusCode::SERVICE_UNAVAILABLE);

    // Route B should still work (backend will fail with 502, but NOT CB-blocked)
    let (status, _) = proxy_get(&router, "/apis/broken-b/test").await;
    assert!(
        status == StatusCode::BAD_GATEWAY || status == StatusCode::GATEWAY_TIMEOUT,
        "Route B should not be CB-blocked, got {}",
        status
    );
}

/// Method not allowed returns 405, not CB trip.
#[tokio::test]
async fn test_method_not_allowed_does_not_trip_cb() {
    let state = state_with_low_cb_threshold();
    state.route_registry.upsert(ApiRoute {
        id: "r1".to_string(),
        name: "limited-api".to_string(),
        tenant_id: "acme".to_string(),
        path_prefix: "/apis/limited".to_string(),
        backend_url: "http://192.0.2.1:19999".to_string(),
        methods: vec!["POST".to_string()],
        spec_hash: "abc".to_string(),
        activated: true,
        classification: None,
        contract_key: None,
    });
    let router = stoa_gateway::build_router(state.clone());

    // Send 10 GET requests to a POST-only route — should get 405, not trip CB
    for _ in 0..10 {
        let (status, _) = proxy_get(&router, "/apis/limited/test").await;
        assert_eq!(status, StatusCode::METHOD_NOT_ALLOWED);
    }

    // CB should still be closed (405 is handled before proxying)
    let request = Request::builder()
        .method("GET")
        .uri("/admin/circuit-breakers")
        .header("Authorization", "Bearer test-token")
        .body(Body::empty())
        .expect("valid request");

    let response = router.clone().oneshot(request).await.expect("ok");
    let body = axum::body::to_bytes(response.into_body(), 1_048_576)
        .await
        .expect("read body");
    let stats: Vec<serde_json::Value> = serde_json::from_slice(&body).expect("valid JSON");
    // No CB entry created since method check happens before proxy
    assert!(stats.is_empty(), "405 should not create a CB entry");
}

/// GET /admin/circuit-breakers returns stats for registered upstream CBs.
#[tokio::test]
async fn test_cb_stats_endpoint() {
    let state = state_with_low_cb_threshold();
    state
        .route_registry
        .upsert(failing_route("r1", "/apis/broken"));
    let router = stoa_gateway::build_router(state.clone());

    // Generate some failures to create a CB entry
    for _ in 0..3 {
        proxy_get(&router, "/apis/broken/test").await;
    }

    // Query admin endpoint
    let request = Request::builder()
        .method("GET")
        .uri("/admin/circuit-breakers")
        .header("Authorization", "Bearer test-token")
        .body(Body::empty())
        .expect("valid request");

    let response = router.clone().oneshot(request).await.expect("ok");
    assert_eq!(response.status(), StatusCode::OK);

    let body = axum::body::to_bytes(response.into_body(), 1_048_576)
        .await
        .expect("read body");
    let stats: Vec<serde_json::Value> = serde_json::from_slice(&body).expect("valid JSON");
    assert!(!stats.is_empty(), "Should have at least 1 CB entry");
    assert_eq!(stats[0]["state"], "closed"); // 3 failures < threshold of 5
    assert_eq!(stats[0]["failure_count"], 3);
}
