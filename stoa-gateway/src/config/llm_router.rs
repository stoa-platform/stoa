//! LLM provider router configuration (CAB-1487).
//!
//! Configures multi-provider LLM routing with cost tracking and budget enforcement.
//! Providers are defined as a list; disabled providers are filtered at startup.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LlmRouterConfig {
    /// Enable the LLM provider router (default: false).
    /// Env: STOA_LLM_ROUTER_ENABLED
    #[serde(default)]
    pub enabled: bool,

    /// Default routing strategy.
    /// Env: STOA_LLM_ROUTER_DEFAULT_STRATEGY
    #[serde(default)]
    pub default_strategy: crate::llm::RoutingStrategy,

    /// Budget limit in USD per billing window. 0 = no limit.
    /// Env: STOA_LLM_ROUTER_BUDGET_LIMIT_USD
    #[serde(default)]
    pub budget_limit_usd: f64,

    /// Provider configurations.
    #[serde(default)]
    pub providers: Vec<crate::llm::ProviderConfig>,

    /// Subscription-to-backend routing map (CAB-1610).
    /// Maps subscription IDs (or plan names) to backend IDs in the provider list.
    /// Enables multi-namespace routing: same API contract, different backends per subscriber.
    #[serde(default)]
    pub subscription_mapping: crate::llm::SubscriptionMapping,
}

impl Default for LlmRouterConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            default_strategy: crate::llm::RoutingStrategy::default(),
            budget_limit_usd: 0.0,
            providers: Vec::new(),
            subscription_mapping: crate::llm::SubscriptionMapping::new(),
        }
    }
}
