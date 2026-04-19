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
    /// HTTP endpoint URL (base for per-op tools, full URL for coarse tools)
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
    /// Optional OpenAPI path pattern with `{name}` placeholders (CAB-2113 Phase 0).
    /// When set, the final URL is `endpoint + substituted(path_pattern)`.
    /// Tokens are pulled from the tool args and removed before the remainder is
    /// sent as query string (GET/DELETE) or JSON body (POST/PUT/PATCH).
    path_pattern: Option<String>,
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
            path_pattern: None,
            client: Client::builder()
                .timeout(std::time::Duration::from_secs(30))
                .build()
                .expect("HTTP client"),
        }
    }

    /// Attach an OpenAPI path pattern (e.g. `/customers/{id}`) for per-op tools.
    /// At execute-time, `{name}` tokens are substituted from the tool args and
    /// appended to `endpoint` to form the final request URL.
    pub fn with_path_pattern(mut self, pattern: impl Into<String>) -> Self {
        self.path_pattern = Some(pattern.into());
        self
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

    fn tenant_id(&self) -> Option<&str> {
        // Public tools (catalog API bridge, per-op expanded tools) are visible
        // to every tenant in `tools/list`. Non-public tools stay tenant-scoped.
        // Execute-time isolation still reads `self.tenant_id` directly via `execute()`.
        if self.public {
            None
        } else {
            Some(&self.tenant_id)
        }
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

        // CAB-2113 Phase 0: when a path pattern is attached, substitute `{name}`
        // tokens from args into the path and append to endpoint. The matched
        // args are removed so they don't leak into the query/body.
        let (final_url, remaining_args) = match &self.path_pattern {
            Some(pattern) => {
                let (path, stripped) = substitute_path_pattern(pattern, args, &self.name)?;
                (format!("{}{}", self.endpoint, path), stripped)
            }
            None => (self.endpoint.clone(), args),
        };

        debug!(
            tool = %self.name,
            endpoint = %final_url,
            method = %self.method,
            "Executing dynamic tool"
        );

        // Build HTTP request
        let mut req = match self.method.to_uppercase().as_str() {
            "GET" => self.client.get(&final_url),
            "POST" => self.client.post(&final_url),
            "PUT" => self.client.put(&final_url),
            "DELETE" => self.client.delete(&final_url),
            "PATCH" => self.client.patch(&final_url),
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

        // Inject skill context header if present (CAB-1365)
        if let Some(ref instructions) = ctx.skill_instructions {
            req = req.header("X-Skill-Context", instructions.as_str());
        }

        let has_body = matches!(
            self.method.to_uppercase().as_str(),
            "POST" | "PUT" | "PATCH"
        );
        if has_body && !remaining_args.is_null() {
            req = req.json(&remaining_args);
        } else if !has_body {
            // GET/DELETE: surface remaining scalar args as query string.
            if let Some(obj) = remaining_args.as_object() {
                let pairs: Vec<(String, String)> = obj
                    .iter()
                    .filter_map(|(k, v)| value_to_query_string(v).map(|s| (k.clone(), s)))
                    .collect();
                if !pairs.is_empty() {
                    req = req.query(&pairs);
                }
            }
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

/// Substitute `{name}` tokens in an OpenAPI path pattern from a JSON args object.
///
/// Returns the substituted path + remaining args (with matched keys removed).
/// Non-object args with a non-empty pattern is an error. A missing required
/// token is an error. Matched values are URL-encoded.
fn substitute_path_pattern(
    pattern: &str,
    args: Value,
    tool_name: &str,
) -> Result<(String, Value), ToolError> {
    let tokens = extract_path_tokens(pattern);
    if tokens.is_empty() {
        return Ok((pattern.to_string(), args));
    }

    let mut obj = match args {
        Value::Object(map) => map,
        Value::Null => serde_json::Map::new(),
        other => {
            return Err(ToolError::ExecutionFailed(format!(
                "Tool {} expects object args for path pattern {}, got {}",
                tool_name, pattern, other
            )));
        }
    };

    let mut substituted = pattern.to_string();
    for token in &tokens {
        let value = obj.remove(token).ok_or_else(|| {
            ToolError::ExecutionFailed(format!(
                "Tool {} missing required path parameter: {}",
                tool_name, token
            ))
        })?;
        let rendered = value_to_query_string(&value).ok_or_else(|| {
            ToolError::ExecutionFailed(format!(
                "Tool {} path parameter {} must be scalar",
                tool_name, token
            ))
        })?;
        substituted =
            substituted.replace(&format!("{{{}}}", token), &urlencoding::encode(&rendered));
    }

    let remaining = if obj.is_empty() {
        Value::Null
    } else {
        Value::Object(obj)
    };
    Ok((substituted, remaining))
}

/// Extract `{name}` tokens from an OpenAPI path pattern, in document order.
fn extract_path_tokens(pattern: &str) -> Vec<String> {
    let mut out = Vec::new();
    let bytes = pattern.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'{' {
            if let Some(end) = pattern[i + 1..].find('}') {
                let name = &pattern[i + 1..i + 1 + end];
                if !name.is_empty() && !name.contains('{') {
                    out.push(name.to_string());
                }
                i += end + 2;
                continue;
            }
        }
        i += 1;
    }
    out
}

/// Render a scalar JSON value as a query-string-ready string.
/// Returns `None` for objects/arrays (not supported in v1).
fn value_to_query_string(value: &Value) -> Option<String> {
    match value {
        Value::String(s) => Some(s.clone()),
        Value::Number(n) => Some(n.to_string()),
        Value::Bool(b) => Some(b.to_string()),
        Value::Null => None,
        Value::Array(_) | Value::Object(_) => None,
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
            skill_instructions: None,
            progress_token: None,
            consumer_id: "test-consumer".to_string(),
            from_control_plane: false,
        };

        let result = tool.execute(json!({}), &ctx).await;
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("not available"));
    }

    #[tokio::test]
    async fn test_skill_context_header_injected() {
        use wiremock::matchers::{header, method};
        use wiremock::{Mock, MockServer, ResponseTemplate};

        let mock = MockServer::start().await;
        let url = format!("{}/api/action", mock.uri());

        Mock::given(method("POST"))
            .and(header("X-Skill-Context", "Always use metric units"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({"result": "ok"})))
            .mount(&mock)
            .await;

        let schema = ToolSchema {
            schema_type: "object".to_string(),
            properties: HashMap::new(),
            required: vec![],
        };

        let tool = DynamicTool::new("t1_action", "Action", &url, "POST", schema, "t1");

        let ctx = ToolContext {
            tenant_id: "t1".to_string(),
            user_id: None,
            user_email: None,
            request_id: "req-1".to_string(),
            roles: vec![],
            scopes: vec![],
            raw_token: None,
            skill_instructions: Some("Always use metric units".to_string()),
            progress_token: None,
            consumer_id: "test-consumer".to_string(),
            from_control_plane: false,
        };

        let result = tool.execute(json!({"query": "temp"}), &ctx).await.unwrap();
        assert!(result.content.iter().any(|c| {
            if let super::super::ToolContent::Text { text } = c {
                text.contains("ok")
            } else {
                false
            }
        }));
    }

    #[tokio::test]
    async fn test_no_skill_context_header_when_none() {
        use wiremock::matchers::method;
        use wiremock::{Mock, MockServer, ResponseTemplate};

        let mock = MockServer::start().await;
        let url = format!("{}/api/action", mock.uri());

        Mock::given(method("POST"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({"clean": true})))
            .mount(&mock)
            .await;

        let schema = ToolSchema {
            schema_type: "object".to_string(),
            properties: HashMap::new(),
            required: vec![],
        };

        let tool = DynamicTool::new("t1_clean", "Clean", &url, "POST", schema, "t1");

        let ctx = ToolContext {
            tenant_id: "t1".to_string(),
            user_id: None,
            user_email: None,
            request_id: "req-1".to_string(),
            roles: vec![],
            scopes: vec![],
            raw_token: None,
            skill_instructions: None,
            progress_token: None,
            consumer_id: "test-consumer".to_string(),
            from_control_plane: false,
        };

        let result = tool.execute(json!({}), &ctx).await.unwrap();
        assert!(result.content.iter().any(|c| {
            if let super::super::ToolContent::Text { text } = c {
                text.contains("clean")
            } else {
                false
            }
        }));
    }

    // === CAB-2113 Phase 0: path-pattern helpers + DynamicTool substitution ===

    #[test]
    fn cab_2113_extract_path_tokens_basic() {
        assert_eq!(
            extract_path_tokens("/customers/{id}"),
            vec!["id".to_string()]
        );
        assert_eq!(
            extract_path_tokens("/a/{x}/b/{y}"),
            vec!["x".to_string(), "y".to_string()]
        );
        assert!(extract_path_tokens("/no/tokens").is_empty());
        assert!(extract_path_tokens("/broken/{unclosed").is_empty());
    }

    #[test]
    fn cab_2113_substitute_path_pattern_strips_matched_keys() {
        let (path, rest) = substitute_path_pattern(
            "/customers/{id}",
            json!({"id": "42", "email": "foo@bar.com"}),
            "demo:bank:get-customer",
        )
        .unwrap();
        assert_eq!(path, "/customers/42");
        assert_eq!(rest, json!({"email": "foo@bar.com"}));
    }

    #[test]
    fn cab_2113_substitute_path_pattern_missing_token_errors() {
        let err = substitute_path_pattern(
            "/customers/{id}",
            json!({"other": "x"}),
            "demo:bank:get-customer",
        )
        .unwrap_err();
        assert!(err.to_string().contains("missing required path parameter"));
    }

    #[test]
    fn cab_2113_substitute_path_pattern_url_encodes_values() {
        let (path, _) =
            substitute_path_pattern("/items/{id}", json!({"id": "a/b c"}), "demo:store:get-item")
                .unwrap();
        assert_eq!(path, "/items/a%2Fb%20c");
    }

    #[tokio::test]
    async fn cab_2113_dynamic_tool_substitutes_path_and_forwards_query() {
        use wiremock::matchers::{method, path as m_path, query_param};
        use wiremock::{Mock, MockServer, ResponseTemplate};

        let mock = MockServer::start().await;
        Mock::given(method("GET"))
            .and(m_path("/customers/42"))
            .and(query_param("expand", "accounts"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({"ok": true})))
            .mount(&mock)
            .await;

        let schema = ToolSchema {
            schema_type: "object".to_string(),
            properties: HashMap::new(),
            required: vec![],
        };
        let tool = DynamicTool::new(
            "demo:bank:get-customer",
            "Get customer",
            mock.uri(),
            "GET",
            schema,
            "demo",
        )
        .into_public()
        .with_path_pattern("/customers/{id}");

        let ctx = ToolContext {
            tenant_id: "demo".to_string(),
            user_id: None,
            user_email: None,
            request_id: "req-1".to_string(),
            roles: vec![],
            scopes: vec![],
            raw_token: None,
            skill_instructions: None,
            progress_token: None,
            consumer_id: "c".to_string(),
            from_control_plane: false,
        };

        let res = tool
            .execute(json!({"id": "42", "expand": "accounts"}), &ctx)
            .await
            .unwrap();
        assert!(res.content.iter().any(|c| {
            if let super::super::ToolContent::Text { text } = c {
                text.contains("\"ok\":true")
            } else {
                false
            }
        }));
    }

    #[tokio::test]
    async fn cab_2113_dynamic_tool_post_sends_remainder_as_body() {
        use wiremock::matchers::{body_partial_json, method, path as m_path};
        use wiremock::{Mock, MockServer, ResponseTemplate};

        let mock = MockServer::start().await;
        Mock::given(method("POST"))
            .and(m_path("/customers/42/transfers"))
            .and(body_partial_json(json!({"amount": 100})))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({"created": true})))
            .mount(&mock)
            .await;

        let schema = ToolSchema {
            schema_type: "object".to_string(),
            properties: HashMap::new(),
            required: vec![],
        };
        let tool = DynamicTool::new(
            "demo:bank:create-transfer",
            "Create transfer",
            mock.uri(),
            "POST",
            schema,
            "demo",
        )
        .into_public()
        .with_path_pattern("/customers/{id}/transfers");

        let ctx = ToolContext {
            tenant_id: "demo".to_string(),
            user_id: None,
            user_email: None,
            request_id: "req-1".to_string(),
            roles: vec![],
            scopes: vec![],
            raw_token: None,
            skill_instructions: None,
            progress_token: None,
            consumer_id: "c".to_string(),
            from_control_plane: false,
        };

        tool.execute(json!({"id": "42", "amount": 100}), &ctx)
            .await
            .unwrap();
    }

    // === CAB-2123: public DynamicTool must be tenant_id=None in discovery ===
    //
    // regression for CAB-2123
    // Before the fix, `Tool::tenant_id` returned `Some(&self.tenant_id)` even when
    // the tool was registered via `.into_public()` — so `ToolRegistry::list(Some(caller))`
    // filtered public per-op tools out for every caller whose tenant didn't match the CRD
    // namespace. This broke standard /mcp/v1/tools discovery for the CAB-2113 banking
    // catalog, forcing clients through the bricolé `stoa_tools action=list` path.

    fn schema_empty_object() -> ToolSchema {
        ToolSchema {
            schema_type: "object".to_string(),
            properties: HashMap::new(),
            required: vec![],
        }
    }

    #[test]
    fn cab_2123_public_dynamic_tool_has_no_tenant_in_definition() {
        let tool = DynamicTool::new(
            "demo_public",
            "public tool",
            "http://localhost",
            "GET",
            schema_empty_object(),
            "demo",
        )
        .into_public();

        assert_eq!(tool.tenant_id(), None);
        assert!(tool.definition().tenant_id.is_none());
    }

    #[test]
    fn cab_2123_private_dynamic_tool_keeps_tenant_in_definition() {
        let tool = DynamicTool::new(
            "demo_private",
            "private tool",
            "http://localhost",
            "GET",
            schema_empty_object(),
            "demo",
        );

        assert_eq!(tool.tenant_id(), Some("demo"));
        assert_eq!(tool.definition().tenant_id.as_deref(), Some("demo"));
    }

    #[test]
    fn cab_2123_registry_list_includes_public_dynamic_tool_for_any_tenant() {
        use super::super::ToolRegistry;
        use std::sync::Arc;

        let registry = ToolRegistry::new();
        let tool = DynamicTool::new(
            "demo:bank:get-customer",
            "Get customer",
            "http://mock",
            "GET",
            schema_empty_object(),
            "demo",
        )
        .into_public();

        registry.register(Arc::new(tool));

        // Public tool must surface for any caller tenant, not just "demo".
        for caller in ["demo", "stoa-demo", "other-tenant", "acme"] {
            let tools = registry.list(Some(caller));
            assert!(
                tools.iter().any(|t| t.name == "demo:bank:get-customer"),
                "public tool invisible to tenant `{}`",
                caller
            );
        }
    }

    #[test]
    fn cab_2123_registry_list_keeps_private_dynamic_tool_tenant_scoped() {
        use super::super::ToolRegistry;
        use std::sync::Arc;

        let registry = ToolRegistry::new();
        let tool = DynamicTool::new(
            "acme_internal",
            "Internal tool",
            "http://mock",
            "GET",
            schema_empty_object(),
            "acme",
        );
        registry.register(Arc::new(tool));

        // Owner sees it; other tenants don't.
        assert!(
            registry
                .list(Some("acme"))
                .iter()
                .any(|t| t.name == "acme_internal"),
            "owner must see its private tool"
        );
        assert!(
            registry
                .list(Some("other"))
                .iter()
                .all(|t| t.name != "acme_internal"),
            "non-owner must not see private tool"
        );
    }

    #[test]
    fn cab_2123_public_per_op_tool_surfaces_via_standard_list() {
        // Reproduces the api_bridge::discover_expanded_api_tools registration pattern
        // (CAB-2113 Phase 0): per-op public tool with a path pattern must surface
        // via `list(Some(caller))` for a caller whose tenant doesn't match the CRD
        // namespace. This is the CAB-2120 demo path that was still broken after the
        // STOA_TOOL_EXPANSION_MODE=per-op prod flip.
        use super::super::ToolRegistry;
        use std::sync::Arc;

        let registry = ToolRegistry::new();
        let tool = DynamicTool::new(
            "demo:bank:get-customer-by-number",
            "Get customer by number",
            "http://banking-mock",
            "GET",
            schema_empty_object(),
            "demo",
        )
        .with_action(Action::Read)
        .with_annotations(ToolAnnotations {
            title: Some("Banking: get customer".to_string()),
            open_world_hint: Some(true),
            ..Default::default()
        })
        .into_public()
        .with_path_pattern("/customers/{customerNumber}");

        registry.register(Arc::new(tool));

        // stoa-demo JWT caller (the real demo scenario) must see the per-op tool.
        let tools = registry.list(Some("stoa-demo"));
        assert!(
            tools
                .iter()
                .any(|t| t.name == "demo:bank:get-customer-by-number"),
            "per-op public tool must surface via standard discovery (CAB-2123)"
        );
    }
}
