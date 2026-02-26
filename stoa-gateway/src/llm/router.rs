//! Multi-provider LLM router with pluggable strategies.

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;

use super::config::{LlmConfig, RoutingStrategy};
use super::cost_tracker::CostTracker;
use super::provider::ProviderState;

/// Routes LLM requests to healthy providers based on the configured strategy.
pub struct LlmRouter {
    providers: Vec<Arc<ProviderState>>,
    strategy: RoutingStrategy,
    round_robin_idx: AtomicUsize,

    /// Per-provider cost accumulator (public for handler access).
    pub cost_tracker: CostTracker,

    /// Whether budget enforcement is active.
    pub budget_enforcement: bool,
}

impl LlmRouter {
    /// Build a router from the configuration block.
    pub fn from_config(config: &LlmConfig) -> Self {
        let providers = config
            .providers
            .iter()
            .map(|p| Arc::new(ProviderState::new(p.clone())))
            .collect();

        Self {
            providers,
            strategy: config.default_strategy,
            round_robin_idx: AtomicUsize::new(0),
            cost_tracker: CostTracker::new(),
            budget_enforcement: config.budget_enforcement,
        }
    }

    /// Select the next provider according to the active strategy.
    ///
    /// Returns `None` when no healthy provider is available.
    pub fn select_provider(&self) -> Option<Arc<ProviderState>> {
        let healthy: Vec<_> = self
            .providers
            .iter()
            .filter(|p| p.is_healthy())
            .cloned()
            .collect();
        if healthy.is_empty() {
            return None;
        }

        match self.strategy {
            RoutingStrategy::RoundRobin => {
                let idx = self.round_robin_idx.fetch_add(1, Ordering::Relaxed);
                Some(healthy[idx % healthy.len()].clone())
            }
            RoutingStrategy::CostOptimized => healthy
                .into_iter()
                .min_by_key(|p| p.config.input_token_cost_microcents)
                .clone(),
            RoutingStrategy::LatencyOptimized => healthy
                .into_iter()
                .min_by_key(|p| p.avg_latency_us())
                .clone(),
        }
    }

    /// Return a reference to the provider list (for admin listing).
    pub fn providers(&self) -> &[Arc<ProviderState>] {
        &self.providers
    }

    /// Return the active routing strategy.
    pub fn strategy(&self) -> RoutingStrategy {
        self.strategy
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::llm::config::LlmProviderConfig;

    fn make_provider(id: &str, cost: u64, enabled: bool) -> LlmProviderConfig {
        LlmProviderConfig {
            id: id.into(),
            display_name: id.into(),
            endpoint: format!("http://{}.local", id),
            api_key: None,
            input_token_cost_microcents: cost,
            output_token_cost_microcents: cost * 5,
            rate_limit_rpm: 0,
            enabled,
        }
    }

    #[test]
    fn round_robin_distributes_evenly() {
        let config = LlmConfig {
            providers: vec![make_provider("a", 30, true), make_provider("b", 60, true)],
            default_strategy: RoutingStrategy::RoundRobin,
            budget_enforcement: false,
        };
        let router = LlmRouter::from_config(&config);

        let first = router.select_provider().expect("first");
        let second = router.select_provider().expect("second");
        assert_ne!(first.config.id, second.config.id);
    }

    #[test]
    fn cost_optimized_picks_cheapest() {
        let config = LlmConfig {
            providers: vec![
                make_provider("expensive", 100, true),
                make_provider("cheap", 10, true),
            ],
            default_strategy: RoutingStrategy::CostOptimized,
            budget_enforcement: false,
        };
        let router = LlmRouter::from_config(&config);

        let chosen = router.select_provider().expect("chosen");
        assert_eq!(chosen.config.id, "cheap");
    }

    #[test]
    fn latency_optimized_picks_fastest() {
        let config = LlmConfig {
            providers: vec![
                make_provider("slow", 30, true),
                make_provider("fast", 30, true),
            ],
            default_strategy: RoutingStrategy::LatencyOptimized,
            budget_enforcement: false,
        };
        let router = LlmRouter::from_config(&config);

        // Simulate latency samples
        router.providers[0].record_latency(5000);
        router.providers[1].record_latency(100);

        let chosen = router.select_provider().expect("chosen");
        assert_eq!(chosen.config.id, "fast");
    }

    #[test]
    fn no_healthy_providers_returns_none() {
        let config = LlmConfig {
            providers: vec![make_provider("a", 30, false)],
            default_strategy: RoutingStrategy::RoundRobin,
            budget_enforcement: false,
        };
        let router = LlmRouter::from_config(&config);
        assert!(router.select_provider().is_none());
    }

    #[test]
    fn skips_unhealthy_provider() {
        let config = LlmConfig {
            providers: vec![make_provider("a", 30, true), make_provider("b", 60, true)],
            default_strategy: RoutingStrategy::RoundRobin,
            budget_enforcement: false,
        };
        let router = LlmRouter::from_config(&config);

        router.providers[0].set_healthy(false);

        let chosen = router.select_provider().expect("chosen");
        assert_eq!(chosen.config.id, "b");
    }

    #[test]
    fn empty_provider_list_returns_none() {
        let config = LlmConfig::default();
        let router = LlmRouter::from_config(&config);
        assert!(router.select_provider().is_none());
    }
}
