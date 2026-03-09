//! A2A (Agent-to-Agent) Protocol Module (CAB-1754)
//!
//! Implements Google's A2A protocol for inter-agent communication with governance.
//! <https://github.com/google/A2A>
//!
//! Endpoints:
//! - GET  /.well-known/agent.json — Agent Card discovery
//! - POST /a2a — JSON-RPC 2.0 task operations
//! - GET  /a2a/agents — List registered agent cards

pub mod discovery;
pub mod handlers;
pub mod registry;
pub mod types;
