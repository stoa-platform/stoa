//! HEGEMON Agent Gateway — Central control plane for AI agent fleet.
//!
//! Provides agent identity extraction, fleet registry, dispatch coordination,
//! budget enforcement, claim management, and metering.
//!
//! Kill switch: `STOA_HEGEMON_ENABLED=false` (default: false — explicit opt-in).

pub mod budget;
pub mod claims;
pub mod dispatch;
pub mod identity;
pub mod registry;

use std::sync::Arc;

use crate::config::Config;
use budget::BudgetTracker;
use claims::ClaimTracker;
use dispatch::DispatchTracker;
use registry::AgentRegistry;

/// Shared state for all HEGEMON subsystems.
///
/// Wrapped in `Option<Arc<HegemonState>>` in AppState — None when disabled.
#[derive(Clone)]
pub struct HegemonState {
    /// In-memory agent registry tracking all authenticated workers.
    pub registry: Arc<AgentRegistry>,
    /// In-memory dispatch tracker for job dispatch and results.
    pub dispatch_tracker: Arc<DispatchTracker>,
    /// In-memory per-agent daily budget tracker.
    pub budget_tracker: Arc<BudgetTracker>,
    /// In-memory claim tracker for phase coordination.
    pub claim_tracker: Arc<ClaimTracker>,
    /// Daily budget limit in USD per agent (from config).
    pub budget_daily_usd: f64,
    /// Warning percentage for budget alerts (0.0-1.0).
    pub budget_warn_pct: f64,
}

impl HegemonState {
    pub fn new(config: &Config) -> Self {
        Self {
            registry: Arc::new(AgentRegistry::new()),
            dispatch_tracker: Arc::new(DispatchTracker::new()),
            budget_tracker: Arc::new(BudgetTracker::new()),
            claim_tracker: Arc::new(ClaimTracker::new()),
            budget_daily_usd: config.hegemon_budget_daily_usd,
            budget_warn_pct: config.hegemon_budget_warn_pct,
        }
    }
}
