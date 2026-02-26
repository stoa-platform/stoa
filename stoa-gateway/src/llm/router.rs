//! LLM Provider Router (CAB-1487)
//!
//! Routes LLM requests to the best available provider based on strategy.
//! Integrates with the circuit breaker registry for per-provider health tracking
//! and supports automatic fallback when a provider is unhealthy.

use serde::{Deserialize, Serialize};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;

use crate::resilience::CircuitBreakerRegistry;

use super::providers::{LlmProvider, ProviderConfig, ProviderRegistry};

/// Strategy for selecting the target LLM provider.
#[derive(Debug, Default, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RoutingStrategy {
    /// Cycle through providers in order.
    #[default]
    RoundRobin,
    /// Pick the provider with the lowest input token cost.
    LowestCost,
    /// Pick the provider with the lowest recent p50 latency (falls back to priority).
    LowestLatency,
    /// Honour the `X-Stoa-Llm-Provider` request header; fall back to priority if absent.
    HeaderOverride,
}

/// Routes LLM requests to providers based on strategy and health state.
pub struct LlmRouter {
    registry: Arc<ProviderRegistry>,
    cb_registry: Arc<CircuitBreakerRegistry>,
    default_strategy: RoutingStrategy,
    round_robin_counter: AtomicUsize,
}

impl LlmRouter {
    /// Create a new router with the given registry, circuit breaker registry, and default strategy.
    pub fn new(
        registry: Arc<ProviderRegistry>,
        cb_registry: Arc<CircuitBreakerRegistry>,
        default_strategy: RoutingStrategy,
    ) -> Self {
        Self {
            registry,
            cb_registry,
            default_strategy,
            round_robin_counter: AtomicUsize::new(0),
        }
    }

    /// Select the best provider for a request, optionally using a header override.
    ///
    /// Returns `None` if no healthy provider is available.
    pub fn select(
        &self,
        strategy: Option<RoutingStrategy>,
        header_provider: Option<&str>,
    ) -> Option<&ProviderConfig> {
        let strat = strategy.unwrap_or(self.default_strategy);

        match strat {
            RoutingStrategy::RoundRobin => self.select_round_robin(),
            RoutingStrategy::LowestCost => self.select_lowest_cost(),
            RoutingStrategy::LowestLatency => self.select_by_priority(),
            RoutingStrategy::HeaderOverride => {
                if let Some(name) = header_provider {
                    if let Some(provider) = self.parse_provider(name) {
                        if self.is_healthy(provider) {
                            return self.registry.get(provider);
                        }
                    }
                }
                // Fall back to priority-based selection
                self.select_by_priority()
            }
        }
    }

    /// Build an ordered fallback chain of healthy providers (excluding a failed one).
    pub fn fallback_chain(&self, failed: LlmProvider) -> Vec<&ProviderConfig> {
        self.healthy_providers_by_priority()
            .into_iter()
            .filter(|p| p.provider != failed)
            .collect()
    }

    /// Record a successful call to a provider (resets circuit breaker).
    pub fn record_success(&self, provider: LlmProvider) {
        let cb = self.get_circuit_breaker(provider);
        cb.record_success();
    }

    /// Record a failed call to a provider (may trip circuit breaker).
    pub fn record_failure(&self, provider: LlmProvider) {
        let cb = self.get_circuit_breaker(provider);
        cb.record_failure();
    }

    /// Check if a provider's circuit breaker allows requests.
    pub fn is_healthy(&self, provider: LlmProvider) -> bool {
        let cb = self.get_circuit_breaker(provider);
        cb.allow_request()
    }

    // --- Private helpers ---

    fn get_circuit_breaker(&self, provider: LlmProvider) -> Arc<crate::resilience::CircuitBreaker> {
        let key = format!("llm-{}", provider);
        self.cb_registry.get_or_create(&key)
    }

    fn select_round_robin(&self) -> Option<&ProviderConfig> {
        let healthy = self.healthy_providers_by_priority();
        if healthy.is_empty() {
            return None;
        }
        let idx = self.round_robin_counter.fetch_add(1, Ordering::Relaxed) % healthy.len();
        Some(healthy[idx])
    }

    fn select_lowest_cost(&self) -> Option<&ProviderConfig> {
        self.registry
            .sorted_by_cost()
            .into_iter()
            .find(|p| self.is_healthy(p.provider))
    }

    fn select_by_priority(&self) -> Option<&ProviderConfig> {
        self.healthy_providers_by_priority().into_iter().next()
    }

    fn healthy_providers_by_priority(&self) -> Vec<&ProviderConfig> {
        self.registry
            .sorted_by_priority()
            .into_iter()
            .filter(|p| self.is_healthy(p.provider))
            .collect()
    }

    fn parse_provider(&self, name: &str) -> Option<LlmProvider> {
        LlmProvider::from_str_opt(name)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::resilience::{CircuitBreakerConfig, CircuitBreakerRegistry};

    fn make_provider(
        provider: LlmProvider,
        priority: u32,
        cost_input: f64,
    ) -> super::super::providers::ProviderConfig {
        super::super::providers::ProviderConfig {
            provider,
            base_url: format!("https://{}.example.com", provider),
            api_key_env: None,
            default_model: None,
            max_concurrent: 50,
            enabled: true,
            cost_per_1m_input: cost_input,
            cost_per_1m_output: cost_input * 3.0,
            priority,
        }
    }

    fn make_router(
        providers: Vec<super::super::providers::ProviderConfig>,
        strategy: RoutingStrategy,
    ) -> LlmRouter {
        let registry = ProviderRegistry::new(providers).into_shared();
        let cb_registry = Arc::new(CircuitBreakerRegistry::new(CircuitBreakerConfig::default()));
        LlmRouter::new(registry, cb_registry, strategy)
    }

    #[test]
    fn round_robin_cycles() {
        let router = make_router(
            vec![
                make_provider(LlmProvider::OpenAi, 1, 5.0),
                make_provider(LlmProvider::Anthropic, 2, 3.0),
            ],
            RoutingStrategy::RoundRobin,
        );

        // First two calls should cycle through providers by priority order
        let first = router.select(None, None).map(|p| p.provider);
        let second = router.select(None, None).map(|p| p.provider);
        assert!(first.is_some());
        assert!(second.is_some());
        // After 2 calls, we should have seen both providers
        assert_ne!(first, second);
    }

    #[test]
    fn lowest_cost_selects_cheapest() {
        let router = make_router(
            vec![
                make_provider(LlmProvider::OpenAi, 1, 15.0),
                make_provider(LlmProvider::Google, 2, 1.25),
                make_provider(LlmProvider::Anthropic, 3, 3.0),
            ],
            RoutingStrategy::LowestCost,
        );

        let selected = router
            .select(Some(RoutingStrategy::LowestCost), None)
            .expect("should select a provider");
        assert_eq!(selected.provider, LlmProvider::Google);
    }

    #[test]
    fn header_override() {
        let router = make_router(
            vec![
                make_provider(LlmProvider::OpenAi, 1, 5.0),
                make_provider(LlmProvider::Anthropic, 2, 3.0),
            ],
            RoutingStrategy::HeaderOverride,
        );

        let selected = router
            .select(Some(RoutingStrategy::HeaderOverride), Some("anthropic"))
            .expect("should select anthropic");
        assert_eq!(selected.provider, LlmProvider::Anthropic);
    }

    #[test]
    fn header_override_unknown_falls_back() {
        let router = make_router(
            vec![
                make_provider(LlmProvider::OpenAi, 1, 5.0),
                make_provider(LlmProvider::Anthropic, 2, 3.0),
            ],
            RoutingStrategy::HeaderOverride,
        );

        // Unknown provider name falls back to priority
        let selected = router
            .select(Some(RoutingStrategy::HeaderOverride), Some("unknown-llm"))
            .expect("should fall back to priority");
        assert_eq!(selected.provider, LlmProvider::OpenAi);
    }

    #[test]
    fn fallback_chain_excludes_failed() {
        let router = make_router(
            vec![
                make_provider(LlmProvider::OpenAi, 1, 5.0),
                make_provider(LlmProvider::Anthropic, 2, 3.0),
                make_provider(LlmProvider::Google, 3, 1.0),
            ],
            RoutingStrategy::RoundRobin,
        );

        let chain = router.fallback_chain(LlmProvider::OpenAi);
        assert_eq!(chain.len(), 2);
        assert!(chain.iter().all(|p| p.provider != LlmProvider::OpenAi));
    }

    #[test]
    fn circuit_breaker_integration() {
        let router = make_router(
            vec![
                make_provider(LlmProvider::OpenAi, 1, 5.0),
                make_provider(LlmProvider::Anthropic, 2, 3.0),
            ],
            RoutingStrategy::LowestLatency,
        );

        // Trip OpenAI circuit breaker (default threshold = 5)
        for _ in 0..6 {
            router.record_failure(LlmProvider::OpenAi);
        }

        assert!(!router.is_healthy(LlmProvider::OpenAi));
        assert!(router.is_healthy(LlmProvider::Anthropic));

        // LowestLatency (priority-based) should skip OpenAI
        let selected = router.select(None, None).expect("should select anthropic");
        assert_eq!(selected.provider, LlmProvider::Anthropic);
    }

    #[test]
    fn empty_registry_returns_none() {
        let registry = ProviderRegistry::empty().into_shared();
        let cb_registry = Arc::new(CircuitBreakerRegistry::new(CircuitBreakerConfig::default()));
        let router = LlmRouter::new(registry, cb_registry, RoutingStrategy::RoundRobin);

        assert!(router.select(None, None).is_none());
    }
}
