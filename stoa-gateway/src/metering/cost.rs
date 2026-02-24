//! Cost Computation Module (CAB-1456)
//!
//! Informational cost estimates for metering enrichment.
//! The Control Plane API is the financial source of truth —
//! these values are advisory only, used for dashboards and alerts.

/// Base cost per tool call in micro-cents (100 microcents = 0.1 cent)
const BASE_COST_MICROCENTS: i64 = 100;

/// Cost per token in micro-cents (1 microcent/token)
const TOKEN_COST_MICROCENTS: i64 = 1;

/// Cost per millisecond of latency in micro-cents (0.1 microcent/ms)
const LATENCY_COST_PER_10MS: i64 = 1;

/// Premium tier multiplier
const PREMIUM_MULTIPLIER: i64 = 2;

/// Compute the informational cost of a tool call in micro-cents.
///
/// Formula: `base_cost (100) + token_cost (1/token) + latency_cost (0.1/ms)`
/// Premium tier applies a 2x multiplier to the total.
///
/// Returns micro-cents (1 cent = 10_000 micro-cents).
pub fn compute_cost(token_count: u64, latency_ms: u64, tool_tier: &str) -> i64 {
    let token_cost = token_count as i64 * TOKEN_COST_MICROCENTS;
    let latency_cost = (latency_ms as i64) * LATENCY_COST_PER_10MS / 10;
    let base = BASE_COST_MICROCENTS + token_cost + latency_cost;

    if tool_tier == "premium" {
        base * PREMIUM_MULTIPLIER
    } else {
        base
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_standard_tier_base_cost() {
        let cost = compute_cost(0, 0, "standard");
        assert_eq!(cost, 100);
    }

    #[test]
    fn test_standard_tier_with_tokens() {
        let cost = compute_cost(500, 0, "standard");
        assert_eq!(cost, 600);
    }

    #[test]
    fn test_standard_tier_with_latency() {
        let cost = compute_cost(0, 200, "standard");
        assert_eq!(cost, 120);
    }

    #[test]
    fn test_standard_tier_combined() {
        let cost = compute_cost(1000, 100, "standard");
        assert_eq!(cost, 1110);
    }

    #[test]
    fn test_premium_tier_multiplier() {
        let standard = compute_cost(1000, 100, "standard");
        let premium = compute_cost(1000, 100, "premium");
        assert_eq!(premium, standard * 2);
    }

    #[test]
    fn test_premium_tier_base_only() {
        let cost = compute_cost(0, 0, "premium");
        assert_eq!(cost, 200);
    }

    #[test]
    fn test_zero_tokens_zero_latency() {
        let cost = compute_cost(0, 0, "standard");
        assert_eq!(cost, BASE_COST_MICROCENTS);
    }

    #[test]
    fn test_high_latency() {
        let cost = compute_cost(0, 10_000, "standard");
        assert_eq!(cost, 1100);
    }

    #[test]
    fn test_unknown_tier_treated_as_standard() {
        let standard = compute_cost(100, 50, "standard");
        let unknown = compute_cost(100, 50, "unknown");
        assert_eq!(unknown, standard);
    }
}
