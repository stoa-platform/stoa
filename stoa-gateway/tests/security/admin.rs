//! Admin API security tests — verify no secret leakage in responses.

use axum::body::Body;
use axum::http::{Request, StatusCode};
use tower::ServiceExt;

use stoa_gateway::config::Config;
use stoa_gateway::state::AppState;

/// DoD #11: Admin health endpoint never leaks secrets.
///
/// The /admin/health response should contain status, version, routes_count,
/// policies_count — NEVER tokens, passwords, or secrets.
#[tokio::test]
async fn test_admin_health_no_secret_leak() {
    let admin_token = "super-secret-admin-token-12345";
    let config = Config {
        admin_api_token: Some(admin_token.to_string()),
        auto_register: false,
        ..Config::default()
    };
    let state = AppState::new(config);
    let router = stoa_gateway::build_router(state);

    let request = Request::builder()
        .method("GET")
        .uri("/admin/health")
        .header("Authorization", format!("Bearer {}", admin_token))
        .body(Body::empty())
        .expect("valid request");

    let response = router.oneshot(request).await.expect("ok");
    assert_eq!(response.status(), StatusCode::OK);

    let body = axum::body::to_bytes(response.into_body(), 1_048_576)
        .await
        .expect("body");
    let body_str = String::from_utf8_lossy(&body);

    // Verify the response does NOT contain any secrets
    let sensitive_patterns = [
        admin_token,
        "password",
        "secret",
        "token",
        "key",
        "credential",
    ];
    for pattern in &sensitive_patterns {
        assert!(
            !body_str.to_lowercase().contains(&pattern.to_lowercase()),
            "Admin health response should not contain '{}', got: {}",
            pattern,
            body_str
        );
    }

    // Verify it IS valid JSON with expected fields
    let data: serde_json::Value = serde_json::from_str(&body_str).expect("valid JSON");
    assert_eq!(data["status"], "ok");
    assert!(data["version"].is_string());
}

/// Admin circuit-breaker stats don't leak tokens.
#[tokio::test]
async fn test_admin_cb_stats_no_secret_leak() {
    let admin_token = "my-admin-api-token-xyz";
    let config = Config {
        admin_api_token: Some(admin_token.to_string()),
        auto_register: false,
        ..Config::default()
    };
    let state = AppState::new(config);
    let router = stoa_gateway::build_router(state);

    let request = Request::builder()
        .method("GET")
        .uri("/admin/circuit-breaker/stats")
        .header("Authorization", format!("Bearer {}", admin_token))
        .body(Body::empty())
        .expect("valid request");

    let response = router.oneshot(request).await.expect("ok");
    assert_eq!(response.status(), StatusCode::OK);

    let body = axum::body::to_bytes(response.into_body(), 1_048_576)
        .await
        .expect("body");
    let body_str = String::from_utf8_lossy(&body);

    assert!(
        !body_str.contains(admin_token),
        "CB stats should not contain admin token"
    );
}
