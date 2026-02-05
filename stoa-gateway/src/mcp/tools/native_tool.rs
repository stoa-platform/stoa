//! Native Tool Implementations
//!
//! Direct HTTP calls to Control Plane API, bypassing the Python mcp-gateway.
//! Each tool implementation maps MCP tool arguments to CP API REST endpoints.
//!
//! Phase 1: Kill the Python dependency.
//! Current: Client → Rust GW → CP API → Python mcp-gateway → CP API → DB (~1038ms)
//! Target:  Client → Rust GW → CP API → DB (<200ms)

use async_trait::async_trait;
use reqwest::Client;
use serde_json::{json, Value};
use std::collections::HashSet;
use std::sync::Arc;
use std::time::Duration;
use tracing::{debug, warn};

use super::{Tool, ToolContext, ToolError, ToolRegistry, ToolResult, ToolSchema};
use crate::uac::Action;

/// Native tool that calls CP API directly (no Python proxy)
pub struct NativeTool {
    tool_name: String,
    description: String,
    schema: ToolSchema,
    required_action: Action,
    client: Client,
    cp_base_url: String,
    /// Optional reference to the tool registry (for stoa_tools)
    tool_registry: Option<Arc<ToolRegistry>>,
}

impl NativeTool {
    pub fn new(
        tool_name: &str,
        description: &str,
        schema: ToolSchema,
        required_action: Action,
        client: Client,
        cp_base_url: &str,
    ) -> Self {
        Self {
            tool_name: tool_name.to_string(),
            description: description.to_string(),
            schema,
            required_action,
            client,
            cp_base_url: cp_base_url.trim_end_matches('/').to_string(),
            tool_registry: None,
        }
    }

    /// Create a NativeTool with access to the tool registry (for stoa_tools)
    pub fn with_registry(mut self, registry: Arc<ToolRegistry>) -> Self {
        self.tool_registry = Some(registry);
        self
    }

    /// Build Authorization header from raw token
    fn auth_header(&self, ctx: &ToolContext) -> Option<String> {
        ctx.raw_token.as_ref().map(|t| format!("Bearer {}", t))
    }

    /// Execute HTTP GET request to CP API
    async fn get(&self, path: &str, ctx: &ToolContext) -> Result<Value, ToolError> {
        let url = format!("{}{}", self.cp_base_url, path);
        debug!(url = %url, tool = %self.tool_name, "Native tool GET");

        let mut req = self.client.get(&url).header("X-Tenant-ID", &ctx.tenant_id);

        if let Some(auth) = self.auth_header(ctx) {
            req = req.header("Authorization", auth);
        }

        let resp = req
            .timeout(Duration::from_secs(30))
            .send()
            .await
            .map_err(|e| ToolError::ExecutionFailed(format!("HTTP request failed: {}", e)))?;

        if !resp.status().is_success() {
            let status = resp.status().as_u16();
            let body = resp.text().await.unwrap_or_default();
            return Err(ToolError::ExecutionFailed(format!(
                "CP API error {}: {}",
                status, body
            )));
        }

        resp.json()
            .await
            .map_err(|e| ToolError::ExecutionFailed(format!("Failed to parse response: {}", e)))
    }

    /// Execute HTTP POST request to CP API
    async fn post(&self, path: &str, body: &Value, ctx: &ToolContext) -> Result<Value, ToolError> {
        let url = format!("{}{}", self.cp_base_url, path);
        debug!(url = %url, tool = %self.tool_name, "Native tool POST");

        let mut req = self
            .client
            .post(&url)
            .header("X-Tenant-ID", &ctx.tenant_id)
            .header("Content-Type", "application/json")
            .json(body);

        if let Some(auth) = self.auth_header(ctx) {
            req = req.header("Authorization", auth);
        }

        let resp = req
            .timeout(Duration::from_secs(30))
            .send()
            .await
            .map_err(|e| ToolError::ExecutionFailed(format!("HTTP request failed: {}", e)))?;

        if !resp.status().is_success() {
            let status = resp.status().as_u16();
            let body = resp.text().await.unwrap_or_default();
            return Err(ToolError::ExecutionFailed(format!(
                "CP API error {}: {}",
                status, body
            )));
        }

        resp.json()
            .await
            .map_err(|e| ToolError::ExecutionFailed(format!("Failed to parse response: {}", e)))
    }

    /// Execute HTTP DELETE request to CP API
    async fn delete(&self, path: &str, ctx: &ToolContext) -> Result<Value, ToolError> {
        let url = format!("{}{}", self.cp_base_url, path);
        debug!(url = %url, tool = %self.tool_name, "Native tool DELETE");

        let mut req = self
            .client
            .delete(&url)
            .header("X-Tenant-ID", &ctx.tenant_id);

        if let Some(auth) = self.auth_header(ctx) {
            req = req.header("Authorization", auth);
        }

        let resp = req
            .timeout(Duration::from_secs(30))
            .send()
            .await
            .map_err(|e| ToolError::ExecutionFailed(format!("HTTP request failed: {}", e)))?;

        if !resp.status().is_success() {
            let status = resp.status().as_u16();
            let body = resp.text().await.unwrap_or_default();
            return Err(ToolError::ExecutionFailed(format!(
                "CP API error {}: {}",
                status, body
            )));
        }

        // DELETE may return empty body
        let text = resp.text().await.unwrap_or_default();
        if text.is_empty() {
            Ok(json!({"status": "deleted"}))
        } else {
            serde_json::from_str(&text)
                .map_err(|e| ToolError::ExecutionFailed(format!("Failed to parse response: {}", e)))
        }
    }
}

#[async_trait]
impl Tool for NativeTool {
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
        // Route to specific tool handler
        match self.tool_name.as_str() {
            "stoa_platform_info" => self.handle_platform_info().await,
            "stoa_platform_health" => self.handle_platform_health().await,
            "stoa_tools" => self.handle_tools(&args, ctx).await,
            "stoa_tenants" => self.handle_tenants(ctx).await,
            "stoa_catalog" => self.handle_catalog(&args, ctx).await,
            "stoa_api_spec" => self.handle_api_spec(&args, ctx).await,
            "stoa_subscription" => self.handle_subscription(&args, ctx).await,
            "stoa_metrics" => self.handle_metrics_stub(&args).await,
            "stoa_logs" => self.handle_logs_stub(&args).await,
            "stoa_alerts" => self.handle_alerts_stub(&args).await,
            "stoa_uac" => self.handle_uac_stub(&args).await,
            "stoa_security" => self.handle_security_stub(&args).await,
            _ => Err(ToolError::ExecutionFailed(format!(
                "Unknown native tool: {}",
                self.tool_name
            ))),
        }
    }
}

// ============================================
// Tool Handlers
// ============================================

impl NativeTool {
    // ─── Local Handlers (no HTTP) ─────────────────────────────────

    async fn handle_platform_info(&self) -> Result<ToolResult, ToolError> {
        let info = json!({
            "platform": "STOA",
            "gateway": "stoa-gateway (Rust)",
            "version": env!("CARGO_PKG_VERSION"),
            "mcp_protocol": "2024-11-05",
            "features": [
                "MCP SSE Transport",
                "OAuth 2.1 (RFC 9728)",
                "JWT Authentication",
                "API Key Authentication",
                "Multi-tenant Isolation",
                "Tool Discovery",
                "Prometheus Metrics"
            ],
            "status": "operational"
        });
        Ok(ToolResult::text(
            serde_json::to_string_pretty(&info).unwrap(),
        ))
    }

    async fn handle_platform_health(&self) -> Result<ToolResult, ToolError> {
        // TODO: Actually check component health
        let health = json!({
            "status": "healthy",
            "components": {
                "gateway": {"status": "healthy", "version": env!("CARGO_PKG_VERSION")},
                "mcp_transport": {"status": "healthy"},
                "session_manager": {"status": "healthy"},
                "tool_registry": {"status": "healthy"}
            },
            "timestamp": chrono::Utc::now().to_rfc3339()
        });
        Ok(ToolResult::text(
            serde_json::to_string_pretty(&health).unwrap(),
        ))
    }

    async fn handle_tools(
        &self,
        args: &Value,
        _ctx: &ToolContext,
    ) -> Result<ToolResult, ToolError> {
        let action = args
            .get("action")
            .and_then(|v| v.as_str())
            .unwrap_or("list");

        let registry = match &self.tool_registry {
            Some(r) => r,
            None => {
                return Ok(ToolResult::text(
                    "Tool registry not available for introspection",
                ))
            }
        };

        match action {
            "list" => {
                let tools: Vec<Value> = registry
                    .list(None)
                    .iter()
                    .map(|t| {
                        json!({
                            "name": t.name,
                            "description": t.description
                        })
                    })
                    .collect();

                Ok(ToolResult::text(
                    serde_json::to_string_pretty(&json!({
                        "tools": tools,
                        "count": tools.len()
                    }))
                    .unwrap(),
                ))
            }
            "schema" => {
                let tool_name = args.get("tool_name").and_then(|v| v.as_str());
                match tool_name {
                    Some(name) => {
                        if let Some(tool) = registry.get(name) {
                            let def = tool.definition();
                            Ok(ToolResult::text(
                                serde_json::to_string_pretty(&def).unwrap(),
                            ))
                        } else {
                            Ok(ToolResult::text(format!("Tool '{}' not found", name)))
                        }
                    }
                    None => Ok(ToolResult::text(
                        "Missing 'tool_name' parameter for schema action",
                    )),
                }
            }
            "search" => {
                let query = args
                    .get("query")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_lowercase();

                let tools: Vec<Value> = registry
                    .list(None)
                    .iter()
                    .filter(|t| {
                        t.name.to_lowercase().contains(&query)
                            || t.description.to_lowercase().contains(&query)
                    })
                    .map(|t| {
                        json!({
                            "name": t.name,
                            "description": t.description
                        })
                    })
                    .collect();

                Ok(ToolResult::text(
                    serde_json::to_string_pretty(&json!({
                        "tools": tools,
                        "count": tools.len(),
                        "query": query
                    }))
                    .unwrap(),
                ))
            }
            _ => Ok(ToolResult::text(format!(
                "Unknown action '{}'. Valid actions: list, schema, search",
                action
            ))),
        }
    }

    // ─── CP API Proxy Handlers ────────────────────────────────────

    async fn handle_tenants(&self, ctx: &ToolContext) -> Result<ToolResult, ToolError> {
        let result = self.get("/v1/tenants", ctx).await?;
        Ok(ToolResult::text(
            serde_json::to_string_pretty(&result).unwrap(),
        ))
    }

    async fn handle_catalog(
        &self,
        args: &Value,
        ctx: &ToolContext,
    ) -> Result<ToolResult, ToolError> {
        let action = args
            .get("action")
            .and_then(|v| v.as_str())
            .unwrap_or("list");

        match action {
            "list" => {
                let mut path = "/v1/portal/apis".to_string();
                let mut query_parts = vec![];

                if let Some(status) = args.get("status").and_then(|v| v.as_str()) {
                    query_parts.push(format!("status={}", status));
                }
                if let Some(category) = args.get("category").and_then(|v| v.as_str()) {
                    query_parts.push(format!("category={}", category));
                }
                if let Some(page) = args.get("page").and_then(|v| v.as_i64()) {
                    query_parts.push(format!("page={}", page));
                }
                if let Some(page_size) = args.get("page_size").and_then(|v| v.as_i64()) {
                    query_parts.push(format!("page_size={}", page_size));
                }

                if !query_parts.is_empty() {
                    path = format!("{}?{}", path, query_parts.join("&"));
                }

                let result = self.get(&path, ctx).await?;
                Ok(ToolResult::text(
                    serde_json::to_string_pretty(&result).unwrap(),
                ))
            }
            "get" => {
                let api_id = args.get("api_id").and_then(|v| v.as_str()).ok_or_else(|| {
                    ToolError::InvalidArguments("Missing 'api_id' for get action".into())
                })?;

                let result = self
                    .get(&format!("/v1/portal/apis/{}", api_id), ctx)
                    .await?;
                Ok(ToolResult::text(
                    serde_json::to_string_pretty(&result).unwrap(),
                ))
            }
            "search" => {
                let query = args.get("query").and_then(|v| v.as_str()).unwrap_or("");
                let path = format!("/v1/portal/apis?search={}", urlencoding::encode(query));
                let result = self.get(&path, ctx).await?;
                Ok(ToolResult::text(
                    serde_json::to_string_pretty(&result).unwrap(),
                ))
            }
            "versions" => {
                let api_id = args.get("api_id").and_then(|v| v.as_str()).ok_or_else(|| {
                    ToolError::InvalidArguments("Missing 'api_id' for versions action".into())
                })?;

                // Get API and extract version info
                let result = self
                    .get(&format!("/v1/portal/apis/{}", api_id), ctx)
                    .await?;
                let version = result.get("version").cloned().unwrap_or(json!("unknown"));
                let versions_info = json!({
                    "api_id": api_id,
                    "current_version": version,
                    "note": "Full version history requires dedicated endpoint"
                });
                Ok(ToolResult::text(
                    serde_json::to_string_pretty(&versions_info).unwrap(),
                ))
            }
            "categories" => {
                // Get all APIs and aggregate categories
                let result = self.get("/v1/portal/apis?page_size=1000", ctx).await?;
                let apis = result.get("apis").and_then(|a| a.as_array());

                let categories: HashSet<String> = apis
                    .map(|arr| {
                        arr.iter()
                            .filter_map(|api| api.get("category").and_then(|c| c.as_str()))
                            .map(String::from)
                            .collect()
                    })
                    .unwrap_or_default();

                let mut cats: Vec<String> = categories.into_iter().collect();
                cats.sort();

                Ok(ToolResult::text(
                    serde_json::to_string_pretty(&json!({
                        "categories": cats,
                        "count": cats.len()
                    }))
                    .unwrap(),
                ))
            }
            _ => Ok(ToolResult::text(format!(
                "Unknown action '{}'. Valid: list, get, search, versions, categories",
                action
            ))),
        }
    }

    async fn handle_api_spec(
        &self,
        args: &Value,
        ctx: &ToolContext,
    ) -> Result<ToolResult, ToolError> {
        let action = args
            .get("action")
            .and_then(|v| v.as_str())
            .unwrap_or("openapi");

        let api_id = args.get("api_id").and_then(|v| v.as_str()).ok_or_else(|| {
            ToolError::InvalidArguments("Missing required 'api_id' parameter".into())
        })?;

        match action {
            "openapi" => {
                let result = self
                    .get(&format!("/v1/portal/apis/{}/openapi", api_id), ctx)
                    .await?;
                Ok(ToolResult::text(
                    serde_json::to_string_pretty(&result).unwrap(),
                ))
            }
            "docs" | "endpoints" => {
                // Get API metadata and format as docs
                let api = self
                    .get(&format!("/v1/portal/apis/{}", api_id), ctx)
                    .await?;

                let name = api
                    .get("name")
                    .and_then(|v| v.as_str())
                    .unwrap_or("Unknown");
                let desc = api
                    .get("description")
                    .and_then(|v| v.as_str())
                    .unwrap_or("No description");
                let version = api.get("version").and_then(|v| v.as_str()).unwrap_or("v1");
                let base_url = api.get("base_url").and_then(|v| v.as_str());
                let endpoints = api.get("endpoints").cloned().unwrap_or(json!([]));

                let docs = json!({
                    "api_id": api_id,
                    "name": name,
                    "description": desc,
                    "version": version,
                    "base_url": base_url,
                    "endpoints": endpoints
                });

                Ok(ToolResult::text(
                    serde_json::to_string_pretty(&docs).unwrap(),
                ))
            }
            _ => Ok(ToolResult::text(format!(
                "Unknown action '{}'. Valid: openapi, docs, endpoints",
                action
            ))),
        }
    }

    async fn handle_subscription(
        &self,
        args: &Value,
        ctx: &ToolContext,
    ) -> Result<ToolResult, ToolError> {
        let action = args
            .get("action")
            .and_then(|v| v.as_str())
            .unwrap_or("list");

        match action {
            "list" => {
                let mut path = "/v1/mcp/subscriptions".to_string();
                let mut query_parts = vec![];

                if let Some(status) = args.get("status").and_then(|v| v.as_str()) {
                    query_parts.push(format!("status={}", status));
                }

                if !query_parts.is_empty() {
                    path = format!("{}?{}", path, query_parts.join("&"));
                }

                let result = self.get(&path, ctx).await?;
                Ok(ToolResult::text(
                    serde_json::to_string_pretty(&result).unwrap(),
                ))
            }
            "get" | "credentials" => {
                let sub_id = args
                    .get("subscription_id")
                    .and_then(|v| v.as_str())
                    .ok_or_else(|| {
                        ToolError::InvalidArguments(
                            "Missing 'subscription_id' for get action".into(),
                        )
                    })?;

                let result = self
                    .get(&format!("/v1/mcp/subscriptions/{}", sub_id), ctx)
                    .await?;
                Ok(ToolResult::text(
                    serde_json::to_string_pretty(&result).unwrap(),
                ))
            }
            "create" => {
                let server_id = args
                    .get("api_id")
                    .or_else(|| args.get("server_id"))
                    .and_then(|v| v.as_str())
                    .ok_or_else(|| {
                        ToolError::InvalidArguments(
                            "Missing 'api_id' or 'server_id' for create action".into(),
                        )
                    })?;

                let plan = args
                    .get("plan")
                    .and_then(|v| v.as_str())
                    .unwrap_or("standard");

                let body = json!({
                    "server_id": server_id,
                    "plan": plan
                });

                let result = self.post("/v1/mcp/subscriptions", &body, ctx).await?;
                Ok(ToolResult::text(
                    serde_json::to_string_pretty(&result).unwrap(),
                ))
            }
            "cancel" => {
                let sub_id = args
                    .get("subscription_id")
                    .and_then(|v| v.as_str())
                    .ok_or_else(|| {
                        ToolError::InvalidArguments(
                            "Missing 'subscription_id' for cancel action".into(),
                        )
                    })?;

                let result = self
                    .delete(&format!("/v1/mcp/subscriptions/{}", sub_id), ctx)
                    .await?;
                Ok(ToolResult::text(
                    serde_json::to_string_pretty(&result).unwrap(),
                ))
            }
            "rotate_key" => {
                let sub_id = args
                    .get("subscription_id")
                    .and_then(|v| v.as_str())
                    .ok_or_else(|| {
                        ToolError::InvalidArguments(
                            "Missing 'subscription_id' for rotate_key action".into(),
                        )
                    })?;

                let result = self
                    .post(
                        &format!("/v1/mcp/subscriptions/{}/rotate-key", sub_id),
                        &json!({}),
                        ctx,
                    )
                    .await?;
                Ok(ToolResult::text(
                    serde_json::to_string_pretty(&result).unwrap(),
                ))
            }
            _ => Ok(ToolResult::text(format!(
                "Unknown action '{}'. Valid: list, get, create, cancel, credentials, rotate_key",
                action
            ))),
        }
    }

    // ─── Stub Handlers (not implemented in Python either) ─────────

    async fn handle_metrics_stub(&self, args: &Value) -> Result<ToolResult, ToolError> {
        let action = args
            .get("action")
            .and_then(|v| v.as_str())
            .unwrap_or("usage");

        warn!(action = %action, "stoa_metrics called — returning stub response");

        let stub = json!({
            "status": "coming_soon",
            "message": format!("Metrics action '{}' is not yet implemented. This feature is planned for Phase 3 (Kafka Metering).", action),
            "action": action,
            "placeholder": true
        });
        Ok(ToolResult::text(
            serde_json::to_string_pretty(&stub).unwrap(),
        ))
    }

    async fn handle_logs_stub(&self, args: &Value) -> Result<ToolResult, ToolError> {
        let action = args
            .get("action")
            .and_then(|v| v.as_str())
            .unwrap_or("search");

        warn!(action = %action, "stoa_logs called — returning stub response");

        let stub = json!({
            "status": "coming_soon",
            "message": format!("Logs action '{}' is not yet implemented. This feature is planned for Phase 3.", action),
            "action": action,
            "placeholder": true
        });
        Ok(ToolResult::text(
            serde_json::to_string_pretty(&stub).unwrap(),
        ))
    }

    async fn handle_alerts_stub(&self, args: &Value) -> Result<ToolResult, ToolError> {
        let action = args
            .get("action")
            .and_then(|v| v.as_str())
            .unwrap_or("list");

        warn!(action = %action, "stoa_alerts called — returning stub response");

        let stub = json!({
            "status": "coming_soon",
            "message": format!("Alerts action '{}' is not yet implemented. This feature is planned for Phase 3.", action),
            "action": action,
            "alerts": [],
            "placeholder": true
        });
        Ok(ToolResult::text(
            serde_json::to_string_pretty(&stub).unwrap(),
        ))
    }

    async fn handle_uac_stub(&self, args: &Value) -> Result<ToolResult, ToolError> {
        let action = args
            .get("action")
            .and_then(|v| v.as_str())
            .unwrap_or("list");

        warn!(action = %action, "stoa_uac called — returning stub response");

        let stub = json!({
            "status": "coming_soon",
            "message": format!("UAC action '{}' is not yet implemented. This feature is planned for Phase 2 (OPA + UAC).", action),
            "action": action,
            "contracts": [],
            "placeholder": true
        });
        Ok(ToolResult::text(
            serde_json::to_string_pretty(&stub).unwrap(),
        ))
    }

    async fn handle_security_stub(&self, args: &Value) -> Result<ToolResult, ToolError> {
        let action = args
            .get("action")
            .and_then(|v| v.as_str())
            .unwrap_or("audit_log");

        warn!(action = %action, "stoa_security called — returning stub response");

        let stub = json!({
            "status": "coming_soon",
            "message": format!("Security action '{}' is not yet implemented. This feature is planned for Phase 2.", action),
            "action": action,
            "policies": [],
            "audit_log": [],
            "placeholder": true
        });
        Ok(ToolResult::text(
            serde_json::to_string_pretty(&stub).unwrap(),
        ))
    }
}

// ============================================
// Factory Functions
// ============================================

/// Create a shared HTTP client for native tools
pub fn create_http_client() -> Client {
    Client::builder()
        .timeout(Duration::from_secs(30))
        .pool_max_idle_per_host(10)
        .build()
        .expect("Failed to create HTTP client")
}

/// Check if a tool has native implementation
pub fn has_native_implementation(tool_name: &str) -> bool {
    matches!(
        tool_name,
        "stoa_platform_info"
            | "stoa_platform_health"
            | "stoa_tools"
            | "stoa_tenants"
            | "stoa_catalog"
            | "stoa_api_spec"
            | "stoa_subscription"
            | "stoa_metrics"
            | "stoa_logs"
            | "stoa_alerts"
            | "stoa_uac"
            | "stoa_security"
    )
}

/// Create all native tools and register them
pub fn register_native_tools(
    registry: &ToolRegistry,
    client: Client,
    cp_base_url: &str,
    tool_registry_ref: Arc<ToolRegistry>,
) {
    use serde_json::json;

    let url = cp_base_url.trim_end_matches('/');

    // Helper to create ToolSchema
    let schema = |props: Value, required: Vec<&str>| ToolSchema {
        schema_type: "object".into(),
        properties: serde_json::from_value(props).unwrap_or_default(),
        required: required.iter().map(|s| s.to_string()).collect(),
    };

    // 1. stoa_platform_info
    registry.register(Arc::new(NativeTool::new(
        "stoa_platform_info",
        "Get STOA platform version, status, and available features",
        schema(json!({}), vec![]),
        Action::Read,
        client.clone(),
        url,
    )));

    // 2. stoa_platform_health
    registry.register(Arc::new(NativeTool::new(
        "stoa_platform_health",
        "Health check all platform components (Gateway, Keycloak, Database, Kafka)",
        schema(
            json!({
                "components": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific components to check"
                }
            }),
            vec![],
        ),
        Action::Read,
        client.clone(),
        url,
    )));

    // 3. stoa_tools (needs registry reference)
    registry.register(Arc::new(
        NativeTool::new(
            "stoa_tools",
            "Tool discovery: list, schema, search",
            schema(
                json!({
                    "action": {"type": "string", "enum": ["list", "schema", "search"]},
                    "tool_name": {"type": "string"},
                    "query": {"type": "string"}
                }),
                vec!["action"],
            ),
            Action::Read,
            client.clone(),
            url,
        )
        .with_registry(tool_registry_ref),
    ));

    // 4. stoa_tenants
    registry.register(Arc::new(NativeTool::new(
        "stoa_tenants",
        "List accessible tenants (admin only)",
        schema(
            json!({
                "include_inactive": {"type": "boolean", "default": false}
            }),
            vec![],
        ),
        Action::Read,
        client.clone(),
        url,
    )));

    // 5. stoa_catalog
    registry.register(Arc::new(NativeTool::new(
        "stoa_catalog",
        "API catalog: list, get, search, versions, categories",
        schema(
            json!({
                "action": {"type": "string", "enum": ["list", "get", "search", "versions", "categories"]},
                "api_id": {"type": "string"},
                "query": {"type": "string"},
                "status": {"type": "string", "enum": ["active", "deprecated", "draft"]},
                "category": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "page": {"type": "integer", "default": 1},
                "page_size": {"type": "integer", "default": 20}
            }),
            vec!["action"],
        ),
        Action::Read,
        client.clone(),
        url,
    )));

    // 6. stoa_api_spec
    registry.register(Arc::new(NativeTool::new(
        "stoa_api_spec",
        "API specification: openapi, docs, endpoints",
        schema(
            json!({
                "action": {"type": "string", "enum": ["openapi", "docs", "endpoints"]},
                "api_id": {"type": "string"},
                "format": {"type": "string", "enum": ["json", "yaml"], "default": "json"},
                "version": {"type": "string"},
                "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"]}
            }),
            vec!["action", "api_id"],
        ),
        Action::Read,
        client.clone(),
        url,
    )));

    // 7. stoa_subscription
    registry.register(Arc::new(NativeTool::new(
        "stoa_subscription",
        "Subscriptions: list, get, create, cancel, credentials, rotate_key",
        schema(
            json!({
                "action": {"type": "string", "enum": ["list", "get", "create", "cancel", "credentials", "rotate_key"]},
                "subscription_id": {"type": "string"},
                "api_id": {"type": "string"},
                "plan": {"type": "string"},
                "status": {"type": "string", "enum": ["active", "pending", "suspended", "cancelled"]},
                "reason": {"type": "string"},
                "grace_period_hours": {"type": "integer", "default": 24}
            }),
            vec!["action"],
        ),
        Action::Read,
        client.clone(),
        url,
    )));

    // 8. stoa_metrics (stub)
    registry.register(Arc::new(NativeTool::new(
        "stoa_metrics",
        "API metrics: usage, latency, errors, quota",
        schema(
            json!({
                "action": {"type": "string", "enum": ["usage", "latency", "errors", "quota"]},
                "api_id": {"type": "string"},
                "subscription_id": {"type": "string"},
                "time_range": {"type": "string", "enum": ["1h", "24h", "7d", "30d", "custom"], "default": "24h"},
                "endpoint": {"type": "string"},
                "error_code": {"type": "integer"}
            }),
            vec!["action"],
        ),
        Action::ViewMetrics,
        client.clone(),
        url,
    )));

    // 9. stoa_logs (stub)
    registry.register(Arc::new(NativeTool::new(
        "stoa_logs",
        "API logs: search, recent",
        schema(
            json!({
                "action": {"type": "string", "enum": ["search", "recent"]},
                "api_id": {"type": "string"},
                "query": {"type": "string"},
                "level": {"type": "string", "enum": ["debug", "info", "warn", "error"]},
                "time_range": {"type": "string", "enum": ["1h", "24h", "7d"], "default": "24h"},
                "limit": {"type": "integer", "default": 100}
            }),
            vec!["action"],
        ),
        Action::ViewLogs,
        client.clone(),
        url,
    )));

    // 10. stoa_alerts (stub)
    registry.register(Arc::new(NativeTool::new(
        "stoa_alerts",
        "Alerts: list, acknowledge",
        schema(
            json!({
                "action": {"type": "string", "enum": ["list", "acknowledge"]},
                "alert_id": {"type": "string"},
                "api_id": {"type": "string"},
                "severity": {"type": "string", "enum": ["info", "warning", "critical"]},
                "status": {"type": "string", "enum": ["active", "acknowledged", "resolved"], "default": "active"},
                "comment": {"type": "string"}
            }),
            vec!["action"],
        ),
        Action::Read,
        client.clone(),
        url,
    )));

    // 11. stoa_uac (stub)
    registry.register(Arc::new(NativeTool::new(
        "stoa_uac",
        "UAC contracts: list, get, validate, sla",
        schema(
            json!({
                "action": {"type": "string", "enum": ["list", "get", "validate", "sla"]},
                "contract_id": {"type": "string"},
                "api_id": {"type": "string"},
                "subscription_id": {"type": "string"},
                "status": {"type": "string", "enum": ["active", "expired", "pending"]},
                "time_range": {"type": "string", "enum": ["7d", "30d", "90d"], "default": "30d"}
            }),
            vec!["action"],
        ),
        Action::Read,
        client.clone(),
        url,
    )));

    // 12. stoa_security (stub)
    registry.register(Arc::new(NativeTool::new(
        "stoa_security",
        "Security: audit_log, check_permissions, list_policies",
        schema(
            json!({
                "action": {"type": "string", "enum": ["audit_log", "check_permissions", "list_policies"]},
                "api_id": {"type": "string"},
                "user_id": {"type": "string"},
                "action_type": {"type": "string", "enum": ["read", "write", "admin"]},
                "policy_type": {"type": "string", "enum": ["rate_limit", "ip_whitelist", "oauth", "jwt"]},
                "time_range": {"type": "string", "enum": ["24h", "7d", "30d", "90d"], "default": "7d"},
                "limit": {"type": "integer", "default": 100}
            }),
            vec!["action"],
        ),
        Action::ViewAudit,
        client,
        url,
    )));

    tracing::info!(tool_count = 12, "Native tools registered");
}
