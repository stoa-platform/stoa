//! Agent Governance Module
//!
//! Implements ADR-012 Agent Governance policies including:
//! - Anti-zombie agent detection (10min TTL on agent tokens)
//! - Mandatory attestation per session
//! - Automatic token revocation for stale sessions
//!
//! # Overview
//!
//! AI agents (Claude, GPT, etc.) require special governance to prevent:
//! - Runaway agents with stale context
//! - Agents operating beyond their intended scope
//! - Resource exhaustion from zombie sessions
//!
//! # Key Features
//!
//! - **Session TTL**: 10 minute default (configurable)
//! - **Activity tracking**: Monitor last activity per session
//! - **Attestation**: Require periodic re-attestation
//! - **Alerts**: Notify on zombie session detection

#![allow(dead_code)]

pub mod zombie;

// Re-exports
pub use zombie::{ZombieDetector, ZombieConfig, ZombieAlert, SessionHealth};
