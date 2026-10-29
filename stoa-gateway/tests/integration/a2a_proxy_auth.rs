//! JWT gates exercised through the production router and a local mock upstream.

use axum::body::{to_bytes, Body};
use axum::http::{Request, StatusCode};
use axum::response::Response;
use axum::Router;
use serde_json::json;
use tower::ServiceExt;
use wiremock::matchers::{method, path};
use wiremock::{Mock, MockServer, ResponseTemplate};

use crate::jwt::{
    self, bad_signature_token, expired_token, other_tenant_token, renewed_token, unscoped_token,
    valid_token,
};
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
        "backends": {"test": {"enabled": true, "base_url": upstream.uri(),
            "required_scopes": ["proxy:read"]}}
    }))
    .unwrap();
}

fn enable_public_proxy(config: &mut Config, upstream: &MockServer) {
    enable_proxy(config, upstream);
    config.api_proxy.require_auth = false;
    let backend = config.api_proxy.backends.get_mut("test").unwrap();
    backend.public = true;
    backend.auth_type = "none".into();
    backend.required_scopes.clear();
}

fn assert_unauthorized(response: Response) {
    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    assert!(response.headers().contains_key("www-authenticate"));
}

#[tokio::test]
async fn regression_a2a_requires_jwt() {
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
        Some(bad_signature_token()),
        Some(expired_token()),
    ] {
        assert_unauthorized(request(&router, "/a2a", token, &body).await);
        assert!(registry.get_task("auth-task").unwrap().is_none());
    }
    let response = request(&router, "/a2a", Some(valid_token()), &body).await;
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
async fn regression_proxy_requires_jwt_by_default() {
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
        Some(bad_signature_token()),
        Some(expired_token()),
    ] {
        assert_unauthorized(request(&router, "/proxy/test/echo", token, "{}").await);
    }
    assert!(upstream.received_requests().await.unwrap().is_empty());
    let response = request(&router, "/proxy/test/echo", Some(valid_token()), "{}").await;
    assert_eq!(response.status(), StatusCode::OK);
    let body = to_bytes(response.into_body(), 1024).await.unwrap();
    assert_eq!(body.as_ref(), b"upstream reached");
}

#[tokio::test]
async fn regression_protected_routes_fail_closed() {
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
            for token in [None, Some("invalid"), Some(valid_token())] {
                assert_unauthorized(request(&router, uri, token, "{}").await);
            }
        }
    }
    assert!(upstream.received_requests().await.unwrap().is_empty());
}

#[tokio::test]
async fn regression_proxy_public_when_require_auth_false() {
    let oidc = jwt::oidc_server().await;
    let upstream = MockServer::start().await;
    Mock::given(method("POST"))
        .and(path("/echo"))
        .respond_with(ResponseTemplate::new(200))
        .expect(3)
        .mount(&upstream)
        .await;
    // Public backend (auth_type none): anonymous calls pass; a presented
    // token is validated even with require_auth=false.
    for (mut config, valid) in [
        (Config::default(), StatusCode::UNAUTHORIZED),
        (jwt::config(&oidc), StatusCode::OK),
    ] {
        enable_public_proxy(&mut config, &upstream);
        let router = stoa_gateway::build_router(AppState::new(config));
        for (token, expected) in [
            (None, StatusCode::OK),
            (Some("invalid"), StatusCode::UNAUTHORIZED),
            (Some(expired_token()), StatusCode::UNAUTHORIZED),
            (Some(valid_token()), valid),
        ] {
            let response = request(&router, "/proxy/test/echo", token, "{}").await;
            assert_eq!(response.status(), expected);
        }
    }
}

async fn send(router: &Router, method: &str, uri: &str, headers: &[(&str, &str)]) -> Response {
    let mut builder = Request::builder().method(method).uri(uri);
    for (name, value) in headers {
        builder = builder.header(*name, *value);
    }
    router
        .clone()
        .oneshot(builder.body(Body::empty()).unwrap())
        .await
        .unwrap()
}

#[tokio::test]
async fn proxy_upstream_request_headers() {
    let oidc = jwt::oidc_server().await;
    let upstream = MockServer::start().await;
    Mock::given(method("GET"))
        .and(path("/echo"))
        .respond_with(ResponseTemplate::new(200))
        .expect(1)
        .mount(&upstream)
        .await;
    let mut config = jwt::config(&oidc);
    config.api_proxy = serde_json::from_value(json!({
        "enabled": true,
        "backends": {"test": {
            "enabled": true,
            "base_url": upstream.uri(),
            "auth_header": "X-API-Key",
            "required_scopes": ["proxy:read"]
        }}
    }))
    .unwrap();
    let router = stoa_gateway::build_router(AppState::new(config));
    let bearer = format!("Bearer {}", valid_token());
    let response = send(
        &router,
        "GET",
        "/proxy/test/echo",
        &[
            ("Authorization", bearer.as_str()),
            ("Cookie", "session=fixture"),
            ("DPoP", "fixture-proof"),
            ("X-API-Key", "caller-value"),
            ("X-Request-Id", "req-1"),
        ],
    )
    .await;
    assert_eq!(response.status(), StatusCode::OK);
    let received = upstream.received_requests().await.unwrap();
    assert_eq!(received.len(), 1);
    let headers = &received[0].headers;
    for name in ["authorization", "cookie", "dpop", "x-api-key"] {
        assert!(!headers.contains_key(name), "{name} relayed upstream");
    }
    assert_eq!(headers.get("x-request-id").unwrap(), "req-1");
}

#[test]
fn bad_signature_fixture_differs_only_by_signature() {
    use base64::engine::general_purpose::URL_SAFE_NO_PAD;
    use base64::Engine;

    let valid: Vec<&str> = valid_token().split('.').collect();
    let altered: Vec<&str> = bad_signature_token().split('.').collect();
    assert_eq!(valid.len(), 3);
    assert_eq!(altered.len(), 3);
    assert_eq!(altered[0], valid[0], "same header and kid");
    assert_eq!(altered[1], valid[1], "same claims");
    assert_ne!(altered[2], valid[2]);
    let signature = URL_SAFE_NO_PAD
        .decode(altered[2])
        .expect("signature segment is valid base64url");
    assert_eq!(signature.len(), 256, "RS256 2048-bit signature");
}

#[tokio::test]
async fn a2a_jwt_guard_covers_all_methods() {
    let oidc = jwt::oidc_server().await;
    let router = stoa_gateway::build_router(AppState::new(jwt::config(&oidc)));
    let bearer = format!("Bearer {}", valid_token());
    for method in ["GET", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"] {
        let response = send(&router, method, "/a2a", &[]).await;
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED, "{method}");
        let response = send(
            &router,
            method,
            "/a2a",
            &[("Authorization", bearer.as_str())],
        )
        .await;
        assert_eq!(
            response.status(),
            StatusCode::METHOD_NOT_ALLOWED,
            "{method}"
        );
    }
}

#[tokio::test]
async fn proxy_jwt_guard_covers_all_methods() {
    let oidc = jwt::oidc_server().await;
    let upstream = MockServer::start().await;
    Mock::given(path("/echo"))
        .respond_with(ResponseTemplate::new(200))
        .mount(&upstream)
        .await;
    let mut config = jwt::config(&oidc);
    enable_proxy(&mut config, &upstream);
    let router = stoa_gateway::build_router(AppState::new(config));
    let methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"];
    for method in methods {
        assert_unauthorized(send(&router, method, "/proxy/test/echo", &[]).await);
    }
    assert!(upstream.received_requests().await.unwrap().is_empty());
    let bearer = format!("Bearer {}", valid_token());
    for method in methods {
        let response = send(
            &router,
            method,
            "/proxy/test/echo",
            &[("Authorization", bearer.as_str())],
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK, "{method}");
    }
    assert_eq!(
        upstream.received_requests().await.unwrap().len(),
        methods.len()
    );
}

#[tokio::test]
async fn proxy_path_variants_without_token() {
    let oidc = jwt::oidc_server().await;
    let upstream = MockServer::start().await;
    Mock::given(path("/echo"))
        .respond_with(ResponseTemplate::new(200))
        .mount(&upstream)
        .await;
    let mut config = jwt::config(&oidc);
    enable_proxy(&mut config, &upstream);
    let router = stoa_gateway::build_router(AppState::new(config));
    for uri in [
        "/proxy",
        "/proxy/",
        "/proxy/test",
        "/proxy/test/",
        "//proxy/test/echo",
        "/PROXY/test/echo",
        "/Proxy/test/echo",
        "/proxy/%74est/echo",
        "/proxy/test/%65cho",
        "/proxy/test//echo",
        "/proxy/test/./echo",
        "/proxy/test/echo?x=1",
        "/proxy/test/echo#frag",
    ] {
        for method in ["GET", "POST"] {
            let status = send(&router, method, uri, &[]).await.status();
            assert!(
                status == StatusCode::UNAUTHORIZED || status == StatusCode::NOT_FOUND,
                "{method} {uri}: {status}"
            );
        }
    }
    assert!(upstream.received_requests().await.unwrap().is_empty());
}

const POLICY_BODY: &str = r#"{"jsonrpc":"2.0","id":1,"method":"tasks/send",
"params":{"id":"policy-task","message":{"role":"user","parts":[{"type":"text","text":"hello"}]}}}"#;
async fn policy_fixture() -> (MockServer, MockServer, Config) {
    let oidc = jwt::oidc_server().await;
    let upstream = MockServer::start().await;
    Mock::given(path("/echo"))
        .respond_with(ResponseTemplate::new(200))
        .mount(&upstream)
        .await;
    let mut config = jwt::config(&oidc);
    enable_proxy(&mut config, &upstream);
    config.quota_enforcement_enabled = true;
    config.quota_default_rate_per_minute = 0;
    (oidc, upstream, config)
}
fn policy_count(state: &AppState) -> u64 {
    state
        .quota_manager
        .get_stats("auth-regression-user")
        .map_or(0, |stats| stats.daily_count)
}
fn assert_unspent_policy(state: &AppState) {
    assert_eq!(policy_count(state), 0);
    assert!(state
        .a2a_registry
        .as_ref()
        .unwrap()
        .get_task("policy-task")
        .unwrap()
        .is_none());
}

#[tokio::test]
async fn regression_router_auth_precedes_quota_once() {
    for uri in ["/a2a", "/proxy/test/echo"] {
        let (_oidc, upstream, mut config) = policy_fixture().await;
        config.quota_default_daily_limit = 1;
        let state = AppState::new(config);
        let router = stoa_gateway::build_router(state.clone());
        let first = request(&router, uri, Some(valid_token()), POLICY_BODY).await;
        assert_eq!(first.status(), StatusCode::OK, "{uri}");
        assert_eq!(
            policy_count(&state),
            1,
            "one successful request, one charge"
        );
        let second = request(&router, uri, Some(valid_token()), POLICY_BODY).await;
        assert_eq!(second.status(), StatusCode::TOO_MANY_REQUESTS, "{uri}");
        let body = to_bytes(second.into_body(), 4096).await.unwrap();
        let error: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert!(error["message"].as_str().unwrap().contains("Daily quota"));
        assert_eq!(policy_count(&state), 1, "quota refusal is not charged");
        assert_eq!(
            upstream.received_requests().await.unwrap().len(),
            usize::from(uri.starts_with("/proxy/"))
        );
    }
}

#[tokio::test]
async fn regression_router_sender_refuses_before_quota_and_handler() {
    for uri in ["/a2a", "/proxy/test/echo"] {
        let (_oidc, upstream, mut config) = policy_fixture().await;
        config.sender_constraint.enabled = true;
        config.sender_constraint.dpop_required = true;
        let state = AppState::new(config);
        let router = stoa_gateway::build_router(state.clone());
        let response = request(&router, uri, Some(valid_token()), POLICY_BODY).await;
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED, "{uri}");
        let body = to_bytes(response.into_body(), 4096).await.unwrap();
        let error: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(error["error"], "SENDER_CONSTRAINT_DPOP_REQUIRED");
        assert_unspent_policy(&state);
        assert!(upstream.received_requests().await.unwrap().is_empty());
        for public in ["/health", "/mcp/capabilities"] {
            assert_eq!(
                send(&router, "GET", public, &[]).await.status(),
                StatusCode::OK
            );
        }
        assert_eq!(policy_count(&state), 0);
    }
}

#[tokio::test]
async fn regression_router_auth_precedes_command_supervision() {
    for uri in ["/a2a", "/proxy/test/echo"] {
        let (_oidc, upstream, mut config) = policy_fixture().await;
        config.supervision_enabled = true;
        config.supervision_default_tier = stoa_gateway::config::SupervisionDefaultTier::Command;
        let state = AppState::new(config);
        let router = stoa_gateway::build_router(state.clone());
        for token in ["invalid", bad_signature_token(), expired_token()] {
            assert_unauthorized(request(&router, uri, Some(token), POLICY_BODY).await);
        }
        let response = request(&router, uri, Some(valid_token()), POLICY_BODY).await;
        assert_eq!(response.status(), StatusCode::FORBIDDEN, "{uri}");
        let body = to_bytes(response.into_body(), 4096).await.unwrap();
        let error: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(error["error"], "supervision_blocked");
        assert_unspent_policy(&state);
        assert!(upstream.received_requests().await.unwrap().is_empty());
    }
}

#[tokio::test]
async fn regression_router_mtls_extracts_before_sender_constraint() {
    let (_oidc, upstream, mut config) = policy_fixture().await;
    config.mtls.enabled = true;
    config.mtls.trusted_proxies = vec!["127.0.0.1/32".to_string()];
    config.sender_constraint.enabled = true;
    config.sender_constraint.mtls_required = true;
    let state = AppState::new(config);
    let router = stoa_gateway::build_router(state.clone());
    for (uri, peer, expected) in [
        ("/a2a", "127.0.0.1:443", StatusCode::OK),
        ("/proxy/test/echo", "127.0.0.1:443", StatusCode::OK),
        ("/proxy/test/echo", "192.0.2.1:443", StatusCode::FORBIDDEN),
    ] {
        let mut req = Request::builder()
            .method("POST")
            .uri(uri)
            .header("Content-Type", "application/json")
            .header("Authorization", format!("Bearer {}", jwt::mtls_token()))
            .header("X-SSL-Client-Verify", "SUCCESS")
            .header("X-SSL-Client-Fingerprint", "11".repeat(32))
            .body(Body::from(POLICY_BODY))
            .unwrap();
        req.extensions_mut().insert(axum::extract::ConnectInfo(
            peer.parse::<std::net::SocketAddr>().unwrap(),
        ));
        assert_eq!(
            router.clone().oneshot(req).await.unwrap().status(),
            expected
        );
    }
    assert_eq!(policy_count(&state), 2);
    assert_eq!(upstream.received_requests().await.unwrap().len(), 1);
}

#[tokio::test]
async fn regression_router_public_proxy_anonymous_passes_policies() {
    let (_oidc, upstream, mut config) = policy_fixture().await;
    enable_public_proxy(&mut config, &upstream);
    config.sender_constraint.enabled = true;
    config.sender_constraint.dpop_required = true;
    let state = AppState::new(config);
    let router = stoa_gateway::build_router(state.clone());
    assert_eq!(
        request(&router, "/proxy/test/echo", None, "{}")
            .await
            .status(),
        StatusCode::OK
    );
    assert_eq!(policy_count(&state), 0);
    assert_eq!(upstream.received_requests().await.unwrap().len(), 1);
}

async fn a2a_call(
    router: &Router,
    token: &str,
    method: &str,
    text: Option<&str>,
) -> serde_json::Value {
    let mut params = json!({"id": "owner-task"});
    if let Some(text) = text {
        params["message"] = json!({"role": "user", "parts": [{"type": "text", "text": text}]});
    }
    let body = json!({"jsonrpc": "2.0", "id": 1, "method": method, "params": params});
    let response = request(router, "/a2a", Some(token), &body.to_string()).await;
    assert_eq!(response.status(), StatusCode::OK, "{method}");
    serde_json::from_slice(&to_bytes(response.into_body(), 65536).await.unwrap()).unwrap()
}

fn error_message(value: &serde_json::Value) -> &str {
    value["error"]["message"].as_str().unwrap_or("")
}

#[tokio::test]
async fn regression_a2a_task_owner_survives_token_renewal() {
    let oidc = jwt::oidc_server().await;
    let router = stoa_gateway::build_router(AppState::new(jwt::config(&oidc)));
    assert_ne!(valid_token(), renewed_token());
    let created = a2a_call(&router, valid_token(), "tasks/send", Some("hello")).await;
    assert!(created["error"].is_null(), "{created}");
    let read = a2a_call(&router, renewed_token(), "tasks/get", None).await;
    assert_eq!(read["result"]["id"], "owner-task", "{read}");
    let next = a2a_call(&router, renewed_token(), "tasks/send", Some("again")).await;
    assert!(next["error"].is_null(), "{next}");
    let cancel = a2a_call(&router, renewed_token(), "tasks/cancel", None).await;
    assert!(!error_message(&cancel).contains("not found"), "{cancel}");
}

#[tokio::test]
async fn regression_a2a_task_refused_to_same_subject_in_other_tenant() {
    let oidc = jwt::oidc_server().await;
    let router = stoa_gateway::build_router(AppState::new(jwt::config(&oidc)));
    let created = a2a_call(&router, valid_token(), "tasks/send", Some("hello")).await;
    assert!(created["error"].is_null(), "{created}");
    for method in ["tasks/get", "tasks/cancel"] {
        let other = a2a_call(&router, other_tenant_token(), method, None).await;
        assert_eq!(
            error_message(&other),
            "Task not found: owner-task",
            "{method}"
        );
    }
    let other = a2a_call(&router, other_tenant_token(), "tasks/send", Some("x")).await;
    assert!(other["result"].is_null(), "{other}");
    let read = a2a_call(&router, valid_token(), "tasks/get", None).await;
    assert_eq!(read["result"]["id"], "owner-task", "{read}");
}

#[tokio::test]
async fn proxy_identity_precedes_quota_when_require_auth_false() {
    let (_oidc, upstream, mut config) = policy_fixture().await;
    config.api_proxy.require_auth = false;
    config.quota_default_daily_limit = 1;
    let state = AppState::new(config);
    let router = stoa_gateway::build_router(state.clone());
    let uri = "/proxy/test/echo";
    let first = request(&router, uri, Some(valid_token()), "{}").await;
    assert_eq!(first.status(), StatusCode::OK);
    assert_eq!(
        policy_count(&state),
        1,
        "quota keyed by the validated identity"
    );
    let second = request(&router, uri, Some(valid_token()), "{}").await;
    assert_eq!(second.status(), StatusCode::TOO_MANY_REQUESTS);
    assert_unauthorized(request(&router, uri, Some(expired_token()), "{}").await);
    assert_eq!(policy_count(&state), 1);
    assert_eq!(upstream.received_requests().await.unwrap().len(), 1);
}

#[tokio::test]
async fn regression_proxy_refusal_is_generic_403_without_upstream_call() {
    for require_auth in [true, false] {
        let (_oidc, upstream, mut config) = policy_fixture().await;
        config.api_proxy.require_auth = require_auth;
        let state = AppState::new(config);
        let router = stoa_gateway::build_router(state.clone());
        let mut cases = vec![Some(unscoped_token())];
        if !require_auth {
            cases.push(None);
        }
        for token in cases {
            let response = request(&router, "/proxy/test/echo", token, "{}").await;
            assert_eq!(response.status(), StatusCode::FORBIDDEN);
            let body = to_bytes(response.into_body(), 1024).await.unwrap();
            assert_eq!(body.as_ref(), b"Access denied");
        }
        assert!(upstream.received_requests().await.unwrap().is_empty());
        // Observed, not changed here: the HTTP quota counts after the handler
        // whatever the status, so the identified 403 is counted once; the
        // anonymous 403 has no identity key.
        assert_eq!(policy_count(&state), 1, "require_auth={require_auth}");
    }
}
