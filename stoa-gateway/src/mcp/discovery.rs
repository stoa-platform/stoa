//! MCP Discovery Endpoints
//!
//! Implements:
//! - GET /mcp - Server discovery
//! - GET /mcp/capabilities - Detailed capabilities

use axum::{extract::State, http::StatusCode, response::IntoResponse, Json};
use serde::{Deserialize, Serialize};
use serde_json::json;

use crate::state::AppState;

/// MCP Protocol Version
pub const MCP_PROTOCOL_VERSION: &str = "2024-11-05";

/// Server info for discovery
#[derive(Debug, Serialize)]
pub struct ServerInfo {
    pub name: String,
    pub version: String,
    #[serde(rename = "protocolVersion")]
    pub protocol_version: String,
}

/// Discovery response
#[derive(Debug, Serialize)]
pub struct DiscoveryResponse {
    pub server: ServerInfo,
    pub endpoints: EndpointInfo,
}

#[derive(Debug, Serialize)]
pub struct EndpointInfo {
    pub sse: String,
    pub tools_list: String,
    pub tools_call: String,
    pub capabilities: String,
}

/// GET /mcp - Server Discovery
pub async fn mcp_discovery(State(state): State<AppState>) -> impl IntoResponse {
    let response = DiscoveryResponse {
        server: ServerInfo {
            name: "STOA Gateway".to_string(),
            version: env!("CARGO_PKG_VERSION").to_string(),
            protocol_version: MCP_PROTOCOL_VERSION.to_string(),
        },
        endpoints: EndpointInfo {
            sse: "/mcp/sse".to_string(),
            tools_list: "/mcp/tools/list".to_string(),
            tools_call: "/mcp/tools/call".to_string(),
            capabilities: "/mcp/capabilities".to_string(),
        },
    };

    Json(response)
}

/// Capabilities response
#[derive(Debug, Serialize)]
pub struct CapabilitiesResponse {
    #[serde(rename = "protocolVersion")]
    pub protocol_version: String,
    pub capabilities: Capabilities,
    #[serde(rename = "serverInfo")]
    pub server_info: ServerInfo,
}

#[derive(Debug, Serialize)]
pub struct Capabilities {
    pub tools: ToolsCapability,
    pub resources: ResourcesCapability,
    pub prompts: PromptsCapability,
    pub logging: LoggingCapability,
}

#[derive(Debug, Serialize)]
pub struct ToolsCapability {
    #[serde(rename = "listChanged")]
    pub list_changed: bool,
}

#[derive(Debug, Serialize)]
pub struct ResourcesCapability {
    pub subscribe: bool,
    #[serde(rename = "listChanged")]
    pub list_changed: bool,
}

#[derive(Debug, Serialize)]
pub struct PromptsCapability {
    #[serde(rename = "listChanged")]
    pub list_changed: bool,
}

#[derive(Debug, Serialize)]
pub struct LoggingCapability {}

/// GET /mcp/capabilities - Detailed server capabilities
pub async fn mcp_capabilities(State(state): State<AppState>) -> impl IntoResponse {
    let tool_count = state.tool_registry.count();

    let response = CapabilitiesResponse {
        protocol_version: MCP_PROTOCOL_VERSION.to_string(),
        capabilities: Capabilities {
            tools: ToolsCapability {
                list_changed: false, // We don't support dynamic tool changes yet
            },
            resources: ResourcesCapability {
                subscribe: false,
                list_changed: false,
            },
            prompts: PromptsCapability {
                list_changed: false,
            },
            logging: LoggingCapability {},
        },
        server_info: ServerInfo {
            name: "STOA Gateway".to_string(),
            version: env!("CARGO_PKG_VERSION").to_string(),
            protocol_version: MCP_PROTOCOL_VERSION.to_string(),
        },
    };

    (
        StatusCode::OK,
        [("X-MCP-Tool-Count", tool_count.to_string())],
        Json(response),
    )
}

/// GET /mcp/health - MCP-specific health check
pub async fn mcp_health(State(state): State<AppState>) -> impl IntoResponse {
    let tool_count = state.tool_registry.count();
    let session_count = state.session_manager.count();

    Json(json!({
        "status": "healthy",
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "tools": tool_count,
        "activeSessions": session_count
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_protocol_version() {
        assert_eq!(MCP_PROTOCOL_VERSION, "2024-11-05");
    }
}
