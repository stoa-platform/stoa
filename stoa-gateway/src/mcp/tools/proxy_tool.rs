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
