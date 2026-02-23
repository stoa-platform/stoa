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

pub mod api_bridge;
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
    /// Owning tenant (None = global tool visible to all tenants)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tenant_id: Option<String>,
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
}

/// Context provided to tool during execution
#[derive(Debug, Clone)]
pub struct ToolContext {
    pub tenant_id: String,
    pub user_id: Option<String>,
    pub user_email: Option<String>,
    pub request_id: String,
    pub roles: Vec<String>,
    /// OAuth scopes from JWT (ADR-012 12-Scope Model)
    pub scopes: Vec<String>,
    /// Raw JWT token for forwarding to downstream services (Control Plane)
    pub raw_token: Option<String>,
    /// Merged skill instructions from CSS cascade resolution (CAB-1365).
    /// Concatenated instructions from all matching skills, ordered by specificity.
    pub skill_instructions: Option<String>,
    /// Progress token from the client's `_meta.progressToken` (CAB-1345 Phase 3).
    /// When present, the tool can send incremental progress notifications over WebSocket.
    /// SSE connections always have this as `None` since SSE can't push mid-request.
    pub progress_token: Option<Value>,
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

    /// Owning tenant ID (None = global tool visible to all tenants)
    fn tenant_id(&self) -> Option<&str> {
        None
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
            tenant_id: self.tenant_id().map(|s| s.to_string()),
        }
    }
}

/// Tool execution error
#[derive(Debug, thiserror::Error)]
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

/// Registry of available tools with per-tenant staleness tracking (CAB-1317).
pub struct ToolRegistry {
    tools: RwLock<HashMap<String, Arc<dyn Tool>>>,
    /// Tracks when tools were last loaded for each tenant (CAB-1317 Phase 2).
    tenant_loaded_at: RwLock<HashMap<String, std::time::Instant>>,
}

impl ToolRegistry {
    pub fn new() -> Self {
        Self {
            tools: RwLock::new(HashMap::new()),
            tenant_loaded_at: RwLock::new(HashMap::new()),
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

    /// List all tools, optionally filtered by tenant.
    ///
    /// When `tenant_id` is Some, returns:
    /// - Global tools (tenant_id = None in definition)
    /// - Tenant-specific tools whose tenant_id matches
    ///
    /// When `tenant_id` is None, returns all tools.
    pub fn list(&self, tenant_id: Option<&str>) -> Vec<ToolDefinition> {
        self.tools
            .read()
            .values()
            .map(|t| t.definition())
            .filter(|def| match tenant_id {
                None => true, // No filter: return all
                Some(tid) => match &def.tenant_id {
                    None => true,        // Global tool: visible to all
                    Some(t) => t == tid, // Tenant tool: must match
                },
            })
            .collect()
    }

    /// Get tool count
    pub fn count(&self) -> usize {
        self.tools.read().len()
    }

    /// Unregister a tool by name (Phase 7: K8s CRD support)
    ///
    /// Returns true if the tool was found and removed, false otherwise.
    pub fn unregister(&self, name: &str) -> bool {
        let removed = self.tools.write().remove(name).is_some();
        if removed {
            tracing::info!(tool = %name, "MCP tool unregistered");
        }
        removed
    }

    /// Check if a tool exists
    pub fn exists(&self, name: &str) -> bool {
        self.tools.read().contains_key(name)
    }

    /// Get all tool names
    pub fn names(&self) -> Vec<String> {
        self.tools.read().keys().cloned().collect()
    }

    // === Staleness tracking (CAB-1317 Phase 2) ===

    /// Check if tools for a tenant are stale (older than `max_age`).
    /// Returns true if never loaded or if loaded longer than `max_age` ago.
    pub fn is_stale(&self, tenant_id: &str, max_age: std::time::Duration) -> bool {
        let loaded_at = self.tenant_loaded_at.read();
        match loaded_at.get(tenant_id) {
            None => true,
            Some(instant) => instant.elapsed() > max_age,
        }
    }

    /// Mark tools as freshly loaded for a tenant.
    pub fn mark_loaded(&self, tenant_id: &str) {
        self.tenant_loaded_at
            .write()
            .insert(tenant_id.to_string(), std::time::Instant::now());
    }

    /// Get the age of the tool cache for a tenant (None if never loaded).
    pub fn tenant_cache_age(&self, tenant_id: &str) -> Option<std::time::Duration> {
        self.tenant_loaded_at
            .read()
            .get(tenant_id)
            .map(|instant| instant.elapsed())
    }

    /// Remove all tools whose name starts with a given prefix.
    /// Used by MCP protocol binder to remove contract-generated tools.
    /// Returns the number of tools removed.
    pub fn remove_by_prefix(&self, prefix: &str) -> usize {
        let mut tools = self.tools.write();
        let before = tools.len();
        tools.retain(|name, _| !name.starts_with(prefix));
        before - tools.len()
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

/// STOA Create API Tool — creates APIs in the Control Plane catalog via REST.
pub struct StoaCreateApiTool {
    client: reqwest::Client,
    cp_base_url: String,
}

impl StoaCreateApiTool {
    pub fn new(client: reqwest::Client, cp_base_url: String) -> Self {
        Self {
            client,
            cp_base_url: cp_base_url.trim_end_matches('/').to_string(),
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

        let openapi_spec = args
            .get("openapi_spec")
            .and_then(|v| v.as_str())
            .ok_or_else(|| ToolError::InvalidArguments("Missing 'openapi_spec' field".into()))?;

        let url = format!("{}/v1/tenants/{}/apis", self.cp_base_url, ctx.tenant_id);

        let payload = serde_json::json!({
            "name": name,
            "version": version,
            "openapi_spec": openapi_spec,
        });

        let mut req = self.client.post(&url).json(&payload);
        if let Some(token) = &ctx.raw_token {
            req = req.header("Authorization", format!("Bearer {}", token));
        }

        let resp = req
            .send()
            .await
            .map_err(|e| ToolError::ExecutionFailed(format!("CP API request failed: {}", e)))?;

        if resp.status().is_success() {
            let body: Value = resp.json().await.unwrap_or_else(
                |_| serde_json::json!({"status": "created", "name": name, "version": version}),
            );
            Ok(ToolResult::text(
                serde_json::to_string_pretty(&body)
                    .unwrap_or_else(|_| format!("API '{}' v{} created", name, version)),
            ))
        } else {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            Err(ToolError::ExecutionFailed(format!(
                "CP API returned {}: {}",
                status, body
            )))
        }
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
            reqwest::Client::new(),
            "http://localhost:8000".to_string(),
        ));

        registry.register(tool);
        assert_eq!(registry.count(), 1);

        let retrieved = registry.get("stoa_create_api");
        assert!(retrieved.is_some());
        assert_eq!(retrieved.unwrap().required_action(), Action::CreateApi);
    }

    #[test]
    fn test_tool_definition() {
        let tool =
            StoaCreateApiTool::new(reqwest::Client::new(), "http://localhost:8000".to_string());

        let def = tool.definition();
        assert_eq!(def.name, "stoa_create_api");
        assert!(!def.description.is_empty());
        assert_eq!(def.input_schema.required.len(), 3);
    }

    #[test]
    fn test_required_action_override() {
        let tool =
            StoaCreateApiTool::new(reqwest::Client::new(), "http://localhost:8000".to_string());

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
        let tool =
            StoaCreateApiTool::new(reqwest::Client::new(), "http://localhost:8000".to_string());
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
        let tool =
            StoaCreateApiTool::new(reqwest::Client::new(), "http://localhost:8000".to_string());
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
            reqwest::Client::new(),
            "http://localhost:8000".to_string(),
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
            reqwest::Client::new(),
            "http://localhost:8000".to_string(),
        ));

        registry.register(tool);

        let names = registry.names();
        assert_eq!(names.len(), 1);
        assert!(names.contains(&"stoa_create_api".to_string()));
    }

    // === Tenant Filtering Tests (CAB-1250) ===

    #[test]
    fn test_list_no_filter_returns_all() {
        let registry = ToolRegistry::new();
        let tool = Arc::new(StoaCreateApiTool::new(
            reqwest::Client::new(),
            "http://localhost:8000".to_string(),
        ));
        registry.register(tool);
        // No tenant filter → returns all
        let tools = registry.list(None);
        assert_eq!(tools.len(), 1);
    }

    #[test]
    fn test_list_global_tool_visible_to_all_tenants() {
        let registry = ToolRegistry::new();
        // StoaCreateApiTool has no tenant_id override → global tool (tenant_id = None)
        let tool = Arc::new(StoaCreateApiTool::new(
            reqwest::Client::new(),
            "http://localhost:8000".to_string(),
        ));
        registry.register(tool);

        // Any tenant should see global tools
        let tools = registry.list(Some("acme"));
        assert_eq!(tools.len(), 1);
        let tools = registry.list(Some("other-tenant"));
        assert_eq!(tools.len(), 1);
    }

    #[test]
    fn test_tool_definition_tenant_id_none_by_default() {
        let tool =
            StoaCreateApiTool::new(reqwest::Client::new(), "http://localhost:8000".to_string());
        let def = tool.definition();
        assert!(def.tenant_id.is_none());
    }

    // === Staleness Tracking Tests (CAB-1317 Phase 2) ===

    #[test]
    fn test_is_stale_when_never_loaded() {
        let registry = ToolRegistry::new();
        // Never loaded → always stale
        assert!(registry.is_stale("acme", std::time::Duration::from_secs(300)));
    }

    #[test]
    fn test_is_stale_after_mark_loaded() {
        let registry = ToolRegistry::new();
        registry.mark_loaded("acme");
        // Just loaded → not stale with 5-min TTL
        assert!(!registry.is_stale("acme", std::time::Duration::from_secs(300)));
    }

    #[test]
    fn test_is_stale_with_zero_ttl() {
        let registry = ToolRegistry::new();
        registry.mark_loaded("acme");
        // Zero TTL → always stale (edge case)
        assert!(registry.is_stale("acme", std::time::Duration::from_secs(0)));
    }

    #[test]
    fn test_is_stale_different_tenants_independent() {
        let registry = ToolRegistry::new();
        registry.mark_loaded("acme");
        // acme loaded, other-tenant never loaded
        assert!(!registry.is_stale("acme", std::time::Duration::from_secs(300)));
        assert!(registry.is_stale("other-tenant", std::time::Duration::from_secs(300)));
    }

    #[test]
    fn test_mark_loaded_updates_timestamp() {
        let registry = ToolRegistry::new();
        registry.mark_loaded("acme");
        let age1 = registry.tenant_cache_age("acme").expect("should exist");
        // Re-mark should produce a newer (or equal) timestamp
        registry.mark_loaded("acme");
        let age2 = registry.tenant_cache_age("acme").expect("should exist");
        assert!(age2 <= age1);
    }

    #[test]
    fn test_tenant_cache_age_none_when_never_loaded() {
        let registry = ToolRegistry::new();
        assert!(registry.tenant_cache_age("ghost").is_none());
    }
}
