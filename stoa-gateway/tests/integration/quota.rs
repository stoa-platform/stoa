//! Quota and rate limiting integration tests.
//!
//! Tests per-consumer quota enforcement, rate limiting, and admin quota endpoints.

use axum::http::{Request, StatusCode};
use axum::{body::Body, response::Response, Router};
use serde_json::{json, Value};
use std::time::Duration;
use tower::ServiceExt;
use wiremock::{matchers::method, Mock, MockServer, ResponseTemplate};

use crate::common::{config_with_admin_token, config_with_quota, TestApp};
use crate::jwt;

// ========================================================================
// Quota disabled (default)
// ========================================================================

#[tokio::test]
async fn test_quota_disabled_health_always_200() {
    // Default config has quota disabled — health always succeeds
    let app = TestApp::new();
    let (status, _body) = app.get("/health").await;
    assert_eq!(status, StatusCode::OK);
}

#[tokio::test]
async fn test_quota_disabled_mcp_accessible() {
    // With quota disabled, MCP endpoints should work without consumer identity
    let app = TestApp::new();
    let (status, _body) = app.get("/mcp").await;
    assert_eq!(status, StatusCode::OK);
}

// ========================================================================
// Admin Quota endpoints
// ========================================================================

#[tokio::test]
async fn test_admin_list_quotas() {
    let config = config_with_admin_token("test-admin-token");
    let app = TestApp::with_config(config);
    let (status, body) = app
        .get_with_bearer("/admin/quotas", "test-admin-token")
        .await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    // Should return a quota summary object
    assert!(json.is_object() || json.is_array());
}

#[tokio::test]
async fn test_admin_get_consumer_quota_not_found() {
    let config = config_with_admin_token("test-admin-token");
    let app = TestApp::with_config(config);
    let (status, _body) = app
        .get_with_bearer("/admin/quotas/unknown-consumer", "test-admin-token")
        .await;
    // Should return 200 with empty/default quota or 404
    assert!(status == StatusCode::OK || status == StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn test_admin_reset_consumer_quota() {
    let config = config_with_admin_token("test-admin-token");
    let app = TestApp::with_config(config);
    let (status, _body) = app
        .post_json_with_bearer("/admin/quotas/consumer-1/reset", "{}", "test-admin-token")
        .await;
    // Reset returns 200 if consumer exists, 404 if not registered
    assert!(status == StatusCode::OK || status == StatusCode::NOT_FOUND);
}

// ========================================================================
// Quota enforcement enabled
// ========================================================================

#[tokio::test]
async fn test_quota_enabled_health_bypassed() {
    // Health endpoints should bypass quota enforcement
    let config = config_with_quota(10, 100);
    let app = TestApp::with_config(config);
    let (status, body) = app.get("/health").await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body, "OK");
}

#[tokio::test]
async fn test_quota_enabled_metrics_bypassed() {
    // Metrics endpoint should bypass quota enforcement
    let config = config_with_quota(10, 100);
    let app = TestApp::with_config(config);
    let (status, _body) = app.get("/metrics").await;
    assert_eq!(status, StatusCode::OK);
}

#[tokio::test]
async fn test_quota_enabled_mcp_discovery_works() {
    // Discovery endpoints should work even with quota enabled
    // (quota checks consumer identity from auth context, anonymous gets default)
    let config = config_with_quota(60, 10_000);
    let app = TestApp::with_config(config);
    let (status, _body) = app.get("/mcp").await;
    assert_eq!(status, StatusCode::OK);
}

pub(crate) const CONTRACT_ROUTE: &str = "/apis/tenant-a/catalog";
pub(crate) const CONTRACT_ADMIN_ROUTE: &str = "/admin/contracts/tenant-a:catalog";

pub(crate) fn quota_contract(upstream: &str) -> Value {
    json!({
        "tenant_id": "tenant-a",
        "name": "catalog",
        "version": "1.0.0",
        "status": "published",
        "inbound_auth": "jwt",
        "policies": [{"type": "consumer_quota", "config": {"consumers": [
            {"consumer_id": "reader", "rate_limit_per_minute": 5},
            {"consumer_id": "editor", "rate_limit_per_minute": 5}
        ]}}],
        "endpoints": [
            {"path": "/items", "methods": ["GET"], "backend_url": format!("{upstream}/items")},
            {"path": "/groups", "methods": ["GET"], "backend_url": format!("{upstream}/groups")}
        ]
    })
}

async fn call_contract(app: &Router, endpoint: &str, bearer: &str) -> Response {
    app.clone()
        .oneshot(
            Request::get(format!("{CONTRACT_ROUTE}/{endpoint}"))
                .header("authorization", format!("Bearer {bearer}"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap()
}

#[tokio::test]
async fn published_contract_returns_429_on_sixth_request_and_recovers_after_fixed_window() {
    assert_published_contract_quota(true).await;
}

#[tokio::test]
async fn published_contract_enforces_consumer_quota_with_generic_quota_disabled() {
    assert_published_contract_quota(false).await;
}

async fn assert_published_contract_quota(quota_enforcement_enabled: bool) {
    let oidc = jwt::oidc_server().await;
    let upstream = MockServer::start().await;
    Mock::given(method("GET"))
        .respond_with(ResponseTemplate::new(200))
        .mount(&upstream)
        .await;

    let admin = uuid::Uuid::new_v4().to_string();
    let mut config = jwt::config(&oidc);
    config.admin_api_token = Some(admin.clone());
    config.quota_enforcement_enabled = quota_enforcement_enabled;
    let app = stoa_gateway::build_router(stoa_gateway::state::AppState::new(config));
    let contract = quota_contract(&upstream.uri());
    let push = || {
        app.clone().oneshot(
            Request::post("/admin/contracts")
                .header("authorization", format!("Bearer {admin}"))
                .header("content-type", "application/json")
                .body(Body::from(contract.to_string()))
                .unwrap(),
        )
    };
    assert_eq!(push().await.unwrap().status(), StatusCode::CREATED);

    let reader = jwt::token_with(json!({"azp": "reader"}));
    let renewed_reader = jwt::token_with(json!({"azp": "reader", "sub": "another-user"}));
    let editor = jwt::token_with(json!({"azp": "editor"}));
    let missing_azp = jwt::token_with(json!({}));
    let unknown_consumer = jwt::token_with(json!({"azp": "viewer"}));
    let wrong_tenant = jwt::token_with(json!({"azp": "reader", "tenant_id": "tenant-b"}));
    for bearer in [&missing_azp, &unknown_consumer, &wrong_tenant] {
        assert_eq!(
            call_contract(&app, "items", bearer).await.status(),
            StatusCode::FORBIDDEN
        );
    }
    assert!(upstream.received_requests().await.unwrap().is_empty());

    let mut reset = None;
    for (index, endpoint) in ["items", "groups", "items", "groups", "items"]
        .into_iter()
        .enumerate()
    {
        let response = call_contract(&app, endpoint, &reader).await;
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(response.headers()["x-ratelimit-limit"], "5");
        assert_eq!(
            response.headers()["x-ratelimit-remaining"]
                .to_str()
                .unwrap(),
            (4 - index).to_string()
        );
        let epoch = response.headers()["x-ratelimit-reset"]
            .to_str()
            .unwrap()
            .parse::<i64>()
            .unwrap();
        assert_eq!(*reset.get_or_insert(epoch), epoch);
    }
    assert_eq!(push().await.unwrap().status(), StatusCode::OK);
    let response = call_contract(&app, "groups", &renewed_reader).await;
    assert_eq!(response.status(), StatusCode::TOO_MANY_REQUESTS);
    assert_eq!(response.headers()["x-ratelimit-limit"], "5");
    assert_eq!(response.headers()["x-ratelimit-remaining"], "0");
    assert_eq!(
        response.headers()["x-ratelimit-reset"].to_str().unwrap(),
        reset.unwrap().to_string()
    );
    let retry = response.headers()["retry-after"]
        .to_str()
        .unwrap()
        .parse::<u64>()
        .unwrap();
    assert!((1..=60).contains(&retry));
    let body = axum::body::to_bytes(response.into_body(), 4096)
        .await
        .unwrap();
    let json: Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(json["error"], "quota_exceeded");
    assert!(json["message"].is_string());
    assert_eq!(json["retry_after_secs"], retry);
    assert_eq!(upstream.received_requests().await.unwrap().len(), 5);

    let response = call_contract(&app, "items", &editor).await;
    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(response.headers()["x-ratelimit-remaining"], "4");

    tokio::time::pause();
    tokio::time::advance(Duration::from_secs(60)).await;
    tokio::time::resume();
    let response = call_contract(&app, "groups", &reader).await;
    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(response.headers()["x-ratelimit-remaining"], "4");
    assert_eq!(upstream.received_requests().await.unwrap().len(), 7);
}
