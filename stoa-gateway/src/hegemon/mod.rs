//! HEGEMON Agent Gateway — Central control plane for AI agent fleet.
//!
//! Provides agent identity extraction, fleet registry, dispatch coordination,
//! budget enforcement, claim management, and metering.
//!
//! Kill switch: `STOA_HEGEMON_ENABLED=false` (default: false — explicit opt-in).

pub mod identity;
pub mod registry;

use std::sync::Arc;

use crate::config::Config;
use registry::AgentRegistry;

/// Shared state for all HEGEMON subsystems.
///
/// Wrapped in `Option<Arc<HegemonState>>` in AppState — None when disabled.
#[derive(Clone)]
pub struct HegemonState {
    /// In-memory agent registry tracking all authenticated workers.
    pub registry: Arc<AgentRegistry>,
    /// Daily budget limit in USD per agent (from config).
    pub budget_daily_usd: f64,
    /// Warning percentage for budget alerts (0.0-1.0).
    pub budget_warn_pct: f64,
}

impl HegemonState {
    pub fn new(config: &Config) -> Self {
        Self {
            registry: Arc::new(AgentRegistry::new()),
            budget_daily_usd: config.hegemon_budget_daily_usd,
            budget_warn_pct: config.hegemon_budget_warn_pct,
        }
    }
}
