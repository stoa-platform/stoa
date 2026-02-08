//! MCP (Model Context Protocol) module
//!
//! Implements MCP server functionality:
//! - Discovery endpoints (RFC 9728 OAuth 2.1)
//! - Tool registry and execution
//! - SSE transport (MCP 2025-03-26)
//! - Session management
//! - Elicitation (server-initiated prompts)

pub mod discovery;
pub mod elicitation;
pub mod handlers;
pub mod protocol;
pub mod session;
pub mod sse;
pub mod tools;
