//! Tool Span Helpers (CAB-1831: enriched with upstream context)
//!
//! Provides instrumentation for tool execution with OTel integration.
//! Enriched span attributes: upstream RTT, TLS version, pool reuse, circuit breaker state.
//! CAB-1842: deployment mode + policy applied attributes for service graph visualization.

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
    policies_applied: Vec<String>,
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
            // CAB-1842: service graph attributes
            "stoa.deployment_mode" = tracing::field::Empty,
            "stoa.policy.applied" = tracing::field::Empty,
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
            policies_applied: Vec::new(),
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

    /// Attach gateway deployment mode for service graph differentiation (CAB-1842).
    ///
    /// Values: "edge-mcp", "sidecar", "proxy", "shadow", "connect".
    /// Tempo metrics-generator uses this dimension to color nodes in the service graph.
    pub fn with_deployment_mode(self, mode: &str) -> Self {
        self._tracing_span.record("stoa.deployment_mode", mode);
        self
    }

    /// Record a policy that was applied during this request (CAB-1842).
    ///
    /// Call once per policy middleware (e.g., "auth-oidc", "rate-limit", "pii-guard").
    /// The accumulated list is flushed to the span attribute on finish.
    pub fn record_policy(&mut self, policy_name: &str) {
        self.policies_applied.push(policy_name.to_string());
    }

    /// Flush accumulated policies to the span attribute.
    fn flush_policies(&self) {
        if !self.policies_applied.is_empty() {
            let policies = self.policies_applied.join(",");
            self._tracing_span
                .record("stoa.policy.applied", policies.as_str());
        }
    }

    /// Get elapsed duration in seconds
    pub fn elapsed_secs(&self) -> f64 {
        self.start.elapsed().as_secs_f64()
    }

    /// Mark span as successful
    pub fn finish_success(mut self) {
        self.finished = true;
        self.flush_policies();
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
        self.flush_policies();
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
        self.flush_policies();
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
        self.flush_policies();
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

/// A child span for individual policy/middleware execution (CAB-1842).
///
/// Created when `STOA_DETAILED_TRACING=true`. Each policy middleware
/// (auth, rate-limit, guardrails, quota) gets its own span, enabling
/// a waterfall breakdown in the trace view.
pub struct PolicySpan {
    _tracing_span: Span,
    start: Instant,
}

impl PolicySpan {
    /// Create a child span for a policy middleware step.
    pub fn new(policy_name: &str, tenant_id: &str) -> Self {
        let tracing_span = span!(
            Level::DEBUG,
            "policy",
            policy = %policy_name,
            tenant = %tenant_id,
            otel.kind = "internal",
            "stoa.policy.name" = %policy_name,
            "stoa.policy.verdict" = tracing::field::Empty,
        );

        Self {
            _tracing_span: tracing_span,
            start: Instant::now(),
        }
    }

    /// Mark policy as allowed
    pub fn finish_allow(self) {
        self._tracing_span.record("stoa.policy.verdict", "allow");
        debug!(
            duration_ms = %(self.start.elapsed().as_secs_f64() * 1000.0),
            "Policy passed"
        );
    }

    /// Mark policy as denied
    pub fn finish_deny(self, reason: &str) {
        self._tracing_span.record("stoa.policy.verdict", "deny");
        debug!(
            duration_ms = %(self.start.elapsed().as_secs_f64() * 1000.0),
            reason = %reason,
            "Policy denied"
        );
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

    // CAB-1842: deployment mode + policy applied tests

    #[test]
    fn test_tool_span_with_deployment_mode() {
        let span = ToolSpan::new("test_tool", "test-tenant", "test-consumer")
            .with_deployment_mode("edge-mcp");
        assert_eq!(span.tool_name, "test_tool");
        span.finish_success();
    }

    #[test]
    fn test_tool_span_with_connect_mode() {
        let span = ToolSpan::new("test_tool", "test-tenant", "test-consumer")
            .with_deployment_mode("connect");
        span.finish_success();
    }

    #[test]
    fn test_tool_span_with_sidecar_mode() {
        let span = ToolSpan::new("test_tool", "test-tenant", "test-consumer")
            .with_deployment_mode("sidecar");
        span.finish_success();
    }

    #[test]
    fn test_tool_span_record_policies() {
        let mut span = ToolSpan::new("test_tool", "test-tenant", "test-consumer")
            .with_deployment_mode("edge-mcp");
        span.record_policy("auth-oidc");
        span.record_policy("rate-limit");
        span.record_policy("pii-guard");
        assert_eq!(span.policies_applied.len(), 3);
        span.finish_success();
    }

    #[test]
    fn test_tool_span_no_policies() {
        let span = ToolSpan::new("test_tool", "test-tenant", "test-consumer")
            .with_deployment_mode("edge-mcp");
        assert!(span.policies_applied.is_empty());
        span.finish_success();
    }

    #[test]
    fn test_tool_span_full_enrichment() {
        let mut span = ToolSpan::new("test_tool", "test-tenant", "test-consumer")
            .with_deployment_mode("edge-mcp")
            .with_uac(Some("c-1"), Some("jwt"), Some("POST"), Some("/api"))
            .with_upstream(Some(42.0), Some("TLSv1.3"), Some(true), Some("closed"));
        span.record_policy("auth-oidc");
        span.record_policy("quota");
        span.finish_success();
    }

    // CAB-1842: PolicySpan tests

    #[test]
    fn test_policy_span_allow() {
        let span = PolicySpan::new("auth-oidc", "test-tenant");
        span.finish_allow();
    }

    #[test]
    fn test_policy_span_deny() {
        let span = PolicySpan::new("rate-limit", "test-tenant");
        span.finish_deny("quota exceeded");
    }
}
