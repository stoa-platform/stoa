//! Tool Span Helpers (CAB-1831: enriched with upstream context)
//!
//! Provides instrumentation for tool execution with OTel integration.
//! Enriched span attributes: upstream RTT, TLS version, pool reuse, circuit breaker state.

use std::time::Instant;
use tracing::{debug, span, Level, Span};

/// A span for tracking tool execution with enriched upstream context.
pub struct ToolSpan {
    tool_name: String,
    tenant_id: String,
    consumer_id: String,
    start: Instant,
    _tracing_span: Span,
    finished: bool,
}

impl ToolSpan {
    /// Create a new tool span
    pub fn new(tool_name: &str, tenant_id: &str, consumer_id: &str) -> Self {
        let tracing_span = span!(
            Level::INFO,
            "tool_call",
            tool = %tool_name,
            tenant = %tenant_id,
            otel.kind = "server",
            contract_id = tracing::field::Empty,
            auth_type = tracing::field::Empty,
            http.method = tracing::field::Empty,
            http.target = tracing::field::Empty,
            // CAB-1831: enriched upstream context
            upstream.rtt_ms = tracing::field::Empty,
            upstream.tls_version = tracing::field::Empty,
            upstream.pool_reuse = tracing::field::Empty,
            upstream.cb_state = tracing::field::Empty,
        );

        debug!(
            tool = %tool_name,
            tenant = %tenant_id,
            "Tool execution started"
        );

        Self {
            tool_name: tool_name.to_string(),
            tenant_id: tenant_id.to_string(),
            consumer_id: consumer_id.to_string(),
            start: Instant::now(),
            _tracing_span: tracing_span,
            finished: false,
        }
    }

    /// Attach UAC context attributes to the span.
    pub fn with_uac(
        self,
        contract_id: Option<&str>,
        auth_type: Option<&str>,
        method: Option<&str>,
        path: Option<&str>,
    ) -> Self {
        if let Some(v) = contract_id {
            self._tracing_span.record("contract_id", v);
        }
        if let Some(v) = auth_type {
            self._tracing_span.record("auth_type", v);
        }
        if let Some(v) = method {
            self._tracing_span.record("http.method", v);
        }
        if let Some(v) = path {
            self._tracing_span.record("http.target", v);
        }
        self
    }

    /// Attach upstream context: RTT, TLS version, connection pool reuse, circuit breaker state.
    pub fn with_upstream(
        self,
        rtt_ms: Option<f64>,
        tls_version: Option<&str>,
        pool_reuse: Option<bool>,
        cb_state: Option<&str>,
    ) -> Self {
        if let Some(v) = rtt_ms {
            self._tracing_span
                .record("upstream.rtt_ms", format!("{v:.2}"));
        }
        if let Some(v) = tls_version {
            self._tracing_span.record("upstream.tls_version", v);
        }
        if let Some(v) = pool_reuse {
            self._tracing_span.record("upstream.pool_reuse", v);
        }
        if let Some(v) = cb_state {
            self._tracing_span.record("upstream.cb_state", v);
        }
        self
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

        crate::metrics::record_tool_call(
            &self.tool_name,
            &self.tenant_id,
            "success",
            duration,
            &self.consumer_id,
        );
        crate::telemetry::record_span_exported();
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

        crate::metrics::record_tool_call(
            &self.tool_name,
            &self.tenant_id,
            "error",
            duration,
            &self.consumer_id,
        );
        crate::telemetry::record_span_exported();
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

        crate::metrics::record_tool_call(
            &self.tool_name,
            &self.tenant_id,
            "cache_hit",
            duration,
            &self.consumer_id,
        );
        crate::telemetry::record_span_exported();
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
            &self.consumer_id,
        );
        crate::telemetry::record_span_exported();
    }
}

impl Drop for ToolSpan {
    fn drop(&mut self) {
        // If not explicitly finished, record as error (likely panic)
        if !self.finished {
            let duration = self.elapsed_secs();
            crate::metrics::record_tool_call(
                &self.tool_name,
                &self.tenant_id,
                "dropped",
                duration,
                &self.consumer_id,
            );
        }
    }
}

/// RAII guard for automatic span finishing
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
        let span = ToolSpan::new("test_tool", "test-tenant", "test-consumer");
        assert_eq!(span.tool_name, "test_tool");
        assert_eq!(span.tenant_id, "test-tenant");
        span.finish_success();
    }

    #[test]
    fn test_tool_span_error() {
        let span = ToolSpan::new("test_tool", "test-tenant", "test-consumer");
        span.finish_error("something went wrong");
    }

    #[test]
    fn test_tool_span_cache_hit() {
        let span = ToolSpan::new("test_tool", "test-tenant", "test-consumer");
        span.finish_cache_hit();
    }

    #[test]
    fn test_tool_span_circuit_open() {
        let span = ToolSpan::new("test_tool", "test-tenant", "test-consumer");
        span.finish_circuit_open();
    }

    #[test]
    fn test_tool_span_guard_success() {
        let span = ToolSpan::new("test_tool", "test-tenant", "test-consumer");
        let guard = ToolSpanGuard::new(span);
        guard.success();
    }

    #[test]
    fn test_tool_span_guard_auto_success() {
        let span = ToolSpan::new("test_tool", "test-tenant", "test-consumer");
        let _guard = ToolSpanGuard::new(span);
        // Auto-finishes on drop with success
    }

    #[test]
    fn test_tool_span_guard_with_error() {
        let span = ToolSpan::new("test_tool", "test-tenant", "test-consumer");
        let mut guard = ToolSpanGuard::new(span);
        guard.set_error("oops");
        // Will finish with error on drop
    }

    #[test]
    fn test_elapsed_secs() {
        let span = ToolSpan::new("test_tool", "test-tenant", "test-consumer");
        std::thread::sleep(std::time::Duration::from_millis(10));
        let elapsed = span.elapsed_secs();
        assert!(elapsed >= 0.01);
        span.finish_success();
    }

    #[test]
    fn test_tool_span_with_uac_attributes() {
        let span = ToolSpan::new("test_tool", "test-tenant", "test-consumer").with_uac(
            Some("contract-123"),
            Some("jwt"),
            Some("POST"),
            Some("/v1/tools/call"),
        );
        assert_eq!(span.tool_name, "test_tool");
        span.finish_success();
    }

    #[test]
    fn test_tool_span_with_partial_uac() {
        let span = ToolSpan::new("test_tool", "test-tenant", "test-consumer").with_uac(
            Some("contract-456"),
            None,
            None,
            Some("/health"),
        );
        span.finish_success();
    }

    #[test]
    fn test_tool_span_with_no_uac() {
        let span = ToolSpan::new("test_tool", "test-tenant", "test-consumer")
            .with_uac(None, None, None, None);
        span.finish_success();
    }

    // CAB-1831: upstream context enrichment tests

    #[test]
    fn test_tool_span_with_full_upstream_context() {
        let span = ToolSpan::new("test_tool", "test-tenant", "test-consumer").with_upstream(
            Some(42.5),
            Some("TLSv1.3"),
            Some(true),
            Some("closed"),
        );
        assert_eq!(span.tool_name, "test_tool");
        span.finish_success();
    }

    #[test]
    fn test_tool_span_with_partial_upstream() {
        let span = ToolSpan::new("test_tool", "test-tenant", "test-consumer").with_upstream(
            Some(15.0),
            None,
            None,
            Some("half_open"),
        );
        span.finish_success();
    }

    #[test]
    fn test_tool_span_with_no_upstream() {
        let span = ToolSpan::new("test_tool", "test-tenant", "test-consumer")
            .with_upstream(None, None, None, None);
        span.finish_success();
    }

    #[test]
    fn test_tool_span_combined_uac_and_upstream() {
        let span = ToolSpan::new("test_tool", "test-tenant", "test-consumer")
            .with_uac(Some("c-1"), Some("jwt"), Some("POST"), Some("/api"))
            .with_upstream(Some(120.3), Some("TLSv1.2"), Some(false), Some("open"));
        span.finish_success();
    }
}
