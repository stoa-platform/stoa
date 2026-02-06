//! MCP Elicitation Support (MCP 2025-03-26)
//!
//! Server-initiated prompts for user input during tool execution.
//! Enables tools to request additional information from users when needed.
//!
//! Note: Types are defined for protocol compliance. Actual usage in tools
//! is a future enhancement.

// Elicitation types are prepared for future tool integration
#![allow(dead_code)]
//!
//! # Protocol Flow
//!
//! 1. Server sends `elicitation/create` with message and schema
//! 2. Client shows prompt to user
//! 3. User responds (accept with data) or declines
//! 4. Client sends `elicitation/response` with result
//! 5. Tool execution continues with user's input
//!
//! # Example
//!
//! ```json
//! // Server → Client
//! {
//!   "jsonrpc": "2.0",
//!   "method": "elicitation/create",
//!   "params": {
//!     "message": "Which environment should we deploy to?",
//!     "requestedSchema": {
//!       "type": "object",
//!       "properties": {
//!         "environment": {
//!           "type": "string",
//!           "enum": ["dev", "staging", "prod"]
//!         }
//!       },
//!       "required": ["environment"]
//!     }
//!   },
//!   "id": "elicit-1"
//! }
//!
//! // Client → Server
//! {
//!   "jsonrpc": "2.0",
//!   "result": {
//!     "action": "accept",
//!     "content": { "environment": "staging" }
//!   },
//!   "id": "elicit-1"
//! }
//! ```

use serde::{Deserialize, Serialize};
use serde_json::Value;
use uuid::Uuid;

/// Elicitation request sent from server to client
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ElicitationRequest {
    /// Unique ID for this elicitation request
    pub id: String,

    /// Human-readable message explaining what input is needed
    pub message: String,

    /// JSON Schema describing the expected response structure
    pub requested_schema: Value,

    /// Optional title for the prompt dialog
    #[serde(skip_serializing_if = "Option::is_none")]
    pub title: Option<String>,

    /// Optional hint about urgency/importance
    #[serde(skip_serializing_if = "Option::is_none")]
    pub priority: Option<ElicitationPriority>,
}

impl ElicitationRequest {
    /// Create a new elicitation request
    pub fn new(message: impl Into<String>, schema: Value) -> Self {
        Self {
            id: Uuid::new_v4().to_string(),
            message: message.into(),
            requested_schema: schema,
            title: None,
            priority: None,
        }
    }

    /// Add a title to the request
    pub fn with_title(mut self, title: impl Into<String>) -> Self {
        self.title = Some(title.into());
        self
    }

    /// Set priority
    pub fn with_priority(mut self, priority: ElicitationPriority) -> Self {
        self.priority = Some(priority);
        self
    }
}

/// Priority hint for elicitation requests
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ElicitationPriority {
    /// Low priority - can be deferred
    Low,
    /// Normal priority (default)
    #[default]
    Normal,
    /// High priority - needs attention soon
    High,
    /// Critical - blocking operation
    Critical,
}

/// User's response to an elicitation request
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ElicitationResponse {
    /// The action taken by the user
    pub action: ElicitationAction,

    /// Response content (present when action is Accept)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub content: Option<Value>,

    /// Optional reason for declining
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
}

impl ElicitationResponse {
    /// Create an accept response with content
    pub fn accept(content: Value) -> Self {
        Self {
            action: ElicitationAction::Accept,
            content: Some(content),
            reason: None,
        }
    }

    /// Create a decline response
    pub fn decline(reason: Option<String>) -> Self {
        Self {
            action: ElicitationAction::Decline,
            content: None,
            reason,
        }
    }
}

/// Action taken by user on elicitation
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ElicitationAction {
    /// User accepted and provided data
    Accept,
    /// User declined the request
    Decline,
}

/// Pending elicitation stored in session
#[derive(Debug, Clone)]
pub struct PendingElicitation {
    /// The original request
    pub request: ElicitationRequest,
    /// Timestamp when created
    pub created_at: chrono::DateTime<chrono::Utc>,
}

impl PendingElicitation {
    /// Create a new pending elicitation
    pub fn new(request: ElicitationRequest) -> Self {
        Self {
            request,
            created_at: chrono::Utc::now(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_elicitation_request_serialization() {
        let request = ElicitationRequest::new(
            "Which environment?",
            json!({
                "type": "object",
                "properties": {
                    "env": { "type": "string", "enum": ["dev", "staging", "prod"] }
                },
                "required": ["env"]
            }),
        )
        .with_title("Deploy Confirmation");

        let json = serde_json::to_value(&request).unwrap();
        assert_eq!(json["message"], "Which environment?");
        assert_eq!(json["title"], "Deploy Confirmation");
        assert!(json["requestedSchema"].is_object());
    }

    #[test]
    fn test_elicitation_response_accept() {
        let response = ElicitationResponse::accept(json!({ "env": "staging" }));

        let json = serde_json::to_value(&response).unwrap();
        assert_eq!(json["action"], "accept");
        assert_eq!(json["content"]["env"], "staging");
    }

    #[test]
    fn test_elicitation_response_decline() {
        let response = ElicitationResponse::decline(Some("User cancelled".into()));

        let json = serde_json::to_value(&response).unwrap();
        assert_eq!(json["action"], "decline");
        assert_eq!(json["reason"], "User cancelled");
        assert!(json.get("content").is_none());
    }

    #[test]
    fn test_elicitation_action_serialization() {
        assert_eq!(
            serde_json::to_string(&ElicitationAction::Accept).unwrap(),
            "\"accept\""
        );
        assert_eq!(
            serde_json::to_string(&ElicitationAction::Decline).unwrap(),
            "\"decline\""
        );
    }

    #[test]
    fn test_elicitation_priority() {
        let request = ElicitationRequest::new("Confirm?", json!({}))
            .with_priority(ElicitationPriority::Critical);

        let json = serde_json::to_value(&request).unwrap();
        assert_eq!(json["priority"], "critical");
    }
}
