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
                        requests_total: Some(crate::metrics::get_requests_total()),
                        error_rate: Some(crate::metrics::get_error_rate()),
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
    pub async fn gateway_id(&self) -> Option<Uuid> {
        *self.gateway_id.read().await
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::Config;
    use crate::mode::GatewayMode;
    use wiremock::matchers::{header, method, path};
    use wiremock::{Mock, MockServer, ResponseTemplate};

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
    fn test_registration_payload_with_tenant() {
        let payload = RegistrationPayload {
            hostname: "gw-1".to_string(),
            mode: "sidecar".to_string(),
            version: "0.1.0".to_string(),
            environment: "staging".to_string(),
            capabilities: vec!["rest".to_string()],
            admin_url: "http://gw-1:8081".to_string(),
            tenant_id: Some("acme".to_string()),
        };

        let json = serde_json::to_string(&payload).unwrap();
        assert!(json.contains("tenant_id"));
        assert!(json.contains("acme"));
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
    fn test_heartbeat_payload_full() {
        let payload = HeartbeatPayload {
            uptime_seconds: 7200,
            routes_count: 5,
            policies_count: 3,
            requests_total: Some(5000),
            error_rate: Some(0.02),
        };

        let json = serde_json::to_string(&payload).unwrap();
        assert!(json.contains("error_rate"));
        assert!(json.contains("0.02"));
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

    #[test]
    fn test_registration_response_deserialize() {
        let json = r#"{
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "name": "gw-edge-dev",
            "status": "active"
        }"#;

        let resp: RegistrationResponse = serde_json::from_str(json).unwrap();
        assert_eq!(resp.name, "gw-edge-dev");
        assert_eq!(resp.status, "active");
    }

    #[test]
    fn test_registration_error_display() {
        let e = RegistrationError::InvalidApiKey;
        assert_eq!(e.to_string(), "Invalid API key");

        let e = RegistrationError::Unreachable("timeout".to_string());
        assert!(e.to_string().contains("timeout"));

        let e = RegistrationError::Rejected("duplicate".to_string());
        assert!(e.to_string().contains("duplicate"));

        let e = RegistrationError::HostnameError("no hostname".to_string());
        assert!(e.to_string().contains("no hostname"));
    }

    #[test]
    fn test_detect_capabilities_edge_mcp() {
        let registrar = GatewayRegistrar::new("http://cp".to_string(), "key".to_string());
        let config = Config {
            gateway_mode: GatewayMode::EdgeMcp,
            policy_enabled: true,
            ..Config::default()
        };

        let caps = registrar.detect_capabilities(&config);
        assert!(caps.contains(&"rest".to_string()));
        assert!(caps.contains(&"oidc".to_string()));
        assert!(caps.contains(&"metering".to_string()));
        assert!(caps.contains(&"mcp".to_string()));
        assert!(caps.contains(&"sse".to_string()));
        assert!(caps.contains(&"policy".to_string()));
    }

    #[test]
    fn test_detect_capabilities_sidecar() {
        let registrar = GatewayRegistrar::new("http://cp".to_string(), "key".to_string());
        let config = Config {
            gateway_mode: GatewayMode::Sidecar,
            policy_enabled: false,
            ..Config::default()
        };

        let caps = registrar.detect_capabilities(&config);
        assert!(caps.contains(&"ext_authz".to_string()));
        assert!(!caps.contains(&"mcp".to_string()));
        assert!(!caps.contains(&"policy".to_string()));
    }

    #[test]
    fn test_detect_capabilities_proxy_with_rate_limit() {
        let registrar = GatewayRegistrar::new("http://cp".to_string(), "key".to_string());
        let config = Config {
            gateway_mode: GatewayMode::Proxy,
            rate_limit_default: Some(1000),
            policy_enabled: false,
            ..Config::default()
        };

        let caps = registrar.detect_capabilities(&config);
        assert!(caps.contains(&"rate_limiting".to_string()));
    }

    #[test]
    fn test_detect_capabilities_shadow() {
        let registrar = GatewayRegistrar::new("http://cp".to_string(), "key".to_string());
        let config = Config {
            gateway_mode: GatewayMode::Shadow,
            policy_enabled: false,
            ..Config::default()
        };

        let caps = registrar.detect_capabilities(&config);
        assert!(caps.contains(&"traffic_capture".to_string()));
        assert!(!caps.contains(&"mcp".to_string()));
    }

    #[test]
    fn test_get_hostname() {
        let registrar = GatewayRegistrar::new("http://cp".to_string(), "key".to_string());
        let hostname = registrar.get_hostname();
        assert!(hostname.is_ok());
        assert!(!hostname.unwrap().is_empty());
    }

    #[tokio::test]
    async fn test_gateway_id_initially_none() {
        let registrar = GatewayRegistrar::new("http://cp".to_string(), "key".to_string());
        assert!(registrar.gateway_id().await.is_none());
    }

    #[tokio::test]
    async fn test_register_success() {
        let mock_server = MockServer::start().await;

        let gw_id = Uuid::new_v4();
        Mock::given(method("POST"))
            .and(path("/v1/internal/gateways/register"))
            .and(header("X-Gateway-Key", "test-key"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "id": gw_id.to_string(),
                "name": "gw-edge-dev",
                "status": "active"
            })))
            .mount(&mock_server)
            .await;

        let registrar = GatewayRegistrar::new(mock_server.uri(), "test-key".to_string());
        let config = Config::default();

        let result = registrar.register(&config).await;
        assert!(result.is_ok());
        assert_eq!(result.unwrap(), gw_id);
        assert_eq!(registrar.gateway_id().await, Some(gw_id));
    }

    #[tokio::test]
    async fn test_register_unauthorized() {
        let mock_server = MockServer::start().await;

        Mock::given(method("POST"))
            .and(path("/v1/internal/gateways/register"))
            .respond_with(ResponseTemplate::new(401))
            .mount(&mock_server)
            .await;

        let registrar = GatewayRegistrar::new(mock_server.uri(), "bad-key".to_string());
        let config = Config::default();

        let result = registrar.register(&config).await;
        assert!(result.is_err());
        assert!(matches!(
            result.unwrap_err(),
            RegistrationError::InvalidApiKey
        ));
    }

    #[tokio::test]
    async fn test_register_forbidden() {
        let mock_server = MockServer::start().await;

        Mock::given(method("POST"))
            .and(path("/v1/internal/gateways/register"))
            .respond_with(ResponseTemplate::new(403))
            .mount(&mock_server)
            .await;

        let registrar = GatewayRegistrar::new(mock_server.uri(), "key".to_string());
        let config = Config::default();

        let result = registrar.register(&config).await;
        assert!(matches!(
            result.unwrap_err(),
            RegistrationError::InvalidApiKey
        ));
    }

    #[tokio::test]
    async fn test_register_server_error() {
        let mock_server = MockServer::start().await;

        Mock::given(method("POST"))
            .and(path("/v1/internal/gateways/register"))
            .respond_with(ResponseTemplate::new(500).set_body_string("internal error"))
            .mount(&mock_server)
            .await;

        let registrar = GatewayRegistrar::new(mock_server.uri(), "key".to_string());
        let config = Config::default();

        let result = registrar.register(&config).await;
        assert!(result.is_err());
        assert!(matches!(
            result.unwrap_err(),
            RegistrationError::Rejected(_)
        ));
    }

    #[tokio::test]
    async fn test_send_heartbeat_success() {
        let mock_server = MockServer::start().await;
        let gw_id = Uuid::new_v4();

        Mock::given(method("POST"))
            .and(path(format!("/v1/internal/gateways/{}/heartbeat", gw_id)))
            .and(header("X-Gateway-Key", "key"))
            .respond_with(ResponseTemplate::new(200))
            .mount(&mock_server)
            .await;

        let registrar = GatewayRegistrar::new(mock_server.uri(), "key".to_string());

        let payload = HeartbeatPayload {
            uptime_seconds: 60,
            routes_count: 5,
            policies_count: 2,
            requests_total: None,
            error_rate: None,
        };

        let result = registrar.send_heartbeat(gw_id, payload).await;
        assert!(result.is_ok());
    }

    #[tokio::test]
    async fn test_send_heartbeat_failure() {
        let mock_server = MockServer::start().await;
        let gw_id = Uuid::new_v4();

        Mock::given(method("POST"))
            .and(path(format!("/v1/internal/gateways/{}/heartbeat", gw_id)))
            .respond_with(ResponseTemplate::new(503))
            .mount(&mock_server)
            .await;

        let registrar = GatewayRegistrar::new(mock_server.uri(), "key".to_string());

        let payload = HeartbeatPayload {
            uptime_seconds: 60,
            routes_count: 0,
            policies_count: 0,
            requests_total: None,
            error_rate: None,
        };

        let result = registrar.send_heartbeat(gw_id, payload).await;
        assert!(result.is_err());
    }
}
