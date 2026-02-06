//! K8s CRD Watcher
//!
//! Watches Tool and ToolSet CRDs and dynamically registers/unregisters tools.
//!
//! Requires: `k8s` feature flag

#![cfg(feature = "k8s")]

use std::sync::Arc;

use futures::StreamExt;
use kube::{
    api::Api,
    runtime::{watcher, watcher::Event},
    Client,
};
use tracing::{debug, error, info, warn};

use super::crds::{Tool, ToolSet};
use crate::mcp::tools::ToolRegistry;

/// CRD Watcher for dynamic tool registration
pub struct CrdWatcher {
    client: Client,
    tool_registry: Arc<ToolRegistry>,
}

impl CrdWatcher {
    /// Create a new CRD watcher
    pub fn new(client: Client, tool_registry: Arc<ToolRegistry>) -> Self {
        Self {
            client,
            tool_registry,
        }
    }

    /// Start watching CRDs (runs forever in background)
    pub async fn start(self) {
        info!("Starting K8s CRD watcher");

        // Watch Tool CRDs across all namespaces
        let tools: Api<Tool> = Api::all(self.client.clone());
        let tool_watcher = watcher(tools, watcher::Config::default());

        // Watch ToolSet CRDs
        let toolsets: Api<ToolSet> = Api::all(self.client.clone());
        let toolset_watcher = watcher(toolsets, watcher::Config::default());

        // Process events concurrently
        tokio::select! {
            result = self.watch_tools(tool_watcher) => {
                if let Err(e) = result {
                    error!(error = %e, "Tool watcher failed");
                }
            }
            result = self.watch_toolsets(toolset_watcher) => {
                if let Err(e) = result {
                    error!(error = %e, "ToolSet watcher failed");
                }
            }
        }
    }

    /// Watch Tool CRD events
    async fn watch_tools(
        &self,
        watcher: impl futures::Stream<Item = Result<Event<Tool>, watcher::Error>>,
    ) -> Result<(), watcher::Error> {
        tokio::pin!(watcher);

        while let Some(event) = watcher.next().await {
            match event {
                Ok(Event::Apply(tool)) => {
                    self.handle_tool_apply(&tool).await;
                }
                Ok(Event::Delete(tool)) => {
                    self.handle_tool_delete(&tool);
                }
                Ok(Event::Init) => {
                    debug!("Tool watcher initialized");
                }
                Ok(Event::InitApply(tool)) => {
                    self.handle_tool_apply(&tool).await;
                }
                Ok(Event::InitDone) => {
                    info!("Tool watcher initial sync complete");
                }
                Err(e) => {
                    warn!(error = %e, "Tool watcher error");
                }
            }
        }

        Ok(())
    }

    /// Watch ToolSet CRD events
    async fn watch_toolsets(
        &self,
        watcher: impl futures::Stream<Item = Result<Event<ToolSet>, watcher::Error>>,
    ) -> Result<(), watcher::Error> {
        tokio::pin!(watcher);

        while let Some(event) = watcher.next().await {
            match event {
                Ok(Event::Apply(toolset)) => {
                    self.handle_toolset_apply(&toolset).await;
                }
                Ok(Event::Delete(toolset)) => {
                    self.handle_toolset_delete(&toolset);
                }
                Ok(Event::Init) => {
                    debug!("ToolSet watcher initialized");
                }
                Ok(Event::InitApply(toolset)) => {
                    self.handle_toolset_apply(&toolset).await;
                }
                Ok(Event::InitDone) => {
                    info!("ToolSet watcher initial sync complete");
                }
                Err(e) => {
                    warn!(error = %e, "ToolSet watcher error");
                }
            }
        }

        Ok(())
    }

    /// Handle Tool CRD apply (create/update)
    async fn handle_tool_apply(&self, tool: &Tool) {
        let namespace = tool.metadata.namespace.as_deref().unwrap_or("default");
        let name = tool.metadata.name.as_deref().unwrap_or("unknown");

        // Generate tool name: {namespace}_{name}
        let tool_name = format!("{}_{}", namespace, to_snake_case(name));

        info!(
            tool = %tool_name,
            tenant = %namespace,
            endpoint = %tool.spec.endpoint,
            "Registering tool from CRD"
        );

        // TODO: Create actual tool implementation (NativeTool or ProxyTool)
        // For now, just log the registration
        // The actual implementation would:
        // 1. Create a DynamicTool that calls the endpoint
        // 2. Register it with the tool registry
        // 3. Apply rate limiting if specified
        // 4. Apply annotations

        debug!(
            tool = %tool_name,
            display_name = %tool.spec.display_name,
            method = %tool.spec.method,
            "Tool CRD processed"
        );
    }

    /// Handle Tool CRD delete
    fn handle_tool_delete(&self, tool: &Tool) {
        let namespace = tool.metadata.namespace.as_deref().unwrap_or("default");
        let name = tool.metadata.name.as_deref().unwrap_or("unknown");

        let tool_name = format!("{}_{}", namespace, to_snake_case(name));

        info!(
            tool = %tool_name,
            tenant = %namespace,
            "Unregistering tool (CRD deleted)"
        );

        if self.tool_registry.unregister(&tool_name) {
            info!(tool = %tool_name, "Tool unregistered successfully");
        } else {
            debug!(tool = %tool_name, "Tool was not registered");
        }
    }

    /// Handle ToolSet CRD apply
    async fn handle_toolset_apply(&self, toolset: &ToolSet) {
        let namespace = toolset.metadata.namespace.as_deref().unwrap_or("default");
        let name = toolset.metadata.name.as_deref().unwrap_or("unknown");

        info!(
            toolset = %name,
            tenant = %namespace,
            upstream = %toolset.spec.upstream.url,
            "Processing ToolSet CRD"
        );

        // TODO: Connect to upstream MCP server and discover tools
        // This will be implemented in the federation module
        // For now, just log the event

        debug!(
            toolset = %name,
            transport = %toolset.spec.upstream.transport,
            tools_filter = ?toolset.spec.tools,
            "ToolSet CRD processed"
        );
    }

    /// Handle ToolSet CRD delete
    fn handle_toolset_delete(&self, toolset: &ToolSet) {
        let namespace = toolset.metadata.namespace.as_deref().unwrap_or("default");
        let name = toolset.metadata.name.as_deref().unwrap_or("unknown");

        info!(
            toolset = %name,
            tenant = %namespace,
            "Removing ToolSet tools (CRD deleted)"
        );

        // TODO: Unregister all tools from this toolset
        // Would need to track which tools came from which toolset
    }
}

/// Convert a string to snake_case
fn to_snake_case(s: &str) -> String {
    let mut result = String::new();
    for (i, c) in s.chars().enumerate() {
        if c.is_uppercase() {
            if i > 0 {
                result.push('_');
            }
            result.push(c.to_lowercase().next().unwrap());
        } else if c == '-' {
            result.push('_');
        } else {
            result.push(c);
        }
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_to_snake_case() {
        assert_eq!(to_snake_case("WeatherAPI"), "weather_a_p_i");
        assert_eq!(to_snake_case("weather-api"), "weather_api");
        assert_eq!(to_snake_case("weatherApi"), "weather_api");
        assert_eq!(to_snake_case("simple"), "simple");
    }
}
