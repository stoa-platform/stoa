//! LLM Cost Calculator & Budget Gate (CAB-1487)
//!
//! Per-request token counting with Prometheus metrics and pre-flight budget checks.
//! The budget gate returns HTTP 429 with `X-Stoa-Budget-Exceeded: true` when the
//! estimated cost would exceed the tenant's remaining budget.

use once_cell::sync::Lazy;
use prometheus::{register_counter_vec, register_histogram_vec, CounterVec, HistogramVec};

use super::providers::{LlmProvider, ProviderRegistry};

// === Prometheus Metrics ===

/// Total LLM cost in USD, by provider and model.
pub static LLM_COST_TOTAL: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "gateway_llm_cost_total",
        "Total LLM cost in USD",
        &["provider", "model"]
    )
    .expect("Failed to create gateway_llm_cost_total metric")
});

/// LLM request latency in seconds, by provider and model.
pub static LLM_LATENCY_SECONDS: Lazy<HistogramVec> = Lazy::new(|| {
    register_histogram_vec!(
        "gateway_llm_latency_seconds",
        "LLM request latency in seconds",
        &["provider", "model"],
        vec![0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0]
    )
    .expect("Failed to create gateway_llm_latency_seconds metric")
});

/// Total LLM fallback events, by source and target provider.
pub static LLM_FALLBACK_TOTAL: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "gateway_llm_fallback_total",
        "Total LLM fallback events",
        &["from_provider", "to_provider"]
    )
    .expect("Failed to create gateway_llm_fallback_total metric")
});

// === Token Usage & Cost Calculation ===

/// Token counts from an LLM response.
#[derive(Debug, Clone)]
pub struct TokenUsage {
    pub input_tokens: u64,
    pub output_tokens: u64,
    pub provider: LlmProvider,
    pub model: String,
}

/// Result of a cost calculation.
#[derive(Debug, Clone)]
pub struct CostResult {
    pub total_usd: f64,
    pub input_cost_usd: f64,
    pub output_cost_usd: f64,
}

/// Calculates per-request cost using provider pricing metadata.
pub struct CostCalculator {
    registry: std::sync::Arc<ProviderRegistry>,
}

impl CostCalculator {
    /// Create a calculator backed by a shared provider registry.
    pub fn new(registry: std::sync::Arc<ProviderRegistry>) -> Self {
        Self { registry }
    }

    /// Calculate cost for a token usage report.
    /// Falls back to zero cost if the provider is not in the registry.
    pub fn calculate(&self, usage: &TokenUsage) -> CostResult {
        let (cost_input_per_m, cost_output_per_m) = self
            .registry
            .get(usage.provider)
            .map(|p| (p.cost_per_1m_input, p.cost_per_1m_output))
            .unwrap_or((0.0, 0.0));

        let input_cost = (usage.input_tokens as f64 / 1_000_000.0) * cost_input_per_m;
        let output_cost = (usage.output_tokens as f64 / 1_000_000.0) * cost_output_per_m;

        CostResult {
            total_usd: input_cost + output_cost,
            input_cost_usd: input_cost,
            output_cost_usd: output_cost,
        }
    }

    /// Calculate cost and record to Prometheus.
    pub fn track(&self, usage: &TokenUsage) -> CostResult {
        let result = self.calculate(usage);
        let provider_label = usage.provider.to_string();
        LLM_COST_TOTAL
            .with_label_values(&[&provider_label, &usage.model])
            .inc_by(result.total_usd);
        result
    }
}

// === Budget Gate ===

/// Outcome of a pre-flight budget check.
#[derive(Debug, Clone, PartialEq)]
pub enum BudgetDecision {
    /// Request is within budget.
    Allowed,
    /// Request would exceed the remaining budget.
    Denied {
        estimated_cost_usd: f64,
        remaining_usd: f64,
    },
}

/// Pre-flight budget gate that estimates cost and checks against a limit.
pub struct BudgetGate {
    calculator: CostCalculator,
    /// Maximum cost in USD before the gate denies requests.
    /// In production this is fetched from CP API; here it is a static threshold.
    limit_usd: f64,
}

impl BudgetGate {
    /// Create a budget gate with a cost limit in USD.
    pub fn new(calculator: CostCalculator, limit_usd: f64) -> Self {
        Self {
            calculator,
            limit_usd,
        }
    }

    /// Check whether the estimated request cost is within budget.
    ///
    /// `estimated_input_tokens` and `estimated_output_tokens` are pre-flight estimates.
    /// `spent_usd` is the amount already consumed in the current billing window.
    pub fn check(
        &self,
        provider: LlmProvider,
        model: &str,
        estimated_input_tokens: u64,
        estimated_output_tokens: u64,
        spent_usd: f64,
    ) -> BudgetDecision {
        let usage = TokenUsage {
            input_tokens: estimated_input_tokens,
            output_tokens: estimated_output_tokens,
            provider,
            model: model.to_string(),
        };
        let cost = self.calculator.calculate(&usage);
        let remaining = self.limit_usd - spent_usd;

        if cost.total_usd > remaining {
            BudgetDecision::Denied {
                estimated_cost_usd: cost.total_usd,
                remaining_usd: remaining,
            }
        } else {
            BudgetDecision::Allowed
        }
    }

    /// Build the HTTP header value for a budget-exceeded response.
    pub fn exceeded_header() -> (&'static str, &'static str) {
        ("X-Stoa-Budget-Exceeded", "true")
    }
}

// === Helper Functions ===

/// Record a fallback event in Prometheus.
pub fn record_fallback(from: LlmProvider, to: LlmProvider) {
    LLM_FALLBACK_TOTAL
        .with_label_values(&[&from.to_string(), &to.to_string()])
        .inc();
}

/// Record LLM request latency in Prometheus.
pub fn record_latency(provider: LlmProvider, model: &str, duration_secs: f64) {
    LLM_LATENCY_SECONDS
        .with_label_values(&[&provider.to_string(), model])
        .observe(duration_secs);
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::llm::providers::ProviderConfig;

    fn make_registry() -> std::sync::Arc<ProviderRegistry> {
        ProviderRegistry::new(vec![
            ProviderConfig {
                provider: LlmProvider::OpenAi,
                backend_id: None,
                base_url: "https://api.openai.com/v1".to_string(),
                api_key_env: None,
                default_model: Some("gpt-4o".to_string()),
                max_concurrent: 50,
                enabled: true,
                cost_per_1m_input: 5.0,
                cost_per_1m_output: 15.0,
                priority: 1,
                deployment: None,
                api_version: None,
            },
            ProviderConfig {
                provider: LlmProvider::Anthropic,
                backend_id: None,
                base_url: "https://api.anthropic.com/v1".to_string(),
                api_key_env: None,
                default_model: Some("claude-sonnet-4-20250514".to_string()),
                max_concurrent: 50,
                enabled: true,
                cost_per_1m_input: 3.0,
                cost_per_1m_output: 15.0,
                priority: 2,
                deployment: None,
                api_version: None,
            },
        ])
        .into_shared()
    }

    #[test]
    fn cost_calculation_openai() {
        let registry = make_registry();
        let calc = CostCalculator::new(registry);

        let usage = TokenUsage {
            input_tokens: 1_000_000,
            output_tokens: 500_000,
            provider: LlmProvider::OpenAi,
            model: "gpt-4o".to_string(),
        };
        let result = calc.calculate(&usage);

        // 1M input * $5/1M = $5.0, 500K output * $15/1M = $7.5
        assert!((result.input_cost_usd - 5.0).abs() < f64::EPSILON);
        assert!((result.output_cost_usd - 7.5).abs() < f64::EPSILON);
        assert!((result.total_usd - 12.5).abs() < f64::EPSILON);
    }

    #[test]
    fn cost_calculation_unknown_provider() {
        let registry = make_registry();
        let calc = CostCalculator::new(registry);

        let usage = TokenUsage {
            input_tokens: 1_000_000,
            output_tokens: 500_000,
            provider: LlmProvider::Local, // Not in registry
            model: "local-model".to_string(),
        };
        let result = calc.calculate(&usage);

        // Unknown provider should return zero cost
        assert!((result.total_usd - 0.0).abs() < f64::EPSILON);
    }

    #[test]
    fn budget_gate_allows_within_limit() {
        let registry = make_registry();
        let calc = CostCalculator::new(registry);
        let gate = BudgetGate::new(calc, 100.0);

        let decision = gate.check(
            LlmProvider::OpenAi,
            "gpt-4o",
            100_000, // ~$0.50
            50_000,  // ~$0.75
            10.0,    // $10 already spent
        );
        assert_eq!(decision, BudgetDecision::Allowed);
    }

    #[test]
    fn budget_gate_zero_cost_allowed() {
        let registry = make_registry();
        let calc = CostCalculator::new(registry);
        let gate = BudgetGate::new(calc, 1.0);

        let decision = gate.check(LlmProvider::Local, "local", 0, 0, 0.0);
        assert_eq!(decision, BudgetDecision::Allowed);
    }

    #[test]
    fn budget_gate_exceeds_limit() {
        let registry = make_registry();
        let calc = CostCalculator::new(registry);
        let gate = BudgetGate::new(calc, 10.0);

        let decision = gate.check(
            LlmProvider::OpenAi,
            "gpt-4o",
            1_000_000, // $5.0 input
            1_000_000, // $15.0 output
            0.0,
        );
        match decision {
            BudgetDecision::Denied {
                estimated_cost_usd,
                remaining_usd,
            } => {
                assert!((estimated_cost_usd - 20.0).abs() < f64::EPSILON);
                assert!((remaining_usd - 10.0).abs() < f64::EPSILON);
            }
            BudgetDecision::Allowed => panic!("Expected Denied"),
        }
    }

    #[test]
    fn exceeded_header_value() {
        let (name, value) = BudgetGate::exceeded_header();
        assert_eq!(name, "X-Stoa-Budget-Exceeded");
        assert_eq!(value, "true");
    }
}
