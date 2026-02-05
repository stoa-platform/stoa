//! MCP Tool trait and registry
//!
//! Provides the Tool abstraction for MCP tools with proper action requirements.

use async_trait::async_trait;
use parking_lot::RwLock;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::sync::Arc;

pub mod proxy_tool;
pub mod stoa_tools;

use crate::uac::Action;

/// JSON Schema for tool parameters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolSchema {
    #[serde(rename = "type")]
    pub schema_type: String,
    pub properties: HashMap<String, Value>,
    #[serde(skip_serializing_if = "Vec::is_empty", default)]
    pub required: Vec<String>,
}

/// Tool definition exposed via MCP
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolDefinition {
    pub name: String,
    pub description: String,
    #[serde(rename = "inputSchema")]
    pub input_schema: ToolSchema,
}

/// Result of tool execution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolResult {
    pub content: Vec<ToolContent>,
    #[serde(rename = "isError", skip_serializing_if = "Option::is_none")]
    pub is_error: Option<bool>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum ToolContent {
    #[serde(rename = "text")]
    Text { text: String },
    #[serde(rename = "image")]
    Image { data: String, mime_type: String },
    #[serde(rename = "resource")]
    Resource { uri: String, text: Option<String> },
}

impl ToolResult {
    pub fn text(text: impl Into<String>) -> Self {
        Self {
            content: vec![ToolContent::Text { text: text.into() }],
            is_error: None,
        }
    }

    #[allow(dead_code)]
    pub fn error(message: impl Into<String>) -> Self {
        Self {
            content: vec![ToolContent::Text {
                text: message.into(),
            }],
            is_error: Some(true),
        }
    }
}

/// Context provided to tool during execution
#[derive(Debug, Clone)]
pub struct ToolContext {
    pub tenant_id: String,
    pub user_id: Option<String>,
    pub user_email: Option<String>,
    #[allow(dead_code)]
    pub request_id: String,
    pub roles: Vec<String>,
    /// Raw JWT token for forwarding to downstream services (Control Plane)
    pub raw_token: Option<String>,
}

/// The Tool trait - implement this for each MCP tool
#[async_trait]
pub trait Tool: Send + Sync {
    /// Tool name (must be unique)
    fn name(&self) -> &str;

    /// Human-readable description
    fn description(&self) -> &str;

    /// JSON Schema for input parameters
    fn input_schema(&self) -> ToolSchema;

    /// Required UAC action to execute this tool
    /// Override this to specify the action (default: Read)
    fn required_action(&self) -> Action {
        Action::Read
    }

    /// Execute the tool with given arguments
    async fn execute(&self, args: Value, ctx: &ToolContext) -> Result<ToolResult, ToolError>;

    /// Get tool definition for MCP tools/list
    fn definition(&self) -> ToolDefinition {
        ToolDefinition {
            name: self.name().to_string(),
            description: self.description().to_string(),
            input_schema: self.input_schema(),
        }
    }
}

/// Tool execution error
#[derive(Debug, thiserror::Error)]
#[allow(dead_code)]
pub enum ToolError {
    #[error("Invalid arguments: {0}")]
    InvalidArguments(String),

    #[error("Execution failed: {0}")]
    ExecutionFailed(String),

    #[error("Permission denied: {0}")]
    PermissionDenied(String),

    #[error("Not found: {0}")]
    NotFound(String),

    #[error("Internal error: {0}")]
    Internal(String),
}

/// Registry of available tools
pub struct ToolRegistry {
    tools: RwLock<HashMap<String, Arc<dyn Tool>>>,
}

impl ToolRegistry {
    pub fn new() -> Self {
        Self {
            tools: RwLock::new(HashMap::new()),
        }
    }

    /// Register a tool
    pub fn register(&self, tool: Arc<dyn Tool>) {
        let name = tool.name().to_string();
        tracing::info!(tool = %name, action = ?tool.required_action(), "Registering MCP tool");
        self.tools.write().insert(name, tool);
    }

    /// Get a tool by name
    pub fn get(&self, name: &str) -> Option<Arc<dyn Tool>> {
        self.tools.read().get(name).cloned()
    }

    /// List all tools (optionally filtered by tenant)
    pub fn list(&self, _tenant_id: Option<&str>) -> Vec<ToolDefinition> {
        // TODO: Add tenant filtering based on subscriptions
        self.tools.read().values().map(|t| t.definition()).collect()
    }

    /// Get tool count
    pub fn count(&self) -> usize {
        self.tools.read().len()
    }
}

impl Default for ToolRegistry {
    fn default() -> Self {
        Self::new()
    }
}

// ============================================
// Example tool implementation
// ============================================

/// Example: STOA Create API Tool
#[allow(dead_code)]
pub struct StoaCreateApiTool {
    control_plane: Arc<dyn std::any::Any + Send + Sync>,
    git_sync: Arc<dyn std::any::Any + Send + Sync>,
    uac_enforcer: Arc<dyn std::any::Any + Send + Sync>,
}

impl StoaCreateApiTool {
    #[allow(dead_code)]
    pub fn new(
        control_plane: Arc<dyn std::any::Any + Send + Sync>,
        git_sync: Arc<dyn std::any::Any + Send + Sync>,
        uac_enforcer: Arc<dyn std::any::Any + Send + Sync>,
    ) -> Self {
        Self {
            control_plane,
            git_sync,
            uac_enforcer,
        }
    }
}

#[async_trait]
impl Tool for StoaCreateApiTool {
    fn name(&self) -> &str {
        "stoa_create_api"
    }

    fn description(&self) -> &str {
        "Create a new API in the STOA catalog with OpenAPI specification"
    }

    fn input_schema(&self) -> ToolSchema {
        let mut properties = HashMap::new();
        properties.insert(
            "name".to_string(),
            serde_json::json!({
                "type": "string",
                "description": "API name (e.g., billing-api)"
            }),
        );
        properties.insert(
            "version".to_string(),
            serde_json::json!({
                "type": "string",
                "description": "API version (e.g., v1)"
            }),
        );
        properties.insert(
            "openapi_spec".to_string(),
            serde_json::json!({
                "type": "string",
                "description": "OpenAPI 3.x specification as JSON or YAML string"
            }),
        );

        ToolSchema {
            schema_type: "object".to_string(),
            properties,
            required: vec![
                "name".to_string(),
                "version".to_string(),
                "openapi_spec".to_string(),
            ],
        }
    }

    /// This tool requires CreateApi action
    fn required_action(&self) -> Action {
        Action::CreateApi
    }

    async fn execute(&self, args: Value, ctx: &ToolContext) -> Result<ToolResult, ToolError> {
        let name = args
            .get("name")
            .and_then(|v| v.as_str())
            .ok_or_else(|| ToolError::InvalidArguments("Missing 'name' field".into()))?;

        let version = args
            .get("version")
            .and_then(|v| v.as_str())
            .ok_or_else(|| ToolError::InvalidArguments("Missing 'version' field".into()))?;

        // TODO: Actual implementation
        // 1. Parse OpenAPI spec
        // 2. Validate against schema
        // 3. Create API in control plane
        // 4. Sync to Git

        Ok(ToolResult::text(format!(
            "API '{}' version '{}' created successfully for tenant '{}'",
            name, version, ctx.tenant_id
        )))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tool_registry() {
        let registry = ToolRegistry::new();
        assert_eq!(registry.count(), 0);

        let tool = Arc::new(StoaCreateApiTool::new(
            Arc::new(()),
            Arc::new(()),
            Arc::new(()),
        ));

        registry.register(tool);
        assert_eq!(registry.count(), 1);

        let retrieved = registry.get("stoa_create_api");
        assert!(retrieved.is_some());
        assert_eq!(retrieved.unwrap().required_action(), Action::CreateApi);
    }

    #[test]
    fn test_tool_definition() {
        let tool = StoaCreateApiTool::new(Arc::new(()), Arc::new(()), Arc::new(()));

        let def = tool.definition();
        assert_eq!(def.name, "stoa_create_api");
        assert!(!def.description.is_empty());
        assert_eq!(def.input_schema.required.len(), 3);
    }

    #[test]
    fn test_required_action_override() {
        let tool = StoaCreateApiTool::new(Arc::new(()), Arc::new(()), Arc::new(()));

        // Should override default Read action
        assert_eq!(tool.required_action(), Action::CreateApi);
    }
}
