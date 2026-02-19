//! Sandbox Echo Tool — zero-dependency demo tool for onboarding (CAB-1325)
//!
//! Returns the input message with metadata (timestamp, request_id).
//! No external calls, <1ms response. Used during trial onboarding flow
//! so new developers can make their first MCP tool call instantly.

use async_trait::async_trait;
use serde_json::Value;
use std::collections::HashMap;

use super::{
    Tool, ToolAnnotations, ToolContext, ToolDefinition, ToolError, ToolResult, ToolSchema,
};
use crate::uac::Action;

/// Sandbox echo tool for developer onboarding.
///
/// Named `stoa_sandbox_echo` — follows the `stoa_` prefix convention.
/// Implements the `Tool` trait directly (no CP API call needed).
pub struct SandboxEchoTool;

#[async_trait]
impl Tool for SandboxEchoTool {
    fn name(&self) -> &str {
        "stoa_sandbox_echo"
    }

    fn description(&self) -> &str {
        "Echo a message back with metadata. Use this to verify your MCP connection works."
    }

    fn input_schema(&self) -> ToolSchema {
        let mut properties = HashMap::new();
        properties.insert(
            "message".to_string(),
            serde_json::json!({
                "type": "string",
                "description": "Message to echo back"
            }),
        );

        ToolSchema {
            schema_type: "object".to_string(),
            properties,
            required: vec!["message".to_string()],
        }
    }

    fn output_schema(&self) -> Option<Value> {
        Some(serde_json::json!({
            "type": "object",
            "properties": {
                "echo": {"type": "string", "description": "The echoed message"},
                "timestamp": {"type": "string", "description": "ISO 8601 timestamp"},
                "request_id": {"type": "string", "description": "Unique request identifier"}
            },
            "required": ["echo", "timestamp", "request_id"]
        }))
    }

    fn required_action(&self) -> Action {
        Action::Read
    }

    fn definition(&self) -> ToolDefinition {
        ToolDefinition {
            name: self.name().to_string(),
            description: self.description().to_string(),
            input_schema: self.input_schema(),
            output_schema: self.output_schema(),
            annotations: Some(
                ToolAnnotations::from_action(Action::Read).with_title("Sandbox Echo"),
            ),
            tenant_id: None, // Global tool, visible to all tenants
        }
    }

    async fn execute(&self, args: Value, ctx: &ToolContext) -> Result<ToolResult, ToolError> {
        let message = args.get("message").and_then(|v| v.as_str()).unwrap_or("");

        let now = chrono::Utc::now().to_rfc3339();

        let response = serde_json::json!({
            "echo": message,
            "timestamp": now,
            "request_id": ctx.request_id,
        });

        Ok(ToolResult::text(
            serde_json::to_string_pretty(&response)
                .unwrap_or_else(|_| format!("{{\"echo\":\"{}\"}}", message)),
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_ctx() -> ToolContext {
        ToolContext {
            tenant_id: "test-tenant".to_string(),
            user_id: Some("test-user".to_string()),
            user_email: Some("test@example.com".to_string()),
            request_id: "req-12345".to_string(),
            roles: vec!["viewer".to_string()],
            scopes: vec!["stoa:read".to_string()],
            raw_token: None,
            skill_instructions: None,
        }
    }

    #[test]
    fn test_tool_metadata() {
        let tool = SandboxEchoTool;
        assert_eq!(tool.name(), "stoa_sandbox_echo");
        assert_eq!(tool.required_action(), Action::Read);
        assert!(tool.description().contains("Echo"));
    }

    #[test]
    fn test_input_schema() {
        let tool = SandboxEchoTool;
        let schema = tool.input_schema();
        assert_eq!(schema.schema_type, "object");
        assert!(schema.properties.contains_key("message"));
        assert_eq!(schema.required, vec!["message"]);
    }

    #[test]
    fn test_output_schema() {
        let tool = SandboxEchoTool;
        let schema = tool.output_schema().expect("should have output schema");
        let obj = schema.as_object().expect("should be object");
        let props = obj.get("properties").expect("should have properties");
        assert!(props.get("echo").is_some());
        assert!(props.get("timestamp").is_some());
        assert!(props.get("request_id").is_some());
    }

    #[test]
    fn test_definition_annotations() {
        let tool = SandboxEchoTool;
        let def = tool.definition();
        let annotations = def.annotations.expect("should have annotations");
        assert_eq!(annotations.read_only_hint, Some(true));
        assert_eq!(annotations.destructive_hint, Some(false));
        assert_eq!(annotations.idempotent_hint, Some(true));
        assert_eq!(annotations.title, Some("Sandbox Echo".to_string()));
        assert!(def.tenant_id.is_none()); // Global tool
    }

    #[tokio::test]
    async fn test_execute_echo() {
        let tool = SandboxEchoTool;
        let ctx = make_ctx();
        let args = serde_json::json!({"message": "Hello STOA!"});

        let result = tool.execute(args, &ctx).await.expect("should succeed");

        let text = match &result.content[0] {
            super::super::ToolContent::Text { text } => text,
            _ => panic!("expected text content"),
        };

        let parsed: Value = serde_json::from_str(text).expect("should be valid JSON");
        assert_eq!(parsed["echo"], "Hello STOA!");
        assert_eq!(parsed["request_id"], "req-12345");
        assert!(parsed["timestamp"].as_str().is_some());
    }

    #[tokio::test]
    async fn test_execute_empty_message() {
        let tool = SandboxEchoTool;
        let ctx = make_ctx();
        let args = serde_json::json!({});

        let result = tool.execute(args, &ctx).await.expect("should succeed");

        let text = match &result.content[0] {
            super::super::ToolContent::Text { text } => text,
            _ => panic!("expected text content"),
        };

        let parsed: Value = serde_json::from_str(text).expect("should be valid JSON");
        assert_eq!(parsed["echo"], "");
    }

    #[tokio::test]
    async fn test_execute_preserves_request_id() {
        let tool = SandboxEchoTool;
        let mut ctx = make_ctx();
        ctx.request_id = "custom-req-id".to_string();
        let args = serde_json::json!({"message": "test"});

        let result = tool.execute(args, &ctx).await.expect("should succeed");

        let text = match &result.content[0] {
            super::super::ToolContent::Text { text } => text,
            _ => panic!("expected text content"),
        };

        let parsed: Value = serde_json::from_str(text).expect("should be valid JSON");
        assert_eq!(parsed["request_id"], "custom-req-id");
    }
}
