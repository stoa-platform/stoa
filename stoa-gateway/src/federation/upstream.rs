//! Upstream MCP Client
//!
//! Connects to upstream MCP servers and proxies tool calls.

// Infrastructure prepared for K8s CRD watcher integration (Phase 7)
#![allow(dead_code)]
#![allow(clippy::redundant_closure)]

use async_trait::async_trait;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::sync::Arc;
use std::time::Duration;
use tracing::{debug, error, info, warn};

use crate::mcp::tools::{Tool, ToolContext, ToolDefinition, ToolError, ToolResult, ToolSchema};
use crate::uac::Action;

/// Configuration for upstream MCP client
#[derive(Debug, Clone)]
pub struct UpstreamMcpConfig {
    /// Upstream MCP server URL
    pub url: String,
    /// Transport type (sse or streamable-http)
    pub transport: TransportType,
    /// Optional auth token
    pub auth_token: Option<String>,
    /// Connection timeout
    pub timeout: Duration,
}

impl Default for UpstreamMcpConfig {
    fn default() -> Self {
        Self {
            url: String::new(),
            transport: TransportType::Sse,
            auth_token: None,
            timeout: Duration::from_secs(30),
        }
    }
}

/// MCP transport type
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TransportType {
    /// Server-Sent Events transport
    Sse,
    /// Streamable HTTP (not yet implemented)
    StreamableHttp,
}

impl TransportType {
    #[allow(clippy::should_implement_trait)]
    pub fn from_str(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "streamable-http" | "streamable_http" | "http" => TransportType::StreamableHttp,
            _ => TransportType::Sse,
        }
    }
}

/// Upstream MCP server client
pub struct UpstreamMcpClient {
    config: UpstreamMcpConfig,
    client: Client,
    /// Server info from initialize response
    server_info: Option<ServerInfo>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct ServerInfo {
    name: String,
    version: String,
}

impl UpstreamMcpClient {
    /// Create a new upstream MCP client
    pub fn new(config: UpstreamMcpConfig) -> Self {
        let client = Client::builder()
            .timeout(config.timeout)
            .build()
            .expect("Failed to create HTTP client");

        Self {
            config,
            client,
            server_info: None,
        }
    }

    /// Get the upstream URL
    pub fn url(&self) -> &str {
        &self.config.url
    }

    /// Initialize connection to upstream (MCP initialize handshake)
    pub async fn initialize(&mut self) -> Result<(), UpstreamError> {
        info!(url = %self.config.url, "Initializing connection to upstream MCP server");

        let request = json!({
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {
                    "name": "stoa-gateway-federation",
                    "version": env!("CARGO_PKG_VERSION")
                }
            },
            "id": 1
        });

        let response = self.send_request(&request).await?;

        if let Some(result) = response.get("result") {
            if let Some(server_info) = result.get("serverInfo") {
                self.server_info = Some(ServerInfo {
                    name: server_info
                        .get("name")
                        .and_then(|v| v.as_str())
                        .unwrap_or("unknown")
                        .to_string(),
                    version: server_info
                        .get("version")
                        .and_then(|v| v.as_str())
                        .unwrap_or("unknown")
                        .to_string(),
                });
            }
            info!(
                server = ?self.server_info,
                "Connected to upstream MCP server"
            );
            Ok(())
        } else if let Some(error) = response.get("error") {
            error!(error = ?error, "Upstream initialize failed");
            Err(UpstreamError::InitializeFailed(format!("{:?}", error)))
        } else {
            Err(UpstreamError::InvalidResponse)
        }
    }

    /// Discover tools from upstream MCP server
    pub async fn discover_tools(&self) -> Result<Vec<ToolDefinition>, UpstreamError> {
        debug!(url = %self.config.url, "Discovering tools from upstream");

        let request = json!({
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": {},
            "id": 2
        });

        let response = self.send_request(&request).await?;

        if let Some(result) = response.get("result") {
            if let Some(tools) = result.get("tools").and_then(|v| v.as_array()) {
                let definitions: Vec<ToolDefinition> = tools
                    .iter()
                    .filter_map(|t| parse_tool_definition(t))
                    .collect();

                info!(
                    count = definitions.len(),
                    url = %self.config.url,
                    "Discovered tools from upstream"
                );

                return Ok(definitions);
            }
        }

        if let Some(error) = response.get("error") {
            warn!(error = ?error, "Upstream tools/list failed");
            return Err(UpstreamError::ToolsListFailed(format!("{:?}", error)));
        }

        Ok(vec![])
    }

    /// Call a tool on the upstream MCP server
    pub async fn call_tool(&self, name: &str, args: Value) -> Result<Value, UpstreamError> {
        debug!(tool = %name, url = %self.config.url, "Calling tool on upstream");

        let request = json!({
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": args
            },
            "id": 3
        });

        let response = self.send_request(&request).await?;

        if let Some(result) = response.get("result") {
            Ok(result.clone())
        } else if let Some(error) = response.get("error") {
            Err(UpstreamError::ToolCallFailed {
                tool: name.to_string(),
                error: format!("{:?}", error),
            })
        } else {
            Err(UpstreamError::InvalidResponse)
        }
    }

    /// Send a JSON-RPC request to upstream
    async fn send_request(&self, request: &Value) -> Result<Value, UpstreamError> {
        let url = match self.config.transport {
            TransportType::Sse => format!("{}/sse", self.config.url.trim_end_matches('/')),
            TransportType::StreamableHttp => self.config.url.clone(),
        };

        let mut req = self
            .client
            .post(&url)
            .header("Content-Type", "application/json");

        if let Some(token) = &self.config.auth_token {
            req = req.header("Authorization", format!("Bearer {}", token));
        }

        let response = req
            .json(request)
            .send()
            .await
            .map_err(|e| UpstreamError::ConnectionFailed(e.to_string()))?;

        if !response.status().is_success() {
            return Err(UpstreamError::HttpError(response.status().as_u16()));
        }

        response
            .json()
            .await
            .map_err(|e| UpstreamError::ParseError(e.to_string()))
    }
}

/// Parse a tool definition from JSON
fn parse_tool_definition(json: &Value) -> Option<ToolDefinition> {
    let name = json.get("name")?.as_str()?.to_string();
    let description = json
        .get("description")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();

    let input_schema = json.get("inputSchema").cloned().unwrap_or(json!({}));

    Some(ToolDefinition {
        name,
        description,
        input_schema: ToolSchema {
            schema_type: input_schema
                .get("type")
                .and_then(|v| v.as_str())
                .unwrap_or("object")
                .to_string(),
            properties: input_schema
                .get("properties")
                .and_then(|v| v.as_object())
                .map(|m| m.iter().map(|(k, v)| (k.clone(), v.clone())).collect())
                .unwrap_or_default(),
            required: input_schema
                .get("required")
                .and_then(|v| v.as_array())
                .map(|arr| {
                    arr.iter()
                        .filter_map(|v| v.as_str().map(String::from))
                        .collect()
                })
                .unwrap_or_default(),
        },
        output_schema: json.get("outputSchema").cloned(),
        annotations: None, // TODO: Parse annotations from upstream
    })
}

/// Upstream client errors
#[derive(Debug, thiserror::Error)]
pub enum UpstreamError {
    #[error("Connection failed: {0}")]
    ConnectionFailed(String),

    #[error("HTTP error: {0}")]
    HttpError(u16),

    #[error("Parse error: {0}")]
    ParseError(String),

    #[error("Initialize failed: {0}")]
    InitializeFailed(String),

    #[error("tools/list failed: {0}")]
    ToolsListFailed(String),

    #[error("Tool call failed: {tool}: {error}")]
    ToolCallFailed { tool: String, error: String },

    #[error("Invalid response from upstream")]
    InvalidResponse,
}

// =============================================================================
// Federated Tool
// =============================================================================

/// A tool that proxies calls to an upstream MCP server
pub struct FederatedTool {
    /// Tool name (may include prefix)
    name: String,
    /// Original tool definition from upstream
    definition: ToolDefinition,
    /// Upstream client
    upstream: Arc<UpstreamMcpClient>,
    /// Original tool name on upstream (without prefix)
    upstream_name: String,
    /// Tenant ID this tool belongs to
    tenant_id: String,
}

impl FederatedTool {
    /// Create a new federated tool
    pub fn new(
        name: String,
        definition: ToolDefinition,
        upstream: Arc<UpstreamMcpClient>,
        upstream_name: String,
        tenant_id: String,
    ) -> Self {
        Self {
            name,
            definition,
            upstream,
            upstream_name,
            tenant_id,
        }
    }
}

#[async_trait]
impl Tool for FederatedTool {
    fn name(&self) -> &str {
        &self.name
    }

    fn description(&self) -> &str {
        &self.definition.description
    }

    fn input_schema(&self) -> ToolSchema {
        self.definition.input_schema.clone()
    }

    fn required_action(&self) -> Action {
        // Default to Read for federated tools
        // TODO: Infer from annotations if available
        Action::Read
    }

    async fn execute(&self, args: Value, ctx: &ToolContext) -> Result<ToolResult, ToolError> {
        // Tenant isolation check
        if ctx.tenant_id != self.tenant_id {
            return Err(ToolError::PermissionDenied(format!(
                "Tool {} not available for tenant {}",
                self.name, ctx.tenant_id
            )));
        }

        debug!(
            tool = %self.name,
            upstream = %self.upstream.url(),
            "Executing federated tool"
        );

        // Call upstream MCP server
        match self.upstream.call_tool(&self.upstream_name, args).await {
            Ok(result) => {
                // Extract content from MCP response
                if let Some(content) = result.get("content") {
                    if let Some(arr) = content.as_array() {
                        if let Some(first) = arr.first() {
                            if let Some(text) = first.get("text").and_then(|v| v.as_str()) {
                                return Ok(ToolResult::text(text));
                            }
                        }
                    }
                }
                // Fallback: return raw result as JSON
                Ok(ToolResult::text(
                    serde_json::to_string_pretty(&result).unwrap_or_default(),
                ))
            }
            Err(e) => Err(ToolError::ExecutionFailed(e.to_string())),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_transport_type_from_str() {
        assert_eq!(TransportType::from_str("sse"), TransportType::Sse);
        assert_eq!(TransportType::from_str("SSE"), TransportType::Sse);
        assert_eq!(
            TransportType::from_str("streamable-http"),
            TransportType::StreamableHttp
        );
        assert_eq!(TransportType::from_str("unknown"), TransportType::Sse);
    }

    #[test]
    fn test_upstream_config_default() {
        let config = UpstreamMcpConfig::default();
        assert!(config.url.is_empty());
        assert_eq!(config.transport, TransportType::Sse);
        assert!(config.auth_token.is_none());
    }

    #[test]
    fn test_parse_tool_definition() {
        let json = json!({
            "name": "test_tool",
            "description": "A test tool",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "arg1": {"type": "string"}
                },
                "required": ["arg1"]
            }
        });

        let def = parse_tool_definition(&json).unwrap();
        assert_eq!(def.name, "test_tool");
        assert_eq!(def.description, "A test tool");
        assert_eq!(def.input_schema.required.len(), 1);
    }

    #[test]
    fn test_parse_tool_definition_minimal() {
        let json = json!({
            "name": "minimal"
        });

        let def = parse_tool_definition(&json).unwrap();
        assert_eq!(def.name, "minimal");
        assert!(def.description.is_empty());
    }

    #[test]
    fn test_upstream_error_display() {
        let err = UpstreamError::ConnectionFailed("timeout".to_string());
        assert!(err.to_string().contains("Connection failed"));

        let err = UpstreamError::ToolCallFailed {
            tool: "test".to_string(),
            error: "oops".to_string(),
        };
        assert!(err.to_string().contains("test"));
    }
}
