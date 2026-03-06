//! HEGEMON Fleet Dashboard (CAB-1721)
//!
//! Admin API for fleet visibility — aggregated status and event history.
//!
//! Endpoints:
//! - `GET /admin/hegemon/dashboard`  → aggregated fleet status JSON
//! - `GET /admin/hegemon/events?since=&limit=` → recent events from ring buffer
//!
//! The dashboard aggregates data from:
//! - `AgentBudgetTracker` (per-agent spend, limits)
//! - `FleetEventBuffer` (ring buffer of agent lifecycle events)

use axum::{
    extract::{Query, State},
    http::StatusCode,
    response::IntoResponse,
    Json,
};
use parking_lot::RwLock;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::time::{Duration, Instant};

use crate::state::AppState;

// === Fleet Event Buffer ===

/// Maximum events stored in the ring buffer.
const DEFAULT_EVENT_BUFFER_SIZE: usize = 1000;

/// Types of agent lifecycle events.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum EventKind {
    AgentRegistered,
    DispatchStarted,
    DispatchCompleted,
    DispatchFailed,
    BudgetWarning,
    BudgetExceeded,
}

/// A single fleet event entry.
#[derive(Debug, Clone, Serialize)]
pub struct FleetEvent {
    pub kind: EventKind,
    pub agent: String,
    pub message: String,
    pub timestamp_epoch_ms: u64,
    /// Monotonic instant for internal ordering and `since` filtering.
    #[serde(skip)]
    pub instant: Instant,
}

/// Ring buffer for fleet events.
pub struct FleetEventBuffer {
    events: RwLock<Vec<FleetEvent>>,
    max_size: usize,
}

impl FleetEventBuffer {
    pub fn new(max_size: usize) -> Self {
        Self {
            events: RwLock::new(Vec::with_capacity(max_size)),
            max_size,
        }
    }

    /// Push an event into the buffer. Oldest events are evicted when full.
    pub fn push(&self, event: FleetEvent) {
        let mut events = self.events.write();
        if events.len() >= self.max_size {
            events.remove(0);
        }
        events.push(event);
    }

    /// Record a new event with the given kind, agent and message.
    pub fn record(&self, kind: EventKind, agent: &str, message: &str) {
        let now_epoch_ms = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_millis() as u64;
        self.push(FleetEvent {
            kind,
            agent: agent.to_string(),
            message: message.to_string(),
            timestamp_epoch_ms: now_epoch_ms,
            instant: Instant::now(),
        });
    }

    /// Query events, optionally filtering by `since` (epoch ms) and limiting count.
    pub fn query(&self, since_epoch_ms: Option<u64>, limit: Option<usize>) -> Vec<FleetEvent> {
        let events = self.events.read();
        let limit = limit.unwrap_or(100).min(500);

        let iter = events.iter().rev();

        let filtered: Vec<FleetEvent> = if let Some(since) = since_epoch_ms {
            iter.filter(|e| e.timestamp_epoch_ms > since)
                .take(limit)
                .cloned()
                .collect()
        } else {
            iter.take(limit).cloned().collect()
        };

        filtered
    }

    /// Count of events currently in the buffer.
    pub fn len(&self) -> usize {
        self.events.read().len()
    }

    /// Whether the buffer is empty.
    pub fn is_empty(&self) -> bool {
        self.events.read().is_empty()
    }
}

impl Default for FleetEventBuffer {
    fn default() -> Self {
        Self::new(DEFAULT_EVENT_BUFFER_SIZE)
    }
}

// === Agent Status (per-agent view) ===

/// Per-agent registration info stored alongside budget data.
#[derive(Debug, Clone)]
pub struct AgentInfo {
    pub agent_id: String,
    pub current_dispatch: Option<String>,
    pub last_seen: Instant,
    pub last_seen_epoch_ms: u64,
}

/// Registry of known agents and their last-known state.
pub struct AgentRegistry {
    agents: RwLock<HashMap<String, AgentInfo>>,
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

    /// Register or update an agent heartbeat.
    pub fn heartbeat(&self, agent_id: &str, current_dispatch: Option<&str>) {
        let now_epoch_ms = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_millis() as u64;
        let mut agents = self.agents.write();
        let info = agents
            .entry(agent_id.to_string())
            .or_insert_with(|| AgentInfo {
                agent_id: agent_id.to_string(),
                current_dispatch: None,
                last_seen: Instant::now(),
                last_seen_epoch_ms: now_epoch_ms,
            });
        info.last_seen = Instant::now();
        info.last_seen_epoch_ms = now_epoch_ms;
        info.current_dispatch = current_dispatch.map(|s| s.to_string());
    }

    /// Get a snapshot of all agents.
    pub fn snapshot(&self) -> Vec<AgentInfo> {
        self.agents.read().values().cloned().collect()
    }

    /// Count agents seen within a given duration.
    pub fn active_count(&self, within: Duration) -> usize {
        let cutoff = Instant::now() - within;
        self.agents
            .read()
            .values()
            .filter(|a| a.last_seen > cutoff)
            .count()
    }
}

// === Response Types ===

#[derive(Debug, Serialize)]
pub struct AgentStatusResponse {
    pub agent_id: String,
    pub current_dispatch: Option<String>,
    pub cost_today_usd: f64,
    pub budget_remaining_usd: f64,
    pub last_seen_epoch_ms: u64,
    pub active: bool,
}

#[derive(Debug, Serialize)]
pub struct FleetSummary {
    pub total_agents: usize,
    pub active_agents: usize,
    pub active_dispatches: usize,
    pub daily_cost_usd: f64,
    pub budget_remaining_usd: f64,
    pub daily_limit_usd: f64,
}

#[derive(Debug, Serialize)]
pub struct DashboardResponse {
    pub fleet: FleetSummary,
    pub agents: Vec<AgentStatusResponse>,
}

#[derive(Debug, Serialize)]
pub struct EventsResponse {
    pub events: Vec<FleetEvent>,
    pub total_buffered: usize,
}

#[derive(Debug, Deserialize)]
pub struct EventsQuery {
    pub since: Option<u64>,
    pub limit: Option<usize>,
}

// === Axum Handlers ===

/// GET /admin/hegemon/dashboard
///
/// Returns aggregated fleet status with per-agent details.
pub async fn dashboard_handler(State(state): State<AppState>) -> impl IntoResponse {
    let (event_buffer, agent_registry) = match (&state.fleet_events, &state.agent_registry) {
        (Some(events), Some(registry)) => (events, registry),
        _ => {
            return (
                StatusCode::SERVICE_UNAVAILABLE,
                Json(serde_json::json!({
                    "error": "dashboard_disabled",
                    "message": "Fleet dashboard is not enabled"
                })),
            )
                .into_response();
        }
    };

    let active_window = Duration::from_secs(300); // 5 minutes
    let agents_snapshot = agent_registry.snapshot();

    let mut agent_statuses: Vec<AgentStatusResponse> = Vec::new();
    let mut total_daily_cost = 0.0_f64;
    let mut active_dispatches = 0_usize;

    for agent_info in &agents_snapshot {
        let is_active = agent_info.last_seen.elapsed() < active_window;

        // Get budget info from AgentBudgetTracker if available
        let (cost_today, remaining) = if let Some(ref tracker) = state.agent_budget {
            let check = tracker.check(&agent_info.agent_id);
            (check.daily_spent_usd, check.remaining_usd)
        } else {
            (0.0, 0.0)
        };

        total_daily_cost += cost_today;

        if agent_info.current_dispatch.is_some() && is_active {
            active_dispatches += 1;
        }

        agent_statuses.push(AgentStatusResponse {
            agent_id: agent_info.agent_id.clone(),
            current_dispatch: agent_info.current_dispatch.clone(),
            cost_today_usd: cost_today,
            budget_remaining_usd: remaining,
            last_seen_epoch_ms: agent_info.last_seen_epoch_ms,
            active: is_active,
        });
    }

    let daily_limit = state
        .agent_budget
        .as_ref()
        .map(|t| t.daily_limit_usd())
        .unwrap_or(0.0);

    let fleet = FleetSummary {
        total_agents: agents_snapshot.len(),
        active_agents: agent_registry.active_count(active_window),
        active_dispatches,
        daily_cost_usd: total_daily_cost,
        budget_remaining_usd: (daily_limit - total_daily_cost).max(0.0),
        daily_limit_usd: daily_limit,
    };

    let _ = event_buffer; // used for wiring proof; events are on the separate endpoint

    (
        StatusCode::OK,
        Json(DashboardResponse {
            fleet,
            agents: agent_statuses,
        }),
    )
        .into_response()
}

/// GET /admin/hegemon/events?since=&limit=
///
/// Returns recent fleet events from the ring buffer.
pub async fn events_handler(
    State(state): State<AppState>,
    Query(query): Query<EventsQuery>,
) -> impl IntoResponse {
    match &state.fleet_events {
        Some(buffer) => {
            let events = buffer.query(query.since, query.limit);
            let total = buffer.len();
            (
                StatusCode::OK,
                Json(EventsResponse {
                    events,
                    total_buffered: total,
                }),
            )
                .into_response()
        }
        None => (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(serde_json::json!({
                "error": "events_disabled",
                "message": "Fleet event buffer is not enabled"
            })),
        )
            .into_response(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // === FleetEventBuffer tests ===

    #[test]
    fn test_event_buffer_push_and_query() {
        let buf = FleetEventBuffer::new(10);
        buf.record(EventKind::AgentRegistered, "w1", "registered");
        buf.record(EventKind::DispatchStarted, "w1", "dispatch started");

        let events = buf.query(None, None);
        assert_eq!(events.len(), 2);
        // Most recent first
        assert_eq!(events[0].kind, EventKind::DispatchStarted);
        assert_eq!(events[1].kind, EventKind::AgentRegistered);
    }

    #[test]
    fn test_event_buffer_eviction() {
        let buf = FleetEventBuffer::new(3);
        buf.record(EventKind::AgentRegistered, "w1", "a");
        buf.record(EventKind::AgentRegistered, "w2", "b");
        buf.record(EventKind::AgentRegistered, "w3", "c");
        buf.record(EventKind::AgentRegistered, "w4", "d");

        assert_eq!(buf.len(), 3);
        let events = buf.query(None, None);
        // Oldest (w1) should be evicted
        assert_eq!(events[2].agent, "w2");
        assert_eq!(events[0].agent, "w4");
    }

    #[test]
    fn test_event_buffer_limit() {
        let buf = FleetEventBuffer::new(100);
        for i in 0..50 {
            buf.record(EventKind::DispatchStarted, &format!("w{}", i), "started");
        }

        let events = buf.query(None, Some(5));
        assert_eq!(events.len(), 5);
    }

    #[test]
    fn test_event_buffer_since_filter() {
        let buf = FleetEventBuffer::new(100);
        buf.record(EventKind::AgentRegistered, "w1", "old");
        let events = buf.query(None, None);
        let first_ts = events[0].timestamp_epoch_ms;

        // Sleep a tiny bit to get a different timestamp
        std::thread::sleep(Duration::from_millis(2));
        buf.record(EventKind::DispatchStarted, "w1", "new");

        let events = buf.query(Some(first_ts), None);
        assert_eq!(events.len(), 1);
        assert_eq!(events[0].message, "new");
    }

    #[test]
    fn test_event_buffer_limit_cap_at_500() {
        let buf = FleetEventBuffer::new(1000);
        for i in 0..700 {
            buf.record(EventKind::DispatchStarted, &format!("w{}", i), "x");
        }
        let events = buf.query(None, Some(999));
        assert_eq!(events.len(), 500); // capped
    }

    // === AgentRegistry tests ===

    #[test]
    fn test_agent_registry_heartbeat_and_snapshot() {
        let reg = AgentRegistry::new();
        reg.heartbeat("w1", Some("CAB-100"));
        reg.heartbeat("w2", None);

        let snap = reg.snapshot();
        assert_eq!(snap.len(), 2);
    }

    #[test]
    fn test_agent_registry_updates_on_heartbeat() {
        let reg = AgentRegistry::new();
        reg.heartbeat("w1", Some("CAB-100"));
        reg.heartbeat("w1", Some("CAB-200"));

        let snap = reg.snapshot();
        assert_eq!(snap.len(), 1);
        assert_eq!(snap[0].current_dispatch.as_deref(), Some("CAB-200"));
    }

    #[test]
    fn test_agent_registry_active_count() {
        let reg = AgentRegistry::new();
        reg.heartbeat("w1", None);
        reg.heartbeat("w2", None);

        // Both should be active (just registered)
        assert_eq!(reg.active_count(Duration::from_secs(60)), 2);
        // None should be active with zero window
        assert_eq!(reg.active_count(Duration::ZERO), 0);
    }

    // === FleetSummary construction ===

    #[test]
    fn test_fleet_summary_serializes() {
        let summary = FleetSummary {
            total_agents: 3,
            active_agents: 2,
            active_dispatches: 1,
            daily_cost_usd: 25.0,
            budget_remaining_usd: 25.0,
            daily_limit_usd: 50.0,
        };
        let json = serde_json::to_value(&summary).expect("serialize");
        assert_eq!(json["total_agents"], 3);
        assert_eq!(json["active_dispatches"], 1);
    }

    #[test]
    fn test_dashboard_response_serializes() {
        let resp = DashboardResponse {
            fleet: FleetSummary {
                total_agents: 1,
                active_agents: 1,
                active_dispatches: 0,
                daily_cost_usd: 10.0,
                budget_remaining_usd: 40.0,
                daily_limit_usd: 50.0,
            },
            agents: vec![AgentStatusResponse {
                agent_id: "w1".to_string(),
                current_dispatch: None,
                cost_today_usd: 10.0,
                budget_remaining_usd: 40.0,
                last_seen_epoch_ms: 1000,
                active: true,
            }],
        };
        let json = serde_json::to_value(&resp).expect("serialize");
        assert_eq!(json["fleet"]["total_agents"], 1);
        assert_eq!(json["agents"][0]["agent_id"], "w1");
    }

    #[test]
    fn test_events_response_serializes() {
        let resp = EventsResponse {
            events: vec![],
            total_buffered: 0,
        };
        let json = serde_json::to_value(&resp).expect("serialize");
        assert_eq!(json["total_buffered"], 0);
        assert!(json["events"].as_array().expect("array").is_empty());
    }
}
