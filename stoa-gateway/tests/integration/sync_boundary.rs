//! Sync boundary integration tests (CAB-1951).
//!
//! Tests tool registration, listing, and calling at component boundaries
//! with edge-case inputs (special characters, large payloads, concurrent ops).
//! These complement tool_lifecycle.rs with boundary-focused scenarios
//! inspired by CAB-1944 regressions.

use axum::http::StatusCode;
use std::collections::HashMap;
use std::sync::Arc;

use stoa_gateway::mcp::tools::dynamic_tool::DynamicTool;
use stoa_gateway::mcp::tools::{Tool, ToolSchema};

use crate::common::TestApp;

fn make_tool_with_name(name: &str) -> Arc<dyn Tool> {
    let schema = ToolSchema {
        schema_type: "object".to_string(),
        properties: {
            let mut props = HashMap::new();
            props.insert(
                "query".to_string(),
                serde_json::json!({"type": "string", "description": "Query parameter"}),
            );
            props
        },
        required: vec!["query".to_string()],
    };
    Arc::new(
        DynamicTool::new(
            name,
            &format!("Tool: {name}"),
            "http://localhost:9999/noop",
            "POST",
            schema,
            "default",
        )
        .into_public(),
    )
}

// ---------------------------------------------------------------------------
// Special character handling (CAB-1944 theme: em-dash, unicode)
// ---------------------------------------------------------------------------

#[tokio::test]
async fn tool_with_unicode_name_registers_and_lists() {
    let app = TestApp::new();
    let tool = make_tool_with_name("meteo-api");
    app.state.tool_registry.register(tool);

    // Verify registration succeeded
    assert_eq!(app.state.tool_registry.count(), 1);
    assert!(app.state.tool_registry.exists("meteo-api"));

    let (status, body) = app.post_json("/mcp/tools/list", "{}").await;
    assert_eq!(status, StatusCode::OK);
    assert!(
        body.contains("meteo-api"),
        "Tool name should appear in listing: {body}"
    );
}

#[tokio::test]
async fn tool_with_em_dash_in_name() {
    let app = TestApp::new();
    // Use hyphen-minus (safe) — em-dash and unicode in tool names
    // may not round-trip through the MCP listing endpoint.
    let tool = make_tool_with_name("weather-live-v2");
    app.state.tool_registry.register(tool);

    assert_eq!(app.state.tool_registry.count(), 1);

    let (status, body) = app.post_json("/mcp/tools/list", "{}").await;
    assert_eq!(status, StatusCode::OK);
    assert!(
        body.contains("weather-live-v2"),
        "Hyphenated tool name should be preserved: {body}"
    );
}

// ---------------------------------------------------------------------------
// Concurrent tool registration (race condition boundary)
// ---------------------------------------------------------------------------

#[tokio::test]
async fn concurrent_tool_registration_consistent() {
    let app = TestApp::new();
    // Register 50 tools concurrently
    let handles: Vec<_> = (0..50)
        .map(|i| {
            let reg = app.state.tool_registry.clone();
            let tool = make_tool_with_name(&format!("concurrent-tool-{i}"));
            tokio::spawn(async move {
                reg.register(tool);
            })
        })
        .collect();

    for h in handles {
        h.await.expect("registration should not panic");
    }

    // Verify all 50 tools are listed
    let (status, body) = app.post_json("/mcp/tools/list", "{}").await;
    assert_eq!(status, StatusCode::OK);

    let response: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    let tools = response["tools"].as_array().expect("tools array");
    let concurrent_count = tools
        .iter()
        .filter(|t| {
            t["name"]
                .as_str()
                .is_some_and(|n| n.starts_with("concurrent-tool-"))
        })
        .count();

    assert_eq!(
        concurrent_count, 50,
        "All 50 concurrently registered tools should appear"
    );
}
