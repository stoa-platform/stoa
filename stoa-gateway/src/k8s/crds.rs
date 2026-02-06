//! K8s CRD Definitions
//!
//! Custom Resource Definitions for dynamic tool registration.
//!
//! Requires: `k8s` feature flag

#![cfg(feature = "k8s")]

use kube::CustomResource;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::Value;

// =============================================================================
// Tool CRD
// =============================================================================

/// An individual tool exposed via MCP
///
/// # Example YAML
///
/// ```yaml
/// apiVersion: gostoa.dev/v1alpha1
/// kind: Tool
/// metadata:
///   name: weather-forecast
///   namespace: tenant-acme
/// spec:
///   displayName: Weather Forecast
///   description: Get weather forecasts for a location
///   endpoint: https://api.weather.example/v1/forecast
///   method: POST
///   inputSchema:
///     type: object
///     properties:
///       location:
///         type: string
///     required: [location]
///   auth: bearer
///   rateLimit: "100/min"
/// ```
#[derive(CustomResource, Debug, Clone, Serialize, Deserialize, JsonSchema)]
#[kube(
    group = "gostoa.dev",
    version = "v1alpha1",
    kind = "Tool",
    namespaced,
    status = "ToolStatus",
    printcolumn = r#"{"name":"Display Name","type":"string","jsonPath":".spec.displayName"}"#,
    printcolumn = r#"{"name":"Endpoint","type":"string","jsonPath":".spec.endpoint"}"#,
    printcolumn = r#"{"name":"Registered","type":"boolean","jsonPath":".status.registered"}"#
)]
#[serde(rename_all = "camelCase")]
pub struct ToolSpec {
    /// Human-readable display name
    pub display_name: String,

    /// Tool description for LLM context
    pub description: String,

    /// HTTP endpoint of the backend service
    pub endpoint: String,

    /// HTTP method (GET, POST, PUT, DELETE)
    pub method: String,

    /// JSON Schema for tool input arguments
    pub input_schema: Value,

    /// Optional JSON Schema for tool output
    #[serde(skip_serializing_if = "Option::is_none")]
    pub output_schema: Option<Value>,

    /// Authentication type: "bearer", "service_account", "none"
    #[serde(default = "default_auth")]
    pub auth: String,

    /// Rate limit expression: "100/min", "1000/hour"
    #[serde(skip_serializing_if = "Option::is_none")]
    pub rate_limit: Option<String>,

    /// MCP tool annotations
    #[serde(skip_serializing_if = "Option::is_none")]
    pub annotations: Option<ToolAnnotationsCrd>,
}

fn default_auth() -> String {
    "none".to_string()
}

/// Tool status (updated by controller)
#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema, Default)]
#[serde(rename_all = "camelCase")]
pub struct ToolStatus {
    /// Whether the tool is registered in the gateway
    #[serde(default)]
    pub registered: bool,

    /// Last time the tool was seen/updated
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_seen: Option<String>,

    /// Error message if registration failed
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

/// MCP tool annotations from CRD
#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "camelCase")]
pub struct ToolAnnotationsCrd {
    /// If true, tool only reads data
    #[serde(skip_serializing_if = "Option::is_none")]
    pub read_only: Option<bool>,

    /// If true, tool may perform destructive actions
    #[serde(skip_serializing_if = "Option::is_none")]
    pub destructive: Option<bool>,

    /// If true, tool is idempotent
    #[serde(skip_serializing_if = "Option::is_none")]
    pub idempotent: Option<bool>,

    /// If true, tool interacts with external world
    #[serde(skip_serializing_if = "Option::is_none")]
    pub open_world: Option<bool>,
}

// =============================================================================
// ToolSet CRD
// =============================================================================

/// A collection of tools from an upstream MCP server
///
/// # Example YAML
///
/// ```yaml
/// apiVersion: gostoa.dev/v1alpha1
/// kind: ToolSet
/// metadata:
///   name: openai-tools
///   namespace: tenant-acme
/// spec:
///   upstream:
///     url: https://mcp.openai.com
///     transport: sse
///     auth:
///       type: bearer
///       secretRef: openai-api-key
///   tools: []  # Empty = all tools
/// ```
#[derive(CustomResource, Debug, Clone, Serialize, Deserialize, JsonSchema)]
#[kube(
    group = "gostoa.dev",
    version = "v1alpha1",
    kind = "ToolSet",
    namespaced,
    status = "ToolSetStatus",
    printcolumn = r#"{"name":"Upstream","type":"string","jsonPath":".spec.upstream.url"}"#,
    printcolumn = r#"{"name":"Tools","type":"integer","jsonPath":".status.toolCount"}"#,
    printcolumn = r#"{"name":"Connected","type":"boolean","jsonPath":".status.connected"}"#
)]
#[serde(rename_all = "camelCase")]
pub struct ToolSetSpec {
    /// Upstream MCP server configuration
    pub upstream: UpstreamConfig,

    /// List of tool names to expose (empty = all tools)
    #[serde(default)]
    pub tools: Vec<String>,

    /// Prefix to add to tool names (to avoid collisions)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub prefix: Option<String>,
}

/// Upstream MCP server configuration
#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "camelCase")]
pub struct UpstreamConfig {
    /// MCP server URL
    pub url: String,

    /// Transport type: "sse" or "streamable-http"
    #[serde(default = "default_transport")]
    pub transport: String,

    /// Authentication configuration
    #[serde(skip_serializing_if = "Option::is_none")]
    pub auth: Option<UpstreamAuth>,

    /// Connection timeout in seconds
    #[serde(skip_serializing_if = "Option::is_none")]
    pub timeout_seconds: Option<u32>,
}

fn default_transport() -> String {
    "sse".to_string()
}

/// Upstream authentication configuration
#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "camelCase")]
pub struct UpstreamAuth {
    /// Auth type: "bearer" or "header"
    #[serde(rename = "type")]
    pub auth_type: String,

    /// K8s Secret reference containing the credential
    pub secret_ref: String,

    /// Header name (for "header" type)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub header_name: Option<String>,
}

/// ToolSet status
#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema, Default)]
#[serde(rename_all = "camelCase")]
pub struct ToolSetStatus {
    /// Whether connected to upstream
    #[serde(default)]
    pub connected: bool,

    /// Number of tools discovered
    #[serde(default)]
    pub tool_count: u32,

    /// List of discovered tool names
    #[serde(default)]
    pub discovered_tools: Vec<String>,

    /// Last successful sync timestamp
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_sync: Option<String>,

    /// Error message if connection failed
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_tool_spec_serialization() {
        let spec = ToolSpec {
            display_name: "Weather API".to_string(),
            description: "Get weather forecasts".to_string(),
            endpoint: "https://api.example.com/weather".to_string(),
            method: "POST".to_string(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "location": {"type": "string"}
                }
            }),
            output_schema: None,
            auth: "bearer".to_string(),
            rate_limit: Some("100/min".to_string()),
            annotations: Some(ToolAnnotationsCrd {
                read_only: Some(true),
                destructive: Some(false),
                idempotent: Some(true),
                open_world: Some(true),
            }),
        };

        let json = serde_json::to_value(&spec).unwrap();
        assert_eq!(json["displayName"], "Weather API");
        assert_eq!(json["annotations"]["readOnly"], true);
    }

    #[test]
    fn test_toolset_spec_serialization() {
        let spec = ToolSetSpec {
            upstream: UpstreamConfig {
                url: "https://mcp.example.com".to_string(),
                transport: "sse".to_string(),
                auth: Some(UpstreamAuth {
                    auth_type: "bearer".to_string(),
                    secret_ref: "api-token".to_string(),
                    header_name: None,
                }),
                timeout_seconds: Some(30),
            },
            tools: vec!["tool1".to_string()],
            prefix: Some("ext_".to_string()),
        };

        let json = serde_json::to_value(&spec).unwrap();
        assert_eq!(json["upstream"]["url"], "https://mcp.example.com");
        assert_eq!(json["prefix"], "ext_");
    }

    #[test]
    fn test_tool_status_default() {
        let status = ToolStatus::default();
        assert!(!status.registered);
        assert!(status.last_seen.is_none());
    }

    #[test]
    fn test_toolset_status_default() {
        let status = ToolSetStatus::default();
        assert!(!status.connected);
        assert_eq!(status.tool_count, 0);
    }
}
