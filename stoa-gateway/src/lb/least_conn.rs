//! Least-connections load balancer (CAB-1833).
//!
//! Picks the healthy upstream with the fewest active connections.
//! Uses `AtomicU32` per upstream for lock-free tracking.

use std::sync::atomic::{AtomicU32, Ordering};

use super::LoadBalancer;

/// Least-connections: picks the upstream with the lowest active count.
pub struct LeastConn {
    active: Vec<AtomicU32>,
}

impl LeastConn {
    pub fn new(count: usize) -> Self {
        let mut active = Vec::with_capacity(count);
        for _ in 0..count {
            active.push(AtomicU32::new(0));
        }
        Self { active }
    }
}

impl LoadBalancer for LeastConn {
    fn select(&self, healthy: &[bool]) -> Option<usize> {
        let mut best: Option<usize> = None;
        let mut best_count = u32::MAX;
        for (i, counter) in self.active.iter().enumerate() {
            if !healthy.get(i).copied().unwrap_or(false) {
                continue;
            }
            let count = counter.load(Ordering::Relaxed);
            if count < best_count {
                best_count = count;
                best = Some(i);
            }
        }
        best
    }

    fn report_start(&self, idx: usize) {
        if let Some(counter) = self.active.get(idx) {
            counter.fetch_add(1, Ordering::Relaxed);
        }
    }

    fn report_done(&self, idx: usize) {
        if let Some(counter) = self.active.get(idx) {
            counter.fetch_sub(1, Ordering::Relaxed);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_picks_lowest_active() {
        let lb = LeastConn::new(3);
        let healthy = [true, true, true];
        // Simulate: backend 0 has 5 active, backend 1 has 2, backend 2 has 3
        for _ in 0..5 {
            lb.report_start(0);
        }
        for _ in 0..2 {
            lb.report_start(1);
        }
        for _ in 0..3 {
            lb.report_start(2);
        }
        assert_eq!(lb.select(&healthy), Some(1));
    }

    #[test]
    fn test_handles_tie_breaking() {
        let lb = LeastConn::new(3);
        let healthy = [true, true, true];
        // All at 0 — first healthy wins (deterministic tie-break)
        assert_eq!(lb.select(&healthy), Some(0));
    }

    #[test]
    fn test_skips_unhealthy() {
        let lb = LeastConn::new(3);
        let healthy = [false, true, true];
        // Backend 1 has more active than backend 2
        lb.report_start(1);
        lb.report_start(1);
        lb.report_start(2);
        assert_eq!(lb.select(&healthy), Some(2));
    }

    #[test]
    fn test_report_start_done() {
        let lb = LeastConn::new(2);
        let healthy = [true, true];
        lb.report_start(0);
        lb.report_start(0);
        lb.report_start(1);
        // Backend 1 has fewer active
        assert_eq!(lb.select(&healthy), Some(1));
        // Complete one request on backend 0
        lb.report_done(0);
        // Now backend 0 has 1, backend 1 has 1 — tie goes to 0
        assert_eq!(lb.select(&healthy), Some(0));
    }

    #[test]
    fn test_all_unhealthy() {
        let lb = LeastConn::new(2);
        let healthy = [false, false];
        assert_eq!(lb.select(&healthy), None);
    }
}
