//! OAuth 2.1 Discovery + Proxy
//!
//! CAB-1094: OAuth endpoints for Claude.ai MCP connector authentication.
//! CAB-1606: RFC 7592 — Dynamic Client Registration Management Protocol.
//!
//! Implements:
//! - RFC 9728: OAuth Protected Resource Metadata
//! - RFC 8414: OAuth Authorization Server Metadata
//! - RFC 7591: Dynamic Client Registration (DCR + public client patch)
//! - RFC 7592: Dynamic Client Registration Management (read/update/delete)
//! - OIDC Discovery (proxy + override)
//! - Token proxy (transparent forward to Keycloak)

pub mod discovery;
pub mod proxy;
