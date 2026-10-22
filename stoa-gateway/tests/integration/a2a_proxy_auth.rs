//! JWT gates exercised through the production router and a local mock upstream.

use axum::body::{to_bytes, Body};
use axum::http::{Request, StatusCode};
use axum::response::Response;
use axum::Router;
use serde_json::json;
use tower::ServiceExt;
use wiremock::matchers::{method, path};
use wiremock::{Mock, MockServer, ResponseTemplate};

use crate::jwt::{self, BAD_SIGNATURE_TOKEN, EXPIRED_TOKEN, VALID_TOKEN};
use stoa_gateway::config::Config;
use stoa_gateway::state::AppState;

async fn request(router: &Router, uri: &str, token: Option<&str>, body: &str) -> Response {
    let mut builder = Request::builder()
        .method("POST")
        .uri(uri)
        .header("Content-Type", "application/json");
    if let Some(token) = token {
        builder = builder.header("Authorization", format!("Bearer {token}"));
    }
    router
        .clone()
        .oneshot(builder.body(Body::from(body.to_string())).unwrap())
        .await
        .unwrap()
}

fn enable_proxy(config: &mut Config, upstream: &MockServer) {
    // Omit require_auth deliberately: deserialization must default to true.
    config.api_proxy = serde_json::from_value(json!({
        "enabled": true,
        "backends": {"test": {"enabled": true, "base_url": upstream.uri()}}
    }))
    .unwrap();
}

fn assert_unauthorized(response: Response) {
    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    assert!(response.headers().contains_key("www-authenticate"));
}

#[tokio::test]
async fn a2a_requires_valid_jwt_before_dispatch() {
    let oidc = jwt::oidc_server().await;
    let state = AppState::new(jwt::config(&oidc));
    let router = stoa_gateway::build_router(state.clone());
    let registry = state.a2a_registry.as_ref().unwrap();
    let body = json!({"jsonrpc": "2.0", "id": 1, "method": "tasks/send", "params": {
        "id": "auth-task", "message": {"role": "user", "parts": [{"type": "text", "text": "hello"}]}
    }})
    .to_string();
    for token in [
        None,
        Some("invalid"),
        Some(BAD_SIGNATURE_TOKEN),
        Some(EXPIRED_TOKEN),
    ] {
        assert_unauthorized(request(&router, "/a2a", token, &body).await);
        assert!(registry.get_task("auth-task").unwrap().is_none());
    }
    let response = request(&router, "/a2a", Some(VALID_TOKEN), &body).await;
    assert_eq!(response.status(), StatusCode::OK);
    assert!(registry.get_task("auth-task").unwrap().is_some());
    for method in ["tasks/get", "tasks/cancel"] {
        let body = json!({"jsonrpc": "2.0", "id": 2, "method": method,
            "params": {"id": "auth-task"}})
        .to_string();
        assert_unauthorized(request(&router, "/a2a", None, &body).await);
    }
}

#[tokio::test]
async fn proxy_defaults_to_requiring_valid_jwt_before_forwarding() {
    let oidc = jwt::oidc_server().await;
    let upstream = MockServer::start().await;
    Mock::given(method("POST"))
        .and(path("/echo"))
        .respond_with(ResponseTemplate::new(200).set_body_string("upstream reached"))
        .expect(1)
        .mount(&upstream)
        .await;
    let mut config = jwt::config(&oidc);
    enable_proxy(&mut config, &upstream);
    assert!(config.api_proxy.require_auth);
    let router = stoa_gateway::build_router(AppState::new(config));
    for token in [
        None,
        Some("invalid"),
        Some(BAD_SIGNATURE_TOKEN),
        Some(EXPIRED_TOKEN),
    ] {
        assert_unauthorized(request(&router, "/proxy/test/echo", token, "{}").await);
    }
    assert!(upstream.received_requests().await.unwrap().is_empty());
    let response = request(&router, "/proxy/test/echo", Some(VALID_TOKEN), "{}").await;
    assert_eq!(response.status(), StatusCode::OK);
    let body = to_bytes(response.into_body(), 1024).await.unwrap();
    assert_eq!(body.as_ref(), b"upstream reached");
}

#[tokio::test]
async fn protected_routes_fail_closed_without_validator_or_keys() {
    let upstream = MockServer::start().await;
    let unavailable_oidc = MockServer::start().await;
    let anonymous_config = Config {
        a2a_enabled: true,
        ..Config::default()
    };
    for mut config in [anonymous_config, jwt::config(&unavailable_oidc)] {
        enable_proxy(&mut config, &upstream);
        let state = AppState::new(config);
        let router = stoa_gateway::build_router(state);
        for uri in ["/a2a", "/proxy/test/echo"] {
            for token in [None, Some("invalid"), Some(VALID_TOKEN)] {
                assert_unauthorized(request(&router, uri, token, "{}").await);
            }
        }
    }
    assert!(upstream.received_requests().await.unwrap().is_empty());
}

#[tokio::test]
async fn proxy_explicitly_public_stays_open_with_or_without_validator() {
    let oidc = jwt::oidc_server().await;
    let upstream = MockServer::start().await;
    Mock::given(method("POST"))
        .and(path("/echo"))
        .respond_with(ResponseTemplate::new(200))
        .expect(8)
        .mount(&upstream)
        .await;
    for mut config in [Config::default(), jwt::config(&oidc)] {
        enable_proxy(&mut config, &upstream);
        config.api_proxy.require_auth = false;
        let router = stoa_gateway::build_router(AppState::new(config));
        for token in [None, Some("invalid"), Some(EXPIRED_TOKEN), Some(VALID_TOKEN)] {
            let response = request(&router, "/proxy/test/echo", token, "{}").await;
            assert_eq!(response.status(), StatusCode::OK);
        }
    }
}
