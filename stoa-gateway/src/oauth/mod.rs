//! OAuth 2.1 Discovery + Proxy
//!
//! CAB-1094: OAuth endpoints for Claude.ai MCP connector authentication.
//!
//! Implements:
//! - RFC 9728: OAuth Protected Resource Metadata
//! - RFC 8414: OAuth Authorization Server Metadata
//! - OIDC Discovery (proxy + override)
//! - Token proxy (transparent forward to Keycloak)
//! - DCR proxy (Dynamic Client Registration + public client patch)

pub mod discovery;
pub mod proxy;
