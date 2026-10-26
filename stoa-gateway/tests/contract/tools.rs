//! Contract tests for MCP tools endpoints (JSON-RPC style + REST v1).
//!
//! Snapshots lock the response shape for tools/list, tools/call, and REST API.

use insta::assert_json_snapshot;

use crate::common::TestApp;

#[tokio::test]
async fn test_tools_list_shape() {
    let app = TestApp::with_mcp_auth().await;
    let (status, body) = app
        .post_json_with_bearer("/mcp/tools/list", "{}", app.mcp_token())
        .await;
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
    assert_eq!(status, axum::http::StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn test_rest_tools_list_shape() {
    let app = TestApp::with_mcp_auth().await;
    let (status, body) = app.get_with_bearer("/mcp/v1/tools", app.mcp_token()).await;
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
    assert_eq!(status, axum::http::StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn test_authenticated_unknown_tool_keeps_not_found_response() {
    let app = TestApp::with_mcp_auth().await;
    for (uri, body, name) in [
        (
            "/mcp/tools/call",
            r#"{"name":"nonexistent-tool","arguments":{}}"#,
            "nonexistent-tool",
        ),
        (
            "/mcp/v1/tools/invoke",
            r#"{"tool":"nonexistent","arguments":{}}"#,
            "nonexistent",
        ),
    ] {
        let (status, response) = app.post_json_with_bearer(uri, body, app.mcp_token()).await;
        assert_eq!(status, axum::http::StatusCode::NOT_FOUND);
        let response: serde_json::Value = serde_json::from_str(&response).unwrap();
        assert_eq!(response["isError"], true);
        assert_eq!(
            response["content"][0]["text"],
            format!("Tool '{name}' not found")
        );
    }
}
