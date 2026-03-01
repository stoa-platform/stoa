//! LLM Provider Router & Cost Tracking (CAB-1487)
//!
//! Multi-provider LLM routing with circuit-breaker integration, cost tracking,
//! and pre-flight budget enforcement.
//!
//! # Architecture
//!
//! ```text
//! Request --> LlmRouter --> ProviderRegistry (sorted by strategy)
//!                |                  |
//!                |           +------+------+
//!                |           v      v      v
//!                |        OpenAI  Claude  Gemini
//!                |
//!                +---> CircuitBreakerRegistry (per-provider health)
//!                |
//!                +---> CostCalculator --> Prometheus metrics
//!                         |
//!                         v
//!                     BudgetGate --> 429 + X-Stoa-Budget-Exceeded
//! ```

pub mod azure;
pub mod cost;
pub mod providers;
pub mod router;

pub use azure::{
    build_chat_completions_url, build_headers as azure_headers, transform_request, AzureRequest,
    AzureTransformError,
};
pub use cost::{
    record_fallback, record_latency, BudgetDecision, BudgetGate, CostCalculator, CostResult,
    TokenUsage, LLM_COST_TOTAL, LLM_FALLBACK_TOTAL, LLM_LATENCY_SECONDS,
};
pub use providers::{LlmProvider, ProviderConfig, ProviderRegistry};
pub use router::{LlmRouter, RoutingStrategy, SubscriptionMapping};
