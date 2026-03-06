//! HEGEMON Agent Budget Tracker (CAB-1716)
//!
//! Centralized atomic budget enforcement for HEGEMON agent workers.
//! Eliminates race conditions from file-based tracking by using in-memory
//! sliding window with atomic operations.
//!
//! Endpoints:
//! - `POST /hegemon/budget/check`  → pre-dispatch budget check
//! - `POST /hegemon/budget/record` → atomic spend recording
//!
//! Config:
//! - `STOA_HEGEMON_BUDGET_DAILY_USD` (default: 50.0)
//! - `STOA_HEGEMON_BUDGET_WARN_PCT` (default: 80)
//!
//! Prometheus:
//! - `hegemon_budget_daily_usd{agent="worker-1"}` — per-agent daily spend

use axum::{extract::State, http::StatusCode, response::IntoResponse, Json};
use parking_lot::RwLock;
use prometheus::{register_gauge_vec, GaugeVec};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::LazyLock;
use std::time::{Duration, Instant};
use tracing::{info, warn};

use crate::state::AppState;

// === Prometheus Metrics ===

static BUDGET_DAILY_USD: LazyLock<GaugeVec> = LazyLock::new(|| {
    register_gauge_vec!(
        "hegemon_budget_daily_usd",
        "HEGEMON agent daily spend in USD",
        &["agent"]
    )
    .expect("Failed to create hegemon_budget_daily_usd metric")
});

// === Data Types ===

/// A single spend record within the sliding window.
#[derive(Debug, Clone)]
struct SpendEntry {
    amount_usd: f64,
    timestamp: Instant,
}

/// Per-agent budget state with sliding window tracking.
#[derive(Debug)]
struct AgentBudget {
    entries: Vec<SpendEntry>,
}

impl AgentBudget {
    fn new() -> Self {
        Self {
            entries: Vec::new(),
        }
    }

    /// Prune entries older than the window duration.
    fn prune(&mut self, window: Duration) {
        let cutoff = Instant::now() - window;
        self.entries.retain(|e| e.timestamp > cutoff);
    }

    /// Sum all spend within the current window.
    fn daily_spent(&self, window: Duration) -> f64 {
        let cutoff = Instant::now() - window;
        self.entries
            .iter()
            .filter(|e| e.timestamp > cutoff)
            .map(|e| e.amount_usd)
            .sum()
    }

    /// Record a new spend entry.
    fn record(&mut self, amount_usd: f64) {
        self.entries.push(SpendEntry {
            amount_usd,
            timestamp: Instant::now(),
        });
    }
}

// === Budget Tracker ===

/// Centralized agent budget tracker with atomic enforcement.
///
/// Uses `parking_lot::RwLock<HashMap>` — same pattern as `BudgetCache` and `QuotaManager`.
/// The write lock is held only during check+record (atomic operation), preventing
/// two concurrent dispatches from both passing when only budget for one remains.
pub struct AgentBudgetTracker {
    agents: RwLock<HashMap<String, AgentBudget>>,
    daily_limit_usd: f64,
    warn_pct: u8,
    window: Duration,
}

impl AgentBudgetTracker {
    /// Create a new budget tracker.
    pub fn new(daily_limit_usd: f64, warn_pct: u8) -> Self {
        Self {
            agents: RwLock::new(HashMap::new()),
            daily_limit_usd,
            warn_pct,
            window: Duration::from_secs(86400), // 24h sliding window
        }
    }

    /// Get the daily budget limit in USD.
    pub fn daily_limit_usd(&self) -> f64 {
        self.daily_limit_usd
    }

    /// Check if a dispatch is allowed for the given agent.
    /// Returns (allowed, remaining_usd, daily_spent_usd).
    pub fn check(&self, agent: &str) -> BudgetCheckResponse {
        let agents = self.agents.read();
        let spent = agents
            .get(agent)
            .map(|b| b.daily_spent(self.window))
            .unwrap_or(0.0);
        let remaining = (self.daily_limit_usd - spent).max(0.0);
        BudgetCheckResponse {
            allowed: spent < self.daily_limit_usd,
            remaining_usd: remaining,
            daily_spent_usd: spent,
            daily_limit_usd: self.daily_limit_usd,
        }
    }

    /// Atomically check budget and record spend if allowed.
    /// Returns the result of the check (after recording if allowed).
    pub fn check_and_record(&self, agent: &str, amount_usd: f64) -> BudgetRecordResponse {
        let mut agents = self.agents.write();
        let budget = agents
            .entry(agent.to_string())
            .or_insert_with(AgentBudget::new);

        // Prune old entries while we hold the lock
        budget.prune(self.window);

        let spent_before = budget.daily_spent(self.window);

        if spent_before + amount_usd > self.daily_limit_usd {
            return BudgetRecordResponse {
                recorded: false,
                remaining_usd: (self.daily_limit_usd - spent_before).max(0.0),
                daily_spent_usd: spent_before,
                daily_limit_usd: self.daily_limit_usd,
                warning: None,
                error: Some("budget_exceeded".to_string()),
            };
        }

        budget.record(amount_usd);
        let spent_after = spent_before + amount_usd;

        // Update Prometheus gauge
        BUDGET_DAILY_USD
            .with_label_values(&[agent])
            .set(spent_after);

        // Check warning threshold
        let pct = (spent_after / self.daily_limit_usd * 100.0) as u8;
        let warning = if pct >= self.warn_pct {
            warn!(
                agent = agent,
                spent_usd = spent_after,
                limit_usd = self.daily_limit_usd,
                pct = pct,
                "HEGEMON budget warning threshold reached"
            );
            Some(format!(
                "Budget at {}% ({:.2}/{:.2} USD)",
                pct, spent_after, self.daily_limit_usd
            ))
        } else {
            None
        };

        BudgetRecordResponse {
            recorded: true,
            remaining_usd: (self.daily_limit_usd - spent_after).max(0.0),
            daily_spent_usd: spent_after,
            daily_limit_usd: self.daily_limit_usd,
            warning,
            error: None,
        }
    }
}

// === Request/Response Types ===

#[derive(Debug, Deserialize)]
pub struct BudgetCheckRequest {
    pub agent: String,
}

#[derive(Debug, Serialize)]
pub struct BudgetCheckResponse {
    pub allowed: bool,
    pub remaining_usd: f64,
    pub daily_spent_usd: f64,
    pub daily_limit_usd: f64,
}

#[derive(Debug, Deserialize)]
pub struct BudgetRecordRequest {
    pub agent: String,
    pub amount_usd: f64,
}

#[derive(Debug, Serialize)]
pub struct BudgetRecordResponse {
    pub recorded: bool,
    pub remaining_usd: f64,
    pub daily_spent_usd: f64,
    pub daily_limit_usd: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub warning: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

// === Axum Handlers ===

/// POST /hegemon/budget/check
///
/// Pre-dispatch budget check. Returns whether a dispatch is allowed.
pub async fn budget_check_handler(
    State(state): State<AppState>,
    Json(req): Json<BudgetCheckRequest>,
) -> impl IntoResponse {
    match &state.agent_budget {
        Some(tracker) => {
            let result = tracker.check(&req.agent);
            (StatusCode::OK, Json(result)).into_response()
        }
        None => (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(serde_json::json!({
                "error": "budget_tracker_disabled",
                "message": "Agent budget tracking is not enabled"
            })),
        )
            .into_response(),
    }
}

/// POST /hegemon/budget/record
///
/// Atomic spend recording. Checks budget and records spend in one operation.
pub async fn budget_record_handler(
    State(state): State<AppState>,
    Json(req): Json<BudgetRecordRequest>,
) -> impl IntoResponse {
    match &state.agent_budget {
        Some(tracker) => {
            if req.amount_usd < 0.0 {
                return (
                    StatusCode::BAD_REQUEST,
                    Json(serde_json::json!({
                        "error": "invalid_amount",
                        "message": "amount_usd must be non-negative"
                    })),
                )
                    .into_response();
            }

            let result = tracker.check_and_record(&req.agent, req.amount_usd);
            let status = if result.recorded {
                StatusCode::OK
            } else {
                StatusCode::PAYMENT_REQUIRED
            };

            info!(
                agent = req.agent,
                amount_usd = req.amount_usd,
                recorded = result.recorded,
                remaining_usd = result.remaining_usd,
                "HEGEMON budget record"
            );

            (status, Json(result)).into_response()
        }
        None => (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(serde_json::json!({
                "error": "budget_tracker_disabled",
                "message": "Agent budget tracking is not enabled"
            })),
        )
            .into_response(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;

    fn make_tracker(limit: f64, warn_pct: u8) -> AgentBudgetTracker {
        AgentBudgetTracker::new(limit, warn_pct)
    }

    // === Basic check ===

    #[test]
    fn test_check_unknown_agent_returns_full_budget() {
        let tracker = make_tracker(50.0, 80);
        let result = tracker.check("worker-1");
        assert!(result.allowed);
        assert!((result.remaining_usd - 50.0).abs() < f64::EPSILON);
        assert!((result.daily_spent_usd - 0.0).abs() < f64::EPSILON);
    }

    // === Record and check ===

    #[test]
    fn test_record_reduces_remaining() {
        let tracker = make_tracker(50.0, 80);
        let result = tracker.check_and_record("worker-1", 10.0);
        assert!(result.recorded);
        assert!((result.daily_spent_usd - 10.0).abs() < f64::EPSILON);
        assert!((result.remaining_usd - 40.0).abs() < f64::EPSILON);
        assert!(result.error.is_none());
    }

    // === Budget exceeded ===

    #[test]
    fn test_record_rejects_over_budget() {
        let tracker = make_tracker(50.0, 80);
        tracker.check_and_record("worker-1", 45.0);

        let result = tracker.check_and_record("worker-1", 10.0);
        assert!(!result.recorded);
        assert!(result.error.is_some());
        assert_eq!(result.error.as_deref(), Some("budget_exceeded"));
    }

    #[test]
    fn test_check_returns_not_allowed_when_over() {
        let tracker = make_tracker(50.0, 80);
        tracker.check_and_record("worker-1", 50.0);

        let result = tracker.check("worker-1");
        assert!(!result.allowed);
        assert!((result.remaining_usd - 0.0).abs() < f64::EPSILON);
    }

    // === Warning threshold ===

    #[test]
    fn test_warning_emitted_at_threshold() {
        let tracker = make_tracker(100.0, 80);
        // Spend 80% of budget
        let result = tracker.check_and_record("worker-1", 80.0);
        assert!(result.recorded);
        assert!(result.warning.is_some());
    }

    #[test]
    fn test_no_warning_below_threshold() {
        let tracker = make_tracker(100.0, 80);
        let result = tracker.check_and_record("worker-1", 50.0);
        assert!(result.recorded);
        assert!(result.warning.is_none());
    }

    // === Per-agent isolation ===

    #[test]
    fn test_agents_have_separate_budgets() {
        let tracker = make_tracker(50.0, 80);
        tracker.check_and_record("worker-1", 45.0);

        // worker-2 should still have full budget
        let result = tracker.check("worker-2");
        assert!(result.allowed);
        assert!((result.remaining_usd - 50.0).abs() < f64::EPSILON);
    }

    // === Concurrency test (key DoD requirement) ===

    #[test]
    fn test_concurrent_dispatches_cannot_exceed_limit() {
        let tracker = Arc::new(make_tracker(50.0, 80));
        let barrier = Arc::new(std::sync::Barrier::new(10));

        let handles: Vec<_> = (0..10)
            .map(|_| {
                let t = tracker.clone();
                let b = barrier.clone();
                std::thread::spawn(move || {
                    b.wait();
                    t.check_and_record("worker-concurrent", 10.0)
                })
            })
            .collect();

        let results: Vec<_> = handles.into_iter().map(|h| h.join().unwrap()).collect();
        let recorded_count = results.iter().filter(|r| r.recorded).count();
        let total_spent: f64 = results
            .iter()
            .filter(|r| r.recorded)
            .map(|_| 10.0_f64)
            .sum();

        // At most 5 out of 10 should succeed (5 * 10 = 50 = limit)
        assert_eq!(recorded_count, 5);
        assert!((total_spent - 50.0).abs() < f64::EPSILON);
    }

    // === Prometheus metric ===

    #[test]
    fn test_prometheus_gauge_updated() {
        let tracker = make_tracker(100.0, 80);
        tracker.check_and_record("prom-test-agent", 25.0);

        let val = BUDGET_DAILY_USD
            .with_label_values(&["prom-test-agent"])
            .get();
        assert!((val - 25.0).abs() < f64::EPSILON);
    }

    // === Edge cases ===

    #[test]
    fn test_zero_amount_allowed() {
        let tracker = make_tracker(50.0, 80);
        let result = tracker.check_and_record("worker-1", 0.0);
        assert!(result.recorded);
    }

    #[test]
    fn test_exact_limit_spend() {
        let tracker = make_tracker(50.0, 80);
        let result = tracker.check_and_record("worker-1", 50.0);
        assert!(result.recorded);

        // Next spend should fail
        let result2 = tracker.check_and_record("worker-1", 0.01);
        assert!(!result2.recorded);
    }
}
