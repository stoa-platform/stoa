//! STOA Tool Registration — Dynamic + Static Fallback
//!
//! Tools are discovered from the Control Plane at startup and periodically
//! refreshed. No gateway rebuild needed when tools change on the CP side.
//!
//! Flow:
//!   1. Try `POST /mcp/tools/list` on Control Plane → dynamic registration
//!   2. If CP unreachable → use embedded static definitions (12 tools)
//!   3. Background task refreshes every 60s from CP

use serde_json::json;
use std::sync::Arc;
use std::time::Duration;

use super::proxy_tool::ProxyTool;
use super::{ToolRegistry, ToolSchema};
use crate::control_plane::{RemoteToolDef, ToolProxyClient};
use crate::uac::Action;

/// Default refresh interval for tool discovery
const TOOL_REFRESH_INTERVAL: Duration = Duration::from_secs(60);

/// Helper to build a ToolSchema from JSON properties
fn schema(props: serde_json::Value, required: Vec<&str>) -> ToolSchema {
    ToolSchema {
        schema_type: "object".into(),
        properties: serde_json::from_value(props).unwrap_or_default(),
        required: required.iter().map(|s| s.to_string()).collect(),
    }
}

/// Convert a remote tool definition into a ProxyTool and register it.
fn register_remote_tool(registry: &ToolRegistry, def: &RemoteToolDef, cp: &Arc<ToolProxyClient>) {
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

// ─── Dynamic Discovery ───────────────────────────────────────────

/// Try to discover and register tools from the Control Plane.
/// Returns the number of tools registered, or an error.
pub async fn discover_and_register(
    registry: &ToolRegistry,
    cp: &Arc<ToolProxyClient>,
) -> Result<usize, String> {
    let defs = cp.discover_tools().await?;
    let count = defs.len();

    for def in &defs {
        register_remote_tool(registry, def, cp);
    }

    tracing::info!(tool_count = count, "Registered tools from Control Plane");
    Ok(count)
}

/// Start a background task that periodically refreshes tools from CP.
pub fn start_tool_refresh_task(registry: Arc<ToolRegistry>, cp: Arc<ToolProxyClient>) {
    tokio::spawn(async move {
        loop {
            tokio::time::sleep(TOOL_REFRESH_INTERVAL).await;

            match cp.discover_tools().await {
                Ok(defs) => {
                    for def in &defs {
                        register_remote_tool(&registry, def, &cp);
                    }
                    tracing::debug!(
                        tool_count = defs.len(),
                        "Refreshed tools from Control Plane"
                    );
                }
                Err(e) => {
                    tracing::debug!(error = %e, "Tool refresh from CP failed (keeping existing tools)");
                }
            }
        }
    });
}

// ─── Static Fallback ─────────────────────────────────────────────

/// Register the 12 STOA tools with hardcoded schemas.
/// Used as fallback when the Control Plane is unreachable at startup.
pub fn register_static_tools(registry: &ToolRegistry, cp: Arc<ToolProxyClient>) {
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
        "Static STOA tools registered (fallback)"
    );
}
