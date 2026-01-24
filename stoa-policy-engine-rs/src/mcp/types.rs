use serde::{Deserialize, Serialize};

/// Represents a tool call in the MCP protocol
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolCall {
    pub name: String,
    pub arguments: serde_json::Value,
}

/// Represents a tool result in the MCP protocol
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolResult {
    pub content: Vec<ContentBlock>,
    #[serde(rename = "isError")]
    pub is_error: bool,
}

/// Content block types for MCP responses
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum ContentBlock {
    #[serde(rename = "text")]
    Text { text: String },
}

impl ToolResult {
    /// Create a successful tool result with text content
    pub fn success(message: &str) -> Self {
        Self {
            content: vec![ContentBlock::Text {
                text: message.to_string(),
            }],
            is_error: false,
        }
    }

    /// Create an error tool result with text content
    pub fn error(message: &str) -> Self {
        Self {
            content: vec![ContentBlock::Text {
                text: message.to_string(),
            }],
            is_error: true,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tool_call_deserialize() {
        let json = r#"{"name": "test_tool", "arguments": {"key": "value"}}"#;
        let tool_call: ToolCall = serde_json::from_str(json).unwrap();
        assert_eq!(tool_call.name, "test_tool");
        assert_eq!(tool_call.arguments["key"], "value");
    }

    #[test]
    fn test_tool_result_error_serialize() {
        let result = ToolResult::error("Something went wrong");
        let json = serde_json::to_string(&result).unwrap();
        assert!(json.contains("\"isError\":true"));
        assert!(json.contains("Something went wrong"));
    }

    #[test]
    fn test_tool_result_success_serialize() {
        let result = ToolResult::success("Operation completed");
        let json = serde_json::to_string(&result).unwrap();
        assert!(json.contains("\"isError\":false"));
    }
}
