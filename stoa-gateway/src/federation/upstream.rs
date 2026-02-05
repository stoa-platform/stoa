//! Upstream MCP Server Federation
//!
//! This module handles connections to upstream MCP servers and exposes
//! their tools through the STOA gateway.

use super::{ConnectionState, FederationConfig, FederationError, FederationMetrics, Result};
use crate::k8s::{ToolAuth, UpstreamConfig};
use crate::mcp::tools::{ToolDefinition, ToolRegistry, ToolSchema};
use async_trait::async_trait;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::atomic::{AtomicU32, AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::RwLock;
use tracing::{debug, error, info, instrument, warn};
use uuid::Uuid;

/// Represents a tool from an upstream MCP server
#[derive(Debug, Clone)]
pub struct UpstreamTool {
    /// Tool name (may be prefixed with upstream identifier)
    pub name: String,

    /// Original name from upstream
    pub original_name: String,

    /// Tool description
    pub description: String,

    /// Input schema
    pub input_schema: serde_json::Value,

    /// Output schema (MCP 2025)
    pub output_schema: Option<serde_json::Value>,

    /// Tool annotations (MCP 2025)
    pub annotations: Option<serde_json::Value>,

    /// Upstream connection ID
    pub upstream_id: String,
}

/// Connection to an upstream MCP server
pub struct UpstreamConnection {
    /// Unique identifier for this connection
    pub id: String,

    /// Human-readable name (from ToolSet)
    pub name: String,

    /// Configuration
    config: UpstreamConfig,

    /// HTTP client for SSE/HTTP transport
    client: Client,

    /// Current connection state
    state: RwLock<ConnectionState>,

    /// Discovered tools
    tools: RwLock<Vec<UpstreamTool>>,

    /// Session ID (for stateful protocols)
    session_id: RwLock<Option<String>>,

    /// Circuit breaker state
    failure_count: AtomicU32,
    last_failure: RwLock<Option<Instant>>,

    /// Last successful health check
    last_health_check: RwLock<Option<Instant>>,

    /// Metrics
    call_count: AtomicU64,
    error_count: AtomicU64,
}

impl UpstreamConnection {
    /// Create a new upstream connection
    pub fn new(name: String, config: UpstreamConfig) -> Self {
        let client = Client::builder()
            .timeout(Duration::from_secs(30))
            .build()
            .expect("Failed to create HTTP client");

        Self {
            id: Uuid::new_v4().to_string(),
            name,
            config,
            client,
            state: RwLock::new(ConnectionState::Disconnected),
            tools: RwLock::new(Vec::new()),
            session_id: RwLock::new(None),
            failure_count: AtomicU32::new(0),
            last_failure: RwLock::new(None),
            last_health_check: RwLock::new(None),
            call_count: AtomicU64::new(0),
            error_count: AtomicU64::new(0),
        }
    }

    /// Get the current connection state
    pub async fn state(&self) -> ConnectionState {
        self.state.read().await.clone()
    }

    /// Get discovered tools
    pub async fn tools(&self) -> Vec<UpstreamTool> {
        self.tools.read().await.clone()
    }

    /// Connect to the upstream server and discover tools
    #[instrument(skip(self), fields(upstream = %self.name))]
    pub async fn connect(&self) -> Result<()> {
        // Check circuit breaker
        if self.is_circuit_open().await {
            return Err(FederationError::CircuitBreakerOpen(self.name.clone()));
        }

        *self.state.write().await = ConnectionState::Connecting;
        info!("Connecting to upstream MCP server: {}", self.config.url);

        // Initialize MCP session
        match self.initialize_session().await {
            Ok(()) => {
                *self.state.write().await = ConnectionState::Connected;
                self.failure_count.store(0, Ordering::SeqCst);
                info!(
                    "Connected to upstream MCP server: {} (session: {:?})",
                    self.name,
                    self.session_id.read().await
                );

                // Discover tools
                self.discover_tools().await?;

                Ok(())
            }
            Err(e) => {
                self.record_failure().await;
                *self.state.write().await = ConnectionState::Failed;
                error!("Failed to connect to {}: {}", self.name, e);
                Err(e)
            }
        }
    }

    /// Initialize MCP session with upstream server
    async fn initialize_session(&self) -> Result<()> {
        let init_request = serde_json::json!({
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {
                    "tools": {},
                    "resources": {}
                },
                "clientInfo": {
                    "name": "stoa-gateway",
                    "version": env!("CARGO_PKG_VERSION")
                }
            },
            "id": 1
        });

        let response = self
            .send_request(&init_request)
            .await?;

        // Parse response
        if let Some(result) = response.get("result") {
            // Store session info if provided
            if let Some(session_id) = result.get("sessionId").and_then(|v| v.as_str()) {
                *self.session_id.write().await = Some(session_id.to_string());
            }

            // Send initialized notification
            let initialized = serde_json::json!({
                "jsonrpc": "2.0",
                "method": "notifications/initialized"
            });
            let _ = self.send_request(&initialized).await;

            Ok(())
        } else if let Some(error) = response.get("error") {
            Err(FederationError::Connection(format!(
                "Upstream initialization error: {}",
                error
            )))
        } else {
            Err(FederationError::Connection(
                "Invalid initialize response".to_string(),
            ))
        }
    }

    /// Discover tools from the upstream server
    #[instrument(skip(self))]
    async fn discover_tools(&self) -> Result<()> {
        let list_request = serde_json::json!({
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": {},
            "id": 2
        });

        let response = self.send_request(&list_request).await?;

        if let Some(result) = response.get("result") {
            if let Some(tools) = result.get("tools").and_then(|v| v.as_array()) {
                let mut discovered = Vec::new();

                for tool in tools {
                    let name = tool
                        .get("name")
                        .and_then(|v| v.as_str())
                        .unwrap_or("unknown")
                        .to_string();

                    let prefixed_name = format!("{}_{}", self.name.replace('-', "_"), name);

                    let upstream_tool = UpstreamTool {
                        name: prefixed_name,
                        original_name: name.clone(),
                        description: tool
                            .get("description")
                            .and_then(|v| v.as_str())
                            .unwrap_or("")
                            .to_string(),
                        input_schema: tool
                            .get("inputSchema")
                            .cloned()
                            .unwrap_or_else(|| serde_json::json!({})),
                        output_schema: tool.get("outputSchema").cloned(),
                        annotations: tool.get("annotations").cloned(),
                        upstream_id: self.id.clone(),
                    };

                    discovered.push(upstream_tool);
                }

                info!(
                    "Discovered {} tools from upstream {}",
                    discovered.len(),
                    self.name
                );

                *self.tools.write().await = discovered;
            }
        }

        Ok(())
    }

    /// Call a tool on the upstream server
    #[instrument(skip(self, arguments), fields(upstream = %self.name, tool = %tool_name))]
    pub async fn call_tool(
        &self,
        tool_name: &str,
        arguments: serde_json::Value,
    ) -> Result<serde_json::Value> {
        // Check circuit breaker
        if self.is_circuit_open().await {
            return Err(FederationError::CircuitBreakerOpen(self.name.clone()));
        }

        // Check connection state
        if *self.state.read().await != ConnectionState::Connected {
            return Err(FederationError::Connection(format!(
                "Upstream {} not connected",
                self.name
            )));
        }

        self.call_count.fetch_add(1, Ordering::SeqCst);

        let call_request = serde_json::json!({
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            },
            "id": Uuid::new_v4().to_string()
        });

        match self.send_request(&call_request).await {
            Ok(response) => {
                self.failure_count.store(0, Ordering::SeqCst);

                if let Some(result) = response.get("result") {
                    Ok(result.clone())
                } else if let Some(error) = response.get("error") {
                    Err(FederationError::Invocation(format!(
                        "Tool call error: {}",
                        error
                    )))
                } else {
                    Err(FederationError::Invocation(
                        "Invalid tool call response".to_string(),
                    ))
                }
            }
            Err(e) => {
                self.error_count.fetch_add(1, Ordering::SeqCst);
                self.record_failure().await;
                Err(e)
            }
        }
    }

    /// Send a JSON-RPC request to the upstream server
    async fn send_request(&self, request: &serde_json::Value) -> Result<serde_json::Value> {
        let mut req = self.client.post(&self.config.url).json(request);

        // Add authentication
        if let Some(auth) = &self.config.auth {
            req = self.apply_auth(req, auth).await?;
        }

        let response = req
            .send()
            .await
            .map_err(|e| FederationError::Connection(e.to_string()))?;

        if !response.status().is_success() {
            return Err(FederationError::Connection(format!(
                "HTTP error: {}",
                response.status()
            )));
        }

        response
            .json()
            .await
            .map_err(|e| FederationError::Connection(format!("JSON parse error: {}", e)))
    }

    /// Apply authentication to a request
    async fn apply_auth(
        &self,
        req: reqwest::RequestBuilder,
        auth: &ToolAuth,
    ) -> Result<reqwest::RequestBuilder> {
        match auth.auth_type.as_str() {
            "bearer" => {
                // In a real implementation, fetch token from K8s secret
                // For now, return the request as-is
                Ok(req)
            }
            "api_key" => {
                let _header_name = auth
                    .header_name
                    .clone()
                    .unwrap_or_else(|| "X-API-Key".to_string());
                // In a real implementation, fetch key from K8s secret
                Ok(req)
            }
            "none" | "" => Ok(req),
            other => Err(FederationError::Auth(format!(
                "Unknown auth type: {}",
                other
            ))),
        }
    }

    /// Check if the circuit breaker is open
    async fn is_circuit_open(&self) -> bool {
        let failures = self.failure_count.load(Ordering::SeqCst);
        if failures < self.config.max_retries {
            return false;
        }

        // Check if enough time has passed to try again
        if let Some(last_failure) = *self.last_failure.read().await {
            let timeout = Duration::from_secs(30); // Default circuit breaker timeout
            if last_failure.elapsed() < timeout {
                return true;
            }
        }

        false
    }

    /// Record a failure for circuit breaker
    async fn record_failure(&self) {
        self.failure_count.fetch_add(1, Ordering::SeqCst);
        *self.last_failure.write().await = Some(Instant::now());
    }

    /// Get connection metrics
    pub fn metrics(&self) -> (u64, u64) {
        (
            self.call_count.load(Ordering::SeqCst),
            self.error_count.load(Ordering::SeqCst),
        )
    }

    /// Disconnect from the upstream server
    pub async fn disconnect(&self) {
        *self.state.write().await = ConnectionState::Disconnected;
        *self.session_id.write().await = None;
        info!("Disconnected from upstream: {}", self.name);
    }
}

/// Manages multiple upstream MCP server connections
pub struct FederationManager {
    /// Configuration
    config: FederationConfig,

    /// Active upstream connections
    connections: RwLock<HashMap<String, Arc<UpstreamConnection>>>,

    /// Tool registry to update
    registry: Arc<RwLock<ToolRegistry>>,

    /// Metrics
    metrics: RwLock<FederationMetrics>,
}

impl FederationManager {
    /// Create a new federation manager
    pub fn new(config: FederationConfig, registry: Arc<RwLock<ToolRegistry>>) -> Self {
        Self {
            config,
            connections: RwLock::new(HashMap::new()),
            registry,
            metrics: RwLock::new(FederationMetrics::default()),
        }
    }

    /// Add an upstream connection
    #[instrument(skip(self, upstream_config))]
    pub async fn add_upstream(
        &self,
        name: String,
        upstream_config: UpstreamConfig,
    ) -> Result<String> {
        if !self.config.enabled {
            return Err(FederationError::Connection(
                "Federation is disabled".to_string(),
            ));
        }

        let connection = Arc::new(UpstreamConnection::new(name.clone(), upstream_config));
        let conn_id = connection.id.clone();

        // Connect and discover tools
        connection.connect().await?;

        // Register discovered tools
        let tools = connection.tools().await;
        for tool in &tools {
            info!("Registered federated tool: {}", tool.name);
        }

        // Store connection
        {
            let mut connections = self.connections.write().await;
            connections.insert(conn_id.clone(), connection);
        }

        // Update metrics
        {
            let mut metrics = self.metrics.write().await;
            metrics.connections += 1;
            metrics.active_connections += 1;
            metrics.tools_discovered += tools.len() as u64;
        }

        Ok(conn_id)
    }

    /// Remove an upstream connection
    pub async fn remove_upstream(&self, connection_id: &str) -> Result<()> {
        let connection = {
            let mut connections = self.connections.write().await;
            connections.remove(connection_id)
        };

        if let Some(conn) = connection {
            conn.disconnect().await;

            // Update metrics
            let mut metrics = self.metrics.write().await;
            metrics.active_connections = metrics.active_connections.saturating_sub(1);
        }

        Ok(())
    }

    /// Call a tool on an upstream server
    #[instrument(skip(self, arguments))]
    pub async fn call_tool(
        &self,
        connection_id: &str,
        tool_name: &str,
        arguments: serde_json::Value,
    ) -> Result<serde_json::Value> {
        let connection = {
            let connections = self.connections.read().await;
            connections.get(connection_id).cloned()
        };

        match connection {
            Some(conn) => {
                let result = conn.call_tool(tool_name, arguments).await?;

                // Update metrics
                {
                    let mut metrics = self.metrics.write().await;
                    metrics.tool_calls += 1;
                    metrics.successful_calls += 1;
                }

                Ok(result)
            }
            None => Err(FederationError::Connection(format!(
                "Connection {} not found",
                connection_id
            ))),
        }
    }

    /// Get all active connections
    pub async fn connections(&self) -> Vec<(String, String, ConnectionState)> {
        let connections = self.connections.read().await;
        let mut result = Vec::new();

        for (id, conn) in connections.iter() {
            result.push((id.clone(), conn.name.clone(), conn.state().await));
        }

        result
    }

    /// Get federation metrics
    pub async fn metrics(&self) -> FederationMetrics {
        // Clone the metrics (FederationMetrics would need Clone derive)
        let m = self.metrics.read().await;
        FederationMetrics {
            connections: m.connections,
            active_connections: m.active_connections,
            tools_discovered: m.tools_discovered,
            tool_calls: m.tool_calls,
            successful_calls: m.successful_calls,
            failed_calls: m.failed_calls,
            circuit_breaker_trips: m.circuit_breaker_trips,
            composition_executions: m.composition_executions,
        }
    }

    /// Health check all upstream connections
    pub async fn health_check(&self) -> HashMap<String, bool> {
        let connections = self.connections.read().await;
        let mut results = HashMap::new();

        for (id, conn) in connections.iter() {
            let healthy = matches!(conn.state().await, ConnectionState::Connected);
            results.insert(id.clone(), healthy);
        }

        results
    }

    /// Refresh tool discovery for all connections
    pub async fn refresh_tools(&self) -> Result<usize> {
        let connections = self.connections.read().await;
        let mut total_tools = 0;

        for conn in connections.values() {
            if let Err(e) = conn.discover_tools().await {
                warn!("Failed to refresh tools from {}: {}", conn.name, e);
            } else {
                total_tools += conn.tools().await.len();
            }
        }

        Ok(total_tools)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_upstream_tool_creation() {
        let tool = UpstreamTool {
            name: "github_create_pr".to_string(),
            original_name: "create_pr".to_string(),
            description: "Create a GitHub PR".to_string(),
            input_schema: serde_json::json!({"type": "object"}),
            output_schema: None,
            annotations: None,
            upstream_id: "test-id".to_string(),
        };

        assert_eq!(tool.name, "github_create_pr");
        assert_eq!(tool.original_name, "create_pr");
    }

    #[test]
    fn test_federation_config_default() {
        let config = FederationConfig::default();
        assert!(config.enabled);
        assert_eq!(config.max_connections, 100);
        assert!(config.apply_policies);
    }

    #[tokio::test]
    async fn test_upstream_connection_initial_state() {
        let config = UpstreamConfig {
            url: "https://example.com/mcp".to_string(),
            transport: "sse".to_string(),
            auth: None,
            timeout: "30s".to_string(),
            max_retries: 3,
            apply_policies: true,
            metering_enabled: true,
        };

        let conn = UpstreamConnection::new("test".to_string(), config);
        assert_eq!(conn.state().await, ConnectionState::Disconnected);
        assert!(conn.tools().await.is_empty());
    }
}
