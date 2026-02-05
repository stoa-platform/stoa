//! Metering Events
//!
//! Event structures for metering tool calls and API requests.
//! Implements ADR-023 zero-blind-spot observability.

// Allow dead code: public API types for future consumption
#![allow(dead_code)]

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::uac::Action;

/// Event status for metering
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EventStatus {
    /// Request completed successfully
    Success,
    /// Request failed with an error
    Error,
    /// Request was rate limited
    RateLimited,
    /// Request was denied by policy
    PolicyDenied,
    /// Request timed out
    Timeout,
    /// Backend returned an error
    BackendError,
}

impl std::fmt::Display for EventStatus {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            EventStatus::Success => write!(f, "success"),
            EventStatus::Error => write!(f, "error"),
            EventStatus::RateLimited => write!(f, "rate_limited"),
            EventStatus::PolicyDenied => write!(f, "policy_denied"),
            EventStatus::Timeout => write!(f, "timeout"),
            EventStatus::BackendError => write!(f, "backend_error"),
        }
    }
}

/// Token usage information (for AI-related tools)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TokenUsage {
    /// Input tokens consumed
    pub input_tokens: u64,
    /// Output tokens generated
    pub output_tokens: u64,
    /// Total tokens (input + output)
    pub total_tokens: u64,
}

impl TokenUsage {
    /// Create new token usage
    pub fn new(input_tokens: u64, output_tokens: u64) -> Self {
        Self {
            input_tokens,
            output_tokens,
            total_tokens: input_tokens + output_tokens,
        }
    }
}

/// MCP Tool Call Event
///
/// Captures complete context for a tool invocation, including:
/// - Identity (tenant, user)
/// - Tool details (name, action)
/// - Timing breakdown (gateway vs backend)
/// - Size metrics (request/response bytes)
/// - Status and optional token usage
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolCallEvent {
    /// Unique event identifier
    pub event_id: Uuid,

    /// Event timestamp (UTC)
    pub timestamp: DateTime<Utc>,

    /// Tenant identifier
    pub tenant_id: String,

    /// User identifier (from JWT, if available)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub user_id: Option<String>,

    /// User email (from JWT, if available)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub user_email: Option<String>,

    /// MCP session ID
    #[serde(skip_serializing_if = "Option::is_none")]
    pub session_id: Option<String>,

    /// Request ID (for correlation)
    pub request_id: String,

    /// Tool name
    pub tool_name: String,

    /// Action performed
    pub action: Action,

    /// Total latency in milliseconds
    pub latency_ms: u64,

    /// Event status
    pub status: EventStatus,

    /// Token usage (for AI tools)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub token_usage: Option<TokenUsage>,

    /// Request body size in bytes
    pub request_size_bytes: u64,

    /// Response body size in bytes
    pub response_size_bytes: u64,

    /// Time spent in gateway logic (ms)
    /// ADR-023: T_gateway = auth + policy + routing
    pub t_gateway_ms: u64,

    /// Time spent waiting for backend (ms)
    /// ADR-023: T_backend = upstream API latency
    pub t_backend_ms: u64,

    /// HTTP status code (for proxy requests)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub http_status: Option<u16>,

    /// Error message (if status is error)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error_message: Option<String>,

    /// OTel trace ID for correlation
    #[serde(skip_serializing_if = "Option::is_none")]
    pub trace_id: Option<String>,

    /// Gateway version
    pub gateway_version: String,
}

impl ToolCallEvent {
    /// Create a new tool call event builder
    pub fn builder() -> ToolCallEventBuilder {
        ToolCallEventBuilder::default()
    }

    /// Get Kafka partition key (tenant_id for locality)
    pub fn partition_key(&self) -> &str {
        &self.tenant_id
    }
}

/// Builder for ToolCallEvent
#[derive(Debug, Default)]
pub struct ToolCallEventBuilder {
    tenant_id: Option<String>,
    user_id: Option<String>,
    user_email: Option<String>,
    session_id: Option<String>,
    request_id: Option<String>,
    tool_name: Option<String>,
    action: Option<Action>,
    latency_ms: u64,
    status: Option<EventStatus>,
    token_usage: Option<TokenUsage>,
    request_size_bytes: u64,
    response_size_bytes: u64,
    t_gateway_ms: u64,
    t_backend_ms: u64,
    http_status: Option<u16>,
    error_message: Option<String>,
    trace_id: Option<String>,
}

impl ToolCallEventBuilder {
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

    /// Set user email
    pub fn user_email(mut self, user_email: Option<String>) -> Self {
        self.user_email = user_email;
        self
    }

    /// Set session ID
    pub fn session_id(mut self, session_id: Option<String>) -> Self {
        self.session_id = session_id;
        self
    }

    /// Set request ID
    pub fn request_id(mut self, request_id: impl Into<String>) -> Self {
        self.request_id = Some(request_id.into());
        self
    }

    /// Set tool name
    pub fn tool_name(mut self, tool_name: impl Into<String>) -> Self {
        self.tool_name = Some(tool_name.into());
        self
    }

    /// Set action
    pub fn action(mut self, action: Action) -> Self {
        self.action = Some(action);
        self
    }

    /// Set latency in milliseconds
    pub fn latency_ms(mut self, latency_ms: u64) -> Self {
        self.latency_ms = latency_ms;
        self
    }

    /// Set status
    pub fn status(mut self, status: EventStatus) -> Self {
        self.status = Some(status);
        self
    }

    /// Set token usage
    pub fn token_usage(mut self, token_usage: Option<TokenUsage>) -> Self {
        self.token_usage = token_usage;
        self
    }

    /// Set request size in bytes
    pub fn request_size_bytes(mut self, bytes: u64) -> Self {
        self.request_size_bytes = bytes;
        self
    }

    /// Set response size in bytes
    pub fn response_size_bytes(mut self, bytes: u64) -> Self {
        self.response_size_bytes = bytes;
        self
    }

    /// Set gateway timing in milliseconds
    pub fn t_gateway_ms(mut self, ms: u64) -> Self {
        self.t_gateway_ms = ms;
        self
    }

    /// Set backend timing in milliseconds
    pub fn t_backend_ms(mut self, ms: u64) -> Self {
        self.t_backend_ms = ms;
        self
    }

    /// Set HTTP status code
    pub fn http_status(mut self, status: Option<u16>) -> Self {
        self.http_status = status;
        self
    }

    /// Set error message
    pub fn error_message(mut self, message: Option<String>) -> Self {
        self.error_message = message;
        self
    }

    /// Set trace ID
    pub fn trace_id(mut self, trace_id: Option<String>) -> Self {
        self.trace_id = trace_id;
        self
    }

    /// Build the event
    pub fn build(self) -> ToolCallEvent {
        ToolCallEvent {
            event_id: Uuid::new_v4(),
            timestamp: Utc::now(),
            tenant_id: self.tenant_id.unwrap_or_else(|| "unknown".to_string()),
            user_id: self.user_id,
            user_email: self.user_email,
            session_id: self.session_id,
            request_id: self.request_id.unwrap_or_else(|| Uuid::new_v4().to_string()),
            tool_name: self.tool_name.unwrap_or_else(|| "unknown".to_string()),
            action: self.action.unwrap_or(Action::Read),
            latency_ms: self.latency_ms,
            status: self.status.unwrap_or(EventStatus::Success),
            token_usage: self.token_usage,
            request_size_bytes: self.request_size_bytes,
            response_size_bytes: self.response_size_bytes,
            t_gateway_ms: self.t_gateway_ms,
            t_backend_ms: self.t_backend_ms,
            http_status: self.http_status,
            error_message: self.error_message,
            trace_id: self.trace_id,
            gateway_version: env!("CARGO_PKG_VERSION").to_string(),
        }
    }
}

/// HTTP Request Event (for proxy mode metering)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HttpRequestEvent {
    /// Unique event identifier
    pub event_id: Uuid,

    /// Event timestamp (UTC)
    pub timestamp: DateTime<Utc>,

    /// Tenant identifier
    pub tenant_id: String,

    /// User identifier (from JWT, if available)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub user_id: Option<String>,

    /// Request ID (for correlation)
    pub request_id: String,

    /// HTTP method
    pub method: String,

    /// Request path
    pub path: String,

    /// Upstream URL
    #[serde(skip_serializing_if = "Option::is_none")]
    pub upstream_url: Option<String>,

    /// Total latency in milliseconds
    pub latency_ms: u64,

    /// HTTP status code
    pub http_status: u16,

    /// Event status
    pub status: EventStatus,

    /// Request body size in bytes
    pub request_size_bytes: u64,

    /// Response body size in bytes
    pub response_size_bytes: u64,

    /// Time spent in gateway logic (ms)
    pub t_gateway_ms: u64,

    /// Time spent waiting for backend (ms)
    pub t_backend_ms: u64,

    /// Error message (if any)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error_message: Option<String>,

    /// OTel trace ID for correlation
    #[serde(skip_serializing_if = "Option::is_none")]
    pub trace_id: Option<String>,

    /// Gateway version
    pub gateway_version: String,
}

impl HttpRequestEvent {
    /// Get Kafka partition key (tenant_id for locality)
    pub fn partition_key(&self) -> &str {
        &self.tenant_id
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_event_status_display() {
        assert_eq!(EventStatus::Success.to_string(), "success");
        assert_eq!(EventStatus::RateLimited.to_string(), "rate_limited");
        assert_eq!(EventStatus::PolicyDenied.to_string(), "policy_denied");
    }

    #[test]
    fn test_token_usage() {
        let usage = TokenUsage::new(100, 200);
        assert_eq!(usage.input_tokens, 100);
        assert_eq!(usage.output_tokens, 200);
        assert_eq!(usage.total_tokens, 300);
    }

    #[test]
    fn test_tool_call_event_builder() {
        let event = ToolCallEvent::builder()
            .tenant_id("tenant-1")
            .user_id(Some("user-123".to_string()))
            .tool_name("stoa_catalog")
            .action(Action::List)
            .latency_ms(150)
            .status(EventStatus::Success)
            .request_size_bytes(256)
            .response_size_bytes(1024)
            .t_gateway_ms(10)
            .t_backend_ms(140)
            .build();

        assert_eq!(event.tenant_id, "tenant-1");
        assert_eq!(event.user_id, Some("user-123".to_string()));
        assert_eq!(event.tool_name, "stoa_catalog");
        assert_eq!(event.latency_ms, 150);
        assert_eq!(event.status, EventStatus::Success);
        assert_eq!(event.t_gateway_ms, 10);
        assert_eq!(event.t_backend_ms, 140);
    }

    #[test]
    fn test_tool_call_event_serialization() {
        let event = ToolCallEvent::builder()
            .tenant_id("tenant-1")
            .tool_name("stoa_catalog")
            .action(Action::List)
            .status(EventStatus::Success)
            .build();

        let json = serde_json::to_string(&event).expect("Failed to serialize");
        assert!(json.contains("tenant-1"));
        assert!(json.contains("stoa_catalog"));
        assert!(json.contains("success"));

        // Should not contain None fields
        assert!(!json.contains("user_id"));
    }

    #[test]
    fn test_partition_key() {
        let event = ToolCallEvent::builder()
            .tenant_id("acme-corp")
            .tool_name("test")
            .action(Action::Read)
            .status(EventStatus::Success)
            .build();

        assert_eq!(event.partition_key(), "acme-corp");
    }
}
