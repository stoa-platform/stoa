//! MCP `InitializeResult` shape conformance (CAB-2110).
//!
//! Anthropic's Toolbox validates the `initialize` response against
//! Pydantic schemas. Under `capabilities.experimental`, every value MUST
//! be a dict (per-feature config object), never an array. Claude.ai
//! rejected the connector with:
//!
//!     ValidationError: 1 validation error for InitializeResult
//!     capabilities.experimental.transports
//!       Input should be a valid dictionary [type=dict_type]
//!
//! This test freezes the contract so no one ever advertises a list under
//! `experimental` again.

use serde_json::{json, Value};

use crate::common::TestApp;

#[tokio::test]
async fn regression_cab_2110_experimental_entries_are_all_dicts() {
    let app = TestApp::new();

    let body = json!({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "cab-2110", "version": "1.0"}
        }
    })
    .to_string();

    let (status, _headers, text) = app
        .post_raw("/mcp/sse", &body, Some("application/json"), None)
        .await;
    assert_eq!(status, axum::http::StatusCode::OK);
    let parsed: Value = serde_json::from_str(&text).expect("body must parse as JSON");
    let result = parsed
        .get("result")
        .expect("initialize must return a result object");
    let caps = result
        .get("capabilities")
        .and_then(|v| v.as_object())
        .expect("capabilities must be an object");

    // The `experimental` block, if present, must map feature-name → object.
    if let Some(exp) = caps.get("experimental") {
        let exp_obj = exp
            .as_object()
            .expect("capabilities.experimental must itself be a JSON object");
        for (feature, value) in exp_obj {
            assert!(
                value.is_object(),
                "capabilities.experimental.{} MUST be a JSON object, got {:?} — \
                 re-advertising an array here would re-break the claude.ai connector \
                 (Pydantic validator rejects dict_type).",
                feature,
                value
            );
        }
    }
}

#[tokio::test]
async fn regression_cab_2110_initialize_result_shape_matches_spec() {
    let app = TestApp::new();

    let body = json!({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "cab-2110", "version": "1.0"}
        }
    })
    .to_string();

    let (_status, _headers, text) = app
        .post_raw("/mcp/sse", &body, Some("application/json"), None)
        .await;
    let parsed: Value = serde_json::from_str(&text).expect("body must parse as JSON");
    let result = parsed.get("result").expect("result required");

    // Required scalar fields
    assert!(
        result
            .get("protocolVersion")
            .and_then(|v| v.as_str())
            .is_some(),
        "result.protocolVersion must be a string"
    );
    let server_info = result
        .get("serverInfo")
        .and_then(|v| v.as_object())
        .expect("result.serverInfo must be an object");
    assert!(server_info.get("name").and_then(|v| v.as_str()).is_some());
    assert!(server_info
        .get("version")
        .and_then(|v| v.as_str())
        .is_some());

    // capabilities block must be an object; each standard sub-key must be
    // either absent or an object (never an array).
    let caps = result
        .get("capabilities")
        .and_then(|v| v.as_object())
        .expect("result.capabilities must be an object");
    for key in ["tools", "resources", "prompts", "logging", "elicitation"] {
        if let Some(v) = caps.get(key) {
            assert!(
                v.is_object(),
                "capabilities.{} must be an object, got {:?}",
                key,
                v
            );
        }
    }
}
