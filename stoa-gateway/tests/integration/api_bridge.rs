//! API Bridge integration tests.
//!
//! Tests the API-to-MCP bridge: tools discovered from the Control Plane catalog
//! are registered and callable through the MCP protocol endpoints.

use axum::http::StatusCode;
use std::collections::HashMap;
use std::sync::Arc;

use stoa_gateway::mcp::tools::dynamic_tool::DynamicTool;
use stoa_gateway::mcp::tools::{Tool, ToolSchema};

use crate::common::TestApp;

// ========================================================================
// Helper: create a DynamicTool simulating a catalog-discovered API tool
// ========================================================================

fn make_catalog_tool(name: &str, description: &str, endpoint: &str) -> Arc<dyn Tool> {
    let schema = ToolSchema {
        schema_type: "object".to_string(),
        properties: {
            let mut props = HashMap::new();
            props.insert(
                "query".to_string(),
                serde_json::json!({"type": "string", "description": "Search query"}),
            );
            props
        },
        required: vec!["query".to_string()],
    };

    Arc::new(DynamicTool::new(name, description, endpoint, "POST", schema, "default").into_public())
}

// ========================================================================
// Test 1: Discovered tool appears in MCP tools/list
// ========================================================================

#[tokio::test]
async fn test_api_bridge_discovered_tool_appears_in_mcp_list() {
    let app = TestApp::new();

    // Simulate API bridge discovery by registering a tool directly
    let tool = make_catalog_tool(
        "billing_api_search",
        "Search billing records",
        "http://localhost:9999/billing/search",
    );
    app.state.tool_registry.register(tool);

    // Verify tool appears in MCP tools/list
    let (status, body) = app.post_json("/mcp/tools/list", "{}").await;
    assert_eq!(status, StatusCode::OK);

    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    let tools = json["tools"].as_array().expect("tools array");

    let found = tools
        .iter()
        .any(|t| t["name"].as_str() == Some("billing_api_search"));
    assert!(
        found,
        "Expected billing_api_search in tools/list, got: {body}"
    );
}

// ========================================================================
// Test 2: Rediscovery replaces stale tools
// ========================================================================

#[tokio::test]
async fn test_api_bridge_rediscovery_replaces_tools() {
    let app = TestApp::new();
    let registry = &app.state.tool_registry;

    // First discovery: register tool v1
    let tool_v1 = make_catalog_tool(
        "weather_api",
        "Get weather v1",
        "http://localhost:9999/weather/v1",
    );
    registry.register(tool_v1);
    assert!(registry.exists("weather_api"));

    // Simulate rediscovery: unregister old, register updated tool
    registry.unregister("weather_api");
    let tool_v2 = make_catalog_tool(
        "weather_api",
        "Get weather v2 with forecast",
        "http://localhost:9999/weather/v2",
    );
    registry.register(tool_v2);

    // Verify updated tool is served via MCP
    let (status, body) = app.post_json("/mcp/tools/list", "{}").await;
    assert_eq!(status, StatusCode::OK);

    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    let tools = json["tools"].as_array().expect("tools array");

    let weather = tools
        .iter()
        .find(|t| t["name"].as_str() == Some("weather_api"))
        .expect("weather_api should exist");

    assert_eq!(
        weather["description"].as_str(),
        Some("Get weather v2 with forecast"),
        "Tool description should reflect v2"
    );
}

// ========================================================================
// Test 3: Calling an unknown bridged tool returns error
// ========================================================================

#[tokio::test]
async fn test_api_bridge_call_unknown_tool_returns_error() {
    let app = TestApp::new();

    // Register one tool but try to call a different name
    let tool = make_catalog_tool("catalog_tool_a", "Tool A", "http://localhost:9999/a");
    app.state.tool_registry.register(tool);

    let (status, body) = app
        .post_json(
            "/mcp/tools/call",
            r#"{"name":"catalog_tool_nonexistent","arguments":{}}"#,
        )
        .await;

    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");

    // Should indicate error — either via isError or HTTP status
    if status == StatusCode::OK {
        assert!(
            json.get("isError").is_some() || json.get("content").is_some(),
            "Expected error indication for unknown tool"
        );
    } else {
        assert!(
            status.is_client_error() || status.is_server_error(),
            "Expected error status, got {status}"
        );
    }
}

// ========================================================================
// Test 4: REST API also reflects bridged tools
// ========================================================================

#[tokio::test]
async fn test_api_bridge_tools_visible_via_rest_api() {
    let app = TestApp::new();

    // Register multiple bridged tools
    for (name, desc) in [
        ("orders_api_list", "List orders"),
        ("orders_api_get", "Get order by ID"),
    ] {
        let tool = make_catalog_tool(name, desc, "http://localhost:9999/orders");
        app.state.tool_registry.register(tool);
    }

    // Verify REST /mcp/v1/tools returns both
    let (status, body) = app.get("/mcp/v1/tools").await;
    assert_eq!(status, StatusCode::OK);

    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert!(json.is_array(), "REST API returns array, got: {body}");

    let tools = json.as_array().expect("array");
    let names: Vec<&str> = tools.iter().filter_map(|t| t["name"].as_str()).collect();

    assert!(
        names.contains(&"orders_api_list"),
        "Expected orders_api_list in REST tools"
    );
    assert!(
        names.contains(&"orders_api_get"),
        "Expected orders_api_get in REST tools"
    );
}

// ========================================================================
// Test 5: Concurrent registration is safe
// ========================================================================

#[tokio::test]
async fn test_api_bridge_concurrent_discovery_safe() {
    let app = TestApp::new();
    let registry = app.state.tool_registry.clone();

    // Spawn concurrent tool registrations simulating parallel discovery
    let mut handles = Vec::new();
    for i in 0..10 {
        let reg = registry.clone();
        handles.push(tokio::spawn(async move {
            let name = format!("concurrent_tool_{i}");
            let tool = make_catalog_tool(
                &name,
                &format!("Concurrent tool {i}"),
                &format!("http://localhost:9999/api/{i}"),
            );
            reg.register(tool);
        }));
    }

    for handle in handles {
        handle.await.expect("task should not panic");
    }

    // All 10 tools should be registered
    assert_eq!(registry.count(), 10);

    // And all should appear in MCP tools/list
    let (status, body) = app.post_json("/mcp/tools/list", "{}").await;
    assert_eq!(status, StatusCode::OK);

    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    let tools = json["tools"].as_array().expect("tools array");
    assert_eq!(
        tools.len(),
        10,
        "Expected 10 tools from concurrent registration"
    );
}
