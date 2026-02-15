//! Circuit Breaker Pattern
//!
//! Prevents cascading failures by fast-failing when backend is unhealthy.
//!
//! Hystrix-style state machine: Closed → Open → HalfOpen → Closed
//!
//! Note: Infrastructure prepared for NativeTool wrapping (Phase 7).

// Circuit breaker infrastructure - some fields used for future monitoring
#![allow(dead_code)]

use parking_lot::RwLock;
use serde::Serialize;
use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tracing::{debug, info, warn};

use crate::metrics;

/// Circuit breaker state
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CircuitState {
    /// Normal operation - requests pass through
    Closed,
    /// Circuit tripped - requests fail fast
    Open,
    /// Testing if backend recovered - limited requests allowed
    HalfOpen,
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
#[derive(Debug, Clone)]
pub struct CircuitBreakerConfig {
    /// Number of failures before opening circuit
    pub failure_threshold: u32,
    /// Time to wait before trying half-open
    pub reset_timeout: Duration,
    /// Number of successes needed to close from half-open
    pub success_threshold: u32,
    /// Rolling window for failure counting
    pub window_size: Duration,
}

impl Default for CircuitBreakerConfig {
    fn default() -> Self {
        Self {
            failure_threshold: 5,
            reset_timeout: Duration::from_secs(30),
            success_threshold: 2,
            window_size: Duration::from_secs(60),
        }
    }
}

/// Circuit breaker statistics
#[derive(Debug, Clone)]
pub struct CircuitBreakerStats {
    /// Current state
    pub state: CircuitState,
    /// Total successful calls
    pub success_count: u64,
    /// Total failed calls
    pub failure_count: u64,
    /// Current consecutive failures
    pub consecutive_failures: u32,
    /// Number of times circuit opened
    pub open_count: u64,
    /// Number of rejected calls (fast-fail)
    pub rejected_count: u64,
    /// Last state change timestamp
    pub last_state_change: Option<Instant>,
}

/// Internal mutable state
struct CircuitBreakerState {
    state: CircuitState,
    consecutive_failures: u32,
    half_open_successes: u32,
    last_failure_time: Option<Instant>,
    last_state_change: Option<Instant>,
}

/// Thread-safe circuit breaker
pub struct CircuitBreaker {
    name: String,
    config: CircuitBreakerConfig,
    state: RwLock<CircuitBreakerState>,
    // Atomic counters for metrics (no lock needed)
    success_count: AtomicU64,
    failure_count: AtomicU64,
    open_count: AtomicU64,
    rejected_count: AtomicU64,
}

impl CircuitBreaker {
    /// Create a new circuit breaker
    pub fn new(name: impl Into<String>, config: CircuitBreakerConfig) -> Arc<Self> {
        Arc::new(Self {
            name: name.into(),
            config,
            state: RwLock::new(CircuitBreakerState {
                state: CircuitState::Closed,
                consecutive_failures: 0,
                half_open_successes: 0,
                last_failure_time: None,
                last_state_change: Some(Instant::now()),
            }),
            success_count: AtomicU64::new(0),
            failure_count: AtomicU64::new(0),
            open_count: AtomicU64::new(0),
            rejected_count: AtomicU64::new(0),
        })
    }

    /// Get current state
    pub fn state(&self) -> CircuitState {
        let state = self.state.read();
        self.effective_state(&state)
    }

    /// Get statistics
    pub fn stats(&self) -> CircuitBreakerStats {
        let state = self.state.read();
        CircuitBreakerStats {
            state: self.effective_state(&state),
            success_count: self.success_count.load(Ordering::Relaxed),
            failure_count: self.failure_count.load(Ordering::Relaxed),
            consecutive_failures: state.consecutive_failures,
            open_count: self.open_count.load(Ordering::Relaxed),
            rejected_count: self.rejected_count.load(Ordering::Relaxed),
            last_state_change: state.last_state_change,
        }
    }

    /// Check effective state (handles timeout transitions)
    fn effective_state(&self, state: &CircuitBreakerState) -> CircuitState {
        match state.state {
            CircuitState::Open => {
                // Check if reset timeout has passed
                if let Some(last_failure) = state.last_failure_time {
                    if last_failure.elapsed() >= self.config.reset_timeout {
                        return CircuitState::HalfOpen;
                    }
                }
                CircuitState::Open
            }
            other => other,
        }
    }

    /// Check if request should be allowed
    pub fn allow_request(&self) -> bool {
        let state = self.state.read();
        let effective = self.effective_state(&state);

        match effective {
            CircuitState::Closed => true,
            CircuitState::HalfOpen => true, // Allow limited requests
            CircuitState::Open => {
                self.rejected_count.fetch_add(1, Ordering::Relaxed);
                debug!(
                    circuit = %self.name,
                    "Circuit open - request rejected"
                );
                false
            }
        }
    }

    /// Record a successful call
    pub fn record_success(&self) {
        self.success_count.fetch_add(1, Ordering::Relaxed);

        let mut state = self.state.write();
        let effective = self.effective_state(&state);

        match effective {
            CircuitState::Closed => {
                // Reset consecutive failures on success
                state.consecutive_failures = 0;
            }
            CircuitState::HalfOpen => {
                state.half_open_successes += 1;
                if state.half_open_successes >= self.config.success_threshold {
                    // Close the circuit
                    info!(
                        circuit = %self.name,
                        "Circuit closing after {} successes in half-open",
                        state.half_open_successes
                    );
                    state.state = CircuitState::Closed;
                    state.consecutive_failures = 0;
                    state.half_open_successes = 0;
                    state.last_state_change = Some(Instant::now());
                    metrics::update_circuit_breaker_state(&self.name, 0.0);
                }
            }
            CircuitState::Open => {
                // Shouldn't happen, but handle gracefully
                state.state = CircuitState::HalfOpen;
                state.half_open_successes = 1;
                state.last_state_change = Some(Instant::now());
                metrics::update_circuit_breaker_state(&self.name, 2.0);
            }
        }
    }

    /// Record a failed call
    pub fn record_failure(&self) {
        self.failure_count.fetch_add(1, Ordering::Relaxed);

        let mut state = self.state.write();
        state.consecutive_failures += 1;
        state.last_failure_time = Some(Instant::now());

        let effective = self.effective_state(&state);

        match effective {
            CircuitState::Closed => {
                if state.consecutive_failures >= self.config.failure_threshold {
                    // Open the circuit
                    warn!(
                        circuit = %self.name,
                        failures = state.consecutive_failures,
                        "Circuit opening after {} consecutive failures",
                        state.consecutive_failures
                    );
                    state.state = CircuitState::Open;
                    state.last_state_change = Some(Instant::now());
                    self.open_count.fetch_add(1, Ordering::Relaxed);
                    metrics::update_circuit_breaker_state(&self.name, 1.0);
                }
            }
            CircuitState::HalfOpen => {
                // Failure in half-open → back to open
                warn!(
                    circuit = %self.name,
                    "Circuit reopening after failure in half-open state"
                );
                state.state = CircuitState::Open;
                state.half_open_successes = 0;
                state.last_state_change = Some(Instant::now());
                self.open_count.fetch_add(1, Ordering::Relaxed);
                metrics::update_circuit_breaker_state(&self.name, 1.0);
            }
            CircuitState::Open => {
                // Already open, just update last failure time
            }
        }
    }

    /// Execute a fallible operation with circuit breaker protection
    pub async fn call<F, T, E>(&self, f: F) -> Result<T, CircuitBreakerError<E>>
    where
        F: std::future::Future<Output = Result<T, E>>,
    {
        if !self.allow_request() {
            return Err(CircuitBreakerError::CircuitOpen);
        }

        // Transition to half-open if needed (lazy state update)
        {
            let mut state = self.state.write();
            if state.state == CircuitState::Open {
                if let Some(last_failure) = state.last_failure_time {
                    if last_failure.elapsed() >= self.config.reset_timeout {
                        debug!(circuit = %self.name, "Circuit transitioning to half-open");
                        state.state = CircuitState::HalfOpen;
                        state.half_open_successes = 0;
                        state.last_state_change = Some(Instant::now());
                    }
                }
            }
        }

        match f.await {
            Ok(result) => {
                self.record_success();
                Ok(result)
            }
            Err(e) => {
                self.record_failure();
                Err(CircuitBreakerError::OperationFailed(e))
            }
        }
    }

    /// Reset the circuit breaker to closed state (admin operation)
    pub fn reset(&self) {
        let mut state = self.state.write();
        info!(circuit = %self.name, "Circuit manually reset to closed");
        state.state = CircuitState::Closed;
        state.consecutive_failures = 0;
        state.half_open_successes = 0;
        state.last_failure_time = None;
        state.last_state_change = Some(Instant::now());
        metrics::update_circuit_breaker_state(&self.name, 0.0);
    }

    /// Get the circuit breaker name
    pub fn name(&self) -> &str {
        &self.name
    }
}

// =============================================================================
// Circuit Breaker Registry (CAB-362)
// =============================================================================

/// Thread-safe registry of per-upstream circuit breakers.
///
/// Each upstream backend gets its own circuit breaker, created lazily on first
/// request. This prevents a single unhealthy upstream from cascading failures
/// to all other upstreams routed through the dynamic proxy.
pub struct CircuitBreakerRegistry {
    breakers: RwLock<HashMap<String, Arc<CircuitBreaker>>>,
    default_config: CircuitBreakerConfig,
}

impl CircuitBreakerRegistry {
    /// Create a new registry with the given default config for new circuit breakers.
    pub fn new(default_config: CircuitBreakerConfig) -> Self {
        Self {
            breakers: RwLock::new(HashMap::new()),
            default_config,
        }
    }

    /// Get an existing circuit breaker or create a new one for the given upstream name.
    pub fn get_or_create(&self, name: &str) -> Arc<CircuitBreaker> {
        // Fast path: read lock
        {
            let breakers = self.breakers.read();
            if let Some(cb) = breakers.get(name) {
                return cb.clone();
            }
        }

        // Slow path: write lock to insert
        let mut breakers = self.breakers.write();
        // Double-check after acquiring write lock
        if let Some(cb) = breakers.get(name) {
            return cb.clone();
        }

        let cb = CircuitBreaker::new(name, self.default_config.clone());
        breakers.insert(name.to_string(), cb.clone());
        cb
    }

    /// Check if the circuit breaker for the given name is open (fast-failing).
    ///
    /// Returns false if no circuit breaker exists for the name (optimistic).
    pub fn is_open(&self, name: &str) -> bool {
        let breakers = self.breakers.read();
        match breakers.get(name) {
            Some(cb) => !cb.allow_request(),
            None => false, // No breaker = healthy (optimistic)
        }
    }

    /// Get stats for all circuit breakers.
    pub fn stats_all(&self) -> Vec<CircuitBreakerStatsEntry> {
        let breakers = self.breakers.read();
        breakers
            .iter()
            .map(|(name, cb)| {
                let stats = cb.stats();
                CircuitBreakerStatsEntry {
                    name: name.clone(),
                    state: stats.state.to_string(),
                    success_count: stats.success_count,
                    failure_count: stats.failure_count,
                    consecutive_failures: stats.consecutive_failures,
                    open_count: stats.open_count,
                    rejected_count: stats.rejected_count,
                }
            })
            .collect()
    }

    /// Reset a specific circuit breaker by name.
    pub fn reset(&self, name: &str) -> bool {
        let breakers = self.breakers.read();
        if let Some(cb) = breakers.get(name) {
            cb.reset();
            true
        } else {
            false
        }
    }
}

/// Stats entry for a single circuit breaker in the registry.
#[derive(Debug, Clone, Serialize)]
pub struct CircuitBreakerStatsEntry {
    pub name: String,
    pub state: String,
    pub success_count: u64,
    pub failure_count: u64,
    pub consecutive_failures: u32,
    pub open_count: u64,
    pub rejected_count: u64,
}

/// Circuit breaker error
#[derive(Debug)]
pub enum CircuitBreakerError<E> {
    /// Circuit is open - request rejected
    CircuitOpen,
    /// Operation failed
    OperationFailed(E),
}

impl<E: std::fmt::Display> std::fmt::Display for CircuitBreakerError<E> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            CircuitBreakerError::CircuitOpen => write!(f, "Circuit breaker is open"),
            CircuitBreakerError::OperationFailed(e) => write!(f, "Operation failed: {}", e),
        }
    }
}

impl<E: std::error::Error + 'static> std::error::Error for CircuitBreakerError<E> {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            CircuitBreakerError::CircuitOpen => None,
            CircuitBreakerError::OperationFailed(e) => Some(e),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_circuit_breaker_starts_closed() {
        let cb = CircuitBreaker::new("test", CircuitBreakerConfig::default());
        assert_eq!(cb.state(), CircuitState::Closed);
        assert!(cb.allow_request());
    }

    #[test]
    fn test_circuit_opens_after_threshold() {
        let config = CircuitBreakerConfig {
            failure_threshold: 3,
            ..Default::default()
        };
        let cb = CircuitBreaker::new("test", config);

        // Record 3 failures
        cb.record_failure();
        assert_eq!(cb.state(), CircuitState::Closed);
        cb.record_failure();
        assert_eq!(cb.state(), CircuitState::Closed);
        cb.record_failure();
        assert_eq!(cb.state(), CircuitState::Open);

        // Should reject requests
        assert!(!cb.allow_request());
    }

    #[test]
    fn test_success_resets_failures() {
        let config = CircuitBreakerConfig {
            failure_threshold: 3,
            ..Default::default()
        };
        let cb = CircuitBreaker::new("test", config);

        cb.record_failure();
        cb.record_failure();
        cb.record_success(); // Should reset
        cb.record_failure();
        cb.record_failure();

        // Still closed (1 failure after reset + 2 = 3, but success reset it)
        assert_eq!(cb.state(), CircuitState::Closed);
    }

    #[test]
    fn test_reset_closes_circuit() {
        let config = CircuitBreakerConfig {
            failure_threshold: 1,
            ..Default::default()
        };
        let cb = CircuitBreaker::new("test", config);

        cb.record_failure();
        assert_eq!(cb.state(), CircuitState::Open);

        cb.reset();
        assert_eq!(cb.state(), CircuitState::Closed);
        assert!(cb.allow_request());
    }

    #[test]
    fn test_stats() {
        let cb = CircuitBreaker::new("test", CircuitBreakerConfig::default());

        cb.record_success();
        cb.record_success();
        cb.record_failure();

        let stats = cb.stats();
        assert_eq!(stats.success_count, 2);
        assert_eq!(stats.failure_count, 1);
        assert_eq!(stats.state, CircuitState::Closed);
    }

    #[tokio::test]
    async fn test_half_open_transition() {
        let config = CircuitBreakerConfig {
            failure_threshold: 1,
            reset_timeout: Duration::from_millis(10),
            success_threshold: 1,
            ..Default::default()
        };
        let cb = CircuitBreaker::new("test", config);

        cb.record_failure();
        assert_eq!(cb.state(), CircuitState::Open);

        // Wait for reset timeout
        tokio::time::sleep(Duration::from_millis(15)).await;

        // Should transition to half-open
        assert_eq!(cb.state(), CircuitState::HalfOpen);
        assert!(cb.allow_request());
    }

    #[tokio::test]
    async fn test_half_open_closes_on_success() {
        let config = CircuitBreakerConfig {
            failure_threshold: 1,
            reset_timeout: Duration::from_millis(10),
            success_threshold: 1,
            ..Default::default()
        };
        let cb = CircuitBreaker::new("test", config);

        cb.record_failure();
        tokio::time::sleep(Duration::from_millis(15)).await;

        // In half-open
        assert_eq!(cb.state(), CircuitState::HalfOpen);

        // Record success
        cb.record_success();
        assert_eq!(cb.state(), CircuitState::Closed);
    }

    #[tokio::test]
    async fn test_call_with_success() {
        let cb = CircuitBreaker::new("test", CircuitBreakerConfig::default());

        let result: Result<i32, CircuitBreakerError<&str>> =
            cb.call(async { Ok::<i32, &str>(42) }).await;

        assert!(result.is_ok());
        assert_eq!(result.unwrap(), 42);
        assert_eq!(cb.stats().success_count, 1);
    }

    #[tokio::test]
    async fn test_call_with_failure() {
        let config = CircuitBreakerConfig {
            failure_threshold: 2,
            ..Default::default()
        };
        let cb = CircuitBreaker::new("test", config);

        let result: Result<i32, CircuitBreakerError<&str>> =
            cb.call(async { Err::<i32, &str>("error") }).await;

        assert!(matches!(
            result,
            Err(CircuitBreakerError::OperationFailed("error"))
        ));
        assert_eq!(cb.stats().failure_count, 1);
    }

    #[tokio::test]
    async fn test_call_rejected_when_open() {
        let config = CircuitBreakerConfig {
            failure_threshold: 1,
            ..Default::default()
        };
        let cb = CircuitBreaker::new("test", config);

        // Open the circuit
        cb.record_failure();

        let result: Result<i32, CircuitBreakerError<&str>> =
            cb.call(async { Ok::<i32, &str>(42) }).await;

        assert!(matches!(result, Err(CircuitBreakerError::CircuitOpen)));
        assert_eq!(cb.stats().rejected_count, 1);
    }
}
