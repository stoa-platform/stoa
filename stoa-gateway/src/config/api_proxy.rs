//! API proxy configuration for internal dogfooding (CAB-1722).
//!
//! Routes internal API calls (Linear, GitHub, Slack, Infisical, etc.) through
//! the gateway with OAuth2 auth and credential injection. Each backend is
//! individually toggled via feature flags for incremental rollout.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApiProxyConfig {
    /// Master switch: enable the `/apis/{backend}/*` proxy router.
    /// Env: STOA_API_PROXY__ENABLED
    #[serde(default)]
    pub enabled: bool,

    /// Require OAuth2 authentication for all API proxy requests.
    /// When false, accepts unauthenticated requests (dev mode only).
    /// Env: STOA_API_PROXY__REQUIRE_AUTH
    #[serde(default = "default_api_proxy_require_auth")]
    pub require_auth: bool,

    /// Per-backend configurations, keyed by backend name (e.g., "linear", "github").
    /// Env: STOA_API_PROXY__BACKENDS__<NAME>__<FIELD> (triple level = double-underscore
    /// between each segment: backends, the backend name, and the field).
    #[serde(default)]
    pub backends: HashMap<String, ProxyBackendConfig>,
}

impl Default for ApiProxyConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            require_auth: default_api_proxy_require_auth(),
            backends: HashMap::new(),
        }
    }
}

/// Configuration for a single proxied backend (CAB-1722).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProxyBackendConfig {
    /// Enable this backend (feature flag for incremental rollout).
    #[serde(default)]
    pub enabled: bool,

    /// Base URL for the upstream backend (e.g., "https://api.linear.app").
    pub base_url: String,

    /// Authentication type for the upstream backend.
    /// Uses the same AuthType as the credential store.
    #[serde(default = "default_proxy_backend_auth_type")]
    pub auth_type: String,

    /// Header name for credential injection (e.g., "Authorization", "X-API-Key").
    #[serde(default = "default_proxy_backend_header")]
    pub auth_header: String,

    /// Rate limit in requests per minute (0 = no limit).
    #[serde(default)]
    pub rate_limit_rpm: u32,

    /// Request timeout in seconds.
    #[serde(default = "default_proxy_backend_timeout_secs")]
    pub timeout_secs: u64,

    /// Enable circuit breaker for this backend.
    #[serde(default = "crate::config::defaults::default_true")]
    pub circuit_breaker_enabled: bool,

    /// Enable direct fallback when gateway is down (critical backends only).
    #[serde(default)]
    pub fallback_direct: bool,

    /// Allowed path prefixes (empty = allow all paths).
    /// Security: prevents proxy abuse by restricting accessible paths.
    #[serde(default)]
    pub allowed_paths: Vec<String>,
}

fn default_api_proxy_require_auth() -> bool {
    true
}

fn default_proxy_backend_auth_type() -> String {
    "bearer".to_string()
}

fn default_proxy_backend_header() -> String {
    "Authorization".to_string()
}

fn default_proxy_backend_timeout_secs() -> u64 {
    30
}

#[cfg(test)]
mod tests {
    use super::{ApiProxyConfig, ProxyBackendConfig};

    #[test]
    fn test_api_proxy_backend_deserialization() {
        let json = serde_json::json!({
            "enabled": true,
            "base_url": "https://api.linear.app",
            "auth_type": "bearer",
            "auth_header": "Authorization",
            "rate_limit_rpm": 120,
            "timeout_secs": 15,
            "circuit_breaker_enabled": true,
            "fallback_direct": false,
            "allowed_paths": ["/graphql"]
        });
        let backend: ProxyBackendConfig = serde_json::from_value(json).unwrap();
        assert!(backend.enabled);
        assert_eq!(backend.base_url, "https://api.linear.app");
        assert_eq!(backend.rate_limit_rpm, 120);
        assert_eq!(backend.timeout_secs, 15);
        assert!(backend.circuit_breaker_enabled);
        assert!(!backend.fallback_direct);
        assert_eq!(backend.allowed_paths, vec!["/graphql"]);
    }

    #[test]
    fn test_api_proxy_config_with_backends() {
        let json = serde_json::json!({
            "enabled": true,
            "require_auth": true,
            "backends": {
                "linear": {
                    "enabled": true,
                    "base_url": "https://api.linear.app",
                    "rate_limit_rpm": 120
                },
                "github": {
                    "enabled": false,
                    "base_url": "https://api.github.com",
                    "rate_limit_rpm": 60
                }
            }
        });
        let proxy: ApiProxyConfig = serde_json::from_value(json).unwrap();
        assert!(proxy.enabled);
        assert_eq!(proxy.backends.len(), 2);
        assert!(proxy.backends["linear"].enabled);
        assert!(!proxy.backends["github"].enabled);
        assert_eq!(proxy.backends["linear"].rate_limit_rpm, 120);
    }

    #[test]
    fn test_proxy_backend_defaults() {
        let json = serde_json::json!({
            "base_url": "https://api.example.com"
        });
        let backend: ProxyBackendConfig = serde_json::from_value(json).unwrap();
        assert!(!backend.enabled);
        assert_eq!(backend.auth_type, "bearer");
        assert_eq!(backend.auth_header, "Authorization");
        assert_eq!(backend.rate_limit_rpm, 0);
        assert_eq!(backend.timeout_secs, 30);
        assert!(backend.circuit_breaker_enabled);
        assert!(!backend.fallback_direct);
        assert!(backend.allowed_paths.is_empty());
    }
}
