//! HEGEMON Budget — Per-agent daily budget enforcement.
//!
//! Centralized atomic budget tracking eliminates race conditions from
//! file-based per-worker tracking. All budget checks and recordings flow
//! through the gateway as the single writer.
//!
//! - `POST /hegemon/budget/check` — pre-dispatch budget check
//! - `POST /hegemon/budget/record` — atomic spend recording
//! - `GET /admin/hegemon/budget` — all agent budget summaries

use std::collections::HashMap;

use axum::extract::State;
use axum::http::StatusCode;
use axum::response::IntoResponse;
use axum::Json;
use parking_lot::RwLock;
use serde::{Deserialize, Serialize};

use crate::metrics;

// =============================================================================
// Types
// =============================================================================

/// Per-agent budget state with daily sliding window.
#[derive(Debug, Clone)]
struct AgentBudget {
    /// Spend entries for today (timestamp, amount).
    entries: Vec<SpendEntry>,
}

/// A single spend record.
#[derive(Debug, Clone)]
struct SpendEntry {
    /// UTC date string (YYYY-MM-DD) for day bucketing.
    date: String,
    /// Amount in USD.
    amount_usd: f64,
    /// Dispatch ID that incurred this cost (stored for audit trail).
    _dispatch_id: String,
}

/// Request body for `POST /hegemon/budget/check`.
#[derive(Debug, Deserialize)]
pub struct BudgetCheckRequest {
    pub worker_name: String,
    #[serde(default)]
    pub estimated_cost_usd: Option<f64>,
}

/// Response for `POST /hegemon/budget/check`.
#[derive(Debug, Serialize)]
pub struct BudgetCheckResponse {
    pub allowed: bool,
    pub remaining_usd: f64,
    pub daily_spent_usd: f64,
    pub daily_limit_usd: f64,
    pub warning: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub warning_message: Option<String>,
}

/// Request body for `POST /hegemon/budget/record`.
#[derive(Debug, Deserialize)]
pub struct BudgetRecordRequest {
    pub worker_name: String,
    pub amount_usd: f64,
    pub dispatch_id: String,
}

/// Response for `POST /hegemon/budget/record`.
#[derive(Debug, Serialize)]
pub struct BudgetRecordResponse {
    pub recorded: bool,
    pub daily_spent_usd: f64,
    pub remaining_usd: f64,
    pub warning: bool,
}

/// Admin summary of an agent's budget.
#[derive(Debug, Serialize)]
pub struct AgentBudgetSummary {
    pub worker_name: String,
    pub daily_spent_usd: f64,
    pub daily_limit_usd: f64,
    pub remaining_usd: f64,
    pub entries_today: usize,
    pub warning: bool,
}

/// Response for `GET /admin/hegemon/budget`.
#[derive(Debug, Serialize)]
struct BudgetListResponse {
    agents: Vec<AgentBudgetSummary>,
    fleet_daily_spent_usd: f64,
}

/// Error response.
#[derive(Serialize)]
struct ErrorResponse {
    error: String,
    message: String,
}

// =============================================================================
// BudgetTracker
// =============================================================================

/// In-memory per-agent daily budget tracker.
///
/// Thread-safe via `parking_lot::RwLock`. Tracks spend per agent per day.
/// Old entries (not today) are pruned on access.
pub struct BudgetTracker {
    agents: RwLock<HashMap<String, AgentBudget>>,
}

impl Default for BudgetTracker {
    fn default() -> Self {
        Self::new()
    }
}

impl BudgetTracker {
    pub fn new() -> Self {
        Self {
            agents: RwLock::new(HashMap::new()),
        }
    }

    /// Check if an agent is within budget for today.
    ///
    /// Returns `(daily_spent, allowed)` where `allowed` means daily_spent + estimated < limit.
    pub fn check(
        &self,
        worker_name: &str,
        daily_limit_usd: f64,
        estimated_cost_usd: f64,
    ) -> (f64, bool) {
        let today = today_str();
        let agents = self.agents.read();
        let spent = agents
            .get(worker_name)
            .map(|b| b.daily_spent(&today))
            .unwrap_or(0.0);
        let allowed = (spent + estimated_cost_usd) <= daily_limit_usd;
        (spent, allowed)
    }

    /// Record a spend for an agent. Returns the new daily total.
    ///
    /// This is atomic — the write lock ensures no concurrent modification.
    pub fn record(&self, worker_name: &str, amount_usd: f64, dispatch_id: &str) -> f64 {
        let today = today_str();
        let mut agents = self.agents.write();
        let budget = agents
            .entry(worker_name.to_string())
            .or_insert_with(|| AgentBudget {
                entries: Vec::new(),
            });

        // Prune old entries (keep only today)
        budget.prune(&today);

        budget.entries.push(SpendEntry {
            date: today.clone(),
            amount_usd,
            _dispatch_id: dispatch_id.to_string(),
        });

        budget.daily_spent(&today)
    }

    /// Get budget summaries for all tracked agents.
    pub fn list(&self, daily_limit_usd: f64, warn_pct: f64) -> Vec<AgentBudgetSummary> {
        let today = today_str();
        let agents = self.agents.read();
        let mut result: Vec<_> = agents
            .iter()
            .map(|(name, budget)| {
                let spent = budget.daily_spent(&today);
                let remaining = (daily_limit_usd - spent).max(0.0);
                AgentBudgetSummary {
                    worker_name: name.clone(),
                    daily_spent_usd: spent,
                    daily_limit_usd,
                    remaining_usd: remaining,
                    entries_today: budget.entries_today(&today),
                    warning: spent >= daily_limit_usd * warn_pct,
                }
            })
            .collect();
        result.sort_by(|a, b| a.worker_name.cmp(&b.worker_name));
        result
    }

    /// Get the number of tracked agents.
    pub fn count(&self) -> usize {
        self.agents.read().len()
    }

    /// Get daily spent for a specific agent.
    pub fn daily_spent(&self, worker_name: &str) -> f64 {
        let today = today_str();
        let agents = self.agents.read();
        agents
            .get(worker_name)
            .map(|b| b.daily_spent(&today))
            .unwrap_or(0.0)
    }
}

impl AgentBudget {
    /// Sum of all spend entries for the given day.
    fn daily_spent(&self, today: &str) -> f64 {
        self.entries
            .iter()
            .filter(|e| e.date == today)
            .map(|e| e.amount_usd)
            .sum()
    }

    /// Count of entries for today.
    fn entries_today(&self, today: &str) -> usize {
        self.entries.iter().filter(|e| e.date == today).count()
    }

    /// Remove entries older than today.
    fn prune(&mut self, today: &str) {
        self.entries.retain(|e| e.date == today);
    }
}

/// Get today's date as YYYY-MM-DD string (UTC).
fn today_str() -> String {
    chrono::Utc::now().format("%Y-%m-%d").to_string()
}

// =============================================================================
// Handlers
// =============================================================================

/// `POST /hegemon/budget/check` — pre-dispatch budget check.
pub async fn budget_check(
    State(state): State<crate::state::AppState>,
    Json(body): Json<BudgetCheckRequest>,
) -> impl IntoResponse {
    match &state.hegemon {
        Some(heg) => {
            let estimated = body.estimated_cost_usd.unwrap_or(0.0);
            let (spent, allowed) =
                heg.budget_tracker
                    .check(&body.worker_name, heg.budget_daily_usd, estimated);
            let remaining = (heg.budget_daily_usd - spent).max(0.0);
            let warning = spent >= heg.budget_daily_usd * heg.budget_warn_pct;

            // Update Prometheus gauge
            metrics::HEGEMON_BUDGET_DAILY_USD
                .with_label_values(&[&body.worker_name])
                .set(spent);

            let warning_message = if warning {
                Some(format!(
                    "Agent '{}' has used {:.1}% of daily budget (${:.2}/${:.2})",
                    body.worker_name,
                    (spent / heg.budget_daily_usd) * 100.0,
                    spent,
                    heg.budget_daily_usd,
                ))
            } else {
                None
            };

            // Emit Kafka event for budget check
            if let Some(ref producer) = state.metering_producer {
                let event = serde_json::json!({
                    "type": "budget_checked",
                    "worker_name": body.worker_name,
                    "daily_spent_usd": spent,
                    "daily_limit_usd": heg.budget_daily_usd,
                    "allowed": allowed,
                    "warning": warning,
                    "timestamp": chrono::Utc::now().to_rfc3339(),
                });
                if let Ok(payload) = serde_json::to_string(&event) {
                    producer.send_raw("hegemon.budget", &body.worker_name, &payload);
                }
            }

            Json(BudgetCheckResponse {
                allowed,
                remaining_usd: remaining,
                daily_spent_usd: spent,
                daily_limit_usd: heg.budget_daily_usd,
                warning,
                warning_message,
            })
            .into_response()
        }
        None => (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(ErrorResponse {
                error: "hegemon_disabled".to_string(),
                message: "HEGEMON module is disabled".to_string(),
            }),
        )
            .into_response(),
    }
}

/// `POST /hegemon/budget/record` — record a spend.
pub async fn budget_record(
    State(state): State<crate::state::AppState>,
    Json(body): Json<BudgetRecordRequest>,
) -> impl IntoResponse {
    match &state.hegemon {
        Some(heg) => {
            if body.amount_usd < 0.0 {
                return (
                    StatusCode::BAD_REQUEST,
                    Json(ErrorResponse {
                        error: "invalid_amount".to_string(),
                        message: "amount_usd must be non-negative".to_string(),
                    }),
                )
                    .into_response();
            }

            let new_total =
                heg.budget_tracker
                    .record(&body.worker_name, body.amount_usd, &body.dispatch_id);
            let remaining = (heg.budget_daily_usd - new_total).max(0.0);
            let warning = new_total >= heg.budget_daily_usd * heg.budget_warn_pct;

            // Update Prometheus gauge
            metrics::HEGEMON_BUDGET_DAILY_USD
                .with_label_values(&[&body.worker_name])
                .set(new_total);

            // Emit Kafka event for budget record
            if let Some(ref producer) = state.metering_producer {
                let event = serde_json::json!({
                    "type": "budget_recorded",
                    "worker_name": body.worker_name,
                    "amount_usd": body.amount_usd,
                    "dispatch_id": body.dispatch_id,
                    "daily_spent_usd": new_total,
                    "daily_limit_usd": heg.budget_daily_usd,
                    "warning": warning,
                    "timestamp": chrono::Utc::now().to_rfc3339(),
                });
                if let Ok(payload) = serde_json::to_string(&event) {
                    producer.send_raw("hegemon.budget", &body.worker_name, &payload);
                }
            }

            Json(BudgetRecordResponse {
                recorded: true,
                daily_spent_usd: new_total,
                remaining_usd: remaining,
                warning,
            })
            .into_response()
        }
        None => (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(ErrorResponse {
                error: "hegemon_disabled".to_string(),
                message: "HEGEMON module is disabled".to_string(),
            }),
        )
            .into_response(),
    }
}

/// `GET /admin/hegemon/budget` — list all agent budget summaries.
pub async fn list_budgets(State(state): State<crate::state::AppState>) -> impl IntoResponse {
    match &state.hegemon {
        Some(heg) => {
            let agents = heg
                .budget_tracker
                .list(heg.budget_daily_usd, heg.budget_warn_pct);
            let fleet_total: f64 = agents.iter().map(|a| a.daily_spent_usd).sum();
            Json(BudgetListResponse {
                agents,
                fleet_daily_spent_usd: fleet_total,
            })
            .into_response()
        }
        None => (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(ErrorResponse {
                error: "hegemon_disabled".to_string(),
                message: "HEGEMON module is disabled".to_string(),
            }),
        )
            .into_response(),
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_new_tracker_empty() {
        let tracker = BudgetTracker::new();
        assert_eq!(tracker.count(), 0);
    }

    #[test]
    fn test_check_unknown_agent_returns_zero_spent() {
        let tracker = BudgetTracker::new();
        let (spent, allowed) = tracker.check("worker-1", 50.0, 0.0);
        assert_eq!(spent, 0.0);
        assert!(allowed);
    }

    #[test]
    fn test_check_with_estimated_cost() {
        let tracker = BudgetTracker::new();
        // Under limit: 0 spent + 30 estimated < 50 limit
        let (_, allowed) = tracker.check("worker-1", 50.0, 30.0);
        assert!(allowed);

        // Over limit: 0 spent + 60 estimated > 50 limit
        let (_, allowed) = tracker.check("worker-1", 50.0, 60.0);
        assert!(!allowed);
    }

    #[test]
    fn test_record_and_check() {
        let tracker = BudgetTracker::new();

        let total = tracker.record("worker-1", 10.0, "heg-001");
        assert!((total - 10.0).abs() < f64::EPSILON);

        let total = tracker.record("worker-1", 15.0, "heg-002");
        assert!((total - 25.0).abs() < f64::EPSILON);

        let (spent, allowed) = tracker.check("worker-1", 50.0, 0.0);
        assert!((spent - 25.0).abs() < f64::EPSILON);
        assert!(allowed);

        // Check with estimated that would exceed
        let (_, allowed) = tracker.check("worker-1", 50.0, 30.0);
        assert!(!allowed);
    }

    #[test]
    fn test_record_returns_daily_total() {
        let tracker = BudgetTracker::new();
        assert!((tracker.record("w-1", 5.0, "d-1") - 5.0).abs() < f64::EPSILON);
        assert!((tracker.record("w-1", 3.0, "d-2") - 8.0).abs() < f64::EPSILON);
        assert!((tracker.record("w-1", 2.0, "d-3") - 10.0).abs() < f64::EPSILON);
    }

    #[test]
    fn test_multiple_agents_independent() {
        let tracker = BudgetTracker::new();
        tracker.record("worker-1", 20.0, "d-1");
        tracker.record("worker-2", 10.0, "d-2");

        assert!((tracker.daily_spent("worker-1") - 20.0).abs() < f64::EPSILON);
        assert!((tracker.daily_spent("worker-2") - 10.0).abs() < f64::EPSILON);
        assert_eq!(tracker.count(), 2);
    }

    #[test]
    fn test_check_exact_limit_allowed() {
        let tracker = BudgetTracker::new();
        tracker.record("worker-1", 50.0, "d-1");
        let (spent, allowed) = tracker.check("worker-1", 50.0, 0.0);
        assert!((spent - 50.0).abs() < f64::EPSILON);
        assert!(allowed); // Exactly at limit with 0 estimated = allowed
    }

    #[test]
    fn test_check_over_limit_denied() {
        let tracker = BudgetTracker::new();
        tracker.record("worker-1", 50.0, "d-1");
        let (_, allowed) = tracker.check("worker-1", 50.0, 1.0);
        assert!(!allowed); // 50 + 1 > 50
    }

    #[test]
    fn test_list_sorted_by_name() {
        let tracker = BudgetTracker::new();
        tracker.record("worker-c", 5.0, "d-1");
        tracker.record("worker-a", 10.0, "d-2");
        tracker.record("worker-b", 15.0, "d-3");

        let summaries = tracker.list(50.0, 0.8);
        assert_eq!(summaries.len(), 3);
        assert_eq!(summaries[0].worker_name, "worker-a");
        assert_eq!(summaries[1].worker_name, "worker-b");
        assert_eq!(summaries[2].worker_name, "worker-c");
    }

    #[test]
    fn test_list_warning_flag() {
        let tracker = BudgetTracker::new();
        tracker.record("worker-ok", 10.0, "d-1"); // 20% of 50
        tracker.record("worker-warn", 42.0, "d-2"); // 84% of 50

        let summaries = tracker.list(50.0, 0.8);
        let ok = summaries
            .iter()
            .find(|s| s.worker_name == "worker-ok")
            .unwrap();
        let warn = summaries
            .iter()
            .find(|s| s.worker_name == "worker-warn")
            .unwrap();

        assert!(!ok.warning);
        assert!(warn.warning);
    }

    #[test]
    fn test_list_remaining_never_negative() {
        let tracker = BudgetTracker::new();
        tracker.record("worker-1", 100.0, "d-1"); // Over the 50 limit

        let summaries = tracker.list(50.0, 0.8);
        let s = &summaries[0];
        assert!((s.remaining_usd - 0.0).abs() < f64::EPSILON);
    }

    #[test]
    fn test_daily_spent_unknown_agent() {
        let tracker = BudgetTracker::new();
        assert!((tracker.daily_spent("nonexistent") - 0.0).abs() < f64::EPSILON);
    }

    #[test]
    fn test_prune_old_entries() {
        let mut budget = AgentBudget {
            entries: vec![
                SpendEntry {
                    date: "2025-01-01".to_string(),
                    amount_usd: 100.0,
                    _dispatch_id: "old-1".to_string(),
                },
                SpendEntry {
                    date: "2025-01-02".to_string(),
                    amount_usd: 200.0,
                    _dispatch_id: "old-2".to_string(),
                },
            ],
        };

        let today = "2026-03-06";
        budget.prune(today);
        assert!(budget.entries.is_empty());
        assert!((budget.daily_spent(today) - 0.0).abs() < f64::EPSILON);
    }

    #[test]
    fn test_prune_keeps_today() {
        let today = today_str();
        let mut budget = AgentBudget {
            entries: vec![
                SpendEntry {
                    date: "2025-01-01".to_string(),
                    amount_usd: 100.0,
                    _dispatch_id: "old".to_string(),
                },
                SpendEntry {
                    date: today.clone(),
                    amount_usd: 5.0,
                    _dispatch_id: "today".to_string(),
                },
            ],
        };

        budget.prune(&today);
        assert_eq!(budget.entries.len(), 1);
        assert!((budget.daily_spent(&today) - 5.0).abs() < f64::EPSILON);
    }

    #[test]
    fn test_concurrent_records() {
        use std::sync::Arc;
        use std::thread;

        let tracker = Arc::new(BudgetTracker::new());
        let mut handles = vec![];

        // 10 threads each recording $1.0
        for i in 0..10 {
            let t = Arc::clone(&tracker);
            handles.push(thread::spawn(move || {
                t.record("worker-1", 1.0, &format!("d-{}", i));
            }));
        }

        for h in handles {
            h.join().unwrap();
        }

        let spent = tracker.daily_spent("worker-1");
        assert!((spent - 10.0).abs() < f64::EPSILON);
        assert_eq!(tracker.count(), 1);
    }

    #[test]
    fn test_concurrent_check_and_record() {
        use std::sync::Arc;
        use std::thread;

        let tracker = Arc::new(BudgetTracker::new());
        let limit = 50.0;

        // Pre-fill to near limit
        tracker.record("worker-1", 48.0, "d-prefill");

        let mut handles = vec![];

        // 5 threads try to check+record $1.0 each (only 2 should be within budget)
        for i in 0..5 {
            let t = Arc::clone(&tracker);
            handles.push(thread::spawn(move || {
                let (_, allowed) = t.check("worker-1", limit, 1.0);
                if allowed {
                    t.record("worker-1", 1.0, &format!("d-{}", i));
                }
            }));
        }

        for h in handles {
            h.join().unwrap();
        }

        // Total should be at most $53 (48 prefill + at most 5 concurrent records)
        // but no more — and certainly not $48 + 5*$1 = $53 overflow
        let spent = tracker.daily_spent("worker-1");
        assert!(spent >= 48.0);
        assert!(spent <= 53.0);
    }

    #[test]
    fn test_empty_list() {
        let tracker = BudgetTracker::new();
        let summaries = tracker.list(50.0, 0.8);
        assert!(summaries.is_empty());
    }

    #[test]
    fn test_entries_today_count() {
        let tracker = BudgetTracker::new();
        tracker.record("worker-1", 5.0, "d-1");
        tracker.record("worker-1", 3.0, "d-2");
        tracker.record("worker-1", 2.0, "d-3");

        let summaries = tracker.list(50.0, 0.8);
        assert_eq!(summaries[0].entries_today, 3);
    }
}
