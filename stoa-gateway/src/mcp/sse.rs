//! MCP SSE Transport Implementation
//!
//! Implements the MCP Streamable HTTP Transport (spec 2025-03-26)
//! Supports both stateless JSON-RPC and stateful SSE connections.
//! Supports JSON-RPC batch requests (array of requests).

use axum::{
    body::{to_bytes, Bytes},
    extract::{Query, State},
    http::{header, HeaderMap, StatusCode},
    response::{sse::Event, IntoResponse, Response, Sse},
    Json,
};
use futures::stream::{self, Stream};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{convert::Infallible, time::Duration};
use tokio::sync::mpsc;
use tokio_stream::{wrappers::ReceiverStream, StreamExt};
use tracing::{debug, error, info};
use uuid::Uuid;

use crate::mcp::handlers::{extract_auth_context, AuthContext, AuthError, ToolsCallRequest};
use crate::mcp::session::Session;
use crate::mcp::tools::ToolContext;
use crate::metrics;
use crate::optimization::{OptimizationSettings, TokenOptimizer};
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
pub const PARSE_ERROR: i32 = -32700;
pub const INVALID_REQUEST: i32 = -32600;
pub const METHOD_NOT_FOUND: i32 = -32601;
pub const INVALID_PARAMS: i32 = -32602;
pub const INTERNAL_ERROR: i32 = -32603;

// Anonymous handshake is stateless; tenant sessions require verified identity.

fn rpc_auth_failure(error: AuthError, id: Option<Value>) -> Response {
    let (status, message) = error;
    let mut response = (status, Json(JsonRpcResponse::error(id, -32001, message))).into_response();
    if status == StatusCode::UNAUTHORIZED {
        response.headers_mut().insert(
            "WWW-Authenticate",
            axum::http::HeaderValue::from_static(
                r#"Bearer resource_metadata="/.well-known/oauth-protected-resource""#,
            ),
        );
    }
    response
}

fn identity_context(auth: AuthContext) -> ToolContext {
    ToolContext {
        tenant_id: auth.tenant_id,
        user_id: auth.user_id,
        user_email: auth.user_email,
        request_id: Uuid::new_v4().to_string(),
        roles: auth.roles,
        scopes: auth.scopes,
        raw_token: auth.raw_token,
        skill_instructions: None,
        progress_token: None,
        consumer_id: auth.consumer_id,
        from_control_plane: false,
    }
}

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
    mut headers: HeaderMap,
    Query(params): Query<SseQueryParams>,
    body: Bytes,
) -> Response {
    let request_id = crate::mcp::handlers::request_id(&headers);
    if let Ok(value) = request_id.parse() {
        headers.insert("x-request-id", value);
    }
    let mut response = handle_sse_post_inner(state, headers, params, body).await;
    if let Ok(value) = request_id.parse() {
        response.headers_mut().insert("x-request-id", value);
    }
    response
}

async fn handle_sse_post_inner(
    state: AppState,
    headers: HeaderMap,
    params: SseQueryParams,
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

    let request_id = crate::mcp::handlers::request_id(&headers);
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

    if !headers.contains_key(header::AUTHORIZATION) {
        if let Some(response) = anonymous_handshake(&state, &request).await {
            if request.id.is_none() && request.method.starts_with("notifications/") {
                return StatusCode::NO_CONTENT.into_response();
            }
            return Json(response).into_response();
        }
    }
    let auth = match extract_auth_context(&state, &headers).await {
        Ok(auth) => auth,
        Err(error) => return rpc_auth_failure(error, request.id),
    };
    let tenant_id = auth.tenant_id.clone();

    // Resolve or create session
    let session_id = match params.session_id {
        Some(ref id) => {
            match state.session_manager.get(id).await {
                Some(session) if session.tenant_id == tenant_id => {}
                _ => return StatusCode::FORBIDDEN.into_response(),
            }
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

    let ctx = identity_context(auth.clone());

    // Route to handler
    let response = match request.method.as_str() {
        "initialize" => handle_initialize(&state, &request, &session_id).await,
        "ping" => handle_ping(&request),
        "tools/list" => handle_tools_list(&state, &request, &ctx).await,
        "tools/call" => handle_tools_call(&state, &request, &headers, &session_id, auth).await,
        "resources/list" => handle_resources_list(&state, &request, &ctx).await,
        "resources/read" => handle_resources_read(&state, &request, &ctx).await,
        "resources/templates/list" => handle_resources_templates_list(&request),
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

    // Content negotiation (MCP Streamable HTTP spec 2025-03-26): if the
    // client accepts `text/event-stream`, wrap the JSON-RPC response in an
    // SSE frame; otherwise keep the legacy `application/json` body for
    // back-compat with curl / claude-code CLI callers that omit Accept.
    if accepts_event_stream(&headers) {
        return build_sse_single_response(&session_id, &response);
    }

    // Always return Mcp-Session-Id header (required by Streamable HTTP transport)
    let mut resp = Json(response).into_response();
    if let Ok(header_value) = session_id.parse() {
        resp.headers_mut().insert("Mcp-Session-Id", header_value);
    }
    resp
}

/// Does the client accept `text/event-stream` for this request?
///
/// Parses the `Accept` header as a comma-separated media-range list and
/// checks for an explicit `text/event-stream` token (case-insensitive,
/// tolerant of quality values like `;q=0.9`). Wildcards (`*/*`) do NOT
/// count as acceptance — legacy HTTP clients like curl that send no
/// Accept (or only `*/*`) keep the pre-existing JSON response so this fix
/// stays strictly additive.
pub fn accepts_event_stream(headers: &HeaderMap) -> bool {
    headers
        .get(header::ACCEPT)
        .and_then(|v| v.to_str().ok())
        .map(|accept| {
            accept.split(',').any(|media_range| {
                let mime = media_range.split(';').next().unwrap_or("").trim();
                mime.eq_ignore_ascii_case("text/event-stream")
            })
        })
        .unwrap_or(false)
}

/// Build the SSE response that carries a single JSON-RPC reply.
///
/// Emits one `event: message` frame with the serialized response and then
/// closes the stream. The spec allows — and in fact recommends — closing
/// after all correlated responses have been sent; clients that need
/// server-initiated notifications open a long-lived `GET /mcp/sse`.
fn build_sse_single_response(session_id: &str, response: &JsonRpcResponse) -> Response {
    let data = serde_json::to_string(response).unwrap_or_else(|e| {
        error!(error = %e, "SSE: failed to serialize JSON-RPC response");
        json!({
            "jsonrpc": "2.0",
            "error": {"code": INTERNAL_ERROR, "message": "serialization failure"},
            "id": Value::Null
        })
        .to_string()
    });

    let event = Event::default().event("message").data(data);
    let one_event: Box<dyn Stream<Item = Result<Event, Infallible>> + Send + Unpin> =
        Box::new(stream::iter(std::iter::once(Ok(event))));

    let mut resp = Sse::new(one_event)
        .keep_alive(
            axum::response::sse::KeepAlive::new()
                .interval(Duration::from_secs(15))
                .text("ping"),
        )
        .into_response();

    if let Ok(header_value) = session_id.parse() {
        resp.headers_mut().insert("Mcp-Session-Id", header_value);
    }
    resp
}

/// POST /mcp — MCP Streamable HTTP Transport (spec 2025-11-25)
///
/// Single endpoint for all JSON-RPC communication. Session ID is passed
/// via the `Mcp-Session-Id` header (not query params like SSE legacy).
/// Delegates to the same JSON-RPC routing as `/mcp/sse` POST.
pub async fn handle_streamable_http_post(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    // Extract session ID from Mcp-Session-Id header (Streamable HTTP spec)
    let session_id = headers
        .get("Mcp-Session-Id")
        .and_then(|v| v.to_str().ok())
        .map(|s| s.to_string());

    let params = SseQueryParams { session_id };

    handle_sse_post(State(state), headers, Query(params), body).await
}

/// GET /mcp/sse - Establish SSE connection (legacy/streaming)
///
/// Opens a persistent SSE connection for real-time updates.
pub async fn handle_sse_get(
    State(state): State<AppState>,
    headers: HeaderMap,
    Query(params): Query<SseQueryParams>,
) -> Response {
    let create_session = params.session_id.is_none();
    let session_id = params
        .session_id
        .unwrap_or_else(|| Uuid::new_v4().to_string());
    let (claims, _) = match crate::auth::tenant::request_identity(&state, &headers).await {
        Ok(identity) => identity,
        Err(error) => return error.into_response(),
    };
    let tenant_id = match crate::auth::tenant::require_tenant(&claims) {
        Ok(tenant) => tenant.to_string(),
        Err(error) => return error.into_response(),
    };
    let (tx, rx) = mpsc::channel::<Event>(32);
    if !state.session_manager.register_tenant_channel(
        &session_id,
        &tenant_id,
        tx.clone(),
        create_session,
    ) {
        return StatusCode::FORBIDDEN.into_response();
    }
    info!(session_id = %session_id, tenant_id = %tenant_id, "SSE connection established");
    metrics::track_sse_connect();
    metrics::update_session_count(state.session_manager.count());

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
    let authorization_deadline = crate::auth::tenant::authorization_deadline(claims.exp);

    tokio::spawn(async move {
        let mut interval = tokio::time::interval(Duration::from_secs(30));
        loop {
            tokio::select! {
                _ = tokio::time::sleep_until(authorization_deadline) => break,
                _ = interval.tick() => {},
            }

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
        session_manager.unregister_channel_if_same(&session_id_clone, &tx_keepalive);

        // Track disconnect with duration
        let duration = connect_time.elapsed().as_secs_f64();
        metrics::track_sse_disconnect(&tenant_id_clone, duration);
        metrics::update_session_count(session_manager.count());
    });

    // Convert to stream
    let stream = ReceiverStream::new(rx).map(Ok::<_, Infallible>);

    Sse::new(stream)
        .keep_alive(
            axum::response::sse::KeepAlive::new()
                .interval(Duration::from_secs(15))
                .text("ping"),
        )
        .into_response()
}

/// DELETE /mcp/sse - Close session
pub async fn handle_sse_delete(
    State(state): State<AppState>,
    Query(params): Query<SseQueryParams>,
    headers: HeaderMap,
) -> Response {
    let (claims, _) = match crate::auth::tenant::request_identity(&state, &headers).await {
        Ok(identity) => identity,
        Err(error) => return error.into_response(),
    };
    if let Some(session_id) = params.session_id {
        let tenant = claims
            .tenant_id()
            .expect("request_identity requires tenant");
        if state.session_manager.remove_for_tenant(&session_id, tenant) {
            info!(session_id = %session_id, "Session closed");
            metrics::update_session_count(state.session_manager.count());
            StatusCode::NO_CONTENT.into_response()
        } else {
            StatusCode::FORBIDDEN.into_response()
        }
    } else {
        StatusCode::BAD_REQUEST.into_response()
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
    let auth = match extract_auth_context(&state, &headers).await {
        Ok(auth) => auth,
        Err(error) => return rpc_auth_failure(error, None),
    };
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
            let auth = auth.clone();
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
                process_authenticated_request(&state, &headers, &params_clone, request, auth).await
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

    // The same validator is used by single HTTP, batch HTTP and WebSocket messages.
    // Revalidation here also rejects tokens that expire after a WebSocket upgrade.
    if !headers.contains_key(header::AUTHORIZATION) {
        if let Some(response) = anonymous_handshake(state, &request).await {
            return response;
        }
    }
    let auth = match extract_auth_context(state, headers).await {
        Ok(auth) => auth,
        Err((_, message)) => return JsonRpcResponse::error(request.id, -32001, message),
    };
    process_authenticated_request(state, headers, params, request, auth).await
}

async fn process_authenticated_request(
    state: &AppState,
    headers: &HeaderMap,
    params: &SseQueryParams,
    request: JsonRpcRequest,
    auth: AuthContext,
) -> JsonRpcResponse {
    if request.jsonrpc != "2.0" {
        return JsonRpcResponse::error(request.id, INVALID_REQUEST, "Invalid JSON-RPC version");
    }
    let session_id = params
        .session_id
        .clone()
        .unwrap_or_else(|| Uuid::new_v4().to_string());
    if let Some(id) = &params.session_id {
        match state.session_manager.get(id).await {
            Some(session) if session.tenant_id == auth.tenant_id => {}
            _ => return JsonRpcResponse::error(request.id, -32003, "Session tenant mismatch"),
        }
    }
    let ctx = identity_context(auth.clone());

    // Route to handler
    match request.method.as_str() {
        "initialize" => handle_initialize(state, &request, &session_id).await,
        "ping" => handle_ping(&request),
        "tools/list" => handle_tools_list(state, &request, &ctx).await,
        "tools/call" => handle_tools_call(state, &request, headers, &session_id, auth).await,
        "resources/list" => handle_resources_list(state, &request, &ctx).await,
        "resources/read" => handle_resources_read(state, &request, &ctx).await,
        "resources/templates/list" => handle_resources_templates_list(&request),
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

/// Capability negotiation never reads tools or creates a tenant-scoped session.
async fn anonymous_handshake(
    state: &AppState,
    request: &JsonRpcRequest,
) -> Option<JsonRpcResponse> {
    match request.method.as_str() {
        "initialize" => Some(handle_initialize(state, request, "").await),
        "ping" => Some(handle_ping(request)),
        "notifications/initialized" | "notifications/cancelled" => {
            Some(JsonRpcResponse::success(request.id.clone(), json!({})))
        }
        _ => None,
    }
}

async fn handle_initialize(
    state: &AppState,
    request: &JsonRpcRequest,
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
                opt_level = ?opt_settings.level,
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
            "elicitation": {}
            // CAB-2110: `experimental.transports` used to be advertised as
            // `{"transports": ["sse", "websocket"]}` but MCP 2025-11-25 / the
            // Anthropic Toolbox validator expect every value under
            // `capabilities.experimental` to be a dict (per-feature config
            // object), not an array. Claude.ai failed initialize with:
            //   ValidationError: capabilities.experimental.transports
            //   Input should be a valid dictionary
            // HTTP-level transport is negotiated via URL + Accept anyway;
            // advertising it in the JSON-RPC capabilities block was purely
            // informational and outside the spec. Drop it entirely rather
            // than reshape it into a dummy dict.
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
    if ctx.tenant_id.is_empty() {
        return JsonRpcResponse::error(request.id.clone(), -32003, "Missing tenant context");
    }

    let tools = state.tool_registry.list(Some(&ctx.tenant_id));

    let result = json!({
        "tools": tools
    });

    JsonRpcResponse::success(request.id.clone(), result)
}

/// Adapt JSON-RPC to the existing execution pipeline, including tenant permissions,
/// guardrails, rate limits, budgets, policy, metrics and metering.
async fn handle_tools_call(
    state: &AppState,
    request: &JsonRpcRequest,
    headers: &HeaderMap,
    session_id: &str,
    auth: AuthContext,
) -> JsonRpcResponse {
    let params = match &request.params {
        Some(params) => params,
        None => {
            return JsonRpcResponse::error(request.id.clone(), INVALID_PARAMS, "Missing params")
        }
    };
    let name = match params.get("name").and_then(Value::as_str) {
        Some(name) => name.to_string(),
        None => {
            return JsonRpcResponse::error(request.id.clone(), INVALID_PARAMS, "Missing tool name")
        }
    };
    let arguments = params
        .get("arguments")
        .cloned()
        .unwrap_or_else(|| json!({}));
    let response = crate::mcp::handlers::mcp_tools_call_with_auth(
        state.clone(),
        headers.clone(),
        ToolsCallRequest { name, arguments },
        Some(auth),
    )
    .await;
    let status = response.status();
    let request_id = response
        .headers()
        .get("x-request-id")
        .and_then(|value| value.to_str().ok())
        .map(str::to_string);
    let body = match to_bytes(response.into_body(), 16 * 1024 * 1024).await {
        Ok(body) => body,
        Err(_) => {
            return JsonRpcResponse::error(
                request.id.clone(),
                INTERNAL_ERROR,
                "Tool response too large",
            )
        }
    };
    let result: Value = match serde_json::from_slice(&body) {
        Ok(result) => result,
        Err(_) => {
            return JsonRpcResponse::error(
                request.id.clone(),
                INTERNAL_ERROR,
                "Invalid tool response",
            )
        }
    };
    if !status.is_success() {
        let code = match status {
            StatusCode::UNAUTHORIZED
            | StatusCode::FORBIDDEN
            | StatusCode::BAD_REQUEST
            | StatusCode::SERVICE_UNAVAILABLE => -32001,
            StatusCode::TOO_MANY_REQUESTS => -32029,
            StatusCode::NOT_FOUND => METHOD_NOT_FOUND,
            _ => INTERNAL_ERROR,
        };
        let mut response = JsonRpcResponse::error(request.id.clone(), code, "Tool call rejected");
        if let Some(error) = &mut response.error {
            error.data = Some(
                if matches!(
                    status,
                    StatusCode::BAD_REQUEST | StatusCode::SERVICE_UNAVAILABLE
                ) {
                    json!({"requestId": request_id})
                } else {
                    json!({"httpStatus": status.as_u16(), "result": result})
                },
            );
        }
        return response;
    }
    // Preserve the session's negotiated response optimization after execution controls.
    let settings = state
        .session_manager
        .get_metadata(session_id, "optimization_settings")
        .await
        .and_then(|json| OptimizationSettings::from_metadata(&json).ok())
        .unwrap_or_default();
    let result = if settings.is_enabled() {
        TokenOptimizer::new(settings).optimize(&result).0
    } else {
        result
    };
    JsonRpcResponse::success(request.id.clone(), result)
}

async fn handle_resources_list(
    state: &AppState,
    request: &JsonRpcRequest,
    ctx: &ToolContext,
) -> JsonRpcResponse {
    // Map registered tools to MCP resources (each tool is also a resource)
    let tools = state.tool_registry.list(Some(&ctx.tenant_id));
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

/// `resources/templates/list` — return URI templates for parameterized resource access (MCP 2025-11-25)
///
/// Returns the `stoa://tools/{name}` template for dynamic tool lookup.
fn handle_resources_templates_list(request: &JsonRpcRequest) -> JsonRpcResponse {
    JsonRpcResponse::success(
        request.id.clone(),
        json!({
            "resourceTemplates": [{
                "uriTemplate": "stoa://tools/{name}",
                "name": "Tool Definition",
                "title": "STOA Tool Definition",
                "description": "Access tool definitions by name. Returns JSON schema and metadata.",
                "mimeType": "application/json"
            }]
        }),
    )
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

    debug!(session_id = %session_id, log_level = %level, "Client set logging level");

    JsonRpcResponse::success(request.id.clone(), json!({}))
}

/// `resources/read` — read a resource by URI (MCP 2025-03-26)
///
/// Supports `stoa://tools/{name}` URIs, returning the full tool schema as JSON.
/// Returns ResourceNotFound (-32002) for unknown tools or unsupported URI schemes.
async fn handle_resources_read(
    state: &AppState,
    request: &JsonRpcRequest,
    ctx: &ToolContext,
) -> JsonRpcResponse {
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
    let tools = state.tool_registry.list(Some(&ctx.tenant_id));
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

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_batch_ws_tenant_header_is_not_identity() {
        let mut state = AppState::new(crate::config::Config::default());
        state.jwt_validator = None;
        let mut headers = HeaderMap::new();
        headers.insert("X-Tenant-ID", "acme".parse().unwrap());
        headers.insert(header::AUTHORIZATION, "Bearer unverified".parse().unwrap());
        for method in ["tools/list", "tools/call"] {
            let response = process_single_request(
                &state,
                &headers,
                &SseQueryParams { session_id: None },
                JsonRpcRequest {
                    jsonrpc: "2.0".to_string(),
                    method: method.to_string(),
                    params: None,
                    id: Some(json!(1)),
                },
            )
            .await;
            assert_eq!(response.error.unwrap().code, -32001);
        }
    }

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

    // === Accept negotiation (CAB-2106 — claude.ai SSE fix) ===

    fn accept(value: &str) -> HeaderMap {
        let mut h = HeaderMap::new();
        h.insert(header::ACCEPT, value.parse().unwrap());
        h
    }

    #[test]
    fn test_accepts_event_stream_explicit() {
        assert!(accepts_event_stream(&accept("text/event-stream")));
    }

    #[test]
    fn test_accepts_event_stream_mcp_compliant_client() {
        // Spec 2025-03-26 says clients MUST list both media types.
        assert!(accepts_event_stream(&accept(
            "application/json, text/event-stream"
        )));
    }

    #[test]
    fn test_accepts_event_stream_with_q_values() {
        assert!(accepts_event_stream(&accept(
            "application/json;q=0.8, text/event-stream;q=0.9"
        )));
    }

    #[test]
    fn test_accepts_event_stream_case_insensitive() {
        assert!(accepts_event_stream(&accept("Text/Event-Stream")));
    }

    #[test]
    fn test_accepts_event_stream_tolerates_whitespace() {
        assert!(accepts_event_stream(&accept(
            "  application/json ,  text/event-stream  "
        )));
    }

    #[test]
    fn test_accepts_event_stream_rejects_json_only() {
        assert!(!accepts_event_stream(&accept("application/json")));
    }

    #[test]
    fn test_accepts_event_stream_rejects_missing_header() {
        assert!(!accepts_event_stream(&HeaderMap::new()));
    }

    #[test]
    fn test_accepts_event_stream_rejects_bare_wildcard() {
        // `*/*` is intentionally NOT accepted: curl / claude-code callers
        // that omit Accept or send `*/*` keep the back-compat JSON body.
        assert!(!accepts_event_stream(&accept("*/*")));
    }

    #[test]
    fn test_accepts_event_stream_rejects_unrelated_types() {
        assert!(!accepts_event_stream(&accept("text/plain, text/html")));
    }
}
