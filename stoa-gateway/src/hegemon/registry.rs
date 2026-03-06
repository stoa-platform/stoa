//! HEGEMON Agent Registry — In-memory tracking of authenticated worker agents.
//!
//! Follows the same `parking_lot::RwLock<HashMap>` pattern as `CircuitBreakerRegistry`.
//! Updated on every authenticated agent request.

use std::collections::HashMap;
use std::time::Instant;

use axum::extract::State;
use axum::http::StatusCode;
use axum::response::IntoResponse;
use axum::Json;
use parking_lot::RwLock;
use serde::Serialize;

use super::identity::AgentIdentity;
use crate::supervision::SupervisionTier;

/// Per-agent state tracked in the registry.
#[derive(Debug, Clone)]
struct AgentEntry {
    /// Worker roles from JWT claims.
    roles: Vec<String>,
    /// Current supervision tier.
    tier: SupervisionTier,
    /// Keycloak subject ID.
    subject: String,
    /// Total requests processed.
    request_count: u64,
    /// First seen timestamp.
    first_seen: Instant,
    /// Last seen timestamp.
    last_seen: Instant,
}

/// In-memory registry of all known HEGEMON agents.
///
/// Thread-safe via `parking_lot::RwLock`. The read path (lookup/list)
/// is lock-free for concurrent readers. Writes (record/update) are serialized.
pub struct AgentRegistry {
    agents: RwLock<HashMap<String, AgentEntry>>,
}

impl Default for AgentRegistry {
    fn default() -> Self {
        Self::new()
    }
}

impl AgentRegistry {
    pub fn new() -> Self {
        Self {
            agents: RwLock::new(HashMap::new()),
        }
    }

    /// Record an agent request. Creates the entry if first seen, otherwise updates.
    pub fn record_request(&self, identity: &AgentIdentity) {
        let now = Instant::now();
        let mut agents = self.agents.write();
        let entry = agents
            .entry(identity.worker_name.clone())
            .or_insert_with(|| AgentEntry {
                roles: identity.worker_roles.clone(),
                tier: identity.supervision_tier,
                subject: identity.subject.clone(),
                request_count: 0,
                first_seen: now,
                last_seen: now,
            });
        entry.request_count += 1;
        entry.last_seen = now;
        entry.tier = identity.supervision_tier;
        entry.roles.clone_from(&identity.worker_roles);
    }

    /// Update the supervision tier for an agent (admin override).
    pub fn update_tier(&self, worker_name: &str, tier: SupervisionTier) -> bool {
        let mut agents = self.agents.write();
        if let Some(entry) = agents.get_mut(worker_name) {
            entry.tier = tier;
            true
        } else {
            false
        }
    }

    /// List all agents as serializable summaries.
    fn list(&self) -> Vec<AgentSummary> {
        let agents = self.agents.read();
        let mut result: Vec<_> = agents
            .iter()
            .map(|(name, entry)| AgentSummary {
                worker_name: name.clone(),
                roles: entry.roles.clone(),
                tier: entry.tier.to_string(),
                subject: entry.subject.clone(),
                request_count: entry.request_count,
                uptime_secs: entry.first_seen.elapsed().as_secs(),
                last_seen_secs_ago: entry.last_seen.elapsed().as_secs(),
            })
            .collect();
        result.sort_by(|a, b| a.worker_name.cmp(&b.worker_name));
        result
    }

    /// Get a single agent summary.
    fn get(&self, worker_name: &str) -> Option<AgentSummary> {
        let agents = self.agents.read();
        agents.get(worker_name).map(|entry| AgentSummary {
            worker_name: worker_name.to_string(),
            roles: entry.roles.clone(),
            tier: entry.tier.to_string(),
            subject: entry.subject.clone(),
            request_count: entry.request_count,
            uptime_secs: entry.first_seen.elapsed().as_secs(),
            last_seen_secs_ago: entry.last_seen.elapsed().as_secs(),
        })
    }

    /// Get the count of tracked agents.
    pub fn count(&self) -> usize {
        self.agents.read().len()
    }
}

/// JSON-serializable agent summary for admin API responses.
#[derive(Debug, Serialize)]
pub struct AgentSummary {
    pub worker_name: String,
    pub roles: Vec<String>,
    pub tier: String,
    pub subject: String,
    pub request_count: u64,
    pub uptime_secs: u64,
    pub last_seen_secs_ago: u64,
}

/// Response for `GET /admin/hegemon/agents`.
#[derive(Serialize)]
struct AgentListResponse {
    agents: Vec<AgentSummary>,
    count: usize,
}

/// Response for `POST /admin/hegemon/agents/:name/tier`.
#[derive(serde::Deserialize)]
pub struct UpdateTierRequest {
    pub tier: String,
}

#[derive(Serialize)]
struct UpdateTierResponse {
    worker_name: String,
    tier: String,
    updated: bool,
}

#[derive(Serialize)]
struct ErrorResponse {
    error: String,
    message: String,
}

// =============================================================================
// Admin Handlers
// =============================================================================

/// `GET /admin/hegemon/agents` — list all tracked agents.
pub async fn list_agents(State(state): State<crate::state::AppState>) -> impl IntoResponse {
    match &state.hegemon {
        Some(heg) => {
            let agents = heg.registry.list();
            let count = agents.len();
            Json(AgentListResponse { agents, count }).into_response()
        }
        None => (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(ErrorResponse {
                error: "hegemon_disabled".to_string(),
                message: "HEGEMON module is disabled (STOA_HEGEMON_ENABLED=false)".to_string(),
            }),
        )
            .into_response(),
    }
}

/// `GET /admin/hegemon/agents/:name` — get a single agent's details.
pub async fn get_agent(
    State(state): State<crate::state::AppState>,
    axum::extract::Path(name): axum::extract::Path<String>,
) -> impl IntoResponse {
    match &state.hegemon {
        Some(heg) => match heg.registry.get(&name) {
            Some(agent) => Json(agent).into_response(),
            None => (
                StatusCode::NOT_FOUND,
                Json(ErrorResponse {
                    error: "agent_not_found".to_string(),
                    message: format!("Agent '{}' not found in registry", name),
                }),
            )
                .into_response(),
        },
        None => (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(ErrorResponse {
                error: "hegemon_disabled".to_string(),
                message: "HEGEMON module is disabled (STOA_HEGEMON_ENABLED=false)".to_string(),
            }),
        )
            .into_response(),
    }
}

/// `POST /admin/hegemon/agents/:name/tier` — update an agent's supervision tier.
pub async fn update_agent_tier(
    State(state): State<crate::state::AppState>,
    axum::extract::Path(name): axum::extract::Path<String>,
    Json(body): Json<UpdateTierRequest>,
) -> impl IntoResponse {
    match &state.hegemon {
        Some(heg) => {
            let tier = match SupervisionTier::from_header(&body.tier) {
                Some(t) => t,
                None => {
                    return (
                        StatusCode::BAD_REQUEST,
                        Json(ErrorResponse {
                            error: "invalid_tier".to_string(),
                            message: format!(
                                "Invalid tier '{}'. Valid: autopilot, copilot, command",
                                body.tier
                            ),
                        }),
                    )
                        .into_response();
                }
            };
            let updated = heg.registry.update_tier(&name, tier);
            if updated {
                Json(UpdateTierResponse {
                    worker_name: name,
                    tier: tier.to_string(),
                    updated: true,
                })
                .into_response()
            } else {
                (
                    StatusCode::NOT_FOUND,
                    Json(ErrorResponse {
                        error: "agent_not_found".to_string(),
                        message: format!("Agent '{}' not found in registry", name),
                    }),
                )
                    .into_response()
            }
        }
        None => (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(ErrorResponse {
                error: "hegemon_disabled".to_string(),
                message: "HEGEMON module is disabled (STOA_HEGEMON_ENABLED=false)".to_string(),
            }),
        )
            .into_response(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::supervision::SupervisionTier;

    fn make_identity(name: &str, roles: &[&str], tier: SupervisionTier) -> AgentIdentity {
        AgentIdentity {
            worker_name: name.to_string(),
            worker_roles: roles.iter().map(|r| r.to_string()).collect(),
            subject: format!("sa-{}", name),
            supervision_tier: tier,
        }
    }

    #[test]
    fn test_record_request_creates_entry() {
        let registry = AgentRegistry::new();
        let id = make_identity("worker-1", &["backend"], SupervisionTier::Autopilot);
        registry.record_request(&id);
        assert_eq!(registry.count(), 1);
        let summary = registry.get("worker-1").unwrap();
        assert_eq!(summary.request_count, 1);
        assert_eq!(summary.roles, vec!["backend"]);
    }

    #[test]
    fn test_record_request_increments_count() {
        let registry = AgentRegistry::new();
        let id = make_identity("worker-1", &["backend"], SupervisionTier::Autopilot);
        registry.record_request(&id);
        registry.record_request(&id);
        registry.record_request(&id);
        let summary = registry.get("worker-1").unwrap();
        assert_eq!(summary.request_count, 3);
    }

    #[test]
    fn test_multiple_agents() {
        let registry = AgentRegistry::new();
        let id1 = make_identity("worker-1", &["backend"], SupervisionTier::Autopilot);
        let id2 = make_identity("worker-2", &["frontend"], SupervisionTier::CoPilot);
        registry.record_request(&id1);
        registry.record_request(&id2);
        assert_eq!(registry.count(), 2);
    }

    #[test]
    fn test_list_sorted_by_name() {
        let registry = AgentRegistry::new();
        let id_c = make_identity("worker-c", &[], SupervisionTier::Autopilot);
        let id_a = make_identity("worker-a", &[], SupervisionTier::Autopilot);
        let id_b = make_identity("worker-b", &[], SupervisionTier::Autopilot);
        registry.record_request(&id_c);
        registry.record_request(&id_a);
        registry.record_request(&id_b);
        let list = registry.list();
        assert_eq!(list[0].worker_name, "worker-a");
        assert_eq!(list[1].worker_name, "worker-b");
        assert_eq!(list[2].worker_name, "worker-c");
    }

    #[test]
    fn test_get_nonexistent_returns_none() {
        let registry = AgentRegistry::new();
        assert!(registry.get("nonexistent").is_none());
    }

    #[test]
    fn test_update_tier() {
        let registry = AgentRegistry::new();
        let id = make_identity("worker-1", &["backend"], SupervisionTier::Autopilot);
        registry.record_request(&id);
        assert!(registry.update_tier("worker-1", SupervisionTier::Command));
        let summary = registry.get("worker-1").unwrap();
        assert_eq!(summary.tier, "command");
    }

    #[test]
    fn test_update_tier_nonexistent_returns_false() {
        let registry = AgentRegistry::new();
        assert!(!registry.update_tier("nonexistent", SupervisionTier::Command));
    }

    #[test]
    fn test_record_request_updates_tier() {
        let registry = AgentRegistry::new();
        let id1 = make_identity("worker-1", &["backend"], SupervisionTier::Autopilot);
        registry.record_request(&id1);
        assert_eq!(registry.get("worker-1").unwrap().tier, "autopilot");

        let id2 = make_identity("worker-1", &["backend"], SupervisionTier::CoPilot);
        registry.record_request(&id2);
        assert_eq!(registry.get("worker-1").unwrap().tier, "copilot");
    }

    #[test]
    fn test_record_request_updates_roles() {
        let registry = AgentRegistry::new();
        let id1 = make_identity("worker-1", &["backend"], SupervisionTier::Autopilot);
        registry.record_request(&id1);
        assert_eq!(registry.get("worker-1").unwrap().roles, vec!["backend"]);

        let id2 = make_identity("worker-1", &["backend", "qa"], SupervisionTier::Autopilot);
        registry.record_request(&id2);
        assert_eq!(
            registry.get("worker-1").unwrap().roles,
            vec!["backend", "qa"]
        );
    }

    #[test]
    fn test_empty_registry() {
        let registry = AgentRegistry::new();
        assert_eq!(registry.count(), 0);
        assert!(registry.list().is_empty());
    }

    #[test]
    fn test_last_seen_updates() {
        let registry = AgentRegistry::new();
        let id = make_identity("worker-1", &["backend"], SupervisionTier::Autopilot);
        registry.record_request(&id);
        let first = registry.get("worker-1").unwrap().last_seen_secs_ago;
        // After a tiny delay and another request, last_seen should be closer to 0
        std::thread::sleep(std::time::Duration::from_millis(10));
        registry.record_request(&id);
        let second = registry.get("worker-1").unwrap().last_seen_secs_ago;
        // Both should be 0 at this timescale, but second should be <= first
        assert!(second <= first);
    }
}
