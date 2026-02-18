//! Skills module — CSS cascade context injection for AI agents (CAB-1314)
//!
//! Provides a resolver that stores skills from K8s CRDs and resolves them
//! using a CSS-like cascade: global < tenant < tool < user specificity.

pub mod resolver;
