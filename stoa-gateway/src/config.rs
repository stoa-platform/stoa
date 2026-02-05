//! Configuration with Figment
//!
//! Supports:
//! - config.yaml file (optional)
//! - Environment variable overrides (STOA_ prefix)
//! - Backward compatible with existing envy-based env vars

use figment::{
    providers::{Env, Format, Serialized, Yaml},
    Figment,
};
use serde::{Deserialize, Serialize};
use std::path::Path;
use tracing::info;

/// Gateway configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {
    // === Server ===
    #[serde(default = "default_port")]
    pub port: u16,
    
    #[serde(default = "default_host")]
    pub host: String,

    // === Authentication ===
    #[serde(default)]
    pub jwt_secret: Option<String>,
    
    #[serde(default)]
    pub jwt_issuer: Option<String>,
    
    #[serde(default)]
    pub keycloak_url: Option<String>,

    #[serde(default)]
    pub keycloak_realm: Option<String>,

    #[serde(default)]
    pub keycloak_client_id: Option<String>,

    #[serde(default)]
    pub keycloak_client_secret: Option<String>,

    /// Keycloak admin password for DCR public client patch (optional).
    /// Env: STOA_KEYCLOAK_ADMIN_PASSWORD
    #[serde(default)]
    pub keycloak_admin_password: Option<String>,

    // === Gateway ===
    /// Public-facing URL of this gateway (for OAuth discovery endpoints).
    /// Env: STOA_GATEWAY_EXTERNAL_URL. Default: http://localhost:8080
    #[serde(default = "default_gateway_external_url")]
    pub gateway_external_url: Option<String>,

    // === Control Plane ===
    #[serde(default)]
    pub control_plane_url: Option<String>,
    
    #[serde(default)]
    pub control_plane_api_key: Option<String>,

    // === Admin API ===
    /// Bearer token for the admin API (Control Plane → gateway calls).
    /// Env: STOA_ADMIN_API_TOKEN. If not set, admin API returns 403.
    #[serde(default)]
    pub admin_api_token: Option<String>,

    // === GitLab (UAC Sync) ===
    #[serde(default)]
    pub gitlab_url: Option<String>,
    
    #[serde(default)]
    pub gitlab_api_url: Option<String>,
    
    #[serde(default)]
    pub gitlab_token: Option<String>,
    
    #[serde(default)]
    pub gitlab_project_id: Option<String>,

    // === Rate Limiting ===
    #[serde(default)]
    pub rate_limit_default: Option<usize>,
    
    #[serde(default)]
    pub rate_limit_window_seconds: Option<u64>,

    // === MCP ===
    #[serde(default = "default_session_ttl")]
    pub mcp_session_ttl_minutes: i64,

    // === Observability ===
    #[serde(default)]
    pub log_level: Option<String>,
    
    #[serde(default)]
    pub log_format: Option<String>,
    
    #[serde(default)]
    pub otel_endpoint: Option<String>,
}

fn default_port() -> u16 {
    8080
}

fn default_host() -> String {
    "0.0.0.0".to_string()
}

fn default_session_ttl() -> i64 {
    30
}

fn default_gateway_external_url() -> Option<String> {
    Some("http://localhost:8080".to_string())
}

impl Default for Config {
    fn default() -> Self {
        Self {
            port: default_port(),
            host: default_host(),
            jwt_secret: None,
            jwt_issuer: None,
            keycloak_url: None,
            keycloak_realm: None,
            keycloak_client_id: None,
            keycloak_client_secret: None,
            keycloak_admin_password: None,
            gateway_external_url: default_gateway_external_url(),
            control_plane_url: None,
            control_plane_api_key: None,
            admin_api_token: None,
            gitlab_url: None,
            gitlab_api_url: None,
            gitlab_token: None,
            gitlab_project_id: None,
            rate_limit_default: Some(1000),
            rate_limit_window_seconds: Some(60),
            mcp_session_ttl_minutes: default_session_ttl(),
            log_level: Some("info".to_string()),
            log_format: Some("json".to_string()),
            otel_endpoint: None,
        }
    }
}

impl Config {
    /// Load configuration from file and environment
    pub fn load() -> Result<Self, figment::Error> {
        let mut figment = Figment::new()
            // Start with defaults
            .merge(Serialized::defaults(Config::default()));

        // Try config.yaml if exists
        let config_paths = ["config.yaml", "config.yml", "/etc/stoa/config.yaml"];
        for path in config_paths {
            if Path::new(path).exists() {
                info!(path = path, "Loading config from file");
                figment = figment.merge(Yaml::file(path));
                break;
            }
        }

        // Environment variables override (STOA_ prefix)
        // e.g., STOA_PORT=9090, STOA_CONTROL_PLANE_URL=http://...
        // No .split("_") — field names use underscores (control_plane_url, not nested)
        figment = figment.merge(Env::prefixed("STOA_"));

        // Legacy env vars (backward compat with envy)
        figment = figment
            .merge(Env::raw().only(&[
                "PORT",
                "HOST",
                "JWT_SECRET",
                "KEYCLOAK_URL",
                "KEYCLOAK_REALM",
                "GITLAB_URL",
                "GITLAB_TOKEN",
                "GITLAB_PROJECT_ID",
            ]));

        let config: Config = figment.extract()?;
        
        info!(
            port = config.port,
            host = %config.host,
            control_plane = config.control_plane_url.as_deref().unwrap_or("not set"),
            "Configuration loaded"
        );

        Ok(config)
    }

    /// Validate configuration
    pub fn validate(&self) -> Result<(), ConfigError> {
        // Warn about missing recommended config
        if self.control_plane_url.is_none() {
            tracing::warn!("CONTROL_PLANE_URL not set - some features will be disabled");
        }

        if self.jwt_secret.is_none() && self.keycloak_url.is_none() {
            tracing::warn!("No JWT_SECRET or KEYCLOAK_URL - auth will be limited");
        }

        Ok(())
    }
}

#[derive(Debug, thiserror::Error)]
pub enum ConfigError {
    #[error("Missing required config: {0}")]
    Missing(String),
    
    #[error("Invalid config value: {0}")]
    Invalid(String),
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_config() {
        let config = Config::default();
        assert_eq!(config.port, 8080);
        assert_eq!(config.host, "0.0.0.0");
        assert_eq!(config.mcp_session_ttl_minutes, 30);
    }

    #[test]
    fn test_load_with_defaults() {
        // This should work even without any config file or env vars
        std::env::remove_var("STOA_PORT");
        let config = Config::load().expect("Should load defaults");
        assert_eq!(config.port, 8080);
    }
}
