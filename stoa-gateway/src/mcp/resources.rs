//! MCP Resources & Prompts — REST Handlers (CAB-1472)
//!
//! REST-style endpoints for MCP spec methods:
//! - `resources/list`           — list available resources
//! - `resources/read`           — read resource contents
//! - `resources/templates/list` — list URI templates
//! - `prompts/list`             — list prompt templates
//! - `prompts/get`              — get a specific prompt with arguments
//! - `completion/complete`      — autocomplete suggestions
//!
//! These complement the JSON-RPC dispatch in `sse.rs` (Streamable HTTP / WebSocket)
//! by providing direct REST endpoints at `/mcp/resources/*`, `/mcp/prompts/*`,
//! and `/mcp/completion/complete`.

use axum::{extract::State, http::StatusCode, response::IntoResponse, Json};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use tracing::debug;

use crate::state::AppState;

// =============================================================================
// Resource Types (MCP 2025-11-25 §Resources)
// =============================================================================

/// A resource exposed by the server.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Resource {
    /// URI identifying this resource (e.g., `stoa://tools/my_tool`)
    pub uri: String,

    /// Short machine-readable name
    pub name: String,

    /// Human-readable title
    #[serde(skip_serializing_if = "Option::is_none")]
    pub title: Option<String>,

    /// Human-readable description
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,

    /// MIME type of the resource content
    #[serde(rename = "mimeType", skip_serializing_if = "Option::is_none")]
    pub mime_type: Option<String>,
}

/// A URI template for parameterized resource access.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResourceTemplate {
    /// RFC 6570 URI template (e.g., `stoa://tools/{name}`)
    #[serde(rename = "uriTemplate")]
    pub uri_template: String,

    /// Short machine-readable name
    pub name: String,

    /// Human-readable title
    #[serde(skip_serializing_if = "Option::is_none")]
    pub title: Option<String>,

    /// Human-readable description
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,

    /// MIME type of the resource content
    #[serde(rename = "mimeType", skip_serializing_if = "Option::is_none")]
    pub mime_type: Option<String>,
}

/// Content block returned by `resources/read`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResourceContent {
    /// URI of the resource
    pub uri: String,

    /// MIME type
    #[serde(rename = "mimeType", skip_serializing_if = "Option::is_none")]
    pub mime_type: Option<String>,

    /// Text content (mutually exclusive with `blob`)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub text: Option<String>,

    /// Base64-encoded binary content (mutually exclusive with `text`)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub blob: Option<String>,
}

// =============================================================================
// Prompt Types (MCP 2025-11-25 §Prompts)
// =============================================================================

/// A prompt template exposed by the server.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Prompt {
    /// Unique name of the prompt
    pub name: String,

    /// Human-readable title
    #[serde(skip_serializing_if = "Option::is_none")]
    pub title: Option<String>,

    /// Description of what the prompt does
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,

    /// Arguments the prompt accepts
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub arguments: Vec<PromptArgument>,
}

/// An argument to a prompt template.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PromptArgument {
    /// Argument name
    pub name: String,

    /// Description of the argument
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,

    /// Whether this argument is required
    #[serde(default)]
    pub required: bool,
}

/// A message in a prompt response.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PromptMessage {
    /// Role: "user" or "assistant"
    pub role: String,

    /// Content of the message
    pub content: PromptContent,
}

/// Content types for prompt messages.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "lowercase")]
pub enum PromptContent {
    /// Plain text content
    Text { text: String },

    /// Image content (base64)
    Image {
        data: String,
        #[serde(rename = "mimeType")]
        mime_type: String,
    },

    /// Embedded resource reference
    Resource { resource: ResourceContent },
}

// =============================================================================
// Completion Types (MCP 2025-11-25 §Completion)
// =============================================================================

/// Completion result with suggestions.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompletionResult {
    /// Suggested values
    pub values: Vec<String>,

    /// Total number of matches (may be > values.len())
    #[serde(skip_serializing_if = "Option::is_none")]
    pub total: Option<u32>,

    /// Whether more results are available
    #[serde(rename = "hasMore", default)]
    pub has_more: bool,
}

// =============================================================================
// Request Types
// =============================================================================

/// Request body for `resources/list`.
#[derive(Debug, Deserialize, Default)]
pub struct ResourcesListRequest {
    /// Pagination cursor
    #[serde(default)]
    pub cursor: Option<String>,
}

/// Request body for `resources/read`.
#[derive(Debug, Deserialize)]
pub struct ResourcesReadRequest {
    /// URI of the resource to read
    pub uri: String,
}

/// Request body for `resources/templates/list`.
#[derive(Debug, Deserialize, Default)]
pub struct ResourcesTemplatesListRequest {
    /// Pagination cursor
    #[serde(default)]
    pub cursor: Option<String>,
}

/// Request body for `prompts/list`.
#[derive(Debug, Deserialize, Default)]
pub struct PromptsListRequest {
    /// Pagination cursor
    #[serde(default)]
    pub cursor: Option<String>,
}

/// Request body for `prompts/get`.
#[derive(Debug, Deserialize)]
pub struct PromptsGetRequest {
    /// Name of the prompt to get
    pub name: String,

    /// Arguments to fill the prompt with
    #[serde(default)]
    pub arguments: std::collections::HashMap<String, String>,
}

/// Reference for completion (either prompt or resource).
#[derive(Debug, Clone, Deserialize)]
#[serde(tag = "type")]
pub enum CompletionRef {
    /// Reference to a prompt
    #[serde(rename = "ref/prompt")]
    Prompt { name: String },

    /// Reference to a resource
    #[serde(rename = "ref/resource")]
    Resource { uri: String },
}

/// Argument being completed.
#[derive(Debug, Clone, Deserialize)]
pub struct CompletionArgument {
    /// Name of the argument
    pub name: String,

    /// Current value (prefix for autocomplete)
    pub value: String,
}

/// Request body for `completion/complete`.
#[derive(Debug, Deserialize)]
pub struct CompletionCompleteRequest {
    /// Reference to prompt or resource
    #[serde(rename = "ref")]
    pub reference: CompletionRef,

    /// Argument to complete
    pub argument: CompletionArgument,
}

// =============================================================================
// Response Types
// =============================================================================

#[derive(Debug, Serialize)]
pub struct ResourcesListResponse {
    pub resources: Vec<Resource>,
    #[serde(rename = "nextCursor", skip_serializing_if = "Option::is_none")]
    pub next_cursor: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct ResourcesReadResponse {
    pub contents: Vec<ResourceContent>,
}

#[derive(Debug, Serialize)]
pub struct ResourcesTemplatesListResponse {
    #[serde(rename = "resourceTemplates")]
    pub resource_templates: Vec<ResourceTemplate>,
    #[serde(rename = "nextCursor", skip_serializing_if = "Option::is_none")]
    pub next_cursor: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct PromptsListResponse {
    pub prompts: Vec<Prompt>,
    #[serde(rename = "nextCursor", skip_serializing_if = "Option::is_none")]
    pub next_cursor: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct PromptsGetResponse {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    pub messages: Vec<PromptMessage>,
}

#[derive(Debug, Serialize)]
pub struct CompletionCompleteResponse {
    pub completion: CompletionResult,
}

// =============================================================================
// REST Handlers
// =============================================================================

/// POST /mcp/resources/list — List available resources
///
/// Maps each registered tool to an MCP resource with `stoa://tools/{name}` URI.
pub async fn mcp_resources_list(
    State(state): State<AppState>,
    Json(_request): Json<ResourcesListRequest>,
) -> impl IntoResponse {
    debug!("Listing MCP resources");

    let tools = state.tool_registry.list(None);
    let resources: Vec<Resource> = tools
        .iter()
        .map(|t| Resource {
            uri: format!("stoa://tools/{}", t.name),
            name: t.name.clone(),
            title: Some(t.name.clone()),
            description: Some(t.description.clone()),
            mime_type: Some("application/json".to_string()),
        })
        .collect();

    Json(ResourcesListResponse {
        resources,
        next_cursor: None,
    })
}

/// POST /mcp/resources/read — Read resource contents
///
/// Supports `stoa://tools/{name}` URIs — returns the tool definition as JSON.
pub async fn mcp_resources_read(
    State(state): State<AppState>,
    Json(request): Json<ResourcesReadRequest>,
) -> Result<Json<ResourcesReadResponse>, (StatusCode, Json<Value>)> {
    debug!(uri = %request.uri, "Reading MCP resource");

    let tool_name = match request.uri.strip_prefix("stoa://tools/") {
        Some(n) => n.to_string(),
        None => {
            return Err((
                StatusCode::BAD_REQUEST,
                Json(json!({
                    "error": {
                        "code": -32602,
                        "message": format!(
                            "Unsupported URI scheme: '{}'. Expected stoa://tools/{{name}}",
                            request.uri
                        )
                    }
                })),
            ));
        }
    };

    let tools = state.tool_registry.list(None);
    let found = tools.iter().find(|t| t.name == tool_name);

    match found {
        Some(tool) => {
            let tool_json = serde_json::to_string_pretty(tool).unwrap_or_default();
            Ok(Json(ResourcesReadResponse {
                contents: vec![ResourceContent {
                    uri: request.uri,
                    mime_type: Some("application/json".to_string()),
                    text: Some(tool_json),
                    blob: None,
                }],
            }))
        }
        None => Err((
            StatusCode::NOT_FOUND,
            Json(json!({
                "error": {
                    "code": -32002,
                    "message": format!("Resource '{}' not found", request.uri)
                }
            })),
        )),
    }
}

/// POST /mcp/resources/templates/list — List resource URI templates
///
/// Returns the `stoa://tools/{name}` template for dynamic tool lookup.
pub async fn mcp_resources_templates_list(
    Json(_request): Json<ResourcesTemplatesListRequest>,
) -> impl IntoResponse {
    debug!("Listing MCP resource templates");

    Json(ResourcesTemplatesListResponse {
        resource_templates: vec![ResourceTemplate {
            uri_template: "stoa://tools/{name}".to_string(),
            name: "Tool Definition".to_string(),
            title: Some("STOA Tool Definition".to_string()),
            description: Some(
                "Access tool definitions by name. Returns JSON schema and metadata.".to_string(),
            ),
            mime_type: Some("application/json".to_string()),
        }],
        next_cursor: None,
    })
}

/// POST /mcp/prompts/list — List available prompt templates
///
/// Currently returns an empty list. Extensible: register prompts to expose them.
pub async fn mcp_prompts_list(Json(_request): Json<PromptsListRequest>) -> impl IntoResponse {
    debug!("Listing MCP prompts");

    Json(PromptsListResponse {
        prompts: vec![],
        next_cursor: None,
    })
}

/// POST /mcp/prompts/get — Get a specific prompt by name
///
/// Returns 404 since STOA has no built-in prompts yet.
pub async fn mcp_prompts_get(
    Json(request): Json<PromptsGetRequest>,
) -> Result<Json<PromptsGetResponse>, (StatusCode, Json<Value>)> {
    debug!(name = %request.name, "Getting MCP prompt");

    Err((
        StatusCode::NOT_FOUND,
        Json(json!({
            "error": {
                "code": -32002,
                "message": format!("Prompt '{}' not found", request.name)
            }
        })),
    ))
}

/// POST /mcp/completion/complete — Autocomplete suggestions
///
/// Returns empty completions. Extensible: add completable prompts/resources.
pub async fn mcp_completion_complete(
    Json(_request): Json<CompletionCompleteRequest>,
) -> impl IntoResponse {
    debug!("Processing MCP completion request");

    Json(CompletionCompleteResponse {
        completion: CompletionResult {
            values: vec![],
            total: Some(0),
            has_more: false,
        },
    })
}

// =============================================================================
// SSE/JSON-RPC Helper (resources/templates/list)
// =============================================================================

/// Handle `resources/templates/list` for JSON-RPC dispatch (SSE/WS transport).
///
/// Called from `sse.rs` dispatch table.
pub fn handle_resources_templates_list_jsonrpc(request_id: Option<Value>) -> Value {
    json!({
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "resourceTemplates": [{
                "uriTemplate": "stoa://tools/{name}",
                "name": "Tool Definition",
                "title": "STOA Tool Definition",
                "description": "Access tool definitions by name. Returns JSON schema and metadata.",
                "mimeType": "application/json"
            }],
            "nextCursor": null
        }
    })
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_resource_serialization() {
        let resource = Resource {
            uri: "stoa://tools/test_tool".to_string(),
            name: "test_tool".to_string(),
            title: Some("Test Tool".to_string()),
            description: Some("A test tool".to_string()),
            mime_type: Some("application/json".to_string()),
        };
        let json = serde_json::to_value(&resource).unwrap();
        assert_eq!(json["uri"], "stoa://tools/test_tool");
        assert_eq!(json["mimeType"], "application/json");
    }

    #[test]
    fn test_resource_template_serialization() {
        let template = ResourceTemplate {
            uri_template: "stoa://tools/{name}".to_string(),
            name: "Tool Definition".to_string(),
            title: None,
            description: None,
            mime_type: Some("application/json".to_string()),
        };
        let json = serde_json::to_value(&template).unwrap();
        assert_eq!(json["uriTemplate"], "stoa://tools/{name}");
        assert!(json.get("title").is_none());
    }

    #[test]
    fn test_resource_content_text() {
        let content = ResourceContent {
            uri: "stoa://tools/test".to_string(),
            mime_type: Some("application/json".to_string()),
            text: Some("{\"name\": \"test\"}".to_string()),
            blob: None,
        };
        let json = serde_json::to_value(&content).unwrap();
        assert_eq!(json["uri"], "stoa://tools/test");
        assert!(json.get("blob").is_none());
    }

    #[test]
    fn test_prompt_serialization() {
        let prompt = Prompt {
            name: "code_review".to_string(),
            title: Some("Code Review".to_string()),
            description: Some("Reviews code quality".to_string()),
            arguments: vec![PromptArgument {
                name: "code".to_string(),
                description: Some("The code to review".to_string()),
                required: true,
            }],
        };
        let json = serde_json::to_value(&prompt).unwrap();
        assert_eq!(json["name"], "code_review");
        assert_eq!(json["arguments"][0]["name"], "code");
        assert_eq!(json["arguments"][0]["required"], true);
    }

    #[test]
    fn test_prompt_empty_arguments_skipped() {
        let prompt = Prompt {
            name: "simple".to_string(),
            title: None,
            description: None,
            arguments: vec![],
        };
        let json = serde_json::to_value(&prompt).unwrap();
        assert!(json.get("arguments").is_none());
    }

    #[test]
    fn test_prompt_message_text() {
        let msg = PromptMessage {
            role: "user".to_string(),
            content: PromptContent::Text {
                text: "Hello, world!".to_string(),
            },
        };
        let json = serde_json::to_value(&msg).unwrap();
        assert_eq!(json["role"], "user");
        assert_eq!(json["content"]["type"], "text");
        assert_eq!(json["content"]["text"], "Hello, world!");
    }

    #[test]
    fn test_prompt_message_resource() {
        let msg = PromptMessage {
            role: "user".to_string(),
            content: PromptContent::Resource {
                resource: ResourceContent {
                    uri: "stoa://tools/test".to_string(),
                    mime_type: Some("text/plain".to_string()),
                    text: Some("content".to_string()),
                    blob: None,
                },
            },
        };
        let json = serde_json::to_value(&msg).unwrap();
        assert_eq!(json["content"]["type"], "resource");
        assert_eq!(json["content"]["resource"]["uri"], "stoa://tools/test");
    }

    #[test]
    fn test_completion_result_serialization() {
        let result = CompletionResult {
            values: vec!["python".to_string(), "pytorch".to_string()],
            total: Some(10),
            has_more: true,
        };
        let json = serde_json::to_value(&result).unwrap();
        assert_eq!(json["values"].as_array().unwrap().len(), 2);
        assert_eq!(json["total"], 10);
        assert_eq!(json["hasMore"], true);
    }

    #[test]
    fn test_completion_ref_prompt_deserialization() {
        let json = json!({
            "type": "ref/prompt",
            "name": "code_review"
        });
        let r: CompletionRef = serde_json::from_value(json).unwrap();
        match r {
            CompletionRef::Prompt { name } => assert_eq!(name, "code_review"),
            _ => panic!("Expected Prompt ref"),
        }
    }

    #[test]
    fn test_completion_ref_resource_deserialization() {
        let json = json!({
            "type": "ref/resource",
            "uri": "stoa://tools/test"
        });
        let r: CompletionRef = serde_json::from_value(json).unwrap();
        match r {
            CompletionRef::Resource { uri } => assert_eq!(uri, "stoa://tools/test"),
            _ => panic!("Expected Resource ref"),
        }
    }

    #[test]
    fn test_resources_list_response_serialization() {
        let resp = ResourcesListResponse {
            resources: vec![Resource {
                uri: "stoa://tools/foo".to_string(),
                name: "foo".to_string(),
                title: None,
                description: None,
                mime_type: None,
            }],
            next_cursor: None,
        };
        let json = serde_json::to_value(&resp).unwrap();
        assert_eq!(json["resources"].as_array().unwrap().len(), 1);
        assert!(json.get("nextCursor").is_none());
    }

    #[test]
    fn test_resources_templates_list_jsonrpc() {
        let result = handle_resources_templates_list_jsonrpc(Some(json!(42)));
        assert_eq!(result["jsonrpc"], "2.0");
        assert_eq!(result["id"], 42);
        let templates = result["result"]["resourceTemplates"].as_array().unwrap();
        assert_eq!(templates.len(), 1);
        assert_eq!(templates[0]["uriTemplate"], "stoa://tools/{name}");
    }

    #[test]
    fn test_completion_complete_response_empty() {
        let resp = CompletionCompleteResponse {
            completion: CompletionResult {
                values: vec![],
                total: Some(0),
                has_more: false,
            },
        };
        let json = serde_json::to_value(&resp).unwrap();
        assert_eq!(json["completion"]["values"].as_array().unwrap().len(), 0);
        assert_eq!(json["completion"]["hasMore"], false);
    }

    #[test]
    fn test_prompts_list_response_empty() {
        let resp = PromptsListResponse {
            prompts: vec![],
            next_cursor: None,
        };
        let json = serde_json::to_value(&resp).unwrap();
        assert_eq!(json["prompts"].as_array().unwrap().len(), 0);
    }

    #[test]
    fn test_prompts_get_request_deserialization() {
        let json = json!({
            "name": "code_review",
            "arguments": {
                "code": "fn main() {}"
            }
        });
        let req: PromptsGetRequest = serde_json::from_value(json).unwrap();
        assert_eq!(req.name, "code_review");
        assert_eq!(req.arguments.get("code").unwrap(), "fn main() {}");
    }

    #[test]
    fn test_resources_read_request_deserialization() {
        let json = json!({ "uri": "stoa://tools/weather" });
        let req: ResourcesReadRequest = serde_json::from_value(json).unwrap();
        assert_eq!(req.uri, "stoa://tools/weather");
    }
}
