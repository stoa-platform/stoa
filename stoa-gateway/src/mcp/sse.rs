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
use futures::stream::{self, Stream};
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
use crate::oauth::discovery::McpEndpoint;
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

/// JSON-RPC methods that are part of the MCP capability-negotiation /
/// discovery surface. MCP clients (claude.ai, MCP Inspector, claude-code)
/// call these right after `initialize` — before any OAuth flow has
/// attached a Bearer token — so 401-ing them breaks the whole handshake
/// even when the server later advertises OAuth on protected operations.
///
/// CAB-2121: tightened to the bare handshake surface only. `tools/list`,
/// `resources/*`, `prompts/*`, `completion/complete`, `roots/list`, and
/// `logging/setLevel` were removed because they leak tool/resource
/// inventory to anonymous callers over Streamable HTTP (`POST /mcp`) —
/// the REST equivalents (`/mcp/tools/list`, `/mcp/v1/tools`, …) are
/// JWT-gated by the router-level `mcp_jwt_required` middleware.
///
/// `notifications/*` are fire-and-forget client messages with no response
/// body, equally safe to accept anonymously.
const PUBLIC_METHODS: &[&str] = &[
    "initialize",
    "ping",
    "notifications/initialized",
    "notifications/cancelled",
];

/// Who sent a request, once its `Authorization` header has been checked.
///
/// A caller is authenticated only when it presented a bearer and that bearer
/// was accepted: validated when a JWT validator is configured, taken as is
/// when none is (development only: `STOA_PUBLIC_MCP_ENABLED` refuses to boot
/// without a validator). A header with another scheme, or an empty bearer,
/// leaves the caller anonymous. Every transport (single request, batch,
/// event stream, WebSocket) resolves its caller here.
pub(crate) struct Caller {
    pub(crate) tenant_id: String,
    user_id: Option<String>,
    user_email: Option<String>,
    roles: Vec<String>,
    scopes: Vec<String>,
    /// The bearer, only when it was accepted.
    token: Option<String>,
}

impl Caller {
    /// No verified identity. `tenant_header` is honoured only in development
    /// (no validator); with a validator an anonymous caller is in `default`.
    fn unverified(tenant_header: Option<String>, token: Option<String>) -> Self {
        Self {
            tenant_id: tenant_header.unwrap_or_else(|| "default".to_string()),
            user_id: None,
            user_email: None,
            roles: vec![],
            scopes: vec![],
            token,
        }
    }

    pub(crate) fn is_authenticated(&self) -> bool {
        self.token.is_some()
    }

    /// Anonymous callers reach `PUBLIC_METHODS` only.
    fn may_call(&self, method: &str) -> bool {
        PUBLIC_METHODS.contains(&method) || self.is_authenticated()
    }

    fn tool_context(&self, request_id: String) -> ToolContext {
        ToolContext {
            tenant_id: self.tenant_id.clone(),
            user_id: self.user_id.clone(),
            user_email: self.user_email.clone(),
            request_id,
            roles: self.roles.clone(),
            scopes: self.scopes.clone(),
            raw_token: self.token.clone(),
            skill_instructions: None, // skills resolved per-tool in handler
            progress_token: None,     // no progress push (half-duplex)
            consumer_id: "unknown".to_string(), // azp not yet extracted on this path
            from_control_plane: false,
        }
    }
}

/// Resolve the caller of a request.
///
/// `Err` carries the validator's message for a bearer that was presented and
/// rejected. With a validator, the tenant comes from the token (or
/// `default`), never from the `X-Tenant-ID` header.
pub(crate) async fn resolve_caller(
    state: &AppState,
    headers: &HeaderMap,
) -> Result<Caller, String> {
    let token = extract_bearer_token(headers).filter(|token| !token.is_empty());
    let Some(ref validator) = state.jwt_validator else {
        if token.is_some() {
            debug!("JWT validator not configured — skipping token validation");
        }
        return Ok(Caller::unverified(extract_tenant(headers), token));
    };
    let Some(token) = token else {
        return Ok(Caller::unverified(None, None));
    };
    match validator.validate(&token).await {
        Ok(claims) => {
            let caller = Caller {
                tenant_id: claims
                    .tenant_id()
                    .map(|tenant| tenant.to_string())
                    .unwrap_or_else(|| "default".to_string()),
                user_id: Some(claims.user_id().to_string()),
                user_email: claims.email.clone(),
                roles: claims.realm_roles().iter().map(|s| s.to_string()).collect(),
                // OAuth scopes from the JWT (ADR-012 12-Scope Model)
                scopes: claims.scopes().iter().map(|s| s.to_string()).collect(),
                token: Some(token),
            };
            debug!(
                user_id = ?caller.user_id,
                tenant_id = %caller.tenant_id,
                scopes = ?caller.scopes,
                "JWT validated — user authenticated"
            );
            Ok(caller)
        }
        Err(e) => Err(e.to_string()),
    }
}

/// Whether `caller` may use the session `id`.
///
/// With a validator, a session that belongs to a tenant is used only by that
/// tenant. A session opened anonymously is in `default` and stays usable by
/// the client that holds its id, before and after it authenticates. An
/// unknown id is not an existing session and is left to the handlers.
async fn session_open_to(state: &AppState, caller: &Caller, id: &str) -> bool {
    // `get` also refreshes the session's activity, with or without a validator.
    let session = state.session_manager.get(id).await;
    if state.jwt_validator.is_none() {
        return true;
    }
    match session {
        Some(session) => session.tenant_id == caller.tenant_id || session.tenant_id == "default",
        None => true,
    }
}

/// 401 for a bearer the validator rejected.
fn invalid_token_response(
    state: &AppState,
    endpoint: McpEndpoint,
    id: Option<Value>,
    error: &str,
) -> Response {
    challenge_response(
        state,
        endpoint,
        Some("invalid_token"),
        JsonRpcResponse::error(id, -32001, format!("Invalid token: {}", error)),
    )
}

/// 401 challenge for a request that needs an authenticated caller.
fn authentication_required_response(
    state: &AppState,
    endpoint: McpEndpoint,
    id: Option<Value>,
) -> Response {
    challenge_response(
        state,
        endpoint,
        None,
        JsonRpcResponse::error(id, -32001, "Authentication required"),
    )
}

/// 401 with the OAuth challenge that tells the client where the protected
/// resource metadata of `endpoint` is (RFC 9728).
fn challenge_response(
    state: &AppState,
    endpoint: McpEndpoint,
    error: Option<&str>,
    body: JsonRpcResponse,
) -> Response {
    let mut response = (StatusCode::UNAUTHORIZED, Json(body)).into_response();
    let challenge = crate::oauth::discovery::bearer_challenge(&state.config, endpoint, error);
    if let Ok(value) = axum::http::HeaderValue::from_str(&challenge) {
        response
            .headers_mut()
            .insert(header::WWW_AUTHENTICATE, value);
    }
    response
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
    headers: HeaderMap,
    Query(params): Query<SseQueryParams>,
    body: Bytes,
) -> Response {
    handle_json_rpc_post(state, McpEndpoint::Sse, headers, params, body).await
}

/// JSON-RPC over POST, shared by `/mcp/sse` and `/mcp`. `endpoint` is the
/// one the request came in on: a 401 names its metadata document.
async fn handle_json_rpc_post(
    state: AppState,
    endpoint: McpEndpoint,
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
        return handle_batch_request(state, endpoint, headers, params, parsed).await;
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

    // === Authentication (OAuth 2.1 challenge, RFC 9728) ===
    // A bearer that is presented must validate, whatever the method. A
    // protected method needs an accepted bearer; a header with another
    // scheme does not count. See `PUBLIC_METHODS` for the anonymous surface.
    // Tool invocation is further gated by UAC / OPA in `handle_tools_call`.
    let caller = match resolve_caller(&state, &headers).await {
        Ok(caller) => caller,
        Err(e) => {
            warn!(error = %e, "JWT validation failed");
            return invalid_token_response(&state, endpoint, request.id, &e);
        }
    };

    if !caller.may_call(&request.method) {
        debug!(
            method = %request.method,
            "Unauthenticated request to protected method — returning 401"
        );
        return authentication_required_response(&state, endpoint, request.id);
    }

    // Resolve or create session
    let session_id = match params.session_id {
        Some(ref id) => {
            // Touch existing session (`session_open_to` reads it)
            if !session_open_to(&state, &caller, id).await {
                return Json(JsonRpcResponse::error(
                    request.id,
                    -32003,
                    "Session tenant mismatch",
                ))
                .into_response();
            }
            id.clone()
        }
        None => {
            // First request (initialize) — create a session
            let id = Uuid::new_v4().to_string();
            let session = Session::new(id.clone(), caller.tenant_id.clone());
            state.session_manager.create(session).await;
            metrics::update_session_count(state.session_manager.count());
            id
        }
    };

    let ctx = caller.tool_context(request_id.clone());

    // Route to handler
    let response = match request.method.as_str() {
        "initialize" => handle_initialize(&state, &request, &ctx, &session_id).await,
        "ping" => handle_ping(&request),
        "tools/list" => handle_tools_list(&state, &request, &ctx).await,
        "tools/call" => handle_tools_call(&state, &request, &ctx, &session_id).await,
        "resources/list" => handle_resources_list(&state, &request).await,
        "resources/read" => handle_resources_read(&state, &request).await,
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

    handle_json_rpc_post(state, McpEndpoint::StreamableHttp, headers, params, body).await
}

/// GET /mcp/sse - Establish SSE connection (legacy/streaming)
///
/// Opens a persistent SSE connection for real-time updates.
///
/// With a JWT validator, the stream needs an authenticated caller, and an
/// existing `sessionId` can only be reopened by the tenant that owns it.
pub async fn handle_sse_get(
    State(state): State<AppState>,
    headers: HeaderMap,
    Query(params): Query<SseQueryParams>,
) -> Response {
    let caller = match resolve_caller(&state, &headers).await {
        Ok(caller) => caller,
        Err(e) => return invalid_token_response(&state, McpEndpoint::Sse, None, &e),
    };
    if state.jwt_validator.is_some() {
        if !caller.is_authenticated() {
            return authentication_required_response(&state, McpEndpoint::Sse, None);
        }
        if let Some(ref id) = params.session_id {
            if let Some(existing) = state.session_manager.get(id).await {
                if existing.tenant_id != caller.tenant_id {
                    return StatusCode::NOT_FOUND.into_response();
                }
            }
        }
    }

    let session_id = params
        .session_id
        .unwrap_or_else(|| Uuid::new_v4().to_string());
    let tenant_id = caller.tenant_id.clone();

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
///
/// With a JWT validator, only an authenticated caller of the owning tenant
/// can close a session. Another tenant's session answers like a missing one.
pub async fn handle_sse_delete(
    State(state): State<AppState>,
    headers: HeaderMap,
    Query(params): Query<SseQueryParams>,
) -> Response {
    let caller = match resolve_caller(&state, &headers).await {
        Ok(caller) => caller,
        Err(e) => return invalid_token_response(&state, McpEndpoint::Sse, None, &e),
    };
    if state.jwt_validator.is_some() {
        if !caller.is_authenticated() {
            return authentication_required_response(&state, McpEndpoint::Sse, None);
        }
        if let Some(ref id) = params.session_id {
            match state.session_manager.get(id).await {
                Some(existing) if existing.tenant_id == caller.tenant_id => {}
                _ => return StatusCode::NOT_FOUND.into_response(),
            }
        }
    }

    if let Some(session_id) = params.session_id {
        // Unregister NotificationBus channel before removing session (CAB-1178)
        state.session_manager.unregister_channel(&session_id);

        if state.session_manager.remove(&session_id).await {
            info!(session_id = %session_id, "Session closed");
            metrics::update_session_count(state.session_manager.count());
            StatusCode::NO_CONTENT.into_response()
        } else {
            StatusCode::NOT_FOUND.into_response()
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
    endpoint: McpEndpoint,
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

    // One caller for the whole batch, resolved the same way as for a single
    // request: a rejected bearer refuses the batch, and each element is then
    // checked against that caller.
    let caller = match resolve_caller(&state, &headers).await {
        Ok(caller) => std::sync::Arc::new(caller),
        Err(e) => {
            warn!(error = %e, "JWT validation failed (batch)");
            return invalid_token_response(&state, endpoint, None, &e);
        }
    };

    // Process all requests concurrently
    let futures: Vec<_> = requests
        .into_iter()
        .map(|req_value| {
            let state = state.clone();
            let caller = caller.clone();
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
                process_request_as(&state, &params_clone, request, &caller).await
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

/// Process one JSON-RPC message for a transport that carries its own
/// `Authorization` header per message (WebSocket). The caller is resolved
/// from that header, exactly as for `POST /mcp`.
pub async fn process_single_request(
    state: &AppState,
    headers: &HeaderMap,
    params: &SseQueryParams,
    request: JsonRpcRequest,
) -> JsonRpcResponse {
    match resolve_caller(state, headers).await {
        Ok(caller) => process_request_as(state, params, request, &caller).await,
        Err(e) => {
            warn!(error = %e, "JWT validation failed");
            JsonRpcResponse::error(request.id, -32001, format!("Invalid token: {}", e))
        }
    }
}

/// Process one JSON-RPC request for an already resolved caller (batch
/// elements and WebSocket messages).
async fn process_request_as(
    state: &AppState,
    params: &SseQueryParams,
    request: JsonRpcRequest,
    caller: &Caller,
) -> JsonRpcResponse {
    // Validate JSON-RPC version
    if request.jsonrpc != "2.0" {
        return JsonRpcResponse::error(request.id, INVALID_REQUEST, "Invalid JSON-RPC version");
    }

    if !caller.may_call(&request.method) {
        return JsonRpcResponse::error(request.id, -32001, "Authentication required");
    }

    if let Some(ref id) = params.session_id {
        if !session_open_to(state, caller, id).await {
            return JsonRpcResponse::error(request.id, -32003, "Session tenant mismatch");
        }
    }

    let session_id = params
        .session_id
        .clone()
        .unwrap_or_else(|| Uuid::new_v4().to_string());

    let ctx = caller.tool_context(Uuid::new_v4().to_string());

    // Route to handler
    match request.method.as_str() {
        "initialize" => handle_initialize(state, &request, &ctx, &session_id).await,
        "ping" => handle_ping(&request),
        "tools/list" => handle_tools_list(state, &request, &ctx).await,
        "tools/call" => handle_tools_call(state, &request, &ctx, &session_id).await,
        "resources/list" => handle_resources_list(state, &request).await,
        "resources/read" => handle_resources_read(state, &request).await,
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
                    opt_level = ?opt_settings.level,
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

/// Authentication of the MCP transports through the real router, with a JWT
/// validator that accepts tokens signed by the test key.
#[cfg(test)]
mod caller_tests {
    use super::*;
    use crate::auth::jwt::tests::{issuer_only, mint, validator_with_mock_server};
    use crate::config::Config;
    use axum::body::Body;
    use axum::http::{Method, Request};
    use axum::Router;
    use std::sync::Arc;
    use tower::ServiceExt;

    /// Headers a caller without an accepted bearer can send.
    const REJECTED: &[Option<&str>] = &[
        None,
        Some("Basic eDp5"),
        Some("Token abc"),
        Some("Bearer"),
        Some("Bearer "),
        Some("Bearer nope"),
        Some("bearer nope"),
    ];

    const PROTECTED_METHODS: &[&str] = &[
        "tools/list",
        "tools/call",
        "resources/list",
        "resources/read",
        "resources/templates/list",
        "prompts/list",
        "logging/setLevel",
        "completion/complete",
        "roots/list",
    ];

    struct Fixture {
        router: Router,
        state: AppState,
        bearer: String,
        /// Kept alive: the validator fetches discovery and JWKS from it.
        _oidc: wiremock::MockServer,
    }

    async fn fixture() -> Fixture {
        let (validator, issuer, oidc) = validator_with_mock_server(issuer_only()).await;
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs() as i64;
        let bearer = format!("Bearer {}", mint(&issuer, now + 300, None));
        let mut state = AppState::new(Config::default());
        state.jwt_validator = Some(Arc::new(validator));
        Fixture {
            router: crate::build_router(state.clone()),
            state,
            bearer,
            _oidc: oidc,
        }
    }

    fn request(method: Method, uri: &str, auth: Option<&str>, body: String) -> Request<Body> {
        let mut request = Request::builder()
            .method(method)
            .uri(uri)
            .header("content-type", "application/json")
            .header("x-tenant-id", "acme");
        if let Some(auth) = auth {
            request = request.header("authorization", auth);
        }
        request.body(Body::from(body)).unwrap()
    }

    async fn status(router: &Router, request: Request<Body>) -> StatusCode {
        router.clone().oneshot(request).await.unwrap().status()
    }

    async fn post(
        router: &Router,
        uri: &str,
        auth: Option<&str>,
        body: String,
    ) -> (StatusCode, String) {
        let response = router
            .clone()
            .oneshot(request(Method::POST, uri, auth, body))
            .await
            .unwrap();
        let status = response.status();
        let bytes = axum::body::to_bytes(response.into_body(), 4 * 1024 * 1024)
            .await
            .unwrap();
        (status, String::from_utf8_lossy(&bytes).into_owned())
    }

    fn rpc(method: &str) -> String {
        format!(
            r#"{{"jsonrpc":"2.0","id":1,"method":"{method}","params":{{"name":"x","uri":"stoa://x","level":"info"}}}}"#
        )
    }

    #[tokio::test]
    async fn accepted_bearer_lists_tools_single_and_batch() {
        let fx = fixture().await;
        for uri in ["/mcp", "/mcp/sse"] {
            let (status, body) = post(&fx.router, uri, Some(&fx.bearer), rpc("tools/list")).await;
            assert_eq!(status, StatusCode::OK, "{uri} {body}");
            assert!(body.contains(r#""tools""#), "{uri} {body}");

            let batch = format!("[{}]", rpc("tools/list"));
            let (status, body) = post(&fx.router, uri, Some(&fx.bearer), batch).await;
            assert_eq!(status, StatusCode::OK, "{uri} {body}");
            assert!(body.contains(r#""tools""#), "{uri} {body}");
        }
    }

    #[tokio::test]
    async fn protected_methods_need_an_accepted_bearer() {
        let fx = fixture().await;
        for auth in REJECTED {
            for uri in ["/mcp", "/mcp/sse"] {
                for method in PROTECTED_METHODS {
                    let (status, body) = post(&fx.router, uri, *auth, rpc(method)).await;
                    assert_eq!(
                        status,
                        StatusCode::UNAUTHORIZED,
                        "{auth:?} {uri} {method} {body}"
                    );
                    assert!(
                        !body.contains(r#""result""#),
                        "{auth:?} {uri} {method} {body}"
                    );
                }
            }
        }
    }

    #[tokio::test]
    async fn batch_elements_need_an_accepted_bearer() {
        let fx = fixture().await;
        let batch = format!(
            "[{}]",
            PROTECTED_METHODS
                .iter()
                .map(|method| rpc(method))
                .collect::<Vec<_>>()
                .join(",")
        );
        for auth in REJECTED {
            for uri in ["/mcp", "/mcp/sse"] {
                let (status, body) = post(&fx.router, uri, *auth, batch.clone()).await;
                assert!(
                    status == StatusCode::UNAUTHORIZED || status == StatusCode::OK,
                    "{auth:?} {uri} {status}"
                );
                assert!(!body.contains(r#""result""#), "{auth:?} {uri} {body}");
                assert!(!body.contains(r#""tools""#), "{auth:?} {uri} {body}");
            }
        }
        // A rejected bearer refuses the whole batch, public methods included.
        let mixed = format!("[{},{}]", rpc("ping"), rpc("tools/list"));
        let (status, _) = post(&fx.router, "/mcp", Some("Bearer nope"), mixed.clone()).await;
        assert_eq!(status, StatusCode::UNAUTHORIZED);
        // No bearer: the public element answers, the protected one does not.
        let (status, body) = post(&fx.router, "/mcp", Some("Basic eDp5"), mixed).await;
        assert_eq!(status, StatusCode::OK);
        assert!(body.contains("Authentication required"), "{body}");
        assert!(!body.contains(r#""tools""#), "{body}");
    }

    #[tokio::test]
    async fn public_methods_stay_anonymous() {
        let fx = fixture().await;
        let initialize = r#"{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"t","version":"0"}}}"#;
        for auth in [None, Some("Basic eDp5")] {
            let (status, body) = post(&fx.router, "/mcp", auth, initialize.to_string()).await;
            assert_eq!(status, StatusCode::OK, "{auth:?} {body}");
            assert!(body.contains(r#""result""#), "{auth:?} {body}");
            let (status, _) = post(&fx.router, "/mcp", auth, rpc("ping")).await;
            assert_eq!(status, StatusCode::OK, "{auth:?}");
        }
        // A bearer that is presented must validate, even for a public method.
        let (status, _) = post(&fx.router, "/mcp", Some("Bearer nope"), rpc("ping")).await;
        assert_eq!(status, StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn tenant_comes_from_the_token_when_a_validator_exists() {
        let fx = fixture().await;
        let mut headers = HeaderMap::new();
        headers.insert("x-tenant-id", "acme".parse().unwrap());

        let anonymous = resolve_caller(&fx.state, &headers).await.unwrap();
        assert!(!anonymous.is_authenticated());
        assert_eq!(
            anonymous.tenant_id, "default",
            "header must not pick the tenant"
        );

        headers.insert(header::AUTHORIZATION, fx.bearer.parse().unwrap());
        let caller = resolve_caller(&fx.state, &headers).await.unwrap();
        assert!(caller.is_authenticated());
        assert_eq!(
            caller.tenant_id, "default",
            "header must not pick the tenant"
        );

        headers.insert(header::AUTHORIZATION, "Bearer nope".parse().unwrap());
        assert!(resolve_caller(&fx.state, &headers).await.is_err());

        // Development mode, no validator: the bearer is taken as is.
        let mut dev = fx.state.clone();
        dev.jwt_validator = None;
        let caller = resolve_caller(&dev, &headers).await.unwrap();
        assert!(caller.is_authenticated());
        assert_eq!(caller.tenant_id, "acme");
    }

    #[tokio::test]
    async fn a_tenant_session_is_closed_to_other_callers() {
        let fx = fixture().await;
        fx.state
            .session_manager
            .create(Session::new("theirs".into(), "other".into()))
            .await;
        fx.state
            .session_manager
            .create(Session::new("anonymous".into(), "default".into()))
            .await;
        let initialize = r#"{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"intruder","version":"0"}}}"#;

        for auth in [None, Some(fx.bearer.as_str())] {
            for body in [
                initialize.to_string(),
                format!("[{initialize}]"),
                rpc("ping"),
            ] {
                let (_, text) = post(&fx.router, "/mcp/sse?sessionId=theirs", auth, body).await;
                assert!(text.contains("Session tenant mismatch"), "{auth:?} {text}");
                assert!(!text.contains(r#""result""#), "{auth:?} {text}");
            }
            // A session opened anonymously stays usable by whoever holds its id.
            let (status, text) = post(
                &fx.router,
                "/mcp/sse?sessionId=anonymous",
                auth,
                rpc("ping"),
            )
            .await;
            assert_eq!(status, StatusCode::OK, "{auth:?} {text}");
            assert!(text.contains(r#""result""#), "{auth:?} {text}");
        }
        assert!(
            fx.state
                .session_manager
                .get_metadata("theirs", "protocol_version")
                .await
                .is_none(),
            "a refused initialize must not write to the session"
        );
    }

    /// The path of a client that initializes anonymously, then authenticates
    /// as a tenant, and the reverse cases that must stay closed.
    #[tokio::test]
    async fn session_ownership_follows_the_tenant() {
        let fx = fixture().await;
        for (id, tenant) in [
            ("anonymous", "default"),
            ("demo", "demo"),
            ("other", "other"),
        ] {
            fx.state
                .session_manager
                .create(Session::new(id.into(), tenant.into()))
                .await;
        }
        let demo = Caller {
            tenant_id: "demo".into(),
            ..Caller::unverified(None, Some("accepted".into()))
        };
        let anonymous = Caller::unverified(None, None);

        assert!(session_open_to(&fx.state, &demo, "anonymous").await);
        assert!(session_open_to(&fx.state, &demo, "demo").await);
        assert!(!session_open_to(&fx.state, &demo, "other").await);
        assert!(session_open_to(&fx.state, &anonymous, "anonymous").await);
        assert!(!session_open_to(&fx.state, &anonymous, "demo").await);
        assert!(session_open_to(&fx.state, &demo, "unknown").await);

        // Development mode (no validator): no ownership check.
        let mut dev = fx.state.clone();
        dev.jwt_validator = None;
        assert!(session_open_to(&dev, &anonymous, "other").await);
    }

    #[tokio::test]
    async fn event_stream_needs_an_authenticated_owner() {
        let fx = fixture().await;
        fx.state
            .session_manager
            .create(Session::new("mine".into(), "default".into()))
            .await;
        fx.state
            .session_manager
            .create(Session::new("theirs".into(), "other".into()))
            .await;

        for auth in REJECTED {
            for (method, uri) in [
                (Method::GET, "/mcp/sse"),
                (Method::GET, "/mcp/sse?sessionId=mine"),
                (Method::DELETE, "/mcp/sse?sessionId=mine"),
            ] {
                assert_eq!(
                    status(
                        &fx.router,
                        request(method.clone(), uri, *auth, String::new())
                    )
                    .await,
                    StatusCode::UNAUTHORIZED,
                    "{auth:?} {method} {uri}"
                );
            }
        }
        assert!(fx.state.session_manager.get("mine").await.is_some());

        let bearer = Some(fx.bearer.as_str());
        let call = |method: Method, uri: &'static str| {
            status(&fx.router, request(method, uri, bearer, String::new()))
        };
        assert_eq!(
            call(Method::GET, "/mcp/sse?sessionId=theirs").await,
            StatusCode::NOT_FOUND
        );
        assert_eq!(
            call(Method::DELETE, "/mcp/sse?sessionId=theirs").await,
            StatusCode::NOT_FOUND
        );
        assert!(fx.state.session_manager.get("theirs").await.is_some());
        assert_eq!(
            call(Method::DELETE, "/mcp/sse?sessionId=missing").await,
            StatusCode::NOT_FOUND
        );
        assert_eq!(
            call(Method::DELETE, "/mcp/sse").await,
            StatusCode::BAD_REQUEST
        );
        assert_eq!(
            call(Method::GET, "/mcp/sse?sessionId=mine").await,
            StatusCode::OK
        );
        assert_eq!(
            call(Method::DELETE, "/mcp/sse?sessionId=mine").await,
            StatusCode::NO_CONTENT
        );
        assert!(fx.state.session_manager.get("mine").await.is_none());
    }
}
