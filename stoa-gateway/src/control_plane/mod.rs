//! Control Plane Module
//!
//! CAB-912: HTTP clients for the FastAPI control plane.

pub mod client;
pub mod registration;
pub mod tool_permissions;
pub mod tool_proxy;

pub use registration::GatewayRegistrar;
pub use tool_permissions::ToolPermissionService;
pub use tool_proxy::{GeneratedToolDef, OidcConfig, RemoteToolDef, ToolProxyClient};
