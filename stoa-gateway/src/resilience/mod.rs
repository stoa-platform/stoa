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
mod retry;

pub use circuit_breaker::{CircuitBreaker, CircuitBreakerConfig};
#[allow(unused_imports)]
pub use circuit_breaker::{CircuitBreakerStats, CircuitState};
#[allow(unused_imports)]
pub use retry::{retry_with_backoff, RetryConfig};
