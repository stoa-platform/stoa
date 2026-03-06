//! HEGEMON Fleet Dashboard — Aggregated fleet status and visibility.
//!
//! Provides admin endpoints for fleet-wide visibility: agent status,
//! active dispatches, budget usage, and event history.
//!
//! Part of CAB-1709 Phase 5b (CAB-1721).

use axum::extract::State;
use axum::response::IntoResponse;
use axum::Json;
use serde::Serialize;

// =============================================================================
// Response Types
// =============================================================================

#[derive(Serialize)]
struct AgentDashboardEntry {
    name: String,
    roles: Vec<String>,
    tier: String,
    request_count: u64,
    uptime_secs: u64,
    last_seen_secs_ago: u64,
    current_dispatch: Option<String>,
    cost_today_usd: f64,
}

#[derive(Serialize)]
struct FleetSummary {
    total_agents: usize,
    active_dispatches: usize,
    daily_cost_usd: f64,
    events_buffered: usize,
}

#[derive(Serialize)]
struct DashboardResponse {
    fleet: FleetSummary,
    agents: Vec<AgentDashboardEntry>,
}

// =============================================================================
// Handlers
// =============================================================================

/// GET /admin/hegemon/dashboard — aggregated fleet status JSON.
///
/// Composes data from all HEGEMON subsystems: registry, dispatch tracker,
/// budget tracker, and event buffer.
pub async fn fleet_dashboard(State(state): State<crate::state::AppState>) -> impl IntoResponse {
    let Some(ref heg) = state.hegemon else {
        return Json(serde_json::json!({
            "error": "hegemon_disabled",
            "message": "HEGEMON module is not enabled"
        }))
        .into_response();
    };

    // Collect per-agent data
    let agents_raw = heg.registry.list();
    let dispatches = heg.dispatch_tracker.list();
    let budgets = heg
        .budget_tracker
        .list(heg.budget_daily_usd, heg.budget_warn_pct);

    let mut agents: Vec<AgentDashboardEntry> = Vec::new();
    let mut total_daily_cost = 0.0_f64;

    for agent in &agents_raw {
        // Find current dispatch for this agent
        let current_dispatch = dispatches
            .iter()
            .find(|d| d.worker_name == agent.worker_name && d.status == "in_progress")
            .map(|d| d.dispatch_id.clone());

        // Get daily spend
        let cost_today = budgets
            .iter()
            .find(|b| b.worker_name == agent.worker_name)
            .map(|b| b.daily_spent_usd)
            .unwrap_or(0.0);
        total_daily_cost += cost_today;

        agents.push(AgentDashboardEntry {
            name: agent.worker_name.clone(),
            roles: agent.roles.clone(),
            tier: agent.tier.clone(),
            request_count: agent.request_count,
            uptime_secs: agent.uptime_secs,
            last_seen_secs_ago: agent.last_seen_secs_ago,
            current_dispatch,
            cost_today_usd: cost_today,
        });
    }

    let active_dispatches = dispatches
        .iter()
        .filter(|d| d.status == "in_progress")
        .count();
    let events_buffered = heg.metering.buffer().len();

    let response = DashboardResponse {
        fleet: FleetSummary {
            total_agents: agents.len(),
            active_dispatches,
            daily_cost_usd: total_daily_cost,
            events_buffered,
        },
        agents,
    };

    Json(response).into_response()
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_dashboard_response_serialization() {
        let response = DashboardResponse {
            fleet: FleetSummary {
                total_agents: 5,
                active_dispatches: 2,
                daily_cost_usd: 12.50,
                events_buffered: 150,
            },
            agents: vec![AgentDashboardEntry {
                name: "worker-1".to_string(),
                roles: vec!["backend".to_string()],
                tier: "autopilot".to_string(),
                request_count: 42,
                uptime_secs: 3600,
                last_seen_secs_ago: 5,
                current_dispatch: Some("d-abc-123".to_string()),
                cost_today_usd: 3.75,
            }],
        };

        let json = serde_json::to_string(&response).expect("serialize");
        assert!(json.contains("\"total_agents\":5"));
        assert!(json.contains("\"active_dispatches\":2"));
        assert!(json.contains("\"worker-1\""));
        assert!(json.contains("\"d-abc-123\""));
        assert!(json.contains("\"autopilot\""));
    }

    #[test]
    fn test_fleet_summary_empty() {
        let summary = FleetSummary {
            total_agents: 0,
            active_dispatches: 0,
            daily_cost_usd: 0.0,
            events_buffered: 0,
        };

        let json = serde_json::to_value(&summary).expect("serialize");
        assert_eq!(json["total_agents"], 0);
        assert_eq!(json["daily_cost_usd"], 0.0);
    }

    #[test]
    fn test_agent_entry_no_dispatch() {
        let agent = AgentDashboardEntry {
            name: "worker-idle".to_string(),
            roles: vec!["qa".to_string()],
            tier: "supervised".to_string(),
            request_count: 0,
            uptime_secs: 0,
            last_seen_secs_ago: 600,
            current_dispatch: None,
            cost_today_usd: 0.0,
        };

        let json = serde_json::to_value(&agent).expect("serialize");
        assert!(json["current_dispatch"].is_null());
        assert_eq!(json["cost_today_usd"], 0.0);
    }

    #[test]
    fn test_multiple_agents_serialization() {
        let response = DashboardResponse {
            fleet: FleetSummary {
                total_agents: 3,
                active_dispatches: 1,
                daily_cost_usd: 8.25,
                events_buffered: 50,
            },
            agents: vec![
                AgentDashboardEntry {
                    name: "worker-1".to_string(),
                    roles: vec!["backend".to_string()],
                    tier: "autopilot".to_string(),
                    request_count: 100,
                    uptime_secs: 7200,
                    last_seen_secs_ago: 2,
                    current_dispatch: Some("d-1".to_string()),
                    cost_today_usd: 5.00,
                },
                AgentDashboardEntry {
                    name: "worker-2".to_string(),
                    roles: vec!["frontend".to_string(), "qa".to_string()],
                    tier: "supervised".to_string(),
                    request_count: 50,
                    uptime_secs: 3600,
                    last_seen_secs_ago: 120,
                    current_dispatch: None,
                    cost_today_usd: 3.25,
                },
                AgentDashboardEntry {
                    name: "worker-3".to_string(),
                    roles: vec!["mcp".to_string()],
                    tier: "autopilot".to_string(),
                    request_count: 75,
                    uptime_secs: 5400,
                    last_seen_secs_ago: 10,
                    current_dispatch: None,
                    cost_today_usd: 0.0,
                },
            ],
        };

        let json = serde_json::to_value(&response).expect("serialize");
        assert_eq!(json["agents"].as_array().expect("array").len(), 3);
        assert_eq!(json["fleet"]["daily_cost_usd"], 8.25);
    }
}
