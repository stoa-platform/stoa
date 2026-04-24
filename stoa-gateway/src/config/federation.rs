//! Configuration for a single upstream MCP server in federation (CAB-1752).

use serde::{Deserialize, Serialize};

use super::redact::Redacted;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FederationUpstreamConfig {
    /// Upstream MCP server URL
    pub url: String,
    /// Transport type (default: "sse")
    pub transport: Option<String>,
    /// Optional auth token (never exposed in admin API, redacted in Debug).
    #[serde(default)]
    pub auth_token: Option<Redacted<String>>,
    /// Connection timeout in seconds (default: 30)
    pub timeout_secs: Option<u64>,
}
