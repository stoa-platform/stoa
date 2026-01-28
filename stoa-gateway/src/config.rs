// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
use serde::Deserialize;

/// Configuration loaded from environment variables.
///
/// All configuration is externalized to support 12-factor app deployment.
#[derive(Debug, Deserialize, Clone)]
pub struct Config {
    /// Server host (default: 0.0.0.0)
    #[serde(default = "default_host")]
    pub host: String,

    /// Server port (default: 8080)
    #[serde(default = "default_port")]
    pub port: u16,

    /// webMethods gateway URL for proxying requests
    #[serde(default = "default_webmethods_url")]
    pub webmethods_url: String,

    /// Health check interval in seconds (default: 5)
    #[serde(default = "default_health_check_interval")]
    pub webmethods_health_check_interval_secs: u64,

    /// Health check timeout in seconds (default: 2)
    #[serde(default = "default_health_check_timeout")]
    pub webmethods_health_check_timeout_secs: u64,

    /// Log level (default: info)
    #[serde(default = "default_log_level")]
    pub log_level: String,

    /// Log format: "json" or "pretty" (default: json)
    #[serde(default = "default_log_format")]
    pub log_format: String,

    /// Shadow mode enabled (P1 feature, default: false)
    #[serde(default)]
    pub shadow_mode_enabled: bool,

    /// Shadow mode timeout in seconds (default: 5)
    #[serde(default = "default_shadow_timeout")]
    pub shadow_timeout_secs: u64,
}

fn default_host() -> String {
    "0.0.0.0".to_string()
}

fn default_port() -> u16 {
    8080
}

fn default_webmethods_url() -> String {
    "https://gateway.gostoa.dev".to_string()
}

fn default_health_check_interval() -> u64 {
    5
}

fn default_health_check_timeout() -> u64 {
    2
}

fn default_log_level() -> String {
    "info".to_string()
}

fn default_log_format() -> String {
    "json".to_string()
}

fn default_shadow_timeout() -> u64 {
    5
}

impl Config {
    /// Load configuration from environment variables.
    ///
    /// Environment variables are uppercase with underscore separators.
    /// Example: `WEBMETHODS_URL`, `LOG_LEVEL`, etc.
    pub fn from_env() -> Result<Self, envy::Error> {
        envy::from_env()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_config() {
        // Clear any existing env vars that might interfere
        std::env::remove_var("HOST");
        std::env::remove_var("PORT");
        std::env::remove_var("WEBMETHODS_URL");

        let config = Config::from_env().expect("Failed to load config");

        assert_eq!(config.host, "0.0.0.0");
        assert_eq!(config.port, 8080);
        assert_eq!(config.webmethods_health_check_interval_secs, 5);
        assert!(!config.shadow_mode_enabled);
    }
}
