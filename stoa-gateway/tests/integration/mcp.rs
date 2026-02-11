//! MCP protocol integration tests.
//!
//! Tests the MCP discovery, tools, and OAuth endpoints across the full router.
//! In EdgeMcp mode (default), these endpoints are available.

use axum::http::StatusCode;

use crate::common::TestApp;

// ========================================================================
// MCP Discovery endpoints (no auth required)
// ========================================================================

#[tokio::test]
async fn test_mcp_discovery_returns_json() {
    let app = TestApp::new();
    let (status, body) = app.get("/mcp").await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    // Discovery response has server.name and server.version
    assert_eq!(json["server"]["name"], "STOA Gateway");
    assert!(json["server"]["version"].is_string());
    // serde renames protocol_version → protocolVersion
    assert!(json["server"]["protocolVersion"].is_string());
}

#[tokio::test]
async fn test_mcp_discovery_includes_endpoints() {
    let app = TestApp::new();
    let (status, body) = app.get("/mcp").await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    // Discovery lists available endpoints
    assert_eq!(json["endpoints"]["sse"], "/mcp/sse");
    assert_eq!(json["endpoints"]["tools_list"], "/mcp/tools/list");
    assert_eq!(json["endpoints"]["tools_call"], "/mcp/tools/call");
}

#[tokio::test]
async fn test_mcp_capabilities_endpoint() {
    let app = TestApp::new();
    let (status, body) = app.get("/mcp/capabilities").await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    // Capabilities should list supported features
    assert!(json.is_object());
    assert!(json.get("capabilities").is_some());
}

#[tokio::test]
async fn test_mcp_health_endpoint() {
    let app = TestApp::new();
    let (status, body) = app.get("/mcp/health").await;
    assert_eq!(status, StatusCode::OK);
    assert!(!body.is_empty());
}

// ========================================================================
// MCP Tools — direct JSON (not JSON-RPC envelope)
// ========================================================================

#[tokio::test]
async fn test_mcp_tools_list_returns_tools() {
    let app = TestApp::new();
    // ToolsListRequest expects {"cursor": null} or just {}
    let (status, body) = app.post_json("/mcp/tools/list", "{}").await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    // Response is ToolsListResponse: {"tools": [...]}
    assert!(json["tools"].is_array());
}

#[tokio::test]
async fn test_mcp_tools_call_unknown_tool() {
    let app = TestApp::new();
    // ToolsCallRequest: {"name": "xxx", "arguments": {}}
    let (status, body) = app
        .post_json(
            "/mcp/tools/call",
            r#"{"name":"nonexistent-tool","arguments":{}}"#,
        )
        .await;
    // Should return a response (200 with error content or a non-200)
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    // The response should indicate an error for unknown tool
    if status == StatusCode::OK {
        // Check isError or content indicating failure
        assert!(
            json.get("isError").is_some() || json.get("content").is_some(),
            "Expected error indication for unknown tool"
        );
    } else {
        // Non-200 status is also acceptable for unknown tool
        assert!(status.is_client_error() || status.is_server_error());
    }
}

#[tokio::test]
async fn test_mcp_tools_list_response_structure() {
    // Verify tools/list returns proper ToolsListResponse shape
    let app = TestApp::new();
    let (status, body) = app.post_json("/mcp/tools/list", "{}").await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    // ToolsListResponse has "tools" array (empty without register_tools from main)
    assert!(json["tools"].is_array());
    // Optional next_cursor field
    assert!(json.get("next_cursor").is_none() || json["next_cursor"].is_null());
}

// ========================================================================
// MCP v1 REST API
// ========================================================================

#[tokio::test]
async fn test_mcp_rest_tools_list() {
    let app = TestApp::new();
    let (status, body) = app.get("/mcp/v1/tools").await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    // REST API returns Vec<ToolDefinition> directly as a JSON array
    assert!(json.is_array(), "Expected array, got: {}", body);
}

#[tokio::test]
async fn test_mcp_rest_tools_invoke_unknown() {
    let app = TestApp::new();
    // RestToolInvokeRequest: {"tool": "name", "arguments": {}}
    let invoke = r#"{"tool":"nonexistent","arguments":{}}"#;
    let (status, body) = app.post_json("/mcp/v1/tools/invoke", invoke).await;
    // Should respond with some indication of failure
    assert!(!body.is_empty());
    // Status varies — could be 200 with error content, 404, or 500
    assert!(
        status == StatusCode::OK
            || status == StatusCode::NOT_FOUND
            || status == StatusCode::INTERNAL_SERVER_ERROR
    );
}

// ========================================================================
// OAuth Discovery endpoints (RFC 9728 / 8414)
// ========================================================================

#[tokio::test]
async fn test_oauth_protected_resource_metadata() {
    let app = TestApp::new();
    let (status, body) = app.get("/.well-known/oauth-protected-resource").await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    // RFC 9728: must have resource field
    assert!(json.get("resource").is_some());
}

#[tokio::test]
async fn test_oauth_authorization_server_metadata() {
    let app = TestApp::new();
    let (status, body) = app.get("/.well-known/oauth-authorization-server").await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    // RFC 8414: must have issuer
    assert!(json.get("issuer").is_some());
}

#[tokio::test]
async fn test_openid_configuration_requires_keycloak() {
    // Without Keycloak URL configured, OIDC discovery returns 503
    let app = TestApp::new();
    let (status, _body) = app.get("/.well-known/openid-configuration").await;
    assert_eq!(status, StatusCode::SERVICE_UNAVAILABLE);
}
