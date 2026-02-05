//! MCP Server Federation Module
//!
//! This module enables the STOA gateway to federate with upstream MCP servers,
//! aggregating their tools into a single unified interface. It also supports
//! tool composition, where multiple tools can be combined into compound workflows.
//!
//! # Architecture
//!
//! ```text
//! ┌─────────────────────────────────────────────────────────────────┐
//! │                      STOA Gateway                               │
//! │  ┌───────────────┐  ┌───────────────┐  ┌───────────────────┐   │
//! │  │ Tool Registry │  │ Federation    │  │ Composition       │   │
//! │  │               │◄─┤ Manager       │  │ Engine            │   │
//! │  │ - native      │  │               │  │                   │   │
//! │  │ - federated   │  │ - discovery   │  │ - step execution  │   │
//! │  │ - composed    │  │ - sync        │  │ - data mapping    │   │
//! │  └───────────────┘  │ - health      │  │ - error handling  │   │
//! │                     └───────┬───────┘  └───────────────────┘   │
//! └─────────────────────────────┼───────────────────────────────────┘
//!                               │
//!          ┌────────────────────┼────────────────────┐
//!          │                    │                    │
//!          ▼                    ▼                    ▼
//!    ┌──────────┐        ┌──────────┐        ┌──────────┐
//!    │ GitHub   │        │ Slack    │        │ Internal │
//!    │ MCP      │        │ MCP      │        │ MCP      │
//!    │ Server   │        │ Server   │        │ Server   │
//!    └──────────┘        └──────────┘        └──────────┘
//! ```
//!
//! # Features
//!
//! - **Upstream Federation**: Connect to external MCP servers and expose their tools
//! - **Tool Discovery**: Automatically discover tools from upstream servers
//! - **Policy Enforcement**: Apply OPA policies to federated tool calls
//! - **Metering**: Track usage of federated tools
//! - **Circuit Breaker**: Handle upstream failures gracefully
//! - **Tool Composition**: Combine multiple tools into workflows

#![allow(dead_code)] // Phase 7 methods will be wired incrementally

pub mod composition;
pub mod upstream;

// Re-exports
pub use composition::{ComposedTool, CompositionEngine, StepResult};
pub use upstream::{FederationManager, UpstreamConnection, UpstreamTool};

use thiserror::Error;

/// Errors that can occur during federation
#[derive(Error, Debug)]
pub enum FederationError {
    #[error("Connection error: {0}")]
    Connection(String),

    #[error("Discovery error: {0}")]
    Discovery(String),

    #[error("Tool invocation error: {0}")]
    Invocation(String),

    #[error("Authentication error: {0}")]
    Auth(String),

    #[error("Timeout: {0}")]
    Timeout(String),

    #[error("Circuit breaker open for: {0}")]
    CircuitBreakerOpen(String),

    #[error("Composition error: {0}")]
    Composition(String),

    #[error("Mapping error: {0}")]
    Mapping(String),
}

/// Result type for federation operations
pub type Result<T> = std::result::Result<T, FederationError>;

/// Configuration for federation
#[derive(Debug, Clone)]
pub struct FederationConfig {
    /// Whether federation is enabled
    pub enabled: bool,

    /// Maximum number of concurrent upstream connections
    pub max_connections: usize,

    /// Default connection timeout
    pub connection_timeout: std::time::Duration,

    /// Default request timeout
    pub request_timeout: std::time::Duration,

    /// Whether to apply OPA policies to federated calls
    pub apply_policies: bool,

    /// Whether to meter federated calls
    pub metering_enabled: bool,

    /// Circuit breaker failure threshold
    pub circuit_breaker_threshold: u32,

    /// Circuit breaker recovery timeout
    pub circuit_breaker_timeout: std::time::Duration,
}

impl Default for FederationConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            max_connections: 100,
            connection_timeout: std::time::Duration::from_secs(30),
            request_timeout: std::time::Duration::from_secs(60),
            apply_policies: true,
            metering_enabled: true,
            circuit_breaker_threshold: 5,
            circuit_breaker_timeout: std::time::Duration::from_secs(30),
        }
    }
}

impl FederationConfig {
    /// Create config from environment variables
    pub fn from_env() -> Self {
        let enabled = std::env::var("FEDERATION_ENABLED")
            .map(|v| v.to_lowercase() == "true")
            .unwrap_or(true);

        let max_connections = std::env::var("FEDERATION_MAX_CONNECTIONS")
            .ok()
            .and_then(|v| v.parse().ok())
            .unwrap_or(100);

        let connection_timeout_secs = std::env::var("FEDERATION_CONNECTION_TIMEOUT_SECS")
            .ok()
            .and_then(|v| v.parse().ok())
            .unwrap_or(30);

        let request_timeout_secs = std::env::var("FEDERATION_REQUEST_TIMEOUT_SECS")
            .ok()
            .and_then(|v| v.parse().ok())
            .unwrap_or(60);

        let apply_policies = std::env::var("FEDERATION_APPLY_POLICIES")
            .map(|v| v.to_lowercase() != "false")
            .unwrap_or(true);

        let metering_enabled = std::env::var("FEDERATION_METERING_ENABLED")
            .map(|v| v.to_lowercase() != "false")
            .unwrap_or(true);

        let circuit_breaker_threshold = std::env::var("FEDERATION_CIRCUIT_BREAKER_THRESHOLD")
            .ok()
            .and_then(|v| v.parse().ok())
            .unwrap_or(5);

        let circuit_breaker_timeout_secs = std::env::var("FEDERATION_CIRCUIT_BREAKER_TIMEOUT_SECS")
            .ok()
            .and_then(|v| v.parse().ok())
            .unwrap_or(30);

        Self {
            enabled,
            max_connections,
            connection_timeout: std::time::Duration::from_secs(connection_timeout_secs),
            request_timeout: std::time::Duration::from_secs(request_timeout_secs),
            apply_policies,
            metering_enabled,
            circuit_breaker_threshold,
            circuit_breaker_timeout: std::time::Duration::from_secs(circuit_breaker_timeout_secs),
        }
    }
}

/// Metrics for federation operations
#[derive(Debug, Default)]
pub struct FederationMetrics {
    /// Total upstream connections
    pub connections: u64,

    /// Active connections
    pub active_connections: u64,

    /// Total tools discovered
    pub tools_discovered: u64,

    /// Total federated tool calls
    pub tool_calls: u64,

    /// Successful tool calls
    pub successful_calls: u64,

    /// Failed tool calls
    pub failed_calls: u64,

    /// Circuit breaker trips
    pub circuit_breaker_trips: u64,

    /// Total composition executions
    pub composition_executions: u64,
}

/// State of an upstream connection
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ConnectionState {
    /// Connection not established
    Disconnected,

    /// Connection in progress
    Connecting,

    /// Connection established and healthy
    Connected,

    /// Connection failed, will retry
    Failed,

    /// Circuit breaker is open
    CircuitOpen,
}

impl std::fmt::Display for ConnectionState {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ConnectionState::Disconnected => write!(f, "Disconnected"),
            ConnectionState::Connecting => write!(f, "Connecting"),
            ConnectionState::Connected => write!(f, "Connected"),
            ConnectionState::Failed => write!(f, "Failed"),
            ConnectionState::CircuitOpen => write!(f, "CircuitOpen"),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_federation_config_default() {
        let config = FederationConfig::default();
        assert!(config.enabled);
        assert_eq!(config.max_connections, 100);
        assert!(config.apply_policies);
        assert!(config.metering_enabled);
    }

    #[test]
    fn test_connection_state_display() {
        assert_eq!(ConnectionState::Connected.to_string(), "Connected");
        assert_eq!(ConnectionState::CircuitOpen.to_string(), "CircuitOpen");
    }
}
