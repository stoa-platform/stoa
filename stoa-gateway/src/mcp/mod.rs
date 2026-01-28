// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
//! MCP (Model Context Protocol) Module
//!
//! CAB-912: Complete MCP Gateway implementation.
//!
//! This module provides:
//! - Protocol types for MCP requests/responses
//! - Tool registry with async trait
//! - HTTP handlers for /mcp/tools/* endpoints

pub mod handlers;
pub mod protocol;
pub mod tools;

pub use handlers::mcp_router;
pub use protocol::*;
pub use tools::registry::ToolRegistry;
