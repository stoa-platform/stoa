//! Error Snapshots
//!
//! Captures rich error context on 4xx/5xx responses for debugging.
//! Implements ADR-023 zero-blind-spot observability.

// Allow dead code: public API types for future consumption
#![allow(dead_code)]

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use uuid::Uuid;

/// Error type classification
#[allow(clippy::enum_variant_names)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ErrorType {
    /// Client error (4xx)
    ClientError,
    /// Server error (5xx)
    ServerError,
    /// Authentication failure (401)
    AuthError,
    /// Authorization failure (403)
    AuthzError,
    /// Rate limit exceeded (429)
    RateLimitError,
    /// Request timeout
    TimeoutError,
    /// Backend connection failure
    ConnectionError,
    /// Policy evaluation failure
    PolicyError,
    /// Tool execution failure
    ToolError,
    /// Internal gateway error
    InternalError,
}

impl ErrorType {
    /// Classify error type from HTTP status code
    pub fn from_status(status: u16) -> Self {
        match status {
            401 => ErrorType::AuthError,
            403 => ErrorType::AuthzError,
            429 => ErrorType::RateLimitError,
            408 | 504 => ErrorType::TimeoutError,
            502 | 503 => ErrorType::ConnectionError,
            400..=499 => ErrorType::ClientError,
            500..=599 => ErrorType::ServerError,
            _ => ErrorType::InternalError,
        }
    }
}

impl std::fmt::Display for ErrorType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ErrorType::ClientError => write!(f, "client_error"),
            ErrorType::ServerError => write!(f, "server_error"),
            ErrorType::AuthError => write!(f, "auth_error"),
            ErrorType::AuthzError => write!(f, "authz_error"),
            ErrorType::RateLimitError => write!(f, "rate_limit_error"),
            ErrorType::TimeoutError => write!(f, "timeout_error"),
            ErrorType::ConnectionError => write!(f, "connection_error"),
            ErrorType::PolicyError => write!(f, "policy_error"),
            ErrorType::ToolError => write!(f, "tool_error"),
            ErrorType::InternalError => write!(f, "internal_error"),
        }
    }
}

/// Gateway state at time of error
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct GatewayState {
    /// Number of active sessions
    pub active_sessions: usize,

    /// Number of active SSE connections
    pub active_connections: usize,

    /// Rate limiter bucket count
    pub rate_limit_buckets: usize,

    /// Approximate memory usage (MB)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub memory_mb: Option<u64>,

    /// Gateway uptime in seconds
    pub uptime_seconds: u64,
}

/// Timing breakdown for error analysis
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct TimingBreakdown {
    /// Time to parse request (ms)
    pub t_parse_ms: u64,

    /// Time for authentication (ms)
    pub t_auth_ms: u64,

    /// Time for policy evaluation (ms)
    pub t_policy_ms: u64,

    /// Time for routing decision (ms)
    pub t_routing_ms: u64,

    /// Time waiting for backend (ms)
    pub t_backend_ms: u64,

    /// Time to serialize response (ms)
    pub t_response_ms: u64,

    /// Total time (ms)
    pub t_total_ms: u64,
}

/// Request context (sanitized - no secrets)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RequestContext {
    /// HTTP method
    pub method: String,

    /// Request path
    pub path: String,

    /// Query parameters (sanitized)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub query: Option<String>,

    /// Content-Type header
    #[serde(skip_serializing_if = "Option::is_none")]
    pub content_type: Option<String>,

    /// User-Agent header
    #[serde(skip_serializing_if = "Option::is_none")]
    pub user_agent: Option<String>,

    /// Request body size in bytes
    pub request_size_bytes: u64,

    /// Selected headers (no auth headers)
    #[serde(skip_serializing_if = "HashMap::is_empty")]
    pub headers: HashMap<String, String>,
}

impl Default for RequestContext {
    fn default() -> Self {
        Self {
            method: "GET".to_string(),
            path: "/".to_string(),
            query: None,
            content_type: None,
            user_agent: None,
            request_size_bytes: 0,
            headers: HashMap::new(),
        }
    }
}

impl RequestContext {
    /// Create a new request context builder
    pub fn builder() -> RequestContextBuilder {
        RequestContextBuilder::default()
    }
}

/// Builder for RequestContext
#[derive(Debug, Default)]
pub struct RequestContextBuilder {
    method: String,
    path: String,
    query: Option<String>,
    content_type: Option<String>,
    user_agent: Option<String>,
    request_size_bytes: u64,
    headers: HashMap<String, String>,
}

impl RequestContextBuilder {
    /// Set HTTP method
    pub fn method(mut self, method: impl Into<String>) -> Self {
        self.method = method.into();
        self
    }

    /// Set request path
    pub fn path(mut self, path: impl Into<String>) -> Self {
        self.path = path.into();
        self
    }

    /// Set query string
    pub fn query(mut self, query: Option<String>) -> Self {
        self.query = query;
        self
    }

    /// Set Content-Type header
    pub fn content_type(mut self, content_type: Option<String>) -> Self {
        self.content_type = content_type;
        self
    }

    /// Set User-Agent header
    pub fn user_agent(mut self, user_agent: Option<String>) -> Self {
        self.user_agent = user_agent;
        self
    }

    /// Set request size
    pub fn request_size_bytes(mut self, size: u64) -> Self {
        self.request_size_bytes = size;
        self
    }

    /// Add a header (will be sanitized)
    pub fn header(mut self, key: impl Into<String>, value: impl Into<String>) -> Self {
        let key = key.into().to_lowercase();
        // Skip sensitive headers
        if !is_sensitive_header(&key) {
            self.headers.insert(key, value.into());
        }
        self
    }

    /// Build the request context
    pub fn build(self) -> RequestContext {
        RequestContext {
            method: self.method,
            path: self.path,
            query: self.query,
            content_type: self.content_type,
            user_agent: self.user_agent,
            request_size_bytes: self.request_size_bytes,
            headers: self.headers,
        }
    }
}

/// Check if a header is sensitive and should be excluded
fn is_sensitive_header(key: &str) -> bool {
    matches!(
        key,
        "authorization"
            | "cookie"
            | "x-api-key"
            | "x-auth-token"
            | "x-csrf-token"
            | "proxy-authorization"
            | "set-cookie"
    )
}

/// Error chain entry
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ErrorChainEntry {
    /// Error type name
    pub error_type: String,

    /// Error message
    pub message: String,

    /// Source file (if available)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub file: Option<String>,

    /// Source line (if available)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub line: Option<u32>,
}

/// Error snapshot for debugging
///
/// Captures complete error context on 4xx/5xx responses:
/// - Error classification and chain
/// - Request context (sanitized)
/// - Timing breakdown
/// - Gateway state
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ErrorSnapshot {
    /// Unique snapshot identifier
    pub snapshot_id: Uuid,

    /// Snapshot timestamp (UTC)
    pub timestamp: DateTime<Utc>,

    /// Tenant identifier
    pub tenant_id: String,

    /// User identifier (if authenticated)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub user_id: Option<String>,

    /// Request ID (for correlation)
    pub request_id: String,

    /// Session ID (if MCP session)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub session_id: Option<String>,

    /// Error type classification
    pub error_type: ErrorType,

    /// HTTP status code
    pub http_status: u16,

    /// Primary error message
    pub error_message: String,

    /// Error chain (for nested errors)
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub error_chain: Vec<ErrorChainEntry>,

    /// Request context (sanitized)
    pub request: RequestContext,

    /// Timing breakdown
    pub timing: TimingBreakdown,

    /// Gateway state at time of error
    pub gateway_state: GatewayState,

    /// Tool name (if MCP tool error)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tool_name: Option<String>,

    /// OTel trace ID for correlation
    #[serde(skip_serializing_if = "Option::is_none")]
    pub trace_id: Option<String>,

    /// Gateway version
    pub gateway_version: String,

    /// Environment (dev, staging, prod)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub environment: Option<String>,
}

impl ErrorSnapshot {
    /// Create a new error snapshot builder
    pub fn builder() -> ErrorSnapshotBuilder {
        ErrorSnapshotBuilder::default()
    }

    /// Get Kafka partition key (tenant_id for locality)
    pub fn partition_key(&self) -> &str {
        &self.tenant_id
    }
}

/// Builder for ErrorSnapshot
#[derive(Debug, Default)]
pub struct ErrorSnapshotBuilder {
    tenant_id: Option<String>,
    user_id: Option<String>,
    request_id: Option<String>,
    session_id: Option<String>,
    error_type: Option<ErrorType>,
    http_status: u16,
    error_message: Option<String>,
    error_chain: Vec<ErrorChainEntry>,
    request: Option<RequestContext>,
    timing: Option<TimingBreakdown>,
    gateway_state: Option<GatewayState>,
    tool_name: Option<String>,
    trace_id: Option<String>,
    environment: Option<String>,
}

impl ErrorSnapshotBuilder {
    /// Set tenant ID
    pub fn tenant_id(mut self, tenant_id: impl Into<String>) -> Self {
        self.tenant_id = Some(tenant_id.into());
        self
    }

    /// Set user ID
    pub fn user_id(mut self, user_id: Option<String>) -> Self {
        self.user_id = user_id;
        self
    }

    /// Set request ID
    pub fn request_id(mut self, request_id: impl Into<String>) -> Self {
        self.request_id = Some(request_id.into());
        self
    }

    /// Set session ID
    pub fn session_id(mut self, session_id: Option<String>) -> Self {
        self.session_id = session_id;
        self
    }

    /// Set error type
    pub fn error_type(mut self, error_type: ErrorType) -> Self {
        self.error_type = Some(error_type);
        self
    }

    /// Set HTTP status code
    pub fn http_status(mut self, status: u16) -> Self {
        self.http_status = status;
        // Auto-classify error type if not set
        if self.error_type.is_none() {
            self.error_type = Some(ErrorType::from_status(status));
        }
        self
    }

    /// Set error message
    pub fn error_message(mut self, message: impl Into<String>) -> Self {
        self.error_message = Some(message.into());
        self
    }

    /// Add an error chain entry
    pub fn add_error_chain(mut self, entry: ErrorChainEntry) -> Self {
        self.error_chain.push(entry);
        self
    }

    /// Set request context
    pub fn request(mut self, request: RequestContext) -> Self {
        self.request = Some(request);
        self
    }

    /// Set timing breakdown
    pub fn timing(mut self, timing: TimingBreakdown) -> Self {
        self.timing = Some(timing);
        self
    }

    /// Set gateway state
    pub fn gateway_state(mut self, state: GatewayState) -> Self {
        self.gateway_state = Some(state);
        self
    }

    /// Set tool name
    pub fn tool_name(mut self, name: Option<String>) -> Self {
        self.tool_name = name;
        self
    }

    /// Set trace ID
    pub fn trace_id(mut self, trace_id: Option<String>) -> Self {
        self.trace_id = trace_id;
        self
    }

    /// Set environment
    pub fn environment(mut self, env: Option<String>) -> Self {
        self.environment = env;
        self
    }

    /// Build the error snapshot
    pub fn build(self) -> ErrorSnapshot {
        ErrorSnapshot {
            snapshot_id: Uuid::new_v4(),
            timestamp: Utc::now(),
            tenant_id: self.tenant_id.unwrap_or_else(|| "unknown".to_string()),
            user_id: self.user_id,
            request_id: self.request_id.unwrap_or_else(|| Uuid::new_v4().to_string()),
            session_id: self.session_id,
            error_type: self
                .error_type
                .unwrap_or(ErrorType::from_status(self.http_status)),
            http_status: self.http_status,
            error_message: self.error_message.unwrap_or_else(|| "Unknown error".to_string()),
            error_chain: self.error_chain,
            request: self.request.unwrap_or_default(),
            timing: self.timing.unwrap_or_default(),
            gateway_state: self.gateway_state.unwrap_or_default(),
            tool_name: self.tool_name,
            trace_id: self.trace_id,
            gateway_version: env!("CARGO_PKG_VERSION").to_string(),
            environment: self.environment,
        }
    }
}

/// Helper to create an error chain entry from an error
#[allow(dead_code)]
pub fn error_to_chain_entry(error: &dyn std::error::Error) -> ErrorChainEntry {
    ErrorChainEntry {
        error_type: std::any::type_name_of_val(error).to_string(),
        message: error.to_string(),
        file: None,
        line: None,
    }
}

/// Build error chain from a std::error::Error
#[allow(dead_code)]
pub fn build_error_chain(error: &dyn std::error::Error) -> Vec<ErrorChainEntry> {
    let mut chain = Vec::new();
    let mut current: Option<&dyn std::error::Error> = Some(error);

    while let Some(err) = current {
        chain.push(error_to_chain_entry(err));
        current = err.source();
    }

    chain
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_error_type_from_status() {
        assert_eq!(ErrorType::from_status(401), ErrorType::AuthError);
        assert_eq!(ErrorType::from_status(403), ErrorType::AuthzError);
        assert_eq!(ErrorType::from_status(429), ErrorType::RateLimitError);
        assert_eq!(ErrorType::from_status(404), ErrorType::ClientError);
        assert_eq!(ErrorType::from_status(500), ErrorType::ServerError);
        assert_eq!(ErrorType::from_status(502), ErrorType::ConnectionError);
        assert_eq!(ErrorType::from_status(504), ErrorType::TimeoutError);
    }

    #[test]
    fn test_error_type_display() {
        assert_eq!(ErrorType::AuthError.to_string(), "auth_error");
        assert_eq!(ErrorType::RateLimitError.to_string(), "rate_limit_error");
    }

    #[test]
    fn test_sensitive_header_detection() {
        assert!(is_sensitive_header("authorization"));
        assert!(is_sensitive_header("cookie"));
        assert!(is_sensitive_header("x-api-key"));
        assert!(!is_sensitive_header("content-type"));
        assert!(!is_sensitive_header("user-agent"));
    }

    #[test]
    fn test_request_context_builder() {
        let ctx = RequestContext::builder()
            .method("POST")
            .path("/mcp/sse")
            .content_type(Some("application/json".to_string()))
            .header("X-Request-ID", "abc123")
            .header("Authorization", "Bearer secret") // Should be excluded
            .build();

        assert_eq!(ctx.method, "POST");
        assert_eq!(ctx.path, "/mcp/sse");
        assert!(ctx.headers.contains_key("x-request-id"));
        assert!(!ctx.headers.contains_key("authorization")); // Sensitive, excluded
    }

    #[test]
    fn test_error_snapshot_builder() {
        let request = RequestContext::builder()
            .method("POST")
            .path("/mcp/tools/call")
            .build();

        let snapshot = ErrorSnapshot::builder()
            .tenant_id("tenant-1")
            .request_id("req-123")
            .http_status(403)
            .error_message("Policy denied: missing stoa:write scope")
            .request(request)
            .tool_name(Some("stoa_create_api".to_string()))
            .build();

        assert_eq!(snapshot.tenant_id, "tenant-1");
        assert_eq!(snapshot.http_status, 403);
        assert_eq!(snapshot.error_type, ErrorType::AuthzError);
        assert_eq!(snapshot.tool_name, Some("stoa_create_api".to_string()));
    }

    #[test]
    fn test_error_snapshot_serialization() {
        let snapshot = ErrorSnapshot::builder()
            .tenant_id("tenant-1")
            .http_status(500)
            .error_message("Internal server error")
            .build();

        let json = serde_json::to_string(&snapshot).expect("Failed to serialize");
        assert!(json.contains("tenant-1"));
        assert!(json.contains("500"));
        assert!(json.contains("Internal server error"));
    }

    #[test]
    fn test_partition_key() {
        let snapshot = ErrorSnapshot::builder()
            .tenant_id("acme-corp")
            .http_status(500)
            .error_message("Error")
            .build();

        assert_eq!(snapshot.partition_key(), "acme-corp");
    }
}
