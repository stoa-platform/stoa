//! A2A JSON-RPC Handlers (CAB-1754)
//!
//! Implements the A2A protocol methods:
//! - tasks/send — Submit a task to an agent (with MCP tool bridge)
//! - tasks/get — Retrieve task status and history
//! - tasks/cancel — Cancel a running task

use axum::{extract::State, http::StatusCode, response::IntoResponse, Json};
use serde_json::json;
use tracing::{info, warn};
use uuid::Uuid;

use crate::mcp::tools::{ToolContent, ToolContext};
use crate::state::AppState;

use super::types::{
    Artifact, JsonRpcRequest, JsonRpcResponse, Message, MessageRole, Part, Task, TaskCancelParams,
    TaskGetParams, TaskSendParams, TaskState, TaskStatus, ToolInvocation, AGENT_UNAVAILABLE,
    INVALID_PARAMS, METHOD_NOT_FOUND, TASK_NOT_CANCELABLE, TASK_NOT_FOUND,
};

/// POST /a2a — JSON-RPC 2.0 dispatcher
///
/// Routes incoming JSON-RPC requests to the appropriate handler based on the method field.
/// Applies STOA governance (auth, rate limit, audit) via middleware layers.
pub async fn a2a_handler(
    State(state): State<AppState>,
    Json(request): Json<JsonRpcRequest>,
) -> impl IntoResponse {
    let Some(ref registry) = state.a2a_registry else {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(JsonRpcResponse::error(
                request.id,
                AGENT_UNAVAILABLE,
                "A2A protocol is not enabled on this gateway",
            )),
        )
            .into_response();
    };

    info!(method = %request.method, id = %request.id, "A2A JSON-RPC request");

    let response = match request.method.as_str() {
        "tasks/send" => handle_tasks_send(&state, registry, &request).await,
        "tasks/get" => handle_tasks_get(registry, &request).await,
        "tasks/cancel" => handle_tasks_cancel(registry, &request).await,
        other => {
            warn!(method = other, "Unknown A2A method");
            JsonRpcResponse::error(
                request.id,
                METHOD_NOT_FOUND,
                format!("Method not found: {other}"),
            )
        }
    };

    Json(response).into_response()
}

/// Extract a ToolInvocation from a message's Data parts, if present.
fn extract_tool_invocation(message: &Message) -> Option<ToolInvocation> {
    for part in &message.parts {
        if let Part::Data { data } = part {
            if let Ok(invocation) = serde_json::from_value::<ToolInvocation>(data.clone()) {
                if !invocation.tool.is_empty() {
                    return Some(invocation);
                }
            }
        }
    }
    None
}

/// Handle tasks/send — create or continue a task, with MCP tool bridge
async fn handle_tasks_send(
    state: &AppState,
    registry: &super::registry::AgentRegistry,
    request: &JsonRpcRequest,
) -> JsonRpcResponse {
    let params: TaskSendParams = match serde_json::from_value(request.params.clone()) {
        Ok(p) => p,
        Err(e) => {
            return JsonRpcResponse::error(
                request.id.clone(),
                INVALID_PARAMS,
                format!("Invalid params: {e}"),
            );
        }
    };

    // Check for MCP tool invocation in message data parts
    if let Some(invocation) = extract_tool_invocation(&params.message) {
        return handle_tool_bridge(state, registry, &params, &invocation, request).await;
    }

    // Check if this is a continuation of an existing task
    if let Ok(Some(_)) = registry.get_task(&params.id) {
        return handle_continuation(registry, &params, request).await;
    }

    // Create a new task
    handle_new_task(registry, &params, request).await
}

/// Handle MCP tool bridge: route A2A task to an MCP tool
async fn handle_tool_bridge(
    state: &AppState,
    registry: &super::registry::AgentRegistry,
    params: &TaskSendParams,
    invocation: &ToolInvocation,
    request: &JsonRpcRequest,
) -> JsonRpcResponse {
    let task_id = if params.id.is_empty() {
        Uuid::new_v4().to_string()
    } else {
        params.id.clone()
    };

    let tool = match state.tool_registry.get(&invocation.tool) {
        Some(t) => t,
        None => {
            let available: Vec<String> = state
                .tool_registry
                .list(None)
                .iter()
                .map(|d| d.name.clone())
                .collect();
            return create_failed_task_response(
                registry,
                &task_id,
                params,
                request,
                &format!(
                    "Tool '{}' not found. Available: {}",
                    invocation.tool,
                    available.join(", ")
                ),
            );
        }
    };

    let ctx = ToolContext {
        tenant_id: params
            .metadata
            .get("tenantId")
            .and_then(|v| v.as_str())
            .unwrap_or("a2a-default")
            .to_string(),
        user_id: Some(
            params
                .metadata
                .get("agentId")
                .and_then(|v| v.as_str())
                .unwrap_or("a2a-agent")
                .to_string(),
        ),
        user_email: None,
        request_id: format!("a2a-{task_id}"),
        roles: vec!["agent".to_string()],
        scopes: vec!["stoa:read".to_string(), "stoa:execute".to_string()],
        raw_token: None,
        consumer_id: "a2a-bridge".to_string(),
        progress_token: None,
        skill_instructions: None,
    };

    match tool.execute(invocation.arguments.clone(), &ctx).await {
        Ok(result) => {
            let parts: Vec<Part> = result
                .content
                .into_iter()
                .map(|c| match c {
                    ToolContent::Text { text } => Part::Text { text },
                    ToolContent::Image { data, mime_type } => Part::Data {
                        data: json!({"type": "image", "data": data, "mimeType": mime_type}),
                    },
                    ToolContent::Resource { uri, text } => Part::Data {
                        data: json!({"type": "resource", "uri": uri, "text": text}),
                    },
                })
                .collect();

            let response_message = Message {
                role: MessageRole::Agent,
                parts: parts.clone(),
                metadata: Default::default(),
            };

            let task = Task {
                id: task_id.clone(),
                context_id: params.context_id.clone(),
                status: TaskStatus {
                    state: TaskState::Completed,
                    message: Some(response_message.clone()),
                    timestamp: Some(chrono::Utc::now().to_rfc3339()),
                },
                history: vec![params.message.clone(), response_message],
                artifacts: vec![Artifact {
                    name: Some("tool-result".to_string()),
                    description: Some(format!("Result from MCP tool '{}'", invocation.tool)),
                    parts,
                    index: Some(0),
                    last_chunk: Some(true),
                    metadata: Default::default(),
                }],
                metadata: params.metadata.clone(),
            };

            if let Err(e) = registry.store_task(task.clone()) {
                return JsonRpcResponse::error(
                    request.id.clone(),
                    AGENT_UNAVAILABLE,
                    format!("Failed to store task: {e}"),
                );
            }

            info!(task_id = %task_id, tool = %invocation.tool, "A2A→MCP tool bridge completed");
            JsonRpcResponse::success(
                request.id.clone(),
                serde_json::to_value(&task).unwrap_or_default(),
            )
        }
        Err(e) => create_failed_task_response(
            registry,
            &task_id,
            params,
            request,
            &format!("Tool execution failed: {e}"),
        ),
    }
}

/// Handle continuation of an existing task
async fn handle_continuation(
    registry: &super::registry::AgentRegistry,
    params: &TaskSendParams,
    request: &JsonRpcRequest,
) -> JsonRpcResponse {
    let mut existing = match registry.get_task(&params.id) {
        Ok(Some(t)) => t,
        _ => {
            return JsonRpcResponse::error(
                request.id.clone(),
                TASK_NOT_FOUND,
                format!("Task not found: {}", params.id),
            );
        }
    };

    existing.history.push(params.message.clone());
    existing.status = TaskStatus {
        state: TaskState::Working,
        message: None,
        timestamp: Some(chrono::Utc::now().to_rfc3339()),
    };

    let response_message = create_gateway_response(&existing);
    existing.history.push(response_message.clone());
    existing.artifacts.push(Artifact {
        name: Some("response".to_string()),
        description: None,
        parts: vec![Part::Text {
            text: format!(
                "Task {} continued. {} messages in history.",
                existing.id,
                existing.history.len()
            ),
        }],
        index: Some(existing.artifacts.len() as u32),
        last_chunk: Some(true),
        metadata: Default::default(),
    });
    existing.status = TaskStatus {
        state: TaskState::Completed,
        message: Some(response_message),
        timestamp: Some(chrono::Utc::now().to_rfc3339()),
    };

    if let Err(e) = registry.store_task(existing.clone()) {
        return JsonRpcResponse::error(
            request.id.clone(),
            AGENT_UNAVAILABLE,
            format!("Failed to update task: {e}"),
        );
    }

    info!(task_id = %existing.id, "A2A task continued");
    JsonRpcResponse::success(
        request.id.clone(),
        serde_json::to_value(&existing).unwrap_or_default(),
    )
}

/// Handle creation of a new task (no tool invocation)
async fn handle_new_task(
    registry: &super::registry::AgentRegistry,
    params: &TaskSendParams,
    request: &JsonRpcRequest,
) -> JsonRpcResponse {
    let task_id = if params.id.is_empty() {
        Uuid::new_v4().to_string()
    } else {
        params.id.clone()
    };

    let response_message = Message {
        role: MessageRole::Agent,
        parts: vec![Part::Text {
            text: format!(
                "Task {task_id} received by STOA Gateway. Processing via governance pipeline."
            ),
        }],
        metadata: Default::default(),
    };

    let task = Task {
        id: task_id.clone(),
        context_id: params.context_id.clone(),
        status: TaskStatus {
            state: TaskState::Completed,
            message: Some(response_message.clone()),
            timestamp: Some(chrono::Utc::now().to_rfc3339()),
        },
        history: vec![params.message.clone(), response_message],
        artifacts: vec![Artifact {
            name: Some("response".to_string()),
            description: None,
            parts: vec![Part::Text {
                text: format!("Task {task_id} processed successfully."),
            }],
            index: Some(0),
            last_chunk: Some(true),
            metadata: Default::default(),
        }],
        metadata: params.metadata.clone(),
    };

    if let Err(e) = registry.store_task(task.clone()) {
        return JsonRpcResponse::error(
            request.id.clone(),
            AGENT_UNAVAILABLE,
            format!("Failed to store task: {e}"),
        );
    }

    info!(task_id = %task_id, "A2A task created and completed");
    JsonRpcResponse::success(
        request.id.clone(),
        serde_json::to_value(&task).unwrap_or_default(),
    )
}

/// Create a failed task and return its JSON-RPC response
fn create_failed_task_response(
    registry: &super::registry::AgentRegistry,
    task_id: &str,
    params: &TaskSendParams,
    request: &JsonRpcRequest,
    error_message: &str,
) -> JsonRpcResponse {
    let error_msg = Message {
        role: MessageRole::Agent,
        parts: vec![Part::Text {
            text: error_message.to_string(),
        }],
        metadata: Default::default(),
    };

    let task = Task {
        id: task_id.to_string(),
        context_id: params.context_id.clone(),
        status: TaskStatus {
            state: TaskState::Failed,
            message: Some(error_msg.clone()),
            timestamp: Some(chrono::Utc::now().to_rfc3339()),
        },
        history: vec![params.message.clone(), error_msg],
        artifacts: vec![],
        metadata: params.metadata.clone(),
    };

    let _ = registry.store_task(task.clone());

    JsonRpcResponse::success(
        request.id.clone(),
        serde_json::to_value(&task).unwrap_or_default(),
    )
}

/// Handle tasks/get — retrieve task status
async fn handle_tasks_get(
    registry: &super::registry::AgentRegistry,
    request: &JsonRpcRequest,
) -> JsonRpcResponse {
    let params: TaskGetParams = match serde_json::from_value(request.params.clone()) {
        Ok(p) => p,
        Err(e) => {
            return JsonRpcResponse::error(
                request.id.clone(),
                INVALID_PARAMS,
                format!("Invalid params: {e}"),
            );
        }
    };

    match registry.get_task(&params.id) {
        Ok(Some(mut task)) => {
            // Optionally truncate history
            if let Some(max_len) = params.history_length {
                if task.history.len() > max_len {
                    let start = task.history.len() - max_len;
                    task.history = task.history[start..].to_vec();
                }
            }
            JsonRpcResponse::success(
                request.id.clone(),
                serde_json::to_value(&task).unwrap_or_default(),
            )
        }
        Ok(None) => JsonRpcResponse::error(
            request.id.clone(),
            TASK_NOT_FOUND,
            format!("Task not found: {}", params.id),
        ),
        Err(e) => JsonRpcResponse::error(
            request.id.clone(),
            AGENT_UNAVAILABLE,
            format!("Registry error: {e}"),
        ),
    }
}

/// Handle tasks/cancel — cancel a running task
async fn handle_tasks_cancel(
    registry: &super::registry::AgentRegistry,
    request: &JsonRpcRequest,
) -> JsonRpcResponse {
    let params: TaskCancelParams = match serde_json::from_value(request.params.clone()) {
        Ok(p) => p,
        Err(e) => {
            return JsonRpcResponse::error(
                request.id.clone(),
                INVALID_PARAMS,
                format!("Invalid params: {e}"),
            );
        }
    };

    match registry.get_task(&params.id) {
        Ok(None) => {
            return JsonRpcResponse::error(
                request.id.clone(),
                TASK_NOT_FOUND,
                format!("Task not found: {}", params.id),
            );
        }
        Err(e) => {
            return JsonRpcResponse::error(
                request.id.clone(),
                AGENT_UNAVAILABLE,
                format!("Registry error: {e}"),
            );
        }
        Ok(Some(_)) => {}
    }

    match registry.cancel_task(&params.id) {
        Ok(true) => {
            info!(task_id = %params.id, "A2A task canceled");
            let task = registry.get_task(&params.id).ok().flatten();
            JsonRpcResponse::success(
                request.id.clone(),
                serde_json::to_value(&task)
                    .unwrap_or(json!({"id": params.id, "status": {"state": "canceled"}})),
            )
        }
        Ok(false) => JsonRpcResponse::error(
            request.id.clone(),
            TASK_NOT_CANCELABLE,
            format!(
                "Task {} is in a terminal state and cannot be canceled",
                params.id
            ),
        ),
        Err(e) => JsonRpcResponse::error(
            request.id.clone(),
            AGENT_UNAVAILABLE,
            format!("Registry error: {e}"),
        ),
    }
}

/// Create a gateway response message for a task.
/// In production, this would be replaced by actual agent routing logic.
fn create_gateway_response(task: &Task) -> Message {
    let last_user_text = task
        .history
        .iter()
        .rev()
        .find(|m| m.role == MessageRole::User)
        .and_then(|m| {
            m.parts.iter().find_map(|p| match p {
                Part::Text { text } => Some(text.clone()),
                _ => None,
            })
        })
        .unwrap_or_else(|| "(no text content)".to_string());

    Message {
        role: MessageRole::Agent,
        parts: vec![Part::Text {
            text: format!(
                "STOA Gateway processed your request: \"{}\". Governance policies applied.",
                if last_user_text.len() > 200 {
                    format!("{}...", &last_user_text[..200])
                } else {
                    last_user_text
                }
            ),
        }],
        metadata: Default::default(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::a2a::types::*;
    use crate::config::Config;
    use std::collections::HashMap;

    fn make_state() -> AppState {
        AppState::new(Config {
            a2a_enabled: true,
            ..Config::default()
        })
    }

    fn make_registry() -> super::super::registry::AgentRegistry {
        super::super::registry::AgentRegistry::new(10, 100)
    }

    fn send_request(id: &str, message_text: &str) -> JsonRpcRequest {
        JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            method: "tasks/send".to_string(),
            params: json!({
                "id": id,
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": message_text}]
                }
            }),
            id: json!(1),
        }
    }

    fn get_request(id: &str) -> JsonRpcRequest {
        JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            method: "tasks/get".to_string(),
            params: json!({"id": id}),
            id: json!(2),
        }
    }

    fn cancel_request(id: &str) -> JsonRpcRequest {
        JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            method: "tasks/cancel".to_string(),
            params: json!({"id": id}),
            id: json!(3),
        }
    }

    #[tokio::test]
    async fn test_tasks_send_creates_task() {
        let state = make_state();
        let registry = state.a2a_registry.as_ref().unwrap();
        let req = send_request("task-1", "Hello, agent!");
        let resp = handle_tasks_send(&state, registry, &req).await;

        assert!(resp.error.is_none());
        let result = resp.result.unwrap();
        assert_eq!(result["id"], "task-1");
        assert_eq!(result["status"]["state"], "completed");
    }

    #[tokio::test]
    async fn test_tasks_send_continues_task() {
        let state = make_state();
        let registry = state.a2a_registry.as_ref().unwrap();

        // First message
        let req1 = send_request("task-1", "First message");
        let resp1 = handle_tasks_send(&state, registry, &req1).await;
        assert!(resp1.error.is_none());

        // Store as working to allow continuation
        registry
            .update_task_status(
                "task-1",
                TaskStatus {
                    state: TaskState::Working,
                    message: None,
                    timestamp: None,
                },
            )
            .unwrap();

        // Second message (continuation)
        let req2 = send_request("task-1", "Follow-up");
        let resp2 = handle_tasks_send(&state, registry, &req2).await;
        assert!(resp2.error.is_none());

        let result = resp2.result.unwrap();
        assert!(result["history"].as_array().unwrap().len() >= 3);
    }

    #[tokio::test]
    async fn test_tasks_get_returns_task() {
        let state = make_state();
        let registry = state.a2a_registry.as_ref().unwrap();

        let send_req = send_request("task-1", "Test");
        handle_tasks_send(&state, registry, &send_req).await;

        let get_req = get_request("task-1");
        let resp = handle_tasks_get(registry, &get_req).await;
        assert!(resp.error.is_none());
        assert_eq!(resp.result.unwrap()["id"], "task-1");
    }

    #[tokio::test]
    async fn test_tasks_get_not_found() {
        let registry = make_registry();
        let req = get_request("nonexistent");
        let resp = handle_tasks_get(&registry, &req).await;
        assert!(resp.error.is_some());
        assert_eq!(resp.error.unwrap().code, TASK_NOT_FOUND);
    }

    #[tokio::test]
    async fn test_tasks_get_with_history_length() {
        let state = make_state();
        let registry = state.a2a_registry.as_ref().unwrap();

        let send_req = send_request("task-1", "Hello");
        handle_tasks_send(&state, registry, &send_req).await;

        let req = JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            method: "tasks/get".to_string(),
            params: json!({"id": "task-1", "historyLength": 1}),
            id: json!(2),
        };
        let resp = handle_tasks_get(registry, &req).await;
        let result = resp.result.unwrap();
        assert!(result["history"].as_array().unwrap().len() <= 1);
    }

    #[tokio::test]
    async fn test_tasks_cancel_working_task() {
        let registry = make_registry();

        let task = Task {
            id: "task-1".to_string(),
            context_id: None,
            status: TaskStatus {
                state: TaskState::Working,
                message: None,
                timestamp: None,
            },
            history: vec![],
            artifacts: vec![],
            metadata: HashMap::new(),
        };
        registry.store_task(task).unwrap();

        let req = cancel_request("task-1");
        let resp = handle_tasks_cancel(&registry, &req).await;
        assert!(resp.error.is_none());

        let result = resp.result.unwrap();
        assert_eq!(result["status"]["state"], "canceled");
    }

    #[tokio::test]
    async fn test_tasks_cancel_completed_task_fails() {
        let state = make_state();
        let registry = state.a2a_registry.as_ref().unwrap();

        let send_req = send_request("task-1", "Done");
        handle_tasks_send(&state, registry, &send_req).await;

        let req = cancel_request("task-1");
        let resp = handle_tasks_cancel(registry, &req).await;
        assert!(resp.error.is_some());
        assert_eq!(resp.error.unwrap().code, TASK_NOT_CANCELABLE);
    }

    #[tokio::test]
    async fn test_tasks_cancel_not_found() {
        let registry = make_registry();
        let req = cancel_request("nonexistent");
        let resp = handle_tasks_cancel(&registry, &req).await;
        assert!(resp.error.is_some());
        assert_eq!(resp.error.unwrap().code, TASK_NOT_FOUND);
    }

    #[tokio::test]
    async fn test_invalid_params() {
        let state = make_state();
        let registry = state.a2a_registry.as_ref().unwrap();
        let req = JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            method: "tasks/send".to_string(),
            params: json!({"wrong_field": true}),
            id: json!(1),
        };
        let resp = handle_tasks_send(&state, registry, &req).await;
        assert!(resp.error.is_some());
        assert_eq!(resp.error.unwrap().code, INVALID_PARAMS);
    }

    #[test]
    fn test_json_rpc_response_success() {
        let resp = JsonRpcResponse::success(json!(1), json!({"result": "ok"}));
        assert_eq!(resp.jsonrpc, "2.0");
        assert!(resp.result.is_some());
        assert!(resp.error.is_none());
    }

    #[test]
    fn test_json_rpc_response_error() {
        let resp = JsonRpcResponse::error(json!(1), -32600, "Invalid Request");
        assert_eq!(resp.jsonrpc, "2.0");
        assert!(resp.result.is_none());
        assert!(resp.error.is_some());
        assert_eq!(resp.error.unwrap().code, -32600);
    }

    #[test]
    fn test_create_gateway_response() {
        let task = Task {
            id: "t1".to_string(),
            context_id: None,
            status: TaskStatus {
                state: TaskState::Working,
                message: None,
                timestamp: None,
            },
            history: vec![Message {
                role: MessageRole::User,
                parts: vec![Part::Text {
                    text: "What can you do?".to_string(),
                }],
                metadata: Default::default(),
            }],
            artifacts: vec![],
            metadata: Default::default(),
        };

        let response = create_gateway_response(&task);
        assert_eq!(response.role, MessageRole::Agent);
        match &response.parts[0] {
            Part::Text { text } => assert!(text.contains("What can you do?")),
            _ => panic!("Expected text part"),
        }
    }

    #[tokio::test]
    async fn test_tasks_send_tool_not_found() {
        let state = make_state();
        let registry = state.a2a_registry.as_ref().unwrap();

        let req = JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            method: "tasks/send".to_string(),
            params: json!({
                "id": "tool-task-1",
                "message": {
                    "role": "user",
                    "parts": [
                        {"type": "data", "data": {"tool": "nonexistent-tool", "arguments": {}}}
                    ]
                }
            }),
            id: json!(1),
        };
        let resp = handle_tasks_send(&state, registry, &req).await;
        assert!(resp.error.is_none()); // Returns success with failed task status
        let result = resp.result.unwrap();
        assert_eq!(result["status"]["state"], "failed");
        assert!(result["status"]["message"]["parts"][0]["text"]
            .as_str()
            .unwrap()
            .contains("not found"));
    }

    #[test]
    fn test_extract_tool_invocation_from_data_part() {
        let message = Message {
            role: MessageRole::User,
            parts: vec![Part::Data {
                data: json!({"tool": "list-apis", "arguments": {"tenant": "acme"}}),
            }],
            metadata: Default::default(),
        };
        let inv = extract_tool_invocation(&message).unwrap();
        assert_eq!(inv.tool, "list-apis");
        assert_eq!(inv.arguments["tenant"], "acme");
    }

    #[test]
    fn test_extract_tool_invocation_no_data() {
        let message = Message {
            role: MessageRole::User,
            parts: vec![Part::Text {
                text: "hello".to_string(),
            }],
            metadata: Default::default(),
        };
        assert!(extract_tool_invocation(&message).is_none());
    }

    #[test]
    fn test_extract_tool_invocation_empty_tool_name() {
        let message = Message {
            role: MessageRole::User,
            parts: vec![Part::Data {
                data: json!({"tool": "", "arguments": {}}),
            }],
            metadata: Default::default(),
        };
        assert!(extract_tool_invocation(&message).is_none());
    }

    #[test]
    fn test_context_id_backward_compat() {
        // Verify sessionId alias works
        let params: TaskSendParams = serde_json::from_value(json!({
            "id": "t1",
            "sessionId": "sess-123",
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "hi"}]
            }
        }))
        .unwrap();
        assert_eq!(params.context_id, Some("sess-123".to_string()));
    }

    #[test]
    fn test_task_state_new_variants() {
        // Verify new A2A v1.0 states serialize correctly
        let auth_required: serde_json::Value =
            serde_json::to_value(TaskState::AuthRequired).unwrap();
        assert_eq!(auth_required, "authrequired");
        let rejected: serde_json::Value = serde_json::to_value(TaskState::Rejected).unwrap();
        assert_eq!(rejected, "rejected");
    }
}
