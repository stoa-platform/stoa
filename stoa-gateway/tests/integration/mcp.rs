//! MCP protocol integration tests.
//!
//! Tests the MCP discovery, tools, and OAuth endpoints across the full router.
//! In EdgeMcp mode (default), these endpoints are available.

use axum::http::StatusCode;
use std::{collections::HashMap, sync::Arc};
use stoa_gateway::config::Config;
use stoa_gateway::mcp::tools::dynamic_tool::DynamicTool;
use stoa_gateway::mcp::tools::ToolSchema;

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
//
// A missing validator refuses protected requests. Successful tool listings
// use the signed local fixture; negotiation remains public.
// ========================================================================

#[tokio::test]
async fn test_mcp_tools_list_no_validator_denies_access() {
    let app = TestApp::new();
    let (status, body) = app.post_json("/mcp/tools/list", "{}").await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert_eq!(json["isError"], true);
    assert!(json.get("tools").is_none());
}

#[tokio::test]
async fn test_mcp_tools_call_no_validator_unknown_tool() {
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

// regression for CAB-2227
#[tokio::test]
async fn test_unauthenticated_tools_call_is_rejected_before_cp_lookup() {
    let app = TestApp::with_config(Config {
        control_plane_url: Some("http://127.0.0.1:1".to_string()),
        quota_enforcement_enabled: false,
        ..Config::default()
    });
    let schema = ToolSchema {
        schema_type: "object".to_string(),
        properties: HashMap::new(),
        required: Vec::new(),
    };
    let tool = DynamicTool::new(
        "any_tool",
        "permission regression tool",
        "http://localhost:9/noop",
        "POST",
        schema,
        "default",
    )
    .into_public();
    app.state.tool_registry.register(Arc::new(tool));

    let (status, _) = app
        .post_json("/mcp/tools/call", r#"{"name":"any_tool","arguments":{}}"#)
        .await;

    // Authentication fails before a tenant permission lookup can be attempted.
    assert_eq!(status, StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn test_mcp_tools_list_no_validator_denial_shape() {
    let app = TestApp::new();
    let (status, body) = app.post_json("/mcp/tools/list", "{}").await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert_eq!(json["isError"], true);
    assert!(json.get("tools").is_none());
}

// ========================================================================
// MCP v1 REST API (validator unset → auth middleware passthrough)
// ========================================================================

#[tokio::test]
async fn test_mcp_rest_tools_list_no_validator() {
    let app = TestApp::new();
    let (status, body) = app.get("/mcp/v1/tools").await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert_eq!(json["isError"], true);
    assert!(json.get("tools").is_none());
}

#[tokio::test]
async fn test_mcp_rest_tools_invoke_no_validator_unknown() {
    let app = TestApp::new();
    // RestToolInvokeRequest: {"tool": "name", "arguments": {}}
    let invoke = r#"{"tool":"nonexistent","arguments":{}}"#;
    let (status, body) = app.post_json("/mcp/v1/tools/invoke", invoke).await;
    assert!(!body.is_empty());
    assert_eq!(status, StatusCode::UNAUTHORIZED);
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

#[tokio::test]
async fn test_authenticated_mcp_tools_list() {
    let app = TestApp::with_mcp_auth().await;
    let (status, body) = app
        .post_json_with_bearer("/mcp/tools/list", "{}", app.mcp_token())
        .await;
    assert_eq!(status, StatusCode::OK);
    let response: serde_json::Value = serde_json::from_str(&body).unwrap();
    assert!(response["tools"].is_array());
}
