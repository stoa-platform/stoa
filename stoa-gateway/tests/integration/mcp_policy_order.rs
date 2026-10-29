//! Composed REST policy order; streaming and API-key transports retain native auth.
use axum::body::{to_bytes, Body};
use axum::http::Request;
use axum::response::Response;
use axum::Router;
use serde_json::{json, Value};
use stoa_gateway::{config::Config, mode::GatewayMode, state::AppState};
use tokio_tungstenite::tungstenite::{client::IntoClientRequest, Error};
use tower::ServiceExt;
use wiremock::{matchers::method, Mock, MockServer, ResponseTemplate};

use super::jwt::{self, bad_signature_token, expired_token, valid_token};

const REST: &[(&str, &str)] = &[
    ("POST", "/mcp/tools/list"),
    ("POST", "/mcp/tools/call"),
    ("POST", "/mcp/resources/list"),
    ("POST", "/mcp/resources/read"),
    ("POST", "/mcp/resources/templates/list"),
    ("POST", "/mcp/prompts/list"),
    ("POST", "/mcp/prompts/get"),
    ("POST", "/mcp/completion/complete"),
    ("GET", "/mcp/v1/tools"),
    ("POST", "/mcp/v1/tools/invoke"),
    ("GET", "/mcp/events"),
];

async fn fixture() -> (MockServer, Config) {
    let oidc = jwt::oidc_server().await;
    let mut config = jwt::config(&oidc);
    config.quota_enforcement_enabled = true;
    config.quota_default_rate_per_minute = 0;
    (oidc, config)
}
fn count(state: &AppState) -> u64 {
    state
        .quota_manager
        .get_stats("auth-regression-user")
        .map_or(0, |stats| stats.daily_count)
}
async fn send(
    router: &Router,
    method: &str,
    uri: &str,
    token: Option<&str>,
    body: &str,
) -> Response {
    let mut request = Request::builder()
        .method(method)
        .uri(uri)
        .header("content-type", "application/json");
    if let Some(token) = token {
        request = request.header("authorization", format!("Bearer {token}"));
    }
    router
        .clone()
        .oneshot(request.body(Body::from(body.to_owned())).unwrap())
        .await
        .unwrap()
}
async fn code(router: &Router, method: &str, uri: &str, token: Option<&str>) -> u16 {
    send(router, method, uri, token, "{}")
        .await
        .status()
        .as_u16()
}
async fn body(response: Response) -> Value {
    let bytes = to_bytes(response.into_body(), 1024 * 1024).await.unwrap();
    serde_json::from_slice(&bytes).unwrap()
}
#[tokio::test]
async fn regression_rest_jwt_precedes_supervision_on_all_eleven_routes() {
    let (_oidc, mut config) = fixture().await;
    config.supervision_enabled = true;
    config.supervision_default_tier = stoa_gateway::config::SupervisionDefaultTier::Command;
    for &(method, uri) in REST {
        let state = AppState::new(config.clone());
        let router = stoa_gateway::build_router(state.clone());
        for token in [
            None,
            Some("invalid"),
            Some(bad_signature_token()),
            Some(expired_token()),
        ] {
            let response = send(&router, method, uri, token, "{}").await;
            assert_eq!(response.status().as_u16(), 401, "{uri}");
            assert!(response.headers().contains_key("www-authenticate"));
        }
        assert_eq!(count(&state), 0);
        let response = send(&router, method, uri, Some(valid_token()), "{}").await;
        if method == "POST" {
            assert_eq!(response.status().as_u16(), 403, "{uri}");
            assert_eq!(body(response).await["error"], "supervision_blocked");
            assert_eq!(count(&state), 0);
        } else {
            assert_eq!(response.status().as_u16(), 200, "{uri}");
            assert_eq!(count(&state), 1);
        }
    }
}
#[tokio::test]
async fn regression_rest_quota_charges_once_and_refuses_the_second_request() {
    let (_oidc, mut config) = fixture().await;
    config.quota_default_daily_limit = 1;
    for (method, uri) in [
        ("POST", "/mcp/tools/list"),
        ("POST", "/mcp/resources/list"),
        ("GET", "/mcp/events"),
    ] {
        let state = AppState::new(config.clone());
        let router = stoa_gateway::build_router(state.clone());
        assert_eq!(code(&router, method, uri, Some(valid_token())).await, 200);
        assert_eq!(count(&state), 1, "{uri}: one request, one charge");
        let response = send(&router, method, uri, Some(valid_token()), "{}").await;
        assert_eq!(response.status().as_u16(), 429);
        let error = body(response).await;
        assert!(error["message"].as_str().unwrap().contains("Daily quota"));
        assert_eq!(count(&state), 1);
    }
}
#[tokio::test]
async fn regression_rest_sender_refuses_before_handler_and_preserves_native_bypasses() {
    let (_oidc, mut config) = fixture().await;
    let router = stoa_gateway::build_router(AppState::new(config.clone()));
    assert_eq!(
        code(&router, "POST", "/mcp/resources/list", Some(valid_token())).await,
        200
    );
    config.sender_constraint.enabled = true;
    config.sender_constraint.dpop_required = true;
    for &(method, uri) in REST {
        if uri.starts_with("/mcp/tools/") || uri.starts_with("/mcp/v1/") {
            continue;
        }
        let state = AppState::new(config.clone());
        let router = stoa_gateway::build_router(state.clone());
        let response = send(&router, method, uri, Some(valid_token()), "{}").await;
        assert_eq!(response.status().as_u16(), 401, "{uri}");
        assert_eq!(
            body(response).await["error"],
            "SENDER_CONSTRAINT_DPOP_REQUIRED"
        );
        assert_eq!(count(&state), 0);
    }
    for (method, uri) in [("POST", "/mcp/tools/list"), ("GET", "/mcp/v1/tools")] {
        let router = stoa_gateway::build_router(AppState::new(config.clone()));
        assert_eq!(code(&router, method, uri, Some(valid_token())).await, 200);
    }
}
#[tokio::test]
async fn regression_public_and_streaming_routes_keep_native_negotiation_and_expiry() {
    let (_oidc, config) = fixture().await;
    let state = AppState::new(config);
    let router = stoa_gateway::build_router(state.clone());
    for uri in [
        "/health",
        "/mcp",
        "/mcp/capabilities",
        "/mcp/health",
        "/.well-known/agent.json",
        "/a2a/agents",
    ] {
        assert_eq!(
            code(&router, "GET", uri, Some("fixture-api-key")).await,
            200,
            "{uri}"
        );
    }
    for uri in ["/mcp", "/mcp/sse"] {
        let init = r#"{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"fixture","version":"1"}}}"#;
        let response = send(&router, "POST", uri, None, init).await;
        assert_eq!(response.status().as_u16(), 200);
        assert!(body(response).await["result"]["protocolVersion"].is_string());
    }
    for token in [None, Some(expired_token())] {
        assert_eq!(code(&router, "GET", "/mcp/sse", token).await, 401);
    }
    let response = send(&router, "GET", "/mcp/sse", Some(valid_token()), "{}").await;
    assert_eq!(response.status().as_u16(), 200);
    let content_type = response.headers()["content-type"].to_str().unwrap();
    assert!(content_type.starts_with("text/event-stream"));
    drop(response);
    assert_eq!(count(&state), 0);
    let config = Config {
        auto_register: false,
        ..Config::default()
    };
    let router = stoa_gateway::build_router(AppState::new(config));
    assert_eq!(
        code(&router, "POST", "/mcp/resources/list", None).await,
        200
    );
    assert_eq!(code(&router, "POST", "/mcp/tools/list", None).await, 401);
}
#[tokio::test]
async fn regression_websocket_keeps_subprotocol_auth_and_expired_handshake_refusal() {
    let (_oidc, mut config) = fixture().await;
    config.websocket_enabled = true;
    let router = stoa_gateway::build_router(AppState::new(config));
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let url = format!("ws://{}/mcp/ws", listener.local_addr().unwrap());
    let server = tokio::spawn(async move { axum::serve(listener, router).await.unwrap() });
    let mut statuses = Vec::new();
    for token in [valid_token(), expired_token()] {
        let mut request = url.clone().into_client_request().unwrap();
        let protocol = format!("mcp-auth.{token}").parse().unwrap();
        request
            .headers_mut()
            .insert("sec-websocket-protocol", protocol);
        let connect = tokio_tungstenite::connect_async(request);
        let result = tokio::time::timeout(std::time::Duration::from_secs(3), connect)
            .await
            .unwrap();
        match result {
            Ok((socket, response)) => {
                statuses.push(response.status().as_u16());
                drop(socket);
            }
            Err(Error::Http(response)) => statuses.push(response.status().as_u16()),
            Err(_) => panic!("unexpected loopback handshake error"),
        }
    }
    server.abort();
    assert_eq!(statuses, [101, 401]);
}
#[tokio::test]
async fn regression_bearer_shaped_llm_api_keys_and_missing_dynamic_routes_stay_native() {
    let (_oidc, mut config) = fixture().await;
    let upstream = MockServer::start().await;
    Mock::given(method("POST"))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({
            "content":[], "usage":{"input_tokens":0,"output_tokens":0}
        })))
        .expect(3)
        .mount(&upstream)
        .await;
    config.llm_proxy_enabled = true;
    config.llm_proxy_skip_validation = true;
    config.llm_proxy_upstream_url = upstream.uri();
    config.llm_proxy_mistral_upstream_url = upstream.uri();
    config.llm_proxy_api_key = Some("fixture-upstream".to_string());
    let state = AppState::new(config);
    let router = stoa_gateway::build_router(state.clone());
    for uri in [
        "/v1/messages",
        "/v1/messages/count_tokens",
        "/v1/chat/completions",
    ] {
        let payload = r#"{"model":"fixture","messages":[],"max_tokens":1}"#;
        let response = send(&router, "POST", uri, Some("fixture-api-key"), payload).await;
        assert_eq!(response.status().as_u16(), 200);
    }
    assert_eq!(upstream.received_requests().await.unwrap().len(), 3);
    assert_eq!(
        code(
            &router,
            "GET",
            "/missing-dynamic-route",
            Some("fixture-api-key")
        )
        .await,
        404
    );
    assert_eq!(count(&state), 0);
}

#[tokio::test]
async fn regression_non_edge_modes_keep_anonymous_health() {
    for gateway_mode in [
        GatewayMode::Sidecar,
        GatewayMode::Proxy,
        GatewayMode::Shadow,
    ] {
        let config = Config {
            gateway_mode,
            auto_register: false,
            ..Config::default()
        };
        let router = stoa_gateway::build_router(AppState::new(config));
        assert_eq!(code(&router, "GET", "/health", None).await, 200);
    }
}
