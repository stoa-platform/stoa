//! Policy Engine Module
//!
//! CAB-1094 Phase 2: OPA-based policy evaluation for scope-based access control.
//!
//! Architecture:
//! - Uses `regorus` crate for pure-Rust OPA evaluation (no sidecar)
//! - Policies loaded from filesystem or config
//! - Sub-1ms evaluation (no network hop)
//!
//! Flow:
//! 1. JWT claims extracted (including scopes)
//! 2. PolicyEngine.evaluate() called with: {user, tool, action, tenant, scopes}
//! 3. Rego policy returns allow/deny
//! 4. SSE handler proceeds or returns 403

pub mod opa;

pub use opa::{PolicyDecision, PolicyEngine, PolicyEngineConfig, PolicyInput};
