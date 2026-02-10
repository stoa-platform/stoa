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
use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;
use tracing::{debug, info};

use super::dynamic_tool::DynamicTool;
use super::{ToolAnnotations, ToolRegistry, ToolSchema};
use crate::uac::Action;

/// Refresh interval for API tool discovery
const API_TOOL_REFRESH_INTERVAL: Duration = Duration::from_secs(60);

/// Minimal API representation from CP portal catalog
#[derive(Debug, Deserialize)]
struct PortalApi {
    name: String,
    #[serde(default)]
    description: Option<String>,
    #[serde(default)]
    backend_url: Option<String>,
    #[serde(default)]
    version: Option<String>,
}

#[derive(Debug, Deserialize)]
struct PortalApisResponse {
    #[serde(default)]
    apis: Vec<PortalApi>,
}

/// Discover published APIs from the CP catalog and register as MCP tools.
///
/// Each API becomes a public DynamicTool that proxies HTTP POST calls
/// to its backend_url. Tools are named after the API slug (e.g. "payments").
///
/// Returns the number of API tools registered.
pub async fn discover_api_tools(
    registry: &ToolRegistry,
    cp_base_url: &str,
    client: &Client,
) -> Result<usize, String> {
    let url = format!(
        "{}/v1/portal/apis?page_size=100",
        cp_base_url.trim_end_matches('/')
    );

    debug!(url = %url, "Discovering API tools from CP catalog");

    let resp = client
        .get(&url)
        .timeout(Duration::from_secs(10))
        .send()
        .await
        .map_err(|e| format!("CP catalog request failed: {}", e))?;

    if !resp.status().is_success() {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        return Err(format!("CP catalog returned {}: {}", status, body));
    }

    let catalog: PortalApisResponse = resp
        .json()
        .await
        .map_err(|e| format!("Failed to parse CP catalog response: {}", e))?;

    let mut count = 0;
    for api in &catalog.apis {
        let backend_url = match &api.backend_url {
            Some(url) if !url.is_empty() => url.clone(),
            _ => {
                debug!(api = %api.name, "Skipping API without backend_url");
                continue;
            }
        };

        // Skip if already registered (native tools take precedence)
        if registry.get(&api.name).is_some() {
            debug!(api = %api.name, "API tool already registered, skipping");
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
            &api.name,
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
        info!(api = %api.name, backend = %backend_url, "Registered API as MCP tool");
    }

    Ok(count)
}

/// Start a background task that periodically refreshes API tools from the CP catalog.
pub fn start_api_tool_refresh_task(
    registry: Arc<ToolRegistry>,
    cp_base_url: String,
    client: Client,
) {
    tokio::spawn(async move {
        loop {
            tokio::time::sleep(API_TOOL_REFRESH_INTERVAL).await;

            match discover_api_tools(&registry, &cp_base_url, &client).await {
                Ok(count) => {
                    if count > 0 {
                        info!(count, "New API tools discovered from catalog");
                    }
                }
                Err(e) => {
                    debug!(error = %e, "API tool refresh failed (keeping existing tools)");
                }
            }
        }
    });
}
