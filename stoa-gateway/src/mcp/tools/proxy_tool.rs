//! Generic Proxy Tool
//!
//! Forwards tool calls to the Control Plane Python API.

use async_trait::async_trait;
use serde_json::Value;
use std::sync::Arc;

use super::{Tool, ToolContext, ToolError, ToolResult, ToolSchema};
use crate::control_plane::ToolProxyClient;
use crate::uac::Action;

/// Generic proxy tool — forwards execution to Control Plane
pub struct ProxyTool {
    tool_name: String,
    description: String,
    schema: ToolSchema,
    required_action: Action,
    cp: Arc<ToolProxyClient>,
}

impl ProxyTool {
    pub fn new(
        tool_name: &str,
        description: &str,
        schema: ToolSchema,
        required_action: Action,
        cp: Arc<ToolProxyClient>,
    ) -> Self {
        Self {
            tool_name: tool_name.to_string(),
            description: description.to_string(),
            schema,
            required_action,
            cp,
        }
    }
}

#[async_trait]
impl Tool for ProxyTool {
    fn name(&self) -> &str {
        &self.tool_name
    }

    fn description(&self) -> &str {
        &self.description
    }

    fn input_schema(&self) -> ToolSchema {
        self.schema.clone()
    }

    fn required_action(&self) -> Action {
        self.required_action
    }

    async fn execute(&self, args: Value, ctx: &ToolContext) -> Result<ToolResult, ToolError> {
        let result = self
            .cp
            .call_tool(&self.tool_name, args, ctx)
            .await
            .map_err(ToolError::ExecutionFailed)?;

        // Python gateway returns MCP-formatted: {"content": [...], "isError": bool}
        // Extract text content directly to avoid double-wrapping.
        if let Some(content_arr) = result.get("content").and_then(|c| c.as_array()) {
            let is_error = result
                .get("isError")
                .and_then(|v| v.as_bool())
                .unwrap_or(false);

            let texts: Vec<String> = content_arr
                .iter()
                .filter_map(|block| block.get("text").and_then(|t| t.as_str()).map(String::from))
                .collect();

            let text = texts.join("\n");
            let mut tool_result = ToolResult::text(text);
            if is_error {
                tool_result.is_error = Some(true);
            }
            return Ok(tool_result);
        }

        // Fallback: serialize entire response as text
        Ok(ToolResult::text(
            serde_json::to_string_pretty(&result).unwrap_or_else(|_| result.to_string()),
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use wiremock::matchers::{method, path};
    use wiremock::{Mock, MockServer, ResponseTemplate};

    fn make_schema() -> ToolSchema {
        ToolSchema {
            schema_type: "object".to_string(),
            properties: Default::default(),
            required: vec![],
        }
    }

    fn make_ctx() -> ToolContext {
        ToolContext {
            tenant_id: "t1".to_string(),
            user_id: Some("u1".to_string()),
            user_email: None,
            request_id: "r1".to_string(),
            roles: vec![],
            scopes: vec![],
            raw_token: None,
        }
    }

    #[test]
    fn constructor_and_getters() {
        let cp = Arc::new(ToolProxyClient::new("http://localhost:9999", None));
        let proxy = ProxyTool::new("my_tool", "My description", make_schema(), Action::ViewMetrics, cp);
        assert_eq!(proxy.name(), "my_tool");
        assert_eq!(proxy.description(), "My description");
        assert_eq!(proxy.required_action(), Action::ViewMetrics);
        assert_eq!(proxy.input_schema().schema_type, "object");
    }

    #[tokio::test]
    async fn unwraps_single_text_content() {
        let mock = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/v1/mcp/tools/call"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({
                "content": [{"type": "text", "text": "hello world"}],
                "isError": false
            })))
            .mount(&mock).await;

        let cp = Arc::new(ToolProxyClient::new(&mock.uri(), None));
        let proxy = ProxyTool::new("test_tool", "test", make_schema(), Action::Read, cp);
        let result = proxy.execute(json!({}), &make_ctx()).await.unwrap();
        match &result.content[0] {
            crate::mcp::tools::ToolContent::Text { text } => assert_eq!(text, "hello world"),
            _ => panic!("expected text"),
        }
    }

    #[tokio::test]
    async fn joins_multiple_text_blocks() {
        let mock = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/v1/mcp/tools/call"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({
                "content": [
                    {"type": "text", "text": "line one"},
                    {"type": "text", "text": "line two"}
                ]
            })))
            .mount(&mock).await;

        let cp = Arc::new(ToolProxyClient::new(&mock.uri(), None));
        let proxy = ProxyTool::new("test_tool", "test", make_schema(), Action::Read, cp);
        let result = proxy.execute(json!({}), &make_ctx()).await.unwrap();
        match &result.content[0] {
            crate::mcp::tools::ToolContent::Text { text } => assert_eq!(text, "line one\nline two"),
            _ => panic!("expected text"),
        }
    }

    #[tokio::test]
    async fn propagates_is_error_flag() {
        let mock = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/v1/mcp/tools/call"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({
                "content": [{"type": "text", "text": "oops"}],
                "isError": true
            })))
            .mount(&mock).await;

        let cp = Arc::new(ToolProxyClient::new(&mock.uri(), None));
        let proxy = ProxyTool::new("test_tool", "test", make_schema(), Action::Read, cp);
        let result = proxy.execute(json!({}), &make_ctx()).await.unwrap();
        assert_eq!(result.is_error, Some(true));
    }

    #[tokio::test]
    async fn fallback_to_pretty_json_when_no_content_array() {
        let mock = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/v1/mcp/tools/call"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({"data": "raw response"})))
            .mount(&mock).await;

        let cp = Arc::new(ToolProxyClient::new(&mock.uri(), None));
        let proxy = ProxyTool::new("test_tool", "test", make_schema(), Action::Read, cp);
        let result = proxy.execute(json!({}), &make_ctx()).await.unwrap();
        match &result.content[0] {
            crate::mcp::tools::ToolContent::Text { text } => assert!(text.contains("raw response")),
            _ => panic!("expected text"),
        }
    }

    #[tokio::test]
    async fn content_without_text_fields_yields_empty() {
        let mock = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/v1/mcp/tools/call"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({
                "content": [{"type": "image", "data": "abc"}]
            })))
            .mount(&mock).await;

        let cp = Arc::new(ToolProxyClient::new(&mock.uri(), None));
        let proxy = ProxyTool::new("test_tool", "test", make_schema(), Action::Read, cp);
        let result = proxy.execute(json!({}), &make_ctx()).await.unwrap();
        match &result.content[0] {
            crate::mcp::tools::ToolContent::Text { text } => assert!(text.is_empty()),
            _ => panic!("expected text"),
        }
    }

    #[tokio::test]
    async fn cp_error_returns_tool_error() {
        let cp = Arc::new(ToolProxyClient::new("http://127.0.0.1:1", None));
        let proxy = ProxyTool::new("test_tool", "test", make_schema(), Action::Read, cp);
        let result = proxy.execute(json!({}), &make_ctx()).await;
        assert!(result.is_err());
    }
}

