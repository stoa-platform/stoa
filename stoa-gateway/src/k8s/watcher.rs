//! K8s CRD Watcher
//!
//! Watches Tool and ToolSet CRDs and dynamically registers/unregisters tools.
//!
//! Requires: `k8s` feature flag (enforced by mod.rs)

use std::sync::Arc;

use futures::StreamExt;
use kube::{
    api::Api,
    runtime::{watcher, watcher::Event},
    Client,
};
use tracing::{debug, error, info, warn};

use super::crds::{GuardrailPolicy, Skill, Tool, ToolAnnotationsCrd, ToolSet};
use crate::events::notifications::format_tools_list_changed;
use crate::federation::upstream::{TransportType, UpstreamMcpClient, UpstreamMcpConfig};
use crate::federation::FederatedTool;
use crate::guardrails::policy::{GuardrailPolicyStore, TenantGuardrailPolicy};
use crate::mcp::session::SessionManager;
use crate::mcp::tools::dynamic_tool::{schema_from_value, DynamicTool};
use crate::mcp::tools::{ToolAnnotations, ToolRegistry};
use crate::skills::resolver::{SkillResolver, SkillScope, StoredSkill};

/// CRD Watcher for dynamic tool + skill + guardrail policy registration
pub struct CrdWatcher {
    client: Client,
    tool_registry: Arc<ToolRegistry>,
    skill_resolver: Arc<SkillResolver>,
    session_manager: Arc<SessionManager>,
    guardrail_policy_store: Arc<GuardrailPolicyStore>,
}

impl CrdWatcher {
    /// Create a new CRD watcher
    pub fn new(
        client: Client,
        tool_registry: Arc<ToolRegistry>,
        skill_resolver: Arc<SkillResolver>,
        session_manager: Arc<SessionManager>,
        guardrail_policy_store: Arc<GuardrailPolicyStore>,
    ) -> Self {
        Self {
            client,
            tool_registry,
            skill_resolver,
            session_manager,
            guardrail_policy_store,
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

        // Watch Skill CRDs (CAB-1314)
        let skills: Api<Skill> = Api::all(self.client.clone());
        let skill_watcher = watcher(skills, watcher::Config::default());

        // Watch GuardrailPolicy CRDs (CAB-1337 Phase 3)
        let guardrail_policies: Api<GuardrailPolicy> = Api::all(self.client.clone());
        let guardrail_policy_watcher = watcher(guardrail_policies, watcher::Config::default());

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
            result = self.watch_skills(skill_watcher) => {
                if let Err(e) = result {
                    error!(error = %e, "Skill watcher failed");
                }
            }
            result = self.watch_guardrail_policies(guardrail_policy_watcher) => {
                if let Err(e) = result {
                    error!(error = %e, "GuardrailPolicy watcher failed");
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

    /// Watch Skill CRD events (CAB-1314)
    async fn watch_skills(
        &self,
        watcher: impl futures::Stream<Item = Result<Event<Skill>, watcher::Error>>,
    ) -> Result<(), watcher::Error> {
        tokio::pin!(watcher);

        while let Some(event) = watcher.next().await {
            match event {
                Ok(Event::Apply(skill)) => {
                    self.handle_skill_apply(&skill);
                }
                Ok(Event::Delete(skill)) => {
                    self.handle_skill_delete(&skill);
                }
                Ok(Event::Init) => {
                    debug!("Skill watcher initialized");
                }
                Ok(Event::InitApply(skill)) => {
                    self.handle_skill_apply(&skill);
                }
                Ok(Event::InitDone) => {
                    info!(
                        count = self.skill_resolver.count(),
                        "Skill watcher initial sync complete"
                    );
                }
                Err(e) => {
                    warn!(error = %e, "Skill watcher error");
                }
            }
        }

        Ok(())
    }

    /// Handle Skill CRD apply — upsert into resolver (sync, no .await needed)
    fn handle_skill_apply(&self, skill: &Skill) {
        let namespace = skill.metadata.namespace.as_deref().unwrap_or("default");
        let meta_name = skill.metadata.name.as_deref().unwrap_or("unknown");
        let key = format!("{}/{}", namespace, meta_name);

        let scope = match SkillScope::from_crd(&skill.spec.scope) {
            Some(s) => s,
            None => {
                warn!(
                    skill = %meta_name,
                    scope = %skill.spec.scope,
                    "Invalid skill scope — skipping"
                );
                return;
            }
        };

        // Clamp priority to 0-100 and cast to u8
        let priority = skill.spec.priority.clamp(0, 100) as u8;

        let stored = StoredSkill {
            key: key.clone(),
            name: skill.spec.name.clone(),
            description: skill.spec.description.clone(),
            tenant_id: namespace.to_string(),
            scope,
            priority,
            instructions: skill.spec.instructions.clone(),
            tool_ref: skill.spec.tool_ref.clone(),
            user_ref: skill.spec.user_ref.clone(),
            enabled: skill.spec.enabled,
        };

        self.skill_resolver.upsert(stored);

        info!(
            skill = %key,
            scope = %scope,
            priority,
            tenant = %namespace,
            "Skill registered from CRD"
        );
    }

    /// Handle Skill CRD delete — remove from resolver (sync)
    fn handle_skill_delete(&self, skill: &Skill) {
        let namespace = skill.metadata.namespace.as_deref().unwrap_or("default");
        let meta_name = skill.metadata.name.as_deref().unwrap_or("unknown");
        let key = format!("{}/{}", namespace, meta_name);

        if self.skill_resolver.remove(&key) {
            info!(skill = %key, "Skill unregistered (CRD deleted)");
        } else {
            debug!(skill = %key, "Skill was not registered");
        }
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

        // Build input schema from CRD spec
        let input_schema = schema_from_value(&tool.spec.input_schema);

        // Create DynamicTool from CRD
        let mut dynamic = DynamicTool::new(
            tool_name.clone(),
            &tool.spec.description,
            &tool.spec.endpoint,
            &tool.spec.method,
            input_schema,
            namespace,
        );

        // Apply output schema if present
        if let Some(ref output) = tool.spec.output_schema {
            dynamic = dynamic.with_output_schema(output.clone());
        }

        // Apply annotations from CRD
        if let Some(ref crd_ann) = tool.spec.annotations {
            dynamic = dynamic.with_annotations(crd_annotations_to_mcp(crd_ann));
        }

        // Register (overwrites if already exists)
        self.tool_registry.register(Arc::new(dynamic));

        // Notify connected SSE clients that the tool list changed (MCP hot-reload)
        let notification = format_tools_list_changed();
        let sent = self
            .session_manager
            .broadcast_to_tenant(namespace, "message", &notification);
        if sent > 0 {
            debug!(
                tool = %tool_name,
                tenant = %namespace,
                sessions_notified = sent,
                "Sent tools/list_changed notification"
            );
        }

        info!(
            tool = %tool_name,
            display_name = %tool.spec.display_name,
            method = %tool.spec.method,
            "Tool registered from CRD"
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
            // Notify connected SSE clients that the tool list changed (MCP hot-reload)
            let notification = format_tools_list_changed();
            let sent =
                self.session_manager
                    .broadcast_to_tenant(namespace, "message", &notification);
            if sent > 0 {
                debug!(
                    tool = %tool_name,
                    tenant = %namespace,
                    sessions_notified = sent,
                    "Sent tools/list_changed notification (tool deleted)"
                );
            }
            info!(tool = %tool_name, "Tool unregistered successfully");
        } else {
            debug!(tool = %tool_name, "Tool was not registered");
        }
    }

    /// Handle ToolSet CRD apply — connect to upstream MCP server and register federated tools
    async fn handle_toolset_apply(&self, toolset: &ToolSet) {
        let namespace = toolset.metadata.namespace.as_deref().unwrap_or("default");
        let name = toolset.metadata.name.as_deref().unwrap_or("unknown");
        let prefix = toolset.spec.prefix.as_deref().unwrap_or("");

        info!(
            toolset = %name,
            tenant = %namespace,
            upstream = %toolset.spec.upstream.url,
            "Processing ToolSet CRD"
        );

        // Read auth token from K8s Secret if configured
        let auth_token = if let Some(auth) = &toolset.spec.upstream.auth {
            let secret_key = auth.secret_key.as_deref().unwrap_or("token");
            match self
                .read_secret(namespace, &auth.secret_ref, secret_key)
                .await
            {
                Ok(token) => Some(token),
                Err(e) => {
                    warn!(
                        secret = %auth.secret_ref,
                        key = %secret_key,
                        error = %e,
                        "Failed to read auth secret"
                    );
                    None
                }
            }
        } else {
            None
        };

        // Create upstream MCP client
        let config = UpstreamMcpConfig {
            url: toolset.spec.upstream.url.clone(),
            transport: TransportType::from_str(&toolset.spec.upstream.transport),
            auth_token,
            timeout: std::time::Duration::from_secs(
                toolset.spec.upstream.timeout_seconds.unwrap_or(30) as u64,
            ),
        };

        let mut client = UpstreamMcpClient::new(config);

        // Initialize connection (MCP handshake)
        if let Err(e) = client.initialize().await {
            warn!(
                toolset = %name,
                error = %e,
                "Failed to connect to upstream MCP server"
            );
            return;
        }

        // Discover tools from upstream
        let tools = match client.discover_tools().await {
            Ok(t) => t,
            Err(e) => {
                warn!(toolset = %name, error = %e, "Failed to discover upstream tools");
                return;
            }
        };

        let upstream = Arc::new(client);
        let filter = &toolset.spec.tools;
        let mut registered = 0;

        for tool_def in &tools {
            // Apply tool filter (empty = all tools)
            if !filter.is_empty() && !filter.contains(&tool_def.name) {
                debug!(tool = %tool_def.name, "Skipping tool (not in filter list)");
                continue;
            }

            let federated_name =
                format!("{}{}_{}", prefix, namespace, to_snake_case(&tool_def.name));

            let federated = FederatedTool::new(
                federated_name.clone(),
                tool_def.clone(),
                upstream.clone(),
                tool_def.name.clone(),
                namespace.to_string(),
            );

            self.tool_registry.register(Arc::new(federated));
            registered += 1;
        }

        info!(
            toolset = %name,
            tenant = %namespace,
            registered,
            total_discovered = tools.len(),
            "ToolSet tools registered from upstream"
        );

        // Notify connected SSE clients if any tools were registered
        if registered > 0 {
            let notification = format_tools_list_changed();
            let sent =
                self.session_manager
                    .broadcast_to_tenant(namespace, "message", &notification);
            if sent > 0 {
                debug!(
                    toolset = %name,
                    tenant = %namespace,
                    sessions_notified = sent,
                    "Sent tools/list_changed notification (ToolSet applied)"
                );
            }
        }
    }

    /// Read a key from a K8s Secret
    async fn read_secret(&self, namespace: &str, name: &str, key: &str) -> Result<String, String> {
        let secrets: Api<k8s_openapi::api::core::v1::Secret> =
            Api::namespaced(self.client.clone(), namespace);

        let secret = secrets
            .get(name)
            .await
            .map_err(|e| format!("Failed to get secret {}/{}: {}", namespace, name, e))?;

        let data = secret
            .data
            .ok_or_else(|| format!("Secret {}/{} has no data", namespace, name))?;

        let bytes = data
            .get(key)
            .ok_or_else(|| format!("Secret {}/{} has no key '{}'", namespace, name, key))?;

        String::from_utf8(bytes.0.clone()).map_err(|e| {
            format!(
                "Secret {}/{} key '{}' is not valid UTF-8: {}",
                namespace, name, key, e
            )
        })
    }

    /// Handle ToolSet CRD delete — unregister all tools with matching prefix
    fn handle_toolset_delete(&self, toolset: &ToolSet) {
        let namespace = toolset.metadata.namespace.as_deref().unwrap_or("default");
        let name = toolset.metadata.name.as_deref().unwrap_or("unknown");
        let prefix = toolset.spec.prefix.as_deref().unwrap_or("");

        info!(
            toolset = %name,
            tenant = %namespace,
            "Removing ToolSet tools (CRD deleted)"
        );

        // Unregister tools that match the prefix+namespace pattern
        let tool_prefix = format!("{}{}_", prefix, namespace);
        let names = self.tool_registry.names();
        let mut removed = 0;

        for tool_name in &names {
            if tool_name.starts_with(&tool_prefix) && self.tool_registry.unregister(tool_name) {
                removed += 1;
            }
        }

        info!(toolset = %name, removed, "ToolSet tools removed");

        // Notify connected SSE clients if any tools were removed
        if removed > 0 {
            let notification = format_tools_list_changed();
            let sent =
                self.session_manager
                    .broadcast_to_tenant(namespace, "message", &notification);
            if sent > 0 {
                debug!(
                    toolset = %name,
                    tenant = %namespace,
                    sessions_notified = sent,
                    "Sent tools/list_changed notification (ToolSet deleted)"
                );
            }
        }
    }
}

/// Convert CRD annotations to MCP ToolAnnotations
fn crd_annotations_to_mcp(crd: &ToolAnnotationsCrd) -> ToolAnnotations {
    ToolAnnotations {
        title: None,
        read_only_hint: crd.read_only,
        destructive_hint: crd.destructive,
        idempotent_hint: crd.idempotent,
        open_world_hint: crd.open_world,
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
