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

use crate::mode::GatewayMode;

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

    // === Policy Engine (Phase 2 OPA) ===
    /// Path to Rego policy file (e.g., /etc/stoa/policies/default.rego)
    /// Env: STOA_POLICY_PATH
    #[serde(default)]
    pub policy_path: Option<String>,

    /// Enable/disable policy enforcement (default: true)
    /// Env: STOA_POLICY_ENABLED
    #[serde(default = "default_policy_enabled")]
    pub policy_enabled: bool,

    // === Observability ===
    #[serde(default)]
    pub log_level: Option<String>,

    #[serde(default)]
    pub log_format: Option<String>,

    #[serde(default)]
    pub otel_endpoint: Option<String>,

    // === Gateway Mode (Phase 8) ===
    /// Gateway deployment mode: edge-mcp, sidecar, proxy, shadow
    /// Env: STOA_GATEWAY_MODE (default: edge-mcp)
    #[serde(default)]
    pub gateway_mode: GatewayMode,

    // === Governance (ADR-012) ===
    /// Enable anti-zombie agent detection
    /// Env: STOA_ZOMBIE_DETECTION_ENABLED (default: true)
    #[serde(default = "default_zombie_detection")]
    pub zombie_detection_enabled: bool,

    /// Session TTL for agent sessions in seconds (default: 600 = 10 min per ADR-012)
    /// Env: STOA_AGENT_SESSION_TTL_SECS
    #[serde(default = "default_agent_session_ttl")]
    pub agent_session_ttl_secs: u64,

    /// Attestation interval (requests between attestations)
    /// Env: STOA_ATTESTATION_INTERVAL
    #[serde(default = "default_attestation_interval")]
    pub attestation_interval: u64,

    // === Shadow Mode ===
    /// Traffic capture source for shadow mode
    /// Env: STOA_SHADOW_CAPTURE_SOURCE (inline, envoy-tap, port-mirror, kafka)
    #[serde(default)]
    pub shadow_capture_source: Option<String>,

    /// Minimum samples before generating UAC
    /// Env: STOA_SHADOW_MIN_SAMPLES
    #[serde(default = "default_shadow_min_samples")]
    pub shadow_min_samples: usize,

    /// GitLab project for UAC MR submission
    /// Env: STOA_SHADOW_GITLAB_PROJECT
    #[serde(default)]
    pub shadow_gitlab_project: Option<String>,

    // === Auto-Registration (ADR-028) ===
    /// Environment identifier for registration (dev, staging, prod)
    /// Env: STOA_ENVIRONMENT
    #[serde(default = "default_environment")]
    pub environment: String,

    /// Enable auto-registration with Control Plane on startup
    /// Env: STOA_AUTO_REGISTER
    #[serde(default = "default_auto_register")]
    pub auto_register: bool,

    /// Heartbeat interval in seconds (default: 30)
    /// Env: STOA_HEARTBEAT_INTERVAL_SECS
    #[serde(default = "default_heartbeat_interval")]
    pub heartbeat_interval_secs: u64,

    // === Native Tools (Phase 1) ===
    /// Enable native tool implementations (default: true)
    /// Set STOA_NATIVE_TOOLS_ENABLED=false to fallback to proxy mode
    /// Env: STOA_NATIVE_TOOLS_ENABLED
    #[serde(default = "default_native_tools_enabled")]
    pub native_tools_enabled: bool,

    // === Kafka Metering (Phase 3: CAB-1105) ===
    /// Enable Kafka metering (default: false — explicit opt-in)
    /// Env: STOA_KAFKA_ENABLED
    #[serde(default)]
    pub kafka_enabled: bool,

    /// Kafka broker addresses (comma-separated)
    /// Env: STOA_KAFKA_BROKERS
    #[serde(default = "default_kafka_brokers")]
    pub kafka_brokers: String,

    /// Kafka topic for metering events
    /// Env: STOA_KAFKA_METERING_TOPIC
    #[serde(default = "default_kafka_metering_topic")]
    pub kafka_metering_topic: String,

    /// Kafka topic for error snapshots
    /// Env: STOA_KAFKA_ERRORS_TOPIC
    #[serde(default = "default_kafka_errors_topic")]
    pub kafka_errors_topic: String,

    // === K8s CRD Watcher (Phase 7: CAB-1105) ===
    /// Enable K8s CRD watching for dynamic tool registration
    /// Env: STOA_K8S_ENABLED (default: false — explicit opt-in)
    #[serde(default)]
    pub k8s_enabled: bool,

    // === Per-Upstream Circuit Breaker (CAB-362) ===
    /// Failure threshold before opening circuit (default: 5)
    /// Env: STOA_CB_FAILURE_THRESHOLD
    #[serde(default = "default_cb_failure_threshold")]
    pub cb_failure_threshold: u32,

    /// Reset timeout in seconds before trying half-open (default: 30)
    /// Env: STOA_CB_RESET_TIMEOUT_SECS
    #[serde(default = "default_cb_reset_timeout_secs")]
    pub cb_reset_timeout_secs: u64,

    /// Successes needed in half-open to close circuit (default: 2)
    /// Env: STOA_CB_SUCCESS_THRESHOLD
    #[serde(default = "default_cb_success_threshold")]
    pub cb_success_threshold: u32,
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

fn default_policy_enabled() -> bool {
    true
}

fn default_zombie_detection() -> bool {
    true
}

fn default_agent_session_ttl() -> u64 {
    600 // 10 minutes per ADR-012
}

fn default_attestation_interval() -> u64 {
    100 // Require attestation every 100 requests
}

fn default_shadow_min_samples() -> usize {
    10 // Minimum samples before pattern is considered stable
}

fn default_environment() -> String {
    "dev".to_string()
}

fn default_auto_register() -> bool {
    true // Auto-register when control_plane_url is set
}

fn default_heartbeat_interval() -> u64 {
    30 // 30 seconds per ADR-028
}

fn default_native_tools_enabled() -> bool {
    true // Phase 1: native tools call CP API directly
}

fn default_kafka_brokers() -> String {
    "redpanda:9092".to_string()
}

fn default_kafka_metering_topic() -> String {
    "stoa.metering".to_string()
}

fn default_kafka_errors_topic() -> String {
    "stoa.errors".to_string()
}

fn default_cb_failure_threshold() -> u32 {
    5
}

fn default_cb_reset_timeout_secs() -> u64 {
    30
}

fn default_cb_success_threshold() -> u32 {
    2
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
            policy_path: None,
            policy_enabled: default_policy_enabled(),
            log_level: Some("info".to_string()),
            log_format: Some("json".to_string()),
            otel_endpoint: None,
            gateway_mode: GatewayMode::default(),
            zombie_detection_enabled: default_zombie_detection(),
            agent_session_ttl_secs: default_agent_session_ttl(),
            attestation_interval: default_attestation_interval(),
            shadow_capture_source: None,
            shadow_min_samples: default_shadow_min_samples(),
            shadow_gitlab_project: None,
            environment: default_environment(),
            auto_register: default_auto_register(),
            heartbeat_interval_secs: default_heartbeat_interval(),
            native_tools_enabled: default_native_tools_enabled(),
            kafka_enabled: false,
            kafka_brokers: default_kafka_brokers(),
            kafka_metering_topic: default_kafka_metering_topic(),
            kafka_errors_topic: default_kafka_errors_topic(),
            k8s_enabled: false,
            cb_failure_threshold: default_cb_failure_threshold(),
            cb_reset_timeout_secs: default_cb_reset_timeout_secs(),
            cb_success_threshold: default_cb_success_threshold(),
        }
    }
}

impl Config {
    /// Load configuration from file and environment
    #[allow(clippy::result_large_err)]
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
        figment = figment.merge(Env::raw().only(&[
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
#[allow(dead_code)]
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
