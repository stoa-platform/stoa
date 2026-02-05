//! Control Plane Module
//!
//! CAB-912: HTTP clients for the FastAPI control plane.

// TODO: Re-enable when mcp::protocol::ApiState and uac::Classification are wired
// pub mod client;
pub mod tool_proxy;

pub use tool_proxy::{OidcConfig, RemoteToolDef, RemoteToolSchema, ToolProxyClient};
