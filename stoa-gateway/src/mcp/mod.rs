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

pub use discovery::{mcp_capabilities, mcp_discovery, mcp_health};
pub use session::{Session, SessionManager};
pub use sse::{handle_sse_delete, handle_sse_get, handle_sse_post};
pub use tools::{Tool, ToolContext, ToolDefinition, ToolRegistry, ToolResult};
