//! Weighted round-robin load balancer (CAB-1833).
//!
//! Pre-computes an index array from weights so selection is O(1).
//! Example: weights [3, 1, 2] -> schedule [0, 0, 0, 1, 2, 2].

use std::sync::atomic::{AtomicUsize, Ordering};

use super::{LoadBalancer, Upstream};

/// Weighted round-robin using a pre-computed schedule.
pub struct Weighted {
    schedule: Vec<usize>,
    counter: AtomicUsize,
}

impl Weighted {
    pub fn new(upstreams: &[Upstream]) -> Self {
        let mut schedule = Vec::new();
        for (i, u) in upstreams.iter().enumerate() {
            for _ in 0..u.weight.max(1) {
                schedule.push(i);
            }
        }
        if schedule.is_empty() {
            // Fallback: at least include each upstream once
            for i in 0..upstreams.len() {
                schedule.push(i);
            }
        }
        Self {
            schedule,
            counter: AtomicUsize::new(0),
        }
    }
}

impl LoadBalancer for Weighted {
    fn select(&self, healthy: &[bool]) -> Option<usize> {
        if self.schedule.is_empty() {
            return None;
        }
        let len = self.schedule.len();
        let start = self.counter.fetch_add(1, Ordering::Relaxed);
        for offset in 0..len {
            let idx = self.schedule[(start + offset) % len];
            if healthy.get(idx).copied().unwrap_or(false) {
                return Some(idx);
            }
        }
        None
    }

    fn report_start(&self, _idx: usize) {}
    fn report_done(&self, _idx: usize) {}
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_upstreams(weights: &[u32]) -> Vec<Upstream> {
        weights
            .iter()
            .enumerate()
            .map(|(i, &w)| Upstream {
                url: format!("http://backend-{i}"),
                weight: w,
                health_check_path: None,
            })
            .collect()
    }

    #[test]
    fn test_respects_weights() {
        let upstreams = make_upstreams(&[3, 1]);
        let lb = Weighted::new(&upstreams);
        let healthy = [true, true];
        let mut counts = [0u32; 2];
        for _ in 0..40 {
            let idx = lb.select(&healthy).unwrap();
            counts[idx] += 1;
        }
        // Backend 0 (weight 3) should get ~3x the traffic of backend 1 (weight 1)
        assert!(counts[0] > counts[1] * 2, "counts: {:?}", counts);
    }

    #[test]
    fn test_skips_unhealthy() {
        let upstreams = make_upstreams(&[3, 1]);
        let lb = Weighted::new(&upstreams);
        let healthy = [false, true];
        for _ in 0..10 {
            assert_eq!(lb.select(&healthy), Some(1));
        }
    }

    #[test]
    fn test_all_unhealthy() {
        let upstreams = make_upstreams(&[3, 1]);
        let lb = Weighted::new(&upstreams);
        let healthy = [false, false];
        assert_eq!(lb.select(&healthy), None);
    }

    #[test]
    fn test_equal_weights() {
        let upstreams = make_upstreams(&[1, 1, 1]);
        let lb = Weighted::new(&upstreams);
        let healthy = [true, true, true];
        let mut counts = [0u32; 3];
        for _ in 0..30 {
            let idx = lb.select(&healthy).unwrap();
            counts[idx] += 1;
        }
        // Equal weights -> equal distribution
        assert_eq!(counts[0], counts[1]);
        assert_eq!(counts[1], counts[2]);
    }
}
