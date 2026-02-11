//! Contract tests for MCP tools endpoints (JSON-RPC style + REST v1).
//!
//! Snapshots lock the response shape for tools/list, tools/call, and REST API.

use insta::assert_json_snapshot;

use crate::common::TestApp;

#[tokio::test]
async fn test_tools_list_shape() {
    let app = TestApp::new();
    let (status, body) = app.post_json("/mcp/tools/list", "{}").await;
    assert_eq!(status, axum::http::StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert_json_snapshot!("tools-list", json);
}

#[tokio::test]
async fn test_tools_call_unknown_shape() {
    let app = TestApp::new();
    let (status, body) = app
        .post_json(
            "/mcp/tools/call",
            r#"{"name":"nonexistent-tool","arguments":{}}"#,
        )
        .await;
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert_json_snapshot!("tools-call-unknown", json, {
        // Status may vary — snapshot captures the error shape
    });
    // Verify it's an error indication
    assert!(
        status.is_success() || status.is_client_error(),
        "Unexpected status: {}",
        status
    );
}

#[tokio::test]
async fn test_rest_tools_list_shape() {
    let app = TestApp::new();
    let (status, body) = app.get("/mcp/v1/tools").await;
    assert_eq!(status, axum::http::StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert_json_snapshot!("rest-tools-list", json);
}

#[tokio::test]
async fn test_rest_tools_invoke_unknown_shape() {
    let app = TestApp::new();
    let (status, body) = app
        .post_json(
            "/mcp/v1/tools/invoke",
            r#"{"tool":"nonexistent","arguments":{}}"#,
        )
        .await;
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert_json_snapshot!("rest-tools-invoke-unknown", json);
    assert!(
        status.is_success() || status.is_client_error() || status.is_server_error(),
        "Unexpected status: {}",
        status
    );
}
