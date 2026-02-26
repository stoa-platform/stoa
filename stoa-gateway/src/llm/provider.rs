//! Runtime state for a single LLM provider.

use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;

use serde::Serialize;

use super::config::LlmProviderConfig;

/// Live runtime state for one provider.
pub struct ProviderState {
    /// Provider configuration (immutable after init).
    pub config: LlmProviderConfig,

    /// Whether the provider is currently healthy.
    healthy: AtomicBool,

    /// Exponential moving average of response latency in microseconds.
    avg_latency_us: AtomicU64,

    /// Lifetime request count.
    total_requests: AtomicU64,
}

impl ProviderState {
    /// Create a new provider state from config.
    pub fn new(config: LlmProviderConfig) -> Self {
        Self {
            healthy: AtomicBool::new(config.enabled),
            avg_latency_us: AtomicU64::new(0),
            total_requests: AtomicU64::new(0),
            config,
        }
    }

    /// Check whether this provider is healthy and enabled.
    pub fn is_healthy(&self) -> bool {
        self.healthy.load(Ordering::Relaxed)
    }

    /// Mark the provider as healthy or unhealthy.
    pub fn set_healthy(&self, healthy: bool) {
        self.healthy.store(healthy, Ordering::Relaxed);
    }

    /// Return the current average latency in microseconds.
    pub fn avg_latency_us(&self) -> u64 {
        self.avg_latency_us.load(Ordering::Relaxed)
    }

    /// Record a new latency sample using exponential moving average.
    ///
    /// Formula: `new = (old * 4 + sample) / 5`
    pub fn record_latency(&self, sample_us: u64) {
        let old = self.avg_latency_us.load(Ordering::Relaxed);
        let new_avg = if old == 0 {
            sample_us
        } else {
            (old * 4 + sample_us) / 5
        };
        self.avg_latency_us.store(new_avg, Ordering::Relaxed);
    }

    /// Return lifetime request count.
    pub fn total_requests(&self) -> u64 {
        self.total_requests.load(Ordering::Relaxed)
    }

    /// Increment the request counter.
    pub fn inc_requests(&self) {
        self.total_requests.fetch_add(1, Ordering::Relaxed);
    }
}

/// Serializable summary of provider state for the admin API.
#[derive(Debug, Serialize)]
pub struct ProviderSummary {
    pub id: String,
    pub display_name: String,
    pub endpoint: String,
    pub healthy: bool,
    pub avg_latency_us: u64,
    pub total_requests: u64,
    pub input_token_cost_microcents: u64,
    pub output_token_cost_microcents: u64,
}

impl ProviderSummary {
    /// Build a summary snapshot from live state.
    pub fn from_state(state: &Arc<ProviderState>) -> Self {
        Self {
            id: state.config.id.clone(),
            display_name: state.config.display_name.clone(),
            endpoint: state.config.endpoint.clone(),
            healthy: state.is_healthy(),
            avg_latency_us: state.avg_latency_us(),
            total_requests: state.total_requests(),
            input_token_cost_microcents: state.config.input_token_cost_microcents,
            output_token_cost_microcents: state.config.output_token_cost_microcents,
        }
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn test_config() -> LlmProviderConfig {
        LlmProviderConfig {
            id: "test-provider".into(),
            display_name: "Test Provider".into(),
            endpoint: "http://localhost:8080".into(),
            api_key: None,
            input_token_cost_microcents: 30,
            output_token_cost_microcents: 150,
            rate_limit_rpm: 0,
            enabled: true,
        }
    }

    #[test]
    fn provider_starts_healthy_when_enabled() {
        let state = ProviderState::new(test_config());
        assert!(state.is_healthy());
    }

    #[test]
    fn provider_health_can_be_toggled() {
        let state = ProviderState::new(test_config());
        state.set_healthy(false);
        assert!(!state.is_healthy());
        state.set_healthy(true);
        assert!(state.is_healthy());
    }

    #[test]
    fn latency_ema_initial_sample() {
        let state = ProviderState::new(test_config());
        state.record_latency(1000);
        assert_eq!(state.avg_latency_us(), 1000);
    }

    #[test]
    fn latency_ema_converges() {
        let state = ProviderState::new(test_config());
        state.record_latency(1000);
        state.record_latency(500);
        // EMA: (1000*4 + 500) / 5 = 900
        assert_eq!(state.avg_latency_us(), 900);
    }
}
