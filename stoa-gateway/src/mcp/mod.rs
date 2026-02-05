//! MCP (Model Context Protocol) module
//!
//! Implements MCP server functionality:
//! - Discovery endpoints
//! - Tool registry and execution
//! - SSE transport
//! - Session management

pub mod discovery;
pub mod handlers;
pub mod session;
pub mod sse;
pub mod tools;
