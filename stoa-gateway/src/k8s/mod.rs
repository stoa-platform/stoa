//! Kubernetes CRD Integration for STOA Gateway
//!
//! This module provides Kubernetes-native tool registration via Custom Resource Definitions.
//! Tools and ToolSets can be defined as K8s resources and are automatically synchronized
//! to the gateway's tool registry.
//!
//! # CRD Types
//!
//! - **Tool**: Single tool definition with endpoint, schema, and auth configuration
//! - **ToolSet**: Collection of tools from an upstream MCP server or composed from multiple tools
//!
//! # Architecture
//!
//! The CRD watcher uses `kube-runtime` to watch for Tool and ToolSet resources across
//! all namespaces. Namespace maps to tenant_id for multi-tenant isolation.
//!
//! ```text
//! K8s API Server
//!       │
//!       ▼
//! ┌─────────────────┐
//! │   CRD Watcher   │ ← watches Tool, ToolSet CRDs
//! └────────┬────────┘
//!          │
//!          ▼
//! ┌─────────────────┐
//! │  Tool Registry  │ ← dynamic tool add/remove
//! └─────────────────┘
//! ```

#![allow(dead_code)] // Phase 7 methods will be wired incrementally

pub mod watcher;

use k8s_openapi::apiextensions_apiserver::pkg::apis::apiextensions::v1::CustomResourceDefinition;
use kube::{CustomResource, CustomResourceExt};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// Re-exports
pub use watcher::CrdWatcher;

/// Tool Custom Resource Definition
///
/// Defines a single tool that can be invoked via MCP protocol.
/// Namespace maps to tenant_id for multi-tenant isolation.
///
/// Example YAML:
/// ```yaml
/// apiVersion: gostoa.dev/v1alpha1
/// kind: Tool
/// metadata:
///   name: billing-create-invoice
///   namespace: tenant-acme
/// spec:
///   displayName: Create Invoice
///   description: Create a new invoice in the billing system
///   endpoint: https://billing.acme.com/v1/invoices
///   method: POST
///   inputSchema:
///     type: object
///     properties:
///       customer_id:
///         type: string
///       amount:
///         type: number
///     required: [customer_id, amount]
///   auth:
///     type: service_account
///     secretRef: billing-sa-token
///   rateLimit: 100/min
///   timeout: 30s
///   annotations:
///     readOnlyHint: false
///     destructiveHint: false
///     idempotentHint: false
/// ```
#[derive(CustomResource, Debug, Clone, Serialize, Deserialize, JsonSchema)]
#[kube(
    group = "gostoa.dev",
    version = "v1alpha1",
    kind = "Tool",
    namespaced,
    status = "ToolStatus",
    shortname = "tl",
    printcolumn = r#"{"name":"Display Name","type":"string","jsonPath":".spec.displayName"}"#,
    printcolumn = r#"{"name":"Endpoint","type":"string","jsonPath":".spec.endpoint"}"#,
    printcolumn = r#"{"name":"Ready","type":"string","jsonPath":".status.ready"}"#
)]
#[serde(rename_all = "camelCase")]
pub struct ToolSpec {
    /// Human-readable display name for the tool
    pub display_name: String,

    /// Detailed description of what the tool does
    pub description: String,

    /// Backend endpoint URL to call when tool is invoked
    pub endpoint: String,

    /// HTTP method for the backend call
    #[serde(default = "default_method")]
    pub method: String,

    /// JSON Schema defining the tool's input parameters
    #[serde(default)]
    pub input_schema: serde_json::Value,

    /// JSON Schema defining the tool's output (optional, for MCP 2025 spec)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub output_schema: Option<serde_json::Value>,

    /// Authentication configuration for backend calls
    #[serde(skip_serializing_if = "Option::is_none")]
    pub auth: Option<ToolAuth>,

    /// Rate limit specification (e.g., "100/min", "1000/hour")
    #[serde(skip_serializing_if = "Option::is_none")]
    pub rate_limit: Option<String>,

    /// Request timeout (e.g., "30s", "1m")
    #[serde(default = "default_timeout")]
    pub timeout: String,

    /// MCP 2025 tool annotations
    #[serde(skip_serializing_if = "Option::is_none")]
    pub annotations: Option<ToolAnnotations>,

    /// Additional headers to include in backend requests
    #[serde(default)]
    pub headers: HashMap<String, String>,

    /// Whether this tool requires user confirmation before execution
    #[serde(default)]
    pub requires_confirmation: bool,
}

fn default_method() -> String {
    "POST".to_string()
}

fn default_timeout() -> String {
    "30s".to_string()
}

/// Tool authentication configuration
#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "camelCase")]
pub struct ToolAuth {
    /// Authentication type: bearer, api_key, service_account, mtls, none
    #[serde(rename = "type")]
    pub auth_type: String,

    /// Reference to K8s Secret containing credentials
    #[serde(skip_serializing_if = "Option::is_none")]
    pub secret_ref: Option<String>,

    /// Header name for API key auth (default: X-API-Key)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub header_name: Option<String>,

    /// Whether to pass through the user's token
    #[serde(default)]
    pub passthrough_user_token: bool,
}

/// MCP 2025 tool annotations (hints for AI clients)
#[derive(Debug, Clone, Default, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "camelCase")]
pub struct ToolAnnotations {
    /// Human-readable title for UI display
    #[serde(skip_serializing_if = "Option::is_none")]
    pub title: Option<String>,

    /// Hint that tool only reads data (no side effects)
    #[serde(default)]
    pub read_only_hint: bool,

    /// Hint that tool performs destructive operations
    #[serde(default)]
    pub destructive_hint: bool,

    /// Hint that tool is idempotent (safe to retry)
    #[serde(default)]
    pub idempotent_hint: bool,

    /// Hint that tool may access external systems beyond its description
    #[serde(default)]
    pub open_world_hint: bool,
}

/// Tool resource status
#[derive(Debug, Clone, Default, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "camelCase")]
pub struct ToolStatus {
    /// Whether the tool is ready for invocation
    #[serde(default)]
    pub ready: bool,

    /// Last observed generation (for reconciliation)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub observed_generation: Option<i64>,

    /// Human-readable status message
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message: Option<String>,

    /// Last time the tool was successfully validated
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_validated: Option<String>,

    /// Conditions following K8s conventions
    #[serde(default)]
    pub conditions: Vec<ToolCondition>,
}

/// Status condition for Tool resource
#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "camelCase")]
pub struct ToolCondition {
    /// Type of condition: Ready, Validated, EndpointReachable
    #[serde(rename = "type")]
    pub condition_type: String,

    /// Status: True, False, Unknown
    pub status: String,

    /// Last time the condition transitioned
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_transition_time: Option<String>,

    /// Machine-readable reason for condition
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,

    /// Human-readable message
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message: Option<String>,
}

/// ToolSet Custom Resource Definition
///
/// Defines a collection of tools, either from an upstream MCP server
/// or composed from multiple tool invocations.
///
/// Example YAML (upstream federation):
/// ```yaml
/// apiVersion: gostoa.dev/v1alpha1
/// kind: ToolSet
/// metadata:
///   name: github-tools
///   namespace: tenant-acme
/// spec:
///   upstream:
///     url: https://github-mcp.internal/sse
///     transport: sse
///     auth:
///       type: bearer
///       secretRef: github-token
///   tools:
///     - name: github_create_pr
///     - name: github_list_repos
/// ```
///
/// Example YAML (tool composition):
/// ```yaml
/// apiVersion: gostoa.dev/v1alpha1
/// kind: ToolSet
/// metadata:
///   name: onboarding-workflow
///   namespace: tenant-acme
/// spec:
///   composition:
///     name: stoa_onboard_api
///     description: Complete API onboarding workflow
///     steps:
///       - tool: stoa_create_api
///         map:
///           name: "$.input.name"
///           version: "$.input.version"
///       - tool: stoa_deploy_api
///         map:
///           api_id: "$.steps[0].result.api_id"
///           env: "dev"
///       - tool: stoa_subscribe_api
///         map:
///           api_id: "$.steps[0].result.api_id"
///           tenant_id: "$.context.tenant_id"
/// ```
#[derive(CustomResource, Debug, Clone, Serialize, Deserialize, JsonSchema)]
#[kube(
    group = "gostoa.dev",
    version = "v1alpha1",
    kind = "ToolSet",
    namespaced,
    status = "ToolSetStatus",
    shortname = "ts",
    printcolumn = r#"{"name":"Type","type":"string","jsonPath":".spec.type"}"#,
    printcolumn = r#"{"name":"Tools","type":"integer","jsonPath":".status.toolCount"}"#,
    printcolumn = r#"{"name":"Ready","type":"string","jsonPath":".status.ready"}"#
)]
#[serde(rename_all = "camelCase")]
pub struct ToolSetSpec {
    /// Type of toolset: upstream (federation) or composition
    #[serde(rename = "type", default = "default_toolset_type")]
    pub toolset_type: String,

    /// Upstream MCP server configuration (for federation)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub upstream: Option<UpstreamConfig>,

    /// Tool composition configuration
    #[serde(skip_serializing_if = "Option::is_none")]
    pub composition: Option<CompositionConfig>,

    /// List of tools to include (for upstream filtering)
    #[serde(default)]
    pub tools: Vec<ToolReference>,

    /// Whether to auto-discover tools from upstream (default: true)
    #[serde(default = "default_true")]
    pub auto_discover: bool,

    /// Refresh interval for tool discovery (e.g., "5m", "1h")
    #[serde(default = "default_refresh_interval")]
    pub refresh_interval: String,
}

fn default_toolset_type() -> String {
    "upstream".to_string()
}

fn default_true() -> bool {
    true
}

fn default_refresh_interval() -> String {
    "5m".to_string()
}

/// Upstream MCP server configuration for federation
#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "camelCase")]
pub struct UpstreamConfig {
    /// URL of the upstream MCP server
    pub url: String,

    /// Transport protocol: sse, websocket, stdio
    #[serde(default = "default_transport")]
    pub transport: String,

    /// Authentication for upstream server
    #[serde(skip_serializing_if = "Option::is_none")]
    pub auth: Option<ToolAuth>,

    /// Connection timeout
    #[serde(default = "default_timeout")]
    pub timeout: String,

    /// Maximum retries for failed connections
    #[serde(default = "default_max_retries")]
    pub max_retries: u32,

    /// Whether to apply gateway policies to upstream calls
    #[serde(default = "default_true")]
    pub apply_policies: bool,

    /// Whether to meter upstream tool calls
    #[serde(default = "default_true")]
    pub metering_enabled: bool,
}

fn default_transport() -> String {
    "sse".to_string()
}

fn default_max_retries() -> u32 {
    3
}

/// Tool composition configuration
#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "camelCase")]
pub struct CompositionConfig {
    /// Name of the composed tool
    pub name: String,

    /// Description of the composed tool
    pub description: String,

    /// Input schema for the composed tool
    #[serde(default)]
    pub input_schema: serde_json::Value,

    /// Sequential steps to execute
    pub steps: Vec<CompositionStep>,

    /// Error handling strategy: fail_fast, continue, rollback
    #[serde(default = "default_error_strategy")]
    pub error_strategy: String,
}

fn default_error_strategy() -> String {
    "fail_fast".to_string()
}

/// Single step in a tool composition
#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "camelCase")]
pub struct CompositionStep {
    /// Name of the step (for referencing in subsequent steps)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,

    /// Tool to invoke
    pub tool: String,

    /// JSONPath mappings from input/previous steps to tool arguments
    #[serde(default)]
    pub map: HashMap<String, String>,

    /// Condition for executing this step (JSONPath expression)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub condition: Option<String>,

    /// Whether to continue on error
    #[serde(default)]
    pub continue_on_error: bool,
}

/// Reference to a tool (for filtering in ToolSets)
#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "camelCase")]
pub struct ToolReference {
    /// Tool name
    pub name: String,

    /// Optional alias for the tool (renames it in the registry)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub alias: Option<String>,

    /// Whether this tool is enabled
    #[serde(default = "default_true")]
    pub enabled: bool,
}

/// ToolSet resource status
#[derive(Debug, Clone, Default, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "camelCase")]
pub struct ToolSetStatus {
    /// Whether the toolset is ready
    #[serde(default)]
    pub ready: bool,

    /// Number of tools registered from this toolset
    #[serde(default)]
    pub tool_count: i32,

    /// Last observed generation
    #[serde(skip_serializing_if = "Option::is_none")]
    pub observed_generation: Option<i64>,

    /// Human-readable status message
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message: Option<String>,

    /// Last time tools were synchronized
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_sync: Option<String>,

    /// List of discovered/registered tool names
    #[serde(default)]
    pub registered_tools: Vec<String>,

    /// Conditions
    #[serde(default)]
    pub conditions: Vec<ToolCondition>,
}

/// Configuration for the K8s CRD watcher
#[derive(Debug, Clone)]
pub struct K8sConfig {
    /// Whether K8s watcher is enabled
    pub enabled: bool,

    /// Namespace to watch (None = all namespaces)
    pub namespace: Option<String>,

    /// Label selector for filtering resources
    pub label_selector: Option<String>,

    /// Resync interval for reconciliation
    pub resync_interval: std::time::Duration,

    /// Whether to use in-cluster config (vs kubeconfig)
    pub in_cluster: bool,
}

impl Default for K8sConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            namespace: None,
            label_selector: None,
            resync_interval: std::time::Duration::from_secs(300),
            in_cluster: true,
        }
    }
}

impl K8sConfig {
    /// Create config from environment variables
    pub fn from_env() -> Self {
        let enabled = std::env::var("K8S_WATCHER_ENABLED")
            .map(|v| v.to_lowercase() == "true")
            .unwrap_or(false);

        let namespace = std::env::var("K8S_WATCH_NAMESPACE").ok();

        let label_selector = std::env::var("K8S_LABEL_SELECTOR").ok();

        let resync_secs = std::env::var("K8S_RESYNC_INTERVAL_SECS")
            .ok()
            .and_then(|v| v.parse().ok())
            .unwrap_or(300);

        let in_cluster = std::env::var("K8S_IN_CLUSTER")
            .map(|v| v.to_lowercase() != "false")
            .unwrap_or(true);

        Self {
            enabled,
            namespace,
            label_selector,
            resync_interval: std::time::Duration::from_secs(resync_secs),
            in_cluster,
        }
    }
}

/// Generate the Tool CRD definition for kubectl apply
pub fn tool_crd() -> CustomResourceDefinition {
    serde_json::from_value(serde_json::json!({
        "apiVersion": "apiextensions.k8s.io/v1",
        "kind": "CustomResourceDefinition",
        "metadata": {
            "name": "tools.gostoa.dev"
        },
        "spec": {
            "group": "gostoa.dev",
            "versions": [{
                "name": "v1alpha1",
                "served": true,
                "storage": true,
                "schema": {
                    "openAPIV3Schema": Tool::crd().spec.versions[0].schema.clone()
                },
                "subresources": {
                    "status": {}
                },
                "additionalPrinterColumns": [
                    {"name": "Display Name", "type": "string", "jsonPath": ".spec.displayName"},
                    {"name": "Endpoint", "type": "string", "jsonPath": ".spec.endpoint"},
                    {"name": "Ready", "type": "string", "jsonPath": ".status.ready"}
                ]
            }],
            "scope": "Namespaced",
            "names": {
                "plural": "tools",
                "singular": "tool",
                "kind": "Tool",
                "shortNames": ["tl"]
            }
        }
    }))
    .expect("valid CRD JSON")
}

/// Generate the ToolSet CRD definition for kubectl apply
pub fn toolset_crd() -> CustomResourceDefinition {
    serde_json::from_value(serde_json::json!({
        "apiVersion": "apiextensions.k8s.io/v1",
        "kind": "CustomResourceDefinition",
        "metadata": {
            "name": "toolsets.gostoa.dev"
        },
        "spec": {
            "group": "gostoa.dev",
            "versions": [{
                "name": "v1alpha1",
                "served": true,
                "storage": true,
                "schema": {
                    "openAPIV3Schema": ToolSet::crd().spec.versions[0].schema.clone()
                },
                "subresources": {
                    "status": {}
                },
                "additionalPrinterColumns": [
                    {"name": "Type", "type": "string", "jsonPath": ".spec.type"},
                    {"name": "Tools", "type": "integer", "jsonPath": ".status.toolCount"},
                    {"name": "Ready", "type": "string", "jsonPath": ".status.ready"}
                ]
            }],
            "scope": "Namespaced",
            "names": {
                "plural": "toolsets",
                "singular": "toolset",
                "kind": "ToolSet",
                "shortNames": ["ts"]
            }
        }
    }))
    .expect("valid CRD JSON")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tool_crd_generation() {
        let crd = Tool::crd();
        assert_eq!(crd.spec.group, "gostoa.dev");
        assert_eq!(crd.spec.names.kind, "Tool");
        assert_eq!(crd.spec.names.plural, "tools");
    }

    #[test]
    fn test_toolset_crd_generation() {
        let crd = ToolSet::crd();
        assert_eq!(crd.spec.group, "gostoa.dev");
        assert_eq!(crd.spec.names.kind, "ToolSet");
        assert_eq!(crd.spec.names.plural, "toolsets");
    }

    #[test]
    fn test_tool_spec_serialization() {
        let spec = ToolSpec {
            display_name: "Test Tool".to_string(),
            description: "A test tool".to_string(),
            endpoint: "https://api.example.com/test".to_string(),
            method: "POST".to_string(),
            input_schema: serde_json::json!({
                "type": "object",
                "properties": {
                    "name": {"type": "string"}
                }
            }),
            output_schema: None,
            auth: Some(ToolAuth {
                auth_type: "bearer".to_string(),
                secret_ref: Some("my-secret".to_string()),
                header_name: None,
                passthrough_user_token: false,
            }),
            rate_limit: Some("100/min".to_string()),
            timeout: "30s".to_string(),
            annotations: Some(ToolAnnotations {
                title: Some("Test".to_string()),
                read_only_hint: true,
                destructive_hint: false,
                idempotent_hint: true,
                open_world_hint: false,
            }),
            headers: HashMap::new(),
            requires_confirmation: false,
        };

        let json = serde_json::to_string(&spec).unwrap();
        assert!(json.contains("Test Tool"));
        assert!(json.contains("readOnlyHint"));
    }

    #[test]
    fn test_k8s_config_from_env() {
        // Test default values
        let config = K8sConfig::default();
        assert!(!config.enabled);
        assert!(config.namespace.is_none());
        assert!(config.in_cluster);
    }

    #[test]
    fn test_composition_step() {
        let step = CompositionStep {
            name: Some("create".to_string()),
            tool: "stoa_create_api".to_string(),
            map: [("name".to_string(), "$.input.name".to_string())]
                .into_iter()
                .collect(),
            condition: Some("$.input.create == true".to_string()),
            continue_on_error: false,
        };

        let json = serde_json::to_string(&step).unwrap();
        assert!(json.contains("stoa_create_api"));
        assert!(json.contains("$.input.name"));
    }
}
