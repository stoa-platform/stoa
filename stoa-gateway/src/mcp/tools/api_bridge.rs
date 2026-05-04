//! API-to-Tool Bridge
//!
//! Discovers published APIs from the Control Plane catalog and registers
//! each one as a DynamicTool in the MCP tool registry.
//!
//! This enables Demo Act 7: "Legacy API → AI Agent" — every published API
//! becomes an MCP tool that AI agents can discover and invoke via
//! GET /mcp/v1/tools and POST /mcp/v1/tools/invoke.

use reqwest::Client;
use serde::Deserialize;
use serde_json::Value;
use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;
use tracing::{debug, info};
use uuid::Uuid;

use super::dynamic_tool::DynamicTool;
use super::{ToolAnnotations, ToolRegistry, ToolSchema};
use crate::config::ExpansionMode;
use crate::uac::Action;

/// Refresh interval for API tool discovery
const API_TOOL_REFRESH_INTERVAL: Duration = Duration::from_secs(60);

/// API representation from CP internal catalog endpoint
#[derive(Debug, Deserialize)]
struct CatalogApi {
    /// API slug (e.g., "payments", "petstore")
    id: String,
    /// Display name
    name: String,
    #[serde(default)]
    description: Option<String>,
    #[serde(default)]
    backend_url: Option<String>,
    #[serde(default)]
    version: Option<String>,
}

#[derive(Debug, Deserialize)]
struct CatalogApisResponse {
    #[serde(default)]
    apis: Vec<CatalogApi>,
}

/// Per-operation tool descriptor from `/v1/internal/catalog/apis/expanded`
/// (CAB-2113 Phase 0). Matches the `ExpandedTool` dataclass emitted by
/// `control-plane-api/src/services/mcp_tool_expander.py`.
#[derive(Debug, Deserialize)]
struct ExpandedTool {
    name: String,
    #[serde(default)]
    description: String,
    #[serde(default)]
    input_schema: Option<Value>,
    backend_url: String,
    #[serde(default = "default_http_method")]
    http_method: String,
    tenant_id: String,
    #[serde(default)]
    path_pattern: Option<String>,
}

fn default_http_method() -> String {
    "POST".to_string()
}

#[derive(Debug, Deserialize)]
struct ExpandedToolsResponse {
    #[serde(default)]
    tools: Vec<ExpandedTool>,
}

/// Discover published APIs from the CP catalog and register as MCP tools.
///
/// Each API becomes a public DynamicTool that proxies HTTP POST calls
/// to its backend_url. Tools are named after the API slug (e.g. "payments").
///
/// When `gateway_id` is provided, only APIs assigned to this gateway are returned.
/// An empty scoped result is authoritative: the gateway has no assigned APIs.
///
/// Returns the number of API tools registered.
pub async fn discover_api_tools(
    registry: &ToolRegistry,
    cp_base_url: &str,
    client: &Client,
    gateway_id: Option<Uuid>,
) -> Result<usize, String> {
    let catalog = fetch_catalog(cp_base_url, client, gateway_id).await?;

    let mut count = 0;
    for api in &catalog.apis {
        let backend_url = match &api.backend_url {
            Some(url) if !url.is_empty() => url.clone(),
            _ => {
                debug!(api = %api.id, "Skipping API without backend_url");
                continue;
            }
        };

        // Use API slug (id) as tool name (e.g., "payments", not "Payments API")
        let tool_name = &api.id;

        // Skip if already registered (native tools take precedence)
        if registry.get(tool_name).is_some() {
            debug!(api = %tool_name, "API tool already registered, skipping");
            continue;
        }

        let description = api
            .description
            .as_deref()
            .unwrap_or("API tool (auto-discovered from catalog)");

        let version_note = api
            .version
            .as_deref()
            .map(|v| format!(" (v{})", v))
            .unwrap_or_default();

        // Build a generic input schema: accepts any JSON arguments
        let mut properties = HashMap::new();
        properties.insert(
            "action".to_string(),
            serde_json::json!({
                "type": "string",
                "description": "API action to perform (e.g. get-status, list, create)"
            }),
        );
        properties.insert(
            "params".to_string(),
            serde_json::json!({
                "type": "object",
                "description": "Additional parameters for the API call"
            }),
        );

        let schema = ToolSchema {
            schema_type: "object".to_string(),
            properties,
            required: vec![],
        };

        let tool = DynamicTool::new(
            tool_name,
            format!("{}{}", description, version_note),
            &backend_url,
            "POST",
            schema,
            "default", // tenant_id unused for public tools
        )
        .with_action(Action::Read)
        .with_annotations(ToolAnnotations {
            title: Some(api.name.clone()),
            open_world_hint: Some(true),
            ..Default::default()
        })
        .into_public();

        registry.register(Arc::new(tool));
        count += 1;
        info!(api = %tool_name, backend = %backend_url, "Registered API as MCP tool");
    }

    Ok(count)
}

/// CAB-2113 Phase 0: discover per-operation MCP tools from the CP expansion endpoint.
///
/// Fetches `/v1/internal/catalog/apis/expanded` (introduced in PR #2415) which
/// returns one `ExpandedTool` per OpenAPI operation. Each tool is registered
/// with its pre-built input schema and path pattern; `DynamicTool` handles
/// path-param substitution + query/body routing at invocation time.
///
/// Returns transport and parse errors to the caller; the background refresh
/// task retries while keeping the existing registry state.
pub async fn discover_expanded_api_tools(
    registry: &ToolRegistry,
    cp_base_url: &str,
    client: &Client,
    gateway_id: Option<Uuid>,
) -> Result<usize, String> {
    let catalog = fetch_expanded_catalog(cp_base_url, client, gateway_id).await?;

    let mut count = 0;
    for tool in catalog.tools {
        if tool.backend_url.is_empty() {
            debug!(tool = %tool.name, "Skipping expanded tool without backend_url");
            continue;
        }
        if registry.get(&tool.name).is_some() {
            debug!(tool = %tool.name, "Expanded tool already registered, skipping");
            continue;
        }

        let schema = tool
            .input_schema
            .as_ref()
            .map(super::dynamic_tool::schema_from_value)
            .unwrap_or_else(|| ToolSchema {
                schema_type: "object".to_string(),
                properties: HashMap::new(),
                required: vec![],
            });

        let mut dyn_tool = DynamicTool::new(
            &tool.name,
            tool.description.clone(),
            &tool.backend_url,
            &tool.http_method,
            schema,
            &tool.tenant_id,
        )
        .with_action(Action::Read)
        .with_annotations(ToolAnnotations {
            title: Some(tool.name.clone()),
            open_world_hint: Some(true),
            ..Default::default()
        })
        .into_public();

        if let Some(pattern) = tool.path_pattern {
            if !pattern.is_empty() {
                dyn_tool = dyn_tool.with_path_pattern(pattern);
            }
        }

        registry.register(Arc::new(dyn_tool));
        count += 1;
        info!(tool = %tool.name, backend = %tool.backend_url, method = %tool.http_method, "Registered expanded tool");
    }

    Ok(count)
}

async fn fetch_expanded_catalog(
    cp_base_url: &str,
    client: &Client,
    gateway_id: Option<Uuid>,
) -> Result<ExpandedToolsResponse, String> {
    let mut url = format!(
        "{}/v1/internal/catalog/apis/expanded",
        cp_base_url.trim_end_matches('/')
    );
    if let Some(gw_id) = gateway_id {
        url.push_str(&format!("?gateway_id={gw_id}"));
    }

    debug!(url = %url, "Discovering expanded tools from CP");

    let resp = client
        .get(&url)
        .timeout(Duration::from_secs(10))
        .send()
        .await
        .map_err(|e| format!("CP expanded catalog request failed: {e}"))?;

    if !resp.status().is_success() {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        return Err(format!("CP expanded catalog returned {status}: {body}"));
    }

    resp.json()
        .await
        .map_err(|e| format!("Failed to parse CP expanded catalog response: {e}"))
}

/// Fetch the API catalog from the Control Plane.
///
/// When `gateway_id` is `Some`, appends `?gateway_id={id}` to scope results
/// to APIs assigned to this gateway (CAB-1940 Phase 2 server-side filter).
async fn fetch_catalog(
    cp_base_url: &str,
    client: &Client,
    gateway_id: Option<Uuid>,
) -> Result<CatalogApisResponse, String> {
    let mut url = format!(
        "{}/v1/internal/catalog/apis",
        cp_base_url.trim_end_matches('/')
    );
    if let Some(gw_id) = gateway_id {
        url.push_str(&format!("?gateway_id={gw_id}"));
    }

    debug!(url = %url, "Discovering API tools from CP internal catalog");

    let resp = client
        .get(&url)
        .timeout(Duration::from_secs(10))
        .send()
        .await
        .map_err(|e| format!("CP catalog request failed: {e}"))?;

    if !resp.status().is_success() {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        return Err(format!("CP catalog returned {status}: {body}"));
    }

    resp.json()
        .await
        .map_err(|e| format!("Failed to parse CP catalog response: {e}"))
}

/// Start a background task that periodically refreshes API tools from the CP catalog.
///
/// When `registrar` is provided, reads the gateway's assigned ID on each tick
/// so the catalog fetch is scoped to this gateway's assigned APIs (CAB-1940).
///
/// `mode` selects between coarse (`/apis`, one tool per API) and per-op
/// (`/apis/expanded`, one tool per OpenAPI operation) discovery (CAB-2113).
pub fn start_api_tool_refresh_task(
    registry: Arc<ToolRegistry>,
    cp_base_url: String,
    client: Client,
    registrar: Option<Arc<crate::control_plane::registration::GatewayRegistrar>>,
    mode: ExpansionMode,
) {
    tokio::spawn(async move {
        loop {
            tokio::time::sleep(API_TOOL_REFRESH_INTERVAL).await;

            let gw_id = match &registrar {
                Some(r) => match r.gateway_id().await {
                    Some(id) => Some(id),
                    None => {
                        debug!("Skipping API tool refresh until gateway registration completes");
                        continue;
                    }
                },
                None => None,
            };

            let result = match mode {
                ExpansionMode::Coarse => {
                    discover_api_tools(&registry, &cp_base_url, &client, gw_id).await
                }
                ExpansionMode::PerOp => {
                    discover_expanded_api_tools(&registry, &cp_base_url, &client, gw_id).await
                }
            };

            let mode_label = expansion_mode_label(mode);
            match result {
                Ok(count) => {
                    crate::metrics::TOOL_EXPANSION_REFRESH_TOTAL
                        .with_label_values(&[mode_label, "ok"])
                        .inc();
                    crate::metrics::TOOL_EXPANSION_OPS_REGISTERED
                        .with_label_values(&[mode_label])
                        .set(count as f64);
                    if count > 0 {
                        info!(count, mode = ?mode, "New API tools discovered from catalog");
                    }
                }
                Err(e) => {
                    crate::metrics::TOOL_EXPANSION_REFRESH_TOTAL
                        .with_label_values(&[mode_label, "err"])
                        .inc();
                    crate::metrics::TOOL_EXPANSION_ERRORS_TOTAL
                        .with_label_values(&[classify_refresh_error(&e)])
                        .inc();
                    debug!(error = %e, mode = ?mode, "API tool refresh failed (keeping existing tools)");
                }
            }
        }
    });
}

/// Stable Prometheus label for an `ExpansionMode`. Kept as a free fn so tests
/// can assert the label surface without touching the metric registry.
fn expansion_mode_label(mode: ExpansionMode) -> &'static str {
    match mode {
        ExpansionMode::Coarse => "coarse",
        ExpansionMode::PerOp => "per-op",
    }
}

/// Coarse categorisation of refresh error strings for the
/// `stoa_gateway_tool_expansion_errors_total{reason=...}` counter. The matching
/// order matters: parse errors come from `resp.json()` after a successful HTTP
/// status, so they must be checked before the generic transport bucket.
fn classify_refresh_error(err: &str) -> &'static str {
    if err.contains("Failed to parse") {
        "parse"
    } else if err.contains("returned") {
        "upstream_status"
    } else {
        "transport"
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use wiremock::matchers::{method, path, query_param};
    use wiremock::{Mock, MockServer, ResponseTemplate};

    #[tokio::test]
    async fn discovers_apis_with_backend_url() {
        let mock = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/v1/internal/catalog/apis"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "apis": [{
                    "id": "payments",
                    "name": "Payments API",
                    "description": "Handle payments",
                    "backend_url": "http://backend:8080",
                    "version": "1.2"
                }]
            })))
            .mount(&mock)
            .await;

        let registry = ToolRegistry::new();
        let client = Client::new();
        let count = discover_api_tools(&registry, &mock.uri(), &client, None)
            .await
            .unwrap();

        assert_eq!(count, 1);
        let tool = registry.get("payments").unwrap();
        assert!(tool.description().contains("Handle payments"));
        assert!(tool.description().contains("(v1.2)"));
    }

    #[tokio::test]
    async fn skips_apis_without_backend_url() {
        let mock = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/v1/internal/catalog/apis"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "apis": [{"id": "no-backend", "name": "No Backend"}]
            })))
            .mount(&mock)
            .await;

        let registry = ToolRegistry::new();
        let client = Client::new();
        let count = discover_api_tools(&registry, &mock.uri(), &client, None)
            .await
            .unwrap();
        assert_eq!(count, 0);
        assert!(registry.get("no-backend").is_none());
    }

    #[tokio::test]
    async fn skips_already_registered_tools() {
        let mock = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/v1/internal/catalog/apis"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "apis": [{"id": "existing", "name": "Existing", "backend_url": "http://backend:8080"}]
            })))
            .mount(&mock).await;

        let registry = ToolRegistry::new();
        let pre = DynamicTool::new(
            "existing",
            "pre-registered",
            "http://x",
            "GET",
            ToolSchema {
                schema_type: "object".to_string(),
                properties: Default::default(),
                required: vec![],
            },
            "t1",
        );
        registry.register(Arc::new(pre));

        let client = Client::new();
        let count = discover_api_tools(&registry, &mock.uri(), &client, None)
            .await
            .unwrap();
        assert_eq!(count, 0);
        assert_eq!(
            registry.get("existing").unwrap().description(),
            "pre-registered"
        );
    }

    #[tokio::test]
    async fn handles_empty_catalog() {
        let mock = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/v1/internal/catalog/apis"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({"apis": []})))
            .mount(&mock)
            .await;

        let registry = ToolRegistry::new();
        let client = Client::new();
        let count = discover_api_tools(&registry, &mock.uri(), &client, None)
            .await
            .unwrap();
        assert_eq!(count, 0);
    }

    #[tokio::test]
    async fn api_without_version_has_no_suffix() {
        let mock = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/v1/internal/catalog/apis"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "apis": [{"id": "simple", "name": "Simple API", "description": "Simple", "backend_url": "http://b:80"}]
            })))
            .mount(&mock).await;

        let registry = ToolRegistry::new();
        let client = Client::new();
        discover_api_tools(&registry, &mock.uri(), &client, None)
            .await
            .unwrap();

        let tool = registry.get("simple").unwrap();
        assert_eq!(tool.description(), "Simple");
        assert!(!tool.description().contains("(v"));
    }

    #[tokio::test]
    async fn http_error_returns_err() {
        let mock = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/v1/internal/catalog/apis"))
            .respond_with(ResponseTemplate::new(500).set_body_string("internal error"))
            .mount(&mock)
            .await;

        let registry = ToolRegistry::new();
        let client = Client::new();
        let result = discover_api_tools(&registry, &mock.uri(), &client, None).await;
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("500"));
    }

    #[tokio::test]
    async fn invalid_json_returns_err() {
        let mock = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/v1/internal/catalog/apis"))
            .respond_with(ResponseTemplate::new(200).set_body_string("not json"))
            .mount(&mock)
            .await;

        let registry = ToolRegistry::new();
        let client = Client::new();
        let result = discover_api_tools(&registry, &mock.uri(), &client, None).await;
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("parse"));
    }

    /// Regression test for CAB-1940: sidecar mode should NOT discover API tools.
    /// The gate is in main.rs (not called for non-EdgeMcp modes), so here we verify
    /// that the tool registry stays empty when discover_api_tools is simply not called.
    #[tokio::test]
    async fn regression_cab_1940_sidecar_has_no_catalog_tools() {
        // Sidecar mode: discover_api_tools is never called (gated in main.rs).
        // Verify the registry is empty by default — no implicit population.
        let registry = ToolRegistry::new();
        assert_eq!(registry.count(), 0, "Sidecar must not have catalog tools");
    }

    /// CAB-1940 Phase 3: gateway_id is sent as query param to scope API discovery.
    #[tokio::test]
    async fn regression_cab_1940_gateway_id_sent_as_query_param() {
        let gw_id = Uuid::new_v4();
        let mock = MockServer::start().await;

        // Only respond when gateway_id query param is present
        Mock::given(method("GET"))
            .and(path("/v1/internal/catalog/apis"))
            .and(query_param("gateway_id", gw_id.to_string()))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "apis": [{"id": "scoped", "name": "Scoped API", "backend_url": "http://b:80"}]
            })))
            .mount(&mock)
            .await;

        let registry = ToolRegistry::new();
        let client = Client::new();
        let count = discover_api_tools(&registry, &mock.uri(), &client, Some(gw_id))
            .await
            .unwrap();

        assert_eq!(count, 1);
        assert!(registry.get("scoped").is_some());
    }

    /// Regression: a scoped empty catalog means this gateway has no assigned APIs.
    /// It must not fall back to the global catalog, otherwise Console shows
    /// unrelated APIs as discovered for gateways with zero deployments.
    #[tokio::test]
    async fn regression_cab_1940_scoped_empty_does_not_fallback() {
        let gw_id = Uuid::new_v4();
        let mock = MockServer::start().await;

        // Filtered request returns empty
        Mock::given(method("GET"))
            .and(path("/v1/internal/catalog/apis"))
            .and(query_param("gateway_id", gw_id.to_string()))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({"apis": []})))
            .expect(1)
            .mount(&mock)
            .await;

        let registry = ToolRegistry::new();
        let client = Client::new();
        let count = discover_api_tools(&registry, &mock.uri(), &client, Some(gw_id))
            .await
            .unwrap();

        assert_eq!(count, 0, "Scoped empty catalog must remain empty");
        assert_eq!(registry.count(), 0);
    }

    /// CAB-1940 Phase 3: no fallback when gateway_id is None (unfiltered is the only call).
    #[tokio::test]
    async fn no_fallback_when_no_gateway_id() {
        let mock = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/v1/internal/catalog/apis"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({"apis": []})))
            .expect(1) // Only one request (no retry)
            .mount(&mock)
            .await;

        let registry = ToolRegistry::new();
        let client = Client::new();
        let count = discover_api_tools(&registry, &mock.uri(), &client, None)
            .await
            .unwrap();
        assert_eq!(count, 0);
    }

    // === CAB-2113 Phase 0: per-operation expansion ===

    fn expanded_tool_json(
        name: &str,
        backend: &str,
        method: &str,
        path_pattern: Option<&str>,
    ) -> serde_json::Value {
        let mut obj = serde_json::json!({
            "name": name,
            "description": format!("op {}", name),
            "input_schema": {"type": "object", "properties": {}, "required": []},
            "backend_url": backend,
            "http_method": method,
            "tenant_id": "demo",
        });
        if let Some(p) = path_pattern {
            obj["path_pattern"] = serde_json::Value::String(p.to_string());
        }
        obj
    }

    #[tokio::test]
    async fn cab_2113_discovers_expanded_tools() {
        let mock = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/v1/internal/catalog/apis/expanded"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "tools": [
                    expanded_tool_json("demo:bank:get-customer", "http://bank:8080", "GET", Some("/customers/{id}")),
                    expanded_tool_json("demo:bank:list-accounts", "http://bank:8080", "GET", Some("/accounts")),
                ]
            })))
            .mount(&mock)
            .await;

        let registry = ToolRegistry::new();
        let client = Client::new();
        let count = discover_expanded_api_tools(&registry, &mock.uri(), &client, None)
            .await
            .unwrap();

        assert_eq!(count, 2);
        assert!(registry.get("demo:bank:get-customer").is_some());
        assert!(registry.get("demo:bank:list-accounts").is_some());
    }

    #[tokio::test]
    async fn cab_2113_expanded_tools_are_idempotent() {
        let mock = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/v1/internal/catalog/apis/expanded"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "tools": [expanded_tool_json("demo:bank:op", "http://bank:8080", "POST", None)]
            })))
            .mount(&mock)
            .await;

        let registry = ToolRegistry::new();
        let client = Client::new();
        let first = discover_expanded_api_tools(&registry, &mock.uri(), &client, None)
            .await
            .unwrap();
        let second = discover_expanded_api_tools(&registry, &mock.uri(), &client, None)
            .await
            .unwrap();

        assert_eq!(first, 1);
        assert_eq!(second, 0, "second pass must not double-register");
    }

    #[tokio::test]
    async fn cab_2113_skips_tool_without_backend_url() {
        let mock = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/v1/internal/catalog/apis/expanded"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "tools": [expanded_tool_json("demo:bank:broken", "", "POST", None)]
            })))
            .mount(&mock)
            .await;

        let registry = ToolRegistry::new();
        let client = Client::new();
        let count = discover_expanded_api_tools(&registry, &mock.uri(), &client, None)
            .await
            .unwrap();
        assert_eq!(count, 0);
    }

    #[tokio::test]
    async fn cab_2113_gateway_id_scope_empty_does_not_fallback() {
        let gw_id = Uuid::new_v4();
        let mock = MockServer::start().await;

        // Filtered request: empty
        Mock::given(method("GET"))
            .and(path("/v1/internal/catalog/apis/expanded"))
            .and(query_param("gateway_id", gw_id.to_string()))
            .respond_with(
                ResponseTemplate::new(200).set_body_json(serde_json::json!({"tools": []})),
            )
            .expect(1)
            .mount(&mock)
            .await;

        let registry = ToolRegistry::new();
        let client = Client::new();
        let count = discover_expanded_api_tools(&registry, &mock.uri(), &client, Some(gw_id))
            .await
            .unwrap();

        assert_eq!(count, 0, "Scoped empty expanded catalog must remain empty");
        assert_eq!(registry.count(), 0);
    }

    #[tokio::test]
    async fn cab_2113_fifty_operation_scalability() {
        // Challenger callout: verify expander round-trip holds at 50 ops,
        // matching the mcp_tool_expander test on the CP side.
        let tools: Vec<_> = (0..50)
            .map(|i| {
                expanded_tool_json(
                    &format!("demo:bank:op{i}"),
                    "http://bank:8080",
                    "GET",
                    Some(&format!("/ops/{{id}}#{i}")),
                )
            })
            .collect();

        let mock = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/v1/internal/catalog/apis/expanded"))
            .respond_with(
                ResponseTemplate::new(200).set_body_json(serde_json::json!({"tools": tools})),
            )
            .mount(&mock)
            .await;

        let registry = ToolRegistry::new();
        let client = Client::new();
        let count = discover_expanded_api_tools(&registry, &mock.uri(), &client, None)
            .await
            .unwrap();
        assert_eq!(count, 50);
        assert!(registry.get("demo:bank:op0").is_some());
        assert!(registry.get("demo:bank:op49").is_some());
    }

    #[tokio::test]
    async fn cab_2113_expanded_http_error_returns_err() {
        let mock = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/v1/internal/catalog/apis/expanded"))
            .respond_with(ResponseTemplate::new(500).set_body_string("boom"))
            .mount(&mock)
            .await;

        let registry = ToolRegistry::new();
        let client = Client::new();
        let err = discover_expanded_api_tools(&registry, &mock.uri(), &client, None)
            .await
            .unwrap_err();
        assert!(err.contains("500"), "got: {err}");
    }

    #[test]
    fn expansion_mode_label_is_kebab_canonical() {
        assert_eq!(expansion_mode_label(ExpansionMode::Coarse), "coarse");
        assert_eq!(expansion_mode_label(ExpansionMode::PerOp), "per-op");
    }

    #[test]
    fn classify_refresh_error_buckets_parse_upstream_transport() {
        assert_eq!(
            classify_refresh_error("Failed to parse CP expanded catalog response: eof"),
            "parse"
        );
        assert_eq!(
            classify_refresh_error("CP expanded catalog returned 503: unavailable"),
            "upstream_status"
        );
        assert_eq!(
            classify_refresh_error("CP expanded catalog request failed: connection refused"),
            "transport"
        );
    }
}
