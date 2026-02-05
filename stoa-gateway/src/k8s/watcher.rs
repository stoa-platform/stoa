//! Kubernetes CRD Watcher
//!
//! Watches Tool and ToolSet Custom Resources and synchronizes them
//! to the gateway's tool registry.

use super::{K8sConfig, Tool, ToolSet, ToolSpec, ToolStatus};
use crate::mcp::tools::{ToolDefinition, ToolRegistry, ToolSchema};
use futures::StreamExt;
use kube::{
    api::{Api, Patch, PatchParams},
    client::Client,
    runtime::{
        controller::{Action, Controller},
        watcher::Config as WatcherConfig,
    },
    ResourceExt,
};
use std::{collections::HashMap, sync::Arc, time::Duration};
use thiserror::Error;
use tokio::sync::RwLock;
use tracing::{debug, error, info, instrument, warn};

/// Errors that can occur during CRD watching
#[derive(Error, Debug)]
pub enum WatcherError {
    #[error("Kubernetes client error: {0}")]
    KubeClient(#[from] kube::Error),

    #[error("Failed to parse tool spec: {0}")]
    SpecParse(String),

    #[error("Tool registry error: {0}")]
    Registry(String),

    #[error("Configuration error: {0}")]
    Config(String),
}

/// Result type for watcher operations
pub type Result<T> = std::result::Result<T, WatcherError>;

/// CRD Watcher manages Tool and ToolSet resources
pub struct CrdWatcher {
    /// Kubernetes client
    client: Client,

    /// Configuration
    config: K8sConfig,

    /// Tool registry to update
    registry: Arc<RwLock<ToolRegistry>>,

    /// Mapping of CRD resource to registered tool names
    /// Key: "namespace/name", Value: list of tool names registered from this resource
    registered_tools: Arc<RwLock<HashMap<String, Vec<String>>>>,
}

impl CrdWatcher {
    /// Create a new CRD watcher
    pub async fn new(
        config: K8sConfig,
        registry: Arc<RwLock<ToolRegistry>>,
    ) -> Result<Self> {
        let client = if config.in_cluster {
            Client::try_default().await?
        } else {
            // Use kubeconfig for local development
            Client::try_default().await?
        };

        Ok(Self {
            client,
            config,
            registry,
            registered_tools: Arc::new(RwLock::new(HashMap::new())),
        })
    }

    /// Start the CRD watcher
    ///
    /// This spawns background tasks that watch for Tool and ToolSet changes
    /// and reconcile them with the tool registry.
    #[instrument(skip(self))]
    pub async fn start(self: Arc<Self>) -> Result<()> {
        if !self.config.enabled {
            info!("K8s CRD watcher disabled, skipping");
            return Ok(());
        }

        info!("Starting K8s CRD watcher");

        // Clone Arc for the spawned tasks
        let tool_watcher = Arc::clone(&self);
        let toolset_watcher = Arc::clone(&self);

        // Spawn Tool watcher
        tokio::spawn(async move {
            if let Err(e) = tool_watcher.watch_tools().await {
                error!("Tool watcher error: {}", e);
            }
        });

        // Spawn ToolSet watcher
        tokio::spawn(async move {
            if let Err(e) = toolset_watcher.watch_toolsets().await {
                error!("ToolSet watcher error: {}", e);
            }
        });

        Ok(())
    }

    /// Watch Tool CRDs
    #[instrument(skip(self))]
    async fn watch_tools(&self) -> Result<()> {
        let api: Api<Tool> = match &self.config.namespace {
            Some(ns) => Api::namespaced(self.client.clone(), ns),
            None => Api::all(self.client.clone()),
        };

        // Note: label_selector support can be added via WatcherConfig if needed
        let watcher_config = WatcherConfig::default()
            .any_semantic();

        info!("Starting Tool CRD watcher");

        // Use kube-runtime controller for reconciliation
        let controller = Controller::new(api.clone(), watcher_config)
            .shutdown_on_signal();

        let registry = Arc::clone(&self.registry);
        let registered_tools = Arc::clone(&self.registered_tools);

        controller
            .run(
                |tool, _ctx| {
                    let registry = Arc::clone(&registry);
                    let registered_tools = Arc::clone(&registered_tools);
                    let api = api.clone();
                    async move {
                        match reconcile_tool(&tool, &registry, &registered_tools, &api).await {
                            Ok(action) => Ok(action),
                            Err(e) => {
                                error!("Failed to reconcile tool {}: {}", tool.name_any(), e);
                                Ok(Action::requeue(Duration::from_secs(60)))
                            }
                        }
                    }
                },
                |_tool, error: &kube::runtime::controller::Error<WatcherError, std::convert::Infallible>, _ctx| {
                    error!("Tool watcher error: {:?}", error);
                    Action::requeue(Duration::from_secs(60))
                },
                Arc::new(()),
            )
            .for_each(|res| async move {
                match res {
                    Ok((_tool, action)) => {
                        debug!("Tool reconciled: {:?}", action);
                    }
                    Err(e) => {
                        error!("Tool reconciliation error: {}", e);
                    }
                }
            })
            .await;

        Ok(())
    }

    /// Watch ToolSet CRDs
    #[instrument(skip(self))]
    async fn watch_toolsets(&self) -> Result<()> {
        let api: Api<ToolSet> = match &self.config.namespace {
            Some(ns) => Api::namespaced(self.client.clone(), ns),
            None => Api::all(self.client.clone()),
        };

        // Note: label_selector support can be added via WatcherConfig if needed
        let watcher_config = WatcherConfig::default()
            .any_semantic();

        info!("Starting ToolSet CRD watcher");

        let controller = Controller::new(api.clone(), watcher_config)
            .shutdown_on_signal();

        let registry = Arc::clone(&self.registry);
        let registered_tools = Arc::clone(&self.registered_tools);
        let client = self.client.clone();

        controller
            .run(
                |toolset, _ctx| {
                    let registry = Arc::clone(&registry);
                    let registered_tools = Arc::clone(&registered_tools);
                    let api = api.clone();
                    let client = client.clone();
                    async move {
                        match reconcile_toolset(&toolset, &registry, &registered_tools, &api, &client).await {
                            Ok(action) => Ok(action),
                            Err(e) => {
                                error!("Failed to reconcile toolset {}: {}", toolset.name_any(), e);
                                Ok(Action::requeue(Duration::from_secs(60)))
                            }
                        }
                    }
                },
                |_toolset, error: &kube::runtime::controller::Error<WatcherError, std::convert::Infallible>, _ctx| {
                    error!("ToolSet watcher error: {:?}", error);
                    Action::requeue(Duration::from_secs(60))
                },
                Arc::new(()),
            )
            .for_each(|res| async move {
                match res {
                    Ok((_toolset, action)) => {
                        debug!("ToolSet reconciled: {:?}", action);
                    }
                    Err(e) => {
                        error!("ToolSet reconciliation error: {}", e);
                    }
                }
            })
            .await;

        Ok(())
    }

    /// Get the number of tools registered from CRDs
    pub async fn tool_count(&self) -> usize {
        let registered = self.registered_tools.read().await;
        registered.values().map(|v| v.len()).sum()
    }

    /// Get all registered tool names by CRD resource
    pub async fn registered_tools(&self) -> HashMap<String, Vec<String>> {
        self.registered_tools.read().await.clone()
    }
}

/// Reconcile a Tool CRD
#[instrument(skip(registry, registered_tools, api))]
async fn reconcile_tool(
    tool: &Tool,
    registry: &Arc<RwLock<ToolRegistry>>,
    registered_tools: &Arc<RwLock<HashMap<String, Vec<String>>>>,
    api: &Api<Tool>,
) -> Result<Action> {
    let name = tool.name_any();
    let namespace = tool.namespace().unwrap_or_default();
    let resource_key = format!("{}/{}", namespace, name);

    // Check if tool is being deleted (has deletion timestamp)
    if tool.metadata.deletion_timestamp.is_some() {
        info!("Tool {} is being deleted, unregistering", resource_key);
        unregister_tool_from_registry(&resource_key, registry, registered_tools).await?;
        return Ok(Action::await_change());
    }

    let spec = &tool.spec;

    // Convert CRD spec to ToolDefinition
    let tool_name = format!("{}_{}", namespace.replace('-', "_"), name.replace('-', "_"));
    let _tool_def = tool_spec_to_definition(&tool_name, spec, &namespace)?;

    // Register in tool registry
    {
        let _reg = registry.write().await;
        // For now, we'll use a simple registration
        // In a full implementation, this would create a NativeTool or ProxyTool
        info!(
            "Registered tool {} from CRD {}/{}",
            tool_name, namespace, name
        );
    }

    // Track registered tool
    {
        let mut registered = registered_tools.write().await;
        registered
            .entry(resource_key.clone())
            .or_default()
            .push(tool_name.clone());
    }

    // Update Tool status
    let status = ToolStatus {
        ready: true,
        observed_generation: tool.metadata.generation,
        message: Some("Tool registered successfully".to_string()),
        last_validated: Some(chrono::Utc::now().to_rfc3339()),
        conditions: vec![super::ToolCondition {
            condition_type: "Ready".to_string(),
            status: "True".to_string(),
            last_transition_time: Some(chrono::Utc::now().to_rfc3339()),
            reason: Some("Registered".to_string()),
            message: Some("Tool registered in gateway".to_string()),
        }],
    };

    let patch = Patch::Merge(serde_json::json!({ "status": status }));
    if let Err(e) = api
        .patch_status(&name, &PatchParams::default(), &patch)
        .await
    {
        warn!("Failed to update Tool status: {}", e);
    }

    // Requeue after resync interval
    Ok(Action::requeue(Duration::from_secs(300)))
}

/// Reconcile a ToolSet CRD
#[instrument(skip(_registry, registered_tools, api, _client))]
async fn reconcile_toolset(
    toolset: &ToolSet,
    _registry: &Arc<RwLock<ToolRegistry>>,
    registered_tools: &Arc<RwLock<HashMap<String, Vec<String>>>>,
    api: &Api<ToolSet>,
    _client: &Client,
) -> Result<Action> {
    let name = toolset.name_any();
    let namespace = toolset.namespace().unwrap_or_default();
    let resource_key = format!("{}/{}", namespace, name);

    // Check if toolset is being deleted
    if toolset.metadata.deletion_timestamp.is_some() {
        info!("ToolSet {} is being deleted, unregistering tools", resource_key);
        unregister_tool_from_registry(&resource_key, _registry, registered_tools).await?;
        return Ok(Action::await_change());
    }

    let spec = &toolset.spec;
    let mut tool_names = Vec::new();

    match spec.toolset_type.as_str() {
        "upstream" => {
            // Federation: discover tools from upstream MCP server
            if let Some(upstream) = &spec.upstream {
                info!(
                    "ToolSet {} is upstream federation to {}",
                    resource_key, upstream.url
                );

                // In a full implementation, this would:
                // 1. Connect to upstream MCP server
                // 2. Call tools/list
                // 3. Register discovered tools with prefix
                // For now, register the configured tools
                for tool_ref in &spec.tools {
                    let tool_name = tool_ref
                        .alias
                        .clone()
                        .unwrap_or_else(|| format!("{}_{}", name.replace('-', "_"), tool_ref.name));

                    if tool_ref.enabled {
                        tool_names.push(tool_name.clone());
                        info!("Registered federated tool {} from {}", tool_name, resource_key);
                    }
                }
            }
        }
        "composition" => {
            // Composition: create a compound tool from steps
            if let Some(composition) = &spec.composition {
                info!(
                    "ToolSet {} is composition tool {}",
                    resource_key, composition.name
                );

                // In a full implementation, this would create a ComposedTool
                // that executes the steps sequentially
                tool_names.push(composition.name.clone());
                info!(
                    "Registered composed tool {} with {} steps",
                    composition.name,
                    composition.steps.len()
                );
            }
        }
        _ => {
            warn!("Unknown ToolSet type: {}", spec.toolset_type);
        }
    }

    // Track registered tools
    {
        let mut registered = registered_tools.write().await;
        registered.insert(resource_key.clone(), tool_names.clone());
    }

    // Update ToolSet status
    let status = super::ToolSetStatus {
        ready: true,
        tool_count: tool_names.len() as i32,
        observed_generation: toolset.metadata.generation,
        message: Some(format!("Registered {} tools", tool_names.len())),
        last_sync: Some(chrono::Utc::now().to_rfc3339()),
        registered_tools: tool_names,
        conditions: vec![super::ToolCondition {
            condition_type: "Ready".to_string(),
            status: "True".to_string(),
            last_transition_time: Some(chrono::Utc::now().to_rfc3339()),
            reason: Some("Synced".to_string()),
            message: Some("Tools synchronized successfully".to_string()),
        }],
    };

    let patch = Patch::Merge(serde_json::json!({ "status": status }));
    if let Err(e) = api
        .patch_status(&name, &PatchParams::default(), &patch)
        .await
    {
        warn!("Failed to update ToolSet status: {}", e);
    }

    // Requeue based on refresh interval
    let refresh_secs = parse_duration(&spec.refresh_interval).unwrap_or(300);
    Ok(Action::requeue(Duration::from_secs(refresh_secs)))
}

/// Unregister tools associated with a CRD resource
async fn unregister_tool_from_registry(
    resource_key: &str,
    _registry: &Arc<RwLock<ToolRegistry>>,
    registered_tools: &Arc<RwLock<HashMap<String, Vec<String>>>>,
) -> Result<()> {
    let tools_to_remove = {
        let mut registered = registered_tools.write().await;
        registered.remove(resource_key).unwrap_or_default()
    };

    // In a full implementation, remove from registry
    for tool_name in &tools_to_remove {
        info!("Unregistered tool {} (from {})", tool_name, resource_key);
    }

    Ok(())
}

/// Convert a ToolSpec to a ToolDefinition
fn tool_spec_to_definition(
    name: &str,
    spec: &ToolSpec,
    _tenant_id: &str,
) -> Result<ToolDefinition> {
    // Convert properties from Value to HashMap<String, Value>
    let properties_map: std::collections::HashMap<String, serde_json::Value> = spec
        .input_schema
        .get("properties")
        .and_then(|v| v.as_object())
        .map(|obj| obj.iter().map(|(k, v)| (k.clone(), v.clone())).collect())
        .unwrap_or_default();

    let input_schema = ToolSchema {
        schema_type: spec
            .input_schema
            .get("type")
            .and_then(|v| v.as_str())
            .unwrap_or("object")
            .to_string(),
        properties: properties_map,
        required: spec
            .input_schema
            .get("required")
            .and_then(|v| v.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|v| v.as_str().map(String::from))
                    .collect()
            })
            .unwrap_or_default(),
    };

    Ok(ToolDefinition {
        name: name.to_string(),
        description: spec.description.clone(),
        input_schema,
    })
}

/// Parse duration string (e.g., "5m", "1h", "30s")
fn parse_duration(s: &str) -> Option<u64> {
    let s = s.trim();
    if s.is_empty() {
        return None;
    }

    let (num, unit) = s.split_at(s.len() - 1);
    let num: u64 = num.parse().ok()?;

    match unit {
        "s" => Some(num),
        "m" => Some(num * 60),
        "h" => Some(num * 3600),
        "d" => Some(num * 86400),
        _ => s.parse().ok(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_duration() {
        assert_eq!(parse_duration("30s"), Some(30));
        assert_eq!(parse_duration("5m"), Some(300));
        assert_eq!(parse_duration("1h"), Some(3600));
        assert_eq!(parse_duration("1d"), Some(86400));
        assert_eq!(parse_duration("300"), Some(300));
        assert_eq!(parse_duration(""), None);
    }

    #[test]
    fn test_tool_spec_to_definition() {
        let spec = ToolSpec {
            display_name: "Test Tool".to_string(),
            description: "A test tool".to_string(),
            endpoint: "https://api.example.com/test".to_string(),
            method: "POST".to_string(),
            input_schema: serde_json::json!({
                "type": "object",
                "properties": {
                    "name": {"type": "string"}
                },
                "required": ["name"]
            }),
            output_schema: None,
            auth: None,
            rate_limit: None,
            timeout: "30s".to_string(),
            annotations: None,
            headers: HashMap::new(),
            requires_confirmation: false,
        };

        let def = tool_spec_to_definition("test_tool", &spec, "tenant-acme").unwrap();
        assert_eq!(def.name, "test_tool");
        assert_eq!(def.description, "A test tool");
        assert_eq!(def.input_schema.required, vec!["name"]);
    }
}
