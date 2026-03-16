//! Multi-upstream load balancing (CAB-1833).
//!
//! Provides pluggable load balancing strategies for routes with multiple
//! upstream backends. Each strategy implements the [`LoadBalancer`] trait
//! and uses lock-free atomics on the hot path.

pub mod least_conn;
pub mod round_robin;
pub mod weighted;

use serde::{Deserialize, Serialize};

use rand::rngs::SmallRng;
use rand::RngExt;
use std::cell::RefCell;

/// A backend upstream target.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Upstream {
    pub url: String,
    #[serde(default = "default_weight")]
    pub weight: u32,
    #[serde(default)]
    pub health_check_path: Option<String>,
}

fn default_weight() -> u32 {
    1
}

/// Load balancer strategy.
#[derive(Debug, Clone, Copy, Serialize, Deserialize, Default, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum LbStrategy {
    #[default]
    RoundRobin,
    Weighted,
    LeastConn,
    Random,
}

impl std::fmt::Display for LbStrategy {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            LbStrategy::RoundRobin => write!(f, "round_robin"),
            LbStrategy::Weighted => write!(f, "weighted"),
            LbStrategy::LeastConn => write!(f, "least_conn"),
            LbStrategy::Random => write!(f, "random"),
        }
    }
}

/// Load balancer trait.
pub trait LoadBalancer: Send + Sync {
    /// Select the next upstream, skipping unhealthy ones.
    fn select(&self, healthy: &[bool]) -> Option<usize>;
    /// Report that a request started (for least_conn tracking).
    fn report_start(&self, idx: usize);
    /// Report that a request finished (for least_conn tracking).
    fn report_done(&self, idx: usize);
}

/// Create a [`LoadBalancer`] for the given strategy and upstreams.
pub fn create(strategy: LbStrategy, upstreams: &[Upstream]) -> Box<dyn LoadBalancer> {
    match strategy {
        LbStrategy::RoundRobin => Box::new(round_robin::RoundRobin::new(upstreams.len())),
        LbStrategy::Weighted => Box::new(weighted::Weighted::new(upstreams)),
        LbStrategy::LeastConn => Box::new(least_conn::LeastConn::new(upstreams.len())),
        LbStrategy::Random => Box::new(RandomLb::new(upstreams.len())),
    }
}

/// Random load balancer — picks a random healthy upstream.
struct RandomLb {
    count: usize,
}

impl RandomLb {
    fn new(count: usize) -> Self {
        Self { count }
    }
}

thread_local! {
    static LB_RNG: RefCell<SmallRng> = RefCell::new(rand::make_rng());
}

impl LoadBalancer for RandomLb {
    fn select(&self, healthy: &[bool]) -> Option<usize> {
        let healthy_indices: Vec<usize> = (0..self.count)
            .filter(|&i| healthy.get(i).copied().unwrap_or(false))
            .collect();
        if healthy_indices.is_empty() {
            return None;
        }
        let idx = LB_RNG.with(|rng| {
            let mut rng = rng.borrow_mut();
            rng.random_range(0..healthy_indices.len())
        });
        Some(healthy_indices[idx])
    }

    fn report_start(&self, _idx: usize) {}
    fn report_done(&self, _idx: usize) {}
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_random_returns_valid_index() {
        let lb = RandomLb::new(3);
        let healthy = [true, true, true];
        for _ in 0..20 {
            let idx = lb.select(&healthy);
            assert!(idx.is_some());
            assert!(idx.unwrap() < 3);
        }
    }

    #[test]
    fn test_random_skips_unhealthy() {
        let lb = RandomLb::new(3);
        let healthy = [false, true, false];
        for _ in 0..20 {
            let idx = lb.select(&healthy);
            assert_eq!(idx, Some(1));
        }
    }

    #[test]
    fn test_random_all_unhealthy_returns_none() {
        let lb = RandomLb::new(3);
        let healthy = [false, false, false];
        assert_eq!(lb.select(&healthy), None);
    }

    #[test]
    fn test_create_strategies() {
        let upstreams = vec![
            Upstream {
                url: "http://a".into(),
                weight: 1,
                health_check_path: None,
            },
            Upstream {
                url: "http://b".into(),
                weight: 2,
                health_check_path: None,
            },
        ];
        let healthy = [true, true];

        let rr = create(LbStrategy::RoundRobin, &upstreams);
        assert!(rr.select(&healthy).is_some());

        let w = create(LbStrategy::Weighted, &upstreams);
        assert!(w.select(&healthy).is_some());

        let lc = create(LbStrategy::LeastConn, &upstreams);
        assert!(lc.select(&healthy).is_some());

        let r = create(LbStrategy::Random, &upstreams);
        assert!(r.select(&healthy).is_some());
    }

    #[test]
    fn test_lb_strategy_display() {
        assert_eq!(LbStrategy::RoundRobin.to_string(), "round_robin");
        assert_eq!(LbStrategy::Weighted.to_string(), "weighted");
        assert_eq!(LbStrategy::LeastConn.to_string(), "least_conn");
        assert_eq!(LbStrategy::Random.to_string(), "random");
    }

    #[test]
    fn test_upstream_default_weight() {
        let json = r#"{"url":"http://localhost:8080"}"#;
        let u: Upstream = serde_json::from_str(json).expect("deserialize");
        assert_eq!(u.weight, 1);
    }

    #[test]
    fn test_lb_strategy_serde() {
        let json = r#""least_conn""#;
        let s: LbStrategy = serde_json::from_str(json).expect("deserialize");
        assert_eq!(s, LbStrategy::LeastConn);
    }
}
