//! Resilience Module (Phase 6: CAB-1105)
//!
//! Circuit breaker and retry patterns for CP API calls.
//!
//! # Circuit Breaker States
//!
//! ```text
//! ┌────────┐  failure_threshold   ┌──────┐
//! │ Closed │  ──────────────────> │ Open │
//! └────────┘                      └──────┘
//!     ↑                              │
//!     │ success                      │ reset_timeout
//!     │                              ↓
//!     │                        ┌──────────┐
//!     └─────────────────────── │ HalfOpen │
//!           success            └──────────┘
//! ```
//!
//! Note: Infrastructure prepared for NativeTool integration (Phase 7).

mod circuit_breaker;
pub mod fallback;
mod retry;

pub use circuit_breaker::{CircuitBreaker, CircuitBreakerConfig, CircuitBreakerError};
pub use circuit_breaker::{CircuitBreakerRegistry, CircuitBreakerStatsEntry};
pub use circuit_breaker::{CircuitBreakerStats, CircuitState};
pub use fallback::{execute_or_direct, FallbackChain};
pub use retry::{retry_with_backoff, retry_with_backoff_if, RetryConfig};
