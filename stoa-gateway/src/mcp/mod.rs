//! MCP (Model Context Protocol) module
//!
//! Implements MCP server functionality:
//! - Discovery endpoints (RFC 9728 OAuth 2.1)
//! - Tool registry and execution
//! - SSE transport (MCP 2025-03-26)
//! - Session management
//! - Elicitation (server-initiated prompts)
//! - WebSocket transport (CAB-1345)
//! - Pending request tracker (bidirectional server-initiated requests)

pub mod discovery;
pub mod elicitation;
pub mod handlers;
pub mod lazy_discovery;
pub mod pending_requests;
pub mod protocol;
pub mod resources;
pub mod session;
pub mod sse;
pub mod tools;
pub mod ws;
