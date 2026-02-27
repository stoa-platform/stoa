//! STOA Tool Registration — Native + Dynamic Discovery
//!
//! Phase 1: Native tools call CP API directly (no Python mcp-gateway).
//!
//! Flow:
//!   1. Register native tools (12 STOA tools, direct CP API calls)
//!   2. Try `GET /v1/mcp/tools` on Control Plane → dynamic registration for unknown tools
//!   3. Try `GET /v1/mcp/generated-tools` → UAC-generated tools (CAB-606)
//!   4. Background task refreshes every 60s from CP (only registers non-native tools)

use std::sync::Arc;
use std::time::Duration;

use super::native_tool::{create_http_client, has_native_implementation, register_native_tools};
use super::proxy_tool::ProxyTool;
use super::{ToolRegistry, ToolSchema};
use crate::cache::PromptCache;
use crate::control_plane::{GeneratedToolDef, RemoteToolDef, ToolProxyClient};
use crate::mcp::session::SessionManager;
use crate::resilience::{
    retry_with_backoff, CircuitBreaker, CircuitBreakerError, CircuitBreakerRegistry, RetryConfig,
};
use crate::uac::Action;

/// Default refresh interval for tool discovery
const TOOL_REFRESH_INTERVAL: Duration = Duration::from_secs(60);

/// Convert a remote tool definition into a ProxyTool and register it.
/// Only used for tools that don't have native implementations.
fn register_remote_tool(registry: &ToolRegistry, def: &RemoteToolDef, cp: &Arc<ToolProxyClient>) {
    // Skip if we have a native implementation
    if has_native_implementation(&def.name) {
        tracing::debug!(tool = %def.name, "Skipping remote registration — native implementation exists");
        return;
    }

    let tool_schema = ToolSchema {
        schema_type: def.input_schema.schema_type.clone(),
        properties: def.input_schema.properties.clone(),
        required: def.input_schema.required.clone(),
    };

    // Infer action from tool name
    let action = infer_action(&def.name);

    registry.register(Arc::new(ProxyTool::new(
        &def.name,
        &def.description,
        tool_schema,
        action,
        cp.clone(),
    )));

    tracing::info!(tool = %def.name, "Registered remote tool (proxy fallback)");
}

/// Register a UAC-generated tool definition as a ProxyTool (CAB-606).
///
/// Generated tools use the naming convention `{contract}:{operation_id}` and
/// come from the Control Plane's `GET /v1/mcp/generated-tools` endpoint.
/// If the tool name collides with a native tool, an alias is registered
/// so clients can still call the generated variant by its full name.
fn register_generated_tool(
    registry: &ToolRegistry,
    def: &GeneratedToolDef,
    cp: &Arc<ToolProxyClient>,
) {
    // Build input schema from the definition (or default to empty object)
    let tool_schema = match &def.input_schema {
        Some(schema_val) => {
            let properties: std::collections::HashMap<String, serde_json::Value> = schema_val
                .get("properties")
                .and_then(|p| serde_json::from_value(p.clone()).ok())
                .unwrap_or_default();
            let required: Vec<String> = schema_val
                .get("required")
                .and_then(|r| serde_json::from_value(r.clone()).ok())
                .unwrap_or_default();
            ToolSchema {
                schema_type: "object".to_string(),
                properties,
                required,
            }
        }
        None => ToolSchema {
            schema_type: "object".to_string(),
            properties: Default::default(),
            required: vec![],
        },
    };

    let action = infer_action(&def.tool_name);
    let description = def
        .description
        .clone()
        .unwrap_or_else(|| format!("UAC-generated tool: {}", def.tool_name));

    registry.register(Arc::new(ProxyTool::new(
        &def.tool_name,
        &description,
        tool_schema,
        action,
        cp.clone(),
    )));

    tracing::info!(
        tool = %def.tool_name,
        version = %def.version,
        "Registered UAC-generated tool (CAB-606)"
    );
}

/// Infer UAC action from tool name convention
fn infer_action(tool_name: &str) -> Action {
    if tool_name.contains("security") || tool_name.contains("audit") {
        Action::ViewAudit
    } else if tool_name.contains("logs") {
        Action::ViewLogs
    } else if tool_name.contains("metrics") {
        Action::ViewMetrics
    } else if tool_name.contains("create") {
        Action::Create
    } else if tool_name.contains("update") {
        Action::Update
    } else if tool_name.contains("delete") {
        Action::Delete
    } else {
        Action::Read
    }
}

// ─── Native + Dynamic Discovery ───────────────────────────────────

/// Register native tools and try to discover additional tools from CP.
///
/// Native tools (12 STOA tools) are always registered and call CP API directly.
/// Additional tools discovered from CP are registered as ProxyTool (fallback).
/// Phase 6: CP discovery is wrapped with circuit breaker + retry for resilience.
/// CAB-606: Also discovers UAC-generated tools from the generated-tools endpoint.
pub async fn discover_and_register(
    registry: Arc<ToolRegistry>,
    cp: &Arc<ToolProxyClient>,
    cb: Arc<CircuitBreaker>,
    session_manager: Option<Arc<SessionManager>>,
    circuit_breakers: Option<Arc<CircuitBreakerRegistry>>,
    prompt_cache: Option<Arc<PromptCache>>,
) -> Result<usize, String> {
    // First, register all native tools
    let cp_url = cp.base_url();
    let http_client = create_http_client();
    // Pass the actual registry so stoa_tools can introspect it
    register_native_tools(
        &registry,
        http_client,
        cp_url,
        registry.clone(),
        session_manager,
        circuit_breakers,
        prompt_cache,
    );

    tracing::info!("Native tools registered (12 STOA tools, direct CP API calls)");

    // Then, try to discover additional tools from CP (with circuit breaker + retry)
    let defs_result = discover_with_resilience(cp, &cb).await;

    match defs_result {
        Ok(defs) => {
            let mut proxy_count = 0;
            for def in &defs {
                if !has_native_implementation(&def.name) {
                    register_remote_tool(&registry, def, cp);
                    proxy_count += 1;
                }
            }
            if proxy_count > 0 {
                tracing::info!(proxy_count, "Additional tools registered via CP proxy");
            }
        }
        Err(e) => {
            tracing::warn!(error = %e, "CP unreachable — using native tools only");
        }
    }

    // CAB-606: Discover UAC-generated tools (best-effort, non-blocking)
    discover_generated_tools_best_effort(&registry, cp).await;

    Ok(registry.count())
}

/// Discover UAC-generated tools from CP (CAB-606).
///
/// Best-effort: logs a warning on failure but doesn't block startup.
/// Uses a default tenant ID for initial discovery; per-tenant discovery
/// happens in `refresh_tools_for_tenant()`.
async fn discover_generated_tools_best_effort(registry: &ToolRegistry, cp: &Arc<ToolProxyClient>) {
    match cp.discover_generated_tools("_default").await {
        Ok(gen_tools) => {
            let mut gen_count = 0;
            for def in &gen_tools {
                if !registry.exists(&def.tool_name) {
                    register_generated_tool(registry, def, cp);
                    gen_count += 1;
                }
            }
            if gen_count > 0 {
                tracing::info!(gen_count, "UAC-generated tools registered (CAB-606)");
            }
        }
        Err(e) => {
            tracing::debug!(
                error = %e,
                "Generated tools discovery unavailable (CAB-606 endpoint may not exist yet)"
            );
        }
    }
}

/// Discover tools from CP with circuit breaker + retry.
///
/// The circuit breaker fast-fails when CP is known to be down.
/// Retry handles transient network issues with exponential backoff.
async fn discover_with_resilience(
    cp: &Arc<ToolProxyClient>,
    cb: &Arc<CircuitBreaker>,
) -> Result<Vec<RemoteToolDef>, String> {
    let retry_config = RetryConfig {
        max_attempts: 2,
        initial_delay: Duration::from_millis(500),
        ..RetryConfig::default()
    };

    let cp_ref = cp.clone();
    let cb_ref = cb.clone();

    retry_with_backoff(&retry_config, "cp-discover-tools", || {
        let cp_inner = cp_ref.clone();
        let cb_inner = cb_ref.clone();
        async move {
            match cb_inner.call(cp_inner.discover_tools()).await {
                Ok(defs) => Ok(defs),
                Err(CircuitBreakerError::CircuitOpen) => {
                    Err("Circuit breaker open — CP API unavailable".to_string())
                }
                Err(CircuitBreakerError::OperationFailed(e)) => Err(e),
            }
        }
    })
    .await
}

/// Start a background task that periodically refreshes tools from CP.
/// Only registers tools that don't have native implementations.
/// Phase 6: Uses circuit breaker + retry for resilient discovery.
pub fn start_tool_refresh_task(
    registry: Arc<ToolRegistry>,
    cp: Arc<ToolProxyClient>,
    cb: Arc<CircuitBreaker>,
) {
    tokio::spawn(async move {
        loop {
            tokio::time::sleep(TOOL_REFRESH_INTERVAL).await;

            match discover_with_resilience(&cp, &cb).await {
                Ok(defs) => {
                    let mut new_count = 0;
                    for def in &defs {
                        if !has_native_implementation(&def.name)
                            && registry.get(&def.name).is_none()
                        {
                            register_remote_tool(&registry, def, &cp);
                            new_count += 1;
                        }
                    }
                    if new_count > 0 {
                        tracing::info!(new_count, "New proxy tools discovered from CP");
                    }
                }
                Err(e) => {
                    tracing::debug!(error = %e, "Tool refresh from CP failed (keeping existing tools)");
                }
            }

            // CAB-606: Also refresh generated tools
            discover_generated_tools_best_effort(&registry, &cp).await;
        }
    });
}

// ─── Per-Tenant Refresh (CAB-1317 Phase 2) ────────────────────────

/// Refresh tools for a specific tenant by re-discovering from CP.
///
/// Only registers NEW tools that don't already have native implementations.
/// Marks the tenant as freshly loaded in the registry (staleness tracking).
/// Called by handlers.rs stale-while-revalidate logic.
/// CAB-606: Also discovers tenant-scoped generated tools.
pub async fn refresh_tools_for_tenant(
    registry: &Arc<ToolRegistry>,
    cp: &Arc<ToolProxyClient>,
    cb: Arc<CircuitBreaker>,
    tenant_id: &str,
) -> Result<usize, String> {
    // CAB-1558: Always mark tenant as loaded, even on discovery failure.
    // Without this, a failed refresh leaves the tenant "never loaded" —
    // every subsequent request retriggers a synchronous HTTP call to the
    // control plane, creating a retry storm that tanks p95 latency.
    // The TTL-based refresh (default 300s) will reattempt later.
    let start = std::time::Instant::now();
    let defs = match discover_with_resilience(cp, &cb).await {
        Ok(d) => {
            crate::metrics::record_tool_discovery(
                tenant_id,
                "success",
                start.elapsed().as_secs_f64(),
            );
            d
        }
        Err(e) => {
            crate::metrics::record_tool_discovery(
                tenant_id,
                "failure",
                start.elapsed().as_secs_f64(),
            );
            registry.mark_loaded(tenant_id);
            tracing::warn!(
                tenant_id = %tenant_id,
                error = %e,
                "Tool discovery failed — marked loaded to prevent retry storm (CAB-1558)"
            );
            return Err(e);
        }
    };
    let mut new_count = 0;
    for def in &defs {
        if !has_native_implementation(&def.name) && registry.get(&def.name).is_none() {
            register_remote_tool(registry, def, cp);
            new_count += 1;
        }
    }

    // CAB-606: Discover tenant-specific generated tools
    match cp.discover_generated_tools(tenant_id).await {
        Ok(gen_tools) => {
            for def in &gen_tools {
                if !registry.exists(&def.tool_name) {
                    register_generated_tool(registry, def, cp);
                    new_count += 1;
                }
            }
        }
        Err(e) => {
            tracing::debug!(
                tenant_id = %tenant_id,
                error = %e,
                "Generated tools discovery failed for tenant (CAB-606)"
            );
        }
    }

    registry.mark_loaded(tenant_id);
    if new_count > 0 {
        tracing::info!(new_count, tenant_id = %tenant_id, "Tenant tool refresh: new tools registered");
    }
    Ok(new_count)
}

// ─── Legacy Fallback (kept for compatibility) ─────────────────────

/// Register the 12 STOA tools with ProxyTool (legacy fallback).
///
/// Used when `STOA_NATIVE_TOOLS_ENABLED=false` to proxy through Python mcp-gateway.
pub fn register_static_tools(registry: &ToolRegistry, cp: Arc<ToolProxyClient>) {
    use serde_json::json;

    /// Helper to build a ToolSchema from JSON properties
    fn schema(props: serde_json::Value, required: Vec<&str>) -> ToolSchema {
        ToolSchema {
            schema_type: "object".into(),
            properties: serde_json::from_value(props).unwrap_or_default(),
            required: required.iter().map(|s| s.to_string()).collect(),
        }
    }

    // 1. stoa_platform_info
    registry.register(Arc::new(ProxyTool::new(
        "stoa_platform_info",
        "Get STOA platform version, status, and available features",
        schema(json!({}), vec![]),
        Action::Read,
        cp.clone(),
    )));

    // 2. stoa_platform_health
    registry.register(Arc::new(ProxyTool::new(
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
        cp.clone(),
    )));

    // 3. stoa_tools
    registry.register(Arc::new(ProxyTool::new(
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
        cp.clone(),
    )));

    // 4. stoa_tenants
    registry.register(Arc::new(ProxyTool::new(
        "stoa_tenants",
        "List accessible tenants (admin only)",
        schema(
            json!({
                "include_inactive": {"type": "boolean", "default": false}
            }),
            vec![],
        ),
        Action::Read,
        cp.clone(),
    )));

    // 5. stoa_catalog
    registry.register(Arc::new(ProxyTool::new(
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
        cp.clone(),
    )));

    // 6. stoa_api_spec
    registry.register(Arc::new(ProxyTool::new(
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
        cp.clone(),
    )));

    // 7. stoa_subscription
    registry.register(Arc::new(ProxyTool::new(
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
        cp.clone(),
    )));

    // 8. stoa_metrics
    registry.register(Arc::new(ProxyTool::new(
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
        cp.clone(),
    )));

    // 9. stoa_logs
    registry.register(Arc::new(ProxyTool::new(
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
        cp.clone(),
    )));

    // 10. stoa_alerts
    registry.register(Arc::new(ProxyTool::new(
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
        cp.clone(),
    )));

    // 11. stoa_uac
    registry.register(Arc::new(ProxyTool::new(
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
        cp.clone(),
    )));

    // 12. stoa_security
    registry.register(Arc::new(ProxyTool::new(
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
        cp.clone(),
    )));

    tracing::info!(
        tool_count = registry.count(),
        "Static STOA tools registered (LEGACY: proxy mode)"
    );
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::control_plane::tool_proxy::{RemoteToolDef, RemoteToolSchema};
    use crate::mcp::tools::ToolRegistry;
    use std::sync::Arc;

    // ─── infer_action ──────────────────────────────────────────

    #[test]
    fn infer_action_security() {
        assert_eq!(infer_action("stoa_security"), Action::ViewAudit);
        assert_eq!(infer_action("audit_log"), Action::ViewAudit);
    }

    #[test]
    fn infer_action_logs() {
        assert_eq!(infer_action("stoa_logs"), Action::ViewLogs);
    }

    #[test]
    fn infer_action_metrics() {
        assert_eq!(infer_action("stoa_metrics"), Action::ViewMetrics);
    }

    #[test]
    fn infer_action_create() {
        assert_eq!(infer_action("create_api"), Action::Create);
    }

    #[test]
    fn infer_action_update() {
        assert_eq!(infer_action("update_policy"), Action::Update);
    }

    #[test]
    fn infer_action_delete() {
        assert_eq!(infer_action("delete_subscription"), Action::Delete);
    }

    #[test]
    fn infer_action_default_read() {
        assert_eq!(infer_action("stoa_catalog"), Action::Read);
        assert_eq!(infer_action("unknown_tool"), Action::Read);
    }

    // ─── register_remote_tool ──────────────────────────────────

    fn make_remote_def(name: &str) -> RemoteToolDef {
        RemoteToolDef {
            name: name.to_string(),
            description: format!("Remote {}", name),
            input_schema: RemoteToolSchema {
                schema_type: "object".to_string(),
                properties: Default::default(),
                required: vec![],
            },
        }
    }

    #[test]
    fn register_remote_tool_skips_native() {
        let registry = ToolRegistry::new();
        let cp = Arc::new(crate::control_plane::ToolProxyClient::new(
            "http://localhost:8000",
            None,
        ));
        let def = make_remote_def("stoa_catalog"); // native tool
        register_remote_tool(&registry, &def, &cp);
        assert_eq!(registry.count(), 0); // should NOT register
    }

    #[test]
    fn register_remote_tool_registers_non_native() {
        let registry = ToolRegistry::new();
        let cp = Arc::new(crate::control_plane::ToolProxyClient::new(
            "http://localhost:8000",
            None,
        ));
        let def = make_remote_def("custom_weather_api");
        register_remote_tool(&registry, &def, &cp);
        assert_eq!(registry.count(), 1);
        assert!(registry.get("custom_weather_api").is_some());
    }

    #[test]
    fn register_remote_tool_copies_schema() {
        let registry = ToolRegistry::new();
        let cp = Arc::new(crate::control_plane::ToolProxyClient::new(
            "http://localhost:8000",
            None,
        ));
        let mut def = make_remote_def("my_tool");
        def.input_schema.required = vec!["action".to_string()];
        register_remote_tool(&registry, &def, &cp);

        let tool = registry.get("my_tool").unwrap();
        let schema = tool.input_schema();
        assert_eq!(schema.required, vec!["action".to_string()]);
    }

    // ─── register_generated_tool (CAB-606) ─────────────────────

    fn make_generated_def(name: &str) -> GeneratedToolDef {
        GeneratedToolDef {
            tool_name: name.to_string(),
            description: Some(format!("Generated: {}", name)),
            input_schema: Some(serde_json::json!({
                "type": "object",
                "properties": {
                    "id": {"type": "string"}
                },
                "required": ["id"]
            })),
            output_schema: None,
            backend_url: Some("https://api.example.com".to_string()),
            http_method: Some("POST".to_string()),
            path_pattern: Some("/v1/invoices".to_string()),
            version: "1.0.0".to_string(),
            enabled: true,
        }
    }

    #[test]
    fn register_generated_tool_creates_proxy() {
        let registry = ToolRegistry::new();
        let cp = Arc::new(crate::control_plane::ToolProxyClient::new(
            "http://localhost:8000",
            None,
        ));
        let def = make_generated_def("billing:create_invoice");
        register_generated_tool(&registry, &def, &cp);

        assert_eq!(registry.count(), 1);
        let tool = registry.get("billing:create_invoice").unwrap();
        assert_eq!(tool.name(), "billing:create_invoice");
        assert_eq!(tool.required_action(), Action::Create); // inferred from "create"
    }

    #[test]
    fn register_generated_tool_with_no_schema() {
        let registry = ToolRegistry::new();
        let cp = Arc::new(crate::control_plane::ToolProxyClient::new(
            "http://localhost:8000",
            None,
        ));
        let def = GeneratedToolDef {
            tool_name: "simple_tool".to_string(),
            description: None,
            input_schema: None,
            output_schema: None,
            backend_url: None,
            http_method: None,
            path_pattern: None,
            version: "1.0.0".to_string(),
            enabled: true,
        };
        register_generated_tool(&registry, &def, &cp);

        assert_eq!(registry.count(), 1);
        let tool = registry.get("simple_tool").unwrap();
        let schema = tool.input_schema();
        assert!(schema.properties.is_empty());
        assert!(schema.required.is_empty());
    }

    #[test]
    fn register_generated_tool_preserves_schema() {
        let registry = ToolRegistry::new();
        let cp = Arc::new(crate::control_plane::ToolProxyClient::new(
            "http://localhost:8000",
            None,
        ));
        let def = make_generated_def("billing:create_invoice");
        register_generated_tool(&registry, &def, &cp);

        let tool = registry.get("billing:create_invoice").unwrap();
        let schema = tool.input_schema();
        assert!(schema.properties.contains_key("id"));
        assert_eq!(schema.required, vec!["id".to_string()]);
    }
}
