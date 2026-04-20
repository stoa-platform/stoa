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

// ============================================================================
// regression for CAB-2121 — /mcp/* auth gate
//
// These build a router with a JWT validator configured (via `keycloak_url`),
// so the `mcp_jwt_required` middleware rejects anonymous callers on all
// protected MCP routes instead of silently falling back to tenant="default"
// / scopes=[stoa:read] in the handler. The validator construction is sync
// and performs no I/O; the invalid-URL is only contacted during actual JWT
// validation, which the "no bearer" / "non-bearer" tests never trigger.
// ============================================================================

/// Build a router with JWT validation enabled (validator = `Some`) so the
/// CAB-2121 middleware gate engages. `keycloak_url` points at an
/// intentionally-unreachable address; no network I/O is attempted at
/// construction time.
fn router_with_jwt_validator() -> axum::Router {
    let config = Config {
        // Loopback port 1: routable but unreachable. Only hit during
        // validate(), never during extract_token() or for anon requests.
        keycloak_url: Some("http://127.0.0.1:1".to_string()),
        keycloak_realm: Some("stoa".to_string()),
        auto_register: false,
        ..Config::default()
    };
    let state = AppState::new(config);
    stoa_gateway::build_router(state)
}

async fn anon_request(uri: &str, method: &str, body: &str) -> axum::http::Response<Body> {
    let router = router_with_jwt_validator();
    let request = Request::builder()
        .method(method)
        .uri(uri)
        .header("Content-Type", "application/json")
        .body(Body::from(body.to_string()))
        .expect("valid request");
    router.oneshot(request).await.expect("router ok")
}

fn assert_bearer_challenge(resp: &axum::http::Response<Body>) {
    let www = resp
        .headers()
        .get("WWW-Authenticate")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");
    assert!(
        www.contains("Bearer"),
        "WWW-Authenticate missing Bearer scheme: {www:?}",
    );
    assert!(
        www.contains("resource_metadata"),
        "WWW-Authenticate missing resource_metadata: {www:?}",
    );
}

#[tokio::test]
async fn test_mcp_tools_call_rejects_anon() {
    let resp = anon_request("/mcp/tools/call", "POST", r#"{"name":"x","arguments":{}}"#).await;
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    assert_bearer_challenge(&resp);
}

#[tokio::test]
async fn test_mcp_tools_list_rejects_anon() {
    let resp = anon_request("/mcp/tools/list", "POST", "{}").await;
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    assert_bearer_challenge(&resp);
}

#[tokio::test]
async fn test_mcp_v1_tools_rejects_anon() {
    let resp = anon_request("/mcp/v1/tools", "GET", "").await;
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    assert_bearer_challenge(&resp);
}

#[tokio::test]
async fn test_mcp_v1_tools_invoke_rejects_anon() {
    let resp = anon_request(
        "/mcp/v1/tools/invoke",
        "POST",
        r#"{"tool":"x","arguments":{}}"#,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    assert_bearer_challenge(&resp);
}

#[tokio::test]
async fn test_mcp_resources_rejects_anon() {
    let resp = anon_request("/mcp/resources/list", "POST", "{}").await;
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    assert_bearer_challenge(&resp);
}

#[tokio::test]
async fn test_mcp_prompts_rejects_anon() {
    let resp = anon_request("/mcp/prompts/list", "POST", "{}").await;
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    assert_bearer_challenge(&resp);
}

#[tokio::test]
async fn test_mcp_events_rejects_anon() {
    let resp = anon_request("/mcp/events", "GET", "").await;
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    assert_bearer_challenge(&resp);
}

#[tokio::test]
async fn test_mcp_tools_call_rejects_malformed_bearer() {
    let router = router_with_jwt_validator();
    let request = Request::builder()
        .method("POST")
        .uri("/mcp/tools/call")
        .header("Content-Type", "application/json")
        .header("Authorization", "Basic dXNlcjpwYXNz")
        .body(Body::from(r#"{"name":"x","arguments":{}}"#))
        .expect("valid request");
    let resp = router.oneshot(request).await.expect("router ok");
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    assert_bearer_challenge(&resp);
}

#[tokio::test]
async fn test_mcp_capabilities_remains_public() {
    let resp = anon_request("/mcp/capabilities", "GET", "").await;
    assert_eq!(resp.status(), StatusCode::OK);
}

#[tokio::test]
async fn test_mcp_discovery_remains_public() {
    let resp = anon_request("/mcp", "GET", "").await;
    assert_eq!(resp.status(), StatusCode::OK);
}

#[tokio::test]
async fn test_mcp_health_remains_public() {
    let resp = anon_request("/mcp/health", "GET", "").await;
    assert_eq!(resp.status(), StatusCode::OK);
}

/// CAB-2121: Streamable HTTP discovery (`POST /mcp` with `tools/list`) must
/// 401 anon — the method is no longer in `PUBLIC_METHODS`. Route itself stays
/// public so `initialize`/`ping` keep working.
#[tokio::test]
async fn test_streamable_http_tools_list_rejects_anon() {
    let resp = anon_request(
        "/mcp",
        "POST",
        r#"{"jsonrpc":"2.0","method":"tools/list","id":1}"#,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    // The in-handler SSE path emits its own WWW-Authenticate header.
    let www = resp
        .headers()
        .get("WWW-Authenticate")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");
    assert!(www.contains("Bearer"), "unexpected header: {www:?}");
}
