//! Dynamic Tool — HTTP endpoint tool created from K8s CRD or admin API
//!
//! Phase 7 (CAB-1105): Tools registered dynamically from Tool CRDs.
//! Each DynamicTool wraps an HTTP endpoint and exposes it as an MCP tool.

#![allow(dead_code)]

use async_trait::async_trait;
use reqwest::Client;
use serde_json::Value;
use tracing::{debug, warn};

use super::{Tool, ToolAnnotations, ToolContext, ToolError, ToolResult, ToolSchema};
use crate::uac::Action;

/// A dynamically registered tool that calls an HTTP endpoint.
///
/// Created from K8s Tool CRDs or admin API.
/// Namespace = tenant_id for isolation.
pub struct DynamicTool {
    /// Tool name ({namespace}_{crd_name})
    name: String,
    /// Human-readable description
    description: String,
    /// HTTP endpoint URL
    endpoint: String,
    /// HTTP method (GET, POST, PUT, DELETE)
    method: String,
    /// JSON Schema for input
    input_schema: ToolSchema,
    /// Optional output schema
    output_schema: Option<Value>,
    /// Tool annotations (MCP 2025-03-26)
    annotations: Option<ToolAnnotations>,
    /// Required UAC action
    action: Action,
    /// Tenant ID for isolation (from CRD namespace)
    tenant_id: String,
    /// Skip tenant isolation check (for catalog API tools accessible to all)
    public: bool,
    /// HTTP client
    client: Client,
}

impl DynamicTool {
    /// Create a new DynamicTool from CRD-style parameters
    pub fn new(
        name: impl Into<String>,
        description: impl Into<String>,
        endpoint: impl Into<String>,
        method: impl Into<String>,
        input_schema: ToolSchema,
        tenant_id: impl Into<String>,
    ) -> Self {
        Self {
            name: name.into(),
            description: description.into(),
            endpoint: endpoint.into(),
            method: method.into(),
            input_schema,
            output_schema: None,
            annotations: None,
            action: Action::Read,
            tenant_id: tenant_id.into(),
            public: false,
            client: Client::builder()
                .timeout(std::time::Duration::from_secs(30))
                .build()
                .expect("HTTP client"),
        }
    }

    pub fn with_output_schema(mut self, schema: Value) -> Self {
        self.output_schema = Some(schema);
        self
    }

    pub fn with_annotations(mut self, annotations: ToolAnnotations) -> Self {
        self.annotations = Some(annotations);
        self
    }

    pub fn with_action(mut self, action: Action) -> Self {
        self.action = action;
        self
    }

    /// Mark tool as public (skip tenant isolation, for catalog API tools)
    pub fn into_public(mut self) -> Self {
        self.public = true;
        self
    }
}

#[async_trait]
impl Tool for DynamicTool {
    fn name(&self) -> &str {
        &self.name
    }

    fn description(&self) -> &str {
        &self.description
    }

    fn input_schema(&self) -> ToolSchema {
        self.input_schema.clone()
    }

    fn output_schema(&self) -> Option<Value> {
        self.output_schema.clone()
    }

    fn required_action(&self) -> Action {
        self.action
    }

    async fn execute(&self, args: Value, ctx: &ToolContext) -> Result<ToolResult, ToolError> {
        // Tenant isolation: CRD namespace must match caller tenant
        // Public tools (catalog API bridge) skip this check
        if !self.public && ctx.tenant_id != self.tenant_id {
            return Err(ToolError::PermissionDenied(format!(
                "Tool {} not available for tenant {}",
                self.name, ctx.tenant_id
            )));
        }

        debug!(
            tool = %self.name,
            endpoint = %self.endpoint,
            method = %self.method,
            "Executing dynamic tool"
        );

        // Build HTTP request
        let mut req = match self.method.to_uppercase().as_str() {
            "GET" => self.client.get(&self.endpoint),
            "POST" => self.client.post(&self.endpoint),
            "PUT" => self.client.put(&self.endpoint),
            "DELETE" => self.client.delete(&self.endpoint),
            "PATCH" => self.client.patch(&self.endpoint),
            other => {
                return Err(ToolError::ExecutionFailed(format!(
                    "Unsupported HTTP method: {}",
                    other
                )));
            }
        };

        // Forward auth token if available
        if let Some(ref token) = ctx.raw_token {
            req = req.header("Authorization", format!("Bearer {}", token));
        }

        // Send arguments as JSON body for POST/PUT/PATCH
        let has_body = matches!(
            self.method.to_uppercase().as_str(),
            "POST" | "PUT" | "PATCH"
        );
        if has_body && !args.is_null() {
            req = req.json(&args);
        }

        // Execute request
        let response = req.send().await.map_err(|e| {
            warn!(tool = %self.name, error = %e, "Dynamic tool HTTP request failed");
            ToolError::ExecutionFailed(format!("HTTP request failed: {}", e))
        })?;

        let status = response.status();
        let body = response.text().await.map_err(|e| {
            ToolError::ExecutionFailed(format!("Failed to read response body: {}", e))
        })?;

        if !status.is_success() {
            return Err(ToolError::ExecutionFailed(format!(
                "HTTP {} from {}: {}",
                status, self.endpoint, body
            )));
        }

        Ok(ToolResult::text(body))
    }
}

/// Create a ToolSchema from a serde_json::Value (CRD inputSchema field)
pub fn schema_from_value(value: &Value) -> ToolSchema {
    ToolSchema {
        schema_type: value
            .get("type")
            .and_then(|v| v.as_str())
            .unwrap_or("object")
            .to_string(),
        properties: value
            .get("properties")
            .and_then(|v| v.as_object())
            .map(|m| m.iter().map(|(k, v)| (k.clone(), v.clone())).collect())
            .unwrap_or_default(),
        required: value
            .get("required")
            .and_then(|v| v.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|v| v.as_str().map(String::from))
                    .collect()
            })
            .unwrap_or_default(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::collections::HashMap;

    #[test]
    fn test_dynamic_tool_creation() {
        let schema = ToolSchema {
            schema_type: "object".to_string(),
            properties: HashMap::new(),
            required: vec![],
        };

        let tool = DynamicTool::new(
            "tenant_weather",
            "Get weather",
            "https://api.example.com/weather",
            "POST",
            schema,
            "tenant-acme",
        );

        assert_eq!(tool.name(), "tenant_weather");
        assert_eq!(tool.description(), "Get weather");
        assert_eq!(tool.required_action(), Action::Read);
    }

    #[test]
    fn test_dynamic_tool_with_builders() {
        let schema = ToolSchema {
            schema_type: "object".to_string(),
            properties: HashMap::new(),
            required: vec![],
        };

        let tool = DynamicTool::new("test", "test", "http://localhost", "GET", schema, "default")
            .with_action(Action::Delete)
            .with_output_schema(json!({"type": "string"}))
            .with_annotations(ToolAnnotations::from_action(Action::Delete));

        assert_eq!(tool.required_action(), Action::Delete);
        assert!(tool.output_schema().is_some());
    }

    #[test]
    fn test_schema_from_value() {
        let value = json!({
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "units": {"type": "string", "enum": ["metric", "imperial"]}
            },
            "required": ["location"]
        });

        let schema = schema_from_value(&value);
        assert_eq!(schema.schema_type, "object");
        assert_eq!(schema.properties.len(), 2);
        assert_eq!(schema.required, vec!["location"]);
    }

    #[test]
    fn test_schema_from_empty_value() {
        let schema = schema_from_value(&json!({}));
        assert_eq!(schema.schema_type, "object");
        assert!(schema.properties.is_empty());
        assert!(schema.required.is_empty());
    }

    #[tokio::test]
    async fn test_tenant_isolation() {
        let schema = ToolSchema {
            schema_type: "object".to_string(),
            properties: HashMap::new(),
            required: vec![],
        };

        let tool = DynamicTool::new(
            "acme_tool",
            "Acme tool",
            "http://localhost:9999/noop",
            "GET",
            schema,
            "tenant-acme",
        );

        let ctx = ToolContext {
            tenant_id: "tenant-other".to_string(),
            user_id: None,
            user_email: None,
            request_id: "req-1".to_string(),
            roles: vec![],
            scopes: vec![],
            raw_token: None,
        };

        let result = tool.execute(json!({}), &ctx).await;
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("not available"));
    }
}
