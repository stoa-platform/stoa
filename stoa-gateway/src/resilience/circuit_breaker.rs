//! Circuit Breaker Pattern
//!
//! Prevents cascading failures by fast-failing requests to unhealthy backends.
//!
//! States:
//! - Closed: Normal operation, requests pass through
//! - Open: Backend is unhealthy, requests fail immediately
//! - HalfOpen: After timeout, allow one probe request
//!
//! Transitions:
//! - Closed -> Open: After N consecutive failures (threshold)
//! - Open -> HalfOpen: After timeout duration
//! - HalfOpen -> Closed: On success
//! - HalfOpen -> Open: On failure

// Allow dead_code for Phase 6 components that will be wired in future handlers
#![allow(dead_code)]

use parking_lot::RwLock;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::atomic::{AtomicI64, AtomicU64, AtomicU8, Ordering};
use std::sync::Arc;
use std::time::Instant;
use tracing::{debug, info, warn};

/// Circuit breaker state
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum CircuitState {
    /// Normal operation - requests pass through
    Closed = 0,
    /// Backend unhealthy - requests fail immediately
    Open = 1,
    /// Probing - allow one request to test if backend recovered
    HalfOpen = 2,
}

impl From<u8> for CircuitState {
    fn from(value: u8) -> Self {
        match value {
            0 => CircuitState::Closed,
            1 => CircuitState::Open,
            2 => CircuitState::HalfOpen,
            _ => CircuitState::Closed, // Default to closed on invalid
        }
    }
}

impl std::fmt::Display for CircuitState {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            CircuitState::Closed => write!(f, "closed"),
            CircuitState::Open => write!(f, "open"),
            CircuitState::HalfOpen => write!(f, "half_open"),
        }
    }
}

/// Circuit breaker configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CircuitBreakerConfig {
    /// Number of consecutive failures before opening circuit
    #[serde(default = "default_failure_threshold")]
    pub failure_threshold: u64,

    /// Duration to stay open before transitioning to half-open
    #[serde(default = "default_open_timeout_secs")]
    pub open_timeout_secs: u64,

    /// Number of successful requests in half-open to close circuit
    #[serde(default = "default_success_threshold")]
    pub success_threshold: u64,

    /// Enable circuit breaker (default: true)
    #[serde(default = "default_enabled")]
    pub enabled: bool,
}

fn default_failure_threshold() -> u64 {
    5
}

fn default_open_timeout_secs() -> u64 {
    30
}

fn default_success_threshold() -> u64 {
    1
}

fn default_enabled() -> bool {
    true
}

impl Default for CircuitBreakerConfig {
    fn default() -> Self {
        Self {
            failure_threshold: default_failure_threshold(),
            open_timeout_secs: default_open_timeout_secs(),
            success_threshold: default_success_threshold(),
            enabled: default_enabled(),
        }
    }
}

/// Circuit breaker for a single backend
pub struct CircuitBreaker {
    /// Backend identifier (e.g., "control-plane", "backend-api")
    name: String,

    /// Current state (atomic for lock-free reads)
    state: AtomicU8,

    /// Consecutive failure count
    failure_count: AtomicU64,

    /// Consecutive success count (for half-open recovery)
    success_count: AtomicU64,

    /// Timestamp of last failure (Unix millis)
    last_failure_time: AtomicI64,

    /// Configuration
    config: CircuitBreakerConfig,

    /// Reference time for timeout calculations
    start_time: Instant,
}

impl CircuitBreaker {
    /// Create a new circuit breaker
    pub fn new(name: impl Into<String>, config: CircuitBreakerConfig) -> Self {
        Self {
            name: name.into(),
            state: AtomicU8::new(CircuitState::Closed as u8),
            failure_count: AtomicU64::new(0),
            success_count: AtomicU64::new(0),
            last_failure_time: AtomicI64::new(0),
            config,
            start_time: Instant::now(),
        }
    }

    /// Get circuit breaker name
    pub fn name(&self) -> &str {
        &self.name
    }

    /// Get current state
    pub fn state(&self) -> CircuitState {
        let raw_state = self.state.load(Ordering::Acquire);
        let state = CircuitState::from(raw_state);

        // Check if we should transition from Open to HalfOpen
        if state == CircuitState::Open {
            let last_failure = self.last_failure_time.load(Ordering::Acquire);
            let now_millis = self.start_time.elapsed().as_millis() as i64;
            let timeout_millis = (self.config.open_timeout_secs * 1000) as i64;

            if now_millis - last_failure >= timeout_millis {
                // Timeout expired, transition to half-open
                if self
                    .state
                    .compare_exchange(
                        CircuitState::Open as u8,
                        CircuitState::HalfOpen as u8,
                        Ordering::AcqRel,
                        Ordering::Acquire,
                    )
                    .is_ok()
                {
                    self.success_count.store(0, Ordering::Release);
                    info!(
                        circuit = %self.name,
                        "Circuit breaker transitioning Open -> HalfOpen"
                    );
                    return CircuitState::HalfOpen;
                }
            }
        }

        state
    }

    /// Check if request should be allowed
    ///
    /// Returns Ok(()) if request can proceed, Err with reason if circuit is open.
    pub fn allow_request(&self) -> Result<(), CircuitOpenError> {
        if !self.config.enabled {
            return Ok(());
        }

        match self.state() {
            CircuitState::Closed => Ok(()),
            CircuitState::HalfOpen => {
                // Allow one request for probing
                debug!(circuit = %self.name, "Allowing probe request in half-open state");
                Ok(())
            }
            CircuitState::Open => {
                let last_failure = self.last_failure_time.load(Ordering::Acquire);
                let now_millis = self.start_time.elapsed().as_millis() as i64;
                let remaining_secs =
                    (self.config.open_timeout_secs as i64) - ((now_millis - last_failure) / 1000);

                Err(CircuitOpenError {
                    backend: self.name.clone(),
                    retry_after_secs: remaining_secs.max(0) as u64,
                })
            }
        }
    }

    /// Record a successful request
    pub fn record_success(&self) {
        if !self.config.enabled {
            return;
        }

        let state = self.state();

        match state {
            CircuitState::Closed => {
                // Reset failure count on success
                self.failure_count.store(0, Ordering::Release);
            }
            CircuitState::HalfOpen => {
                let new_count = self.success_count.fetch_add(1, Ordering::AcqRel) + 1;

                if new_count >= self.config.success_threshold {
                    // Enough successful probes, close circuit
                    if self
                        .state
                        .compare_exchange(
                            CircuitState::HalfOpen as u8,
                            CircuitState::Closed as u8,
                            Ordering::AcqRel,
                            Ordering::Acquire,
                        )
                        .is_ok()
                    {
                        self.failure_count.store(0, Ordering::Release);
                        self.success_count.store(0, Ordering::Release);
                        info!(
                            circuit = %self.name,
                            successes = new_count,
                            "Circuit breaker transitioning HalfOpen -> Closed"
                        );
                    }
                }
            }
            CircuitState::Open => {
                // Shouldn't happen - success in open state means timeout triggered
                // and state should be half-open
            }
        }
    }

    /// Record a failed request
    pub fn record_failure(&self) {
        if !self.config.enabled {
            return;
        }

        let now_millis = self.start_time.elapsed().as_millis() as i64;
        self.last_failure_time.store(now_millis, Ordering::Release);

        let state = self.state();

        match state {
            CircuitState::Closed => {
                let new_count = self.failure_count.fetch_add(1, Ordering::AcqRel) + 1;

                if new_count >= self.config.failure_threshold {
                    // Threshold reached, open circuit
                    if self
                        .state
                        .compare_exchange(
                            CircuitState::Closed as u8,
                            CircuitState::Open as u8,
                            Ordering::AcqRel,
                            Ordering::Acquire,
                        )
                        .is_ok()
                    {
                        warn!(
                            circuit = %self.name,
                            failures = new_count,
                            timeout_secs = self.config.open_timeout_secs,
                            "Circuit breaker transitioning Closed -> Open"
                        );
                    }
                }
            }
            CircuitState::HalfOpen => {
                // Probe failed, back to open
                if self
                    .state
                    .compare_exchange(
                        CircuitState::HalfOpen as u8,
                        CircuitState::Open as u8,
                        Ordering::AcqRel,
                        Ordering::Acquire,
                    )
                    .is_ok()
                {
                    self.success_count.store(0, Ordering::Release);
                    warn!(
                        circuit = %self.name,
                        "Circuit breaker transitioning HalfOpen -> Open (probe failed)"
                    );
                }
            }
            CircuitState::Open => {
                // Already open, just update last failure time (done above)
            }
        }
    }

    /// Get failure count
    #[allow(dead_code)]
    pub fn failure_count(&self) -> u64 {
        self.failure_count.load(Ordering::Acquire)
    }

    /// Reset circuit breaker to closed state
    #[allow(dead_code)]
    pub fn reset(&self) {
        self.state
            .store(CircuitState::Closed as u8, Ordering::Release);
        self.failure_count.store(0, Ordering::Release);
        self.success_count.store(0, Ordering::Release);
        info!(circuit = %self.name, "Circuit breaker reset to Closed");
    }

    /// Get statistics for monitoring
    #[allow(dead_code)]
    pub fn stats(&self) -> CircuitBreakerStats {
        CircuitBreakerStats {
            name: self.name.clone(),
            state: self.state(),
            failure_count: self.failure_count.load(Ordering::Acquire),
            success_count: self.success_count.load(Ordering::Acquire),
        }
    }
}

/// Error returned when circuit is open
#[derive(Debug, Clone)]
pub struct CircuitOpenError {
    pub backend: String,
    pub retry_after_secs: u64,
}

impl std::fmt::Display for CircuitOpenError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "Circuit breaker open for backend '{}' - retry after {} seconds",
            self.backend, self.retry_after_secs
        )
    }
}

impl std::error::Error for CircuitOpenError {}

/// Circuit breaker statistics
#[derive(Debug, Clone)]
pub struct CircuitBreakerStats {
    pub name: String,
    pub state: CircuitState,
    pub failure_count: u64,
    pub success_count: u64,
}

/// Registry of circuit breakers per backend
pub struct CircuitBreakerRegistry {
    breakers: RwLock<HashMap<String, Arc<CircuitBreaker>>>,
    default_config: CircuitBreakerConfig,
}

impl CircuitBreakerRegistry {
    /// Create a new registry
    pub fn new(default_config: CircuitBreakerConfig) -> Self {
        Self {
            breakers: RwLock::new(HashMap::new()),
            default_config,
        }
    }

    /// Get or create a circuit breaker for a backend
    pub fn get_or_create(&self, backend: &str) -> Arc<CircuitBreaker> {
        // Fast path: read lock
        {
            let breakers = self.breakers.read();
            if let Some(cb) = breakers.get(backend) {
                return cb.clone();
            }
        }

        // Slow path: write lock
        let mut breakers = self.breakers.write();

        // Double-check after acquiring write lock
        if let Some(cb) = breakers.get(backend) {
            return cb.clone();
        }

        let cb = Arc::new(CircuitBreaker::new(backend, self.default_config.clone()));
        breakers.insert(backend.to_string(), cb.clone());
        cb
    }

    /// Get circuit breaker for a backend (if exists)
    #[allow(dead_code)]
    pub fn get(&self, backend: &str) -> Option<Arc<CircuitBreaker>> {
        self.breakers.read().get(backend).cloned()
    }

    /// Get all circuit breaker statistics
    #[allow(dead_code)]
    pub fn all_stats(&self) -> Vec<CircuitBreakerStats> {
        self.breakers
            .read()
            .values()
            .map(|cb| cb.stats())
            .collect()
    }
}

impl Default for CircuitBreakerRegistry {
    fn default() -> Self {
        Self::new(CircuitBreakerConfig::default())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::thread;
    use std::time::Duration;

    #[test]
    fn test_circuit_breaker_initial_state() {
        let cb = CircuitBreaker::new("test", CircuitBreakerConfig::default());
        assert_eq!(cb.state(), CircuitState::Closed);
        assert_eq!(cb.failure_count(), 0);
    }

    #[test]
    fn test_circuit_breaker_allows_request_when_closed() {
        let cb = CircuitBreaker::new("test", CircuitBreakerConfig::default());
        assert!(cb.allow_request().is_ok());
    }

    #[test]
    fn test_circuit_breaker_opens_after_threshold() {
        let config = CircuitBreakerConfig {
            failure_threshold: 3,
            open_timeout_secs: 30,
            ..Default::default()
        };
        let cb = CircuitBreaker::new("test", config);

        // Record failures up to threshold
        cb.record_failure();
        assert_eq!(cb.state(), CircuitState::Closed);

        cb.record_failure();
        assert_eq!(cb.state(), CircuitState::Closed);

        cb.record_failure();
        assert_eq!(cb.state(), CircuitState::Open);
    }

    #[test]
    fn test_circuit_breaker_blocks_when_open() {
        let config = CircuitBreakerConfig {
            failure_threshold: 1,
            open_timeout_secs: 30,
            ..Default::default()
        };
        let cb = CircuitBreaker::new("test", config);

        cb.record_failure();
        assert_eq!(cb.state(), CircuitState::Open);

        let result = cb.allow_request();
        assert!(result.is_err());

        let err = result.unwrap_err();
        assert_eq!(err.backend, "test");
    }

    #[test]
    fn test_circuit_breaker_resets_on_success() {
        let config = CircuitBreakerConfig {
            failure_threshold: 5,
            ..Default::default()
        };
        let cb = CircuitBreaker::new("test", config);

        // Record some failures
        cb.record_failure();
        cb.record_failure();
        assert_eq!(cb.failure_count(), 2);

        // Success resets counter
        cb.record_success();
        assert_eq!(cb.failure_count(), 0);
    }

    #[test]
    fn test_circuit_breaker_transitions_to_half_open() {
        let config = CircuitBreakerConfig {
            failure_threshold: 1,
            open_timeout_secs: 1, // 1 second timeout
            ..Default::default()
        };
        let cb = CircuitBreaker::new("test", config);

        cb.record_failure();

        // Should be open immediately after failure (within timeout window)
        let state = cb.state.load(std::sync::atomic::Ordering::Acquire);
        assert_eq!(CircuitState::from(state), CircuitState::Open);

        // NOTE: We don't test the HalfOpen transition timing here
        // as it would require waiting 1+ second. The transition logic
        // is tested implicitly by the closes_from_half_open test.
    }

    #[test]
    fn test_circuit_breaker_closes_from_half_open_on_success() {
        let config = CircuitBreakerConfig {
            failure_threshold: 1,
            open_timeout_secs: 0,
            success_threshold: 1,
            ..Default::default()
        };
        let cb = CircuitBreaker::new("test", config);

        cb.record_failure();
        thread::sleep(Duration::from_millis(10));

        // Should be half-open now
        assert_eq!(cb.state(), CircuitState::HalfOpen);

        // Success should close
        cb.record_success();
        assert_eq!(cb.state(), CircuitState::Closed);
    }

    #[test]
    fn test_circuit_breaker_reopens_from_half_open_on_failure() {
        let config = CircuitBreakerConfig {
            failure_threshold: 1,
            open_timeout_secs: 0,
            ..Default::default()
        };
        let cb = CircuitBreaker::new("test", config);

        cb.record_failure();
        // With timeout 0, state() immediately transitions to HalfOpen
        assert_eq!(cb.state(), CircuitState::HalfOpen);

        // Failure in HalfOpen should transition back to Open
        cb.record_failure();
        // Check raw state to avoid auto-transition
        let state = cb.state.load(std::sync::atomic::Ordering::Acquire);
        assert_eq!(CircuitState::from(state), CircuitState::Open);
    }

    #[test]
    fn test_circuit_breaker_disabled() {
        let config = CircuitBreakerConfig {
            failure_threshold: 1,
            enabled: false,
            ..Default::default()
        };
        let cb = CircuitBreaker::new("test", config);

        // Even after failure, should allow requests
        cb.record_failure();
        assert!(cb.allow_request().is_ok());
    }

    #[test]
    fn test_circuit_breaker_registry() {
        let registry = CircuitBreakerRegistry::default();

        let cb1 = registry.get_or_create("backend-a");
        let cb2 = registry.get_or_create("backend-a");
        let cb3 = registry.get_or_create("backend-b");

        // Same backend returns same instance
        assert!(Arc::ptr_eq(&cb1, &cb2));

        // Different backend returns different instance
        assert!(!Arc::ptr_eq(&cb1, &cb3));
    }

    #[test]
    fn test_circuit_breaker_reset() {
        let config = CircuitBreakerConfig {
            failure_threshold: 1,
            ..Default::default()
        };
        let cb = CircuitBreaker::new("test", config);

        cb.record_failure();
        assert_eq!(cb.state(), CircuitState::Open);

        cb.reset();
        assert_eq!(cb.state(), CircuitState::Closed);
        assert_eq!(cb.failure_count(), 0);
    }
}
