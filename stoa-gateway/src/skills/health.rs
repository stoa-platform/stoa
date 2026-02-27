//! Skill Health Tracker — per-skill success/failure monitoring (CAB-1551)
//!
//! Tracks execution outcomes per skill key with a circuit breaker pattern.
//! Each skill gets its own circuit breaker instance from the shared registry.

use parking_lot::RwLock;
use serde::Serialize;
use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;

use crate::resilience::{CircuitBreakerConfig, CircuitBreakerRegistry};

/// Per-skill health statistics.
#[derive(Debug, Clone, Serialize)]
pub struct SkillHealthStats {
    pub skill_key: String,
    pub success_count: u64,
    pub failure_count: u64,
    pub circuit_state: String,
    pub total_calls: u64,
    pub success_rate: f64,
}

/// Internal counters for a single skill.
struct SkillCounters {
    successes: AtomicU64,
    failures: AtomicU64,
}

/// Tracks health metrics per skill key and integrates with circuit breakers.
pub struct SkillHealthTracker {
    counters: RwLock<HashMap<String, Arc<SkillCounters>>>,
    circuit_breakers: Arc<CircuitBreakerRegistry>,
}

impl SkillHealthTracker {
    /// Create a new tracker with a dedicated circuit breaker registry for skills.
    pub fn new(cb_config: CircuitBreakerConfig) -> Self {
        Self {
            counters: RwLock::new(HashMap::new()),
            circuit_breakers: Arc::new(CircuitBreakerRegistry::new(cb_config)),
        }
    }

    /// Get or create counters for a skill key.
    fn get_counters(&self, skill_key: &str) -> Arc<SkillCounters> {
        {
            let counters = self.counters.read();
            if let Some(c) = counters.get(skill_key) {
                return c.clone();
            }
        }

        let mut counters = self.counters.write();
        counters
            .entry(skill_key.to_string())
            .or_insert_with(|| {
                Arc::new(SkillCounters {
                    successes: AtomicU64::new(0),
                    failures: AtomicU64::new(0),
                })
            })
            .clone()
    }

    /// Check if a skill execution should be allowed (circuit breaker check).
    pub fn allow_execution(&self, skill_key: &str) -> bool {
        let cb = self.circuit_breakers.get_or_create(skill_key);
        cb.allow_request()
    }

    /// Record a successful skill execution.
    pub fn record_success(&self, skill_key: &str) {
        let counters = self.get_counters(skill_key);
        counters.successes.fetch_add(1, Ordering::Relaxed);
        let cb = self.circuit_breakers.get_or_create(skill_key);
        cb.record_success();
    }

    /// Record a failed skill execution.
    pub fn record_failure(&self, skill_key: &str) {
        let counters = self.get_counters(skill_key);
        counters.failures.fetch_add(1, Ordering::Relaxed);
        let cb = self.circuit_breakers.get_or_create(skill_key);
        cb.record_failure();
    }

    /// Get health stats for a specific skill.
    pub fn stats(&self, skill_key: &str) -> SkillHealthStats {
        let counters = self.get_counters(skill_key);
        let successes = counters.successes.load(Ordering::Relaxed);
        let failures = counters.failures.load(Ordering::Relaxed);
        let total = successes + failures;
        let success_rate = if total > 0 {
            successes as f64 / total as f64
        } else {
            1.0
        };

        let cb = self.circuit_breakers.get_or_create(skill_key);
        let state = cb.state();

        SkillHealthStats {
            skill_key: skill_key.to_string(),
            success_count: successes,
            failure_count: failures,
            circuit_state: state.to_string(),
            total_calls: total,
            success_rate,
        }
    }

    /// Get health stats for all tracked skills.
    pub fn stats_all(&self) -> Vec<SkillHealthStats> {
        let counters = self.counters.read();
        counters.keys().map(|key| self.stats(key)).collect()
    }

    /// Reset circuit breaker for a specific skill.
    pub fn reset_circuit_breaker(&self, skill_key: &str) -> bool {
        self.circuit_breakers.reset(skill_key)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;

    fn default_config() -> CircuitBreakerConfig {
        CircuitBreakerConfig {
            failure_threshold: 3,
            reset_timeout: Duration::from_secs(30),
            success_threshold: 2,
            window_size: Duration::from_secs(60),
        }
    }

    #[test]
    fn test_record_success() {
        let tracker = SkillHealthTracker::new(default_config());
        tracker.record_success("ns/my-skill");

        let stats = tracker.stats("ns/my-skill");
        assert_eq!(stats.success_count, 1);
        assert_eq!(stats.failure_count, 0);
        assert_eq!(stats.total_calls, 1);
        assert!((stats.success_rate - 1.0).abs() < f64::EPSILON);
        assert_eq!(stats.circuit_state, "closed");
    }

    #[test]
    fn test_record_failure() {
        let tracker = SkillHealthTracker::new(default_config());
        tracker.record_failure("ns/my-skill");

        let stats = tracker.stats("ns/my-skill");
        assert_eq!(stats.success_count, 0);
        assert_eq!(stats.failure_count, 1);
        assert!((stats.success_rate - 0.0).abs() < f64::EPSILON);
    }

    #[test]
    fn test_circuit_opens_after_threshold() {
        let tracker = SkillHealthTracker::new(default_config());
        tracker.record_failure("ns/flaky");
        tracker.record_failure("ns/flaky");
        tracker.record_failure("ns/flaky");

        let stats = tracker.stats("ns/flaky");
        assert_eq!(stats.circuit_state, "open");
        assert!(!tracker.allow_execution("ns/flaky"));
    }

    #[test]
    fn test_allow_execution_when_closed() {
        let tracker = SkillHealthTracker::new(default_config());
        assert!(tracker.allow_execution("ns/healthy"));
    }

    #[test]
    fn test_mixed_success_failure() {
        let tracker = SkillHealthTracker::new(default_config());
        tracker.record_success("ns/mixed");
        tracker.record_success("ns/mixed");
        tracker.record_failure("ns/mixed");

        let stats = tracker.stats("ns/mixed");
        assert_eq!(stats.total_calls, 3);
        assert!((stats.success_rate - 2.0 / 3.0).abs() < 0.001);
    }

    #[test]
    fn test_stats_all() {
        let tracker = SkillHealthTracker::new(default_config());
        tracker.record_success("ns/a");
        tracker.record_failure("ns/b");

        let all = tracker.stats_all();
        assert_eq!(all.len(), 2);
    }

    #[test]
    fn test_reset_circuit_breaker() {
        let config = CircuitBreakerConfig {
            failure_threshold: 1,
            ..default_config()
        };
        let tracker = SkillHealthTracker::new(config);
        tracker.record_failure("ns/broken");

        assert!(!tracker.allow_execution("ns/broken"));
        assert!(tracker.reset_circuit_breaker("ns/broken"));
        assert!(tracker.allow_execution("ns/broken"));
    }

    #[test]
    fn test_reset_nonexistent_returns_false() {
        let tracker = SkillHealthTracker::new(default_config());
        assert!(!tracker.reset_circuit_breaker("ns/unknown"));
    }

    #[test]
    fn test_no_calls_success_rate_is_one() {
        let tracker = SkillHealthTracker::new(default_config());
        let stats = tracker.stats("ns/new-skill");
        assert!((stats.success_rate - 1.0).abs() < f64::EPSILON);
    }

    #[test]
    fn test_skill_isolation() {
        let tracker = SkillHealthTracker::new(default_config());
        tracker.record_success("ns/a");
        tracker.record_failure("ns/b");

        assert_eq!(tracker.stats("ns/a").success_count, 1);
        assert_eq!(tracker.stats("ns/a").failure_count, 0);
        assert_eq!(tracker.stats("ns/b").success_count, 0);
        assert_eq!(tracker.stats("ns/b").failure_count, 1);
    }
}
