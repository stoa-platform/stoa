//! A2A Protocol Types (CAB-1754)
//!
//! Based on the A2A specification: <https://github.com/google/A2A>
//! JSON-RPC 2.0 based inter-agent communication protocol.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// ─── Agent Card (/.well-known/agent.json) ───

/// Agent Card — describes an agent's capabilities for discovery.
/// Served at `/.well-known/agent.json` per the A2A spec.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AgentCard {
    /// Human-readable agent name
    pub name: String,
    /// Brief description of the agent's purpose
    pub description: String,
    /// URL of this agent's A2A endpoint
    pub url: String,
    /// A2A protocol version supported
    pub protocol_version: String,
    /// Capabilities this agent offers
    pub capabilities: AgentCapabilities,
    /// Authentication requirements
    #[serde(skip_serializing_if = "Option::is_none")]
    pub authentication: Option<AgentAuthentication>,
    /// Skills (high-level capabilities) the agent provides
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub skills: Vec<AgentSkill>,
    /// Provider information
    #[serde(skip_serializing_if = "Option::is_none")]
    pub provider: Option<AgentProvider>,
}

/// Agent capabilities declaration
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AgentCapabilities {
    /// Whether the agent supports streaming responses
    #[serde(default)]
    pub streaming: bool,
    /// Whether the agent can push notifications
    #[serde(default)]
    pub push_notifications: bool,
    /// Whether the agent maintains state across tasks
    #[serde(default)]
    pub state_transition_history: bool,
}

/// Authentication requirements for interacting with the agent
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AgentAuthentication {
    /// Supported authentication schemes (e.g., "bearer", "apiKey", "oauth2")
    pub schemes: Vec<String>,
    /// Credentials (optional, for public agents)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub credentials: Option<String>,
}

/// A skill represents a high-level capability the agent can perform
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AgentSkill {
    /// Unique identifier for this skill
    pub id: String,
    /// Human-readable name
    pub name: String,
    /// Detailed description
    pub description: String,
    /// Example prompts / input patterns
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub tags: Vec<String>,
    /// Example inputs
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub examples: Vec<String>,
    /// Input modes (text, file, data)
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub input_modes: Vec<String>,
    /// Output modes (text, file, data)
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub output_modes: Vec<String>,
}

/// Provider information
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentProvider {
    /// Organization name
    pub organization: String,
    /// Contact URL
    #[serde(skip_serializing_if = "Option::is_none")]
    pub url: Option<String>,
}

// ─── JSON-RPC 2.0 Protocol ───

/// JSON-RPC 2.0 Request
#[derive(Debug, Clone, Deserialize)]
pub struct JsonRpcRequest {
    pub jsonrpc: String,
    pub method: String,
    #[serde(default)]
    pub params: serde_json::Value,
    pub id: serde_json::Value,
}

/// JSON-RPC 2.0 Response
#[derive(Debug, Clone, Serialize)]
pub struct JsonRpcResponse {
    pub jsonrpc: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<JsonRpcError>,
    pub id: serde_json::Value,
}

/// JSON-RPC 2.0 Error
#[derive(Debug, Clone, Serialize)]
pub struct JsonRpcError {
    pub code: i32,
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub data: Option<serde_json::Value>,
}

impl JsonRpcResponse {
    pub fn success(id: serde_json::Value, result: serde_json::Value) -> Self {
        Self {
            jsonrpc: "2.0".to_string(),
            result: Some(result),
            error: None,
            id,
        }
    }

    pub fn error(id: serde_json::Value, code: i32, message: impl Into<String>) -> Self {
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

// ─── A2A Task Types ───

/// Task state machine: submitted → working → completed | failed | canceled
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum TaskState {
    Submitted,
    Working,
    InputRequired,
    Completed,
    Failed,
    Canceled,
}

/// A task represents a unit of work sent to an agent
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Task {
    /// Unique task identifier
    pub id: String,
    /// Optional session ID for multi-turn conversations
    #[serde(skip_serializing_if = "Option::is_none")]
    pub session_id: Option<String>,
    /// Current task status
    pub status: TaskStatus,
    /// Conversation history (input + output messages)
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub history: Vec<Message>,
    /// Task artifacts (generated outputs)
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub artifacts: Vec<Artifact>,
    /// Task metadata
    #[serde(default, skip_serializing_if = "HashMap::is_empty")]
    pub metadata: HashMap<String, serde_json::Value>,
}

/// Task status with optional message
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskStatus {
    pub state: TaskState,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message: Option<Message>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub timestamp: Option<String>,
}

/// A message in the A2A protocol (user or agent)
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Message {
    /// Message role: "user" or "agent"
    pub role: MessageRole,
    /// Message parts (text, file, data)
    pub parts: Vec<Part>,
    /// Optional metadata
    #[serde(default, skip_serializing_if = "HashMap::is_empty")]
    pub metadata: HashMap<String, serde_json::Value>,
}

/// Message role
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum MessageRole {
    User,
    Agent,
}

/// Part types for message content
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "camelCase")]
pub enum Part {
    /// Text content
    #[serde(rename = "text")]
    Text { text: String },
    /// File reference
    #[serde(rename = "file")]
    File { file: FileContent },
    /// Structured data
    #[serde(rename = "data")]
    Data { data: serde_json::Value },
}

/// File content — either inline bytes or a URI reference
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FileContent {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub mime_type: Option<String>,
    /// Base64-encoded file bytes (inline)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub bytes: Option<String>,
    /// URI reference (remote)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub uri: Option<String>,
}

/// Artifact — a generated output from the agent
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Artifact {
    /// Artifact name
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    /// Artifact description
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    /// Artifact parts (text, file, data)
    pub parts: Vec<Part>,
    /// Optional index for ordering
    #[serde(skip_serializing_if = "Option::is_none")]
    pub index: Option<u32>,
    /// Whether this is the last chunk (streaming)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_chunk: Option<bool>,
    /// Metadata
    #[serde(default, skip_serializing_if = "HashMap::is_empty")]
    pub metadata: HashMap<String, serde_json::Value>,
}

// ─── A2A Method Parameters ───

/// Parameters for tasks/send method
#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct TaskSendParams {
    /// Task ID (client-generated UUID)
    pub id: String,
    /// Optional session ID for multi-turn
    #[serde(skip_serializing_if = "Option::is_none")]
    pub session_id: Option<String>,
    /// Message to send
    pub message: Message,
    /// Task metadata
    #[serde(default)]
    pub metadata: HashMap<String, serde_json::Value>,
}

/// Parameters for tasks/get method
#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct TaskGetParams {
    /// Task ID to retrieve
    pub id: String,
    /// Number of history items to include
    #[serde(skip_serializing_if = "Option::is_none")]
    pub history_length: Option<usize>,
}

/// Parameters for tasks/cancel method
#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct TaskCancelParams {
    /// Task ID to cancel
    pub id: String,
}

// ─── JSON-RPC Error Codes ───

/// Standard JSON-RPC error codes
pub const PARSE_ERROR: i32 = -32700;
pub const INVALID_REQUEST: i32 = -32600;
pub const METHOD_NOT_FOUND: i32 = -32601;
pub const INVALID_PARAMS: i32 = -32602;

/// A2A-specific error codes (application-level)
pub const TASK_NOT_FOUND: i32 = -32001;
pub const TASK_NOT_CANCELABLE: i32 = -32002;
pub const AGENT_UNAVAILABLE: i32 = -32003;

/// A2A Protocol version
pub const A2A_PROTOCOL_VERSION: &str = "0.2.2";
