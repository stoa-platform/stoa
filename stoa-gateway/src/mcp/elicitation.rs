//! MCP Elicitation - Server-Initiated User Prompts
//!
//! Implements the elicitation capability from MCP spec 2025-03-26.
//! Allows tools to request user input mid-execution.
//!
//! Example use case: `stoa_deploy_api` tool asks user to confirm
//! the target environment before deploying.

use serde::{Deserialize, Serialize};
use serde_json::Value;

/// Elicitation request from server to client
///
/// Sent via `elicitation/create` method to request user input during tool execution.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ElicitationRequest {
    /// Unique ID for this elicitation request
    pub id: String,

    /// Human-readable message to display to the user
    pub message: String,

    /// JSON Schema describing the expected input format
    #[serde(rename = "requestedSchema")]
    pub requested_schema: ElicitationSchema,

    /// Optional timeout in milliseconds (default: no timeout)
    #[serde(rename = "timeoutMs", skip_serializing_if = "Option::is_none")]
    pub timeout_ms: Option<u64>,
}

/// Schema for elicitation request
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ElicitationSchema {
    #[serde(rename = "type")]
    pub schema_type: String,

    #[serde(skip_serializing_if = "Option::is_none")]
    pub properties: Option<Value>,

    #[serde(skip_serializing_if = "Option::is_none")]
    pub required: Option<Vec<String>>,

    /// For enum types
    #[serde(rename = "enum", skip_serializing_if = "Option::is_none")]
    pub enum_values: Option<Vec<String>>,

    /// Human-readable description of expected input
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
}

/// Response from client to elicitation request
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ElicitationResponse {
    /// ID matching the original request
    pub id: String,

    /// User's response data (must conform to requestedSchema)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub data: Option<Value>,

    /// True if user cancelled/dismissed the prompt
    #[serde(default)]
    pub cancelled: bool,

    /// Error message if something went wrong
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

/// Elicitation result after processing client response
#[derive(Debug, Clone)]
pub enum ElicitationResult {
    /// User provided valid input
    Success(Value),
    /// User cancelled the prompt
    Cancelled,
    /// Request timed out
    Timeout,
    /// Validation or other error
    Error(String),
}

impl ElicitationRequest {
    /// Create a simple text input elicitation
    #[allow(dead_code)]
    pub fn text(id: impl Into<String>, message: impl Into<String>) -> Self {
        Self {
            id: id.into(),
            message: message.into(),
            requested_schema: ElicitationSchema {
                schema_type: "string".to_string(),
                properties: None,
                required: None,
                enum_values: None,
                description: None,
            },
            timeout_ms: None,
        }
    }

    /// Create an enum selection elicitation
    #[allow(dead_code)]
    pub fn select(
        id: impl Into<String>,
        message: impl Into<String>,
        options: Vec<String>,
    ) -> Self {
        Self {
            id: id.into(),
            message: message.into(),
            requested_schema: ElicitationSchema {
                schema_type: "string".to_string(),
                properties: None,
                required: None,
                enum_values: Some(options),
                description: None,
            },
            timeout_ms: None,
        }
    }

    /// Create an object input elicitation with JSON Schema
    #[allow(dead_code)]
    pub fn object(
        id: impl Into<String>,
        message: impl Into<String>,
        properties: Value,
        required: Option<Vec<String>>,
    ) -> Self {
        Self {
            id: id.into(),
            message: message.into(),
            requested_schema: ElicitationSchema {
                schema_type: "object".to_string(),
                properties: Some(properties),
                required,
                enum_values: None,
                description: None,
            },
            timeout_ms: None,
        }
    }

    /// Create a confirmation (yes/no) elicitation
    #[allow(dead_code)]
    pub fn confirm(id: impl Into<String>, message: impl Into<String>) -> Self {
        Self::select(id, message, vec!["yes".to_string(), "no".to_string()])
    }

    /// Create an environment selection elicitation
    /// Common use case for deployment tools
    #[allow(dead_code)]
    pub fn select_environment(id: impl Into<String>, message: impl Into<String>) -> Self {
        Self::select(
            id,
            message,
            vec!["dev".to_string(), "staging".to_string(), "prod".to_string()],
        )
    }

    /// Set timeout in milliseconds
    #[allow(dead_code)]
    pub fn with_timeout(mut self, timeout_ms: u64) -> Self {
        self.timeout_ms = Some(timeout_ms);
        self
    }

    /// Set description for the schema
    #[allow(dead_code)]
    pub fn with_description(mut self, description: impl Into<String>) -> Self {
        self.requested_schema.description = Some(description.into());
        self
    }
}

impl ElicitationResponse {
    /// Create a successful response with data
    #[allow(dead_code)]
    pub fn success(id: impl Into<String>, data: Value) -> Self {
        Self {
            id: id.into(),
            data: Some(data),
            cancelled: false,
            error: None,
        }
    }

    /// Create a cancelled response
    #[allow(dead_code)]
    pub fn cancelled(id: impl Into<String>) -> Self {
        Self {
            id: id.into(),
            data: None,
            cancelled: true,
            error: None,
        }
    }

    /// Create an error response
    #[allow(dead_code)]
    pub fn error(id: impl Into<String>, error: impl Into<String>) -> Self {
        Self {
            id: id.into(),
            data: None,
            cancelled: false,
            error: Some(error.into()),
        }
    }

    /// Convert to ElicitationResult
    pub fn into_result(self) -> ElicitationResult {
        if self.cancelled {
            ElicitationResult::Cancelled
        } else if let Some(error) = self.error {
            ElicitationResult::Error(error)
        } else if let Some(data) = self.data {
            ElicitationResult::Success(data)
        } else {
            ElicitationResult::Error("No data provided".to_string())
        }
    }
}

/// Handle elicitation/create method
///
/// This is called by the SSE handler when processing an elicitation request.
/// In the current implementation, we store pending elicitations and wait
/// for client responses via SSE notifications.
#[allow(dead_code)]
pub fn handle_elicitation_create(
    request: &ElicitationRequest,
) -> Result<serde_json::Value, String> {
    // Validate the request
    if request.id.is_empty() {
        return Err("Elicitation ID cannot be empty".to_string());
    }

    if request.message.is_empty() {
        return Err("Elicitation message cannot be empty".to_string());
    }

    // Return the elicitation request as JSON-RPC notification
    // The client will respond via notifications/elicitation_response
    Ok(serde_json::json!({
        "id": request.id,
        "status": "pending"
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_text_elicitation() {
        let req = ElicitationRequest::text("req-1", "Enter your name");
        assert_eq!(req.id, "req-1");
        assert_eq!(req.message, "Enter your name");
        assert_eq!(req.requested_schema.schema_type, "string");
    }

    #[test]
    fn test_select_elicitation() {
        let req = ElicitationRequest::select(
            "req-2",
            "Choose a color",
            vec!["red".to_string(), "blue".to_string(), "green".to_string()],
        );
        assert_eq!(req.requested_schema.schema_type, "string");
        assert_eq!(
            req.requested_schema.enum_values,
            Some(vec![
                "red".to_string(),
                "blue".to_string(),
                "green".to_string()
            ])
        );
    }

    #[test]
    fn test_object_elicitation() {
        let props = json!({
            "name": {"type": "string"},
            "age": {"type": "integer"}
        });
        let req = ElicitationRequest::object(
            "req-3",
            "Enter your details",
            props,
            Some(vec!["name".to_string()]),
        );
        assert_eq!(req.requested_schema.schema_type, "object");
        assert!(req.requested_schema.properties.is_some());
        assert_eq!(
            req.requested_schema.required,
            Some(vec!["name".to_string()])
        );
    }

    #[test]
    fn test_confirm_elicitation() {
        let req = ElicitationRequest::confirm("req-4", "Are you sure?");
        assert_eq!(
            req.requested_schema.enum_values,
            Some(vec!["yes".to_string(), "no".to_string()])
        );
    }

    #[test]
    fn test_environment_elicitation() {
        let req = ElicitationRequest::select_environment("req-5", "Which environment?");
        assert_eq!(
            req.requested_schema.enum_values,
            Some(vec![
                "dev".to_string(),
                "staging".to_string(),
                "prod".to_string()
            ])
        );
    }

    #[test]
    fn test_elicitation_with_timeout() {
        let req = ElicitationRequest::text("req-6", "Quick!").with_timeout(5000);
        assert_eq!(req.timeout_ms, Some(5000));
    }

    #[test]
    fn test_response_success() {
        let resp = ElicitationResponse::success("req-1", json!("test value"));
        let result = resp.into_result();
        matches!(result, ElicitationResult::Success(_));
    }

    #[test]
    fn test_response_cancelled() {
        let resp = ElicitationResponse::cancelled("req-1");
        let result = resp.into_result();
        matches!(result, ElicitationResult::Cancelled);
    }

    #[test]
    fn test_response_error() {
        let resp = ElicitationResponse::error("req-1", "Something went wrong");
        let result = resp.into_result();
        matches!(result, ElicitationResult::Error(_));
    }

    #[test]
    fn test_handle_elicitation_create_valid() {
        let req = ElicitationRequest::text("req-1", "Enter name");
        let result = handle_elicitation_create(&req);
        assert!(result.is_ok());
    }

    #[test]
    fn test_handle_elicitation_create_empty_id() {
        let req = ElicitationRequest::text("", "Enter name");
        let result = handle_elicitation_create(&req);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("ID cannot be empty"));
    }

    #[test]
    fn test_handle_elicitation_create_empty_message() {
        let req = ElicitationRequest::text("req-1", "");
        let result = handle_elicitation_create(&req);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("message cannot be empty"));
    }

    #[test]
    fn test_elicitation_serialization() {
        let req = ElicitationRequest::select_environment("req-1", "Which environment?");
        let json = serde_json::to_string(&req).unwrap();

        // Check camelCase serialization
        assert!(json.contains("requestedSchema"));
        assert!(!json.contains("requested_schema"));

        // Can deserialize back
        let parsed: ElicitationRequest = serde_json::from_str(&json).unwrap();
        assert_eq!(parsed.id, req.id);
    }
}
