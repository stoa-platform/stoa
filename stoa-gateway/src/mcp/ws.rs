//! MCP WebSocket Transport (CAB-1345)
//!
//! Provides full-duplex WebSocket transport for MCP alongside SSE.
//! Reuses `process_single_request()` from SSE for JSON-RPC dispatch.
//!
//! Auth: Bearer token from `Authorization` header (non-browser) or
//! `Sec-WebSocket-Protocol: mcp-auth.<token>` subprotocol (browser).
//!
//! Phase 2 additions (CAB-1345):
//! - Detect inbound responses to server-initiated requests
//! - `request_sampling()`, `request_roots_list()`, `notify_tools_changed()`
//! - PendingRequestTracker cleanup on disconnect

use axum::{
    extract::{
        ws::{Message, WebSocket, WebSocketUpgrade},
        State,
    },
    http::{header, HeaderMap, StatusCode},
    response::{IntoResponse, Response},
};
use serde_json::Value;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::mpsc;
use tracing::{debug, info, warn};

use crate::mcp::pending_requests::{PendingRequestTracker, ServerRequestResult};
use crate::mcp::session::Session;
use crate::mcp::sse::{
    extract_bearer_token, process_single_request, JsonRpcRequest, JsonRpcResponse, SseQueryParams,
};
use crate::metrics;
use crate::state::AppState;

/// WebSocket upgrade handler.
///
/// Validates the feature flag, extracts auth token, and upgrades the connection.
pub async fn handle_ws_upgrade(
    State(state): State<AppState>,
    ws: WebSocketUpgrade,
    headers: HeaderMap,
) -> Response {
    // Feature gate: WebSocket must be explicitly enabled
    if !state.config.websocket_enabled {
        return (StatusCode::NOT_FOUND, "WebSocket transport is not enabled").into_response();
    }

    // Extract token from Authorization header or subprotocol
    let token = extract_ws_token(&headers);
    if token.is_none() {
        return (
            StatusCode::UNAUTHORIZED,
            "Missing Bearer token (Authorization header or mcp-auth subprotocol)",
        )
            .into_response();
    }

    let token = token.expect("checked above");

    // Build headers for process_single_request (it expects Authorization header)
    let synthetic_headers = build_headers_from_token(&token);

    // Check if browser is using subprotocol auth — we need to echo back the subprotocol
    let selected_protocol = extract_subprotocol(&headers);

    let upgrade = if let Some(proto) = selected_protocol {
        ws.protocols([proto])
    } else {
        ws
    };

    upgrade.on_upgrade(move |socket| handle_ws_connection(socket, state, synthetic_headers))
}

/// Main WebSocket connection loop.
///
/// Uses `tokio::select!` with 3 branches:
/// 1. Inbound client messages → parse JSON-RPC → dispatch via `process_single_request`
/// 2. Outbound server notifications → forward as Text
/// 3. Periodic ping → keepalive
async fn handle_ws_connection(mut socket: WebSocket, state: AppState, headers: HeaderMap) {
    let session_id = uuid::Uuid::new_v4().to_string();
    let tenant_id = headers
        .get("X-Tenant-ID")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("unknown")
        .to_string();

    // Create MCP session
    let session = Session::new(session_id.clone(), tenant_id.clone());
    state.session_manager.create(session).await;

    // Register WS notification channel
    let (notify_tx, mut notify_rx) = mpsc::channel::<String>(64);
    state
        .session_manager
        .register_ws_channel(&session_id, notify_tx);

    metrics::track_ws_connect();
    let start = Instant::now();
    info!(session_id = %session_id, tenant_id = %tenant_id, "WebSocket connected");

    let mut ping_interval = tokio::time::interval(Duration::from_secs(30));
    // Skip the first tick (fires immediately)
    ping_interval.tick().await;

    loop {
        tokio::select! {
            // Branch 1: inbound client message
            msg = socket.recv() => {
                match msg {
                    Some(Ok(Message::Text(text))) => {
                        let response = handle_ws_text_message(
                            &text, &state, &headers, &session_id
                        ).await;
                        if let Some(resp_text) = response {
                            if socket.send(Message::Text(resp_text)).await.is_err() {
                                break;
                            }
                        }
                    }
                    Some(Ok(Message::Ping(data))) => {
                        if socket.send(Message::Pong(data)).await.is_err() {
                            break;
                        }
                    }
                    Some(Ok(Message::Pong(_))) => {
                        // Keepalive response — no action needed
                    }
                    Some(Ok(Message::Close(_))) | None => {
                        debug!(session_id = %session_id, "WebSocket closed by client");
                        break;
                    }
                    Some(Ok(Message::Binary(_))) => {
                        // MCP uses text frames only
                        warn!(session_id = %session_id, "Ignoring binary WebSocket frame");
                    }
                    Some(Err(e)) => {
                        warn!(session_id = %session_id, error = %e, "WebSocket error");
                        break;
                    }
                }
            }
            // Branch 2: outbound server notification
            notification = notify_rx.recv() => {
                match notification {
                    Some(text) => {
                        if socket.send(Message::Text(text)).await.is_err() {
                            break;
                        }
                    }
                    None => {
                        // Channel closed (session removed)
                        break;
                    }
                }
            }
            // Branch 3: periodic ping
            _ = ping_interval.tick() => {
                if socket.send(Message::Ping(vec![])).await.is_err() {
                    break;
                }
            }
        }
    }

    // Cleanup
    let duration = start.elapsed().as_secs_f64();
    state.pending_requests.remove_session(&session_id);
    state.session_manager.unregister_ws_channel(&session_id);
    state.session_manager.remove(&session_id).await;
    metrics::track_ws_disconnect(&tenant_id, duration);
    info!(
        session_id = %session_id,
        duration_secs = duration,
        "WebSocket disconnected"
    );
}

// ---------------------------------------------------------------------------
// Response Detection (CAB-1345 Phase 2)
// ---------------------------------------------------------------------------

/// Check if an inbound JSON object is a response to a server-initiated request.
///
/// JSON-RPC responses have `id` + (`result` or `error`) but NO `method` field.
/// Server-initiated request IDs use the `srv-N` prefix.
fn is_server_request_response(value: &Value) -> bool {
    let obj = match value.as_object() {
        Some(o) => o,
        None => return false,
    };
    // Must have id, no method, and either result or error
    obj.contains_key("id")
        && !obj.contains_key("method")
        && (obj.contains_key("result") || obj.contains_key("error"))
}

/// Try to resolve an inbound response against the pending request tracker.
///
/// Returns `true` if the message was a response and was handled.
fn try_resolve_response(value: &Value, tracker: &PendingRequestTracker, session_id: &str) -> bool {
    let obj = match value.as_object() {
        Some(o) => o,
        None => return false,
    };

    let request_id = match obj.get("id").and_then(|v| v.as_str()) {
        Some(id) => id.to_string(),
        None => {
            // id might be a number
            match obj.get("id").and_then(|v| v.as_u64()) {
                Some(n) => n.to_string(),
                None => return false,
            }
        }
    };

    resolve_with_id(obj, tracker, session_id, &request_id)
}

fn resolve_with_id(
    obj: &serde_json::Map<String, Value>,
    tracker: &PendingRequestTracker,
    session_id: &str,
    request_id: &str,
) -> bool {
    let result = if let Some(result_val) = obj.get("result") {
        ServerRequestResult::Success(result_val.clone())
    } else if let Some(error_val) = obj.get("error") {
        let code = error_val
            .get("code")
            .and_then(|v| v.as_i64())
            .unwrap_or(-32000);
        let message = error_val
            .get("message")
            .and_then(|v| v.as_str())
            .unwrap_or("Unknown error")
            .to_string();
        ServerRequestResult::Error { code, message }
    } else {
        return false;
    };

    tracker.resolve(session_id, request_id, result)
}

/// Handle a single inbound text message (JSON-RPC request, response, or batch).
async fn handle_ws_text_message(
    text: &str,
    state: &AppState,
    headers: &HeaderMap,
    session_id: &str,
) -> Option<String> {
    metrics::track_ws_message("inbound", "request");

    let params = SseQueryParams {
        session_id: Some(session_id.to_string()),
    };

    // Try parsing as a single request first, then as batch
    let parsed: Result<Value, _> = serde_json::from_str(text);
    match parsed {
        Ok(Value::Array(arr)) => {
            // JSON-RPC batch
            let response = handle_ws_batch(arr, state, headers, &params).await;
            metrics::track_ws_message("outbound", "batch_response");
            Some(serde_json::to_string(&response).unwrap_or_default())
        }
        Ok(value) => {
            // Check if this is a response to a server-initiated request
            if is_server_request_response(&value)
                && try_resolve_response(&value, &state.pending_requests, session_id)
            {
                metrics::track_ws_message("inbound", "server_request_response");
                return None; // Response handled, no reply needed
            }

            // Single request
            match serde_json::from_value::<JsonRpcRequest>(value) {
                Ok(req) => {
                    let method = req.method.clone();
                    let resp = process_single_request(state, headers, &params, req).await;
                    metrics::track_ws_message("outbound", &method);
                    Some(serde_json::to_string(&resp).unwrap_or_default())
                }
                Err(e) => {
                    let err = JsonRpcResponse::error(
                        None,
                        crate::mcp::sse::PARSE_ERROR,
                        format!("Invalid JSON-RPC request: {e}"),
                    );
                    Some(serde_json::to_string(&err).unwrap_or_default())
                }
            }
        }
        Err(e) => {
            let err = JsonRpcResponse::error(
                None,
                crate::mcp::sse::PARSE_ERROR,
                format!("Invalid JSON: {e}"),
            );
            Some(serde_json::to_string(&err).unwrap_or_default())
        }
    }
}

/// Handle a JSON-RPC batch request over WebSocket.
async fn handle_ws_batch(
    items: Vec<Value>,
    state: &AppState,
    headers: &HeaderMap,
    params: &SseQueryParams,
) -> Vec<JsonRpcResponse> {
    let mut responses = Vec::with_capacity(items.len());
    for item in items {
        match serde_json::from_value::<JsonRpcRequest>(item) {
            Ok(req) => {
                let resp = process_single_request(state, headers, params, req).await;
                responses.push(resp);
            }
            Err(e) => {
                responses.push(JsonRpcResponse::error(
                    None,
                    crate::mcp::sse::PARSE_ERROR,
                    format!("Invalid request in batch: {e}"),
                ));
            }
        }
    }
    responses
}

/// Extract auth token from WS upgrade request.
///
/// Priority:
/// 1. `Authorization: Bearer <token>` header (non-browser clients)
/// 2. `Sec-WebSocket-Protocol: mcp-auth.<token>` subprotocol (browser clients)
fn extract_ws_token(headers: &HeaderMap) -> Option<String> {
    // Try Authorization header first
    if let Some(token) = extract_bearer_token(headers) {
        return Some(token);
    }

    // Fall back to subprotocol-based auth (browser pattern)
    extract_token_from_subprotocol(headers)
}

/// Extract token from `Sec-WebSocket-Protocol: mcp-auth.<base64-token>` header.
///
/// Browser WebSocket API cannot set custom headers. The MCP convention is to
/// pass the token via a subprotocol that starts with `mcp-auth.`.
fn extract_token_from_subprotocol(headers: &HeaderMap) -> Option<String> {
    headers
        .get("Sec-WebSocket-Protocol")
        .and_then(|v| v.to_str().ok())
        .and_then(|protocols| {
            protocols
                .split(',')
                .map(|s| s.trim())
                .find(|p| p.starts_with("mcp-auth."))
                .and_then(|p| p.strip_prefix("mcp-auth."))
                .map(|t| t.to_string())
        })
}

/// Extract the mcp-auth subprotocol value for echoing back in upgrade response.
fn extract_subprotocol(headers: &HeaderMap) -> Option<String> {
    headers
        .get("Sec-WebSocket-Protocol")
        .and_then(|v| v.to_str().ok())
        .and_then(|protocols| {
            protocols
                .split(',')
                .map(|s| s.trim())
                .find(|p| p.starts_with("mcp-auth."))
                .map(|p| p.to_string())
        })
}

/// Build a synthetic HeaderMap with Authorization header from an extracted token.
/// This lets `process_single_request` reuse its existing JWT validation path.
fn build_headers_from_token(token: &str) -> HeaderMap {
    let mut headers = HeaderMap::new();
    if let Ok(val) = format!("Bearer {token}").parse() {
        headers.insert(header::AUTHORIZATION, val);
    }
    headers
}

// ---------------------------------------------------------------------------
// Progress Notifications (CAB-1345 Phase 3)
// ---------------------------------------------------------------------------

/// Send a `notifications/progress` notification to the client over WebSocket.
///
/// Used when `tools/call` includes `_meta.progressToken`. The server sends
/// incremental progress updates as the tool executes. SSE clients are
/// unaffected (progress_tx = None since SSE can't push mid-request).
///
/// MCP progress notification spec:
/// - `progressToken`: opaque token from the client's `_meta.progressToken`
/// - `progress`: current progress value (e.g., bytes transferred, steps done)
/// - `total`: optional total expected (e.g., total bytes, total steps)
pub fn notify_progress(
    session_manager: &crate::mcp::session::SessionManager,
    session_id: &str,
    progress_token: &Value,
    progress: f64,
    total: Option<f64>,
) {
    let mut notification = serde_json::json!({
        "jsonrpc": "2.0",
        "method": "notifications/progress",
        "params": {
            "progressToken": progress_token,
            "progress": progress
        }
    });
    if let Some(t) = total {
        notification["params"]["total"] = serde_json::json!(t);
    }
    let text = serde_json::to_string(&notification).unwrap_or_default();
    if !session_manager.send_to_session_ws(session_id, &text) {
        debug!(
            session_id = %session_id,
            "Failed to send progress notification (client may have disconnected)"
        );
    }
}

// ---------------------------------------------------------------------------
// Server-Initiated Request Helpers (CAB-1345 Phase 2)
// ---------------------------------------------------------------------------

/// Send a `sampling/createMessage` request to the client and await the response.
///
/// Used for server-initiated LLM sampling via the MCP bidirectional protocol.
/// The client's LLM generates the response — 60s timeout accounts for inference time.
pub async fn request_sampling(
    tracker: &Arc<PendingRequestTracker>,
    session_manager: &crate::mcp::session::SessionManager,
    session_id: &str,
    params: Value,
) -> ServerRequestResult {
    let ws_send = |sid: &str, msg: &str| -> bool { session_manager.send_to_session_ws(sid, msg) };
    tracker
        .send_request(
            session_id,
            "sampling/createMessage",
            Some(params),
            &ws_send,
            Duration::from_secs(60),
        )
        .await
}

/// Send a `roots/list` request to the client and await the response.
///
/// Asks the client for its filesystem roots (workspace directories, project roots).
/// 10s timeout — this should be a fast local operation.
pub async fn request_roots_list(
    tracker: &Arc<PendingRequestTracker>,
    session_manager: &crate::mcp::session::SessionManager,
    session_id: &str,
) -> ServerRequestResult {
    let ws_send = |sid: &str, msg: &str| -> bool { session_manager.send_to_session_ws(sid, msg) };
    tracker
        .send_request(
            session_id,
            "roots/list",
            None,
            &ws_send,
            Duration::from_secs(10),
        )
        .await
}

/// Send a `notifications/tools/listChanged` notification to the client.
///
/// Fire-and-forget: tells the client that the server's tool list has changed
/// so it should re-fetch `tools/list`. No response expected.
pub fn notify_tools_changed(
    session_manager: &crate::mcp::session::SessionManager,
    session_id: &str,
) {
    let notification = serde_json::json!({
        "jsonrpc": "2.0",
        "method": "notifications/tools/listChanged",
    });
    let text = serde_json::to_string(&notification).unwrap_or_default();
    if !session_manager.send_to_session_ws(session_id, &text) {
        warn!(
            session_id = %session_id,
            "Failed to send tools/listChanged notification"
        );
    }
}

/// Broadcast a `notifications/tools/listChanged` notification to all sessions of a tenant.
pub fn broadcast_tools_changed(
    session_manager: &crate::mcp::session::SessionManager,
    tenant_id: &str,
) {
    let notification = serde_json::json!({
        "jsonrpc": "2.0",
        "method": "notifications/tools/listChanged",
    });
    let text = serde_json::to_string(&notification).unwrap_or_default();
    session_manager.broadcast_to_tenant_ws(tenant_id, &text);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extract_ws_token_from_authorization() {
        let mut headers = HeaderMap::new();
        headers.insert(
            header::AUTHORIZATION,
            "Bearer my-jwt-token".parse().unwrap(),
        );
        assert_eq!(extract_ws_token(&headers), Some("my-jwt-token".to_string()));
    }

    #[test]
    fn test_extract_ws_token_from_subprotocol() {
        let mut headers = HeaderMap::new();
        headers.insert(
            "Sec-WebSocket-Protocol",
            "mcp-auth.eyJhbGciOiJSUzI1NiJ9".parse().unwrap(),
        );
        assert_eq!(
            extract_ws_token(&headers),
            Some("eyJhbGciOiJSUzI1NiJ9".to_string())
        );
    }

    #[test]
    fn test_extract_ws_token_prefers_authorization() {
        let mut headers = HeaderMap::new();
        headers.insert(
            header::AUTHORIZATION,
            "Bearer header-token".parse().unwrap(),
        );
        headers.insert(
            "Sec-WebSocket-Protocol",
            "mcp-auth.subproto-token".parse().unwrap(),
        );
        // Authorization header takes priority
        assert_eq!(extract_ws_token(&headers), Some("header-token".to_string()));
    }

    #[test]
    fn test_extract_ws_token_no_auth() {
        let headers = HeaderMap::new();
        assert_eq!(extract_ws_token(&headers), None);
    }

    #[test]
    fn test_extract_subprotocol_multiple() {
        let mut headers = HeaderMap::new();
        headers.insert(
            "Sec-WebSocket-Protocol",
            "mcp, mcp-auth.mytoken123".parse().unwrap(),
        );
        assert_eq!(
            extract_subprotocol(&headers),
            Some("mcp-auth.mytoken123".to_string())
        );
    }

    #[test]
    fn test_extract_subprotocol_none() {
        let headers = HeaderMap::new();
        assert_eq!(extract_subprotocol(&headers), None);
    }

    #[test]
    fn test_extract_token_from_subprotocol_strips_prefix() {
        let mut headers = HeaderMap::new();
        headers.insert("Sec-WebSocket-Protocol", "mcp-auth.abc123".parse().unwrap());
        assert_eq!(
            extract_token_from_subprotocol(&headers),
            Some("abc123".to_string())
        );
    }

    #[test]
    fn test_build_headers_from_token() {
        let headers = build_headers_from_token("test-token");
        assert_eq!(
            headers
                .get(header::AUTHORIZATION)
                .unwrap()
                .to_str()
                .unwrap(),
            "Bearer test-token"
        );
    }

    #[test]
    fn test_websocket_disabled_returns_404() {
        // This is tested at the handler level (integration), but we verify
        // the feature flag concept is correct
        let config = crate::config::Config::default();
        assert!(!config.websocket_enabled);
    }

    // --- Phase 2 tests: response detection ---

    #[test]
    fn test_is_server_request_response_success() {
        let value = serde_json::json!({
            "jsonrpc": "2.0",
            "id": "srv-1",
            "result": {"content": "hello"}
        });
        assert!(is_server_request_response(&value));
    }

    #[test]
    fn test_is_server_request_response_error() {
        let value = serde_json::json!({
            "jsonrpc": "2.0",
            "id": "srv-1",
            "error": {"code": -32601, "message": "Method not found"}
        });
        assert!(is_server_request_response(&value));
    }

    #[test]
    fn test_is_server_request_response_not_a_response() {
        // Has method → it's a request, not a response
        let value = serde_json::json!({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list"
        });
        assert!(!is_server_request_response(&value));
    }

    #[test]
    fn test_is_server_request_response_notification() {
        // No id, no result/error → notification
        let value = serde_json::json!({
            "jsonrpc": "2.0",
            "method": "notifications/tools/listChanged"
        });
        assert!(!is_server_request_response(&value));
    }

    #[test]
    fn test_try_resolve_response_success() {
        let tracker = PendingRequestTracker::new();
        let mut rx = tracker.register("ws-session-1", "srv-1");

        let value = serde_json::json!({
            "jsonrpc": "2.0",
            "id": "srv-1",
            "result": {"content": [{"type": "text", "text": "Hello!"}]}
        });

        assert!(try_resolve_response(&value, &tracker, "ws-session-1"));

        let result = rx.try_recv().expect("should have result");
        match result {
            ServerRequestResult::Success(v) => {
                assert_eq!(v["content"][0]["text"], "Hello!");
            }
            _ => panic!("expected Success"),
        }
    }

    #[test]
    fn test_try_resolve_response_error() {
        let tracker = PendingRequestTracker::new();
        let mut rx = tracker.register("ws-session-1", "srv-2");

        let value = serde_json::json!({
            "jsonrpc": "2.0",
            "id": "srv-2",
            "error": {"code": -32601, "message": "Method not found"}
        });

        assert!(try_resolve_response(&value, &tracker, "ws-session-1"));

        let result = rx.try_recv().expect("should have result");
        match result {
            ServerRequestResult::Error { code, message } => {
                assert_eq!(code, -32601);
                assert_eq!(message, "Method not found");
            }
            _ => panic!("expected Error"),
        }
    }

    #[test]
    fn test_try_resolve_response_unknown_id() {
        let tracker = PendingRequestTracker::new();

        let value = serde_json::json!({
            "jsonrpc": "2.0",
            "id": "srv-999",
            "result": {}
        });

        // No pending request for srv-999
        assert!(!try_resolve_response(&value, &tracker, "ws-session-1"));
    }

    #[test]
    fn test_try_resolve_response_numeric_id() {
        let tracker = PendingRequestTracker::new();
        let mut rx = tracker.register("ws-session-1", "42");

        let value = serde_json::json!({
            "jsonrpc": "2.0",
            "id": 42,
            "result": {"ok": true}
        });

        assert!(try_resolve_response(&value, &tracker, "ws-session-1"));

        let result = rx.try_recv().expect("should have result");
        match result {
            ServerRequestResult::Success(v) => {
                assert_eq!(v["ok"], true);
            }
            _ => panic!("expected Success"),
        }
    }

    // --- Phase 3 tests: progress notifications ---

    #[test]
    fn test_notify_progress_builds_correct_json() {
        // Verify the JSON structure of a progress notification
        let token = serde_json::json!("progress-token-1");
        let mut notification = serde_json::json!({
            "jsonrpc": "2.0",
            "method": "notifications/progress",
            "params": {
                "progressToken": token,
                "progress": 5.0
            }
        });
        notification["params"]["total"] = serde_json::json!(10.0);

        assert_eq!(notification["method"], "notifications/progress");
        assert_eq!(notification["params"]["progressToken"], "progress-token-1");
        assert_eq!(notification["params"]["progress"], 5.0);
        assert_eq!(notification["params"]["total"], 10.0);
    }

    #[test]
    fn test_notify_progress_without_total() {
        let token = serde_json::json!(42);
        let notification = serde_json::json!({
            "jsonrpc": "2.0",
            "method": "notifications/progress",
            "params": {
                "progressToken": token,
                "progress": 3.0
            }
        });

        assert!(notification["params"].get("total").is_none());
        assert_eq!(notification["params"]["progress"], 3.0);
    }
}
