//! MCP Tool trait and registry
//!
//! Provides the Tool abstraction for MCP tools with proper action requirements.
//! Implements MCP 2025-03-26 spec: Tool annotations, outputSchema, etc.

use async_trait::async_trait;
use parking_lot::RwLock;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::sync::Arc;

pub mod dynamic_tool;
pub mod native_tool;
pub mod proxy_tool;
pub mod stoa_tools;

use crate::uac::Action;

// ============================================
// MCP 2025-03-26: Tool Annotations
// ============================================

/// Tool annotations for MCP 2025-03-26 spec compliance
///
/// Provides hints to clients about tool behavior for better UX
/// (confirmations, caching, parallel execution).
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ToolAnnotations {
    /// Human-readable title for the tool
    #[serde(skip_serializing_if = "Option::is_none")]
    pub title: Option<String>,

    /// If true, tool only reads data (no side effects)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub read_only_hint: Option<bool>,

    /// If true, tool may perform destructive actions (delete, overwrite)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub destructive_hint: Option<bool>,

    /// If true, calling multiple times with same args = same result
    #[serde(skip_serializing_if = "Option::is_none")]
    pub idempotent_hint: Option<bool>,

    /// If true, tool interacts with external world (not closed system)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub open_world_hint: Option<bool>,
}

impl ToolAnnotations {
    /// Create annotations from a UAC Action
    ///
    /// Auto-derives hints based on action semantics:
    /// - Read/List → readOnlyHint: true, destructiveHint: false, idempotentHint: true
    /// - Create → readOnlyHint: false, destructiveHint: false, idempotentHint: false
    /// - Update → readOnlyHint: false, destructiveHint: false, idempotentHint: true
    /// - Delete → readOnlyHint: false, destructiveHint: true, idempotentHint: false
    pub fn from_action(action: Action) -> Self {
        match action {
            // Read operations
            Action::Read | Action::List | Action::Search => Self {
                read_only_hint: Some(true),
                destructive_hint: Some(false),
                idempotent_hint: Some(true),
                open_world_hint: Some(true), // Reads from external system
                ..Default::default()
            },
            // View operations (also read-only)
            Action::ViewMetrics | Action::ViewLogs | Action::ViewAudit => Self {
                read_only_hint: Some(true),
                destructive_hint: Some(false),
                idempotent_hint: Some(true),
                open_world_hint: Some(true),
                ..Default::default()
            },
            // Create operations
            Action::Create | Action::CreateApi | Action::Subscribe => Self {
                read_only_hint: Some(false),
                destructive_hint: Some(false),
                idempotent_hint: Some(false), // Create is not idempotent
                open_world_hint: Some(true),
                ..Default::default()
            },
            // Update operations
            Action::Update | Action::UpdateApi | Action::ManageSubscription => Self {
                read_only_hint: Some(false),
                destructive_hint: Some(false),
                idempotent_hint: Some(true), // PUT-style updates are idempotent
                open_world_hint: Some(true),
                ..Default::default()
            },
            // Delete operations
            Action::Delete | Action::DeleteApi | Action::Unsubscribe => Self {
                read_only_hint: Some(false),
                destructive_hint: Some(true), // Destructive!
                idempotent_hint: Some(false),
                open_world_hint: Some(true),
                ..Default::default()
            },
            // Publish/Deprecate (state changes, not destructive)
            Action::PublishApi | Action::DeprecateApi => Self {
                read_only_hint: Some(false),
                destructive_hint: Some(false),
                idempotent_hint: Some(true), // Publish is idempotent
                open_world_hint: Some(true),
                ..Default::default()
            },
            // Admin operations
            Action::ManageUsers | Action::ManageTenants | Action::ManageContracts => Self {
                read_only_hint: Some(false),
                destructive_hint: Some(false), // Could be destructive, but not always
                idempotent_hint: Some(false),
                open_world_hint: Some(true),
                ..Default::default()
            },
        }
    }

    /// Create annotations with a title
    #[allow(dead_code)]
    pub fn with_title(mut self, title: impl Into<String>) -> Self {
        self.title = Some(title.into());
        self
    }
}

/// JSON Schema for tool parameters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolSchema {
    #[serde(rename = "type")]
    pub schema_type: String,
    pub properties: HashMap<String, Value>,
    #[serde(skip_serializing_if = "Vec::is_empty", default)]
    pub required: Vec<String>,
}

/// Tool definition exposed via MCP (2025-03-26 spec)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolDefinition {
    pub name: String,
    pub description: String,
    #[serde(rename = "inputSchema")]
    pub input_schema: ToolSchema,
    /// Optional output schema for structured tool responses (MCP 2025-03-26)
    #[serde(rename = "outputSchema", skip_serializing_if = "Option::is_none")]
    pub output_schema: Option<Value>,
    /// Tool behavior hints for clients (MCP 2025-03-26)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub annotations: Option<ToolAnnotations>,
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
    /// OAuth scopes from JWT (ADR-012 12-Scope Model)
    pub scopes: Vec<String>,
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

    /// Optional JSON Schema for output (MCP 2025-03-26)
    /// Override this to provide structured output schema
    fn output_schema(&self) -> Option<Value> {
        None
    }

    /// Required UAC action to execute this tool
    /// Override this to specify the action (default: Read)
    fn required_action(&self) -> Action {
        Action::Read
    }

    /// Execute the tool with given arguments
    async fn execute(&self, args: Value, ctx: &ToolContext) -> Result<ToolResult, ToolError>;

    /// Get tool definition for MCP tools/list (MCP 2025-03-26 compliant)
    fn definition(&self) -> ToolDefinition {
        // Auto-derive annotations from required_action
        let annotations = ToolAnnotations::from_action(self.required_action());

        ToolDefinition {
            name: self.name().to_string(),
            description: self.description().to_string(),
            input_schema: self.input_schema(),
            output_schema: self.output_schema(),
            annotations: Some(annotations),
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

    /// Unregister a tool by name (Phase 7: K8s CRD support)
    ///
    /// Returns true if the tool was found and removed, false otherwise.
    #[allow(dead_code)] // Used by k8s::CrdWatcher when k8s feature enabled
    pub fn unregister(&self, name: &str) -> bool {
        let removed = self.tools.write().remove(name).is_some();
        if removed {
            tracing::info!(tool = %name, "MCP tool unregistered");
        }
        removed
    }

    /// Check if a tool exists
    #[allow(dead_code)] // Used by k8s::CrdWatcher when k8s feature enabled
    pub fn exists(&self, name: &str) -> bool {
        self.tools.read().contains_key(name)
    }

    /// Get all tool names
    #[allow(dead_code)] // Used by k8s::CrdWatcher when k8s feature enabled
    pub fn names(&self) -> Vec<String> {
        self.tools.read().keys().cloned().collect()
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

    // === MCP 2025-03-26 Annotations Tests ===

    #[test]
    fn test_annotations_from_read_action() {
        let annotations = ToolAnnotations::from_action(Action::Read);
        assert_eq!(annotations.read_only_hint, Some(true));
        assert_eq!(annotations.destructive_hint, Some(false));
        assert_eq!(annotations.idempotent_hint, Some(true));
    }

    #[test]
    fn test_annotations_from_delete_action() {
        let annotations = ToolAnnotations::from_action(Action::Delete);
        assert_eq!(annotations.read_only_hint, Some(false));
        assert_eq!(annotations.destructive_hint, Some(true)); // Destructive!
        assert_eq!(annotations.idempotent_hint, Some(false));
    }

    #[test]
    fn test_annotations_from_create_action() {
        let annotations = ToolAnnotations::from_action(Action::Create);
        assert_eq!(annotations.read_only_hint, Some(false));
        assert_eq!(annotations.destructive_hint, Some(false));
        assert_eq!(annotations.idempotent_hint, Some(false)); // Create not idempotent
    }

    #[test]
    fn test_annotations_from_update_action() {
        let annotations = ToolAnnotations::from_action(Action::Update);
        assert_eq!(annotations.read_only_hint, Some(false));
        assert_eq!(annotations.destructive_hint, Some(false));
        assert_eq!(annotations.idempotent_hint, Some(true)); // Update is idempotent
    }

    #[test]
    fn test_tool_definition_includes_annotations() {
        let tool = StoaCreateApiTool::new(Arc::new(()), Arc::new(()), Arc::new(()));
        let def = tool.definition();

        // CreateApi → not read-only, not destructive
        let annotations = def.annotations.expect("annotations should be present");
        assert_eq!(annotations.read_only_hint, Some(false));
        assert_eq!(annotations.destructive_hint, Some(false));
        assert_eq!(annotations.idempotent_hint, Some(false)); // Create is not idempotent
    }

    #[test]
    fn test_annotations_serialization() {
        let annotations = ToolAnnotations::from_action(Action::Read).with_title("Read Data");

        let json = serde_json::to_value(&annotations).unwrap();
        assert_eq!(json["title"], "Read Data");
        assert_eq!(json["readOnlyHint"], true);
        assert_eq!(json["destructiveHint"], false);
    }

    #[test]
    fn test_tool_definition_serialization_with_annotations() {
        let tool = StoaCreateApiTool::new(Arc::new(()), Arc::new(()), Arc::new(()));
        let def = tool.definition();

        let json = serde_json::to_value(&def).unwrap();
        assert!(json.get("annotations").is_some());
        assert_eq!(json["annotations"]["readOnlyHint"], false);
    }

    // === Phase 7: Unregister Tests ===

    #[test]
    fn test_tool_registry_unregister() {
        let registry = ToolRegistry::new();

        let tool = Arc::new(StoaCreateApiTool::new(
            Arc::new(()),
            Arc::new(()),
            Arc::new(()),
        ));

        registry.register(tool);
        assert_eq!(registry.count(), 1);
        assert!(registry.exists("stoa_create_api"));

        // Unregister
        let removed = registry.unregister("stoa_create_api");
        assert!(removed);
        assert_eq!(registry.count(), 0);
        assert!(!registry.exists("stoa_create_api"));

        // tools/list should not show it
        let tools = registry.list(None);
        assert!(tools.is_empty());
    }

    #[test]
    fn test_tool_registry_unregister_nonexistent() {
        let registry = ToolRegistry::new();

        // Unregister non-existent tool
        let removed = registry.unregister("nonexistent_tool");
        assert!(!removed);
    }

    #[test]
    fn test_tool_registry_names() {
        let registry = ToolRegistry::new();

        let tool = Arc::new(StoaCreateApiTool::new(
            Arc::new(()),
            Arc::new(()),
            Arc::new(()),
        ));

        registry.register(tool);

        let names = registry.names();
        assert_eq!(names.len(), 1);
        assert!(names.contains(&"stoa_create_api".to_string()));
    }
}
