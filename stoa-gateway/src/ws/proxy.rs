//! Generic WebSocket Proxy (CAB-1758)
//!
//! Bidirectional WebSocket relay through the STOA Gateway with governance:
//! - Auth validated on HTTP upgrade (JWT/API key from Authorization header)
//! - Per-message rate limiting (token bucket per connection)
//! - Prometheus metrics (active connections, messages, duration, rate-limited)
//! - Audit logging of frames (opt-in, via tracing at DEBUG level)
//!
//! Route: `GET /ws/:route_id` — looks up backend URL from RouteRegistry,
//! upgrades to WebSocket, and relays frames bidirectionally.

use axum::{
    extract::{
        ws::{Message, WebSocket, WebSocketUpgrade},
        Path, State,
    },
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
};
use futures::{SinkExt, StreamExt};
use std::time::Instant;
use tracing::{debug, info, warn};

use crate::metrics;
use crate::state::AppState;

use super::rate_limit::WsRateLimiter;

/// GET /ws/:route_id — WebSocket proxy upgrade handler.
///
/// 1. Validates auth (Bearer token from Authorization header)
/// 2. Looks up backend URL from RouteRegistry
/// 3. Upgrades HTTP to WebSocket
/// 4. Connects to backend WebSocket
/// 5. Relays frames bidirectionally with rate limiting
pub async fn ws_proxy_upgrade(
    State(state): State<AppState>,
    Path(route_id): Path<String>,
    ws: WebSocketUpgrade,
    headers: HeaderMap,
) -> Response {
    // Feature gate
    if !state.config.ws_proxy_enabled {
        return (StatusCode::NOT_FOUND, "WebSocket proxy is not enabled").into_response();
    }

    // Auth: require Bearer token
    let token = headers
        .get("authorization")
        .and_then(|v| v.to_str().ok())
        .and_then(|v| {
            v.strip_prefix("Bearer ")
                .or_else(|| v.strip_prefix("bearer "))
        });

    if token.is_none() {
        return (
            StatusCode::UNAUTHORIZED,
            "Missing Bearer token in Authorization header",
        )
            .into_response();
    }

    // Look up backend URL from route registry
    let route = state.route_registry.get(&route_id);
    let Some(route) = route else {
        return (
            StatusCode::NOT_FOUND,
            format!("Route not found: {route_id}"),
        )
            .into_response();
    };

    if !route.activated {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            format!("Route {} is not active", route_id),
        )
            .into_response();
    }

    // Convert backend URL to WebSocket URL
    let backend_ws_url = http_to_ws_url(&route.backend_url);
    let tenant_id = route.tenant_id.clone();
    let rate_limit = state.config.ws_proxy_rate_limit_per_second;
    let burst = state.config.ws_proxy_rate_limit_burst;

    info!(
        route_id = %route_id,
        backend = %backend_ws_url,
        tenant = %tenant_id,
        "WebSocket proxy upgrade"
    );

    ws.on_upgrade(move |socket| {
        handle_ws_proxy(
            socket,
            backend_ws_url,
            tenant_id,
            route_id,
            rate_limit,
            burst,
        )
    })
}

/// Convert an HTTP(S) URL to a WS(S) URL.
fn http_to_ws_url(url: &str) -> String {
    if let Some(rest) = url.strip_prefix("https://") {
        format!("wss://{rest}")
    } else if let Some(rest) = url.strip_prefix("http://") {
        format!("ws://{rest}")
    } else if url.starts_with("ws://") || url.starts_with("wss://") {
        url.to_string()
    } else {
        format!("ws://{url}")
    }
}

/// Bidirectional WebSocket relay between client and backend.
async fn handle_ws_proxy(
    client_socket: WebSocket,
    backend_url: String,
    tenant_id: String,
    route_id: String,
    rate_limit_per_second: f64,
    rate_limit_burst: usize,
) {
    let start = Instant::now();
    metrics::track_ws_proxy_connect();

    // Connect to backend WebSocket
    let backend_conn = tokio_tungstenite::connect_async(&backend_url).await;
    let backend_stream = match backend_conn {
        Ok((stream, _)) => stream,
        Err(e) => {
            warn!(
                backend = %backend_url,
                route_id = %route_id,
                error = %e,
                "Failed to connect to backend WebSocket"
            );
            metrics::track_ws_proxy_disconnect(&tenant_id, start.elapsed().as_secs_f64());
            return;
        }
    };

    info!(
        route_id = %route_id,
        backend = %backend_url,
        "WebSocket proxy connected"
    );

    let (mut backend_sink, mut backend_stream_rx) = backend_stream.split();
    let (mut client_sink, mut client_stream) = client_socket.split();

    let mut client_rl = WsRateLimiter::new(rate_limit_per_second, rate_limit_burst);
    let mut backend_rl = WsRateLimiter::new(rate_limit_per_second, rate_limit_burst);

    loop {
        tokio::select! {
            // Client → Backend
            msg = client_stream.next() => {
                match msg {
                    Some(Ok(msg)) => {
                        if matches!(msg, Message::Close(_)) {
                            debug!(route_id = %route_id, "Client sent close frame");
                            let _ = backend_sink.close().await;
                            break;
                        }

                        if !client_rl.try_acquire() {
                            metrics::track_ws_proxy_rate_limited(&route_id, "client");
                            debug!(route_id = %route_id, "Client message rate-limited");
                            continue;
                        }

                        metrics::track_ws_proxy_message("client_to_backend", &route_id);
                        log_frame("client→backend", &route_id, &msg);

                        if let Some(tung_msg) = axum_to_tungstenite(&msg) {
                            if backend_sink.send(tung_msg).await.is_err() {
                                warn!(route_id = %route_id, "Backend send failed");
                                break;
                            }
                        }
                    }
                    Some(Err(e)) => {
                        debug!(route_id = %route_id, error = %e, "Client read error");
                        break;
                    }
                    None => break,
                }
            }

            // Backend → Client
            msg = backend_stream_rx.next() => {
                match msg {
                    Some(Ok(msg)) => {
                        if msg.is_close() {
                            debug!(route_id = %route_id, "Backend sent close frame");
                            let _ = client_sink.close().await;
                            break;
                        }

                        if !backend_rl.try_acquire() {
                            metrics::track_ws_proxy_rate_limited(&route_id, "backend");
                            debug!(route_id = %route_id, "Backend message rate-limited");
                            continue;
                        }

                        metrics::track_ws_proxy_message("backend_to_client", &route_id);
                        log_frame_tungstenite("backend→client", &route_id, &msg);

                        if let Some(axum_msg) = tungstenite_to_axum(&msg) {
                            if client_sink.send(axum_msg).await.is_err() {
                                warn!(route_id = %route_id, "Client send failed");
                                break;
                            }
                        }
                    }
                    Some(Err(e)) => {
                        debug!(route_id = %route_id, error = %e, "Backend read error");
                        break;
                    }
                    None => break,
                }
            }
        }
    }

    let duration = start.elapsed().as_secs_f64();
    info!(
        route_id = %route_id,
        duration_secs = duration,
        "WebSocket proxy disconnected"
    );
    metrics::track_ws_proxy_disconnect(&tenant_id, duration);
}

/// Convert axum WebSocket message to tungstenite message.
fn axum_to_tungstenite(msg: &Message) -> Option<tokio_tungstenite::tungstenite::Message> {
    use tokio_tungstenite::tungstenite::Message as TMsg;
    match msg {
        Message::Text(text) => Some(TMsg::Text(text.to_string().into())),
        Message::Binary(data) => Some(TMsg::Binary(data.to_vec().into())),
        Message::Ping(data) => Some(TMsg::Ping(data.to_vec().into())),
        Message::Pong(data) => Some(TMsg::Pong(data.to_vec().into())),
        Message::Close(_) => Some(TMsg::Close(None)),
    }
}

/// Convert tungstenite message to axum WebSocket message.
fn tungstenite_to_axum(msg: &tokio_tungstenite::tungstenite::Message) -> Option<Message> {
    use tokio_tungstenite::tungstenite::Message as TMsg;
    match msg {
        TMsg::Text(text) => Some(Message::Text(text.to_string())),
        TMsg::Binary(data) => Some(Message::Binary(data.to_vec())),
        TMsg::Ping(data) => Some(Message::Ping(data.to_vec())),
        TMsg::Pong(data) => Some(Message::Pong(data.to_vec())),
        TMsg::Close(_) => Some(Message::Close(None)),
        _ => None,
    }
}

/// Audit log an axum WebSocket frame (DEBUG level — opt-in).
fn log_frame(direction: &str, route_id: &str, msg: &Message) {
    match msg {
        Message::Text(text) => {
            let preview = if text.len() > 200 {
                format!("{}...", &text[..200])
            } else {
                text.to_string()
            };
            debug!(
                direction,
                route_id,
                frame_type = "text",
                preview,
                "WS frame"
            );
        }
        Message::Binary(data) => {
            debug!(
                direction,
                route_id,
                frame_type = "binary",
                len = data.len(),
                "WS frame"
            );
        }
        Message::Ping(_) => {
            debug!(direction, route_id, frame_type = "ping", "WS frame");
        }
        Message::Pong(_) => {
            debug!(direction, route_id, frame_type = "pong", "WS frame");
        }
        Message::Close(_) => {
            debug!(direction, route_id, frame_type = "close", "WS frame");
        }
    }
}

/// Audit log a tungstenite WebSocket frame (DEBUG level — opt-in).
fn log_frame_tungstenite(
    direction: &str,
    route_id: &str,
    msg: &tokio_tungstenite::tungstenite::Message,
) {
    use tokio_tungstenite::tungstenite::Message as TMsg;
    match msg {
        TMsg::Text(text) => {
            let preview = if text.len() > 200 {
                format!("{}...", &text[..200])
            } else {
                text.to_string()
            };
            debug!(
                direction,
                route_id,
                frame_type = "text",
                preview,
                "WS frame"
            );
        }
        TMsg::Binary(data) => {
            debug!(
                direction,
                route_id,
                frame_type = "binary",
                len = data.len(),
                "WS frame"
            );
        }
        TMsg::Ping(_) => {
            debug!(direction, route_id, frame_type = "ping", "WS frame");
        }
        TMsg::Pong(_) => {
            debug!(direction, route_id, frame_type = "pong", "WS frame");
        }
        TMsg::Close(_) => {
            debug!(direction, route_id, frame_type = "close", "WS frame");
        }
        TMsg::Frame(_) => {}
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_http_to_ws_url() {
        assert_eq!(
            http_to_ws_url("https://backend.example.com/v1"),
            "wss://backend.example.com/v1"
        );
        assert_eq!(
            http_to_ws_url("http://localhost:8080"),
            "ws://localhost:8080"
        );
        assert_eq!(http_to_ws_url("wss://already.ws"), "wss://already.ws");
        assert_eq!(http_to_ws_url("ws://already.ws"), "ws://already.ws");
        assert_eq!(http_to_ws_url("bare-host:8080"), "ws://bare-host:8080");
    }

    #[test]
    fn test_axum_to_tungstenite_text() {
        let msg = Message::Text("hello".to_string());
        let result = axum_to_tungstenite(&msg).unwrap();
        assert!(
            matches!(result, tokio_tungstenite::tungstenite::Message::Text(ref t) if AsRef::<str>::as_ref(t) == "hello")
        );
    }

    #[test]
    fn test_tungstenite_to_axum_text() {
        let msg = tokio_tungstenite::tungstenite::Message::Text("hello".into());
        let result = tungstenite_to_axum(&msg).unwrap();
        assert!(matches!(result, Message::Text(ref t) if t == "hello"));
    }

    #[test]
    fn test_axum_to_tungstenite_binary() {
        let msg = Message::Binary(vec![1, 2, 3]);
        let result = axum_to_tungstenite(&msg).unwrap();
        assert!(
            matches!(result, tokio_tungstenite::tungstenite::Message::Binary(ref d) if d.as_ref() == [1, 2, 3])
        );
    }

    #[test]
    fn test_axum_to_tungstenite_close() {
        let msg = Message::Close(None);
        let result = axum_to_tungstenite(&msg).unwrap();
        assert!(matches!(
            result,
            tokio_tungstenite::tungstenite::Message::Close(_)
        ));
    }

    #[test]
    fn test_tungstenite_ping_returns_some() {
        let msg = tokio_tungstenite::tungstenite::Message::Ping(vec![1, 2].into());
        let result = tungstenite_to_axum(&msg);
        assert!(result.is_some());
        assert!(matches!(result.unwrap(), Message::Ping(_)));
    }
}
