//! Resilience Module
//!
//! Production-grade resilience patterns for backend calls:
//! - Circuit breaker: fast-fail on repeated failures
//! - Retry with exponential backoff and jitter
//! - Timeout management

pub mod circuit_breaker;
pub mod retry;

pub use circuit_breaker::{CircuitBreakerConfig, CircuitBreakerRegistry};
pub use retry::{RetryConfig, RetryPolicy};

// Re-export for future use
#[allow(unused_imports)]
pub use circuit_breaker::{CircuitBreaker, CircuitState};
#[allow(unused_imports)]
pub use retry::with_retry;
