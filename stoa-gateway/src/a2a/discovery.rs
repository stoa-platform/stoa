//! A2A Discovery Endpoints (CAB-1754)
//!
//! Implements:
//! - GET /.well-known/agent.json — Agent Card (A2A spec)
//! - GET /a2a/agents — List registered agents

use axum::{extract::State, http::StatusCode, response::IntoResponse, Json};
use serde_json::json;

use crate::state::AppState;

use super::types::{
    AgentAuthentication, AgentCapabilities, AgentCard, AgentProvider, AgentSkill,
    A2A_PROTOCOL_VERSION,
};

/// GET /.well-known/agent.json — STOA Gateway Agent Card
///
/// Returns the Agent Card for the STOA Gateway itself, describing its
/// capabilities as an A2A-enabled agent proxy/gateway.
pub async fn agent_card(State(state): State<AppState>) -> impl IntoResponse {
    let gateway_url = state
        .config
        .gateway_external_url
        .clone()
        .unwrap_or_else(|| format!("http://localhost:{}", state.config.port));

    let card = AgentCard {
        name: "STOA Gateway".to_string(),
        description: "European Agent Gateway — A2A proxy with governance, auth, rate limiting, and audit trail. Routes inter-agent tasks through policy enforcement.".to_string(),
        url: format!("{gateway_url}/a2a"),
        protocol_version: A2A_PROTOCOL_VERSION.to_string(),
        capabilities: AgentCapabilities {
            streaming: false,
            push_notifications: false,
            state_transition_history: true,
        },
        authentication: Some(AgentAuthentication {
            schemes: vec!["bearer".to_string(), "apiKey".to_string()],
            credentials: None,
        }),
        skills: vec![
            AgentSkill {
                id: "mcp-bridge".to_string(),
                name: "MCP Tool Bridge".to_string(),
                description: "Bridge MCP tools as A2A skills — any registered MCP tool can be invoked via the A2A protocol.".to_string(),
                tags: vec!["mcp".to_string(), "bridge".to_string(), "tools".to_string()],
                examples: vec!["List available tools".to_string(), "Call a REST API tool".to_string()],
                input_modes: vec!["text".to_string(), "data".to_string()],
                output_modes: vec!["text".to_string(), "data".to_string()],
            },
            AgentSkill {
                id: "agent-routing".to_string(),
                name: "Agent Routing".to_string(),
                description: "Route tasks to registered downstream agents with governance policies (auth, rate limiting, audit).".to_string(),
                tags: vec!["routing".to_string(), "governance".to_string()],
                examples: vec!["Send a task to agent X".to_string()],
                input_modes: vec!["text".to_string(), "data".to_string(), "file".to_string()],
                output_modes: vec!["text".to_string(), "data".to_string(), "file".to_string()],
            },
        ],
        provider: Some(AgentProvider {
            organization: "STOA Platform".to_string(),
            url: Some("https://gostoa.dev".to_string()),
        }),
    };

    Json(card)
}

/// GET /a2a/agents — List registered agent cards
///
/// Returns all agents registered with the gateway's A2A agent registry.
pub async fn list_agents(State(state): State<AppState>) -> impl IntoResponse {
    let Some(ref registry) = state.a2a_registry else {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({
                "error": "A2A protocol is not enabled on this gateway"
            })),
        )
            .into_response();
    };

    match registry.list_agents() {
        Ok(agents) => Json(json!({
            "agents": agents,
            "count": agents.len()
        }))
        .into_response(),
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({ "error": e.to_string() })),
        )
            .into_response(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::a2a::registry::AgentRegistry;

    // Test that agent_card returns valid JSON with correct fields
    #[test]
    fn test_agent_card_structure() {
        let card = AgentCard {
            name: "STOA Gateway".to_string(),
            description: "Test".to_string(),
            url: "http://localhost:8080/a2a".to_string(),
            protocol_version: A2A_PROTOCOL_VERSION.to_string(),
            capabilities: AgentCapabilities {
                streaming: false,
                push_notifications: false,
                state_transition_history: true,
            },
            authentication: Some(AgentAuthentication {
                schemes: vec!["bearer".to_string()],
                credentials: None,
            }),
            skills: vec![],
            provider: None,
        };

        let json = serde_json::to_value(&card).unwrap();
        assert_eq!(json["name"], "STOA Gateway");
        assert_eq!(json["protocolVersion"], A2A_PROTOCOL_VERSION);
        assert_eq!(json["capabilities"]["stateTransitionHistory"], true);
        assert!(json["authentication"]["schemes"].is_array());
    }

    #[test]
    fn test_agent_card_serialization_round_trip() {
        let card = AgentCard {
            name: "test-agent".to_string(),
            description: "A test agent".to_string(),
            url: "https://example.com/a2a".to_string(),
            protocol_version: A2A_PROTOCOL_VERSION.to_string(),
            capabilities: AgentCapabilities {
                streaming: true,
                push_notifications: false,
                state_transition_history: false,
            },
            authentication: None,
            skills: vec![AgentSkill {
                id: "echo".to_string(),
                name: "Echo".to_string(),
                description: "Echoes input back".to_string(),
                tags: vec!["test".to_string()],
                examples: vec![],
                input_modes: vec!["text".to_string()],
                output_modes: vec!["text".to_string()],
            }],
            provider: Some(AgentProvider {
                organization: "Test Org".to_string(),
                url: None,
            }),
        };

        let serialized = serde_json::to_string(&card).unwrap();
        let deserialized: AgentCard = serde_json::from_str(&serialized).unwrap();
        assert_eq!(deserialized.name, card.name);
        assert_eq!(deserialized.skills.len(), 1);
        assert_eq!(deserialized.skills[0].id, "echo");
    }

    #[test]
    fn test_registry_list_agents() {
        let registry = AgentRegistry::new(10, 100);
        let card = AgentCard {
            name: "downstream-agent".to_string(),
            description: "A downstream agent".to_string(),
            url: "https://downstream.example.com/a2a".to_string(),
            protocol_version: A2A_PROTOCOL_VERSION.to_string(),
            capabilities: AgentCapabilities {
                streaming: false,
                push_notifications: false,
                state_transition_history: false,
            },
            authentication: None,
            skills: vec![],
            provider: None,
        };

        registry.register_agent(card).unwrap();
        let agents = registry.list_agents().unwrap();
        assert_eq!(agents.len(), 1);
        assert_eq!(agents[0].name, "downstream-agent");
    }
}
