//! Contract tests for MCP discovery endpoints.
//!
//! Snapshots lock the JSON response structure for /mcp, /mcp/capabilities, /mcp/health.

use insta::assert_json_snapshot;

use crate::common::TestApp;

#[tokio::test]
async fn test_mcp_discovery_shape() {
    let app = TestApp::new();
    let (status, body) = app.get("/mcp").await;
    assert_eq!(status, axum::http::StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert_json_snapshot!("mcp-discovery", json, {
        ".server.version" => "[version]",
        ".server.protocolVersion" => "[protocol_version]",
    });
}

#[tokio::test]
async fn test_mcp_capabilities_shape() {
    let app = TestApp::new();
    let (status, body) = app.get("/mcp/capabilities").await;
    assert_eq!(status, axum::http::StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert_json_snapshot!("mcp-capabilities", json, {
        ".server.version" => "[version]",
    });
}

#[tokio::test]
async fn test_mcp_health_shape() {
    let app = TestApp::new();
    let (status, body) = app.get("/mcp/health").await;
    assert_eq!(status, axum::http::StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert_json_snapshot!("mcp-health", json);
}
