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
use crate::cache::PromptCache;
use crate::mcp::session::SessionManager;
use crate::resilience::CircuitBreakerRegistry;
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
    /// Optional output schema for structured responses (MCP 2025-03-26)
    output_schema: Option<Value>,
    /// Optional session manager for health checks
    session_manager: Option<Arc<SessionManager>>,
    /// Optional circuit breaker registry for health checks
    circuit_breakers: Option<Arc<CircuitBreakerRegistry>>,
    /// Optional prompt cache for CAB-1123 cache tools
    prompt_cache: Option<Arc<PromptCache>>,
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
            output_schema: None,
            session_manager: None,
            circuit_breakers: None,
            prompt_cache: None,
        }
    }

    /// Create a NativeTool with access to the tool registry (for stoa_tools)
    pub fn with_registry(mut self, registry: Arc<ToolRegistry>) -> Self {
        self.tool_registry = Some(registry);
        self
    }

    /// Set output schema for structured responses (MCP 2025-03-26)
    pub fn with_output_schema(mut self, schema: Value) -> Self {
        self.output_schema = Some(schema);
        self
    }

    /// Set session manager reference for health checks
    pub fn with_session_manager(mut self, sm: Arc<SessionManager>) -> Self {
        self.session_manager = Some(sm);
        self
    }

    /// Set circuit breaker registry for health checks
    pub fn with_circuit_breakers(mut self, cb: Arc<CircuitBreakerRegistry>) -> Self {
        self.circuit_breakers = Some(cb);
        self
    }

    /// Set prompt cache for CAB-1123 cache tools
    pub fn with_prompt_cache(mut self, cache: Arc<PromptCache>) -> Self {
        self.prompt_cache = Some(cache);
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

    fn output_schema(&self) -> Option<Value> {
        self.output_schema.clone()
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
            "stoa_cache_load" => self.handle_cache_load(&args).await,
            "stoa_cache_get" => self.handle_cache_get(&args).await,
            "stoa_cache_invalidate" => self.handle_cache_invalidate().await,
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
            "mcp_protocol": "2025-03-26",
            "features": [
                "MCP SSE Transport",
                "OAuth 2.1 (RFC 9728)",
                "JWT Authentication",
                "API Key Authentication",
                "Multi-tenant Isolation",
                "Tool Discovery",
                "Prometheus Metrics",
                "Tool Annotations (MCP 2025-03-26)",
                "Batch Requests",
                "Elicitation"
            ],
            "status": "operational"
        });
        Ok(ToolResult::text(
            serde_json::to_string_pretty(&info).unwrap(),
        ))
    }

    async fn handle_platform_health(&self) -> Result<ToolResult, ToolError> {
        let session_count = self
            .session_manager
            .as_ref()
            .map(|sm| sm.count())
            .unwrap_or(0);

        let (cb_status, cb_detail) = self
            .circuit_breakers
            .as_ref()
            .map(|cb| {
                let entries = cb.stats_all();
                let total = entries.len();
                let open_count = entries.iter().filter(|e| e.state == "Open").count();
                let half_open_count = entries.iter().filter(|e| e.state == "HalfOpen").count();
                let status = if open_count > 0 {
                    "degraded"
                } else {
                    "healthy"
                };
                (
                    status,
                    json!({
                        "status": status,
                        "total": total,
                        "open": open_count,
                        "half_open": half_open_count,
                        "closed": total - open_count - half_open_count,
                    }),
                )
            })
            .unwrap_or((
                "healthy",
                json!({"status": "healthy", "detail": "not configured"}),
            ));

        let tool_count = self
            .tool_registry
            .as_ref()
            .map(|r| r.list(None).len())
            .unwrap_or(0);

        let overall = if cb_status == "degraded" {
            "degraded"
        } else {
            "healthy"
        };

        let health = json!({
            "status": overall,
            "components": {
                "gateway": {"status": "healthy", "version": env!("CARGO_PKG_VERSION")},
                "mcp_transport": {"status": "healthy"},
                "session_manager": {"status": "healthy", "active_sessions": session_count},
                "tool_registry": {"status": "healthy", "registered_tools": tool_count},
                "circuit_breakers": cb_detail,
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

    // ─── Prompt Cache Tools (CAB-1123 Phase 2) ──────────────────

    async fn handle_cache_load(&self, args: &Value) -> Result<ToolResult, ToolError> {
        let cache = self
            .prompt_cache
            .as_ref()
            .ok_or_else(|| ToolError::ExecutionFailed("Prompt cache not configured".into()))?;

        let entries = args
            .get("entries")
            .and_then(|v| v.as_array())
            .ok_or_else(|| ToolError::InvalidArguments("Missing 'entries' array".into()))?;

        let patterns: Vec<(String, String)> = entries
            .iter()
            .filter_map(|e| {
                let key = e.get("key")?.as_str()?;
                let value = e.get("value")?.as_str()?;
                Some((key.to_string(), value.to_string()))
            })
            .collect();

        let count = cache.load_patterns(patterns);
        Ok(ToolResult::text(
            json!({"loaded": count, "status": "ok"}).to_string(),
        ))
    }

    async fn handle_cache_get(&self, args: &Value) -> Result<ToolResult, ToolError> {
        let cache = self
            .prompt_cache
            .as_ref()
            .ok_or_else(|| ToolError::ExecutionFailed("Prompt cache not configured".into()))?;

        let key = args
            .get("key")
            .and_then(|v| v.as_str())
            .ok_or_else(|| ToolError::InvalidArguments("Missing 'key' parameter".into()))?;

        match cache.get(key) {
            Some(value) => Ok(ToolResult::text(
                json!({"key": key, "value": value}).to_string(),
            )),
            None => Ok(ToolResult::text(
                json!({"key": key, "error": "Pattern not found"}).to_string(),
            )),
        }
    }

    async fn handle_cache_invalidate(&self) -> Result<ToolResult, ToolError> {
        let cache = self
            .prompt_cache
            .as_ref()
            .ok_or_else(|| ToolError::ExecutionFailed("Prompt cache not configured".into()))?;

        cache.clear();
        Ok(ToolResult::text(json!({"status": "cleared"}).to_string()))
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
            | "stoa_cache_load"
            | "stoa_cache_get"
            | "stoa_cache_invalidate"
    )
}

/// Create all native tools and register them
pub fn register_native_tools(
    registry: &ToolRegistry,
    client: Client,
    cp_base_url: &str,
    tool_registry_ref: Arc<ToolRegistry>,
    session_manager: Option<Arc<SessionManager>>,
    circuit_breakers: Option<Arc<CircuitBreakerRegistry>>,
    prompt_cache: Option<Arc<PromptCache>>,
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
    registry.register(Arc::new(
        NativeTool::new(
            "stoa_platform_info",
            "Get STOA platform version, status, and available features",
            schema(json!({}), vec![]),
            Action::Read,
            client.clone(),
            url,
        )
        .with_output_schema(json!({
            "type": "object",
            "properties": {
                "platform": {"type": "string"},
                "gateway": {"type": "string"},
                "version": {"type": "string"},
                "mcp_protocol": {"type": "string"},
                "features": {"type": "array", "items": {"type": "string"}},
                "status": {"type": "string", "enum": ["operational", "degraded", "down"]}
            },
            "required": ["platform", "version", "status"]
        })),
    ));

    // 2. stoa_platform_health
    let mut health_tool = NativeTool::new(
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
    );
    if let Some(sm) = session_manager {
        health_tool = health_tool.with_session_manager(sm);
    }
    if let Some(cb) = circuit_breakers {
        health_tool = health_tool.with_circuit_breakers(cb);
    }
    registry.register(Arc::new(health_tool));

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
    registry.register(Arc::new(
        NativeTool::new(
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
        )
        .with_output_schema(json!({
            "type": "object",
            "properties": {
                "tenants": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "name": {"type": "string"},
                            "status": {"type": "string"}
                        }
                    }
                }
            }
        })),
    ));

    // 5. stoa_catalog
    registry.register(Arc::new(NativeTool::new(
        "stoa_catalog",
        "API catalog: list, get, search, versions, categories. Returns paginated API listings with filtering support.",
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
        client.clone(),
        url,
    )));

    // 13. stoa_cache_load (CAB-1123)
    let mut cache_load = NativeTool::new(
        "stoa_cache_load",
        "Load prompt patterns into the gateway cache for reuse across agent sessions",
        schema(
            json!({
                "entries": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string"},
                            "value": {"type": "string"}
                        },
                        "required": ["key", "value"]
                    },
                    "description": "Array of {key, value} pattern entries to cache"
                }
            }),
            vec!["entries"],
        ),
        Action::Create,
        client.clone(),
        url,
    );
    if let Some(ref pc) = prompt_cache {
        cache_load = cache_load.with_prompt_cache(pc.clone());
    }
    registry.register(Arc::new(cache_load));

    // 14. stoa_cache_get (CAB-1123)
    let mut cache_get = NativeTool::new(
        "stoa_cache_get",
        "Retrieve a cached prompt pattern by key",
        schema(
            json!({
                "key": {"type": "string", "description": "Cache key to look up"}
            }),
            vec!["key"],
        ),
        Action::Read,
        client.clone(),
        url,
    );
    if let Some(ref pc) = prompt_cache {
        cache_get = cache_get.with_prompt_cache(pc.clone());
    }
    registry.register(Arc::new(cache_get));

    // 15. stoa_cache_invalidate (CAB-1123)
    let mut cache_invalidate = NativeTool::new(
        "stoa_cache_invalidate",
        "Clear all cached prompt patterns",
        schema(json!({}), vec![]),
        Action::Delete,
        client,
        url,
    );
    if let Some(ref pc) = prompt_cache {
        cache_invalidate = cache_invalidate.with_prompt_cache(pc.clone());
    }
    registry.register(Arc::new(cache_invalidate));

    tracing::info!(tool_count = 15, "Native tools registered");
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::mcp::tools::{Tool, ToolContext, ToolRegistry, ToolSchema};
    use serde_json::json;
    use std::sync::Arc;

    fn make_ctx() -> ToolContext {
        ToolContext {
            tenant_id: "test-tenant".to_string(),
            user_id: Some("user-1".to_string()),
            user_email: Some("user@test.com".to_string()),
            request_id: "req-1".to_string(),
            roles: vec!["viewer".to_string()],
            scopes: vec!["stoa:read".to_string()],
            raw_token: None,
            skill_instructions: None,
            progress_token: None,
        }
    }

    fn make_tool(name: &str) -> NativeTool {
        NativeTool::new(
            name,
            "test tool",
            ToolSchema {
                schema_type: "object".to_string(),
                properties: Default::default(),
                required: vec![],
            },
            Action::Read,
            Client::new(),
            "http://localhost:8000",
        )
    }

    // ─── auth_header ───────────────────────────────────────────

    #[test]
    fn auth_header_none_when_no_token() {
        let tool = make_tool("test");
        let ctx = make_ctx();
        assert!(tool.auth_header(&ctx).is_none());
    }

    #[test]
    fn auth_header_formats_bearer_token() {
        let tool = make_tool("test");
        let mut ctx = make_ctx();
        ctx.raw_token = Some("abc123".to_string());
        assert_eq!(tool.auth_header(&ctx).unwrap(), "Bearer abc123");
    }

    // ─── has_native_implementation ─────────────────────────────

    #[test]
    fn has_native_impl_for_all_known_tools() {
        let known = [
            "stoa_platform_info",
            "stoa_platform_health",
            "stoa_tools",
            "stoa_tenants",
            "stoa_catalog",
            "stoa_api_spec",
            "stoa_subscription",
            "stoa_metrics",
            "stoa_logs",
            "stoa_alerts",
            "stoa_uac",
            "stoa_security",
            "stoa_cache_load",
            "stoa_cache_get",
            "stoa_cache_invalidate",
        ];
        for name in &known {
            assert!(has_native_implementation(name), "{} should be native", name);
        }
    }

    #[test]
    fn has_native_impl_false_for_unknown() {
        assert!(!has_native_implementation("custom_tool"));
        assert!(!has_native_implementation(""));
    }

    // ─── handle_platform_info ──────────────────────────────────

    #[tokio::test]
    async fn platform_info_returns_valid_json() {
        let tool = make_tool("stoa_platform_info");
        let result = tool.handle_platform_info().await.unwrap();

        let text = match &result.content[0] {
            crate::mcp::tools::ToolContent::Text { text } => text,
            _ => panic!("expected text content"),
        };
        let v: Value = serde_json::from_str(text).unwrap();
        assert_eq!(v["platform"], "STOA");
        assert_eq!(v["status"], "operational");
        assert!(v["features"].as_array().unwrap().len() > 5);
        assert!(!v["version"].as_str().unwrap().is_empty());
    }

    // ─── handle_platform_health ────────────────────────────────

    #[tokio::test]
    async fn platform_health_returns_components() {
        let tool = make_tool("stoa_platform_health");
        let result = tool.handle_platform_health().await.unwrap();

        let text = match &result.content[0] {
            crate::mcp::tools::ToolContent::Text { text } => text,
            _ => panic!("expected text content"),
        };
        let v: Value = serde_json::from_str(text).unwrap();
        assert_eq!(v["status"], "healthy");
        assert!(v["components"]["gateway"]["status"].is_string());
        assert!(v["timestamp"].is_string());
    }

    // ─── handle_tools (with real ToolRegistry) ─────────────────

    #[tokio::test]
    async fn tools_list_action() {
        let registry = Arc::new(ToolRegistry::new());
        // Register one tool for testing
        registry.register(Arc::new(make_tool("test_tool_alpha")));

        let tool = make_tool("stoa_tools").with_registry(registry);
        let ctx = make_ctx();
        let args = json!({"action": "list"});
        let result = tool.handle_tools(&args, &ctx).await.unwrap();

        let text = match &result.content[0] {
            crate::mcp::tools::ToolContent::Text { text } => text,
            _ => panic!("expected text content"),
        };
        let v: Value = serde_json::from_str(text).unwrap();
        assert_eq!(v["count"], 1);
        assert_eq!(v["tools"][0]["name"], "test_tool_alpha");
    }

    #[tokio::test]
    async fn tools_schema_action() {
        let registry = Arc::new(ToolRegistry::new());
        registry.register(Arc::new(make_tool("my_tool")));

        let tool = make_tool("stoa_tools").with_registry(registry);
        let ctx = make_ctx();
        let args = json!({"action": "schema", "tool_name": "my_tool"});
        let result = tool.handle_tools(&args, &ctx).await.unwrap();

        let text = match &result.content[0] {
            crate::mcp::tools::ToolContent::Text { text } => text,
            _ => panic!("expected text content"),
        };
        let v: Value = serde_json::from_str(text).unwrap();
        assert_eq!(v["name"], "my_tool");
    }

    #[tokio::test]
    async fn tools_schema_not_found() {
        let registry = Arc::new(ToolRegistry::new());
        let tool = make_tool("stoa_tools").with_registry(registry);
        let ctx = make_ctx();
        let args = json!({"action": "schema", "tool_name": "nonexistent"});
        let result = tool.handle_tools(&args, &ctx).await.unwrap();

        let text = match &result.content[0] {
            crate::mcp::tools::ToolContent::Text { text } => text,
            _ => panic!("expected text content"),
        };
        assert!(text.contains("not found"));
    }

    #[tokio::test]
    async fn tools_schema_missing_tool_name() {
        let registry = Arc::new(ToolRegistry::new());
        let tool = make_tool("stoa_tools").with_registry(registry);
        let ctx = make_ctx();
        let args = json!({"action": "schema"});
        let result = tool.handle_tools(&args, &ctx).await.unwrap();

        let text = match &result.content[0] {
            crate::mcp::tools::ToolContent::Text { text } => text,
            _ => panic!("expected text content"),
        };
        assert!(text.contains("Missing"));
    }

    #[tokio::test]
    async fn tools_search_action() {
        let registry = Arc::new(ToolRegistry::new());
        registry.register(Arc::new(make_tool("catalog_tool")));
        registry.register(Arc::new(make_tool("platform_tool")));

        let tool = make_tool("stoa_tools").with_registry(registry);
        let ctx = make_ctx();
        let args = json!({"action": "search", "query": "catalog"});
        let result = tool.handle_tools(&args, &ctx).await.unwrap();

        let text = match &result.content[0] {
            crate::mcp::tools::ToolContent::Text { text } => text,
            _ => panic!("expected text content"),
        };
        let v: Value = serde_json::from_str(text).unwrap();
        assert_eq!(v["count"], 1);
    }

    #[tokio::test]
    async fn tools_no_registry_returns_message() {
        let tool = make_tool("stoa_tools"); // no registry
        let ctx = make_ctx();
        let args = json!({"action": "list"});
        let result = tool.handle_tools(&args, &ctx).await.unwrap();

        let text = match &result.content[0] {
            crate::mcp::tools::ToolContent::Text { text } => text,
            _ => panic!("expected text content"),
        };
        assert!(text.contains("not available"));
    }

    #[tokio::test]
    async fn tools_unknown_action() {
        let registry = Arc::new(ToolRegistry::new());
        let tool = make_tool("stoa_tools").with_registry(registry);
        let ctx = make_ctx();
        let args = json!({"action": "delete"});
        let result = tool.handle_tools(&args, &ctx).await.unwrap();

        let text = match &result.content[0] {
            crate::mcp::tools::ToolContent::Text { text } => text,
            _ => panic!("expected text content"),
        };
        assert!(text.contains("Unknown action"));
    }

    // ─── Stub handlers ────────────────────────────────────────

    #[tokio::test]
    async fn metrics_stub_returns_coming_soon() {
        let tool = make_tool("stoa_metrics");
        let args = json!({"action": "usage"});
        let result = tool.handle_metrics_stub(&args).await.unwrap();

        let text = match &result.content[0] {
            crate::mcp::tools::ToolContent::Text { text } => text,
            _ => panic!("expected text content"),
        };
        let v: Value = serde_json::from_str(text).unwrap();
        assert_eq!(v["status"], "coming_soon");
        assert_eq!(v["action"], "usage");
        assert_eq!(v["placeholder"], true);
    }

    #[tokio::test]
    async fn logs_stub_returns_coming_soon() {
        let tool = make_tool("stoa_logs");
        let args = json!({"action": "search"});
        let result = tool.handle_logs_stub(&args).await.unwrap();

        let text = match &result.content[0] {
            crate::mcp::tools::ToolContent::Text { text } => text,
            _ => panic!("expected text content"),
        };
        let v: Value = serde_json::from_str(text).unwrap();
        assert_eq!(v["status"], "coming_soon");
    }

    #[tokio::test]
    async fn alerts_stub_returns_coming_soon() {
        let tool = make_tool("stoa_alerts");
        let args = json!({"action": "list"});
        let result = tool.handle_alerts_stub(&args).await.unwrap();

        let text = match &result.content[0] {
            crate::mcp::tools::ToolContent::Text { text } => text,
            _ => panic!("expected text content"),
        };
        let v: Value = serde_json::from_str(text).unwrap();
        assert_eq!(v["status"], "coming_soon");
        assert!(v["alerts"].as_array().unwrap().is_empty());
    }

    #[tokio::test]
    async fn uac_stub_returns_coming_soon() {
        let tool = make_tool("stoa_uac");
        let args = json!({"action": "list"});
        let result = tool.handle_uac_stub(&args).await.unwrap();

        let text = match &result.content[0] {
            crate::mcp::tools::ToolContent::Text { text } => text,
            _ => panic!("expected text content"),
        };
        let v: Value = serde_json::from_str(text).unwrap();
        assert_eq!(v["status"], "coming_soon");
    }

    #[tokio::test]
    async fn security_stub_returns_coming_soon() {
        let tool = make_tool("stoa_security");
        let args = json!({"action": "audit_log"});
        let result = tool.handle_security_stub(&args).await.unwrap();

        let text = match &result.content[0] {
            crate::mcp::tools::ToolContent::Text { text } => text,
            _ => panic!("expected text content"),
        };
        let v: Value = serde_json::from_str(text).unwrap();
        assert_eq!(v["status"], "coming_soon");
        assert_eq!(v["action"], "audit_log");
    }

    // ─── execute routing ──────────────────────────────────────

    #[tokio::test]
    async fn execute_routes_to_platform_info() {
        let tool = make_tool("stoa_platform_info");
        let ctx = make_ctx();
        let result = tool.execute(json!({}), &ctx).await.unwrap();
        let text = match &result.content[0] {
            crate::mcp::tools::ToolContent::Text { text } => text,
            _ => panic!("expected text content"),
        };
        assert!(text.contains("STOA"));
    }

    #[tokio::test]
    async fn execute_unknown_tool_returns_error() {
        let tool = make_tool("unknown_xyz");
        let ctx = make_ctx();
        let result = tool.execute(json!({}), &ctx).await;
        assert!(result.is_err());
        let err = result.unwrap_err();
        assert!(err.to_string().contains("Unknown native tool"));
    }

    // ─── Tool trait methods ───────────────────────────────────

    #[test]
    fn trait_name_description() {
        let tool = make_tool("stoa_catalog");
        assert_eq!(tool.name(), "stoa_catalog");
        assert_eq!(tool.description(), "test tool");
    }

    #[test]
    fn trait_required_action() {
        let tool = make_tool("test");
        assert_eq!(tool.required_action(), Action::Read);
    }

    #[test]
    fn output_schema_none_by_default() {
        let tool = make_tool("test");
        assert!(tool.output_schema().is_none());
    }

    #[test]
    fn output_schema_set_with_builder() {
        let tool = make_tool("test").with_output_schema(json!({"type": "object"}));
        assert!(tool.output_schema().is_some());
    }

    // ─── create_http_client ───────────────────────────────────

    #[test]
    fn create_http_client_succeeds() {
        let _client = create_http_client();
        // Just ensure it doesn't panic
    }

    // ─── cp_base_url trailing slash ───────────────────────────

    #[test]
    fn base_url_strips_trailing_slash() {
        let tool = NativeTool::new(
            "test",
            "test",
            ToolSchema {
                schema_type: "object".to_string(),
                properties: Default::default(),
                required: vec![],
            },
            Action::Read,
            Client::new(),
            "http://localhost:8000/",
        );
        assert_eq!(tool.cp_base_url, "http://localhost:8000");
    }

    // ================================================================
    // PR2: Wiremock-based HTTP tests
    // ================================================================

    mod http {
        use super::*;
        use wiremock::matchers::{method, path};
        use wiremock::{Mock, MockServer, ResponseTemplate};

        async fn make_mock_tool(mock: &MockServer, name: &str) -> NativeTool {
            NativeTool::new(
                name,
                "test tool",
                ToolSchema {
                    schema_type: "object".to_string(),
                    properties: Default::default(),
                    required: vec![],
                },
                Action::Read,
                Client::new(),
                &mock.uri(),
            )
        }

        // ─── GET / POST / DELETE helpers ───────────────────────────

        #[tokio::test]
        async fn get_success() {
            let mock = MockServer::start().await;
            Mock::given(method("GET"))
                .and(path("/v1/test"))
                .respond_with(ResponseTemplate::new(200).set_body_json(json!({"ok": true})))
                .mount(&mock)
                .await;

            let tool = make_mock_tool(&mock, "test").await;
            let ctx = make_ctx();
            let result = tool.get("/v1/test", &ctx).await.unwrap();
            assert_eq!(result["ok"], true);
        }

        #[tokio::test]
        async fn get_error_status() {
            let mock = MockServer::start().await;
            Mock::given(method("GET"))
                .and(path("/v1/fail"))
                .respond_with(ResponseTemplate::new(404).set_body_string("not found"))
                .mount(&mock)
                .await;

            let tool = make_mock_tool(&mock, "test").await;
            let ctx = make_ctx();
            let err = tool.get("/v1/fail", &ctx).await.unwrap_err();
            assert!(err.to_string().contains("404"));
        }

        #[tokio::test]
        async fn post_success() {
            let mock = MockServer::start().await;
            Mock::given(method("POST"))
                .and(path("/v1/create"))
                .respond_with(ResponseTemplate::new(200).set_body_json(json!({"id": "new-1"})))
                .mount(&mock)
                .await;

            let tool = make_mock_tool(&mock, "test").await;
            let ctx = make_ctx();
            let body = json!({"name": "test"});
            let result = tool.post("/v1/create", &body, &ctx).await.unwrap();
            assert_eq!(result["id"], "new-1");
        }

        #[tokio::test]
        async fn post_error_status() {
            let mock = MockServer::start().await;
            Mock::given(method("POST"))
                .and(path("/v1/create"))
                .respond_with(ResponseTemplate::new(400).set_body_string("bad request"))
                .mount(&mock)
                .await;

            let tool = make_mock_tool(&mock, "test").await;
            let ctx = make_ctx();
            let err = tool.post("/v1/create", &json!({}), &ctx).await.unwrap_err();
            assert!(err.to_string().contains("400"));
        }

        #[tokio::test]
        async fn delete_success_with_body() {
            let mock = MockServer::start().await;
            Mock::given(method("DELETE"))
                .and(path("/v1/items/1"))
                .respond_with(ResponseTemplate::new(200).set_body_json(json!({"deleted": true})))
                .mount(&mock)
                .await;

            let tool = make_mock_tool(&mock, "test").await;
            let ctx = make_ctx();
            let result = tool.delete("/v1/items/1", &ctx).await.unwrap();
            assert_eq!(result["deleted"], true);
        }

        #[tokio::test]
        async fn delete_success_empty_body() {
            let mock = MockServer::start().await;
            Mock::given(method("DELETE"))
                .and(path("/v1/items/2"))
                .respond_with(ResponseTemplate::new(200))
                .mount(&mock)
                .await;

            let tool = make_mock_tool(&mock, "test").await;
            let ctx = make_ctx();
            let result = tool.delete("/v1/items/2", &ctx).await.unwrap();
            assert_eq!(result["status"], "deleted");
        }

        // ─── handle_tenants ────────────────────────────────────────

        #[tokio::test]
        async fn tenants_success() {
            let mock = MockServer::start().await;
            Mock::given(method("GET"))
                .and(path("/v1/tenants"))
                .respond_with(ResponseTemplate::new(200).set_body_json(json!({
                    "tenants": [{"id": "t1", "name": "Acme"}]
                })))
                .mount(&mock)
                .await;

            let tool = make_mock_tool(&mock, "stoa_tenants").await;
            let ctx = make_ctx();
            let result = tool.handle_tenants(&ctx).await.unwrap();
            let text = match &result.content[0] {
                crate::mcp::tools::ToolContent::Text { text } => text,
                _ => panic!("expected text"),
            };
            let v: Value = serde_json::from_str(text).unwrap();
            assert_eq!(v["tenants"][0]["id"], "t1");
        }

        #[tokio::test]
        async fn tenants_error() {
            let mock = MockServer::start().await;
            Mock::given(method("GET"))
                .and(path("/v1/tenants"))
                .respond_with(ResponseTemplate::new(403).set_body_string("forbidden"))
                .mount(&mock)
                .await;

            let tool = make_mock_tool(&mock, "stoa_tenants").await;
            let ctx = make_ctx();
            let err = tool.handle_tenants(&ctx).await.unwrap_err();
            assert!(err.to_string().contains("403"));
        }

        // ─── handle_catalog ────────────────────────────────────────

        #[tokio::test]
        async fn catalog_list() {
            let mock = MockServer::start().await;
            Mock::given(method("GET"))
                .and(path("/v1/portal/apis"))
                .respond_with(ResponseTemplate::new(200).set_body_json(json!({
                    "apis": [{"id": "api1", "name": "My API"}]
                })))
                .mount(&mock)
                .await;

            let tool = make_mock_tool(&mock, "stoa_catalog").await;
            let ctx = make_ctx();
            let result = tool
                .handle_catalog(&json!({"action": "list"}), &ctx)
                .await
                .unwrap();
            let text = match &result.content[0] {
                crate::mcp::tools::ToolContent::Text { text } => text,
                _ => panic!("expected text"),
            };
            let v: Value = serde_json::from_str(text).unwrap();
            assert!(v["apis"].is_array());
        }

        #[tokio::test]
        async fn catalog_get() {
            let mock = MockServer::start().await;
            Mock::given(method("GET"))
                .and(path("/v1/portal/apis/api1"))
                .respond_with(ResponseTemplate::new(200).set_body_json(json!({
                    "id": "api1", "name": "My API"
                })))
                .mount(&mock)
                .await;

            let tool = make_mock_tool(&mock, "stoa_catalog").await;
            let ctx = make_ctx();
            let result = tool
                .handle_catalog(&json!({"action": "get", "api_id": "api1"}), &ctx)
                .await
                .unwrap();
            let text = match &result.content[0] {
                crate::mcp::tools::ToolContent::Text { text } => text,
                _ => panic!("expected text"),
            };
            let v: Value = serde_json::from_str(text).unwrap();
            assert_eq!(v["id"], "api1");
        }

        #[tokio::test]
        async fn catalog_search() {
            let mock = MockServer::start().await;
            Mock::given(method("GET"))
                .and(path("/v1/portal/apis"))
                .respond_with(ResponseTemplate::new(200).set_body_json(json!({
                    "apis": [{"id": "payments", "name": "Payments"}]
                })))
                .mount(&mock)
                .await;

            let tool = make_mock_tool(&mock, "stoa_catalog").await;
            let ctx = make_ctx();
            let result = tool
                .handle_catalog(&json!({"action": "search", "query": "pay"}), &ctx)
                .await
                .unwrap();
            let text = match &result.content[0] {
                crate::mcp::tools::ToolContent::Text { text } => text,
                _ => panic!("expected text"),
            };
            assert!(text.contains("payments") || text.contains("Payments"));
        }

        // ─── handle_subscription ───────────────────────────────────

        #[tokio::test]
        async fn subscription_list() {
            let mock = MockServer::start().await;
            Mock::given(method("GET"))
                .and(path("/v1/mcp/subscriptions"))
                .respond_with(ResponseTemplate::new(200).set_body_json(json!({
                    "subscriptions": [{"id": "sub-1"}]
                })))
                .mount(&mock)
                .await;

            let tool = make_mock_tool(&mock, "stoa_subscription").await;
            let ctx = make_ctx();
            let result = tool
                .handle_subscription(&json!({"action": "list"}), &ctx)
                .await
                .unwrap();
            let text = match &result.content[0] {
                crate::mcp::tools::ToolContent::Text { text } => text,
                _ => panic!("expected text"),
            };
            let v: Value = serde_json::from_str(text).unwrap();
            assert!(v["subscriptions"].is_array());
        }

        #[tokio::test]
        async fn subscription_create() {
            let mock = MockServer::start().await;
            Mock::given(method("POST"))
                .and(path("/v1/mcp/subscriptions"))
                .respond_with(ResponseTemplate::new(200).set_body_json(json!({
                    "id": "sub-new", "status": "pending"
                })))
                .mount(&mock)
                .await;

            let tool = make_mock_tool(&mock, "stoa_subscription").await;
            let ctx = make_ctx();
            let result = tool
                .handle_subscription(
                    &json!({"action": "create", "api_id": "api1", "plan": "free"}),
                    &ctx,
                )
                .await
                .unwrap();
            let text = match &result.content[0] {
                crate::mcp::tools::ToolContent::Text { text } => text,
                _ => panic!("expected text"),
            };
            let v: Value = serde_json::from_str(text).unwrap();
            assert_eq!(v["status"], "pending");
        }

        #[tokio::test]
        async fn subscription_error() {
            let mock = MockServer::start().await;
            Mock::given(method("GET"))
                .and(path("/v1/mcp/subscriptions"))
                .respond_with(ResponseTemplate::new(500).set_body_string("server error"))
                .mount(&mock)
                .await;

            let tool = make_mock_tool(&mock, "stoa_subscription").await;
            let ctx = make_ctx();
            let err = tool
                .handle_subscription(&json!({"action": "list"}), &ctx)
                .await
                .unwrap_err();
            assert!(err.to_string().contains("500"));
        }
    }

    // ─── Prompt Cache Tools (CAB-1123) ──────────────────────────

    mod cache_tools {
        use super::*;
        use crate::cache::{PromptCache, PromptCacheConfig};

        fn make_cache_tool(name: &str) -> NativeTool {
            let cache = Arc::new(PromptCache::new(PromptCacheConfig::default()));
            make_tool(name).with_prompt_cache(cache)
        }

        #[tokio::test]
        async fn cache_load_inserts_entries() {
            let cache = Arc::new(PromptCache::new(PromptCacheConfig::default()));
            let tool = make_tool("stoa_cache_load").with_prompt_cache(cache.clone());
            let args = json!({
                "entries": [
                    {"key": "greet", "value": "Hello!"},
                    {"key": "bye", "value": "Goodbye!"}
                ]
            });
            let result = tool.handle_cache_load(&args).await.unwrap();
            let text = match &result.content[0] {
                crate::mcp::tools::ToolContent::Text { text } => text,
                _ => panic!("expected text content"),
            };
            assert!(text.contains("\"loaded\":2"));
            assert_eq!(cache.get("greet").unwrap(), "Hello!");
        }

        #[tokio::test]
        async fn cache_get_returns_value() {
            let cache = Arc::new(PromptCache::new(PromptCacheConfig::default()));
            cache.put("k1".into(), "v1".into());
            let tool = make_tool("stoa_cache_get").with_prompt_cache(cache);
            let result = tool.handle_cache_get(&json!({"key": "k1"})).await.unwrap();
            let text = match &result.content[0] {
                crate::mcp::tools::ToolContent::Text { text } => text,
                _ => panic!("expected text content"),
            };
            assert!(text.contains("v1"));
        }

        #[tokio::test]
        async fn cache_get_missing_key() {
            let tool = make_cache_tool("stoa_cache_get");
            let result = tool
                .handle_cache_get(&json!({"key": "nope"}))
                .await
                .unwrap();
            let text = match &result.content[0] {
                crate::mcp::tools::ToolContent::Text { text } => text,
                _ => panic!("expected text content"),
            };
            assert!(text.contains("Pattern not found"));
        }

        #[tokio::test]
        async fn cache_invalidate_clears_all() {
            let cache = Arc::new(PromptCache::new(PromptCacheConfig::default()));
            cache.put("a".into(), "1".into());
            let tool = make_tool("stoa_cache_invalidate").with_prompt_cache(cache.clone());
            let result = tool.handle_cache_invalidate().await.unwrap();
            let text = match &result.content[0] {
                crate::mcp::tools::ToolContent::Text { text } => text,
                _ => panic!("expected text content"),
            };
            assert!(text.contains("cleared"));
            assert_eq!(cache.stats().entry_count, 0);
        }

        #[test]
        fn has_native_impl_includes_cache_tools() {
            assert!(has_native_implementation("stoa_cache_load"));
            assert!(has_native_implementation("stoa_cache_get"));
            assert!(has_native_implementation("stoa_cache_invalidate"));
        }
    }
}
