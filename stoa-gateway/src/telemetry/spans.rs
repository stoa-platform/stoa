//! Tool Span Helpers
//!
//! Provides instrumentation for tool execution with optional OTel integration.
//! Falls back to tracing spans when OTel is not available.
//!
//! Note: Infrastructure prepared for SSE handler integration (Phase 7).

// Span infrastructure prepared for future integration
#![allow(dead_code)]

use std::time::Instant;
use tracing::{debug, span, Level, Span};

/// A span for tracking tool execution
///
/// When OTel is active, creates an OTel span with proper attributes.
/// Otherwise, uses a tracing span for local observability.
pub struct ToolSpan {
    tool_name: String,
    tenant_id: String,
    start: Instant,
    _tracing_span: Span,
    finished: bool,
}

impl ToolSpan {
    /// Create a new tool span
    pub fn new(tool_name: &str, tenant_id: &str) -> Self {
        let tracing_span = span!(
            Level::INFO,
            "tool_call",
            tool = %tool_name,
            tenant = %tenant_id,
            otel.kind = "server"
        );

        debug!(
            tool = %tool_name,
            tenant = %tenant_id,
            "Tool execution started"
        );

        Self {
            tool_name: tool_name.to_string(),
            tenant_id: tenant_id.to_string(),
            start: Instant::now(),
            _tracing_span: tracing_span,
            finished: false,
        }
    }

    /// Get elapsed duration in seconds
    pub fn elapsed_secs(&self) -> f64 {
        self.start.elapsed().as_secs_f64()
    }

    /// Mark span as successful
    pub fn finish_success(mut self) {
        self.finished = true;
        let duration = self.elapsed_secs();
        debug!(
            tool = %self.tool_name,
            tenant = %self.tenant_id,
            duration_ms = %(duration * 1000.0),
            status = "success",
            "Tool execution completed"
        );

        // Record metrics
        crate::metrics::record_tool_call(&self.tool_name, &self.tenant_id, "success", duration);
    }

    /// Mark span as failed with error
    pub fn finish_error(mut self, error: &str) {
        self.finished = true;
        let duration = self.elapsed_secs();
        debug!(
            tool = %self.tool_name,
            tenant = %self.tenant_id,
            duration_ms = %(duration * 1000.0),
            status = "error",
            error = %error,
            "Tool execution failed"
        );

        // Record metrics
        crate::metrics::record_tool_call(&self.tool_name, &self.tenant_id, "error", duration);
    }

    /// Mark span as cache hit (no execution)
    pub fn finish_cache_hit(mut self) {
        self.finished = true;
        let duration = self.elapsed_secs();
        debug!(
            tool = %self.tool_name,
            tenant = %self.tenant_id,
            duration_ms = %(duration * 1000.0),
            status = "cache_hit",
            "Tool result served from cache"
        );

        // Record metrics with cache_hit status
        crate::metrics::record_tool_call(&self.tool_name, &self.tenant_id, "cache_hit", duration);
    }

    /// Mark span as circuit breaker open (fast fail)
    pub fn finish_circuit_open(mut self) {
        self.finished = true;
        let duration = self.elapsed_secs();
        debug!(
            tool = %self.tool_name,
            tenant = %self.tenant_id,
            duration_ms = %(duration * 1000.0),
            status = "circuit_open",
            "Tool call rejected - circuit breaker open"
        );

        crate::metrics::record_tool_call(
            &self.tool_name,
            &self.tenant_id,
            "circuit_open",
            duration,
        );
    }
}

impl Drop for ToolSpan {
    fn drop(&mut self) {
        // If not explicitly finished, record as error (likely panic)
        if !self.finished {
            let duration = self.elapsed_secs();
            crate::metrics::record_tool_call(&self.tool_name, &self.tenant_id, "dropped", duration);
        }
    }
}

/// RAII guard for automatic span finishing
///
/// Use when you want the span to auto-finish on scope exit.
pub struct ToolSpanGuard {
    span: Option<ToolSpan>,
    error: Option<String>,
}

impl ToolSpanGuard {
    /// Create a new guard wrapping a span
    pub fn new(span: ToolSpan) -> Self {
        Self {
            span: Some(span),
            error: None,
        }
    }

    /// Set error to be recorded on drop
    pub fn set_error(&mut self, error: impl Into<String>) {
        self.error = Some(error.into());
    }

    /// Explicitly finish with success (takes ownership)
    pub fn success(mut self) {
        if let Some(span) = self.span.take() {
            span.finish_success();
        }
    }

    /// Explicitly finish with error (takes ownership)
    pub fn error(mut self, err: &str) {
        if let Some(span) = self.span.take() {
            span.finish_error(err);
        }
    }
}

impl Drop for ToolSpanGuard {
    fn drop(&mut self) {
        if let Some(span) = self.span.take() {
            if let Some(ref err) = self.error {
                span.finish_error(err);
            } else {
                // Default to success if no error set
                span.finish_success();
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tool_span_creation() {
        let span = ToolSpan::new("test_tool", "test-tenant");
        assert_eq!(span.tool_name, "test_tool");
        assert_eq!(span.tenant_id, "test-tenant");
        span.finish_success();
    }

    #[test]
    fn test_tool_span_error() {
        let span = ToolSpan::new("test_tool", "test-tenant");
        span.finish_error("something went wrong");
    }

    #[test]
    fn test_tool_span_cache_hit() {
        let span = ToolSpan::new("test_tool", "test-tenant");
        span.finish_cache_hit();
    }

    #[test]
    fn test_tool_span_circuit_open() {
        let span = ToolSpan::new("test_tool", "test-tenant");
        span.finish_circuit_open();
    }

    #[test]
    fn test_tool_span_guard_success() {
        let span = ToolSpan::new("test_tool", "test-tenant");
        let guard = ToolSpanGuard::new(span);
        guard.success();
    }

    #[test]
    fn test_tool_span_guard_auto_success() {
        let span = ToolSpan::new("test_tool", "test-tenant");
        let _guard = ToolSpanGuard::new(span);
        // Auto-finishes on drop with success
    }

    #[test]
    fn test_tool_span_guard_with_error() {
        let span = ToolSpan::new("test_tool", "test-tenant");
        let mut guard = ToolSpanGuard::new(span);
        guard.set_error("oops");
        // Will finish with error on drop
    }

    #[test]
    fn test_elapsed_secs() {
        let span = ToolSpan::new("test_tool", "test-tenant");
        std::thread::sleep(std::time::Duration::from_millis(10));
        let elapsed = span.elapsed_secs();
        assert!(elapsed >= 0.01);
        span.finish_success();
    }
}
