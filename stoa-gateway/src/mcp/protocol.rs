//! MCP Protocol Types
//!
//! Model Context Protocol (MCP) types for tools/list and tools/call endpoints.
//! CAB-912: Complete MCP Gateway implementation.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// =============================================================================
// Request Types
// =============================================================================

/// Request for listing available tools
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ToolsListRequest {
    /// Pagination cursor for fetching next page
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cursor: Option<String>,
}

/// Request for calling a tool
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolCallRequest {
    /// Name of the tool to call
    pub name: String,

    /// Arguments to pass to the tool
    #[serde(default)]
    pub arguments: HashMap<String, serde_json::Value>,
}

// =============================================================================
// Response Types
// =============================================================================

/// Response containing list of available tools
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolsListResponse {
    /// List of available tools
    pub tools: Vec<ToolDefinition>,

    /// Cursor for next page (if more results available)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub next_cursor: Option<String>,
}

/// Response from calling a tool
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolCallResponse {
    /// Content blocks returned by the tool
    pub content: Vec<ContentBlock>,

    /// Whether the tool execution resulted in an error
    #[serde(default)]
    pub is_error: bool,
}

impl ToolCallResponse {
    /// Create a successful text response
    pub fn text(text: impl Into<String>) -> Self {
        Self {
            content: vec![ContentBlock::Text { text: text.into() }],
            is_error: false,
        }
    }

    /// Create an error response
    pub fn error(message: impl Into<String>) -> Self {
        Self {
            content: vec![ContentBlock::Text {
                text: message.into(),
            }],
            is_error: true,
        }
    }

    /// Create a JSON response
    pub fn json<T: Serialize>(data: &T) -> Result<Self, serde_json::Error> {
        let text = serde_json::to_string_pretty(data)?;
        Ok(Self {
            content: vec![ContentBlock::Text { text }],
            is_error: false,
        })
    }
}

// =============================================================================
// Tool Definition
// =============================================================================

/// Definition of a tool available in the MCP gateway
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolDefinition {
    /// Unique name of the tool
    pub name: String,

    /// Human-readable description
    pub description: String,

    /// JSON Schema for the input arguments
    #[serde(rename = "inputSchema")]
    pub input_schema: serde_json::Value,
}

// =============================================================================
// Content Blocks
// =============================================================================

/// Content block types returned by tools
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "lowercase")]
pub enum ContentBlock {
    /// Text content
    Text { text: String },

    /// Image content (base64 encoded)
    Image {
        data: String,
        #[serde(rename = "mimeType")]
        mime_type: String,
    },

    /// Resource reference
    Resource {
        uri: String,
        #[serde(rename = "mimeType", skip_serializing_if = "Option::is_none")]
        mime_type: Option<String>,
        #[serde(skip_serializing_if = "Option::is_none")]
        text: Option<String>,
    },
}

// =============================================================================
// API State (for stoa_create_api tool)
// =============================================================================

/// State of an API after creation
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ApiState {
    /// API is active and serving traffic
    Active,

    /// API is pending sync to Git
    PendingSync,

    /// API is pending human review (VH/VVH)
    PendingReview,

    /// API creation failed
    Failed,
}

impl std::fmt::Display for ApiState {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ApiState::Active => write!(f, "active"),
            ApiState::PendingSync => write!(f, "pending_sync"),
            ApiState::PendingReview => write!(f, "pending_review"),
            ApiState::Failed => write!(f, "failed"),
        }
    }
}

// =============================================================================
// Create API Request/Response
// =============================================================================

/// Arguments for stoa_create_api tool
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreateApiArgs {
    /// Tenant identifier
    pub tenant: String,

    /// API name
    pub name: String,

    /// API endpoint path (e.g., "/v1/weather")
    pub endpoint: String,

    /// Classification level: H, VH, or VVH
    pub classification: String,

    /// Backend URL to proxy to
    #[serde(skip_serializing_if = "Option::is_none")]
    pub backend_url: Option<String>,

    /// Policies to apply
    #[serde(default)]
    pub policies: Vec<String>,

    /// Optional description
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
}

/// Result of stoa_create_api tool execution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreateApiResult {
    /// Whether the API was created successfully
    pub success: bool,

    /// Created API ID (UUID)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub api_id: Option<String>,

    /// Current state of the API
    pub state: ApiState,

    /// Policy version used for enforcement
    pub policy_version: String,

    /// Human-readable message
    pub message: String,

    /// Public URL for the API (if active)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub public_url: Option<String>,

    /// Merge request URL (if pending review)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub merge_request_url: Option<String>,
}

// =============================================================================
// Error Types
// =============================================================================

/// MCP protocol errors
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct McpError {
    /// Error code
    pub code: McpErrorCode,

    /// Human-readable message
    pub message: String,

    /// Additional details
    #[serde(skip_serializing_if = "Option::is_none")]
    pub details: Option<serde_json::Value>,
}

/// MCP error codes
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum McpErrorCode {
    /// Tool not found
    ToolNotFound,

    /// Invalid arguments
    InvalidArguments,

    /// Rate limit exceeded
    RateLimitExceeded,

    /// Policy violation
    PolicyViolation,

    /// Missing required policies
    MissingPolicies,

    /// Git sync failed
    GitSyncFailed,

    /// Internal server error
    InternalError,
}

impl McpError {
    pub fn tool_not_found(name: &str) -> Self {
        Self {
            code: McpErrorCode::ToolNotFound,
            message: format!("Tool not found: {}", name),
            details: None,
        }
    }

    pub fn invalid_arguments(message: impl Into<String>) -> Self {
        Self {
            code: McpErrorCode::InvalidArguments,
            message: message.into(),
            details: None,
        }
    }

    pub fn rate_limit_exceeded(classification: &str, limit: u32) -> Self {
        Self {
            code: McpErrorCode::RateLimitExceeded,
            message: format!(
                "Rate limit exceeded for {} classification: max {} per hour",
                classification, limit
            ),
            details: None,
        }
    }

    pub fn policy_violation(reason: impl Into<String>, missing: Vec<String>) -> Self {
        Self {
            code: McpErrorCode::PolicyViolation,
            message: reason.into(),
            details: Some(serde_json::json!({ "missing_policies": missing })),
        }
    }

    pub fn git_sync_failed(reason: impl Into<String>) -> Self {
        Self {
            code: McpErrorCode::GitSyncFailed,
            message: reason.into(),
            details: None,
        }
    }

    pub fn internal(message: impl Into<String>) -> Self {
        Self {
            code: McpErrorCode::InternalError,
            message: message.into(),
            details: None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tool_call_response_text() {
        let response = ToolCallResponse::text("Hello, world!");
        assert!(!response.is_error);
        assert_eq!(response.content.len(), 1);
        match &response.content[0] {
            ContentBlock::Text { text } => assert_eq!(text, "Hello, world!"),
            _ => panic!("Expected text content"),
        }
    }

    #[test]
    fn test_tool_call_response_error() {
        let response = ToolCallResponse::error("Something went wrong");
        assert!(response.is_error);
    }

    #[test]
    fn test_tool_call_response_json() {
        let data = serde_json::json!({ "status": "ok" });
        let response = ToolCallResponse::json(&data).unwrap();
        assert!(!response.is_error);
    }

    #[test]
    fn test_api_state_display() {
        assert_eq!(ApiState::Active.to_string(), "active");
        assert_eq!(ApiState::PendingReview.to_string(), "pending_review");
    }

    #[test]
    fn test_mcp_error_serialization() {
        let error = McpError::rate_limit_exceeded("VVH", 2);
        let json = serde_json::to_string(&error).unwrap();
        assert!(json.contains("RATE_LIMIT_EXCEEDED"));
    }
}
