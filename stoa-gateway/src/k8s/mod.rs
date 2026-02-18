//! K8s CRD Module (Phase 7: CAB-1105)
//!
//! Dynamic tool registration via Kubernetes Custom Resource Definitions.
//! Enables GitOps-style tool management without code changes.
//!
//! # CRDs
//!
//! - `Tool` - Individual tool exposed via MCP
//! - `ToolSet` - Collection of tools from an upstream MCP server
//!
//! # Tenant Isolation
//!
//! K8s namespace = tenant_id. Tools in namespace X are only visible to tenant X.
//!
//! Note: Requires `k8s` feature flag. Without it, the module provides no-op stubs.

#[cfg(feature = "k8s")]
pub mod crds;
#[cfg(feature = "k8s")]
pub mod watcher;

#[cfg(feature = "k8s")]
pub use crds::{Skill, SkillSpec, SkillStatus, Tool, ToolSet, ToolSetSpec, ToolSpec};
#[cfg(feature = "k8s")]
pub use watcher::CrdWatcher;

// Stub types when k8s feature is disabled
#[cfg(not(feature = "k8s"))]
pub mod stubs {
    //! Stub types when k8s feature is disabled
    #![allow(dead_code)]

    use serde::{Deserialize, Serialize};
    use serde_json::Value;

    /// Stub Tool spec for when k8s feature is disabled
    #[derive(Debug, Clone, Serialize, Deserialize)]
    pub struct ToolSpec {
        pub display_name: String,
        pub description: String,
        pub endpoint: String,
        pub method: String,
        pub input_schema: Value,
        #[serde(skip_serializing_if = "Option::is_none")]
        pub output_schema: Option<Value>,
        #[serde(default = "default_auth")]
        pub auth: String,
        #[serde(skip_serializing_if = "Option::is_none")]
        pub rate_limit: Option<String>,
        #[serde(skip_serializing_if = "Option::is_none")]
        pub annotations: Option<ToolAnnotationsCrd>,
    }

    fn default_auth() -> String {
        "none".to_string()
    }

    /// Stub ToolSet spec
    #[derive(Debug, Clone, Serialize, Deserialize)]
    pub struct ToolSetSpec {
        pub upstream: UpstreamConfig,
        #[serde(default)]
        pub tools: Vec<String>,
    }

    /// Upstream MCP server configuration
    #[derive(Debug, Clone, Serialize, Deserialize)]
    pub struct UpstreamConfig {
        pub url: String,
        pub transport: String,
        #[serde(skip_serializing_if = "Option::is_none")]
        pub auth: Option<UpstreamAuth>,
    }

    /// Upstream authentication configuration
    #[derive(Debug, Clone, Serialize, Deserialize)]
    pub struct UpstreamAuth {
        pub auth_type: String,
        pub secret_ref: String,
    }

    /// Tool annotations for CRD
    #[derive(Debug, Clone, Serialize, Deserialize)]
    pub struct ToolAnnotationsCrd {
        #[serde(skip_serializing_if = "Option::is_none")]
        pub read_only: Option<bool>,
        #[serde(skip_serializing_if = "Option::is_none")]
        pub destructive: Option<bool>,
        #[serde(skip_serializing_if = "Option::is_none")]
        pub idempotent: Option<bool>,
    }
}

#[cfg(not(feature = "k8s"))]
pub use stubs::*;

#[cfg(test)]
mod tests {
    #[test]
    #[cfg(not(feature = "k8s"))]
    fn test_tool_spec_serialization() {
        use super::*;
        use serde_json::json;

        let spec = ToolSpec {
            display_name: "Weather API".to_string(),
            description: "Get weather forecasts".to_string(),
            endpoint: "https://api.weather.example/v1/forecast".to_string(),
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
            annotations: None,
        };

        let json_val = serde_json::to_value(&spec).unwrap();
        assert_eq!(json_val["display_name"], "Weather API");
        assert_eq!(json_val["method"], "POST");
    }

    #[test]
    #[cfg(not(feature = "k8s"))]
    fn test_toolset_spec_serialization() {
        use super::*;

        let spec = ToolSetSpec {
            upstream: UpstreamConfig {
                url: "https://mcp.example.com".to_string(),
                transport: "sse".to_string(),
                auth: Some(UpstreamAuth {
                    auth_type: "bearer".to_string(),
                    secret_ref: "mcp-token-secret".to_string(),
                }),
            },
            tools: vec!["tool1".to_string(), "tool2".to_string()],
        };

        let json_val = serde_json::to_value(&spec).unwrap();
        assert_eq!(json_val["upstream"]["url"], "https://mcp.example.com");
        assert_eq!(json_val["upstream"]["transport"], "sse");
        assert_eq!(json_val["tools"].as_array().unwrap().len(), 2);
    }
}
