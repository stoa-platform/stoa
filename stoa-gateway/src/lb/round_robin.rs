//! Round-robin load balancer (CAB-1833).

use std::sync::atomic::{AtomicUsize, Ordering};

use super::LoadBalancer;

/// Lock-free round-robin that skips unhealthy backends.
pub struct RoundRobin {
    counter: AtomicUsize,
    count: usize,
}

impl RoundRobin {
    pub fn new(count: usize) -> Self {
        Self {
            counter: AtomicUsize::new(0),
            count,
        }
    }
}

impl LoadBalancer for RoundRobin {
    fn select(&self, healthy: &[bool]) -> Option<usize> {
        if self.count == 0 {
            return None;
        }
        let start = self.counter.fetch_add(1, Ordering::Relaxed);
        for offset in 0..self.count {
            let idx = (start + offset) % self.count;
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

    #[test]
    fn test_cycles_through_backends() {
        let lb = RoundRobin::new(3);
        let healthy = [true, true, true];
        let a = lb.select(&healthy).unwrap();
        let b = lb.select(&healthy).unwrap();
        let c = lb.select(&healthy).unwrap();
        // All three should be distinct
        assert_ne!(a, b);
        assert_ne!(b, c);
        // Fourth wraps around
        let d = lb.select(&healthy).unwrap();
        assert_eq!(d, a);
    }

    #[test]
    fn test_skips_unhealthy() {
        let lb = RoundRobin::new(3);
        let healthy = [false, true, false];
        for _ in 0..5 {
            assert_eq!(lb.select(&healthy), Some(1));
        }
    }

    #[test]
    fn test_all_unhealthy() {
        let lb = RoundRobin::new(3);
        let healthy = [false, false, false];
        assert_eq!(lb.select(&healthy), None);
    }

    #[test]
    fn test_empty() {
        let lb = RoundRobin::new(0);
        assert_eq!(lb.select(&[]), None);
    }
}
