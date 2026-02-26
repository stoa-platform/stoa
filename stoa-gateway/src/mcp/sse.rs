//! MCP SSE Transport Implementation
//!
//! Implements the MCP Streamable HTTP Transport (spec 2025-03-26)
//! Supports both stateless JSON-RPC and stateful SSE connections.
//! Supports JSON-RPC batch requests (array of requests).

use axum::{
    body::Bytes,
    extract::{Query, State},
    http::{header, HeaderMap, StatusCode},
    response::{sse::Event, IntoResponse, Response, Sse},
    Json,
};
use futures::stream::Stream;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{convert::Infallible, time::Duration};
use tokio::sync::mpsc;
use tokio_stream::{wrappers::ReceiverStream, StreamExt};
use tracing::{debug, error, info, warn};
use uuid::Uuid;

use crate::mcp::session::Session;
use crate::mcp::tools::ToolContext;
use crate::metrics;
use crate::optimization::{OptimizationSettings, TokenOptimizer};
use crate::state::{AppState, PolicyCallerCtx};

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
pub const PARSE_ERROR: i32 = -32700;
pub const INVALID_REQUEST: i32 = -32600;
pub const METHOD_NOT_FOUND: i32 = -32601;
pub const INVALID_PARAMS: i32 = -32602;
pub const INTERNAL_ERROR: i32 = -32603;

// ============================================
// MCP Protocol Version Negotiation (2025-11-25)
// ============================================

/// Supported MCP protocol versions (newest first)
const SUPPORTED_VERSIONS: &[&str] = &[
    "2025-11-25", // Latest draft - Claude.ai sends this version
    "2025-03-26", // Stable - full annotations, outputSchema, elicitation
    "2024-11-05", // Previous stable - backward compat
];

/// Default protocol version (returned when client doesn't specify)
const DEFAULT_PROTOCOL_VERSION: &str = "2025-11-25";

/// Negotiate the highest mutually supported protocol version
///
/// Returns the highest version that both client and server support.
/// If client requests unknown version, returns latest supported.
fn negotiate_protocol_version(client_version: Option<&str>) -> &'static str {
    match client_version {
        Some(requested) => {
            // Check if client's requested version is supported
            if SUPPORTED_VERSIONS.contains(&requested) {
                // Find the static str from our list
                SUPPORTED_VERSIONS
                    .iter()
                    .find(|&&v| v == requested)
                    .copied()
                    .unwrap_or(DEFAULT_PROTOCOL_VERSION)
            } else {
                // Unknown version - return latest
                debug!(
                    requested = %requested,
                    negotiated = %DEFAULT_PROTOCOL_VERSION,
                    "Client requested unknown version, using latest"
                );
                DEFAULT_PROTOCOL_VERSION
            }
        }
        None => {
            // No version specified - use default (latest)
            DEFAULT_PROTOCOL_VERSION
        }
    }
}

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

/// POST /mcp/sse - Handle JSON-RPC request (single or batch)
///
/// Accepts JSON-RPC requests and returns either:
/// - JSON response for simple requests
/// - JSON array of responses for batch requests (MCP 2025-03-26)
/// - SSE stream for streaming responses
pub async fn handle_sse_post(
    State(state): State<AppState>,
    headers: HeaderMap,
    Query(params): Query<SseQueryParams>,
    body: Bytes,
) -> Response {
    // === Phase 5: Batch Request Detection (MCP 2025-03-26) ===
    let parsed: Value = match serde_json::from_slice(&body) {
        Ok(v) => v,
        Err(e) => {
            return Json(JsonRpcResponse::error(
                None,
                PARSE_ERROR,
                format!("Parse error: {}", e),
            ))
            .into_response();
        }
    };

    // Detect batch vs single request
    if parsed.is_array() {
        // Batch request - process all and return array
        return handle_batch_request(state, headers, params, parsed).await;
    }

    // Single request - parse and process
    let request: JsonRpcRequest = match serde_json::from_value(parsed) {
        Ok(r) => r,
        Err(e) => {
            return Json(JsonRpcResponse::error(
                None,
                INVALID_REQUEST,
                format!("Invalid request: {}", e),
            ))
            .into_response();
        }
    };

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
    let public_methods = [
        "initialize",
        "ping",
        "notifications/initialized",
        "notifications/cancelled",
    ];
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

    // Validate JWT and extract user identity (including scopes for OPA policy evaluation)
    let (tenant_id, user_id, user_email, roles, scopes, validated_token) = if let Some(ref token) =
        raw_token
    {
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
                    // Extract OAuth scopes from JWT (ADR-012 12-Scope Model)
                    let s: Vec<String> = claims.scopes().iter().map(|s| s.to_string()).collect();
                    debug!(
                        user_id = ?uid,
                        tenant_id = %tenant,
                        scopes = ?s,
                        "JWT validated — user authenticated"
                    );
                    (tenant, uid, email, r, s, Some(token.clone()))
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
            let tenant = extract_tenant(&headers).unwrap_or_else(|| "default".to_string());
            (tenant, None, None, vec![], vec![], Some(token.clone()))
        }
    } else {
        // No token present (public methods only reach here)
        let tenant = extract_tenant(&headers).unwrap_or_else(|| "default".to_string());
        (tenant, None, None, vec![], vec![], None)
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
        scopes,
        raw_token: validated_token,
        skill_instructions: None, // SSE: skills resolved per-tool in handler
        progress_token: None,     // SSE: no progress push (half-duplex)
    };

    // Route to handler
    let response = match request.method.as_str() {
        "initialize" => handle_initialize(&state, &request, &ctx, &session_id).await,
        "ping" => handle_ping(&request),
        "tools/list" => handle_tools_list(&state, &request, &ctx).await,
        "tools/call" => handle_tools_call(&state, &request, &ctx, &session_id).await,
        "resources/list" => handle_resources_list(&state, &request).await,
        "resources/read" => handle_resources_read(&state, &request).await,
        "prompts/list" => handle_prompts_list(&request),
        "prompts/get" => handle_prompts_get(&request),
        "logging/setLevel" => handle_logging_set_level(&state, &request, &session_id).await,
        "completion/complete" => handle_completion_complete(&request),
        "roots/list" => handle_roots_list(&request),
        "notifications/initialized" => {
            // Client notification, no response needed
            debug!("Client initialized notification received");
            return StatusCode::NO_CONTENT.into_response();
        }
        "notifications/cancelled" => {
            // Client cancelled a previous request — acknowledge silently
            debug!(
                request_id = ?request.params.as_ref().and_then(|p| p.get("requestId")),
                "Client cancelled request notification received"
            );
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
    resp.headers_mut()
        .insert("Mcp-Session-Id", session_id.parse().unwrap());
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
    let session_id = params
        .session_id
        .unwrap_or_else(|| Uuid::new_v4().to_string());
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

    // Register channel for NotificationBus (CAB-1178: enables push events from Kafka consumer)
    state
        .session_manager
        .register_channel(&session_id, tx.clone());

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
        // Unregister NotificationBus channel on disconnect (CAB-1178)
        session_manager.unregister_channel(&session_id_clone);

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
        // Unregister NotificationBus channel before removing session (CAB-1178)
        state.session_manager.unregister_channel(&session_id);

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
// Batch Request Handler (MCP 2025-03-26)
// ============================================

/// Handle batch JSON-RPC requests
///
/// Processes an array of requests in parallel and returns array of responses.
/// Errors in individual requests don't affect others.
async fn handle_batch_request(
    state: AppState,
    headers: HeaderMap,
    params: SseQueryParams,
    batch: Value,
) -> Response {
    let requests: Vec<Value> = match batch.as_array() {
        Some(arr) => arr.clone(),
        None => {
            return Json(JsonRpcResponse::error(
                None,
                INVALID_REQUEST,
                "Expected array for batch request",
            ))
            .into_response();
        }
    };

    // Empty batch returns empty array
    if requests.is_empty() {
        return Json::<Vec<JsonRpcResponse>>(vec![]).into_response();
    }

    debug!(count = requests.len(), "Processing batch request");

    // Process all requests concurrently
    let futures: Vec<_> = requests
        .into_iter()
        .map(|req_value| {
            let state = state.clone();
            let headers = headers.clone();
            let params_clone = SseQueryParams {
                session_id: params.session_id.clone(),
            };

            async move {
                // Parse individual request
                let request: JsonRpcRequest = match serde_json::from_value(req_value.clone()) {
                    Ok(r) => r,
                    Err(e) => {
                        // Extract id from raw value if possible
                        let id = req_value.get("id").cloned();
                        return JsonRpcResponse::error(
                            id,
                            INVALID_REQUEST,
                            format!("Invalid request: {}", e),
                        );
                    }
                };

                // Route to appropriate handler
                process_single_request(&state, &headers, &params_clone, request).await
            }
        })
        .collect();

    let responses: Vec<JsonRpcResponse> = futures::future::join_all(futures).await;

    // Return session ID if we have one
    let mut resp = Json(responses).into_response();
    if let Some(ref session_id) = params.session_id {
        if let Ok(value) = session_id.parse() {
            resp.headers_mut().insert("Mcp-Session-Id", value);
        }
    }
    resp
}

/// Process a single JSON-RPC request (used by both single and batch handlers)
pub async fn process_single_request(
    state: &AppState,
    headers: &HeaderMap,
    params: &SseQueryParams,
    request: JsonRpcRequest,
) -> JsonRpcResponse {
    // Validate JSON-RPC version
    if request.jsonrpc != "2.0" {
        return JsonRpcResponse::error(request.id, INVALID_REQUEST, "Invalid JSON-RPC version");
    }

    // For batch processing, we need simplified auth check
    // Full auth is handled in the main handler for single requests
    let public_methods = [
        "initialize",
        "ping",
        "notifications/initialized",
        "notifications/cancelled",
    ];
    let has_auth = headers.get(header::AUTHORIZATION).is_some();

    if !public_methods.contains(&request.method.as_str()) && !has_auth {
        return JsonRpcResponse::error(request.id, -32001, "Authentication required");
    }

    // Extract tenant and create minimal context
    let tenant_id = extract_tenant(headers).unwrap_or_else(|| "default".to_string());
    let session_id = params
        .session_id
        .clone()
        .unwrap_or_else(|| Uuid::new_v4().to_string());

    let ctx = ToolContext {
        tenant_id,
        user_id: None,
        user_email: None,
        request_id: Uuid::new_v4().to_string(),
        roles: vec![],
        scopes: vec![],
        raw_token: None,
        skill_instructions: None,
        progress_token: None,
    };

    // Route to handler
    match request.method.as_str() {
        "initialize" => handle_initialize(state, &request, &ctx, &session_id).await,
        "ping" => handle_ping(&request),
        "tools/list" => handle_tools_list(state, &request, &ctx).await,
        "tools/call" => handle_tools_call(state, &request, &ctx, &session_id).await,
        "resources/list" => handle_resources_list(state, &request).await,
        "resources/read" => handle_resources_read(state, &request).await,
        "prompts/list" => handle_prompts_list(&request),
        "prompts/get" => handle_prompts_get(&request),
        "logging/setLevel" => handle_logging_set_level(state, &request, &session_id).await,
        "completion/complete" => handle_completion_complete(&request),
        "roots/list" => handle_roots_list(&request),
        "notifications/initialized" => {
            // No response for notifications
            JsonRpcResponse::success(None, json!(null))
        }
        "notifications/cancelled" => {
            // Client cancelled a previous request — no meaningful action needed
            debug!(
                request_id = ?request.params.as_ref().and_then(|p| p.get("requestId")),
                "Client cancelled request (batch)"
            );
            JsonRpcResponse::success(None, json!(null))
        }
        _ => JsonRpcResponse::error(
            request.id,
            METHOD_NOT_FOUND,
            format!("Method '{}' not found", request.method),
        ),
    }
}

// ============================================
// JSON-RPC Method Handlers
// ============================================

async fn handle_initialize(
    state: &AppState,
    request: &JsonRpcRequest,
    _ctx: &ToolContext,
    session_id: &str,
) -> JsonRpcResponse {
    debug!("Handling initialize request");

    // Parse client info from params
    let client_info = request.params.as_ref().and_then(|p| p.get("clientInfo"));

    if let Some(info) = client_info {
        debug!(client_info = ?info, "Client connected");
    }

    // === Phase 5: Protocol Version Negotiation (MCP 2025-03-26) ===
    let client_version = request
        .params
        .as_ref()
        .and_then(|p| p.get("protocolVersion"))
        .and_then(|v| v.as_str());

    let negotiated_version = negotiate_protocol_version(client_version);

    // Store negotiated protocol version in session
    state
        .session_manager
        .update_metadata(
            session_id,
            "protocol_version".to_string(),
            negotiated_version.to_string(),
        )
        .await;

    debug!(
        client_version = ?client_version,
        negotiated_version = %negotiated_version,
        "Protocol version negotiated"
    );

    // === Phase 4: Token Optimization Capability Negotiation (ADR-015) ===
    // Parse client capabilities for tokenOptimization preferences
    if let Some(capabilities) = request.params.as_ref().and_then(|p| p.get("capabilities")) {
        let opt_settings = OptimizationSettings::from_capabilities(capabilities);

        // Store optimization settings in session metadata (JSON serialized)
        if let Ok(settings_json) = opt_settings.to_metadata() {
            state
                .session_manager
                .update_metadata(
                    session_id,
                    "optimization_settings".to_string(),
                    settings_json,
                )
                .await;
            debug!(
                level = ?opt_settings.level,
                max_tokens = ?opt_settings.max_response_tokens,
                "Token optimization negotiated"
            );
        }
    }

    let result = json!({
        "protocolVersion": negotiated_version,
        "capabilities": {
            "tools": {
                "listChanged": true  // We support tool list change notifications
            },
            "resources": {
                "subscribe": false,
                "listChanged": false
            },
            "prompts": {
                "listChanged": false
            },
            "logging": {},
            // Advertise token optimization support (Phase 4)
            "tokenOptimization": {
                "supported": true,
                "levels": ["none", "moderate", "aggressive"]
            },
            // Advertise elicitation support (Phase 5)
            "elicitation": {},
            // Advertise supported transports (CAB-1345 Phase 3)
            "experimental": {
                "transports": ["sse", "websocket"]
            }
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
    session_id: &str,
) -> JsonRpcResponse {
    let params = match &request.params {
        Some(p) => p,
        None => {
            return JsonRpcResponse::error(request.id.clone(), INVALID_PARAMS, "Missing params");
        }
    };

    let tool_name = match params.get("name").and_then(|v| v.as_str()) {
        Some(n) => n,
        None => {
            return JsonRpcResponse::error(request.id.clone(), INVALID_PARAMS, "Missing tool name");
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

    // Check UAC permission using OPA policy engine (Phase 2: CAB-1094)
    // Default to stoa:read scope for authenticated users without explicit scopes
    let required_action = tool.required_action();
    let effective_scopes = if ctx.scopes.is_empty() && ctx.user_id.is_some() {
        vec!["stoa:read".to_string()]
    } else {
        ctx.scopes.clone()
    };

    if let Err(e) = state.uac_enforcer.check_with_context(
        PolicyCallerCtx {
            user_id: ctx.user_id.clone(),
            user_email: ctx.user_email.clone(),
            scopes: effective_scopes.clone(),
            roles: ctx.roles.clone(),
        },
        &ctx.tenant_id,
        tool_name,
        required_action,
    ) {
        warn!(
            tool = %tool_name,
            action = ?required_action,
            tenant = %ctx.tenant_id,
            scopes = ?effective_scopes,
            "UAC policy denied: {}",
            e
        );
        return JsonRpcResponse::error(
            request.id.clone(),
            -32001, // Permission denied
            format!("Permission denied: {}", e),
        );
    }

    // === Phase 4: Token Optimization (ADR-015) ===
    // Retrieve optimization settings from session metadata
    let opt_settings = state
        .session_manager
        .get_metadata(session_id, "optimization_settings")
        .await
        .and_then(|json| OptimizationSettings::from_metadata(&json).ok())
        .unwrap_or_default();

    // Execute tool
    match tool.execute(arguments, ctx).await {
        Ok(result) => {
            let mut result_json = json!({
                "content": result.content
            });
            if let Some(true) = result.is_error {
                result_json["isError"] = json!(true);
            }

            // Apply token optimization if enabled (Phase 4: ADR-015)
            let optimized_result = if opt_settings.is_enabled() {
                let optimizer = TokenOptimizer::new(opt_settings.clone());
                let (optimized, stats) = optimizer.optimize(&result_json);

                debug!(
                    tool = %tool_name,
                    level = ?opt_settings.level,
                    input_bytes = stats.input_bytes,
                    output_bytes = stats.output_bytes,
                    reduction_pct = stats.reduction_pct,
                    "Token optimization applied"
                );

                optimized
            } else {
                result_json
            };

            JsonRpcResponse::success(request.id.clone(), optimized_result)
        }
        Err(e) => {
            error!(tool = %tool_name, error = %e, "Tool execution failed");
            JsonRpcResponse::error(request.id.clone(), INTERNAL_ERROR, e.to_string())
        }
    }
}

async fn handle_resources_list(state: &AppState, request: &JsonRpcRequest) -> JsonRpcResponse {
    // Map registered tools to MCP resources (each tool is also a resource)
    let tools = state.tool_registry.list(None);
    let resources: Vec<serde_json::Value> = tools
        .iter()
        .map(|t| {
            json!({
                "uri": format!("stoa://tools/{}", t.name),
                "name": t.name,
                "description": t.description,
                "mimeType": "application/json"
            })
        })
        .collect();
    let result = json!({ "resources": resources });
    JsonRpcResponse::success(request.id.clone(), result)
}

/// `prompts/list` — return list of server-defined prompt templates (MCP 2025-03-26)
///
/// Currently returns an empty list — STOA has no built-in prompts.
/// Extensible: add prompts to the registry to expose them here.
fn handle_prompts_list(request: &JsonRpcRequest) -> JsonRpcResponse {
    JsonRpcResponse::success(
        request.id.clone(),
        json!({
            "prompts": []
        }),
    )
}

/// `prompts/get` — retrieve a specific prompt template by name (MCP 2025-03-26)
///
/// Returns PromptNotFound (-32002) since STOA has no built-in prompts yet.
fn handle_prompts_get(request: &JsonRpcRequest) -> JsonRpcResponse {
    let name = request
        .params
        .as_ref()
        .and_then(|p| p.get("name"))
        .and_then(|v| v.as_str())
        .unwrap_or("<unknown>");

    JsonRpcResponse::error(
        request.id.clone(),
        -32002,
        format!("Prompt '{}' not found", name),
    )
}

/// `completion/complete` — provide autocompletion suggestions (MCP 2025-03-26)
///
/// Returns an empty completion list — STOA has no completable references yet.
/// Extensible: add completable prompts/resources to provide suggestions here.
fn handle_completion_complete(request: &JsonRpcRequest) -> JsonRpcResponse {
    JsonRpcResponse::success(
        request.id.clone(),
        json!({
            "completion": {
                "values": [],
                "hasMore": false,
                "total": 0
            }
        }),
    )
}

/// `roots/list` — return the list of root URIs the server exposes (MCP 2025-03-26)
///
/// Returns an empty roots list — STOA operates as a gateway proxy
/// and does not expose filesystem-like roots.
fn handle_roots_list(request: &JsonRpcRequest) -> JsonRpcResponse {
    JsonRpcResponse::success(
        request.id.clone(),
        json!({
            "roots": []
        }),
    )
}

/// `logging/setLevel` — set the minimum log level for server→client notifications (MCP 2025-03-26)
///
/// Stores the level in session metadata. The gateway will push `notifications/message`
/// events at or above this level to the connected SSE client.
///
/// Valid levels (MCP spec): debug, info, notice, warning, error, critical, alert, emergency
async fn handle_logging_set_level(
    state: &AppState,
    request: &JsonRpcRequest,
    session_id: &str,
) -> JsonRpcResponse {
    let level = match request
        .params
        .as_ref()
        .and_then(|p| p.get("level"))
        .and_then(|v| v.as_str())
    {
        Some(l) => l,
        None => {
            return JsonRpcResponse::error(
                request.id.clone(),
                INVALID_PARAMS,
                "Missing 'level' param",
            );
        }
    };

    const VALID_LEVELS: &[&str] = &[
        "debug",
        "info",
        "notice",
        "warning",
        "error",
        "critical",
        "alert",
        "emergency",
    ];

    if !VALID_LEVELS.contains(&level) {
        return JsonRpcResponse::error(
            request.id.clone(),
            INVALID_PARAMS,
            format!(
                "Invalid log level '{}'. Valid: {}",
                level,
                VALID_LEVELS.join(", ")
            ),
        );
    }

    state
        .session_manager
        .update_metadata(session_id, "logging_level".to_string(), level.to_string())
        .await;

    debug!(session_id = %session_id, level = %level, "Client set logging level");

    JsonRpcResponse::success(request.id.clone(), json!({}))
}

/// `resources/read` — read a resource by URI (MCP 2025-03-26)
///
/// Supports `stoa://tools/{name}` URIs, returning the full tool schema as JSON.
/// Returns ResourceNotFound (-32002) for unknown tools or unsupported URI schemes.
async fn handle_resources_read(state: &AppState, request: &JsonRpcRequest) -> JsonRpcResponse {
    let uri = match request
        .params
        .as_ref()
        .and_then(|p| p.get("uri"))
        .and_then(|v| v.as_str())
    {
        Some(u) => u.to_string(),
        None => {
            return JsonRpcResponse::error(
                request.id.clone(),
                INVALID_PARAMS,
                "Missing 'uri' param",
            );
        }
    };

    // Only stoa://tools/{name} URIs are supported
    let tool_name = match uri.strip_prefix("stoa://tools/") {
        Some(n) => n.to_string(),
        None => {
            return JsonRpcResponse::error(
                request.id.clone(),
                INVALID_PARAMS,
                format!(
                    "Unsupported URI scheme: '{}'. Expected stoa://tools/{{name}}",
                    uri
                ),
            );
        }
    };

    // Look up tool in registry
    let tools = state.tool_registry.list(None);
    let found = tools.iter().find(|t| t.name == tool_name);

    match found {
        Some(tool) => {
            let tool_json = serde_json::to_string_pretty(tool).unwrap_or_default();
            let result = json!({
                "contents": [{
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": tool_json
                }]
            });
            JsonRpcResponse::success(request.id.clone(), result)
        }
        None => JsonRpcResponse::error(
            request.id.clone(),
            -32002,
            format!("Resource '{}' not found", uri),
        ),
    }
}

// ============================================
// Helpers
// ============================================

/// Extract Bearer token from Authorization header.
/// Used by both SSE and WebSocket transports.
pub fn extract_bearer_token(headers: &HeaderMap) -> Option<String> {
    headers
        .get(header::AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
        .and_then(|auth| {
            let parts: Vec<&str> = auth.splitn(2, ' ').collect();
            if parts.len() == 2 && parts[0].eq_ignore_ascii_case("bearer") {
                Some(parts[1].trim().to_string())
            } else {
                None
            }
        })
}

fn extract_tenant(headers: &HeaderMap) -> Option<String> {
    // Try X-Tenant-ID header first
    if let Some(tenant) = headers.get("X-Tenant-ID") {
        return tenant.to_str().ok().map(|s| s.to_string());
    }

    // JWT-based tenant extraction happens at the SSE POST handler layer
    // (lines 254-306) where the full auth context is available.
    // This fallback returns None when no X-Tenant-ID header is present.
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

    // === Phase 5: Protocol Version Negotiation Tests ===

    #[test]
    fn test_negotiate_version_2025() {
        let result = negotiate_protocol_version(Some("2025-03-26"));
        assert_eq!(result, "2025-03-26");
    }

    #[test]
    fn test_negotiate_version_2024() {
        let result = negotiate_protocol_version(Some("2024-11-05"));
        assert_eq!(result, "2024-11-05");
    }

    #[test]
    fn test_negotiate_version_unknown() {
        // Unknown version → returns latest
        let result = negotiate_protocol_version(Some("2099-01-01"));
        assert_eq!(result, "2025-11-25");
    }

    #[test]
    fn test_negotiate_version_none() {
        // No version → returns default (latest)
        let result = negotiate_protocol_version(None);
        assert_eq!(result, "2025-11-25");
    }

    #[test]
    fn test_supported_versions_order() {
        // Latest version should be first
        assert_eq!(SUPPORTED_VERSIONS[0], "2025-11-25");
        assert!(SUPPORTED_VERSIONS.contains(&"2025-03-26"));
        assert!(SUPPORTED_VERSIONS.contains(&"2024-11-05"));
    }

    // === extract_tenant tests ===

    #[test]
    fn test_extract_tenant_from_header() {
        let mut headers = HeaderMap::new();
        headers.insert("X-Tenant-ID", "acme-corp".parse().unwrap());
        assert_eq!(extract_tenant(&headers), Some("acme-corp".to_string()));
    }

    #[test]
    fn test_extract_tenant_missing_header() {
        let headers = HeaderMap::new();
        assert_eq!(extract_tenant(&headers), None);
    }

    #[test]
    fn test_extract_tenant_empty_header() {
        let mut headers = HeaderMap::new();
        headers.insert("X-Tenant-ID", "".parse().unwrap());
        assert_eq!(extract_tenant(&headers), Some("".to_string()));
    }

    // === JsonRpcResponse edge cases ===

    #[test]
    fn test_json_rpc_response_null_id() {
        let resp = JsonRpcResponse::success(None, json!({"data": 42}));
        assert!(resp.id.is_none());
        assert_eq!(resp.jsonrpc, "2.0");
    }

    #[test]
    fn test_json_rpc_response_string_id() {
        let resp = JsonRpcResponse::success(Some(json!("req-abc")), json!({}));
        assert_eq!(resp.id.unwrap(), "req-abc");
    }

    #[test]
    fn test_json_rpc_error_data_field_is_none() {
        let resp = JsonRpcResponse::error(Some(json!(1)), INTERNAL_ERROR, "boom");
        let err = resp.error.unwrap();
        assert_eq!(err.code, INTERNAL_ERROR);
        assert_eq!(err.message, "boom");
        assert!(err.data.is_none());
    }

    #[test]
    fn test_json_rpc_response_serialization_skips_none_fields() {
        let success = JsonRpcResponse::success(Some(json!(1)), json!("ok"));
        let json = serde_json::to_value(&success).unwrap();
        assert!(json.get("result").is_some());
        assert!(json.get("error").is_none()); // skip_serializing_if = None

        let error = JsonRpcResponse::error(Some(json!(1)), -1, "err");
        let json = serde_json::to_value(&error).unwrap();
        assert!(json.get("error").is_some());
        assert!(json.get("result").is_none()); // skip_serializing_if = None
    }

    // === Protocol negotiation edge cases ===

    #[test]
    fn test_negotiate_version_empty_string() {
        let result = negotiate_protocol_version(Some(""));
        assert_eq!(result, DEFAULT_PROTOCOL_VERSION);
    }

    // === SseQueryParams deserialization ===

    #[test]
    fn test_sse_query_params_deserialize_with_session() {
        let params: SseQueryParams = serde_json::from_str(r#"{"sessionId": "abc-123"}"#).unwrap();
        assert_eq!(params.session_id, Some("abc-123".to_string()));
    }

    #[test]
    fn test_sse_query_params_deserialize_without_session() {
        let params: SseQueryParams = serde_json::from_str(r#"{}"#).unwrap();
        assert!(params.session_id.is_none());
    }

    // === MCP Spec Compliance: completion/complete ===

    #[test]
    fn test_completion_complete_returns_empty_values() {
        let request = JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            id: Some(json!(42)),
            method: "completion/complete".to_string(),
            params: Some(json!({
                "ref": { "type": "ref/prompt", "name": "test" },
                "argument": { "name": "arg1", "value": "he" }
            })),
        };
        let resp = handle_completion_complete(&request);
        assert!(resp.error.is_none());
        let result = resp.result.unwrap();
        let completion = result.get("completion").unwrap();
        assert_eq!(completion["values"], json!([]));
        assert_eq!(completion["hasMore"], json!(false));
        assert_eq!(completion["total"], json!(0));
    }

    #[test]
    fn test_completion_complete_preserves_request_id() {
        let request = JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            id: Some(json!("req-99")),
            method: "completion/complete".to_string(),
            params: None,
        };
        let resp = handle_completion_complete(&request);
        assert_eq!(resp.id, Some(json!("req-99")));
    }

    // === MCP Spec Compliance: roots/list ===

    #[test]
    fn test_roots_list_returns_empty_array() {
        let request = JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            id: Some(json!(7)),
            method: "roots/list".to_string(),
            params: None,
        };
        let resp = handle_roots_list(&request);
        assert!(resp.error.is_none());
        let result = resp.result.unwrap();
        assert_eq!(result["roots"], json!([]));
    }

    #[test]
    fn test_roots_list_preserves_request_id() {
        let request = JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            id: Some(json!("roots-1")),
            method: "roots/list".to_string(),
            params: None,
        };
        let resp = handle_roots_list(&request);
        assert_eq!(resp.id, Some(json!("roots-1")));
    }

    // === MCP Spec Compliance: ping ===

    #[test]
    fn test_ping_returns_empty_object() {
        let request = JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            id: Some(json!(1)),
            method: "ping".to_string(),
            params: None,
        };
        let resp = handle_ping(&request);
        assert!(resp.error.is_none());
        assert_eq!(resp.result.unwrap(), json!({}));
    }

    #[test]
    fn test_ping_preserves_request_id() {
        let request = JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            id: Some(json!("ping-42")),
            method: "ping".to_string(),
            params: None,
        };
        let resp = handle_ping(&request);
        assert_eq!(resp.id, Some(json!("ping-42")));
    }

    // === MCP Spec Compliance: prompts/list ===

    #[test]
    fn test_prompts_list_returns_empty_array() {
        let request = JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            id: Some(json!(10)),
            method: "prompts/list".to_string(),
            params: None,
        };
        let resp = handle_prompts_list(&request);
        assert!(resp.error.is_none());
        let result = resp.result.unwrap();
        assert_eq!(result["prompts"], json!([]));
    }

    #[test]
    fn test_prompts_list_preserves_request_id() {
        let request = JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            id: Some(json!("prompts-1")),
            method: "prompts/list".to_string(),
            params: None,
        };
        let resp = handle_prompts_list(&request);
        assert_eq!(resp.id, Some(json!("prompts-1")));
    }

    // === MCP Spec Compliance: prompts/get ===

    #[test]
    fn test_prompts_get_returns_not_found() {
        let request = JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            id: Some(json!(11)),
            method: "prompts/get".to_string(),
            params: Some(json!({"name": "my-prompt"})),
        };
        let resp = handle_prompts_get(&request);
        assert!(resp.error.is_some());
        let err = resp.error.unwrap();
        assert_eq!(err.code, -32002);
        assert!(err.message.contains("my-prompt"));
    }

    #[test]
    fn test_prompts_get_missing_name_uses_unknown() {
        let request = JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            id: Some(json!(12)),
            method: "prompts/get".to_string(),
            params: None,
        };
        let resp = handle_prompts_get(&request);
        assert!(resp.error.is_some());
        let err = resp.error.unwrap();
        assert_eq!(err.code, -32002);
        assert!(err.message.contains("<unknown>"));
    }

    #[test]
    fn test_prompts_get_preserves_request_id() {
        let request = JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            id: Some(json!("prompt-req-1")),
            method: "prompts/get".to_string(),
            params: Some(json!({"name": "test"})),
        };
        let resp = handle_prompts_get(&request);
        assert_eq!(resp.id, Some(json!("prompt-req-1")));
    }

    // === MCP Spec Compliance: 2025-11-25 version ===

    #[test]
    fn test_negotiate_version_2025_11_25() {
        let result = negotiate_protocol_version(Some("2025-11-25"));
        assert_eq!(result, "2025-11-25");
    }

    #[test]
    fn test_negotiate_empty_string_returns_default() {
        // Empty string is not a valid version, treated as unknown
        let result = negotiate_protocol_version(Some(""));
        assert_eq!(result, DEFAULT_PROTOCOL_VERSION);
    }
}
