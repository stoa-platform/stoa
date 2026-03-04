//! Tool lifecycle integration tests.
//!
//! Tests full CRUD lifecycle, admin/MCP endpoint consistency,
//! schema validation rejection, and concurrent registry operations.

use axum::http::StatusCode;
use std::collections::HashMap;
use std::sync::Arc;

use stoa_gateway::mcp::tools::dynamic_tool::DynamicTool;
use stoa_gateway::mcp::tools::{Tool, ToolSchema};

use crate::common::TestApp;

/// Create a valid DynamicTool with the given name, made public (no tenant isolation).
fn make_tool(name: &str, description: &str) -> Arc<dyn Tool> {
    let schema = ToolSchema {
        schema_type: "object".to_string(),
        properties: {
            let mut props = HashMap::new();
            props.insert(
                "input".to_string(),
                serde_json::json!({"type": "string", "description": "An input parameter"}),
            );
            props
        },
        required: vec!["input".to_string()],
    };
    Arc::new(
        DynamicTool::new(
            name,
            description,
            "http://localhost:9999/noop",
            "POST",
            schema,
            "default",
        )
        .into_public(),
    )
}

// ========================================================================
// Full CRUD lifecycle
// ========================================================================

#[tokio::test]
async fn test_tool_register_appears_in_list_then_unregister_removes() {
    let app = TestApp::new();
    let registry = &app.state.tool_registry;

    // Initially no tools registered
    assert_eq!(registry.count(), 0);

    // Register a tool
    let tool = make_tool("lifecycle-tool", "A test tool for CRUD");
    registry.register(tool);

    // Verify it appears in the registry
    assert_eq!(registry.count(), 1);
    assert!(registry.exists("lifecycle-tool"));
    assert!(registry.get("lifecycle-tool").is_some());

    // Verify it appears via MCP tools/list endpoint
    let (status, body) = app.post_json("/mcp/tools/list", "{}").await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    let tools = json["tools"].as_array().expect("tools is array");
    assert_eq!(tools.len(), 1);
    assert_eq!(tools[0]["name"], "lifecycle-tool");

    // Unregister
    let removed = registry.unregister("lifecycle-tool");
    assert!(removed);

    // Verify it's gone from registry
    assert_eq!(registry.count(), 0);
    assert!(!registry.exists("lifecycle-tool"));

    // Verify it's gone from MCP endpoint
    let (status, body) = app.post_json("/mcp/tools/list", "{}").await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    let tools = json["tools"].as_array().expect("tools is array");
    assert!(tools.is_empty());

    // Unregister again returns false (already removed)
    assert!(!registry.unregister("lifecycle-tool"));
}

// ========================================================================
// MCP and REST API endpoint consistency
// ========================================================================

#[tokio::test]
async fn test_registered_tools_visible_in_both_mcp_and_rest_endpoints() {
    let app = TestApp::new();
    let registry = &app.state.tool_registry;

    // Register two tools
    registry.register(make_tool("tool-alpha", "First tool"));
    registry.register(make_tool("tool-beta", "Second tool"));

    // Check MCP tools/list (POST /mcp/tools/list)
    let (status, body) = app.post_json("/mcp/tools/list", "{}").await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    let mcp_tools = json["tools"].as_array().expect("tools array");
    assert_eq!(mcp_tools.len(), 2);

    // Extract names from MCP response
    let mut mcp_names: Vec<String> = mcp_tools
        .iter()
        .map(|t| t["name"].as_str().expect("name is string").to_string())
        .collect();
    mcp_names.sort();
    assert_eq!(mcp_names, vec!["tool-alpha", "tool-beta"]);

    // Check REST API (GET /mcp/v1/tools)
    let (status, body) = app.get("/mcp/v1/tools").await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    let rest_tools = json.as_array().expect("REST returns array");
    assert_eq!(rest_tools.len(), 2);

    // Extract names from REST response
    let mut rest_names: Vec<String> = rest_tools
        .iter()
        .map(|t| t["name"].as_str().expect("name is string").to_string())
        .collect();
    rest_names.sort();
    assert_eq!(rest_names, vec!["tool-alpha", "tool-beta"]);

    // Both endpoints return the same set of tools
    assert_eq!(mcp_names, rest_names);
}

// ========================================================================
// Schema validation rejects invalid tools
// ========================================================================

#[tokio::test]
async fn test_try_register_rejects_invalid_tools() {
    let app = TestApp::new();
    let registry = &app.state.tool_registry;

    // Tool with empty name — rejected
    let bad_name = Arc::new(
        DynamicTool::new(
            "",
            "Has empty name",
            "http://localhost:9999/noop",
            "POST",
            ToolSchema {
                schema_type: "object".to_string(),
                properties: HashMap::new(),
                required: vec![],
            },
            "default",
        )
        .into_public(),
    );
    let result = registry.try_register(bad_name);
    assert!(result.is_err());
    let err = result.unwrap_err();
    assert!(err.errors.iter().any(|e| e.field == "name"));

    // Tool with invalid schema type — rejected
    let bad_schema = Arc::new(
        DynamicTool::new(
            "bad-schema-tool",
            "Has wrong schema type",
            "http://localhost:9999/noop",
            "POST",
            ToolSchema {
                schema_type: "array".to_string(),
                properties: HashMap::new(),
                required: vec![],
            },
            "default",
        )
        .into_public(),
    );
    let result = registry.try_register(bad_schema);
    assert!(result.is_err());
    let err = result.unwrap_err();
    assert!(err.errors.iter().any(|e| e.field == "inputSchema.type"));

    // Tool with spaces in name — rejected
    let bad_chars = Arc::new(
        DynamicTool::new(
            "tool with spaces",
            "Invalid name chars",
            "http://localhost:9999/noop",
            "POST",
            ToolSchema {
                schema_type: "object".to_string(),
                properties: HashMap::new(),
                required: vec![],
            },
            "default",
        )
        .into_public(),
    );
    let result = registry.try_register(bad_chars);
    assert!(result.is_err());

    // None of the invalid tools should be in the registry
    assert_eq!(registry.count(), 0);

    // Valid tool still registers fine after rejections
    let valid = make_tool("valid-tool", "This one is fine");
    let result = registry.try_register(valid);
    assert!(result.is_ok());
    assert_eq!(registry.count(), 1);
}

// ========================================================================
// Concurrent register, list, and unregister
// ========================================================================

#[tokio::test]
async fn test_concurrent_register_list_unregister_is_safe() {
    let app = TestApp::new();
    let registry = app.state.tool_registry.clone();

    // Spawn 20 tasks: 10 registering tools, 10 listing
    let mut handles = Vec::new();

    for i in 0..10 {
        let reg = registry.clone();
        handles.push(tokio::spawn(async move {
            let tool = make_tool(
                &format!("concurrent-tool-{}", i),
                &format!("Concurrent tool number {}", i),
            );
            reg.register(tool);
        }));
    }

    for _ in 0..10 {
        let reg = registry.clone();
        handles.push(tokio::spawn(async move {
            // List should never panic even during concurrent registration
            let _tools = reg.list(None);
        }));
    }

    // Wait for all tasks to complete
    for handle in handles {
        handle.await.expect("task should not panic");
    }

    // All 10 tools should be registered
    assert_eq!(registry.count(), 10);

    // Now concurrently unregister half and list
    let mut handles2 = Vec::new();

    for i in 0..5 {
        let reg = registry.clone();
        handles2.push(tokio::spawn(async move {
            reg.unregister(&format!("concurrent-tool-{}", i));
        }));
    }

    for _ in 0..5 {
        let reg = registry.clone();
        handles2.push(tokio::spawn(async move {
            let _tools = reg.list(None);
        }));
    }

    for handle in handles2 {
        handle.await.expect("task should not panic");
    }

    // 5 tools should remain
    assert_eq!(registry.count(), 5);

    // Verify via MCP endpoint
    let (status, body) = app.post_json("/mcp/tools/list", "{}").await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    let tools = json["tools"].as_array().expect("tools array");
    assert_eq!(tools.len(), 5);
}
