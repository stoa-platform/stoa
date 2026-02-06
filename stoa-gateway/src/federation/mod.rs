//! MCP Server Federation Module (Phase 7: CAB-1105)
//!
//! Enables connecting to upstream MCP servers and exposing their tools.
//!
//! # Features
//!
//! - **Upstream Client**: Connect to any MCP server (SSE transport)
//! - **Tool Discovery**: Fetch tools from upstream via `tools/list`
//! - **Federated Tool**: Proxy tool calls to upstream MCP server
//! - **Tool Composition**: Combine multiple tools into compound tools
//!
//! # Tenant Isolation
//!
//! Federated tools respect tenant boundaries:
//! - ToolSet CRD namespace = tenant
//! - OPA policy checks apply before upstream calls
//! - Metering tracks federated calls

// Infrastructure prepared for K8s CRD watcher integration (Phase 7)
#![allow(dead_code)]
#![allow(unused_imports)]

pub mod composition;
pub mod upstream;

pub use composition::{ComposedTool, CompositionStep};
pub use upstream::{FederatedTool, UpstreamMcpClient, UpstreamMcpConfig};
