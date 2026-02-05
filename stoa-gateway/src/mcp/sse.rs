//! MCP SSE Transport Implementation
//!
//! Implements the MCP Streamable HTTP Transport (spec 2025-03-26)
//! Supports both stateless JSON-RPC and stateful SSE connections.

use axum::{
    extract::{Query, State},
    http::{header, HeaderMap, StatusCode},
    response::{sse::Event, IntoResponse, Response, Sse},
    Json,
};
use futures::stream::{self, Stream};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{convert::Infallible, pin::Pin, sync::Arc, time::Duration};
use tokio::sync::mpsc;
use tokio_stream::{wrappers::ReceiverStream, StreamExt};
use tracing::{debug, error, info, warn};
use uuid::Uuid;

use crate::mcp::session::{Session, SessionManager};
use crate::mcp::tools::{ToolContext, ToolRegistry};
use crate::metrics;
use crate::state::AppState;

// ============================================
// JSON-RPC Types
// ============================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JsonRpcRequest {
    pub jsonrpc: String,
    pub method: String,
    #[serde(default)]
    pub params: Option<Value>,
    pub id: Option<Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JsonRpcResponse {
    pub jsonrpc: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<JsonRpcError>,
    pub id: Option<Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JsonRpcError {
    pub code: i32,
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub data: Option<Value>,
}

impl JsonRpcResponse {
    pub fn success(id: Option<Value>, result: Value) -> Self {
        Self {
            jsonrpc: "2.0".to_string(),
            result: Some(result),
            error: None,
            id,
        }
    }

    pub fn error(id: Option<Value>, code: i32, message: impl Into<String>) -> Self {
        Self {
            jsonrpc: "2.0".to_string(),
            result: None,
            error: Some(JsonRpcError {
                code,
                message: message.into(),
                data: None,
            }),
            id,
        }
    }
}

// JSON-RPC Error Codes
const PARSE_ERROR: i32 = -32700;
const INVALID_REQUEST: i32 = -32600;
const METHOD_NOT_FOUND: i32 = -32601;
const INVALID_PARAMS: i32 = -32602;
const INTERNAL_ERROR: i32 = -32603;

// ============================================
// SSE Query Parameters
// ============================================

#[derive(Debug, Deserialize)]
pub struct SseQueryParams {
    /// Session ID for stateful connections
    #[serde(rename = "sessionId")]
    pub session_id: Option<String>,
}

// ============================================
// Handlers
// ============================================

/// POST /mcp/sse - Handle JSON-RPC request
/// 
/// Accepts JSON-RPC requests and returns either:
/// - JSON response for simple requests
/// - SSE stream for streaming responses
pub async fn handle_sse_post(
    State(state): State<AppState>,
    headers: HeaderMap,
    Query(params): Query<SseQueryParams>,
    Json(request): Json<JsonRpcRequest>,
) -> Response {
    let request_id = Uuid::new_v4().to_string();
    debug!(
        request_id = %request_id,
        method = %request.method,
        session_id = ?params.session_id,
        "MCP SSE POST request"
    );

    // Validate JSON-RPC version
    if request.jsonrpc != "2.0" {
        return Json(JsonRpcResponse::error(
            request.id,
            INVALID_REQUEST,
            "Invalid JSON-RPC version",
        ))
        .into_response();
    }

    // === OAuth 2.1 Auth Challenge (RFC 9728) ===
    // Public methods that don't require authentication
    let public_methods = ["initialize", "ping", "notifications/initialized"];
    let has_auth = headers.get(header::AUTHORIZATION).is_some();

    if !public_methods.contains(&request.method.as_str()) && !has_auth {
        debug!(
            method = %request.method,
            "Unauthenticated request to protected method — returning 401"
        );
        return (
            StatusCode::UNAUTHORIZED,
            [(
                "WWW-Authenticate",
                r#"Bearer resource_metadata="/.well-known/oauth-protected-resource""#,
            )],
            Json(JsonRpcResponse::error(
                request.id,
                -32001,
                "Authentication required",
            )),
        )
            .into_response();
    }

    // === JWT Validation & Identity Extraction ===
    // Extract Bearer token from Authorization header
    let raw_token = headers
        .get(header::AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
        .and_then(|auth| {
            let parts: Vec<&str> = auth.splitn(2, ' ').collect();
            if parts.len() == 2 && parts[0].to_lowercase() == "bearer" {
                Some(parts[1].trim().to_string())
            } else {
                None
            }
        });

    // Validate JWT and extract user identity
    let (tenant_id, user_id, user_email, roles, validated_token) =
        if let Some(ref token) = raw_token {
            if let Some(ref validator) = state.jwt_validator {
                match validator.validate(token).await {
                    Ok(claims) => {
                        let tenant = claims
                            .tenant_id()
                            .map(|t| t.to_string())
                            .or_else(|| extract_tenant(&headers))
                            .unwrap_or_else(|| "default".to_string());
                        let uid = Some(claims.user_id().to_string());
                        let email = claims.email.clone();
                        let r: Vec<String> =
                            claims.realm_roles().iter().map(|s| s.to_string()).collect();
                        debug!(
                            user_id = ?uid,
                            tenant_id = %tenant,
                            "JWT validated — user authenticated"
                        );
                        (tenant, uid, email, r, Some(token.clone()))
                    }
                    Err(e) => {
                        warn!(error = %e, "JWT validation failed");
                        return (
                            StatusCode::UNAUTHORIZED,
                            [(
                                "WWW-Authenticate",
                                r#"Bearer error="invalid_token", resource_metadata="/.well-known/oauth-protected-resource""#,
                            )],
                            Json(JsonRpcResponse::error(
                                request.id,
                                -32001,
                                format!("Invalid token: {}", e),
                            )),
                        )
                            .into_response();
                    }
                }
            } else {
                // No JWT validator configured — accept token but don't validate
                debug!("JWT validator not configured — skipping token validation");
                let tenant =
                    extract_tenant(&headers).unwrap_or_else(|| "default".to_string());
                (tenant, None, None, vec![], Some(token.clone()))
            }
        } else {
            // No token present (public methods only reach here)
            let tenant = extract_tenant(&headers).unwrap_or_else(|| "default".to_string());
            (tenant, None, None, vec![], None)
        };

    // Resolve or create session
    let session_id = match params.session_id {
        Some(ref id) => {
            // Touch existing session
            let _ = state.session_manager.get(id).await;
            id.clone()
        }
        None => {
            // First request (initialize) — create a session
            let id = Uuid::new_v4().to_string();
            let session = Session::new(id.clone(), tenant_id.clone());
            state.session_manager.create(session).await;
            metrics::update_session_count(state.session_manager.count());
            id
        }
    };

    let ctx = ToolContext {
        tenant_id,
        user_id,
        user_email,
        request_id: request_id.clone(),
        roles,
        raw_token: validated_token,
    };

    // Route to handler
    let response = match request.method.as_str() {
        "initialize" => handle_initialize(&state, &request, &ctx).await,
        "ping" => handle_ping(&request),
        "tools/list" => handle_tools_list(&state, &request, &ctx).await,
        "tools/call" => handle_tools_call(&state, &request, &ctx).await,
        "resources/list" => handle_resources_list(&state, &request).await,
        "notifications/initialized" => {
            // Client notification, no response needed
            debug!("Client initialized notification received");
            return StatusCode::NO_CONTENT.into_response();
        }
        _ => JsonRpcResponse::error(
            request.id,
            METHOD_NOT_FOUND,
            format!("Method '{}' not found", request.method),
        ),
    };

    // Always return Mcp-Session-Id header (required by Streamable HTTP transport)
    let mut resp = Json(response).into_response();
    resp.headers_mut().insert(
        "Mcp-Session-Id",
        session_id.parse().unwrap(),
    );
    resp
}

/// GET /mcp/sse - Establish SSE connection (legacy/streaming)
///
/// Opens a persistent SSE connection for real-time updates.
pub async fn handle_sse_get(
    State(state): State<AppState>,
    headers: HeaderMap,
    Query(params): Query<SseQueryParams>,
) -> Sse<impl Stream<Item = Result<Event, Infallible>>> {
    let session_id = params.session_id.unwrap_or_else(|| Uuid::new_v4().to_string());
    let tenant_id = extract_tenant(&headers).unwrap_or_else(|| "default".to_string());

    info!(
        session_id = %session_id,
        tenant_id = %tenant_id,
        "SSE connection established"
    );

    // Create session
    let session = Session::new(session_id.clone(), tenant_id.clone());
    state.session_manager.create(session).await;
    metrics::track_sse_connect();
    metrics::update_session_count(state.session_manager.count());

    // Create event stream
    let (tx, rx) = mpsc::channel::<Event>(32);
    
    // Send initial endpoint event
    let endpoint_event = Event::default()
        .event("endpoint")
        .data(format!("/mcp/sse?sessionId={}", session_id));
    
    let _ = tx.send(endpoint_event).await;

    // Spawn keepalive task
    let tx_keepalive = tx.clone();
    let session_id_clone = session_id.clone();
    let tenant_id_clone = tenant_id.clone();
    let session_manager = state.session_manager.clone();
    let connect_time = std::time::Instant::now();

    tokio::spawn(async move {
        let mut interval = tokio::time::interval(Duration::from_secs(30));
        loop {
            interval.tick().await;

            // Check if session still exists
            if session_manager.get(&session_id_clone).await.is_none() {
                debug!(session_id = %session_id_clone, "Session expired, closing SSE");
                break;
            }

            // Send keepalive
            let event = Event::default().comment("keepalive");
            if tx_keepalive.send(event).await.is_err() {
                debug!(session_id = %session_id_clone, "SSE client disconnected");
                break;
            }
        }
        // Track disconnect with duration
        let duration = connect_time.elapsed().as_secs_f64();
        metrics::track_sse_disconnect(&tenant_id_clone, duration);
        metrics::update_session_count(session_manager.count());
    });

    // Convert to stream
    let stream = ReceiverStream::new(rx).map(Ok);

    Sse::new(stream).keep_alive(
        axum::response::sse::KeepAlive::new()
            .interval(Duration::from_secs(15))
            .text("ping"),
    )
}

/// DELETE /mcp/sse - Close session
pub async fn handle_sse_delete(
    State(state): State<AppState>,
    Query(params): Query<SseQueryParams>,
) -> impl IntoResponse {
    if let Some(session_id) = params.session_id {
        if state.session_manager.remove(&session_id).await {
            info!(session_id = %session_id, "Session closed");
            metrics::update_session_count(state.session_manager.count());
            StatusCode::NO_CONTENT
        } else {
            StatusCode::NOT_FOUND
        }
    } else {
        StatusCode::BAD_REQUEST
    }
}

// ============================================
// JSON-RPC Method Handlers
// ============================================

async fn handle_initialize(
    state: &AppState,
    request: &JsonRpcRequest,
    ctx: &ToolContext,
) -> JsonRpcResponse {
    debug!("Handling initialize request");

    // Parse client info from params
    let client_info = request.params.as_ref().and_then(|p| p.get("clientInfo"));
    
    if let Some(info) = client_info {
        debug!(client_info = ?info, "Client connected");
    }

    let result = json!({
        "protocolVersion": "2024-11-05",
        "capabilities": {
            "tools": {
                "listChanged": false
            },
            "resources": {
                "subscribe": false,
                "listChanged": false
            },
            "prompts": {
                "listChanged": false
            },
            "logging": {}
        },
        "serverInfo": {
            "name": "STOA Gateway",
            "version": env!("CARGO_PKG_VERSION")
        }
    });

    JsonRpcResponse::success(request.id.clone(), result)
}

fn handle_ping(request: &JsonRpcRequest) -> JsonRpcResponse {
    JsonRpcResponse::success(request.id.clone(), json!({}))
}

async fn handle_tools_list(
    state: &AppState,
    request: &JsonRpcRequest,
    ctx: &ToolContext,
) -> JsonRpcResponse {
    let tools = state.tool_registry.list(Some(&ctx.tenant_id));
    
    let result = json!({
        "tools": tools
    });

    JsonRpcResponse::success(request.id.clone(), result)
}

async fn handle_tools_call(
    state: &AppState,
    request: &JsonRpcRequest,
    ctx: &ToolContext,
) -> JsonRpcResponse {
    let params = match &request.params {
        Some(p) => p,
        None => {
            return JsonRpcResponse::error(
                request.id.clone(),
                INVALID_PARAMS,
                "Missing params",
            );
        }
    };

    let tool_name = match params.get("name").and_then(|v| v.as_str()) {
        Some(n) => n,
        None => {
            return JsonRpcResponse::error(
                request.id.clone(),
                INVALID_PARAMS,
                "Missing tool name",
            );
        }
    };

    let arguments = params.get("arguments").cloned().unwrap_or(json!({}));

    // Get tool from registry
    let tool = match state.tool_registry.get(tool_name) {
        Some(t) => t,
        None => {
            return JsonRpcResponse::error(
                request.id.clone(),
                METHOD_NOT_FOUND,
                format!("Tool '{}' not found", tool_name),
            );
        }
    };

    // Check UAC permission using tool's required_action (FIX for hardcoded action)
    let required_action = tool.required_action();
    if let Err(e) = state.uac_enforcer.check(&ctx.tenant_id, required_action).await {
        warn!(
            tool = %tool_name,
            action = ?required_action,
            tenant = %ctx.tenant_id,
            "UAC check failed: {}",
            e
        );
        return JsonRpcResponse::error(
            request.id.clone(),
            -32001, // Permission denied
            format!("Permission denied: {}", e),
        );
    }

    // Execute tool
    match tool.execute(arguments, ctx).await {
        Ok(result) => {
            let mut result_json = json!({
                "content": result.content
            });
            if let Some(true) = result.is_error {
                result_json["isError"] = json!(true);
            }
            JsonRpcResponse::success(request.id.clone(), result_json)
        }
        Err(e) => {
            error!(tool = %tool_name, error = %e, "Tool execution failed");
            JsonRpcResponse::error(
                request.id.clone(),
                INTERNAL_ERROR,
                e.to_string(),
            )
        }
    }
}

async fn handle_resources_list(
    state: &AppState,
    request: &JsonRpcRequest,
) -> JsonRpcResponse {
    // TODO: Implement resource listing
    let result = json!({
        "resources": []
    });
    JsonRpcResponse::success(request.id.clone(), result)
}

// ============================================
// Helpers
// ============================================

fn extract_tenant(headers: &HeaderMap) -> Option<String> {
    // Try X-Tenant-ID header first
    if let Some(tenant) = headers.get("X-Tenant-ID") {
        return tenant.to_str().ok().map(|s| s.to_string());
    }
    
    // TODO: Extract from JWT token
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_json_rpc_response_success() {
        let resp = JsonRpcResponse::success(Some(json!(1)), json!({"status": "ok"}));
        assert!(resp.error.is_none());
        assert!(resp.result.is_some());
    }

    #[test]
    fn test_json_rpc_response_error() {
        let resp = JsonRpcResponse::error(Some(json!(1)), -32600, "Invalid request");
        assert!(resp.error.is_some());
        assert!(resp.result.is_none());
        assert_eq!(resp.error.as_ref().unwrap().code, -32600);
    }
}
