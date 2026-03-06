//! HEGEMON Agent Coordination (CAB-1709)
//!
//! Provides gateway-coordinated claim management for multi-agent workflows.
//! Replaces local `.claude/claims/*.json` + `mkdir` locks with atomic HTTP endpoints.

pub mod claims;
