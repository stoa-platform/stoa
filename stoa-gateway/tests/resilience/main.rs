//! Resilience tests for STOA Gateway
//!
//! Tests circuit breaker integration, fault injection (CP/Keycloak down),
//! and concurrency under load via the full Axum router.
//!
//! Run: `cargo test --test resilience`

mod circuit_breaker;
mod common;
mod concurrency;
mod fault_injection;
