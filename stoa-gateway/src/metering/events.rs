//! Metering Events (ADR-023: Zero-Blind-Spot)
//!
//! Every tool call generates a `ToolCallEvent`.
//! Every error (4xx/5xx) generates an `ErrorSnapshot` (enriched event).

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

/// Status of a tool call event
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum EventStatus {
    /// Successful tool execution
    Success,
    /// Tool execution failed
    Error,
    /// Request was rate limited
    RateLimited,
    /// Access denied by policy
    PolicyDenied,
    /// Tool not found
    NotFound,
}

impl std::fmt::Display for EventStatus {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            EventStatus::Success => write!(f, "success"),
            EventStatus::Error => write!(f, "error"),
            EventStatus::RateLimited => write!(f, "rate_limited"),
            EventStatus::PolicyDenied => write!(f, "policy_denied"),
            EventStatus::NotFound => write!(f, "not_found"),
        }
    }
}

/// Tool call metering event
///
/// Published to `stoa.metering` topic for every tool invocation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolCallEvent {
    /// Unique event identifier
    pub event_id: Uuid,

    /// Event timestamp (UTC)
    pub timestamp: DateTime<Utc>,

    /// Tenant identifier
    pub tenant_id: String,

    /// User identifier (if authenticated)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub user_id: Option<String>,

    /// User email (if available)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub user_email: Option<String>,

    /// Tool name
    pub tool_name: String,

    /// Action performed (Read, Create, Delete, etc.)
    pub action: String,

    /// Total latency in milliseconds
    pub latency_ms: u64,

    /// Event status
    pub status: EventStatus,

    /// Request payload size in bytes
    pub request_size_bytes: u64,

    /// Response payload size in bytes
    pub response_size_bytes: u64,

    // === Zero-Blind-Spot Timing (ADR-023) ===
    /// Time spent in gateway logic (ms)
    pub t_gateway_ms: u64,

    /// Time waiting for backend (Control Plane API) (ms)
    pub t_backend_ms: u64,

    /// OAuth scopes present in the request
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub scopes: Vec<String>,

    /// User roles
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub roles: Vec<String>,

    /// Gateway instance identifier
    #[serde(skip_serializing_if = "Option::is_none")]
    pub gateway_id: Option<String>,
}

impl ToolCallEvent {
    /// Create a new tool call event
    pub fn new(tenant_id: String, tool_name: String, action: String) -> Self {
        Self {
            event_id: Uuid::new_v4(),
            timestamp: Utc::now(),
            tenant_id,
            user_id: None,
            user_email: None,
            tool_name,
            action,
            latency_ms: 0,
            status: EventStatus::Success,
            request_size_bytes: 0,
            response_size_bytes: 0,
            t_gateway_ms: 0,
            t_backend_ms: 0,
            scopes: vec![],
            roles: vec![],
            gateway_id: None,
        }
    }

    /// Set user context
    pub fn with_user(mut self, user_id: Option<String>, user_email: Option<String>) -> Self {
        self.user_id = user_id;
        self.user_email = user_email;
        self
    }

    /// Set timing information
    pub fn with_timing(mut self, latency_ms: u64, t_gateway_ms: u64, t_backend_ms: u64) -> Self {
        self.latency_ms = latency_ms;
        self.t_gateway_ms = t_gateway_ms;
        self.t_backend_ms = t_backend_ms;
        self
    }

    /// Set status
    pub fn with_status(mut self, status: EventStatus) -> Self {
        self.status = status;
        self
    }

    /// Set payload sizes
    pub fn with_sizes(mut self, request_bytes: u64, response_bytes: u64) -> Self {
        self.request_size_bytes = request_bytes;
        self.response_size_bytes = response_bytes;
        self
    }

    /// Set scopes and roles
    pub fn with_auth(mut self, scopes: Vec<String>, roles: Vec<String>) -> Self {
        self.scopes = scopes;
        self.roles = roles;
        self
    }
}

/// Gateway state snapshot for error context
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct GatewaySnapshot {
    /// Number of active MCP sessions
    pub active_sessions: u64,

    /// Gateway uptime in seconds
    pub uptime_secs: u64,

    /// Current rate limiter bucket count
    pub rate_limit_buckets: u64,

    /// Memory usage estimate (RSS in bytes, if available)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub memory_rss_bytes: Option<u64>,
}

/// Error snapshot for debugging and audit
///
/// Published to `stoa.errors` topic on every 4xx/5xx response.
/// Extends ToolCallEvent with error-specific context.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ErrorSnapshot {
    /// Base metering event (contains all standard fields)
    #[serde(flatten)]
    pub base_event: ToolCallEvent,

    /// Error type classification
    pub error_type: String,

    /// Human-readable error message (sanitized — no secrets)
    pub error_message: String,

    /// HTTP request path
    pub request_path: String,

    /// HTTP request method
    pub request_method: String,

    /// HTTP response status code
    pub response_status: u16,

    /// Gateway state at time of error
    pub gateway_state: GatewaySnapshot,

    /// Stack trace (if available, production: disabled)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub stack_trace: Option<String>,
}

impl ErrorSnapshot {
    /// Create an error snapshot from a tool call event
    pub fn from_event(
        event: ToolCallEvent,
        error_type: String,
        error_message: String,
        response_status: u16,
    ) -> Self {
        Self {
            base_event: event,
            error_type,
            error_message,
            request_path: String::new(),
            request_method: String::new(),
            response_status,
            gateway_state: GatewaySnapshot::default(),
            stack_trace: None,
        }
    }

    /// Set request context
    pub fn with_request(mut self, path: String, method: String) -> Self {
        self.request_path = path;
        self.request_method = method;
        self
    }

    /// Set gateway state
    pub fn with_gateway_state(mut self, state: GatewaySnapshot) -> Self {
        self.gateway_state = state;
        self
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tool_call_event_serialization() {
        let event = ToolCallEvent::new(
            "tenant-acme".to_string(),
            "stoa_catalog".to_string(),
            "Read".to_string(),
        )
        .with_user(
            Some("user-123".to_string()),
            Some("user@example.com".to_string()),
        )
        .with_timing(150, 10, 140)
        .with_status(EventStatus::Success)
        .with_sizes(256, 1024);

        let json = serde_json::to_string_pretty(&event).unwrap();
        assert!(json.contains("tenant-acme"));
        assert!(json.contains("stoa_catalog"));
        assert!(json.contains("user-123"));
        assert!(json.contains("150")); // latency_ms
    }

    #[test]
    fn test_error_snapshot_serialization() {
        let event = ToolCallEvent::new(
            "tenant-acme".to_string(),
            "stoa_subscription".to_string(),
            "Create".to_string(),
        )
        .with_status(EventStatus::PolicyDenied);

        let snapshot = ErrorSnapshot::from_event(
            event,
            "PolicyDenied".to_string(),
            "scope 'stoa:write' required".to_string(),
            403,
        )
        .with_request("/mcp/tools/call".to_string(), "POST".to_string())
        .with_gateway_state(GatewaySnapshot {
            active_sessions: 42,
            uptime_secs: 3600,
            rate_limit_buckets: 10,
            memory_rss_bytes: None,
        });

        let json = serde_json::to_string_pretty(&snapshot).unwrap();
        assert!(json.contains("PolicyDenied"));
        assert!(json.contains("403"));
        assert!(json.contains("42")); // active_sessions
    }

    #[test]
    fn test_event_status_display() {
        assert_eq!(EventStatus::Success.to_string(), "success");
        assert_eq!(EventStatus::PolicyDenied.to_string(), "policy_denied");
        assert_eq!(EventStatus::RateLimited.to_string(), "rate_limited");
    }

    #[test]
    fn test_timing_breakdown() {
        let event =
            ToolCallEvent::new("tenant".to_string(), "tool".to_string(), "Read".to_string())
                .with_timing(200, 50, 150);

        // t_gateway + t_backend should approximately equal latency
        // (allowing for measurement overhead)
        assert!(event.t_gateway_ms + event.t_backend_ms <= event.latency_ms + 10);
    }
}
