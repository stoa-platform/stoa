//! Metering Middleware
//!
//! Axum middleware layer for automatic request metering.
//! Captures timing, sizes, and errors for every request.

// Allow dead code: public API types for future consumption
#![allow(dead_code)]

use axum::{
    body::Body,
    extract::State,
    http::{Request, Response, StatusCode},
    middleware::Next,
};
use std::sync::Arc;
use std::time::Instant;
use tracing::{debug, warn};

use super::events::{EventStatus, HttpRequestEvent};
use super::producer::MeteringProducer;
use super::snapshots::{
    ErrorSnapshot, ErrorType, GatewayState, RequestContext, TimingBreakdown,
};
use crate::state::AppState;

/// Metering context passed through request extensions
#[derive(Debug, Clone)]
pub struct MeteringContext {
    /// Request start time
    pub start_time: Instant,

    /// Time after authentication
    pub after_auth: Option<Instant>,

    /// Time after policy evaluation
    pub after_policy: Option<Instant>,

    /// Time after routing decision
    pub after_routing: Option<Instant>,

    /// Time when backend call started
    pub backend_start: Option<Instant>,

    /// Time when backend call completed
    pub backend_end: Option<Instant>,

    /// Request ID for correlation
    pub request_id: String,

    /// Tenant ID (extracted from auth)
    pub tenant_id: Option<String>,

    /// User ID (extracted from auth)
    pub user_id: Option<String>,

    /// Session ID (for MCP requests)
    pub session_id: Option<String>,

    /// Tool name (for MCP tool calls)
    pub tool_name: Option<String>,

    /// Request body size
    pub request_size_bytes: u64,
}

impl MeteringContext {
    /// Create a new metering context
    pub fn new(request_id: String) -> Self {
        Self {
            start_time: Instant::now(),
            after_auth: None,
            after_policy: None,
            after_routing: None,
            backend_start: None,
            backend_end: None,
            request_id,
            tenant_id: None,
            user_id: None,
            session_id: None,
            tool_name: None,
            request_size_bytes: 0,
        }
    }

    /// Mark authentication complete
    #[allow(dead_code)]
    pub fn mark_auth_complete(&mut self) {
        self.after_auth = Some(Instant::now());
    }

    /// Mark policy evaluation complete
    #[allow(dead_code)]
    pub fn mark_policy_complete(&mut self) {
        self.after_policy = Some(Instant::now());
    }

    /// Mark routing complete
    #[allow(dead_code)]
    pub fn mark_routing_complete(&mut self) {
        self.after_routing = Some(Instant::now());
    }

    /// Mark backend call start
    #[allow(dead_code)]
    pub fn mark_backend_start(&mut self) {
        self.backend_start = Some(Instant::now());
    }

    /// Mark backend call complete
    #[allow(dead_code)]
    pub fn mark_backend_complete(&mut self) {
        self.backend_end = Some(Instant::now());
    }

    /// Calculate timing breakdown
    pub fn timing_breakdown(&self) -> TimingBreakdown {
        let now = Instant::now();
        let total = now.duration_since(self.start_time).as_millis() as u64;

        let t_auth = self
            .after_auth
            .map(|t| t.duration_since(self.start_time).as_millis() as u64)
            .unwrap_or(0);

        let t_policy = self
            .after_policy
            .map(|t| {
                t.duration_since(self.after_auth.unwrap_or(self.start_time))
                    .as_millis() as u64
            })
            .unwrap_or(0);

        let t_routing = self
            .after_routing
            .map(|t| {
                t.duration_since(self.after_policy.unwrap_or(self.start_time))
                    .as_millis() as u64
            })
            .unwrap_or(0);

        let t_backend = match (self.backend_start, self.backend_end) {
            (Some(start), Some(end)) => end.duration_since(start).as_millis() as u64,
            _ => 0,
        };

        TimingBreakdown {
            t_parse_ms: 0, // Minimal, included in auth
            t_auth_ms: t_auth,
            t_policy_ms: t_policy,
            t_routing_ms: t_routing,
            t_backend_ms: t_backend,
            t_response_ms: 0, // Calculated after response
            t_total_ms: total,
        }
    }

    /// Calculate gateway time (total - backend)
    #[allow(dead_code)]
    pub fn gateway_time_ms(&self) -> u64 {
        let timing = self.timing_breakdown();
        timing.t_total_ms.saturating_sub(timing.t_backend_ms)
    }
}

/// Metering middleware layer
///
/// Wraps requests to capture:
/// - Request/response sizes
/// - Timing breakdown
/// - Error snapshots on 4xx/5xx
///
/// Events are sent to Kafka asynchronously (fire-and-forget).
pub async fn metering_middleware(
    State(state): State<AppState>,
    mut request: Request<Body>,
    next: Next,
) -> Response<Body> {
    // Skip metering for health/metrics endpoints
    let path = request.uri().path();
    if path == "/health" || path == "/ready" || path == "/metrics" {
        return next.run(request).await;
    }

    // Get or create metering producer
    let producer = match state.metering_producer.as_ref() {
        Some(p) if p.is_enabled() => p.clone(),
        _ => {
            // Metering disabled, just run the request
            return next.run(request).await;
        }
    };

    // Initialize metering context
    let request_id = uuid::Uuid::new_v4().to_string();
    let mut ctx = MeteringContext::new(request_id.clone());

    // Extract request metadata
    let method = request.method().to_string();
    let uri_path = request.uri().path().to_string();
    let query = request.uri().query().map(|q| q.to_string());

    // Extract tenant from header (auth middleware will set it)
    ctx.tenant_id = request
        .headers()
        .get("X-Tenant-ID")
        .and_then(|v| v.to_str().ok())
        .map(|s| s.to_string());

    // Extract content-type and user-agent
    let content_type = request
        .headers()
        .get("content-type")
        .and_then(|v| v.to_str().ok())
        .map(|s| s.to_string());

    let user_agent = request
        .headers()
        .get("user-agent")
        .and_then(|v| v.to_str().ok())
        .map(|s| s.to_string());

    // Estimate request size from Content-Length header
    ctx.request_size_bytes = request
        .headers()
        .get("content-length")
        .and_then(|v| v.to_str().ok())
        .and_then(|s| s.parse().ok())
        .unwrap_or(0);

    // Store context in request extensions for downstream handlers
    request.extensions_mut().insert(ctx.clone());

    // Execute the request
    let response = next.run(request).await;

    // Calculate timing
    let total_ms = ctx.start_time.elapsed().as_millis() as u64;
    let timing = ctx.timing_breakdown();

    // Get response status
    let status = response.status();
    let status_code = status.as_u16();

    // Estimate response size from Content-Length header
    let response_size_bytes = response
        .headers()
        .get("content-length")
        .and_then(|v| v.to_str().ok())
        .and_then(|s| s.parse().ok())
        .unwrap_or(0);

    // Determine event status
    let event_status = if status.is_success() {
        EventStatus::Success
    } else if status == StatusCode::TOO_MANY_REQUESTS {
        EventStatus::RateLimited
    } else if status == StatusCode::FORBIDDEN {
        EventStatus::PolicyDenied
    } else if status.is_client_error() {
        EventStatus::Error
    } else if status.is_server_error() {
        EventStatus::BackendError
    } else {
        EventStatus::Error
    };

    // Send HTTP request event
    let http_event = create_http_event(
        &ctx,
        &method,
        &uri_path,
        status_code,
        event_status,
        ctx.request_size_bytes,
        response_size_bytes,
        timing.t_total_ms.saturating_sub(timing.t_backend_ms),
        timing.t_backend_ms,
    );
    producer.send_http_request(http_event);

    // Send error snapshot on 4xx/5xx
    if status.is_client_error() || status.is_server_error() {
        let request_ctx = RequestContext::builder()
            .method(&method)
            .path(&uri_path)
            .query(query)
            .content_type(content_type)
            .user_agent(user_agent)
            .request_size_bytes(ctx.request_size_bytes)
            .build();

        let gateway_state = get_gateway_state(&state);

        let snapshot = ErrorSnapshot::builder()
            .tenant_id(ctx.tenant_id.clone().unwrap_or_else(|| "unknown".to_string()))
            .user_id(ctx.user_id.clone())
            .request_id(&request_id)
            .session_id(ctx.session_id.clone())
            .http_status(status_code)
            .error_message(format!("HTTP {} response", status_code))
            .request(request_ctx)
            .timing(timing)
            .gateway_state(gateway_state)
            .tool_name(ctx.tool_name.clone())
            .build();

        debug!(
            request_id = %request_id,
            status = %status_code,
            "Publishing error snapshot"
        );

        producer.send_error_snapshot(snapshot);
    }

    debug!(
        request_id = %request_id,
        method = %method,
        path = %uri_path,
        status = %status_code,
        latency_ms = %total_ms,
        "Request metered"
    );

    response
}

/// Create an HTTP request event
#[allow(clippy::too_many_arguments)]
fn create_http_event(
    ctx: &MeteringContext,
    method: &str,
    path: &str,
    status: u16,
    event_status: EventStatus,
    request_size: u64,
    response_size: u64,
    t_gateway_ms: u64,
    t_backend_ms: u64,
) -> HttpRequestEvent {
    HttpRequestEvent {
        event_id: uuid::Uuid::new_v4(),
        timestamp: chrono::Utc::now(),
        tenant_id: ctx.tenant_id.clone().unwrap_or_else(|| "unknown".to_string()),
        user_id: ctx.user_id.clone(),
        request_id: ctx.request_id.clone(),
        method: method.to_string(),
        path: path.to_string(),
        upstream_url: None,
        latency_ms: t_gateway_ms + t_backend_ms,
        http_status: status,
        status: event_status,
        request_size_bytes: request_size,
        response_size_bytes: response_size,
        t_gateway_ms,
        t_backend_ms,
        error_message: None,
        trace_id: None,
        gateway_version: env!("CARGO_PKG_VERSION").to_string(),
    }
}

/// Get current gateway state for error snapshots
fn get_gateway_state(state: &AppState) -> GatewayState {
    GatewayState {
        active_sessions: state.session_manager.count(),
        active_connections: 0, // TODO: Track SSE connections
        rate_limit_buckets: 0, // TODO: Expose from rate limiter
        memory_mb: None,       // TODO: Track memory usage
        uptime_seconds: 0,     // TODO: Track uptime
    }
}

/// Extension trait for Request to access metering context
pub trait MeteringExt {
    /// Get the metering context (if present)
    fn metering_context(&self) -> Option<&MeteringContext>;

    /// Get a mutable reference to the metering context
    fn metering_context_mut(&mut self) -> Option<&mut MeteringContext>;
}

impl<B> MeteringExt for Request<B> {
    fn metering_context(&self) -> Option<&MeteringContext> {
        self.extensions().get::<MeteringContext>()
    }

    fn metering_context_mut(&mut self) -> Option<&mut MeteringContext> {
        self.extensions_mut().get_mut::<MeteringContext>()
    }
}

/// Record a tool call event
///
/// Called from MCP handlers to record tool invocations.
#[allow(clippy::too_many_arguments)]
pub fn record_tool_call(
    producer: &Arc<MeteringProducer>,
    tenant_id: &str,
    user_id: Option<&str>,
    user_email: Option<&str>,
    session_id: Option<&str>,
    request_id: &str,
    tool_name: &str,
    action: crate::uac::Action,
    latency_ms: u64,
    status: EventStatus,
    request_size_bytes: u64,
    response_size_bytes: u64,
    t_gateway_ms: u64,
    t_backend_ms: u64,
    error_message: Option<String>,
) {
    use super::events::ToolCallEvent;

    let event = ToolCallEvent::builder()
        .tenant_id(tenant_id)
        .user_id(user_id.map(|s| s.to_string()))
        .user_email(user_email.map(|s| s.to_string()))
        .session_id(session_id.map(|s| s.to_string()))
        .request_id(request_id)
        .tool_name(tool_name)
        .action(action)
        .latency_ms(latency_ms)
        .status(status)
        .request_size_bytes(request_size_bytes)
        .response_size_bytes(response_size_bytes)
        .t_gateway_ms(t_gateway_ms)
        .t_backend_ms(t_backend_ms)
        .error_message(error_message)
        .build();

    producer.send_tool_call(event);
}

/// Record an error snapshot for tool execution failures
#[allow(dead_code, clippy::too_many_arguments)]
pub fn record_tool_error(
    producer: &Arc<MeteringProducer>,
    tenant_id: &str,
    user_id: Option<&str>,
    request_id: &str,
    session_id: Option<&str>,
    tool_name: &str,
    error_message: &str,
    timing: TimingBreakdown,
    gateway_state: GatewayState,
) {
    let snapshot = ErrorSnapshot::builder()
        .tenant_id(tenant_id)
        .user_id(user_id.map(|s| s.to_string()))
        .request_id(request_id)
        .session_id(session_id.map(|s| s.to_string()))
        .error_type(ErrorType::ToolError)
        .http_status(500)
        .error_message(error_message)
        .tool_name(Some(tool_name.to_string()))
        .timing(timing)
        .gateway_state(gateway_state)
        .build();

    warn!(
        tool = %tool_name,
        request_id = %request_id,
        "Publishing tool error snapshot"
    );

    producer.send_error_snapshot(snapshot);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_metering_context_new() {
        let ctx = MeteringContext::new("req-123".to_string());
        assert_eq!(ctx.request_id, "req-123");
        assert!(ctx.tenant_id.is_none());
        assert!(ctx.user_id.is_none());
    }

    #[test]
    fn test_timing_breakdown() {
        let ctx = MeteringContext::new("req-123".to_string());
        let timing = ctx.timing_breakdown();
        assert!(timing.t_total_ms >= 0);
    }

    #[test]
    fn test_create_http_event() {
        let ctx = MeteringContext::new("req-123".to_string());
        let event = create_http_event(
            &ctx,
            "GET",
            "/health",
            200,
            EventStatus::Success,
            0,
            2,
            5,
            0,
        );

        assert_eq!(event.method, "GET");
        assert_eq!(event.path, "/health");
        assert_eq!(event.http_status, 200);
        assert_eq!(event.latency_ms, 5);
    }
}
