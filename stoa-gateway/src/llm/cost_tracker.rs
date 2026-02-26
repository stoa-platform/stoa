//! Per-provider cost accumulation.

use std::collections::HashMap;
use std::sync::Arc;

use serde::Serialize;
use tokio::sync::RwLock;

/// Accumulated cost for one provider.
#[derive(Debug, Clone, Serialize)]
pub struct ProviderCost {
    pub provider_id: String,
    pub total_input_tokens: u64,
    pub total_output_tokens: u64,
    pub total_cost_microcents: u64,
}

/// Thread-safe cost accumulator keyed by provider ID.
#[derive(Clone)]
pub struct CostTracker {
    costs: Arc<RwLock<HashMap<String, ProviderCost>>>,
}

impl Default for CostTracker {
    fn default() -> Self {
        Self::new()
    }
}

impl CostTracker {
    /// Create a new empty tracker.
    pub fn new() -> Self {
        Self {
            costs: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    /// Record a completed request's token usage.
    pub async fn record(
        &self,
        provider_id: &str,
        input_tokens: u64,
        output_tokens: u64,
        input_cost_per_token: u64,
        output_cost_per_token: u64,
    ) {
        let cost = input_tokens * input_cost_per_token + output_tokens * output_cost_per_token;
        let mut map = self.costs.write().await;
        let entry = map
            .entry(provider_id.to_string())
            .or_insert_with(|| ProviderCost {
                provider_id: provider_id.to_string(),
                total_input_tokens: 0,
                total_output_tokens: 0,
                total_cost_microcents: 0,
            });
        entry.total_input_tokens += input_tokens;
        entry.total_output_tokens += output_tokens;
        entry.total_cost_microcents += cost;
    }

    /// Return a point-in-time snapshot of all provider costs.
    pub async fn snapshot(&self) -> Vec<ProviderCost> {
        let map = self.costs.read().await;
        map.values().cloned().collect()
    }

    /// Return aggregate cost across all providers.
    pub async fn total_cost_microcents(&self) -> u64 {
        let map = self.costs.read().await;
        map.values().map(|c| c.total_cost_microcents).sum()
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn empty_tracker_has_zero_cost() {
        let tracker = CostTracker::new();
        assert_eq!(tracker.total_cost_microcents().await, 0);
        assert!(tracker.snapshot().await.is_empty());
    }

    #[tokio::test]
    async fn record_accumulates_costs() {
        let tracker = CostTracker::new();
        tracker.record("openai", 100, 50, 30, 150).await;
        // cost = 100*30 + 50*150 = 3000 + 7500 = 10500
        assert_eq!(tracker.total_cost_microcents().await, 10500);
    }

    #[tokio::test]
    async fn multiple_providers_tracked_separately() {
        let tracker = CostTracker::new();
        tracker.record("openai", 100, 50, 30, 150).await;
        tracker.record("anthropic", 200, 100, 15, 75).await;

        let snap = tracker.snapshot().await;
        assert_eq!(snap.len(), 2);

        // openai: 100*30 + 50*150 = 10500
        // anthropic: 200*15 + 100*75 = 3000 + 7500 = 10500
        assert_eq!(tracker.total_cost_microcents().await, 21000);
    }

    #[tokio::test]
    async fn same_provider_accumulates() {
        let tracker = CostTracker::new();
        tracker.record("openai", 100, 50, 30, 150).await;
        tracker.record("openai", 200, 100, 30, 150).await;

        let snap = tracker.snapshot().await;
        assert_eq!(snap.len(), 1);

        let entry = &snap[0];
        assert_eq!(entry.total_input_tokens, 300);
        assert_eq!(entry.total_output_tokens, 150);
        // 100*30+50*150 + 200*30+100*150 = 10500 + 21000 = 31500
        assert_eq!(entry.total_cost_microcents, 31500);
    }

    #[tokio::test]
    async fn snapshot_is_independent_copy() {
        let tracker = CostTracker::new();
        tracker.record("a", 10, 5, 10, 20).await;
        let snap1 = tracker.snapshot().await;
        tracker.record("b", 20, 10, 10, 20).await;
        let snap2 = tracker.snapshot().await;

        assert_eq!(snap1.len(), 1);
        assert_eq!(snap2.len(), 2);
    }
}
