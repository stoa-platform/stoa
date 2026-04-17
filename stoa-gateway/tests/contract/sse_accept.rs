//! Accept header content-negotiation tests for `POST /mcp/sse` (CAB-2106).
//!
//! MCP Streamable HTTP transport spec 2025-03-26 requires the server to
//! respond with `text/event-stream` whenever the client accepts it, and to
//! keep the back-compat `application/json` path for callers that do not.
//!
//! These tests lock down the Accept matrix × JSON-RPC method pairing plus
//! the `Mcp-Session-Id` header contract.

use serde_json::{json, Value};

use crate::common::TestApp;

const TEST_TOKEN: &str = "test-bearer-token";

fn initialize_body(id: i64) -> String {
    json!({
        "jsonrpc": "2.0",
        "id": id,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "claude-ai-test", "version": "1.0"}
        }
    })
    .to_string()
}

fn tools_list_body(id: i64) -> String {
    json!({
        "jsonrpc": "2.0",
        "id": id,
        "method": "tools/list"
    })
    .to_string()
}

fn tools_call_unknown_body(id: i64) -> String {
    json!({
        "jsonrpc": "2.0",
        "id": id,
        "method": "tools/call",
        "params": {
            "name": "this-tool-does-not-exist",
            "arguments": {}
        }
    })
    .to_string()
}

fn content_type(headers: &axum::http::HeaderMap) -> String {
    headers
        .get(axum::http::header::CONTENT_TYPE)
        .and_then(|v| v.to_str().ok())
        .unwrap_or("")
        .to_string()
}

// ===========================================================
// Accept: text/event-stream → SSE response
// ===========================================================

#[tokio::test]
async fn initialize_returns_sse_when_accept_is_event_stream() {
    let app = TestApp::new();
    let (status, headers, body) = app
        .post_raw(
            "/mcp/sse",
            &initialize_body(1),
            Some("text/event-stream"),
            Some(TEST_TOKEN),
        )
        .await;

    assert_eq!(status, axum::http::StatusCode::OK);
    assert!(
        content_type(&headers).starts_with("text/event-stream"),
        "expected text/event-stream, got: {}",
        content_type(&headers)
    );
    assert!(
        body.contains("event: message"),
        "body must include SSE message event, got: {}",
        body
    );
    assert!(
        body.contains("\"jsonrpc\":\"2.0\""),
        "body must embed JSON-RPC response, got: {}",
        body
    );
    assert!(
        headers.get("mcp-session-id").is_some(),
        "Mcp-Session-Id header must accompany SSE initialize response"
    );
}

#[tokio::test]
async fn initialize_returns_sse_when_accept_lists_both() {
    let app = TestApp::new();
    let (status, headers, body) = app
        .post_raw(
            "/mcp/sse",
            &initialize_body(2),
            Some("application/json, text/event-stream"),
            Some(TEST_TOKEN),
        )
        .await;

    assert_eq!(status, axum::http::StatusCode::OK);
    assert!(
        content_type(&headers).starts_with("text/event-stream"),
        "MCP-compliant client (both media types) must get SSE; got: {}",
        content_type(&headers)
    );
    assert!(body.contains("event: message"));
}

#[tokio::test]
async fn initialize_returns_sse_with_q_values() {
    let app = TestApp::new();
    let (status, headers, _) = app
        .post_raw(
            "/mcp/sse",
            &initialize_body(3),
            Some("application/json;q=0.8, text/event-stream;q=0.9"),
            Some(TEST_TOKEN),
        )
        .await;

    assert_eq!(status, axum::http::StatusCode::OK);
    assert!(
        content_type(&headers).starts_with("text/event-stream"),
        "q-value-annotated Accept must still route to SSE; got: {}",
        content_type(&headers)
    );
}

#[tokio::test]
async fn initialize_case_insensitive_accept() {
    let app = TestApp::new();
    let (status, headers, _) = app
        .post_raw(
            "/mcp/sse",
            &initialize_body(4),
            Some("Text/Event-Stream"),
            Some(TEST_TOKEN),
        )
        .await;

    assert_eq!(status, axum::http::StatusCode::OK);
    assert!(content_type(&headers).starts_with("text/event-stream"));
}

// ===========================================================
// Accept without text/event-stream → JSON response (back-compat)
// ===========================================================

#[tokio::test]
async fn initialize_returns_json_when_accept_is_json_only() {
    let app = TestApp::new();
    let (status, headers, body) = app
        .post_raw(
            "/mcp/sse",
            &initialize_body(5),
            Some("application/json"),
            Some(TEST_TOKEN),
        )
        .await;

    assert_eq!(status, axum::http::StatusCode::OK);
    assert!(
        content_type(&headers).starts_with("application/json"),
        "Accept: application/json must keep back-compat JSON; got: {}",
        content_type(&headers)
    );
    let parsed: Value = serde_json::from_str(&body).expect("body must parse as JSON");
    assert_eq!(parsed["jsonrpc"], "2.0");
    assert!(
        headers.get("mcp-session-id").is_some(),
        "Mcp-Session-Id must be present on JSON path too"
    );
}

#[tokio::test]
async fn initialize_returns_json_when_accept_absent() {
    let app = TestApp::new();
    let (status, headers, body) = app
        .post_raw("/mcp/sse", &initialize_body(6), None, Some(TEST_TOKEN))
        .await;

    assert_eq!(status, axum::http::StatusCode::OK);
    assert!(
        content_type(&headers).starts_with("application/json"),
        "absent Accept defaults to JSON (legacy clients); got: {}",
        content_type(&headers)
    );
    let parsed: Value = serde_json::from_str(&body).expect("body must parse as JSON");
    assert_eq!(parsed["jsonrpc"], "2.0");
}

// ===========================================================
// Method coverage: tools/list, tools/call via SSE
// ===========================================================

#[tokio::test]
async fn tools_list_sse_wraps_json_rpc_response() {
    let app = TestApp::new();
    let (status, headers, body) = app
        .post_raw(
            "/mcp/sse",
            &tools_list_body(10),
            Some("text/event-stream"),
            Some(TEST_TOKEN),
        )
        .await;

    assert_eq!(status, axum::http::StatusCode::OK);
    assert!(content_type(&headers).starts_with("text/event-stream"));
    assert!(body.contains("event: message"));
    assert!(body.contains("\"tools\""));
}

#[tokio::test]
async fn tools_call_sse_wraps_error_for_unknown_tool() {
    let app = TestApp::new();
    let (status, headers, body) = app
        .post_raw(
            "/mcp/sse",
            &tools_call_unknown_body(11),
            Some("text/event-stream"),
            Some(TEST_TOKEN),
        )
        .await;

    assert_eq!(status, axum::http::StatusCode::OK);
    assert!(content_type(&headers).starts_with("text/event-stream"));
    assert!(body.contains("event: message"));
    assert!(
        body.contains("-32601") || body.contains("not found"),
        "unknown tool must surface METHOD_NOT_FOUND wrapped in SSE message, got: {}",
        body
    );
}

// ===========================================================
// Session reuse
// ===========================================================

#[tokio::test]
async fn session_reuse_does_not_create_new_session() {
    let app = TestApp::new();

    // First call: initialize, no session_id → server mints one
    let (_, headers, _) = app
        .post_raw(
            "/mcp/sse",
            &initialize_body(20),
            Some("application/json"),
            Some(TEST_TOKEN),
        )
        .await;
    let session_id = headers
        .get("mcp-session-id")
        .and_then(|v| v.to_str().ok())
        .expect("initialize must return Mcp-Session-Id")
        .to_string();
    let count_after_first = app.state.session_manager.count();
    assert_eq!(
        count_after_first, 1,
        "initialize must create exactly one session"
    );

    // Second call: tools/list with ?sessionId= → reuse, no new session
    let uri = format!("/mcp/sse?sessionId={}", session_id);
    let (status, headers, _) = app
        .post_raw(
            &uri,
            &tools_list_body(21),
            Some("application/json"),
            Some(TEST_TOKEN),
        )
        .await;
    assert_eq!(status, axum::http::StatusCode::OK);
    assert_eq!(
        headers.get("mcp-session-id").and_then(|v| v.to_str().ok()),
        Some(session_id.as_str()),
        "Mcp-Session-Id must echo the reused session"
    );
    assert_eq!(
        app.state.session_manager.count(),
        count_after_first,
        "second request must NOT create a new session"
    );
}
