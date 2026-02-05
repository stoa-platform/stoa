//! MCP Metrics
//!
//! Prometheus metrics for MCP operations:
//! - Tool call duration histograms
//! - SSE connection duration
//! - Request counters

use once_cell::sync::Lazy;
use prometheus::{
    register_counter_vec, register_gauge, register_histogram_vec, CounterVec, Gauge, HistogramVec,
};

// === Tool Metrics ===

/// Histogram of MCP tool call durations in seconds
pub static MCP_TOOL_DURATION: Lazy<HistogramVec> = Lazy::new(|| {
    register_histogram_vec!(
        "stoa_mcp_tool_duration_seconds",
        "Duration of MCP tool calls",
        &["tool", "tenant", "status"],
        vec![0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
    )
    .expect("Failed to create stoa_mcp_tool_duration_seconds metric")
});

/// Counter of MCP tool calls
pub static MCP_TOOL_CALLS_TOTAL: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_mcp_tools_calls_total",
        "Total number of MCP tool calls",
        &["tool", "tenant", "status"]
    )
    .expect("Failed to create stoa_mcp_tools_calls_total metric")
});

// === SSE Metrics ===

/// Histogram of SSE connection durations in seconds
pub static MCP_SSE_CONNECTION_DURATION: Lazy<HistogramVec> = Lazy::new(|| {
    register_histogram_vec!(
        "stoa_mcp_sse_connection_duration_seconds",
        "Duration of SSE connections",
        &["tenant"],
        vec![1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0, 1800.0]
    )
    .expect("Failed to create stoa_mcp_sse_connection_duration_seconds metric")
});

/// Gauge of active SSE connections
pub static MCP_SSE_CONNECTIONS_ACTIVE: Lazy<Gauge> = Lazy::new(|| {
    register_gauge!(
        "stoa_mcp_sse_connections_active",
        "Number of active SSE connections"
    )
    .expect("Failed to create stoa_mcp_sse_connections_active metric")
});

// === Session Metrics ===

/// Gauge of active MCP sessions
pub static MCP_SESSIONS_ACTIVE: Lazy<Gauge> = Lazy::new(|| {
    register_gauge!("stoa_mcp_sessions_active", "Number of active MCP sessions")
        .expect("Failed to create stoa_mcp_sessions_active metric")
});

// === Rate Limit Metrics ===

/// Counter of rate limit hits
pub static RATE_LIMIT_HITS: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_rate_limit_hits_total",
        "Total number of rate limit hits",
        &["tenant"]
    )
    .expect("Failed to create stoa_rate_limit_hits_total metric")
});

/// Gauge of rate limiter bucket count
pub static RATE_LIMIT_BUCKETS: Lazy<Gauge> = Lazy::new(|| {
    register_gauge!(
        "stoa_rate_limit_buckets",
        "Number of active rate limit buckets"
    )
    .expect("Failed to create stoa_rate_limit_buckets metric")
});

// === Helper Functions ===

/// Extract the current OTel trace_id from the active tracing span (if any).
/// TODO: Re-enable once OpenTelemetry deps are stabilized (CAB-1088).
#[allow(dead_code)]
fn current_trace_id() -> Option<String> {
    // Disabled: opentelemetry 0.27 API changes pending resolution
    None
}

/// Record a tool call with timing and optional trace_id exemplar.
///
/// When OTel tracing is active, the histogram observation includes
/// a `trace_id` exemplar, enabling click-through from Grafana metrics
/// panels directly to the Tempo trace view.
pub fn record_tool_call(tool: &str, tenant: &str, status: &str, duration_secs: f64) {
    let histogram = MCP_TOOL_DURATION.with_label_values(&[tool, tenant, status]);

    // TODO: re-enable exemplar support once prometheus crate supports it
    // (observe_with_exemplar not available in prometheus 0.13)
    histogram.observe(duration_secs);

    MCP_TOOL_CALLS_TOTAL
        .with_label_values(&[tool, tenant, status])
        .inc();
}

/// Track SSE connection (call on connect)
pub fn track_sse_connect() {
    MCP_SSE_CONNECTIONS_ACTIVE.inc();
}

/// Track SSE disconnect with duration
pub fn track_sse_disconnect(tenant: &str, duration_secs: f64) {
    MCP_SSE_CONNECTIONS_ACTIVE.dec();
    MCP_SSE_CONNECTION_DURATION
        .with_label_values(&[tenant])
        .observe(duration_secs);
}

/// Update session count gauge
pub fn update_session_count(count: usize) {
    MCP_SESSIONS_ACTIVE.set(count as f64);
}

/// Record rate limit hit
pub fn record_rate_limit_hit(tenant: &str) {
    RATE_LIMIT_HITS.with_label_values(&[tenant]).inc();
}

/// Update rate limit bucket count
pub fn update_rate_limit_buckets(count: usize) {
    RATE_LIMIT_BUCKETS.set(count as f64);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_record_tool_call() {
        // Should not panic
        record_tool_call("test_tool", "tenant-1", "success", 0.05);
    }

    #[test]
    fn test_sse_tracking() {
        track_sse_connect();
        track_sse_disconnect("tenant-1", 30.0);
    }
}
