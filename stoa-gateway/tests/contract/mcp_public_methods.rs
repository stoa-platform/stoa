//! MCP capability-negotiation public-method matrix.
//!
//! CAB-2109 locked `initialize` / `ping` / `notifications/*` as anonymously
//! reachable so claude.ai, MCP Inspector and claude-code can complete the
//! MCP handshake before attaching an OAuth token.
//!
//! CAB-2121 then tightened the surface: `tools/list`, `resources/*`,
//! `prompts/*`, `completion/*`, `roots/list`, `logging/setLevel` were
//! removed from the anonymous allowlist because they leaked tool and
//! resource inventory to unauthenticated callers over Streamable HTTP.
//! Those methods must now 401 when called without a Bearer token, so MCP
//! clients get the standard OAuth challenge and retry with a token.
//!
//! `tools/call` stays covered in its own regression below — it was never
//! part of the anon surface.

use serde_json::{json, Value};

use crate::common::TestApp;

/// Every MCP method that an unauthenticated client is allowed to call
/// during capability negotiation. Pair is `(method, params)`.
fn discovery_methods() -> Vec<(&'static str, Value)> {
    vec![
        (
            "initialize",
            json!({
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "cap-nego", "version": "1.0"}
            }),
        ),
        ("ping", json!({})),
    ]
}

/// MCP methods that used to be anon-accessible (CAB-2109) but were
/// re-gated by CAB-2121 because they leak tool/resource inventory.
fn gated_read_methods() -> Vec<(&'static str, Value)> {
    vec![
        ("tools/list", json!({})),
        ("resources/list", json!({})),
        ("resources/templates/list", json!({})),
        ("resources/read", json!({"uri": "stoa://tools/nonexistent"})),
        ("prompts/list", json!({})),
        ("prompts/get", json!({"name": "nonexistent"})),
        (
            "completion/complete",
            json!({
                "ref": {"type": "ref/prompt", "name": "x"},
                "argument": {"name": "a", "value": "b"}
            }),
        ),
        ("roots/list", json!({})),
        ("logging/setLevel", json!({"level": "info"})),
    ]
}

/// Regression for CAB-2109: every discovery method above must be
/// reachable without an `Authorization` header. 401 on any of them
/// re-opens the claude.ai connector bug.
#[tokio::test]
async fn regression_cab_2109_discovery_methods_are_public() {
    let app = TestApp::new();

    for (method, params) in discovery_methods() {
        let body = json!({
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params
        })
        .to_string();

        let (status, _headers, text) = app
            .post_raw("/mcp/sse", &body, Some("application/json"), None)
            .await;

        assert_eq!(
            status,
            axum::http::StatusCode::OK,
            "method `{}` MUST be reachable anonymously; got {} with body {}",
            method,
            status,
            text
        );

        // Any JSON-RPC error here should be a legitimate domain-level
        // error (e.g. prompt/resource not found), NOT an auth error.
        let parsed: Value = serde_json::from_str(&text).unwrap_or_else(|e| {
            panic!(
                "method `{}` returned non-JSON body: {} ({})",
                method, text, e
            )
        });
        if let Some(err) = parsed.get("error") {
            let code = err.get("code").and_then(|c| c.as_i64()).unwrap_or(0);
            assert_ne!(
                code, -32001,
                "method `{}` still returns -32001 Authentication required: {}",
                method, err
            );
        }
    }
}

/// `notifications/*` are fire-and-forget client messages — must stay
/// accepted anonymously (HTTP 204, no JSON body) so the client can
/// complete the handshake without auth.
#[tokio::test]
async fn regression_cab_2109_notifications_initialized_anonymous() {
    let app = TestApp::new();
    let body = json!({
        "jsonrpc": "2.0",
        "method": "notifications/initialized"
    })
    .to_string();

    let (status, _headers, _body) = app
        .post_raw("/mcp/sse", &body, Some("application/json"), None)
        .await;

    assert_eq!(
        status,
        axum::http::StatusCode::NO_CONTENT,
        "notifications/initialized must accept anonymous posts with 204"
    );
}

/// Regression for CAB-2121: methods removed from the anon allowlist must
/// return 401 `-32001 Authentication required` so MCP clients trigger the
/// OAuth flow instead of receiving a leaked tool/resource inventory.
#[tokio::test]
async fn regression_cab_2121_gated_methods_require_auth() {
    let app = TestApp::new();

    for (method, params) in gated_read_methods() {
        let body = json!({
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params
        })
        .to_string();

        let (status, _headers, text) = app
            .post_raw("/mcp/sse", &body, Some("application/json"), None)
            .await;

        assert_eq!(
            status,
            axum::http::StatusCode::UNAUTHORIZED,
            "method `{}` MUST require auth (CAB-2121); got {} with body {}",
            method,
            status,
            text
        );

        let parsed: Value = serde_json::from_str(&text).unwrap_or_else(|e| {
            panic!(
                "method `{}` returned non-JSON body: {} ({})",
                method, text, e
            )
        });
        let code = parsed
            .get("error")
            .and_then(|e| e.get("code"))
            .and_then(|c| c.as_i64())
            .unwrap_or(0);
        assert_eq!(
            code, -32001,
            "method `{}` must return -32001 Authentication required, got: {}",
            method, parsed
        );
    }
}

/// `tools/call` is intentionally NOT in the public list: without a
/// Bearer token the gateway must still challenge with 401 +
/// `WWW-Authenticate` so MCP clients trigger the OAuth flow.
#[tokio::test]
async fn regression_cab_2109_tools_call_still_requires_auth() {
    let app = TestApp::new();
    let body = json!({
        "jsonrpc": "2.0",
        "id": 42,
        "method": "tools/call",
        "params": {"name": "stoa_platform_health", "arguments": {}}
    })
    .to_string();

    let (status, headers, text) = app
        .post_raw("/mcp/sse", &body, Some("application/json"), None)
        .await;

    assert_eq!(
        status,
        axum::http::StatusCode::UNAUTHORIZED,
        "tools/call without Bearer must 401 (got body {})",
        text
    );
    let www = headers
        .get("www-authenticate")
        .and_then(|v| v.to_str().ok())
        .unwrap_or_default();
    assert!(
        www.contains("Bearer"),
        "401 must carry a Bearer challenge header, got: {:?}",
        www
    );
}
