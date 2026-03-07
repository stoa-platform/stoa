//! API Proxy — Internal dogfooding backend registry (CAB-1722).
//!
//! Routes `/apis/{backend}/*` requests to configured upstream backends
//! with credential injection and per-backend feature flags.
//! Separate from the existing `/mcp/*` router (Council adjustment #4).

use crate::config::{ApiProxyConfig, ProxyBackendConfig};
use parking_lot::RwLock;
use std::collections::HashMap;

/// Runtime registry of enabled proxy backends.
/// Built from `ApiProxyConfig` at startup, supports hot-reload.
pub struct ApiProxyRegistry {
    backends: RwLock<HashMap<String, RegisteredBackend>>,
}

/// A backend resolved from config into runtime state.
#[derive(Debug, Clone)]
pub struct RegisteredBackend {
    pub name: String,
    pub config: ProxyBackendConfig,
}

impl ApiProxyRegistry {
    /// Create a registry from the API proxy config section.
    /// Only registers backends where `enabled: true`.
    pub fn from_config(config: &ApiProxyConfig) -> Self {
        let mut backends = HashMap::new();
        for (name, backend_config) in &config.backends {
            if backend_config.enabled {
                backends.insert(
                    name.clone(),
                    RegisteredBackend {
                        name: name.clone(),
                        config: backend_config.clone(),
                    },
                );
                tracing::info!(
                    backend = %name,
                    base_url = %backend_config.base_url,
                    rate_limit_rpm = backend_config.rate_limit_rpm,
                    circuit_breaker = backend_config.circuit_breaker_enabled,
                    fallback_direct = backend_config.fallback_direct,
                    "API proxy backend registered"
                );
            } else {
                tracing::debug!(backend = %name, "API proxy backend disabled, skipping");
            }
        }

        if backends.is_empty() {
            tracing::info!("API proxy: no backends enabled");
        } else {
            tracing::info!(count = backends.len(), "API proxy: backends registered");
        }

        Self {
            backends: RwLock::new(backends),
        }
    }

    /// Look up a backend by name. Returns None if not registered or disabled.
    pub fn get(&self, name: &str) -> Option<RegisteredBackend> {
        self.backends.read().get(name).cloned()
    }

    /// List all registered (enabled) backend names.
    pub fn list_names(&self) -> Vec<String> {
        self.backends.read().keys().cloned().collect()
    }

    /// Number of registered backends.
    pub fn count(&self) -> usize {
        self.backends.read().len()
    }

    /// Hot-reload: replace all backends from updated config.
    pub fn reload(&self, config: &ApiProxyConfig) {
        let mut backends = HashMap::new();
        for (name, backend_config) in &config.backends {
            if backend_config.enabled {
                backends.insert(
                    name.clone(),
                    RegisteredBackend {
                        name: name.clone(),
                        config: backend_config.clone(),
                    },
                );
            }
        }
        let count = backends.len();
        *self.backends.write() = backends;
        tracing::info!(count, "API proxy: backends reloaded");
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::ApiProxyConfig;

    fn make_config(backends: Vec<(&str, bool, &str)>) -> ApiProxyConfig {
        let mut map = HashMap::new();
        for (name, enabled, url) in backends {
            map.insert(
                name.to_string(),
                ProxyBackendConfig {
                    enabled,
                    base_url: url.to_string(),
                    auth_type: "bearer".to_string(),
                    auth_header: "Authorization".to_string(),
                    rate_limit_rpm: 60,
                    timeout_secs: 30,
                    circuit_breaker_enabled: true,
                    fallback_direct: false,
                    allowed_paths: vec![],
                },
            );
        }
        ApiProxyConfig {
            enabled: true,
            require_auth: true,
            backends: map,
        }
    }

    #[test]
    fn test_registry_from_config_filters_disabled() {
        let config = make_config(vec![
            ("linear", true, "https://api.linear.app"),
            ("github", false, "https://api.github.com"),
            ("slack", true, "https://slack.com/api"),
        ]);
        let registry = ApiProxyRegistry::from_config(&config);
        assert_eq!(registry.count(), 2);
        assert!(registry.get("linear").is_some());
        assert!(registry.get("github").is_none());
        assert!(registry.get("slack").is_some());
    }

    #[test]
    fn test_registry_empty_config() {
        let config = ApiProxyConfig::default();
        let registry = ApiProxyRegistry::from_config(&config);
        assert_eq!(registry.count(), 0);
        assert!(registry.get("anything").is_none());
    }

    #[test]
    fn test_registry_list_names() {
        let config = make_config(vec![
            ("linear", true, "https://api.linear.app"),
            ("pushgateway", true, "http://pushgateway:9091"),
        ]);
        let registry = ApiProxyRegistry::from_config(&config);
        let mut names = registry.list_names();
        names.sort();
        assert_eq!(names, vec!["linear", "pushgateway"]);
    }

    #[test]
    fn test_registry_reload() {
        let config1 = make_config(vec![("linear", true, "https://api.linear.app")]);
        let registry = ApiProxyRegistry::from_config(&config1);
        assert_eq!(registry.count(), 1);

        let config2 = make_config(vec![
            ("linear", true, "https://api.linear.app"),
            ("github", true, "https://api.github.com"),
        ]);
        registry.reload(&config2);
        assert_eq!(registry.count(), 2);
        assert!(registry.get("github").is_some());
    }

    #[test]
    fn test_registry_reload_disables_backend() {
        let config1 = make_config(vec![
            ("linear", true, "https://api.linear.app"),
            ("github", true, "https://api.github.com"),
        ]);
        let registry = ApiProxyRegistry::from_config(&config1);
        assert_eq!(registry.count(), 2);

        let config2 = make_config(vec![
            ("linear", true, "https://api.linear.app"),
            ("github", false, "https://api.github.com"),
        ]);
        registry.reload(&config2);
        assert_eq!(registry.count(), 1);
        assert!(registry.get("github").is_none());
    }

    #[test]
    fn test_registered_backend_has_config() {
        let config = make_config(vec![("linear", true, "https://api.linear.app")]);
        let registry = ApiProxyRegistry::from_config(&config);
        let backend = registry.get("linear").unwrap();
        assert_eq!(backend.name, "linear");
        assert_eq!(backend.config.base_url, "https://api.linear.app");
        assert_eq!(backend.config.rate_limit_rpm, 60);
        assert!(backend.config.circuit_breaker_enabled);
    }
}
