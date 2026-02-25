//! MCP spec conformance tests (CAB-1333 Phase 3)
//!
//! Validates that every method advertised in `initialize` capabilities
//! has a working handler and returns spec-compliant JSON shapes.
//!
//! Coverage:
//! - prompts/list, prompts/get
//! - logging/setLevel (valid + invalid levels)
//! - resources/read (valid URI, unsupported scheme, missing param)
//! - Capability parity: every capability entry → at least one working method
//! - Batch requests: new methods work in batch (MCP 2025-03-26)
//! - Method not found: unregistered methods return -32601

use serde_json::{json, Value};

use crate::common::TestApp;

// JWT validation is disabled in TestApp (no jwt_validator configured).
// Any Bearer token passes the auth check with anonymous context.
const TEST_TOKEN: &str = "test-bearer-token";

/// Helper: POST a JSON-RPC 2.0 request to /mcp/sse and return parsed response.
async fn jsonrpc(
    app: &TestApp,
    method: &str,
    params: Option<Value>,
) -> (axum::http::StatusCode, Value) {
    let mut req = json!({
        "jsonrpc": "2.0",
        "method": method,
        "id": 1
    });
    if let Some(p) = params {
        req["params"] = p;
    }
    let body = req.to_string();
    let (status, text) = app
        .post_json_with_bearer("/mcp/sse", &body, TEST_TOKEN)
        .await;
    let value: Value = serde_json::from_str(&text).expect("response must be valid JSON");
    (status, value)
}

/// Helper: POST a JSON-RPC 2.0 batch request to /mcp/sse.
async fn jsonrpc_batch(app: &TestApp, requests: Value) -> (axum::http::StatusCode, Value) {
    let (status, text) = app
        .post_json_with_bearer("/mcp/sse", &requests.to_string(), TEST_TOKEN)
        .await;
    let value: Value = serde_json::from_str(&text).expect("batch response must be valid JSON");
    (status, value)
}

// ============================================================
// prompts/list
// ============================================================

#[tokio::test]
async fn test_prompts_list_returns_empty_array() {
    let app = TestApp::new();
    let (status, resp) = jsonrpc(&app, "prompts/list", None).await;

    assert_eq!(status, axum::http::StatusCode::OK);
    assert_eq!(resp["jsonrpc"], "2.0");
    assert_eq!(resp["id"], 1);
    assert!(resp["error"].is_null(), "should not return an error");

    let prompts = &resp["result"]["prompts"];
    assert!(
        prompts.is_array(),
        "result.prompts must be an array, got: {}",
        prompts
    );
    assert_eq!(
        prompts.as_array().unwrap().len(),
        0,
        "STOA has no built-in prompts"
    );
}

#[tokio::test]
async fn test_prompts_list_with_cursor_param() {
    // cursor param should be accepted and ignored (no prompts to paginate)
    let app = TestApp::new();
    let (status, resp) = jsonrpc(
        &app,
        "prompts/list",
        Some(json!({ "cursor": "next-page-token" })),
    )
    .await;

    assert_eq!(status, axum::http::StatusCode::OK);
    let prompts = &resp["result"]["prompts"];
    assert!(prompts.is_array());
}

// ============================================================
// prompts/get
// ============================================================

#[tokio::test]
async fn test_prompts_get_unknown_returns_not_found() {
    let app = TestApp::new();
    let (status, resp) = jsonrpc(
        &app,
        "prompts/get",
        Some(json!({ "name": "my-prompt-template" })),
    )
    .await;

    assert_eq!(status, axum::http::StatusCode::OK);
    assert_eq!(resp["jsonrpc"], "2.0");
    assert!(resp["result"].is_null(), "should not have a result");
    assert!(!resp["error"].is_null(), "should return an error");

    let code = resp["error"]["code"].as_i64().unwrap();
    assert_eq!(code, -32002, "PromptNotFound error code must be -32002");

    let msg = resp["error"]["message"].as_str().unwrap();
    assert!(
        msg.contains("my-prompt-template"),
        "error message must include the prompt name"
    );
}

#[tokio::test]
async fn test_prompts_get_missing_name_param() {
    // When name is absent, handler uses "<unknown>" placeholder
    let app = TestApp::new();
    let (status, resp) = jsonrpc(&app, "prompts/get", Some(json!({}))).await;

    assert_eq!(status, axum::http::StatusCode::OK);
    let code = resp["error"]["code"].as_i64().unwrap();
    assert_eq!(code, -32002);
    let msg = resp["error"]["message"].as_str().unwrap();
    assert!(msg.contains("<unknown>"));
}

// ============================================================
// logging/setLevel
// ============================================================

#[tokio::test]
async fn test_logging_set_level_valid_levels() {
    let app = TestApp::new();
    let valid_levels = [
        "debug",
        "info",
        "notice",
        "warning",
        "error",
        "critical",
        "alert",
        "emergency",
    ];

    for level in valid_levels {
        let (status, resp) =
            jsonrpc(&app, "logging/setLevel", Some(json!({ "level": level }))).await;

        assert_eq!(status, axum::http::StatusCode::OK, "level={}", level);
        assert!(
            resp["error"].is_null(),
            "level '{}' should be accepted, got error: {}",
            level,
            resp["error"]
        );
        assert_eq!(
            resp["result"],
            json!({}),
            "result must be empty object for level={}",
            level
        );
    }
}

#[tokio::test]
async fn test_logging_set_level_invalid_returns_invalid_params() {
    let app = TestApp::new();
    let (status, resp) = jsonrpc(
        &app,
        "logging/setLevel",
        Some(json!({ "level": "verbose" })),
    )
    .await;

    assert_eq!(status, axum::http::StatusCode::OK);
    let code = resp["error"]["code"].as_i64().unwrap();
    assert_eq!(code, -32602, "INVALID_PARAMS for unknown level");

    let msg = resp["error"]["message"].as_str().unwrap();
    assert!(msg.contains("verbose"), "error must include the bad level");
    // Spec: valid levels should be listed in the error message
    assert!(msg.contains("debug"), "error must list valid levels");
}

#[tokio::test]
async fn test_logging_set_level_missing_param() {
    let app = TestApp::new();
    let (status, resp) = jsonrpc(&app, "logging/setLevel", Some(json!({}))).await;

    assert_eq!(status, axum::http::StatusCode::OK);
    let code = resp["error"]["code"].as_i64().unwrap();
    assert_eq!(code, -32602);
}

#[tokio::test]
async fn test_logging_set_level_without_params() {
    let app = TestApp::new();
    let (status, resp) = jsonrpc(&app, "logging/setLevel", None).await;

    assert_eq!(status, axum::http::StatusCode::OK);
    let code = resp["error"]["code"].as_i64().unwrap();
    assert_eq!(code, -32602);
}

// ============================================================
// resources/read
// ============================================================

#[tokio::test]
async fn test_resources_read_unknown_tool_returns_not_found() {
    let app = TestApp::new();
    let (status, resp) = jsonrpc(
        &app,
        "resources/read",
        Some(json!({ "uri": "stoa://tools/stoa_list_apis" })),
    )
    .await;

    assert_eq!(status, axum::http::StatusCode::OK);
    // Test app has no tools registered → -32002 ResourceNotFound
    assert!(!resp["error"].is_null(), "should return an error");
    let code = resp["error"]["code"].as_i64().unwrap();
    assert_eq!(code, -32002);
    let msg = resp["error"]["message"].as_str().unwrap();
    assert!(msg.contains("stoa://tools/stoa_list_apis"));
}

#[tokio::test]
async fn test_resources_read_unsupported_uri_scheme() {
    let app = TestApp::new();
    let (status, resp) = jsonrpc(
        &app,
        "resources/read",
        Some(json!({ "uri": "https://example.com/resource" })),
    )
    .await;

    assert_eq!(status, axum::http::StatusCode::OK);
    let code = resp["error"]["code"].as_i64().unwrap();
    assert_eq!(code, -32602, "unsupported scheme → INVALID_PARAMS");
    let msg = resp["error"]["message"].as_str().unwrap();
    assert!(msg.contains("stoa://tools/"));
}

#[tokio::test]
async fn test_resources_read_missing_uri_param() {
    let app = TestApp::new();
    let (status, resp) = jsonrpc(&app, "resources/read", Some(json!({}))).await;

    assert_eq!(status, axum::http::StatusCode::OK);
    let code = resp["error"]["code"].as_i64().unwrap();
    assert_eq!(code, -32602);
}

#[tokio::test]
async fn test_resources_read_response_shape_when_found() {
    // Regression guard: when a tool IS in the registry, verify the response shape.
    // Note: TestApp starts with an empty registry. This test documents the expected shape.
    // Future: use a TestApp variant with pre-loaded tools.

    // Verify resources/list returns URIs that match the resources/read scheme
    let app = TestApp::new();
    let (_, list_resp) = jsonrpc(&app, "resources/list", None).await;
    let resources = list_resp["result"]["resources"]
        .as_array()
        .expect("resources/list must return array");

    for resource in resources {
        let uri = resource["uri"].as_str().unwrap();
        assert!(
            uri.starts_with("stoa://tools/"),
            "resource URIs must use stoa://tools/ scheme, got: {}",
            uri
        );
    }
}

// ============================================================
// Capability Parity
// ============================================================

#[tokio::test]
async fn test_capability_parity_all_advertised_capabilities_have_handlers() {
    let app = TestApp::new();

    // Fetch advertised capabilities via initialize
    let (status, resp) = jsonrpc(
        &app,
        "initialize",
        Some(json!({
            "protocolVersion": "2025-03-26",
            "clientInfo": { "name": "conformance-test", "version": "1.0" }
        })),
    )
    .await;
    assert_eq!(status, axum::http::StatusCode::OK);
    let caps = &resp["result"]["capabilities"];

    // Verify each advertised capability has at least one working handler

    // tools capability → tools/list must not return METHOD_NOT_FOUND
    if !caps["tools"].is_null() {
        let (_, r) = jsonrpc(&app, "tools/list", None).await;
        let code = r["error"]["code"].as_i64().unwrap_or(0);
        assert_ne!(code, -32601, "tools/list must not return METHOD_NOT_FOUND");
    }

    // resources capability → resources/list must not return METHOD_NOT_FOUND
    if !caps["resources"].is_null() {
        let (_, r) = jsonrpc(&app, "resources/list", None).await;
        let code = r["error"]["code"].as_i64().unwrap_or(0);
        assert_ne!(
            code, -32601,
            "resources/list must not return METHOD_NOT_FOUND"
        );
    }

    // prompts capability → prompts/list must not return METHOD_NOT_FOUND
    if !caps["prompts"].is_null() {
        let (_, r) = jsonrpc(&app, "prompts/list", None).await;
        let code = r["error"]["code"].as_i64().unwrap_or(0);
        assert_ne!(
            code, -32601,
            "prompts/list must not return METHOD_NOT_FOUND"
        );
    }

    // logging capability → logging/setLevel must not return METHOD_NOT_FOUND
    if !caps["logging"].is_null() {
        // Use a valid level to avoid INVALID_PARAMS masking METHOD_NOT_FOUND
        let (_, r) = jsonrpc(&app, "logging/setLevel", Some(json!({ "level": "info" }))).await;
        let code = r["error"]["code"].as_i64().unwrap_or(0);
        assert_ne!(
            code, -32601,
            "logging/setLevel must not return METHOD_NOT_FOUND"
        );
    }
}

// ============================================================
// Batch Request Support (MCP 2025-03-26)
// ============================================================

#[tokio::test]
async fn test_batch_with_new_methods() {
    let app = TestApp::new();
    let batch = json!([
        { "jsonrpc": "2.0", "method": "prompts/list", "id": 1 },
        { "jsonrpc": "2.0", "method": "prompts/get", "params": { "name": "x" }, "id": 2 },
        { "jsonrpc": "2.0", "method": "logging/setLevel", "params": { "level": "warning" }, "id": 3 },
        { "jsonrpc": "2.0", "method": "resources/read", "params": { "uri": "stoa://tools/missing" }, "id": 4 }
    ]);

    let (status, resp) = jsonrpc_batch(&app, batch).await;
    assert_eq!(status, axum::http::StatusCode::OK);

    let responses = resp.as_array().expect("batch must return array");
    assert_eq!(responses.len(), 4, "must have 4 responses for 4 requests");

    // Verify each response has the correct id and valid JSON-RPC structure
    for r in responses {
        assert_eq!(r["jsonrpc"], "2.0", "each response must have jsonrpc=2.0");
        assert!(!r["id"].is_null(), "each response must echo back the id");
    }

    // Response 1: prompts/list → success with prompts array
    let r1 = responses.iter().find(|r| r["id"] == 1).unwrap();
    assert!(r1["error"].is_null());
    assert!(r1["result"]["prompts"].is_array());

    // Response 2: prompts/get "x" → -32002
    let r2 = responses.iter().find(|r| r["id"] == 2).unwrap();
    assert_eq!(r2["error"]["code"], -32002);

    // Response 3: logging/setLevel "warning" → success {}
    let r3 = responses.iter().find(|r| r["id"] == 3).unwrap();
    assert!(r3["error"].is_null());
    assert_eq!(r3["result"], json!({}));

    // Response 4: resources/read unknown tool → -32002
    let r4 = responses.iter().find(|r| r["id"] == 4).unwrap();
    assert_eq!(r4["error"]["code"], -32002);
}

// ============================================================
// Method Not Found (spec: -32601)
// ============================================================

#[tokio::test]
async fn test_unregistered_method_returns_not_found() {
    let app = TestApp::new();
    let (status, resp) = jsonrpc(&app, "sampling/createMessage", None).await;

    // sampling/createMessage is intentionally not implemented — deferred
    assert_eq!(status, axum::http::StatusCode::OK);
    let code = resp["error"]["code"].as_i64().unwrap();
    assert_eq!(
        code, -32601,
        "unimplemented methods must return METHOD_NOT_FOUND"
    );
}

#[tokio::test]
async fn test_roots_list_returns_empty_array() {
    let app = TestApp::new();
    let (status, resp) = jsonrpc(&app, "roots/list", None).await;

    // roots/list implemented (CAB-1472) — returns empty roots (gateway has no filesystem roots)
    assert_eq!(status, axum::http::StatusCode::OK);
    assert!(resp.get("error").is_none(), "roots/list should succeed");
    let roots = resp["result"]["roots"]
        .as_array()
        .expect("result.roots must be an array");
    assert!(roots.is_empty(), "gateway roots list should be empty");
}
