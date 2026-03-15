//! Contract tests for A2A protocol endpoints (CAB-1754).
//!
//! Snapshots lock the JSON response structure for:
//! - GET /.well-known/agent.json — Agent Card
//! - POST /a2a — JSON-RPC task operations
//! - GET /a2a/agents — Agent listing

use insta::assert_json_snapshot;

use crate::common::TestApp;

fn a2a_app() -> TestApp {
    let config = stoa_gateway::config::Config {
        a2a_enabled: true,
        ..stoa_gateway::config::Config::default()
    };
    TestApp::with_config(config)
}

#[tokio::test]
async fn test_agent_card_shape() {
    let app = a2a_app();
    let (status, body) = app.get("/.well-known/agent.json").await;
    assert_eq!(status, axum::http::StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert_json_snapshot!("a2a-agent-card", json, {
        ".url" => "[url]",
    });
}

#[tokio::test]
async fn test_a2a_tasks_send_shape() {
    let app = a2a_app();
    let body = serde_json::json!({
        "jsonrpc": "2.0",
        "method": "tasks/send",
        "params": {
            "id": "test-task-001",
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "Hello from contract test"}]
            }
        },
        "id": 1
    });
    let (status, response) = app
        .post_json("/a2a", &serde_json::to_string(&body).unwrap())
        .await;
    assert_eq!(status, axum::http::StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&response).expect("valid JSON");

    // Verify JSON-RPC envelope
    assert_eq!(json["jsonrpc"], "2.0");
    assert_eq!(json["id"], 1);
    assert!(json["result"].is_object());
    assert!(json["error"].is_null());

    // Verify task structure
    let task = &json["result"];
    assert_eq!(task["id"], "test-task-001");
    assert_eq!(task["status"]["state"], "completed");
    assert!(task["history"].is_array());
    assert!(task["artifacts"].is_array());
}

#[tokio::test]
async fn test_a2a_tasks_get_not_found_shape() {
    let app = a2a_app();
    let body = serde_json::json!({
        "jsonrpc": "2.0",
        "method": "tasks/get",
        "params": {"id": "nonexistent-task"},
        "id": 2
    });
    let (status, response) = app
        .post_json("/a2a", &serde_json::to_string(&body).unwrap())
        .await;
    assert_eq!(status, axum::http::StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&response).expect("valid JSON");

    assert_eq!(json["jsonrpc"], "2.0");
    assert_eq!(json["id"], 2);
    assert!(json["error"].is_object());
    assert_eq!(json["error"]["code"], -32001); // TASK_NOT_FOUND
}

#[tokio::test]
async fn test_a2a_method_not_found_shape() {
    let app = a2a_app();
    let body = serde_json::json!({
        "jsonrpc": "2.0",
        "method": "unknown/method",
        "params": {},
        "id": 3
    });
    let (status, response) = app
        .post_json("/a2a", &serde_json::to_string(&body).unwrap())
        .await;
    assert_eq!(status, axum::http::StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&response).expect("valid JSON");

    assert_eq!(json["error"]["code"], -32601); // METHOD_NOT_FOUND
}

#[tokio::test]
async fn test_a2a_agents_list_shape() {
    let app = a2a_app();
    let (status, body) = app.get("/a2a/agents").await;
    assert_eq!(status, axum::http::StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");

    assert!(json["agents"].is_array());
    assert_eq!(json["count"], 0); // No agents registered by default
}

#[tokio::test]
async fn test_a2a_tool_bridge_not_found_shape() {
    let app = a2a_app();
    let body = serde_json::json!({
        "jsonrpc": "2.0",
        "method": "tasks/send",
        "params": {
            "id": "tool-task-001",
            "message": {
                "role": "user",
                "parts": [
                    {"type": "text", "text": "Invoke a tool"},
                    {"type": "data", "data": {"tool": "nonexistent-tool", "arguments": {}}}
                ]
            }
        },
        "id": 4
    });
    let (status, response) = app
        .post_json("/a2a", &serde_json::to_string(&body).unwrap())
        .await;
    assert_eq!(status, axum::http::StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&response).expect("valid JSON");

    // Tool bridge returns a failed task (not a JSON-RPC error)
    let task = &json["result"];
    assert_eq!(task["status"]["state"], "failed");
}

#[tokio::test]
async fn test_a2a_protocol_version() {
    let app = a2a_app();
    let (_, body) = app.get("/.well-known/agent.json").await;
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert_eq!(json["protocolVersion"], "1.0");
}
