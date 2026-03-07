//! HEGEMON Inter-Agent Messaging — In-memory inbox per agent.
//!
//! Agents communicate through the gateway via simple message passing.
//! Each agent has a ring-buffer inbox (default 100 messages, 24h TTL).
//!
//! Part of CAB-1709 Phase 6.

use std::collections::HashMap;
use std::collections::VecDeque;

use axum::extract::{Path, Query, State};
use axum::http::StatusCode;
use axum::response::IntoResponse;
use axum::Json;
use parking_lot::RwLock;
use serde::{Deserialize, Serialize};

// =============================================================================
// Configuration
// =============================================================================

/// Maximum messages per agent inbox.
const DEFAULT_INBOX_CAPACITY: usize = 100;

/// Message TTL in seconds (24 hours).
const MESSAGE_TTL_SECS: i64 = 86400;

// =============================================================================
// Message Types
// =============================================================================

/// A single inter-agent message.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentMessage {
    /// Unique message ID (auto-generated).
    pub id: String,
    /// Sender agent name.
    pub from: String,
    /// Recipient agent name.
    pub to: String,
    /// Message subject (optional).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub subject: Option<String>,
    /// Message body.
    pub body: String,
    /// ISO 8601 timestamp.
    pub timestamp: String,
    /// Whether the message has been read.
    pub read: bool,
}

impl AgentMessage {
    fn new(from: &str, to: &str, subject: Option<String>, body: &str) -> Self {
        Self {
            id: format!(
                "msg-{}-{}",
                chrono::Utc::now().timestamp_millis(),
                &uuid_fragment()
            ),
            from: from.to_string(),
            to: to.to_string(),
            subject,
            body: body.to_string(),
            timestamp: chrono::Utc::now().to_rfc3339(),
            read: false,
        }
    }

    /// Check if message has expired (older than TTL).
    fn is_expired(&self) -> bool {
        if let Ok(ts) = chrono::DateTime::parse_from_rfc3339(&self.timestamp) {
            let age = chrono::Utc::now().signed_duration_since(ts);
            age.num_seconds() > MESSAGE_TTL_SECS
        } else {
            false
        }
    }
}

/// Generate a short random fragment for message IDs.
fn uuid_fragment() -> String {
    use std::time::SystemTime;
    let nanos = SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .unwrap_or_default()
        .subsec_nanos();
    format!("{:08x}", nanos)
}

// =============================================================================
// Agent Inbox
// =============================================================================

/// Per-agent inbox with ring buffer semantics.
struct AgentInbox {
    messages: VecDeque<AgentMessage>,
    capacity: usize,
}

impl AgentInbox {
    fn new() -> Self {
        Self {
            messages: VecDeque::with_capacity(DEFAULT_INBOX_CAPACITY),
            capacity: DEFAULT_INBOX_CAPACITY,
        }
    }

    /// Push a message, evicting oldest if at capacity. Also evicts expired messages.
    fn push(&mut self, msg: AgentMessage) {
        // Evict expired messages first
        self.messages.retain(|m| !m.is_expired());
        // Then evict oldest if still at capacity
        if self.messages.len() >= self.capacity {
            self.messages.pop_front();
        }
        self.messages.push_back(msg);
    }

    /// Get all non-expired messages, optionally only unread.
    fn list(&self, unread_only: bool) -> Vec<AgentMessage> {
        self.messages
            .iter()
            .filter(|m| !m.is_expired())
            .filter(|m| !unread_only || !m.read)
            .cloned()
            .collect()
    }

    /// Mark a message as read by ID. Returns true if found.
    fn mark_read(&mut self, message_id: &str) -> bool {
        for msg in &mut self.messages {
            if msg.id == message_id {
                msg.read = true;
                return true;
            }
        }
        false
    }

    /// Mark all messages as read. Returns count of newly marked.
    fn mark_all_read(&mut self) -> usize {
        let mut count = 0;
        for msg in &mut self.messages {
            if !msg.read {
                msg.read = true;
                count += 1;
            }
        }
        count
    }

    /// Count of non-expired unread messages.
    fn unread_count(&self) -> usize {
        self.messages
            .iter()
            .filter(|m| !m.is_expired() && !m.read)
            .count()
    }

    /// Total non-expired message count.
    fn count(&self) -> usize {
        self.messages.iter().filter(|m| !m.is_expired()).count()
    }
}

// =============================================================================
// Message Hub
// =============================================================================

/// Central message hub managing all agent inboxes.
///
/// Thread-safe via `parking_lot::RwLock`.
pub struct MessageHub {
    inboxes: RwLock<HashMap<String, AgentInbox>>,
}

impl Default for MessageHub {
    fn default() -> Self {
        Self::new()
    }
}

impl MessageHub {
    pub fn new() -> Self {
        Self {
            inboxes: RwLock::new(HashMap::new()),
        }
    }

    /// Send a message from one agent to another.
    pub fn send(&self, from: &str, to: &str, subject: Option<String>, body: &str) -> AgentMessage {
        let msg = AgentMessage::new(from, to, subject, body);
        let mut inboxes = self.inboxes.write();
        let inbox = inboxes
            .entry(to.to_string())
            .or_insert_with(AgentInbox::new);
        inbox.push(msg.clone());
        msg
    }

    /// Get messages for an agent.
    pub fn inbox(&self, agent_name: &str, unread_only: bool) -> Vec<AgentMessage> {
        let inboxes = self.inboxes.read();
        match inboxes.get(agent_name) {
            Some(inbox) => inbox.list(unread_only),
            None => vec![],
        }
    }

    /// Mark a specific message as read.
    pub fn mark_read(&self, agent_name: &str, message_id: &str) -> bool {
        let mut inboxes = self.inboxes.write();
        if let Some(inbox) = inboxes.get_mut(agent_name) {
            inbox.mark_read(message_id)
        } else {
            false
        }
    }

    /// Mark all messages for an agent as read.
    pub fn mark_all_read(&self, agent_name: &str) -> usize {
        let mut inboxes = self.inboxes.write();
        if let Some(inbox) = inboxes.get_mut(agent_name) {
            inbox.mark_all_read()
        } else {
            0
        }
    }

    /// Get inbox summary for all agents (for admin).
    pub fn summaries(&self) -> Vec<InboxSummary> {
        let inboxes = self.inboxes.read();
        let mut result: Vec<_> = inboxes
            .iter()
            .map(|(name, inbox)| InboxSummary {
                agent_name: name.clone(),
                total: inbox.count(),
                unread: inbox.unread_count(),
            })
            .collect();
        result.sort_by(|a, b| a.agent_name.cmp(&b.agent_name));
        result
    }

    /// Get total number of agents with inboxes.
    pub fn agent_count(&self) -> usize {
        self.inboxes.read().len()
    }
}

// =============================================================================
// API Types
// =============================================================================

/// Summary of an agent's inbox.
#[derive(Debug, Serialize)]
pub struct InboxSummary {
    pub agent_name: String,
    pub total: usize,
    pub unread: usize,
}

/// Request body for sending a message.
#[derive(Debug, Deserialize)]
pub struct SendMessageRequest {
    pub from: String,
    pub to: String,
    #[serde(default)]
    pub subject: Option<String>,
    pub body: String,
}

/// Query params for inbox listing.
#[derive(Debug, Deserialize)]
pub struct InboxQuery {
    #[serde(default)]
    pub unread_only: Option<bool>,
}

/// Request body for marking a message as read.
#[derive(Debug, Deserialize)]
pub struct MarkReadRequest {
    pub message_id: String,
}

#[derive(Serialize)]
struct ErrorResponse {
    error: String,
    message: String,
}

#[derive(Serialize)]
struct SendResponse {
    message: AgentMessage,
    status: String,
}

#[derive(Serialize)]
struct InboxResponse {
    agent_name: String,
    messages: Vec<AgentMessage>,
    count: usize,
    unread: usize,
}

#[derive(Serialize)]
struct MarkReadResponse {
    message_id: String,
    marked: bool,
}

#[derive(Serialize)]
struct MarkAllReadResponse {
    agent_name: String,
    marked_count: usize,
}

#[derive(Serialize)]
struct AdminListResponse {
    inboxes: Vec<InboxSummary>,
    count: usize,
}

// =============================================================================
// Handlers — Agent-facing (non-admin)
// =============================================================================

/// `POST /hegemon/messages` — send a message to another agent.
pub async fn send_message(
    State(state): State<crate::state::AppState>,
    Json(body): Json<SendMessageRequest>,
) -> impl IntoResponse {
    let Some(ref heg) = state.hegemon else {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(ErrorResponse {
                error: "hegemon_disabled".to_string(),
                message: "HEGEMON module is not enabled".to_string(),
            }),
        )
            .into_response();
    };

    if body.from.is_empty() || body.to.is_empty() || body.body.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(ErrorResponse {
                error: "invalid_request".to_string(),
                message: "from, to, and body are required".to_string(),
            }),
        )
            .into_response();
    }

    if body.from == body.to {
        return (
            StatusCode::BAD_REQUEST,
            Json(ErrorResponse {
                error: "invalid_request".to_string(),
                message: "Cannot send a message to yourself".to_string(),
            }),
        )
            .into_response();
    }

    let msg = heg
        .message_hub
        .send(&body.from, &body.to, body.subject, &body.body);

    Json(SendResponse {
        message: msg,
        status: "delivered".to_string(),
    })
    .into_response()
}

/// `GET /hegemon/messages/:agent_name` — get inbox for an agent.
pub async fn get_inbox(
    State(state): State<crate::state::AppState>,
    Path(agent_name): Path<String>,
    Query(query): Query<InboxQuery>,
) -> impl IntoResponse {
    let Some(ref heg) = state.hegemon else {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(ErrorResponse {
                error: "hegemon_disabled".to_string(),
                message: "HEGEMON module is not enabled".to_string(),
            }),
        )
            .into_response();
    };

    let unread_only = query.unread_only.unwrap_or(false);
    let messages = heg.message_hub.inbox(&agent_name, unread_only);
    let unread = messages.iter().filter(|m| !m.read).count();
    let count = messages.len();

    Json(InboxResponse {
        agent_name,
        messages,
        count,
        unread,
    })
    .into_response()
}

/// `POST /hegemon/messages/:agent_name/read` — mark a message as read.
pub async fn mark_message_read(
    State(state): State<crate::state::AppState>,
    Path(agent_name): Path<String>,
    Json(body): Json<MarkReadRequest>,
) -> impl IntoResponse {
    let Some(ref heg) = state.hegemon else {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(ErrorResponse {
                error: "hegemon_disabled".to_string(),
                message: "HEGEMON module is not enabled".to_string(),
            }),
        )
            .into_response();
    };

    let marked = heg.message_hub.mark_read(&agent_name, &body.message_id);

    if marked {
        Json(MarkReadResponse {
            message_id: body.message_id,
            marked: true,
        })
        .into_response()
    } else {
        (
            StatusCode::NOT_FOUND,
            Json(ErrorResponse {
                error: "message_not_found".to_string(),
                message: format!(
                    "Message '{}' not found in {}'s inbox",
                    body.message_id, agent_name
                ),
            }),
        )
            .into_response()
    }
}

/// `POST /hegemon/messages/:agent_name/read-all` — mark all messages as read.
pub async fn mark_all_messages_read(
    State(state): State<crate::state::AppState>,
    Path(agent_name): Path<String>,
) -> impl IntoResponse {
    let Some(ref heg) = state.hegemon else {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(ErrorResponse {
                error: "hegemon_disabled".to_string(),
                message: "HEGEMON module is not enabled".to_string(),
            }),
        )
            .into_response();
    };

    let count = heg.message_hub.mark_all_read(&agent_name);

    Json(MarkAllReadResponse {
        agent_name,
        marked_count: count,
    })
    .into_response()
}

// =============================================================================
// Handlers — Admin
// =============================================================================

/// `GET /admin/hegemon/messages` — list all agent inboxes (admin).
pub async fn list_inboxes(State(state): State<crate::state::AppState>) -> impl IntoResponse {
    match &state.hegemon {
        Some(heg) => {
            let inboxes = heg.message_hub.summaries();
            let count = inboxes.len();
            Json(AdminListResponse { inboxes, count }).into_response()
        }
        None => (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(ErrorResponse {
                error: "hegemon_disabled".to_string(),
                message: "HEGEMON module is not enabled".to_string(),
            }),
        )
            .into_response(),
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_send_message() {
        let hub = MessageHub::new();
        let msg = hub.send("worker-1", "worker-2", None, "hello");
        assert_eq!(msg.from, "worker-1");
        assert_eq!(msg.to, "worker-2");
        assert_eq!(msg.body, "hello");
        assert!(!msg.read);
        assert!(msg.id.starts_with("msg-"));
    }

    #[test]
    fn test_send_message_with_subject() {
        let hub = MessageHub::new();
        let msg = hub.send(
            "worker-1",
            "worker-2",
            Some("Phase 2 status".to_string()),
            "Phase 2 complete",
        );
        assert_eq!(msg.subject, Some("Phase 2 status".to_string()));
    }

    #[test]
    fn test_inbox_retrieval() {
        let hub = MessageHub::new();
        hub.send("worker-1", "worker-2", None, "msg 1");
        hub.send("worker-3", "worker-2", None, "msg 2");
        hub.send("worker-1", "worker-3", None, "msg 3");

        let inbox = hub.inbox("worker-2", false);
        assert_eq!(inbox.len(), 2);
        assert_eq!(inbox[0].body, "msg 1");
        assert_eq!(inbox[1].body, "msg 2");
    }

    #[test]
    fn test_inbox_unread_only() {
        let hub = MessageHub::new();
        hub.send("worker-1", "worker-2", None, "msg 1");
        hub.send("worker-1", "worker-2", None, "msg 2");

        // Mark first as read
        let msgs = hub.inbox("worker-2", false);
        hub.mark_read("worker-2", &msgs[0].id);

        let unread = hub.inbox("worker-2", true);
        assert_eq!(unread.len(), 1);
        assert_eq!(unread[0].body, "msg 2");
    }

    #[test]
    fn test_empty_inbox() {
        let hub = MessageHub::new();
        let inbox = hub.inbox("nonexistent", false);
        assert!(inbox.is_empty());
    }

    #[test]
    fn test_mark_read() {
        let hub = MessageHub::new();
        let msg = hub.send("worker-1", "worker-2", None, "hello");

        assert!(hub.mark_read("worker-2", &msg.id));
        let inbox = hub.inbox("worker-2", false);
        assert!(inbox[0].read);
    }

    #[test]
    fn test_mark_read_nonexistent() {
        let hub = MessageHub::new();
        assert!(!hub.mark_read("worker-1", "nonexistent-id"));
    }

    #[test]
    fn test_mark_all_read() {
        let hub = MessageHub::new();
        hub.send("worker-1", "worker-2", None, "msg 1");
        hub.send("worker-3", "worker-2", None, "msg 2");
        hub.send("worker-1", "worker-2", None, "msg 3");

        let count = hub.mark_all_read("worker-2");
        assert_eq!(count, 3);

        let unread = hub.inbox("worker-2", true);
        assert!(unread.is_empty());
    }

    #[test]
    fn test_mark_all_read_empty_inbox() {
        let hub = MessageHub::new();
        let count = hub.mark_all_read("nonexistent");
        assert_eq!(count, 0);
    }

    #[test]
    fn test_inbox_capacity_eviction() {
        let hub = MessageHub::new();
        // Send more than DEFAULT_INBOX_CAPACITY messages
        for i in 0..110 {
            hub.send("worker-1", "worker-2", None, &format!("msg {i}"));
        }

        let inbox = hub.inbox("worker-2", false);
        // Should have at most DEFAULT_INBOX_CAPACITY
        assert!(inbox.len() <= DEFAULT_INBOX_CAPACITY);
        // Oldest messages evicted — first message should be msg 10
        assert_eq!(inbox[0].body, "msg 10");
    }

    #[test]
    fn test_summaries() {
        let hub = MessageHub::new();
        hub.send("worker-1", "worker-a", None, "msg 1");
        hub.send("worker-1", "worker-b", None, "msg 2");
        hub.send("worker-1", "worker-b", None, "msg 3");

        // Mark one as read
        let msgs = hub.inbox("worker-b", false);
        hub.mark_read("worker-b", &msgs[0].id);

        let summaries = hub.summaries();
        assert_eq!(summaries.len(), 2);
        // Sorted by name
        assert_eq!(summaries[0].agent_name, "worker-a");
        assert_eq!(summaries[0].total, 1);
        assert_eq!(summaries[0].unread, 1);
        assert_eq!(summaries[1].agent_name, "worker-b");
        assert_eq!(summaries[1].total, 2);
        assert_eq!(summaries[1].unread, 1);
    }

    #[test]
    fn test_agent_count() {
        let hub = MessageHub::new();
        assert_eq!(hub.agent_count(), 0);
        hub.send("w1", "w2", None, "hello");
        assert_eq!(hub.agent_count(), 1);
        hub.send("w1", "w3", None, "hello");
        assert_eq!(hub.agent_count(), 2);
    }

    #[test]
    fn test_message_expiry() {
        let hub = MessageHub::new();

        // Create a message with a timestamp far in the past
        let mut msg = AgentMessage::new("worker-1", "worker-2", None, "old message");
        msg.timestamp = "2020-01-01T00:00:00+00:00".to_string();

        // Manually push to inbox
        {
            let mut inboxes = hub.inboxes.write();
            let inbox = inboxes
                .entry("worker-2".to_string())
                .or_insert_with(AgentInbox::new);
            inbox.messages.push_back(msg);
        }

        // Should be filtered out (expired)
        let inbox = hub.inbox("worker-2", false);
        assert!(inbox.is_empty());
    }

    #[test]
    fn test_concurrent_sends() {
        let hub = std::sync::Arc::new(MessageHub::new());
        let mut handles = vec![];

        for i in 0..10 {
            let h = hub.clone();
            handles.push(std::thread::spawn(move || {
                for j in 0..20 {
                    h.send(
                        &format!("sender-{i}"),
                        "receiver",
                        None,
                        &format!("msg-{i}-{j}"),
                    );
                }
            }));
        }

        for handle in handles {
            handle.join().expect("thread join");
        }

        let inbox = hub.inbox("receiver", false);
        // 200 messages sent, capacity 100 — should have exactly 100
        assert_eq!(inbox.len(), DEFAULT_INBOX_CAPACITY);
    }

    #[test]
    fn test_message_id_uniqueness() {
        let hub = MessageHub::new();
        let msg1 = hub.send("w1", "w2", None, "a");
        let msg2 = hub.send("w1", "w2", None, "b");
        assert_ne!(msg1.id, msg2.id);
    }

    #[test]
    fn test_message_serialization() {
        let msg = AgentMessage::new("worker-1", "worker-2", Some("test".to_string()), "body");
        let json = serde_json::to_string(&msg).expect("serialize");
        assert!(json.contains("\"worker-1\""));
        assert!(json.contains("\"worker-2\""));
        assert!(json.contains("\"test\""));
        assert!(json.contains("\"body\""));
        assert!(json.contains("\"read\":false"));
    }

    #[test]
    fn test_message_without_subject_skips_field() {
        let msg = AgentMessage::new("w1", "w2", None, "body");
        let json = serde_json::to_string(&msg).expect("serialize");
        // subject should not appear when None (skip_serializing_if)
        assert!(!json.contains("subject"));
    }
}
