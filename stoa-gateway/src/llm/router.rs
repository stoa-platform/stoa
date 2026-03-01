//! LLM Provider Router (CAB-1487)
//!
//! Routes LLM requests to the best available provider based on strategy.
//! Integrates with the circuit breaker registry for per-provider health tracking
//! and supports automatic fallback when a provider is unhealthy.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
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

    /// Select a provider by subscription ID using a subscription-to-backend mapping.
    ///
    /// This enables multi-namespace routing: the same API contract is served by
    /// different backends depending on the subscriber's plan. For example, two Azure
    /// OpenAI namespaces (`projet-alpha`, `projet-beta`) can be routed to based on
    /// which plan the subscriber is on.
    ///
    /// Returns `None` if the subscription has no mapping or the mapped backend is
    /// not found / unhealthy.
    pub fn select_for_subscription(
        &self,
        subscription_id: &str,
        mapping: &SubscriptionMapping,
    ) -> Option<&ProviderConfig> {
        let backend_id = mapping.get_backend(subscription_id)?;
        let config = self.registry.get_by_backend_id(backend_id)?;
        if self.is_healthy(config.provider) {
            Some(config)
        } else {
            None
        }
    }
}

/// Maps subscription IDs (or plan names) to backend IDs in the provider registry.
///
/// # Example
///
/// ```text
/// Plan "Projet Alpha" → backend_id "projet-alpha" → Azure OpenAI namespace alpha
/// Plan "Projet Beta"  → backend_id "projet-beta"  → Azure OpenAI namespace beta
/// ```
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct SubscriptionMapping {
    /// subscription_id → backend_id
    map: HashMap<String, String>,
}

impl SubscriptionMapping {
    /// Create an empty mapping.
    pub fn new() -> Self {
        Self {
            map: HashMap::new(),
        }
    }

    /// Create a mapping from a list of (subscription_id, backend_id) pairs.
    pub fn from_pairs(pairs: impl IntoIterator<Item = (String, String)>) -> Self {
        Self {
            map: pairs.into_iter().collect(),
        }
    }

    /// Add a subscription → backend mapping.
    pub fn insert(&mut self, subscription_id: String, backend_id: String) {
        self.map.insert(subscription_id, backend_id);
    }

    /// Look up which backend a subscription maps to.
    pub fn get_backend(&self, subscription_id: &str) -> Option<&str> {
        self.map.get(subscription_id).map(|s| s.as_str())
    }

    /// Number of mappings.
    pub fn len(&self) -> usize {
        self.map.len()
    }

    /// Whether the mapping is empty.
    pub fn is_empty(&self) -> bool {
        self.map.is_empty()
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
            backend_id: None,
            base_url: format!("https://{}.example.com", provider),
            api_key_env: None,
            default_model: None,
            max_concurrent: 50,
            enabled: true,
            cost_per_1m_input: cost_input,
            cost_per_1m_output: cost_input * 3.0,
            priority,
            deployment: None,
            api_version: None,
        }
    }

    fn make_azure_backend(
        backend_id: &str,
        endpoint: &str,
        deployment: &str,
        priority: u32,
    ) -> super::super::providers::ProviderConfig {
        super::super::providers::ProviderConfig {
            provider: LlmProvider::AzureOpenAi,
            backend_id: Some(backend_id.to_string()),
            base_url: endpoint.to_string(),
            api_key_env: Some(format!(
                "AZURE_{}_KEY",
                backend_id.to_uppercase().replace('-', "_")
            )),
            default_model: None,
            max_concurrent: 50,
            enabled: true,
            cost_per_1m_input: 5.0,
            cost_per_1m_output: 15.0,
            priority,
            deployment: Some(deployment.to_string()),
            api_version: Some("2024-12-01-preview".to_string()),
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

    // --- Subscription routing tests (CAB-1610) ---

    #[test]
    fn subscription_routes_to_correct_backend() {
        let router = make_router(
            vec![
                make_azure_backend(
                    "projet-alpha",
                    "https://projet-alpha.openai.azure.com",
                    "gpt-4o",
                    1,
                ),
                make_azure_backend(
                    "projet-beta",
                    "https://projet-beta.openai.azure.com",
                    "gpt-4o",
                    2,
                ),
            ],
            RoutingStrategy::RoundRobin,
        );

        let mapping = SubscriptionMapping::from_pairs(vec![
            ("sub-alpha-001".to_string(), "projet-alpha".to_string()),
            ("sub-beta-001".to_string(), "projet-beta".to_string()),
        ]);

        // Same contract, different subscriptions → different backends
        let alpha = router
            .select_for_subscription("sub-alpha-001", &mapping)
            .expect("should route to alpha");
        assert_eq!(alpha.base_url, "https://projet-alpha.openai.azure.com");
        assert_eq!(alpha.backend_id.as_deref(), Some("projet-alpha"));

        let beta = router
            .select_for_subscription("sub-beta-001", &mapping)
            .expect("should route to beta");
        assert_eq!(beta.base_url, "https://projet-beta.openai.azure.com");
        assert_eq!(beta.backend_id.as_deref(), Some("projet-beta"));
    }

    #[test]
    fn subscription_unknown_returns_none() {
        let router = make_router(
            vec![make_azure_backend(
                "projet-alpha",
                "https://projet-alpha.openai.azure.com",
                "gpt-4o",
                1,
            )],
            RoutingStrategy::RoundRobin,
        );

        let mapping = SubscriptionMapping::from_pairs(vec![(
            "sub-alpha-001".to_string(),
            "projet-alpha".to_string(),
        )]);

        // Unknown subscription → None (caller returns 401)
        assert!(router
            .select_for_subscription("sub-unknown", &mapping)
            .is_none());
    }

    #[test]
    fn subscription_unhealthy_backend_returns_none() {
        let router = make_router(
            vec![make_azure_backend(
                "projet-alpha",
                "https://projet-alpha.openai.azure.com",
                "gpt-4o",
                1,
            )],
            RoutingStrategy::RoundRobin,
        );

        let mapping = SubscriptionMapping::from_pairs(vec![(
            "sub-alpha-001".to_string(),
            "projet-alpha".to_string(),
        )]);

        // Trip circuit breaker for AzureOpenAi
        for _ in 0..6 {
            router.record_failure(LlmProvider::AzureOpenAi);
        }

        // Backend is unhealthy → None
        assert!(router
            .select_for_subscription("sub-alpha-001", &mapping)
            .is_none());
    }

    #[test]
    fn subscription_mapping_to_missing_backend_returns_none() {
        let router = make_router(
            vec![make_azure_backend(
                "projet-alpha",
                "https://projet-alpha.openai.azure.com",
                "gpt-4o",
                1,
            )],
            RoutingStrategy::RoundRobin,
        );

        // Mapping points to a backend that doesn't exist in registry
        let mapping = SubscriptionMapping::from_pairs(vec![(
            "sub-gamma-001".to_string(),
            "projet-gamma".to_string(),
        )]);

        assert!(router
            .select_for_subscription("sub-gamma-001", &mapping)
            .is_none());
    }

    #[test]
    fn subscription_mapping_operations() {
        let mut mapping = SubscriptionMapping::new();
        assert!(mapping.is_empty());
        assert_eq!(mapping.len(), 0);

        mapping.insert("sub-1".to_string(), "backend-a".to_string());
        mapping.insert("sub-2".to_string(), "backend-b".to_string());

        assert!(!mapping.is_empty());
        assert_eq!(mapping.len(), 2);
        assert_eq!(mapping.get_backend("sub-1"), Some("backend-a"));
        assert_eq!(mapping.get_backend("sub-2"), Some("backend-b"));
        assert_eq!(mapping.get_backend("sub-3"), None);
    }
}
