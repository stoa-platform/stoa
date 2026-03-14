//! A2A (Agent-to-Agent) Protocol Module (CAB-1754)
//!
//! Implements Google's A2A protocol for inter-agent communication with governance.
//! <https://github.com/google/A2A>
//!
//! Endpoints:
//! - GET  /.well-known/agent.json — Agent Card discovery
//! - POST /a2a — JSON-RPC 2.0 task operations (with MCP tool bridge)
//! - Admin: CRUD for agent registrations (under /admin/a2a/agents)

pub mod admin;
pub mod discovery;
pub mod handlers;
pub mod registry;
pub mod types;
