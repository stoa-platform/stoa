//! MCP Discovery Endpoints
//!
//! Implements:
//! - GET /mcp - Server discovery
//! - GET /mcp/capabilities - Detailed capabilities

use axum::{extract::State, http::StatusCode, response::IntoResponse, Json};
use serde::Serialize;
use serde_json::json;

use crate::state::AppState;

/// MCP Protocol Version (latest supported)
pub const MCP_PROTOCOL_VERSION: &str = "2025-03-26";

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
pub async fn mcp_discovery(State(_state): State<AppState>) -> impl IntoResponse {
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
    #[serde(skip_serializing_if = "Option::is_none")]
    pub notifications: Option<NotificationsCapability>,
}

#[derive(Debug, Serialize)]
pub struct NotificationsCapability {
    pub supported: bool,
    pub types: Vec<String>,
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
            notifications: Some(NotificationsCapability {
                supported: true,
                types: vec![
                    "stoa.api.lifecycle".to_string(),
                    "stoa.deployment.events".to_string(),
                    "stoa.security.alerts".to_string(),
                    "stoa.subscription.events".to_string(),
                ],
            }),
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
        assert_eq!(MCP_PROTOCOL_VERSION, "2025-03-26");
    }

    #[test]
    fn test_discovery_response_serialization() {
        let resp = DiscoveryResponse {
            server: ServerInfo {
                name: "STOA Gateway".to_string(),
                version: "0.1.0".to_string(),
                protocol_version: MCP_PROTOCOL_VERSION.to_string(),
            },
            endpoints: EndpointInfo {
                sse: "/mcp/sse".to_string(),
                tools_list: "/mcp/tools/list".to_string(),
                tools_call: "/mcp/tools/call".to_string(),
                capabilities: "/mcp/capabilities".to_string(),
            },
        };

        let json = serde_json::to_value(&resp).unwrap();
        assert_eq!(json["server"]["protocolVersion"], "2025-03-26");
        assert_eq!(json["endpoints"]["sse"], "/mcp/sse");
        assert_eq!(json["endpoints"]["tools_list"], "/mcp/tools/list");
        assert_eq!(json["endpoints"]["tools_call"], "/mcp/tools/call");
        assert_eq!(json["endpoints"]["capabilities"], "/mcp/capabilities");
    }

    #[test]
    fn test_capabilities_response_serialization() {
        let resp = CapabilitiesResponse {
            protocol_version: MCP_PROTOCOL_VERSION.to_string(),
            capabilities: Capabilities {
                tools: ToolsCapability {
                    list_changed: false,
                },
                resources: ResourcesCapability {
                    subscribe: false,
                    list_changed: false,
                },
                prompts: PromptsCapability {
                    list_changed: false,
                },
                logging: LoggingCapability {},
                notifications: None,
            },
            server_info: ServerInfo {
                name: "STOA Gateway".to_string(),
                version: "0.1.0".to_string(),
                protocol_version: MCP_PROTOCOL_VERSION.to_string(),
            },
        };

        let json = serde_json::to_value(&resp).unwrap();
        assert_eq!(json["protocolVersion"], "2025-03-26");
        assert_eq!(json["capabilities"]["tools"]["listChanged"], false);
        assert_eq!(json["capabilities"]["resources"]["subscribe"], false);
        assert_eq!(json["serverInfo"]["name"], "STOA Gateway");
        // notifications is None → should be omitted
        assert!(json["capabilities"]["notifications"].is_null());
    }

    #[test]
    fn test_notifications_capability_serialization() {
        let cap = Capabilities {
            tools: ToolsCapability {
                list_changed: false,
            },
            resources: ResourcesCapability {
                subscribe: false,
                list_changed: false,
            },
            prompts: PromptsCapability {
                list_changed: false,
            },
            logging: LoggingCapability {},
            notifications: Some(NotificationsCapability {
                supported: true,
                types: vec!["stoa.api.lifecycle".to_string()],
            }),
        };
        let json = serde_json::to_value(&cap).unwrap();
        assert_eq!(json["notifications"]["supported"], true);
        assert_eq!(json["notifications"]["types"][0], "stoa.api.lifecycle");
    }

    #[test]
    fn test_server_info_rename_fields() {
        let info = ServerInfo {
            name: "test".to_string(),
            version: "1.0".to_string(),
            protocol_version: "2025-03-26".to_string(),
        };
        let json = serde_json::to_value(&info).unwrap();
        // protocolVersion is camelCase via #[serde(rename)]
        assert!(json.get("protocolVersion").is_some());
        assert!(json.get("protocol_version").is_none());
    }

    #[test]
    fn test_capabilities_rename_fields() {
        let cap = ToolsCapability { list_changed: true };
        let json = serde_json::to_value(&cap).unwrap();
        assert!(json.get("listChanged").is_some());
        assert!(json.get("list_changed").is_none());
    }

    #[test]
    fn test_endpoint_info_all_fields() {
        let endpoints = EndpointInfo {
            sse: "/a".to_string(),
            tools_list: "/b".to_string(),
            tools_call: "/c".to_string(),
            capabilities: "/d".to_string(),
        };
        let json = serde_json::to_value(&endpoints).unwrap();
        assert_eq!(json.as_object().unwrap().len(), 4);
    }
}
