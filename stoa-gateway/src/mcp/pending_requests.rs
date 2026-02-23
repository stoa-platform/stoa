//! MCP Pending Request Tracker (CAB-1345 Phase 2)
//!
//! Correlates server-initiated JSON-RPC requests with client responses.
//! The server sends a request (e.g., `sampling/createMessage`) over WebSocket,
//! registers a oneshot channel keyed by `(session_id, request_id)`, and waits
//! for the client to send back a response with a matching `id`.
//!
//! The WS message loop detects inbound responses (messages with `result` or
//! `error` but no `method`) and resolves them via `resolve()`.

use parking_lot::RwLock;
use serde_json::Value;
use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;
use tokio::sync::oneshot;
use tracing::{debug, warn};

/// Result of a server-initiated request to the client.
#[derive(Debug)]
pub enum ServerRequestResult {
    /// Client responded with a success result.
    Success(Value),
    /// Client responded with a JSON-RPC error.
    Error { code: i64, message: String },
    /// The request timed out waiting for a client response.
    Timeout,
}

/// Tracks pending server-initiated requests across all WebSocket sessions.
///
/// Thread-safe: uses `parking_lot::RwLock` for the map and `AtomicU64` for ID generation.
pub struct PendingRequestTracker {
    /// Maps `(session_id, request_id)` to the oneshot sender that resolves the request.
    pending: RwLock<HashMap<(String, String), oneshot::Sender<ServerRequestResult>>>,
    /// Monotonically increasing counter for generating unique server request IDs.
    next_id: AtomicU64,
}

impl PendingRequestTracker {
    pub fn new() -> Self {
        Self {
            pending: RwLock::new(HashMap::new()),
            next_id: AtomicU64::new(1),
        }
    }

    /// Generate a unique request ID for server-initiated requests.
    /// Format: `"srv-{N}"` to distinguish from client-originated IDs.
    pub fn next_request_id(&self) -> String {
        let id = self.next_id.fetch_add(1, Ordering::Relaxed);
        format!("srv-{id}")
    }

    /// Register a pending request and return a receiver that will be resolved
    /// when the client responds (or times out).
    ///
    /// Returns `(request_id, receiver)`.
    pub fn register(
        &self,
        session_id: &str,
        request_id: &str,
    ) -> oneshot::Receiver<ServerRequestResult> {
        let (tx, rx) = oneshot::channel();
        let key = (session_id.to_string(), request_id.to_string());
        self.pending.write().insert(key, tx);
        debug!(
            session_id = %session_id,
            request_id = %request_id,
            "Server request registered"
        );
        rx
    }

    /// Resolve a pending request with a client response.
    ///
    /// Called by the WS message loop when it receives a response (no `method` field).
    /// Returns `true` if the request was found and resolved.
    pub fn resolve(&self, session_id: &str, request_id: &str, result: ServerRequestResult) -> bool {
        let key = (session_id.to_string(), request_id.to_string());
        if let Some(tx) = self.pending.write().remove(&key) {
            if tx.send(result).is_err() {
                warn!(
                    session_id = %session_id,
                    request_id = %request_id,
                    "Receiver dropped before response could be delivered"
                );
            }
            true
        } else {
            debug!(
                session_id = %session_id,
                request_id = %request_id,
                "No pending request found for response"
            );
            false
        }
    }

    /// Remove all pending requests for a session (cleanup on disconnect).
    pub fn remove_session(&self, session_id: &str) {
        let mut pending = self.pending.write();
        let keys_to_remove: Vec<(String, String)> = pending
            .keys()
            .filter(|(sid, _)| sid == session_id)
            .cloned()
            .collect();

        for key in keys_to_remove {
            if let Some(tx) = pending.remove(&key) {
                let _ = tx.send(ServerRequestResult::Timeout);
            }
        }
    }

    /// Send a server-initiated JSON-RPC request and wait for the response.
    ///
    /// This is the high-level helper: generates an ID, registers the pending
    /// request, sends the JSON-RPC message over the WS channel, and awaits
    /// the response with a timeout.
    pub async fn send_request(
        &self,
        session_id: &str,
        method: &str,
        params: Option<Value>,
        ws_send: &dyn Fn(&str, &str) -> bool,
        timeout: Duration,
    ) -> ServerRequestResult {
        let request_id = self.next_request_id();

        // Build JSON-RPC request
        let mut request = serde_json::json!({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        });
        if let Some(p) = params {
            request["params"] = p;
        }
        let request_text = serde_json::to_string(&request).unwrap_or_default();

        // Register the pending request
        let rx = self.register(session_id, &request_id);

        // Send via WS channel
        if !ws_send(session_id, &request_text) {
            // Channel full or closed — remove the pending request
            self.pending
                .write()
                .remove(&(session_id.to_string(), request_id.clone()));
            return ServerRequestResult::Error {
                code: -32000,
                message: "Failed to send request to client (channel unavailable)".to_string(),
            };
        }

        debug!(
            session_id = %session_id,
            request_id = %request_id,
            method = %method,
            "Server request sent, awaiting response"
        );

        // Wait for response with timeout
        match tokio::time::timeout(timeout, rx).await {
            Ok(Ok(result)) => result,
            Ok(Err(_)) => {
                // Sender dropped (session disconnected)
                ServerRequestResult::Timeout
            }
            Err(_) => {
                // Timeout — clean up
                self.pending
                    .write()
                    .remove(&(session_id.to_string(), request_id));
                ServerRequestResult::Timeout
            }
        }
    }
}

impl Default for PendingRequestTracker {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_next_request_id_increments() {
        let tracker = PendingRequestTracker::new();
        let id1 = tracker.next_request_id();
        let id2 = tracker.next_request_id();
        assert_eq!(id1, "srv-1");
        assert_eq!(id2, "srv-2");
    }

    #[test]
    fn test_register_and_resolve_success() {
        let tracker = PendingRequestTracker::new();
        let mut rx = tracker.register("session-1", "srv-1");

        let resolved = tracker.resolve(
            "session-1",
            "srv-1",
            ServerRequestResult::Success(serde_json::json!({"content": "hello"})),
        );
        assert!(resolved);

        let result = rx.try_recv().expect("should have result");
        match result {
            ServerRequestResult::Success(v) => {
                assert_eq!(v["content"], "hello");
            }
            _ => panic!("expected Success"),
        }
    }

    #[test]
    fn test_register_and_resolve_error() {
        let tracker = PendingRequestTracker::new();
        let mut rx = tracker.register("session-1", "srv-1");

        tracker.resolve(
            "session-1",
            "srv-1",
            ServerRequestResult::Error {
                code: -32601,
                message: "Method not found".to_string(),
            },
        );

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
    fn test_resolve_unknown_request() {
        let tracker = PendingRequestTracker::new();
        let resolved = tracker.resolve(
            "no-such-session",
            "no-such-id",
            ServerRequestResult::Timeout,
        );
        assert!(!resolved);
    }

    #[test]
    fn test_remove_session_cleans_up() {
        let tracker = PendingRequestTracker::new();
        let _rx1 = tracker.register("session-1", "srv-1");
        let _rx2 = tracker.register("session-1", "srv-2");
        let _rx3 = tracker.register("session-2", "srv-3");

        tracker.remove_session("session-1");

        // session-1 requests should be removed
        assert!(!tracker.resolve("session-1", "srv-1", ServerRequestResult::Timeout));
        assert!(!tracker.resolve("session-1", "srv-2", ServerRequestResult::Timeout));
        // session-2 should still be there
        assert!(tracker.resolve("session-2", "srv-3", ServerRequestResult::Timeout));
    }

    #[tokio::test]
    async fn test_send_request_channel_failure() {
        let tracker = PendingRequestTracker::new();
        let result = tracker
            .send_request(
                "session-1",
                "sampling/createMessage",
                Some(serde_json::json!({"prompt": "test"})),
                &|_sid, _msg| false, // simulate channel failure
                Duration::from_secs(5),
            )
            .await;

        match result {
            ServerRequestResult::Error { code, .. } => {
                assert_eq!(code, -32000);
            }
            _ => panic!("expected Error for channel failure"),
        }
    }

    #[tokio::test]
    async fn test_send_request_timeout() {
        let tracker = PendingRequestTracker::new();
        let result = tracker
            .send_request(
                "session-1",
                "roots/list",
                None,
                &|_sid, _msg| true,        // simulate successful send
                Duration::from_millis(50), // very short timeout
            )
            .await;

        match result {
            ServerRequestResult::Timeout => {} // expected
            _ => panic!("expected Timeout"),
        }
    }
}
