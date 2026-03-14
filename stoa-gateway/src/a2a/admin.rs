//! A2A Admin Handlers (CAB-1754)
//!
//! CRUD operations for managing A2A agent registrations.
//! Protected by the admin API auth middleware.
//!
//! Endpoints (nested under /admin):
//! - POST   /a2a/agents      — Register a new agent
//! - DELETE  /a2a/agents/:name — Unregister an agent
//! - GET    /a2a/agents       — List all registered agents (admin view)
//! - GET    /a2a/agents/:name — Get a specific agent card

use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::IntoResponse,
    Json,
};
use serde_json::json;

use crate::state::AppState;

use super::types::AgentCard;

/// POST /admin/a2a/agents — Register a new downstream agent.
pub async fn register_agent(
    State(state): State<AppState>,
    Json(card): Json<AgentCard>,
) -> impl IntoResponse {
    let Some(ref registry) = state.a2a_registry else {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({"error": "A2A protocol is not enabled"})),
        )
            .into_response();
    };

    match registry.register_agent(card) {
        Ok(is_new) => {
            let status = if is_new {
                StatusCode::CREATED
            } else {
                StatusCode::OK
            };
            (
                status,
                Json(json!({
                    "status": if is_new { "registered" } else { "updated" }
                })),
            )
                .into_response()
        }
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"error": e.to_string()})),
        )
            .into_response(),
    }
}

/// DELETE /admin/a2a/agents/:name — Unregister an agent by name.
pub async fn unregister_agent(
    State(state): State<AppState>,
    Path(name): Path<String>,
) -> impl IntoResponse {
    let Some(ref registry) = state.a2a_registry else {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({"error": "A2A protocol is not enabled"})),
        )
            .into_response();
    };

    match registry.unregister_agent(&name) {
        Ok(true) => (StatusCode::OK, Json(json!({"status": "unregistered"}))).into_response(),
        Ok(false) => (
            StatusCode::NOT_FOUND,
            Json(json!({"error": format!("Agent not found: {name}")})),
        )
            .into_response(),
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"error": e.to_string()})),
        )
            .into_response(),
    }
}

/// GET /admin/a2a/agents — List all registered agents (admin view with count).
pub async fn list_agents(State(state): State<AppState>) -> impl IntoResponse {
    let Some(ref registry) = state.a2a_registry else {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({"error": "A2A protocol is not enabled"})),
        )
            .into_response();
    };

    match registry.list_agents() {
        Ok(agents) => {
            let count = agents.len();
            Json(json!({
                "agents": agents,
                "count": count,
                "protocol_version": super::types::A2A_PROTOCOL_VERSION,
            }))
            .into_response()
        }
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"error": e.to_string()})),
        )
            .into_response(),
    }
}

/// GET /admin/a2a/agents/:name — Get a specific agent card.
pub async fn get_agent(
    State(state): State<AppState>,
    Path(name): Path<String>,
) -> impl IntoResponse {
    let Some(ref registry) = state.a2a_registry else {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({"error": "A2A protocol is not enabled"})),
        )
            .into_response();
    };

    match registry.get_agent(&name) {
        Ok(Some(card)) => Json(json!(card)).into_response(),
        Ok(None) => (
            StatusCode::NOT_FOUND,
            Json(json!({"error": format!("Agent not found: {name}")})),
        )
            .into_response(),
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"error": e.to_string()})),
        )
            .into_response(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::a2a::types::*;
    use crate::config::Config;

    fn make_state() -> AppState {
        AppState::new(Config {
            a2a_enabled: true,
            ..Config::default()
        })
    }

    fn test_card(name: &str) -> AgentCard {
        AgentCard {
            name: name.to_string(),
            description: format!("Test agent {name}"),
            url: format!("https://example.com/agents/{name}"),
            protocol_version: A2A_PROTOCOL_VERSION.to_string(),
            capabilities: AgentCapabilities {
                streaming: false,
                push_notifications: false,
                state_transition_history: false,
            },
            authentication: None,
            skills: vec![],
            provider: None,
        }
    }

    #[test]
    fn test_register_via_registry() {
        let state = make_state();
        let registry = state.a2a_registry.as_ref().unwrap();
        assert!(registry.register_agent(test_card("alpha")).unwrap());
        assert_eq!(registry.agent_count().unwrap(), 1);
    }

    #[test]
    fn test_unregister_via_registry() {
        let state = make_state();
        let registry = state.a2a_registry.as_ref().unwrap();
        registry.register_agent(test_card("alpha")).unwrap();
        assert!(registry.unregister_agent("alpha").unwrap());
        assert_eq!(registry.agent_count().unwrap(), 0);
    }

    #[test]
    fn test_get_agent_via_registry() {
        let state = make_state();
        let registry = state.a2a_registry.as_ref().unwrap();
        registry.register_agent(test_card("alpha")).unwrap();
        let card = registry.get_agent("alpha").unwrap().unwrap();
        assert_eq!(card.name, "alpha");
        assert_eq!(card.protocol_version, A2A_PROTOCOL_VERSION);
    }
}
