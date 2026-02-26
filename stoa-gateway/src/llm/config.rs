//! LLM provider configuration types.

use serde::{Deserialize, Serialize};

/// Strategy for selecting which LLM provider handles a request.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RoutingStrategy {
    /// Distribute requests evenly across healthy providers.
    #[default]
    RoundRobin,
    /// Prefer the provider with the lowest per-token cost.
    CostOptimized,
    /// Prefer the provider with the lowest observed latency.
    LatencyOptimized,
}

/// Configuration for a single LLM provider.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LlmProviderConfig {
    /// Unique identifier (e.g. "openai-gpt4", "anthropic-claude").
    pub id: String,

    /// Human-friendly name shown in admin UI.
    #[serde(default)]
    pub display_name: String,

    /// Base endpoint URL for completions.
    pub endpoint: String,

    /// Optional API key (injected at runtime).
    #[serde(default)]
    pub api_key: Option<String>,

    /// Cost per input token in micro-cents.
    #[serde(default = "default_input_cost")]
    pub input_token_cost_microcents: u64,

    /// Cost per output token in micro-cents.
    #[serde(default = "default_output_cost")]
    pub output_token_cost_microcents: u64,

    /// Rate-limit in requests per minute (0 = unlimited).
    #[serde(default)]
    pub rate_limit_rpm: u32,

    /// Whether this provider is enabled for routing.
    #[serde(default = "default_true")]
    pub enabled: bool,
}

/// Top-level LLM configuration block.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct LlmConfig {
    /// Registered providers.
    #[serde(default)]
    pub providers: Vec<LlmProviderConfig>,

    /// Default routing strategy.
    #[serde(default)]
    pub default_strategy: RoutingStrategy,

    /// Enable budget enforcement (reject requests when budget exhausted).
    #[serde(default)]
    pub budget_enforcement: bool,
}

fn default_input_cost() -> u64 {
    30
}
fn default_output_cost() -> u64 {
    150
}
fn default_true() -> bool {
    true
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_strategy_is_round_robin() {
        assert_eq!(RoutingStrategy::default(), RoutingStrategy::RoundRobin);
    }

    #[test]
    fn llm_config_default_has_no_providers() {
        let cfg = LlmConfig::default();
        assert!(cfg.providers.is_empty());
        assert!(!cfg.budget_enforcement);
    }

    #[test]
    fn strategy_serde_round_trip() {
        let json = serde_json::to_string(&RoutingStrategy::CostOptimized).expect("serialize");
        let parsed: RoutingStrategy = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(parsed, RoutingStrategy::CostOptimized);
    }

    #[test]
    fn provider_config_defaults() {
        let json = r#"{"id":"test","endpoint":"http://localhost"}"#;
        let cfg: LlmProviderConfig = serde_json::from_str(json).expect("parse");
        assert_eq!(cfg.input_token_cost_microcents, 30);
        assert_eq!(cfg.output_token_cost_microcents, 150);
        assert!(cfg.enabled);
        assert!(cfg.api_key.is_none());
    }

    #[test]
    fn provider_config_custom_costs() {
        let json = r#"{
            "id": "custom",
            "endpoint": "http://llm.local",
            "input_token_cost_microcents": 100,
            "output_token_cost_microcents": 500,
            "enabled": false
        }"#;
        let cfg: LlmProviderConfig = serde_json::from_str(json).expect("parse");
        assert_eq!(cfg.input_token_cost_microcents, 100);
        assert_eq!(cfg.output_token_cost_microcents, 500);
        assert!(!cfg.enabled);
    }
}
