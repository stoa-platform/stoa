//! Plugin Registry — Load, Unload, Execute (CAB-1759)
//!
//! Thread-safe registry that manages plugin lifecycle and phase-based execution.
//! Supports hot-reload: plugins can be added/removed at runtime without restart.

use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::{info, warn};

use super::sdk::{Phase, Plugin, PluginContext, PluginMetadata, PluginResult};

/// Thread-safe plugin registry with hot-reload support.
///
/// Plugins are stored by name and indexed by phase for fast lookup.
/// All operations are async and use `RwLock` for concurrent read access.
pub struct PluginRegistry {
    /// Plugins indexed by name
    plugins: RwLock<HashMap<String, Arc<dyn Plugin>>>,
    /// Phase index: maps each phase to ordered list of plugin names
    phase_index: RwLock<HashMap<Phase, Vec<String>>>,
}

impl PluginRegistry {
    /// Create an empty plugin registry.
    pub fn new() -> Self {
        Self {
            plugins: RwLock::new(HashMap::new()),
            phase_index: RwLock::new(HashMap::new()),
        }
    }

    /// Register a plugin into the registry.
    ///
    /// Calls `on_load` with the provided config. If `on_load` fails,
    /// the plugin is not registered and an error is returned.
    /// If a plugin with the same name exists, it is replaced (hot-reload).
    pub async fn register(
        &self,
        plugin: Arc<dyn Plugin>,
        config: &serde_json::Value,
    ) -> Result<PluginMetadata, String> {
        let metadata = plugin.metadata();
        let name = metadata.name.clone();

        // Call on_load for initialization
        plugin.on_load(config).await?;

        // If replacing an existing plugin, unload it first
        {
            let plugins = self.plugins.read().await;
            if let Some(existing) = plugins.get(&name) {
                if let Err(e) = existing.on_unload().await {
                    warn!(plugin = %name, error = %e, "failed to unload existing plugin during hot-reload");
                }
            }
        }

        // Update phase index
        {
            let mut index = self.phase_index.write().await;
            // Remove old entries for this plugin name
            for phase_plugins in index.values_mut() {
                phase_plugins.retain(|n| n != &name);
            }
            // Add new entries
            for phase in &metadata.phases {
                index.entry(*phase).or_default().push(name.clone());
            }
        }

        // Insert plugin
        {
            let mut plugins = self.plugins.write().await;
            plugins.insert(name.clone(), plugin);
        }

        info!(plugin = %name, version = %metadata.version, phases = ?metadata.phases, "plugin registered");
        Ok(metadata)
    }

    /// Unregister a plugin by name.
    ///
    /// Calls `on_unload` for cleanup. Returns the metadata of the removed plugin,
    /// or `None` if no plugin with that name was registered.
    pub async fn unregister(&self, name: &str) -> Option<PluginMetadata> {
        let plugin = {
            let mut plugins = self.plugins.write().await;
            plugins.remove(name)
        };

        if let Some(ref plugin) = plugin {
            let metadata = plugin.metadata();

            // Remove from phase index
            {
                let mut index = self.phase_index.write().await;
                for phase_plugins in index.values_mut() {
                    phase_plugins.retain(|n| n != name);
                }
            }

            // Call on_unload
            if let Err(e) = plugin.on_unload().await {
                warn!(plugin = %name, error = %e, "plugin on_unload failed");
            }

            info!(plugin = %name, "plugin unregistered");
            Some(metadata)
        } else {
            None
        }
    }

    /// Execute all plugins registered for a given phase.
    ///
    /// Plugins are executed in registration order. If any plugin returns
    /// `PluginResult::Terminate`, execution stops and the termination
    /// result is returned immediately.
    pub async fn execute_phase(&self, phase: Phase, ctx: &mut PluginContext) -> PluginResult {
        let plugin_names = {
            let index = self.phase_index.read().await;
            index.get(&phase).cloned().unwrap_or_default()
        };

        let plugins = self.plugins.read().await;

        for name in &plugin_names {
            if let Some(plugin) = plugins.get(name) {
                let result = plugin.execute(phase, ctx).await;
                match &result {
                    PluginResult::Terminate { status, .. } => {
                        info!(
                            plugin = %name,
                            phase = %phase,
                            status = %status,
                            "plugin terminated request"
                        );
                        return result;
                    }
                    PluginResult::Continue => {}
                }
            }
        }

        PluginResult::Continue
    }

    /// List all registered plugins and their metadata.
    pub async fn list(&self) -> Vec<PluginMetadata> {
        let plugins = self.plugins.read().await;
        plugins.values().map(|p| p.metadata()).collect()
    }

    /// Get metadata for a specific plugin by name.
    pub async fn get(&self, name: &str) -> Option<PluginMetadata> {
        let plugins = self.plugins.read().await;
        plugins.get(name).map(|p| p.metadata())
    }

    /// Get the number of registered plugins.
    pub async fn count(&self) -> usize {
        let plugins = self.plugins.read().await;
        plugins.len()
    }

    /// Get plugin names registered for a specific phase.
    pub async fn plugins_for_phase(&self, phase: Phase) -> Vec<String> {
        let index = self.phase_index.read().await;
        index.get(&phase).cloned().unwrap_or_default()
    }
}

impl Default for PluginRegistry {
    fn default() -> Self {
        Self::new()
    }
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use async_trait::async_trait;
    use axum::http::{HeaderMap, StatusCode};

    /// Test plugin that adds a custom header.
    struct TestPlugin {
        name: String,
        phases: Vec<Phase>,
    }

    impl TestPlugin {
        fn new(name: &str, phases: Vec<Phase>) -> Self {
            Self {
                name: name.to_string(),
                phases,
            }
        }
    }

    #[async_trait]
    impl Plugin for TestPlugin {
        fn metadata(&self) -> PluginMetadata {
            PluginMetadata {
                name: self.name.clone(),
                version: "1.0.0".to_string(),
                description: format!("Test plugin: {}", self.name),
                phases: self.phases.clone(),
            }
        }

        async fn execute(&self, _phase: Phase, ctx: &mut PluginContext) -> PluginResult {
            ctx.set_request_header(&format!("X-Plugin-{}", self.name), "active");
            PluginResult::Continue
        }
    }

    /// Test plugin that terminates requests.
    struct BlockingPlugin;

    #[async_trait]
    impl Plugin for BlockingPlugin {
        fn metadata(&self) -> PluginMetadata {
            PluginMetadata {
                name: "blocker".to_string(),
                version: "1.0.0".to_string(),
                description: "Blocks all requests".to_string(),
                phases: vec![Phase::PreAuth],
            }
        }

        async fn execute(&self, _phase: Phase, _ctx: &mut PluginContext) -> PluginResult {
            PluginResult::Terminate {
                status: StatusCode::FORBIDDEN,
                body: "blocked by plugin".to_string(),
            }
        }
    }

    /// Plugin that fails on_load.
    struct FailLoadPlugin;

    #[async_trait]
    impl Plugin for FailLoadPlugin {
        fn metadata(&self) -> PluginMetadata {
            PluginMetadata {
                name: "fail-load".to_string(),
                version: "1.0.0".to_string(),
                description: "Fails on load".to_string(),
                phases: vec![Phase::PreAuth],
            }
        }

        async fn on_load(&self, _config: &serde_json::Value) -> Result<(), String> {
            Err("initialization failed".to_string())
        }

        async fn execute(&self, _phase: Phase, _ctx: &mut PluginContext) -> PluginResult {
            PluginResult::Continue
        }
    }

    fn make_ctx() -> PluginContext {
        PluginContext::new(
            Phase::PreAuth,
            "test-tenant".to_string(),
            "/test".to_string(),
            "GET".to_string(),
            HeaderMap::new(),
        )
    }

    #[tokio::test]
    async fn test_register_and_list() {
        let registry = PluginRegistry::new();
        let plugin = Arc::new(TestPlugin::new("test-1", vec![Phase::PreAuth]));

        let meta = registry
            .register(plugin, &serde_json::Value::Null)
            .await
            .expect("register");

        assert_eq!(meta.name, "test-1");
        assert_eq!(registry.count().await, 1);

        let list = registry.list().await;
        assert_eq!(list.len(), 1);
        assert_eq!(list[0].name, "test-1");
    }

    #[tokio::test]
    async fn test_unregister() {
        let registry = PluginRegistry::new();
        let plugin = Arc::new(TestPlugin::new("removable", vec![Phase::PostUpstream]));

        registry
            .register(plugin, &serde_json::Value::Null)
            .await
            .expect("register");

        assert_eq!(registry.count().await, 1);

        let removed = registry.unregister("removable").await;
        assert!(removed.is_some());
        assert_eq!(removed.expect("removed").name, "removable");
        assert_eq!(registry.count().await, 0);
    }

    #[tokio::test]
    async fn test_unregister_nonexistent() {
        let registry = PluginRegistry::new();
        let removed = registry.unregister("ghost").await;
        assert!(removed.is_none());
    }

    #[tokio::test]
    async fn test_execute_phase_continue() {
        let registry = PluginRegistry::new();
        let plugin = Arc::new(TestPlugin::new("header-adder", vec![Phase::PreAuth]));

        registry
            .register(plugin, &serde_json::Value::Null)
            .await
            .expect("register");

        let mut ctx = make_ctx();
        let result = registry.execute_phase(Phase::PreAuth, &mut ctx).await;
        assert!(matches!(result, PluginResult::Continue));
        assert_eq!(
            ctx.get_request_header("x-plugin-header-adder"),
            Some("active")
        );
    }

    #[tokio::test]
    async fn test_execute_phase_terminate() {
        let registry = PluginRegistry::new();
        let plugin = Arc::new(BlockingPlugin);

        registry
            .register(plugin, &serde_json::Value::Null)
            .await
            .expect("register");

        let mut ctx = make_ctx();
        let result = registry.execute_phase(Phase::PreAuth, &mut ctx).await;
        match result {
            PluginResult::Terminate { status, body } => {
                assert_eq!(status, StatusCode::FORBIDDEN);
                assert_eq!(body, "blocked by plugin");
            }
            _ => panic!("expected Terminate"),
        }
    }

    #[tokio::test]
    async fn test_execute_phase_chain_stops_on_terminate() {
        let registry = PluginRegistry::new();

        // Register a plugin that continues
        let p1 = Arc::new(TestPlugin::new("first", vec![Phase::PreAuth]));
        registry
            .register(p1, &serde_json::Value::Null)
            .await
            .expect("register p1");

        // Register a plugin that terminates
        let p2 = Arc::new(BlockingPlugin);
        registry
            .register(p2, &serde_json::Value::Null)
            .await
            .expect("register p2");

        // Register a plugin that should NOT execute (after termination)
        let p3 = Arc::new(TestPlugin::new("third", vec![Phase::PreAuth]));
        registry
            .register(p3, &serde_json::Value::Null)
            .await
            .expect("register p3");

        let mut ctx = make_ctx();
        let result = registry.execute_phase(Phase::PreAuth, &mut ctx).await;
        assert!(matches!(result, PluginResult::Terminate { .. }));

        // First plugin ran (set header)
        assert_eq!(ctx.get_request_header("x-plugin-first"), Some("active"));
        // Third plugin did NOT run (blocked by termination)
        assert_eq!(ctx.get_request_header("x-plugin-third"), None);
    }

    #[tokio::test]
    async fn test_execute_empty_phase() {
        let registry = PluginRegistry::new();
        let mut ctx = make_ctx();

        // No plugins registered — should return Continue
        let result = registry.execute_phase(Phase::OnError, &mut ctx).await;
        assert!(matches!(result, PluginResult::Continue));
    }

    #[tokio::test]
    async fn test_phase_index() {
        let registry = PluginRegistry::new();

        let p1 = Arc::new(TestPlugin::new(
            "multi",
            vec![Phase::PreAuth, Phase::PostUpstream],
        ));
        registry
            .register(p1, &serde_json::Value::Null)
            .await
            .expect("register");

        let pre_auth = registry.plugins_for_phase(Phase::PreAuth).await;
        assert_eq!(pre_auth, vec!["multi"]);

        let post_upstream = registry.plugins_for_phase(Phase::PostUpstream).await;
        assert_eq!(post_upstream, vec!["multi"]);

        let on_error = registry.plugins_for_phase(Phase::OnError).await;
        assert!(on_error.is_empty());
    }

    #[tokio::test]
    async fn test_hot_reload_replaces_plugin() {
        let registry = PluginRegistry::new();

        let v1 = Arc::new(TestPlugin::new("updatable", vec![Phase::PreAuth]));
        registry
            .register(v1, &serde_json::Value::Null)
            .await
            .expect("register v1");

        assert_eq!(registry.count().await, 1);

        // Re-register with same name = hot-reload
        let v2 = Arc::new(TestPlugin::new(
            "updatable",
            vec![Phase::PreAuth, Phase::PostUpstream],
        ));
        registry
            .register(v2, &serde_json::Value::Null)
            .await
            .expect("register v2");

        // Still 1 plugin (replaced, not added)
        assert_eq!(registry.count().await, 1);

        // Phase index updated
        let phases = registry.plugins_for_phase(Phase::PostUpstream).await;
        assert_eq!(phases, vec!["updatable"]);
    }

    #[tokio::test]
    async fn test_failed_load_not_registered() {
        let registry = PluginRegistry::new();
        let plugin = Arc::new(FailLoadPlugin);

        let result = registry.register(plugin, &serde_json::Value::Null).await;
        assert!(result.is_err());
        assert_eq!(registry.count().await, 0);
    }

    #[tokio::test]
    async fn test_get_plugin() {
        let registry = PluginRegistry::new();
        let plugin = Arc::new(TestPlugin::new("findable", vec![Phase::PreUpstream]));

        registry
            .register(plugin, &serde_json::Value::Null)
            .await
            .expect("register");

        let found = registry.get("findable").await;
        assert!(found.is_some());
        assert_eq!(found.expect("found").name, "findable");

        let not_found = registry.get("missing").await;
        assert!(not_found.is_none());
    }

    #[tokio::test]
    async fn test_unregister_clears_phase_index() {
        let registry = PluginRegistry::new();
        let plugin = Arc::new(TestPlugin::new(
            "indexed",
            vec![Phase::PreAuth, Phase::OnError],
        ));

        registry
            .register(plugin, &serde_json::Value::Null)
            .await
            .expect("register");

        assert_eq!(registry.plugins_for_phase(Phase::PreAuth).await.len(), 1);
        assert_eq!(registry.plugins_for_phase(Phase::OnError).await.len(), 1);

        registry.unregister("indexed").await;

        assert!(registry.plugins_for_phase(Phase::PreAuth).await.is_empty());
        assert!(registry.plugins_for_phase(Phase::OnError).await.is_empty());
    }
}
