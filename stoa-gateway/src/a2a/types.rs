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

/// Task state machine (A2A v1.0):
/// submitted → working → completed | failed | canceled | input_required | auth_required | rejected
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum TaskState {
    Submitted,
    Working,
    InputRequired,
    Completed,
    Failed,
    Canceled,
    /// Agent requires authentication/authorization (A2A v1.0)
    AuthRequired,
    /// Agent rejected the task (A2A v1.0)
    Rejected,
}

/// A task represents a unit of work sent to an agent
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Task {
    /// Unique task identifier
    pub id: String,
    /// Context ID for multi-turn conversations (A2A v1.0, replaces session_id)
    #[serde(alias = "sessionId", skip_serializing_if = "Option::is_none")]
    pub context_id: Option<String>,
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
    /// Context ID for multi-turn (A2A v1.0)
    #[serde(alias = "sessionId", skip_serializing_if = "Option::is_none")]
    pub context_id: Option<String>,
    /// Message to send
    pub message: Message,
    /// Task metadata
    #[serde(default)]
    pub metadata: HashMap<String, serde_json::Value>,
}

/// MCP tool invocation payload — sent as a Data part in A2A messages.
/// Enables the A2A → MCP bridge: agents invoke MCP tools via the A2A protocol.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolInvocation {
    /// MCP tool name to invoke
    pub tool: String,
    /// Tool arguments (JSON object)
    #[serde(default)]
    pub arguments: serde_json::Value,
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

/// A2A Protocol version (upgraded to v1.0 — CAB-1754)
pub const A2A_PROTOCOL_VERSION: &str = "1.0";

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    // ─── AgentCard serialization ───

    #[test]
    fn test_agent_card_round_trip() {
        let card = AgentCard {
            name: "Test Agent".to_string(),
            description: "A test agent".to_string(),
            url: "http://localhost:8080/a2a".to_string(),
            protocol_version: A2A_PROTOCOL_VERSION.to_string(),
            capabilities: AgentCapabilities {
                streaming: true,
                push_notifications: false,
                state_transition_history: true,
            },
            authentication: Some(AgentAuthentication {
                schemes: vec!["bearer".to_string()],
                credentials: None,
            }),
            skills: vec![AgentSkill {
                id: "translate".to_string(),
                name: "Translate".to_string(),
                description: "Translates text".to_string(),
                tags: vec!["nlp".to_string()],
                examples: vec!["Translate hello to French".to_string()],
                input_modes: vec!["text".to_string()],
                output_modes: vec!["text".to_string()],
            }],
            provider: Some(AgentProvider {
                organization: "STOA".to_string(),
                url: Some("https://gostoa.dev".to_string()),
            }),
        };

        let json = serde_json::to_value(&card).expect("serialize");
        // camelCase field names
        assert_eq!(json["protocolVersion"], "1.0");
        assert!(json["capabilities"]["streaming"].as_bool().expect("bool"));
        assert_eq!(json["skills"][0]["id"], "translate");

        let deserialized: AgentCard = serde_json::from_value(json).expect("deserialize");
        assert_eq!(deserialized.name, "Test Agent");
        assert!(deserialized.capabilities.streaming);
        assert_eq!(deserialized.skills.len(), 1);
    }

    #[test]
    fn test_agent_card_optional_fields_omitted() {
        let card = AgentCard {
            name: "Minimal".to_string(),
            description: "Minimal agent".to_string(),
            url: "http://localhost".to_string(),
            protocol_version: "1.0".to_string(),
            capabilities: AgentCapabilities {
                streaming: false,
                push_notifications: false,
                state_transition_history: false,
            },
            authentication: None,
            skills: vec![],
            provider: None,
        };

        let json = serde_json::to_value(&card).expect("serialize");
        assert!(json.get("authentication").is_none());
        assert!(json.get("skills").is_none()); // skip_serializing_if = Vec::is_empty
        assert!(json.get("provider").is_none());
    }

    // ─── JSON-RPC 2.0 ───

    #[test]
    fn test_jsonrpc_request_deserialize() {
        let raw = json!({
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "params": {"id": "task-1"},
            "id": 1
        });
        let req: JsonRpcRequest = serde_json::from_value(raw).expect("deserialize");
        assert_eq!(req.jsonrpc, "2.0");
        assert_eq!(req.method, "tasks/send");
        assert_eq!(req.params["id"], "task-1");
    }

    #[test]
    fn test_jsonrpc_request_default_params() {
        let raw = json!({
            "jsonrpc": "2.0",
            "method": "agent/info",
            "id": "abc"
        });
        let req: JsonRpcRequest = serde_json::from_value(raw).expect("deserialize");
        assert!(req.params.is_null()); // serde default
    }

    #[test]
    fn test_jsonrpc_response_success() {
        let resp = JsonRpcResponse::success(json!(1), json!({"status": "ok"}));
        assert_eq!(resp.jsonrpc, "2.0");
        assert!(resp.result.is_some());
        assert!(resp.error.is_none());
        assert_eq!(resp.id, json!(1));

        let json = serde_json::to_value(&resp).expect("serialize");
        assert!(json.get("error").is_none()); // skip_serializing_if
        assert_eq!(json["result"]["status"], "ok");
    }

    #[test]
    fn test_jsonrpc_response_error() {
        let resp = JsonRpcResponse::error(json!("req-42"), METHOD_NOT_FOUND, "Method not found");
        assert!(resp.result.is_none());
        assert!(resp.error.is_some());

        let err = resp.error.as_ref().expect("error");
        assert_eq!(err.code, -32601);
        assert_eq!(err.message, "Method not found");

        let json = serde_json::to_value(&resp).expect("serialize");
        assert!(json.get("result").is_none()); // skip_serializing_if
        assert_eq!(json["error"]["code"], -32601);
    }

    #[test]
    fn test_jsonrpc_response_string_id() {
        let resp = JsonRpcResponse::success(json!("uuid-123"), json!(null));
        assert_eq!(resp.id, json!("uuid-123"));
    }

    // ─── TaskState enum ───

    #[test]
    fn test_task_state_serialization() {
        assert_eq!(
            serde_json::to_value(TaskState::Submitted).expect("ser"),
            json!("submitted")
        );
        assert_eq!(
            serde_json::to_value(TaskState::Working).expect("ser"),
            json!("working")
        );
        assert_eq!(
            serde_json::to_value(TaskState::InputRequired).expect("ser"),
            json!("inputrequired")
        );
        assert_eq!(
            serde_json::to_value(TaskState::Completed).expect("ser"),
            json!("completed")
        );
        assert_eq!(
            serde_json::to_value(TaskState::Failed).expect("ser"),
            json!("failed")
        );
        assert_eq!(
            serde_json::to_value(TaskState::Canceled).expect("ser"),
            json!("canceled")
        );
        assert_eq!(
            serde_json::to_value(TaskState::AuthRequired).expect("ser"),
            json!("authrequired")
        );
        assert_eq!(
            serde_json::to_value(TaskState::Rejected).expect("ser"),
            json!("rejected")
        );
    }

    #[test]
    fn test_task_state_round_trip() {
        for state in [
            TaskState::Submitted,
            TaskState::Working,
            TaskState::Completed,
            TaskState::Failed,
            TaskState::Canceled,
            TaskState::InputRequired,
            TaskState::AuthRequired,
            TaskState::Rejected,
        ] {
            let json = serde_json::to_value(&state).expect("serialize");
            let back: TaskState = serde_json::from_value(json).expect("deserialize");
            assert_eq!(back, state);
        }
    }

    // ─── Part tagged enum ───

    #[test]
    fn test_part_text_serialization() {
        let part = Part::Text {
            text: "Hello world".to_string(),
        };
        let json = serde_json::to_value(&part).expect("serialize");
        assert_eq!(json["type"], "text");
        assert_eq!(json["text"], "Hello world");
    }

    #[test]
    fn test_part_file_serialization() {
        let part = Part::File {
            file: FileContent {
                name: Some("report.pdf".to_string()),
                mime_type: Some("application/pdf".to_string()),
                bytes: Some("base64data".to_string()),
                uri: None,
            },
        };
        let json = serde_json::to_value(&part).expect("serialize");
        assert_eq!(json["type"], "file");
        assert_eq!(json["file"]["name"], "report.pdf");
        assert!(json["file"].get("uri").is_none());
    }

    #[test]
    fn test_part_data_serialization() {
        let part = Part::Data {
            data: json!({"key": "value", "count": 42}),
        };
        let json = serde_json::to_value(&part).expect("serialize");
        assert_eq!(json["type"], "data");
        assert_eq!(json["data"]["count"], 42);
    }

    #[test]
    fn test_part_round_trip_all_variants() {
        let parts = vec![
            Part::Text {
                text: "hi".to_string(),
            },
            Part::File {
                file: FileContent {
                    name: None,
                    mime_type: None,
                    bytes: None,
                    uri: Some("https://example.com/f.txt".to_string()),
                },
            },
            Part::Data {
                data: json!([1, 2, 3]),
            },
        ];
        for part in parts {
            let json = serde_json::to_value(&part).expect("serialize");
            let back: Part = serde_json::from_value(json).expect("deserialize");
            let re_json = serde_json::to_value(&back).expect("re-serialize");
            let orig_json = serde_json::to_value(&part).expect("orig");
            assert_eq!(re_json, orig_json);
        }
    }

    // ─── Task ───

    #[test]
    fn test_task_full_round_trip() {
        let task = Task {
            id: "task-001".to_string(),
            context_id: Some("ctx-abc".to_string()),
            status: TaskStatus {
                state: TaskState::Working,
                message: Some(Message {
                    role: MessageRole::Agent,
                    parts: vec![Part::Text {
                        text: "Processing...".to_string(),
                    }],
                    metadata: HashMap::new(),
                }),
                timestamp: Some("2026-03-18T12:00:00Z".to_string()),
            },
            history: vec![Message {
                role: MessageRole::User,
                parts: vec![Part::Text {
                    text: "Translate hello".to_string(),
                }],
                metadata: HashMap::new(),
            }],
            artifacts: vec![Artifact {
                name: Some("translation".to_string()),
                description: None,
                parts: vec![Part::Text {
                    text: "Bonjour".to_string(),
                }],
                index: Some(0),
                last_chunk: Some(true),
                metadata: HashMap::new(),
            }],
            metadata: HashMap::new(),
        };

        let json = serde_json::to_value(&task).expect("serialize");
        assert_eq!(json["contextId"], "ctx-abc");
        assert_eq!(json["status"]["state"], "working");

        let back: Task = serde_json::from_value(json).expect("deserialize");
        assert_eq!(back.id, "task-001");
        assert_eq!(back.context_id, Some("ctx-abc".to_string()));
        assert_eq!(back.history.len(), 1);
        assert_eq!(back.artifacts.len(), 1);
    }

    #[test]
    fn test_task_minimal_omits_empty_collections() {
        let task = Task {
            id: "t1".to_string(),
            context_id: None,
            status: TaskStatus {
                state: TaskState::Submitted,
                message: None,
                timestamp: None,
            },
            history: vec![],
            artifacts: vec![],
            metadata: HashMap::new(),
        };

        let json = serde_json::to_value(&task).expect("serialize");
        assert!(json.get("contextId").is_none());
        assert!(json.get("history").is_none()); // skip_serializing_if = Vec::is_empty
        assert!(json.get("artifacts").is_none());
        assert!(json.get("metadata").is_none()); // skip_serializing_if = HashMap::is_empty
    }

    // ─── context_id alias ───

    #[test]
    fn test_task_send_params_session_id_alias() {
        let raw = json!({
            "id": "task-1",
            "sessionId": "sess-old",
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "hi"}]
            }
        });
        let params: TaskSendParams = serde_json::from_value(raw).expect("deserialize");
        assert_eq!(params.context_id, Some("sess-old".to_string()));
    }

    #[test]
    fn test_task_send_params_context_id() {
        let raw = json!({
            "id": "task-2",
            "contextId": "ctx-new",
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "hello"}]
            }
        });
        let params: TaskSendParams = serde_json::from_value(raw).expect("deserialize");
        assert_eq!(params.context_id, Some("ctx-new".to_string()));
    }

    // ─── ToolInvocation ───

    #[test]
    fn test_tool_invocation_round_trip() {
        let inv = ToolInvocation {
            tool: "weather_lookup".to_string(),
            arguments: json!({"city": "Paris"}),
        };
        let json = serde_json::to_value(&inv).expect("serialize");
        assert_eq!(json["tool"], "weather_lookup");
        assert_eq!(json["arguments"]["city"], "Paris");

        let back: ToolInvocation = serde_json::from_value(json).expect("deserialize");
        assert_eq!(back.tool, "weather_lookup");
    }

    #[test]
    fn test_tool_invocation_default_arguments() {
        let raw = json!({"tool": "ping"});
        let inv: ToolInvocation = serde_json::from_value(raw).expect("deserialize");
        assert_eq!(inv.tool, "ping");
        assert!(inv.arguments.is_null()); // serde default
    }

    // ─── TaskGetParams / TaskCancelParams ───

    #[test]
    fn test_task_get_params() {
        let raw = json!({"id": "t-1", "historyLength": 5});
        let params: TaskGetParams = serde_json::from_value(raw).expect("deserialize");
        assert_eq!(params.id, "t-1");
        assert_eq!(params.history_length, Some(5));
    }

    #[test]
    fn test_task_cancel_params() {
        let raw = json!({"id": "t-2"});
        let params: TaskCancelParams = serde_json::from_value(raw).expect("deserialize");
        assert_eq!(params.id, "t-2");
    }

    // ─── Error codes ───

    #[test]
    fn test_error_code_values() {
        assert_eq!(PARSE_ERROR, -32700);
        assert_eq!(INVALID_REQUEST, -32600);
        assert_eq!(METHOD_NOT_FOUND, -32601);
        assert_eq!(INVALID_PARAMS, -32602);
        assert_eq!(TASK_NOT_FOUND, -32001);
        assert_eq!(TASK_NOT_CANCELABLE, -32002);
        assert_eq!(AGENT_UNAVAILABLE, -32003);
    }

    // ─── MessageRole ───

    #[test]
    fn test_message_role_serialization() {
        assert_eq!(
            serde_json::to_value(MessageRole::User).expect("ser"),
            json!("user")
        );
        assert_eq!(
            serde_json::to_value(MessageRole::Agent).expect("ser"),
            json!("agent")
        );
    }
}
