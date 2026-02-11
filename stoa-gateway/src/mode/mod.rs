//! Gateway Mode Selection Module
//!
//! STOA Gateway supports four deployment modes under a unified architecture (ADR-024):
//!
//! ```text
//! ┌─────────────────────────────────────────────────────────────────────────┐
//! │                         STOA Gateway Binary                             │
//! ├─────────────┬─────────────┬─────────────┬─────────────────────────────┤
//! │  edge-mcp   │   sidecar   │    proxy    │          shadow             │
//! │  (current)  │  (planned)  │  (planned)  │         (planned)           │
//! ├─────────────┼─────────────┼─────────────┼─────────────────────────────┤
//! │ MCP SSE     │ Policy gate │ Full proxy  │ Traffic capture             │
//! │ Tool exec   │ Allow/deny  │ Transform   │ UAC generation              │
//! │ OAuth 2.1   │ Metering    │ Rate limit  │ Pattern analysis            │
//! └─────────────┴─────────────┴─────────────┴─────────────────────────────┘
//! ```
//!
//! # Mode Selection
//!
//! Set via `STOA_MODE` environment variable:
//! - `edge-mcp` (default): Full MCP protocol, SSE transport, tool execution
//! - `sidecar`: Behind Kong/Envoy/Apigee, policy enforcement only
//! - `proxy`: Inline proxy with request/response transformation
//! - `shadow`: Passive traffic capture, UAC auto-generation
//!
//! # Architecture Notes
//!
//! All modes share:
//! - OPA policy engine
//! - Kafka metering
//! - OpenTelemetry tracing
//! - Configuration loading
//!
//! Mode-specific middleware layers are activated based on the selected mode.

#![allow(dead_code)] // Phase 8 methods will be wired incrementally

pub mod proxy;
pub mod shadow;
pub mod sidecar;

use serde::{Deserialize, Serialize};
use std::fmt;
use std::str::FromStr;
use thiserror::Error;

/// Gateway deployment modes (ADR-024)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, Default)]
#[serde(rename_all = "kebab-case")]
pub enum GatewayMode {
    /// MCP protocol, SSE transport, tool execution (current production mode)
    #[default]
    EdgeMcp,

    /// Sidecar deployment behind existing gateway (Kong, Envoy, Apigee)
    /// - Receives pre-authenticated requests
    /// - Applies OPA policies
    /// - Returns allow/deny decisions
    /// - No MCP protocol in this mode
    Sidecar,

    /// Full inline proxy mode
    /// - Request/response transformation
    /// - Rate limiting enforcement
    /// - JWT validation + scope checking
    /// - API versioning support
    Proxy,

    /// Shadow/passive mode for traffic analysis
    /// - Mirror traffic via port mirroring or envoy tap
    /// - Parse HTTP requests/responses
    /// - Auto-generate UAC contracts
    /// - Auto-generate MCP tool definitions
    Shadow,
}

impl GatewayMode {
    /// Get all available modes
    pub fn all() -> &'static [GatewayMode] {
        &[
            GatewayMode::EdgeMcp,
            GatewayMode::Sidecar,
            GatewayMode::Proxy,
            GatewayMode::Shadow,
        ]
    }

    /// Check if this mode supports MCP protocol
    pub fn supports_mcp(&self) -> bool {
        matches!(self, GatewayMode::EdgeMcp)
    }

    /// Check if this mode requires upstream routing
    pub fn requires_upstream(&self) -> bool {
        matches!(self, GatewayMode::Proxy | GatewayMode::Shadow)
    }

    /// Check if this mode is read-only (no side effects)
    pub fn is_passive(&self) -> bool {
        matches!(self, GatewayMode::Shadow)
    }

    /// Check if this mode handles request/response transformation
    pub fn supports_transformation(&self) -> bool {
        matches!(self, GatewayMode::Proxy)
    }

    /// Get mode-specific default port
    pub fn default_port(&self) -> u16 {
        match self {
            GatewayMode::EdgeMcp => 8080,
            GatewayMode::Sidecar => 8081,
            GatewayMode::Proxy => 8082,
            GatewayMode::Shadow => 8083,
        }
    }

    /// Get mode description for logging/UI
    pub fn description(&self) -> &'static str {
        match self {
            GatewayMode::EdgeMcp => "MCP Edge Gateway with SSE transport",
            GatewayMode::Sidecar => "Sidecar policy enforcement",
            GatewayMode::Proxy => "Inline proxy with transformation",
            GatewayMode::Shadow => "Shadow traffic analysis",
        }
    }
}

impl fmt::Display for GatewayMode {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            GatewayMode::EdgeMcp => write!(f, "edge-mcp"),
            GatewayMode::Sidecar => write!(f, "sidecar"),
            GatewayMode::Proxy => write!(f, "proxy"),
            GatewayMode::Shadow => write!(f, "shadow"),
        }
    }
}

/// Error parsing gateway mode
#[derive(Error, Debug)]
#[error("Invalid gateway mode: {0}. Valid modes: edge-mcp, sidecar, proxy, shadow")]
pub struct ParseModeError(String);

impl FromStr for GatewayMode {
    type Err = ParseModeError;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s.to_lowercase().as_str() {
            "edge-mcp" | "edge_mcp" | "edgemcp" | "mcp" => Ok(GatewayMode::EdgeMcp),
            "sidecar" => Ok(GatewayMode::Sidecar),
            "proxy" => Ok(GatewayMode::Proxy),
            "shadow" => Ok(GatewayMode::Shadow),
            _ => Err(ParseModeError(s.to_string())),
        }
    }
}

/// Mode configuration loaded from environment
#[derive(Debug, Clone)]
pub struct ModeConfig {
    /// Selected gateway mode
    pub mode: GatewayMode,

    /// Mode-specific settings
    pub settings: ModeSettings,
}

/// Mode-specific configuration settings
#[derive(Debug, Clone)]
pub enum ModeSettings {
    /// Edge MCP mode settings
    EdgeMcp(EdgeMcpSettings),

    /// Sidecar mode settings
    Sidecar(SidecarSettings),

    /// Proxy mode settings
    Proxy(ProxySettings),

    /// Shadow mode settings
    Shadow(ShadowSettings),
}

/// Edge MCP mode configuration
#[derive(Debug, Clone, Default)]
pub struct EdgeMcpSettings {
    /// Enable SSE keepalive
    pub sse_keepalive: bool,

    /// SSE keepalive interval in seconds
    pub sse_keepalive_interval_secs: u64,

    /// Maximum concurrent sessions
    pub max_sessions: usize,

    /// Session timeout in seconds
    pub session_timeout_secs: u64,
}

/// Sidecar mode configuration
#[derive(Debug, Clone, Default)]
pub struct SidecarSettings {
    /// Upstream gateway type (kong, envoy, apigee, nginx, etc.)
    pub upstream_type: String,

    /// Header containing pre-validated user info
    pub user_info_header: String,

    /// Header containing tenant ID
    pub tenant_id_header: String,

    /// Return format for allow/deny decisions
    pub decision_format: DecisionFormat,
}

/// Format for sidecar allow/deny decisions
#[derive(Debug, Clone, Default)]
pub enum DecisionFormat {
    /// HTTP status code only (200 allow, 403 deny)
    #[default]
    StatusCode,

    /// JSON body with details
    JsonBody,

    /// Envoy ext_authz format
    EnvoyExtAuthz,

    /// Kong plugin format
    KongPlugin,
}

/// Proxy mode configuration
#[derive(Debug, Clone, Default)]
pub struct ProxySettings {
    /// Enable request body transformation
    pub transform_request: bool,

    /// Enable response body transformation
    pub transform_response: bool,

    /// Enable header injection
    pub inject_headers: bool,

    /// Enable WebSocket passthrough
    pub websocket_passthrough: bool,

    /// Backend connection pool size
    pub connection_pool_size: usize,
}

/// Shadow mode configuration
#[derive(Debug, Clone, Default)]
pub struct ShadowSettings {
    /// Traffic capture method
    pub capture_method: CaptureMethod,

    /// Output directory for generated UAC contracts
    pub uac_output_dir: String,

    /// Enable automatic GitLab MR creation
    pub auto_create_mr: bool,

    /// GitLab project for MRs
    pub gitlab_project: Option<String>,

    /// Minimum requests before generating UAC
    pub min_requests_for_uac: u64,

    /// Analysis window in hours
    pub analysis_window_hours: u64,
}

/// Traffic capture method for shadow mode
#[derive(Debug, Clone, Default)]
pub enum CaptureMethod {
    /// Envoy tap filter
    #[default]
    EnvoyTap,

    /// Port mirroring
    PortMirror,

    /// Inline (copy traffic)
    Inline,

    /// Kafka topic replay
    KafkaReplay,
}

impl ModeConfig {
    /// Load mode configuration from environment
    pub fn from_env() -> Self {
        let mode = std::env::var("STOA_MODE")
            .ok()
            .and_then(|s| s.parse().ok())
            .unwrap_or_default();

        let settings = match mode {
            GatewayMode::EdgeMcp => ModeSettings::EdgeMcp(EdgeMcpSettings::from_env()),
            GatewayMode::Sidecar => ModeSettings::Sidecar(SidecarSettings::from_env()),
            GatewayMode::Proxy => ModeSettings::Proxy(ProxySettings::from_env()),
            GatewayMode::Shadow => ModeSettings::Shadow(ShadowSettings::from_env()),
        };

        Self { mode, settings }
    }

    /// Get the selected mode
    pub fn mode(&self) -> GatewayMode {
        self.mode
    }

    /// Get Edge MCP settings (panics if wrong mode)
    pub fn edge_mcp(&self) -> &EdgeMcpSettings {
        match &self.settings {
            ModeSettings::EdgeMcp(s) => s,
            _ => panic!("Not in edge-mcp mode"),
        }
    }

    /// Get Sidecar settings (panics if wrong mode)
    pub fn sidecar(&self) -> &SidecarSettings {
        match &self.settings {
            ModeSettings::Sidecar(s) => s,
            _ => panic!("Not in sidecar mode"),
        }
    }

    /// Get Proxy settings (panics if wrong mode)
    pub fn proxy(&self) -> &ProxySettings {
        match &self.settings {
            ModeSettings::Proxy(s) => s,
            _ => panic!("Not in proxy mode"),
        }
    }

    /// Get Shadow settings (panics if wrong mode)
    pub fn shadow(&self) -> &ShadowSettings {
        match &self.settings {
            ModeSettings::Shadow(s) => s,
            _ => panic!("Not in shadow mode"),
        }
    }
}

impl EdgeMcpSettings {
    pub fn from_env() -> Self {
        Self {
            sse_keepalive: std::env::var("STOA_SSE_KEEPALIVE")
                .map(|v| v.to_lowercase() != "false")
                .unwrap_or(true),
            sse_keepalive_interval_secs: std::env::var("STOA_SSE_KEEPALIVE_INTERVAL")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(30),
            max_sessions: std::env::var("STOA_MAX_SESSIONS")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(10000),
            session_timeout_secs: std::env::var("STOA_SESSION_TIMEOUT")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(3600),
        }
    }
}

impl SidecarSettings {
    pub fn from_env() -> Self {
        Self {
            upstream_type: std::env::var("STOA_UPSTREAM_TYPE")
                .unwrap_or_else(|_| "generic".to_string()),
            user_info_header: std::env::var("STOA_USER_INFO_HEADER")
                .unwrap_or_else(|_| "X-User-Info".to_string()),
            tenant_id_header: std::env::var("STOA_TENANT_ID_HEADER")
                .unwrap_or_else(|_| "X-Tenant-ID".to_string()),
            decision_format: DecisionFormat::default(),
        }
    }
}

impl ProxySettings {
    pub fn from_env() -> Self {
        Self {
            transform_request: std::env::var("STOA_TRANSFORM_REQUEST")
                .map(|v| v.to_lowercase() == "true")
                .unwrap_or(false),
            transform_response: std::env::var("STOA_TRANSFORM_RESPONSE")
                .map(|v| v.to_lowercase() == "true")
                .unwrap_or(false),
            inject_headers: std::env::var("STOA_INJECT_HEADERS")
                .map(|v| v.to_lowercase() != "false")
                .unwrap_or(true),
            websocket_passthrough: std::env::var("STOA_WEBSOCKET_PASSTHROUGH")
                .map(|v| v.to_lowercase() == "true")
                .unwrap_or(false),
            connection_pool_size: std::env::var("STOA_CONNECTION_POOL_SIZE")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(100),
        }
    }
}

impl ShadowSettings {
    pub fn from_env() -> Self {
        Self {
            capture_method: CaptureMethod::default(),
            uac_output_dir: std::env::var("STOA_UAC_OUTPUT_DIR")
                .unwrap_or_else(|_| "/var/stoa/uac".to_string()),
            auto_create_mr: std::env::var("STOA_AUTO_CREATE_MR")
                .map(|v| v.to_lowercase() == "true")
                .unwrap_or(false),
            gitlab_project: std::env::var("STOA_GITLAB_PROJECT").ok(),
            min_requests_for_uac: std::env::var("STOA_MIN_REQUESTS_FOR_UAC")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(100),
            analysis_window_hours: std::env::var("STOA_ANALYSIS_WINDOW_HOURS")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(168), // 7 days
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_gateway_mode_parse() {
        assert_eq!(
            "edge-mcp".parse::<GatewayMode>().unwrap(),
            GatewayMode::EdgeMcp
        );
        assert_eq!("mcp".parse::<GatewayMode>().unwrap(), GatewayMode::EdgeMcp);
        assert_eq!(
            "sidecar".parse::<GatewayMode>().unwrap(),
            GatewayMode::Sidecar
        );
        assert_eq!("proxy".parse::<GatewayMode>().unwrap(), GatewayMode::Proxy);
        assert_eq!(
            "shadow".parse::<GatewayMode>().unwrap(),
            GatewayMode::Shadow
        );
        assert!("invalid".parse::<GatewayMode>().is_err());
    }

    #[test]
    fn test_gateway_mode_display() {
        assert_eq!(GatewayMode::EdgeMcp.to_string(), "edge-mcp");
        assert_eq!(GatewayMode::Sidecar.to_string(), "sidecar");
        assert_eq!(GatewayMode::Proxy.to_string(), "proxy");
        assert_eq!(GatewayMode::Shadow.to_string(), "shadow");
    }

    #[test]
    fn test_gateway_mode_capabilities() {
        assert!(GatewayMode::EdgeMcp.supports_mcp());
        assert!(!GatewayMode::Sidecar.supports_mcp());
        assert!(!GatewayMode::Proxy.supports_mcp());
        assert!(!GatewayMode::Shadow.supports_mcp());

        assert!(!GatewayMode::EdgeMcp.is_passive());
        assert!(!GatewayMode::Sidecar.is_passive());
        assert!(!GatewayMode::Proxy.is_passive());
        assert!(GatewayMode::Shadow.is_passive());
    }

    #[test]
    fn test_gateway_mode_default() {
        assert_eq!(GatewayMode::default(), GatewayMode::EdgeMcp);
    }

    #[test]
    fn test_mode_config_default() {
        let config = ModeConfig::from_env();
        assert_eq!(config.mode(), GatewayMode::EdgeMcp);
    }

    #[test]
    fn test_default_ports() {
        assert_eq!(GatewayMode::EdgeMcp.default_port(), 8080);
        assert_eq!(GatewayMode::Sidecar.default_port(), 8081);
        assert_eq!(GatewayMode::Proxy.default_port(), 8082);
        assert_eq!(GatewayMode::Shadow.default_port(), 8083);
    }

    #[test]
    fn test_requires_upstream() {
        assert!(!GatewayMode::EdgeMcp.requires_upstream());
        assert!(!GatewayMode::Sidecar.requires_upstream());
        assert!(GatewayMode::Proxy.requires_upstream());
        assert!(GatewayMode::Shadow.requires_upstream());
    }

    #[test]
    fn test_supports_transformation() {
        assert!(!GatewayMode::EdgeMcp.supports_transformation());
        assert!(!GatewayMode::Sidecar.supports_transformation());
        assert!(GatewayMode::Proxy.supports_transformation());
        assert!(!GatewayMode::Shadow.supports_transformation());
    }

    #[test]
    fn test_description_not_empty() {
        for mode in GatewayMode::all() {
            assert!(!mode.description().is_empty());
        }
    }

    #[test]
    fn test_all_modes_count() {
        assert_eq!(GatewayMode::all().len(), 4);
    }

    #[test]
    fn test_mode_parse_variants() {
        // edge-mcp has multiple aliases
        assert_eq!(
            "edge_mcp".parse::<GatewayMode>().unwrap(),
            GatewayMode::EdgeMcp
        );
        assert_eq!(
            "edgemcp".parse::<GatewayMode>().unwrap(),
            GatewayMode::EdgeMcp
        );
        assert_eq!("MCP".parse::<GatewayMode>().unwrap(), GatewayMode::EdgeMcp);
        assert_eq!(
            "SIDECAR".parse::<GatewayMode>().unwrap(),
            GatewayMode::Sidecar
        );
        assert_eq!("PROXY".parse::<GatewayMode>().unwrap(), GatewayMode::Proxy);
        assert_eq!(
            "SHADOW".parse::<GatewayMode>().unwrap(),
            GatewayMode::Shadow
        );
    }

    #[test]
    fn test_mode_parse_error_message() {
        let err = "foobar".parse::<GatewayMode>().unwrap_err();
        let msg = err.to_string();
        assert!(msg.contains("foobar"));
        assert!(msg.contains("edge-mcp"));
    }

    #[test]
    fn test_mode_serde_roundtrip() {
        let mode = GatewayMode::EdgeMcp;
        let json = serde_json::to_string(&mode).unwrap();
        assert_eq!(json, "\"edge-mcp\"");
        let deserialized: GatewayMode = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized, GatewayMode::EdgeMcp);
    }

    #[test]
    fn test_mode_serde_all_variants() {
        for mode in GatewayMode::all() {
            let json = serde_json::to_string(mode).unwrap();
            let back: GatewayMode = serde_json::from_str(&json).unwrap();
            assert_eq!(&back, mode);
        }
    }

    #[test]
    #[should_panic(expected = "Not in sidecar mode")]
    fn test_mode_config_wrong_accessor_sidecar() {
        let config = ModeConfig::from_env(); // defaults to EdgeMcp
        let _ = config.sidecar();
    }

    #[test]
    #[should_panic(expected = "Not in proxy mode")]
    fn test_mode_config_wrong_accessor_proxy() {
        let config = ModeConfig::from_env();
        let _ = config.proxy();
    }

    #[test]
    #[should_panic(expected = "Not in shadow mode")]
    fn test_mode_config_wrong_accessor_shadow() {
        let config = ModeConfig::from_env();
        let _ = config.shadow();
    }

    #[test]
    fn test_mode_config_edge_mcp_accessor() {
        let config = ModeConfig::from_env(); // defaults to EdgeMcp
        let settings = config.edge_mcp();
        assert!(settings.sse_keepalive); // default is true
    }
}
