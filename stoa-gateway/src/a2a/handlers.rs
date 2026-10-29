//! A2A JSON-RPC Handlers (CAB-1754)
//!
//! Implements the A2A protocol methods:
//! - tasks/send — Submit a task to an agent (with MCP tool bridge)
//! - tasks/get — Retrieve task status and history
//! - tasks/cancel — Cancel a running task

use axum::{
    extract::{Extension, State},
    http::{HeaderMap, StatusCode},
    response::IntoResponse,
    Json,
};
use serde_json::json;
use tracing::{info, warn};
use uuid::Uuid;

use crate::auth::middleware::AuthenticatedUser;
use crate::auth::mtls::{fingerprints_match, ClientCertInfo};
use crate::mcp::handlers::request_tool_context;
use crate::mcp::tools::ToolContent;
use crate::state::AppState;

use super::registry::RegistryError;
use super::types::{
    Artifact, JsonRpcRequest, JsonRpcResponse, Message, MessageRole, Part, Task, TaskCancelParams,
    TaskGetParams, TaskOwner, TaskSendParams, TaskState, TaskStatus, ToolInvocation,
    AGENT_UNAVAILABLE, INVALID_PARAMS, METHOD_NOT_FOUND, TASK_NOT_CANCELABLE, TASK_NOT_FOUND,
};

/// POST /a2a — JSON-RPC 2.0 dispatcher
///
/// Routes incoming JSON-RPC requests to the appropriate handler based on the method field.
/// Applies STOA governance (auth, rate limit, audit) via middleware layers.
pub async fn a2a_handler(
    State(state): State<AppState>,
    headers: HeaderMap,
    user: Option<Extension<AuthenticatedUser>>,
    cert: Option<Extension<ClientCertInfo>>,
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

    // Tasks belong to the validated identity, never to a request field.
    // The owner is the identity validated by the route's JWT layer (tenant
    // claim and subject), never the raw bearer: a renewed token for the same
    // identity keeps its tasks.
    let identity = match user {
        Some(Extension(user)) => task_owner(&state, &user.claims, &headers, cert.as_deref()),
        None => Err(crate::auth::middleware::AuthError::unauthorized(
            "Authentication required",
        )),
    };
    let owner = match identity {
        Ok(owner) => owner,
        Err(e) => {
            let status = match e.error.as_str() {
                "forbidden" => StatusCode::FORBIDDEN,
                _ => StatusCode::UNAUTHORIZED,
            };
            let error = JsonRpcResponse::error(request.id, -32001, e.message);
            return (status, Json(error)).into_response();
        }
    };

    let (status, response) = match request.method.as_str() {
        "tasks/send" => {
            handle_tasks_send_with_headers(&state, registry, &request, &headers, &owner).await
        }
        "tasks/get" => (
            StatusCode::OK,
            handle_tasks_get(registry, &request, &owner).await,
        ),
        "tasks/cancel" => (
            StatusCode::OK,
            handle_tasks_cancel(registry, &request, &owner).await,
        ),
        other => {
            warn!(method = other, "Unknown A2A method");
            (
                StatusCode::OK,
                JsonRpcResponse::error(
                    request.id,
                    METHOD_NOT_FOUND,
                    format!("Method not found: {other}"),
                ),
            )
        }
    };

    (status, Json(response)).into_response()
}

/// Task owner from validated claims; an `X-Tenant-ID` header must match.
/// Federation claims follow `request_identity`. No DPoP proof verifier is
/// wired, so a `cnf.jkt` token is refused; a `cnf.x5t#S256` token needs the
/// client certificate extracted by the mTLS layer, and must match it.
fn task_owner(
    state: &AppState,
    claims: &crate::auth::claims::Claims,
    headers: &HeaderMap,
    cert: Option<&ClientCertInfo>,
) -> Result<TaskOwner, crate::auth::middleware::AuthError> {
    use crate::auth::middleware::AuthError;
    if claims.sub.trim().is_empty() {
        return Err(AuthError::unauthorized("A subject claim is required"));
    }
    let tenant = crate::auth::tenant::require_tenant(claims)?;
    if headers
        .get_all("X-Tenant-ID")
        .iter()
        .any(|h| h.to_str().ok() != Some(tenant))
    {
        return Err(AuthError::forbidden(
            "Tenant header does not match authenticated tenant",
        ));
    }
    if let Some(cnf) = &claims.cnf {
        let bound_to_cert = match (&cnf.jkt, &cnf.x5t_s256, cert) {
            (None, None, _) => true,
            (None, Some(x5t), Some(cert)) => {
                fingerprints_match(&cert.fingerprint, x5t).unwrap_or(false)
            }
            _ => false,
        };
        if !bound_to_cert {
            return Err(AuthError::unauthorized(
                "Sender-constrained tokens unsupported on this transport",
            ));
        }
    }
    crate::auth::tenant::check_federation_claims(state, claims)?;
    Ok(TaskOwner {
        tenant_id: tenant.to_string(),
        subject: claims.sub.clone(),
        sub_account_id: claims.sub_account_id.clone(),
        master_account_id: claims.master_account_id.clone(),
    })
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
#[cfg(test)]
async fn handle_tasks_send(
    state: &AppState,
    registry: &super::registry::AgentRegistry,
    request: &JsonRpcRequest,
) -> JsonRpcResponse {
    handle_tasks_send_with_headers(state, registry, request, &HeaderMap::new(), &test_owner())
        .await
        .1
}

#[cfg(test)]
fn test_owner() -> TaskOwner {
    TaskOwner {
        tenant_id: "tenant-a".to_string(),
        subject: "user-a".to_string(),
        sub_account_id: None,
        master_account_id: None,
    }
}

/// JSON-RPC error for a failed task write; a taken id is a caller error.
fn store_error(request: &JsonRpcRequest, e: RegistryError) -> JsonRpcResponse {
    match e {
        RegistryError::TaskIdUnavailable => JsonRpcResponse::error(
            request.id.clone(),
            INVALID_PARAMS,
            "Task id is not available",
        ),
        e => JsonRpcResponse::error(
            request.id.clone(),
            AGENT_UNAVAILABLE,
            format!("Failed to store task: {e}"),
        ),
    }
}

async fn handle_tasks_send_with_headers(
    state: &AppState,
    registry: &super::registry::AgentRegistry,
    request: &JsonRpcRequest,
    headers: &HeaderMap,
    owner: &TaskOwner,
) -> (StatusCode, JsonRpcResponse) {
    let params: TaskSendParams = match serde_json::from_value(request.params.clone()) {
        Ok(p) => p,
        Err(e) => {
            return (
                StatusCode::OK,
                JsonRpcResponse::error(
                    request.id.clone(),
                    INVALID_PARAMS,
                    format!("Invalid params: {e}"),
                ),
            );
        }
    };

    // Check for MCP tool invocation in message data parts
    if let Some(invocation) = extract_tool_invocation(&params.message) {
        return handle_tool_bridge(
            state,
            registry,
            &params,
            &invocation,
            request,
            headers,
            owner,
        )
        .await;
    }

    // Check if this is a continuation of a task owned by the caller
    if let Ok(Some(existing)) = registry.get_owned_task(&params.id, owner) {
        return (
            StatusCode::OK,
            handle_continuation(registry, existing, &params, request).await,
        );
    }

    // Create a new task
    (
        StatusCode::OK,
        handle_new_task(registry, &params, request, owner).await,
    )
}

/// Handle MCP tool bridge: route A2A task to an MCP tool
async fn handle_tool_bridge(
    state: &AppState,
    registry: &super::registry::AgentRegistry,
    params: &TaskSendParams,
    invocation: &ToolInvocation,
    request: &JsonRpcRequest,
    headers: &HeaderMap,
    owner: &TaskOwner,
) -> (StatusCode, JsonRpcResponse) {
    let (ctx, tool) = match request_tool_context(state, headers, &invocation.tool).await {
        Ok(authorized) => authorized,
        Err((status, message)) => {
            return (
                status,
                JsonRpcResponse::error(request.id.clone(), -32001, message),
            );
        }
    };
    let task_id = if params.id.is_empty() {
        Uuid::new_v4().to_string()
    } else {
        params.id.clone()
    };
    // Refuse before execution an id held by another owner.
    let taken = registry
        .get_task(&task_id)
        .map(|t| t.is_some_and(|t| t.owner.as_ref() != Some(owner)));
    if !matches!(taken, Ok(false)) {
        return (
            StatusCode::OK,
            store_error(request, RegistryError::TaskIdUnavailable),
        );
    }

    let response = match tool.execute(invocation.arguments.clone(), &ctx).await {
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
                owner: Some(owner.clone()),
            };

            if let Err(e) = registry.store_task(task.clone()) {
                return (StatusCode::OK, store_error(request, e));
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
            owner,
            &format!("Tool execution failed: {e}"),
        ),
    };
    (StatusCode::OK, response)
}

/// Handle continuation of an existing task
async fn handle_continuation(
    registry: &super::registry::AgentRegistry,
    mut existing: Task,
    params: &TaskSendParams,
    request: &JsonRpcRequest,
) -> JsonRpcResponse {
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
        return store_error(request, e);
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
    owner: &TaskOwner,
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
        owner: Some(owner.clone()),
    };

    if let Err(e) = registry.store_task(task.clone()) {
        return store_error(request, e);
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
    owner: &TaskOwner,
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
        owner: Some(owner.clone()),
    };

    if let Err(e @ RegistryError::TaskIdUnavailable) = registry.store_task(task.clone()) {
        return store_error(request, e);
    }

    JsonRpcResponse::success(
        request.id.clone(),
        serde_json::to_value(&task).unwrap_or_default(),
    )
}

/// Handle tasks/get — retrieve task status
async fn handle_tasks_get(
    registry: &super::registry::AgentRegistry,
    request: &JsonRpcRequest,
    owner: &TaskOwner,
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

    match registry.get_owned_task(&params.id, owner) {
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
    owner: &TaskOwner,
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

    match registry.get_owned_task(&params.id, owner) {
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
            let task = registry.get_owned_task(&params.id, owner).ok().flatten();
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
        let resp = handle_tasks_get(registry, &get_req, &test_owner()).await;
        assert!(resp.error.is_none());
        assert_eq!(resp.result.unwrap()["id"], "task-1");
    }

    #[tokio::test]
    async fn test_tasks_get_not_found() {
        let registry = make_registry();
        let req = get_request("nonexistent");
        let resp = handle_tasks_get(&registry, &req, &test_owner()).await;
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
        let resp = handle_tasks_get(registry, &req, &test_owner()).await;
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
            owner: Some(test_owner()),
        };
        registry.store_task(task).unwrap();

        let req = cancel_request("task-1");
        let resp = handle_tasks_cancel(&registry, &req, &test_owner()).await;
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
        let resp = handle_tasks_cancel(registry, &req, &test_owner()).await;
        assert!(resp.error.is_some());
        assert_eq!(resp.error.unwrap().code, TASK_NOT_CANCELABLE);
    }

    #[tokio::test]
    async fn test_tasks_cancel_not_found() {
        let registry = make_registry();
        let req = cancel_request("nonexistent");
        let resp = handle_tasks_cancel(&registry, &req, &test_owner()).await;
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
            owner: None,
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
        assert_eq!(resp.error.as_ref().unwrap().code, -32001);
        assert!(resp.result.is_none());
        assert!(registry.get_task("tool-task-1").unwrap().is_none());
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

    #[test]
    fn regression_task_owner_separates_federated_sub_accounts() {
        let state = AppState::new(Config {
            federation_enabled: true,
            ..Config::default()
        });
        let owner = |sub_account: &str| {
            let claims: crate::auth::claims::Claims = serde_json::from_value(serde_json::json!({
                "sub": "user-a", "exp": 9999999999u64, "iat": 1, "iss": "https://issuer.test",
                "tenant_id": "tenant-a", "sub_account_id": sub_account, "master_account_id": "m-1"
            }))
            .unwrap();
            task_owner(&state, &claims, &HeaderMap::new(), None).unwrap()
        };
        assert_ne!(owner("sub-1"), owner("sub-2"));
        assert_eq!(owner("sub-1").sub_account_id.as_deref(), Some("sub-1"));
    }

    #[test]
    fn regression_task_owner_separates_federated_masters() {
        let state = AppState::new(Config {
            federation_enabled: true,
            ..Config::default()
        });
        let owner = |master: &str| {
            let claims: crate::auth::claims::Claims = serde_json::from_value(serde_json::json!({
                "sub": "user-a", "exp": 9999999999u64, "iat": 1, "iss": "https://issuer.test",
                "tenant_id": "tenant-a", "sub_account_id": "sub-1", "master_account_id": master
            }))
            .unwrap();
            task_owner(&state, &claims, &HeaderMap::new(), None).unwrap()
        };
        assert_ne!(owner("m-1"), owner("m-2"));
    }

    fn other_owner() -> TaskOwner {
        TaskOwner {
            tenant_id: "tenant-a".to_string(),
            subject: "user-b".to_string(),
            sub_account_id: None,
            master_account_id: None,
        }
    }

    #[tokio::test]
    async fn regression_tasks_get_hides_other_owner_task() {
        let state = make_state();
        let registry = state.a2a_registry.as_ref().unwrap();
        handle_tasks_send(&state, registry, &send_request("task-1", "secret")).await;

        let foreign = handle_tasks_get(registry, &get_request("task-1"), &other_owner()).await;
        let absent = handle_tasks_get(registry, &get_request("task-x"), &other_owner()).await;
        assert!(foreign.result.is_none());
        assert_eq!(foreign.error.as_ref().unwrap().code, TASK_NOT_FOUND);
        assert_eq!(absent.error.as_ref().unwrap().code, TASK_NOT_FOUND);
        assert_eq!(
            foreign.error.unwrap().message,
            absent.error.unwrap().message.replace("task-x", "task-1")
        );
    }

    #[tokio::test]
    async fn regression_tasks_send_does_not_continue_or_overwrite_other_owner_task() {
        let state = make_state();
        let registry = state.a2a_registry.as_ref().unwrap();
        handle_tasks_send(&state, registry, &send_request("task-1", "first")).await;
        let before = registry.get_task("task-1").unwrap().unwrap();

        let req = send_request("task-1", "intrusion");
        let (_, resp) = handle_tasks_send_with_headers(
            &state,
            registry,
            &req,
            &HeaderMap::new(),
            &other_owner(),
        )
        .await;
        assert!(resp.result.is_none());
        assert_eq!(resp.error.unwrap().code, INVALID_PARAMS);
        let after = registry.get_task("task-1").unwrap().unwrap();
        assert_eq!(after.owner, Some(test_owner()));
        assert_eq!(after.history.len(), before.history.len());
    }
}
