//! Gateway Auto-Registration (ADR-028)
//!
//! Implements the "Apple ecosystem" experience where gateways self-register
//! with the Control Plane at startup and maintain presence via heartbeat.
//!
//! # Example
//!
//! ```ignore
//! let registrar = GatewayRegistrar::new(
//!     "https://api.gostoa.dev".to_string(),
//!     "gw_secret_key".to_string(),
//! );
//!
//! // Register at startup
//! let gateway_id = registrar.register(&config).await?;
//!
//! // Start background heartbeat (every 30s)
//! registrar.start_heartbeat(state.clone());
//! ```

use serde::{Deserialize, Serialize};
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::RwLock;
use tracing::{debug, error, info, warn};
use uuid::Uuid;

use crate::config::Config;
use crate::state::AppState;

/// Registration payload sent to Control Plane
#[derive(Debug, Clone, Serialize)]
pub struct RegistrationPayload {
    /// Hostname of this gateway instance
    pub hostname: String,

    /// Gateway mode (edge_mcp, sidecar, proxy, shadow)
    pub mode: String,

    /// Gateway version
    pub version: String,

    /// Environment (dev, staging, prod)
    pub environment: String,

    /// Declared capabilities
    pub capabilities: Vec<String>,

    /// Admin API URL for Control Plane to call back
    pub admin_url: String,

    /// Optional tenant restriction
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tenant_id: Option<String>,
}

/// Heartbeat payload sent every 30 seconds
#[derive(Debug, Clone, Serialize)]
pub struct HeartbeatPayload {
    /// Uptime in seconds
    pub uptime_seconds: u64,

    /// Number of registered routes
    pub routes_count: usize,

    /// Number of registered policies
    pub policies_count: usize,

    /// Total requests processed (optional)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub requests_total: Option<u64>,

    /// Current error rate (optional)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error_rate: Option<f64>,
}

/// Response from Control Plane registration
#[derive(Debug, Clone, Deserialize)]
#[allow(dead_code)] // Fields used for JSON deserialization
pub struct RegistrationResponse {
    /// Assigned gateway ID
    pub id: Uuid,

    /// Gateway name (derived from hostname-mode-env)
    pub name: String,

    /// Current status
    pub status: String,
}

/// Error types for registration operations
#[derive(Debug, thiserror::Error)]
#[allow(dead_code)] // Variants reserved for future use
pub enum RegistrationError {
    #[error("HTTP request failed: {0}")]
    HttpError(#[from] reqwest::Error),

    #[error("Invalid API key")]
    InvalidApiKey,

    #[error("Control Plane unreachable: {0}")]
    Unreachable(String),

    #[error("Registration rejected: {0}")]
    Rejected(String),

    #[error("Hostname detection failed: {0}")]
    HostnameError(String),
}

/// Gateway registrar for auto-registration with Control Plane
pub struct GatewayRegistrar {
    /// HTTP client for Control Plane API
    client: reqwest::Client,

    /// Control Plane base URL
    cp_url: String,

    /// API key for authentication
    api_key: String,

    /// Assigned gateway ID (after registration)
    gateway_id: RwLock<Option<Uuid>>,

    /// Start time for uptime calculation
    start_time: std::time::Instant,
}

impl GatewayRegistrar {
    /// Create a new registrar
    pub fn new(cp_url: String, api_key: String) -> Self {
        Self {
            client: reqwest::Client::builder()
                .timeout(Duration::from_secs(30))
                .build()
                .expect("Failed to create HTTP client"),
            cp_url,
            api_key,
            gateway_id: RwLock::new(None),
            start_time: std::time::Instant::now(),
        }
    }

    /// Register this gateway with the Control Plane
    ///
    /// Returns the assigned gateway ID on success.
    pub async fn register(&self, config: &Config) -> Result<Uuid, RegistrationError> {
        let hostname = self.get_hostname()?;
        let mode = config.gateway_mode.to_string();
        let capabilities = self.detect_capabilities(config);

        let payload = RegistrationPayload {
            hostname: hostname.clone(),
            mode: mode.clone(),
            version: env!("CARGO_PKG_VERSION").to_string(),
            environment: config.environment.clone(),
            capabilities,
            admin_url: format!("http://{}:{}", hostname, config.port),
            tenant_id: None, // Platform-wide gateway
        };

        info!(
            hostname = %payload.hostname,
            mode = %payload.mode,
            environment = %payload.environment,
            "Registering gateway with Control Plane"
        );

        let url = format!("{}/v1/internal/gateways/register", self.cp_url);

        let response = self
            .client
            .post(&url)
            .header("X-Gateway-Key", &self.api_key)
            .header("Content-Type", "application/json")
            .json(&payload)
            .send()
            .await?;

        match response.status() {
            status if status.is_success() => {
                let reg_response: RegistrationResponse = response.json().await?;
                info!(
                    gateway_id = %reg_response.id,
                    name = %reg_response.name,
                    "Gateway registered successfully"
                );

                // Store the gateway ID
                *self.gateway_id.write().await = Some(reg_response.id);

                Ok(reg_response.id)
            }
            reqwest::StatusCode::UNAUTHORIZED => {
                error!("Invalid API key for gateway registration");
                Err(RegistrationError::InvalidApiKey)
            }
            reqwest::StatusCode::FORBIDDEN => {
                error!("Gateway registration forbidden - check API key configuration");
                Err(RegistrationError::InvalidApiKey)
            }
            status => {
                let body = response.text().await.unwrap_or_default();
                error!(
                    status = %status,
                    body = %body,
                    "Gateway registration failed"
                );
                Err(RegistrationError::Rejected(format!(
                    "Status {}: {}",
                    status, body
                )))
            }
        }
    }

    /// Start background heartbeat loop
    ///
    /// Spawns a tokio task that sends heartbeats at the configured interval.
    pub fn start_heartbeat(self: Arc<Self>, state: Arc<AppState>, interval_secs: u64) {
        let registrar = self.clone();

        tokio::spawn(async move {
            let mut interval = tokio::time::interval(Duration::from_secs(interval_secs));

            loop {
                interval.tick().await;

                let gateway_id = *registrar.gateway_id.read().await;

                if let Some(id) = gateway_id {
                    let payload = HeartbeatPayload {
                        uptime_seconds: registrar.start_time.elapsed().as_secs(),
                        routes_count: state.route_registry.count(),
                        policies_count: state.policy_registry.count(),
                        requests_total: None, // TODO: Wire up metrics
                        error_rate: None,     // TODO: Wire up metrics
                    };

                    if let Err(e) = registrar.send_heartbeat(id, payload).await {
                        warn!(error = %e, "Failed to send heartbeat");
                    } else {
                        debug!(gateway_id = %id, "Heartbeat sent");
                    }
                }
            }
        });
    }

    /// Send a single heartbeat
    async fn send_heartbeat(
        &self,
        gateway_id: Uuid,
        payload: HeartbeatPayload,
    ) -> Result<(), RegistrationError> {
        let url = format!(
            "{}/v1/internal/gateways/{}/heartbeat",
            self.cp_url, gateway_id
        );

        let response = self
            .client
            .post(&url)
            .header("X-Gateway-Key", &self.api_key)
            .header("Content-Type", "application/json")
            .json(&payload)
            .send()
            .await?;

        if response.status().is_success() {
            Ok(())
        } else {
            Err(RegistrationError::Rejected(format!(
                "Heartbeat failed: {}",
                response.status()
            )))
        }
    }

    /// Get the hostname of this machine
    fn get_hostname(&self) -> Result<String, RegistrationError> {
        hostname::get()
            .map(|h| h.to_string_lossy().to_string())
            .map_err(|e| RegistrationError::HostnameError(e.to_string()))
    }

    /// Detect capabilities based on configuration
    fn detect_capabilities(&self, config: &Config) -> Vec<String> {
        let mut caps = vec![
            "rest".to_string(),     // Always support REST
            "oidc".to_string(),     // OIDC enforcement
            "metering".to_string(), // Usage metering
        ];

        // MCP support depends on mode
        match config.gateway_mode {
            crate::mode::GatewayMode::EdgeMcp => {
                caps.push("mcp".to_string());
                caps.push("sse".to_string());
            }
            crate::mode::GatewayMode::Sidecar => {
                caps.push("ext_authz".to_string());
            }
            crate::mode::GatewayMode::Proxy => {
                caps.push("rate_limiting".to_string());
            }
            crate::mode::GatewayMode::Shadow => {
                caps.push("traffic_capture".to_string());
            }
        }

        // Rate limiting if configured
        if config.rate_limit_default.is_some() && !caps.contains(&"rate_limiting".to_string()) {
            caps.push("rate_limiting".to_string());
        }

        // Policy engine
        if config.policy_enabled {
            caps.push("policy".to_string());
        }

        caps
    }

    /// Get the registered gateway ID (if any)
    #[allow(dead_code)] // Public API for future use
    pub async fn gateway_id(&self) -> Option<Uuid> {
        *self.gateway_id.read().await
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_registration_payload_serialization() {
        let payload = RegistrationPayload {
            hostname: "gateway-abc123".to_string(),
            mode: "edge_mcp".to_string(),
            version: "0.1.0".to_string(),
            environment: "dev".to_string(),
            capabilities: vec!["rest".to_string(), "mcp".to_string()],
            admin_url: "http://gateway-abc123:8080".to_string(),
            tenant_id: None,
        };

        let json = serde_json::to_string(&payload).expect("Should serialize");
        assert!(json.contains("gateway-abc123"));
        assert!(json.contains("edge_mcp"));
        assert!(!json.contains("tenant_id")); // None should be skipped
    }

    #[test]
    fn test_heartbeat_payload_serialization() {
        let payload = HeartbeatPayload {
            uptime_seconds: 3600,
            routes_count: 10,
            policies_count: 5,
            requests_total: Some(1000),
            error_rate: None,
        };

        let json = serde_json::to_string(&payload).expect("Should serialize");
        assert!(json.contains("3600"));
        assert!(json.contains("1000"));
        assert!(!json.contains("error_rate")); // None should be skipped
    }

    #[test]
    fn test_registrar_creation() {
        let registrar = GatewayRegistrar::new(
            "https://api.example.com".to_string(),
            "test-key".to_string(),
        );

        assert_eq!(registrar.cp_url, "https://api.example.com");
        assert_eq!(registrar.api_key, "test-key");
    }
}
