//! Skills module — CSS cascade context injection for AI agents (CAB-1314)
//!
//! Provides a resolver that stores skills from K8s CRDs and resolves them
//! using a CSS-like cascade: global < tenant < tool < user specificity.
//! Includes per-skill health tracking with circuit breaker (CAB-1551).

pub mod context;
pub mod health;
pub mod middleware;
pub mod resolver;
