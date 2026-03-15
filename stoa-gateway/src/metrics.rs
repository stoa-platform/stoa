//! Gateway Metrics
//!
//! Prometheus metrics for the STOA Gateway:
//! - HTTP request counters and latency histograms (all endpoints)
//! - MCP tool call duration histograms
//! - SSE connection duration
//! - Rate limit and session gauges

use once_cell::sync::Lazy;
use prometheus::{
    register_counter_vec, register_gauge, register_gauge_vec, register_histogram_vec, CounterVec,
    Gauge, GaugeVec, HistogramVec,
};

// === HTTP Metrics (all requests) ===

/// Counter of all HTTP requests by method, path, and status code.
pub static HTTP_REQUESTS_TOTAL: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_http_requests_total",
        "Total number of HTTP requests",
        &["method", "path", "status"]
    )
    .expect("Failed to create stoa_http_requests_total metric")
});

/// Histogram of HTTP request durations in seconds.
pub static HTTP_REQUEST_DURATION: Lazy<HistogramVec> = Lazy::new(|| {
    register_histogram_vec!(
        "stoa_http_request_duration_seconds",
        "Duration of HTTP requests in seconds",
        &["method", "path"],
        vec![0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
    )
    .expect("Failed to create stoa_http_request_duration_seconds metric")
});

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

/// Counter of MCP tool calls (includes consumer_id for per-consumer analytics, CAB-1782)
pub static MCP_TOOL_CALLS_TOTAL: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_mcp_tools_calls_total",
        "Total number of MCP tool calls",
        &["tool", "tenant", "status", "consumer_id"]
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

// === Circuit Breaker Metrics (ADR-025) ===

/// Gauge of circuit breaker state per upstream.
/// Values: 0 = closed, 1 = open, 2 = half_open
pub static CIRCUIT_BREAKER_STATE: Lazy<GaugeVec> = Lazy::new(|| {
    register_gauge_vec!(
        "stoa_circuit_breaker_state",
        "Circuit breaker state per upstream (0=closed, 1=open, 2=half_open)",
        &["upstream"]
    )
    .expect("Failed to create stoa_circuit_breaker_state metric")
});

// === Quota Metrics (ADR-022) ===

/// Gauge of remaining quota per consumer and period.
pub static QUOTA_REMAINING: Lazy<GaugeVec> = Lazy::new(|| {
    register_gauge_vec!(
        "stoa_quota_remaining",
        "Remaining quota requests per consumer and period",
        &["consumer", "period"]
    )
    .expect("Failed to create stoa_quota_remaining metric")
});

// === mTLS Metrics (CAB-864) ===

/// Counter of mTLS certificate validation outcomes.
pub static MTLS_VALIDATIONS_TOTAL: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_mtls_validations_total",
        "Total mTLS certificate validations",
        &["result", "tenant"]
    )
    .expect("Failed to create stoa_mtls_validations_total metric")
});

/// Counter of RFC 8705 certificate-token binding checks.
pub static MTLS_BINDING_CHECKS_TOTAL: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_mtls_binding_checks_total",
        "Total RFC 8705 certificate-token binding checks",
        &["result"]
    )
    .expect("Failed to create stoa_mtls_binding_checks_total metric")
});

/// Gauge of certificates expiring within 30 days.
pub static MTLS_CERTS_EXPIRING_SOON: Lazy<Gauge> = Lazy::new(|| {
    register_gauge!(
        "stoa_mtls_certs_expiring_soon",
        "Number of certificates expiring within 30 days"
    )
    .expect("Failed to create stoa_mtls_certs_expiring_soon metric")
});

// === Guardrails Metrics (CAB-707) ===

/// Counter of PII detections in tool call arguments.
pub static GUARDRAILS_PII_DETECTED: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_guardrails_pii_detected_total",
        "Total PII detections in tool call arguments",
        &["action"]
    )
    .expect("Failed to create stoa_guardrails_pii_detected_total metric")
});

/// Counter of prompt injection attempts blocked.
pub static GUARDRAILS_INJECTION_BLOCKED: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_guardrails_injection_blocked_total",
        "Total prompt injection attempts blocked",
        &["tool"]
    )
    .expect("Failed to create stoa_guardrails_injection_blocked_total metric")
});

/// Counter of content filter events (CAB-1337 Phase 1).
/// Labels: action=blocked|sensitive, category=financial|medical|violence|malware
pub static GUARDRAILS_CONTENT_FILTERED: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_guardrails_content_filtered_total",
        "Total content filter events by action and category",
        &["action", "category"]
    )
    .expect("Failed to create stoa_guardrails_content_filtered_total metric")
});

// === Prompt Guard Metrics (CAB-1761) ===

/// Counter of prompt guard detections by category and action.
pub static PROMPT_GUARD_DETECTED: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_prompt_guard_detected_total",
        "Total prompt guard threat detections by category and action",
        &["category", "action"]
    )
    .expect("Failed to create stoa_prompt_guard_detected_total metric")
});

/// Counter of prompts scanned by the prompt guard (pass + detected).
pub static PROMPT_GUARD_SCANNED: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_prompt_guard_scanned_total",
        "Total prompts scanned by prompt guard",
        &["result"]
    )
    .expect("Failed to create stoa_prompt_guard_scanned_total metric")
});

// === RAG Injector Metrics (CAB-1761) ===

/// Counter of RAG context injection attempts by source and result.
pub static RAG_INJECTIONS_TOTAL: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_rag_injections_total",
        "Total RAG context injection attempts by source and result",
        &["source", "result"]
    )
    .expect("Failed to create stoa_rag_injections_total metric")
});

/// Histogram of RAG source fetch duration in seconds.
pub static RAG_FETCH_DURATION: Lazy<HistogramVec> = Lazy::new(|| {
    register_histogram_vec!(
        "stoa_rag_fetch_duration_seconds",
        "Duration of RAG context source fetch operations",
        &["source"]
    )
    .expect("Failed to create stoa_rag_fetch_duration_seconds metric")
});

// === Token Budget Metrics (CAB-1337 Phase 2) ===

/// Total tokens processed per tenant and direction.
pub static TOKEN_BUDGET_TOKENS_TOTAL: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_token_budget_tokens_total",
        "Total tokens processed per tenant and direction",
        &["tenant", "direction"]
    )
    .expect("Failed to create stoa_token_budget_tokens_total metric")
});

/// Token budget exceeded events per tenant.
pub static TOKEN_BUDGET_EXCEEDED_TOTAL: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_token_budget_exceeded_total",
        "Total token budget exceeded events per tenant",
        &["tenant"]
    )
    .expect("Failed to create stoa_token_budget_exceeded_total metric")
});

// === DPoP Metrics (CAB-438, RFC 9449) ===

/// Counter of DPoP proof validations by result (valid, invalid_signature, expired, replay, etc.)
pub static DPOP_VALIDATIONS_TOTAL: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_dpop_validations_total",
        "Total DPoP proof validations by result",
        &["result"]
    )
    .expect("Failed to create stoa_dpop_validations_total metric")
});

// === Sender-Constraint Metrics (CAB-1607) ===

/// Counter of unified sender-constraint checks by result, method, and tenant.
pub static SENDER_CONSTRAINT_CHECKS_TOTAL: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_sender_constraint_checks_total",
        "Total sender-constraint checks (mTLS + DPoP unified pipeline)",
        &["result", "method", "tenant"]
    )
    .expect("Failed to create stoa_sender_constraint_checks_total metric")
});

// === Security Profile Enforcement Metrics (CAB-1744) ===

/// Counter of profile enforcement checks by result and profile.
pub static PROFILE_ENFORCEMENT_TOTAL: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_profile_enforcement_total",
        "Total security profile enforcement checks by result and profile",
        &["result", "profile"]
    )
    .expect("Failed to create stoa_profile_enforcement_total metric")
});

// === HEGEMON Supervision Metrics (CAB-1636) ===

/// Counter of HEGEMON supervision decisions by tier and action.
/// Labels: tier (autopilot|copilot|command), action (pass|notify|block).
pub static SUPERVISION_DECISIONS_TOTAL: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_hegemon_supervision_decisions_total",
        "Total HEGEMON supervision decisions by tier and action",
        &["tier", "action"]
    )
    .expect("Failed to create stoa_hegemon_supervision_decisions_total metric")
});

/// Record a supervision decision.
pub fn record_supervision_decision(tier: &str, action: &str) {
    SUPERVISION_DECISIONS_TOTAL
        .with_label_values(&[tier, action])
        .inc();
}

// === HEGEMON Dispatch Metrics (CAB-1713) ===

/// Counter of HEGEMON dispatches by worker name.
pub static HEGEMON_DISPATCHES_TOTAL: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_hegemon_dispatches_total",
        "Total HEGEMON dispatches by worker",
        &["worker"]
    )
    .expect("Failed to create stoa_hegemon_dispatches_total metric")
});

/// Gauge of active (in-progress) HEGEMON dispatches.
pub static HEGEMON_DISPATCH_ACTIVE: Lazy<Gauge> = Lazy::new(|| {
    register_gauge!(
        "stoa_hegemon_dispatch_active",
        "Number of active HEGEMON dispatches"
    )
    .expect("Failed to create stoa_hegemon_dispatch_active metric")
});

/// Histogram of HEGEMON dispatch durations in seconds, by worker.
pub static HEGEMON_DISPATCH_DURATION: Lazy<HistogramVec> = Lazy::new(|| {
    register_histogram_vec!(
        "stoa_hegemon_dispatch_duration_seconds",
        "Duration of HEGEMON dispatches in seconds",
        &["worker"],
        vec![60.0, 300.0, 600.0, 900.0, 1800.0, 3600.0, 7200.0]
    )
    .expect("Failed to create stoa_hegemon_dispatch_duration_seconds metric")
});

/// Histogram of HEGEMON dispatch cost in USD, by worker.
pub static HEGEMON_DISPATCH_COST: Lazy<HistogramVec> = Lazy::new(|| {
    register_histogram_vec!(
        "stoa_hegemon_dispatch_cost_usd",
        "Cost of HEGEMON dispatches in USD",
        &["worker"],
        vec![0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0]
    )
    .expect("Failed to create stoa_hegemon_dispatch_cost_usd metric")
});

// === HEGEMON Budget Metrics (CAB-1716) ===

/// Gauge of daily spend per agent in USD.
pub static HEGEMON_BUDGET_DAILY_USD: Lazy<GaugeVec> = Lazy::new(|| {
    register_gauge_vec!(
        "stoa_hegemon_budget_daily_usd",
        "Daily budget spent per HEGEMON agent in USD",
        &["worker"]
    )
    .expect("Failed to create stoa_hegemon_budget_daily_usd metric")
});

// === Tool Discovery Metrics (CAB-1558) ===

/// Histogram of tool discovery (CP sync) durations in seconds, per tenant and outcome.
pub static TOOL_DISCOVERY_DURATION: Lazy<HistogramVec> = Lazy::new(|| {
    register_histogram_vec!(
        "stoa_tool_discovery_duration_seconds",
        "Duration of tool discovery calls to control plane",
        &["tenant", "result"],
        vec![0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
    )
    .expect("Failed to create stoa_tool_discovery_duration_seconds metric")
});

/// Counter of tool discovery failures per tenant.
pub static TOOL_DISCOVERY_FAILURES_TOTAL: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_tool_discovery_failures_total",
        "Total tool discovery failures (CP unreachable or error)",
        &["tenant"]
    )
    .expect("Failed to create stoa_tool_discovery_failures_total metric")
});

// === Fallback Metrics (CAB-708) ===

/// Counter of fallback chain attempts (primary tool failed, trying fallbacks).
pub static FALLBACK_ATTEMPTS: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_fallback_attempts_total",
        "Total fallback chain attempts (primary tool failed)",
        &["tool"]
    )
    .expect("Failed to create stoa_fallback_attempts_total metric")
});

/// Counter of exhausted fallback chains (all providers failed).
pub static FALLBACK_EXHAUSTED: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_fallback_exhausted_total",
        "Total fallback chains exhausted (all providers failed)",
        &["tool"]
    )
    .expect("Failed to create stoa_fallback_exhausted_total metric")
});

// === Federation Metrics (CAB-1371) ===

/// Counter of federation requests by sub-account and status.
pub static FEDERATION_REQUESTS_TOTAL: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_federation_requests_total",
        "Total federation requests by sub-account",
        &["sub_account_id", "master_account_id", "status"]
    )
    .expect("Failed to create stoa_federation_requests_total metric")
});

// === API Proxy Metrics (CAB-1726) ===

/// Counter of API proxy requests by backend, method, and status code.
pub static API_PROXY_REQUESTS_TOTAL: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_api_proxy_requests_total",
        "Total API proxy requests by backend",
        &["backend", "method", "status"]
    )
    .expect("Failed to create stoa_api_proxy_requests_total metric")
});

/// Histogram of API proxy request durations in seconds, by backend.
pub static API_PROXY_DURATION: Lazy<HistogramVec> = Lazy::new(|| {
    register_histogram_vec!(
        "stoa_api_proxy_duration_seconds",
        "Duration of API proxy requests in seconds",
        &["backend"],
        vec![0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
    )
    .expect("Failed to create stoa_api_proxy_duration_seconds metric")
});

/// Counter of API proxy rate limit rejections by backend.
pub static API_PROXY_RATE_LIMITED: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_api_proxy_rate_limited_total",
        "Total API proxy rate limit rejections",
        &["backend"]
    )
    .expect("Failed to create stoa_api_proxy_rate_limited_total metric")
});

/// Counter of API proxy circuit breaker rejections by backend.
pub static API_PROXY_CIRCUIT_OPEN: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_api_proxy_circuit_open_total",
        "Total API proxy circuit breaker rejections",
        &["backend"]
    )
    .expect("Failed to create stoa_api_proxy_circuit_open_total metric")
});

// === Upstream Latency Metrics ===

/// Histogram of upstream (backend) response times in seconds.
pub static UPSTREAM_LATENCY: Lazy<HistogramVec> = Lazy::new(|| {
    register_histogram_vec!(
        "stoa_upstream_latency_seconds",
        "Backend upstream response time in seconds",
        &["upstream", "status"],
        vec![0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
    )
    .expect("Failed to create stoa_upstream_latency_seconds metric")
});

// === Helper Functions ===

/// Record a tool call with timing and optional trace_id exemplar.
///
/// When OTel tracing is active, the histogram observation includes
/// a `trace_id` exemplar, enabling click-through from Grafana metrics
/// panels directly to the Tempo trace view.
pub fn record_tool_call(
    tool: &str,
    tenant: &str,
    status: &str,
    duration_secs: f64,
    consumer_id: &str,
) {
    let histogram = MCP_TOOL_DURATION.with_label_values(&[tool, tenant, status]);

    // CAB-1088: exemplar support blocked on prometheus crate 0.14
    // (observe_with_exemplar not available in 0.13; track upstream PR)
    histogram.observe(duration_secs);

    // CAB-1782: consumer_id on CounterVec only (not HistogramVec — cardinality guard)
    MCP_TOOL_CALLS_TOTAL
        .with_label_values(&[tool, tenant, status, consumer_id])
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

// === WebSocket Metrics (CAB-1345) ===

pub static MCP_WS_CONNECTIONS_ACTIVE: Lazy<Gauge> = Lazy::new(|| {
    register_gauge!(
        "stoa_mcp_ws_connections_active",
        "Number of active WebSocket connections"
    )
    .expect("Failed to create stoa_mcp_ws_connections_active metric")
});

pub static MCP_WS_CONNECTION_DURATION: Lazy<HistogramVec> = Lazy::new(|| {
    register_histogram_vec!(
        "stoa_mcp_ws_connection_duration_seconds",
        "Duration of WebSocket connections",
        &["tenant"],
        vec![1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0, 1800.0]
    )
    .expect("Failed to create stoa_mcp_ws_connection_duration_seconds metric")
});

pub static MCP_WS_MESSAGES_TOTAL: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_mcp_ws_messages_total",
        "Total WebSocket messages",
        &["direction", "method"]
    )
    .expect("Failed to create stoa_mcp_ws_messages_total metric")
});

pub fn track_ws_connect() {
    MCP_WS_CONNECTIONS_ACTIVE.inc();
}

pub fn track_ws_disconnect(tenant: &str, duration_secs: f64) {
    MCP_WS_CONNECTIONS_ACTIVE.dec();
    MCP_WS_CONNECTION_DURATION
        .with_label_values(&[tenant])
        .observe(duration_secs);
}

pub fn track_ws_message(direction: &str, method: &str) {
    MCP_WS_MESSAGES_TOTAL
        .with_label_values(&[direction, method])
        .inc();
}

// === WebSocket Proxy Metrics (CAB-1758) ===

pub static WS_PROXY_CONNECTIONS_ACTIVE: Lazy<Gauge> = Lazy::new(|| {
    register_gauge!(
        "stoa_ws_proxy_connections_active",
        "Number of active WebSocket proxy connections"
    )
    .expect("Failed to create stoa_ws_proxy_connections_active metric")
});

pub static WS_PROXY_CONNECTION_DURATION: Lazy<HistogramVec> = Lazy::new(|| {
    register_histogram_vec!(
        "stoa_ws_proxy_connection_duration_seconds",
        "Duration of WebSocket proxy connections",
        &["tenant"],
        vec![1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0, 1800.0]
    )
    .expect("Failed to create stoa_ws_proxy_connection_duration_seconds metric")
});

pub static WS_PROXY_MESSAGES_TOTAL: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_ws_proxy_messages_total",
        "Total WebSocket proxy messages relayed",
        &["direction", "route_id"]
    )
    .expect("Failed to create stoa_ws_proxy_messages_total metric")
});

pub static WS_PROXY_RATE_LIMITED_TOTAL: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_ws_proxy_rate_limited_total",
        "Total WebSocket proxy messages dropped by rate limiter",
        &["route_id", "source"]
    )
    .expect("Failed to create stoa_ws_proxy_rate_limited_total metric")
});

pub fn track_ws_proxy_connect() {
    WS_PROXY_CONNECTIONS_ACTIVE.inc();
}

pub fn track_ws_proxy_disconnect(tenant: &str, duration_secs: f64) {
    WS_PROXY_CONNECTIONS_ACTIVE.dec();
    WS_PROXY_CONNECTION_DURATION
        .with_label_values(&[tenant])
        .observe(duration_secs);
}

pub fn track_ws_proxy_message(direction: &str, route_id: &str) {
    WS_PROXY_MESSAGES_TOTAL
        .with_label_values(&[direction, route_id])
        .inc();
}

pub fn track_ws_proxy_rate_limited(route_id: &str, source: &str) {
    WS_PROXY_RATE_LIMITED_TOTAL
        .with_label_values(&[route_id, source])
        .inc();
}

// === SOAP/XML Bridge Metrics (CAB-1762) ===

static SOAP_PROXY_REQUESTS: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_soap_proxy_requests_total",
        "Total SOAP proxy requests",
        &["route_id"]
    )
    .expect("Failed to create stoa_soap_proxy_requests_total metric")
});

static SOAP_PROXY_RESPONSES: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_soap_proxy_responses_total",
        "Total SOAP proxy responses by success/failure",
        &["route_id", "success"]
    )
    .expect("Failed to create stoa_soap_proxy_responses_total metric")
});

static SOAP_PROXY_FAULTS: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_soap_proxy_faults_total",
        "Total SOAP faults detected in responses",
        &["route_id"]
    )
    .expect("Failed to create stoa_soap_proxy_faults_total metric")
});

static SOAP_BRIDGE_REQUESTS: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_soap_bridge_requests_total",
        "Total SOAP bridge tool invocations",
        &["operation"]
    )
    .expect("Failed to create stoa_soap_bridge_requests_total metric")
});

static SOAP_BRIDGE_RESPONSES: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_soap_bridge_responses_total",
        "Total SOAP bridge tool responses by success/failure",
        &["operation", "success"]
    )
    .expect("Failed to create stoa_soap_bridge_responses_total metric")
});

pub fn track_soap_proxy_request(route_id: &str) {
    SOAP_PROXY_REQUESTS.with_label_values(&[route_id]).inc();
}

pub fn track_soap_proxy_response(route_id: &str, success: bool) {
    SOAP_PROXY_RESPONSES
        .with_label_values(&[route_id, if success { "true" } else { "false" }])
        .inc();
}

pub fn track_soap_proxy_fault(route_id: &str) {
    SOAP_PROXY_FAULTS.with_label_values(&[route_id]).inc();
}

pub fn track_soap_bridge_request(operation: &str) {
    SOAP_BRIDGE_REQUESTS.with_label_values(&[operation]).inc();
}

pub fn track_soap_bridge_response(operation: &str, success: bool) {
    SOAP_BRIDGE_RESPONSES
        .with_label_values(&[operation, if success { "true" } else { "false" }])
        .inc();
}

// === gRPC Protocol Metrics (CAB-1755) ===

static GRPC_PROXY_REQUESTS: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_grpc_proxy_requests_total",
        "Total gRPC proxy requests",
        &["route_id"]
    )
    .expect("Failed to create stoa_grpc_proxy_requests_total metric")
});

static GRPC_PROXY_RESPONSES: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_grpc_proxy_responses_total",
        "Total gRPC proxy responses by success/failure",
        &["route_id", "success"]
    )
    .expect("Failed to create stoa_grpc_proxy_responses_total metric")
});

static GRPC_BRIDGE_REQUESTS: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_grpc_bridge_requests_total",
        "Total gRPC bridge tool invocations",
        &["method"]
    )
    .expect("Failed to create stoa_grpc_bridge_requests_total metric")
});

static GRPC_BRIDGE_RESPONSES: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_grpc_bridge_responses_total",
        "Total gRPC bridge tool responses by success/failure",
        &["method", "success"]
    )
    .expect("Failed to create stoa_grpc_bridge_responses_total metric")
});

pub fn track_grpc_proxy_request(route_id: &str) {
    GRPC_PROXY_REQUESTS.with_label_values(&[route_id]).inc();
}

pub fn track_grpc_proxy_response(route_id: &str, success: bool) {
    GRPC_PROXY_RESPONSES
        .with_label_values(&[route_id, if success { "true" } else { "false" }])
        .inc();
}

pub fn track_grpc_bridge_request(method: &str) {
    GRPC_BRIDGE_REQUESTS.with_label_values(&[method]).inc();
}

pub fn track_grpc_bridge_response(method: &str, success: bool) {
    GRPC_BRIDGE_RESPONSES
        .with_label_values(&[method, if success { "true" } else { "false" }])
        .inc();
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

// === Circuit Breaker metrics helpers ===

/// Update circuit breaker state for an upstream.
/// State values: 0 = closed, 1 = open, 2 = half_open
pub fn update_circuit_breaker_state(upstream: &str, state: f64) {
    CIRCUIT_BREAKER_STATE
        .with_label_values(&[upstream])
        .set(state);
}

// === Quota metrics helpers ===

/// Update remaining quota for a consumer.
pub fn update_quota_remaining(consumer: &str, period: &str, remaining: f64) {
    QUOTA_REMAINING
        .with_label_values(&[consumer, period])
        .set(remaining);
}

// === Guardrails metrics helpers ===

/// Record a PII detection event (action: "redacted" or "blocked").
pub fn record_guardrails_pii(action: &str) {
    GUARDRAILS_PII_DETECTED.with_label_values(&[action]).inc();
}

/// Record a prompt injection block event.
pub fn record_guardrails_injection(tool: &str) {
    GUARDRAILS_INJECTION_BLOCKED
        .with_label_values(&[tool])
        .inc();
}

/// Record a content filter event (CAB-1337 Phase 1).
/// action: "blocked" | "sensitive"
/// category: "financial" | "medical" | "violence" | "malware"
pub fn record_guardrails_content_filter(action: &str, category: &str) {
    GUARDRAILS_CONTENT_FILTERED
        .with_label_values(&[action, category])
        .inc();
}

// === Prompt Guard metrics helpers (CAB-1761) ===

/// Record a prompt guard detection event.
pub fn record_prompt_guard_detected(category: &str, action: &str) {
    PROMPT_GUARD_DETECTED
        .with_label_values(&[category, action])
        .inc();
}

/// Record a prompt guard scan result (pass or detected).
pub fn record_prompt_guard_scanned(result: &str) {
    PROMPT_GUARD_SCANNED.with_label_values(&[result]).inc();
}

// === RAG Injector metrics helpers (CAB-1761) ===

/// Record a RAG context injection attempt.
pub fn record_rag_injection(source: &str, result: &str) {
    RAG_INJECTIONS_TOTAL
        .with_label_values(&[source, result])
        .inc();
}

/// Record the duration of a RAG source fetch.
pub fn record_rag_fetch_duration(source: &str, duration_secs: f64) {
    RAG_FETCH_DURATION
        .with_label_values(&[source])
        .observe(duration_secs);
}

/// Record token consumption for a tenant.
pub fn record_token_budget_usage(tenant: &str, direction: &str, tokens: u64) {
    TOKEN_BUDGET_TOKENS_TOTAL
        .with_label_values(&[tenant, direction])
        .inc_by(tokens as f64);
}

/// Record a token budget exceeded event.
pub fn record_token_budget_exceeded(tenant: &str) {
    TOKEN_BUDGET_EXCEEDED_TOTAL
        .with_label_values(&[tenant])
        .inc();
}

// === Tool discovery metrics helpers ===

/// Record a tool discovery attempt with duration and result.
pub fn record_tool_discovery(tenant: &str, result: &str, duration_secs: f64) {
    TOOL_DISCOVERY_DURATION
        .with_label_values(&[tenant, result])
        .observe(duration_secs);
    if result != "success" {
        TOOL_DISCOVERY_FAILURES_TOTAL
            .with_label_values(&[tenant])
            .inc();
    }
}

// === Fallback metrics helpers ===

/// Record a fallback chain attempt for a tool.
pub fn record_fallback_attempt(tool: &str) {
    FALLBACK_ATTEMPTS.with_label_values(&[tool]).inc();
}

/// Record an exhausted fallback chain for a tool.
pub fn record_fallback_exhausted(tool: &str) {
    FALLBACK_EXHAUSTED.with_label_values(&[tool]).inc();
}

// === Upstream latency helpers ===

/// Record upstream (backend) response latency.
pub fn record_upstream_latency(upstream: &str, status: u16, duration_secs: f64) {
    let status_str = status.to_string();
    UPSTREAM_LATENCY
        .with_label_values(&[upstream, &status_str])
        .observe(duration_secs);
}

// === Federation metrics helpers ===

/// Record a federation request with sub-account, master account, and status.
pub fn record_federation_request(sub_account_id: &str, master_account_id: &str, status: &str) {
    FEDERATION_REQUESTS_TOTAL
        .with_label_values(&[sub_account_id, master_account_id, status])
        .inc();
}

// === DPoP metrics helpers ===

/// Record a DPoP validation outcome.
pub fn record_dpop_validation(result: &str) {
    DPOP_VALIDATIONS_TOTAL.with_label_values(&[result]).inc();
}

// === mTLS metrics helpers ===

/// Record an mTLS validation outcome.
pub fn record_mtls_validation(result: &str, tenant: &str) {
    MTLS_VALIDATIONS_TOTAL
        .with_label_values(&[result, tenant])
        .inc();
}

/// Record an RFC 8705 binding check outcome.
pub fn record_mtls_binding_check(result: &str) {
    MTLS_BINDING_CHECKS_TOTAL.with_label_values(&[result]).inc();
}

// === Sender-Constraint metrics helpers ===

/// Record a sender-constraint check outcome.
pub fn record_sender_constraint_check(result: &str, method: &str, tenant: &str) {
    SENDER_CONSTRAINT_CHECKS_TOTAL
        .with_label_values(&[result, method, tenant])
        .inc();
}

// === Profile Enforcement metrics helpers (CAB-1744) ===

/// Record a security profile enforcement check outcome.
pub fn record_profile_enforcement(result: &str, profile: &str) {
    PROFILE_ENFORCEMENT_TOTAL
        .with_label_values(&[result, profile])
        .inc();
}

// === API proxy metrics helpers (CAB-1726) ===

/// Record an API proxy request with backend, method, status, and duration.
pub fn record_api_proxy_request(backend: &str, method: &str, status: u16, duration_secs: f64) {
    let status_str = status.to_string();
    API_PROXY_REQUESTS_TOTAL
        .with_label_values(&[backend, method, &status_str])
        .inc();
    API_PROXY_DURATION
        .with_label_values(&[backend])
        .observe(duration_secs);
}

/// Record an API proxy rate limit rejection.
pub fn record_api_proxy_rate_limited(backend: &str) {
    API_PROXY_RATE_LIMITED.with_label_values(&[backend]).inc();
}

/// Record an API proxy circuit breaker rejection.
pub fn record_api_proxy_circuit_open(backend: &str) {
    API_PROXY_CIRCUIT_OPEN.with_label_values(&[backend]).inc();
}

// === HTTP metrics helpers ===

/// Record an HTTP request with method, path, status, and duration.
pub fn record_http_request(method: &str, path: &str, status: u16, duration_secs: f64) {
    let status_str = status.to_string();
    HTTP_REQUESTS_TOTAL
        .with_label_values(&[method, path, &status_str])
        .inc();
    HTTP_REQUEST_DURATION
        .with_label_values(&[method, path])
        .observe(duration_secs);
}

/// Normalize a request path to a low-cardinality label.
///
/// Replaces dynamic path segments (UUIDs, numeric IDs) with placeholders
/// to prevent label cardinality explosion in Prometheus.
pub fn normalize_path(path: &str) -> String {
    let segments: Vec<&str> = path.split('/').collect();
    let normalized: Vec<String> = segments
        .iter()
        .map(|s| {
            if s.is_empty() {
                String::new()
            } else if s.chars().all(|c| c.is_ascii_hexdigit() || c == '-') && s.len() >= 8 {
                // UUID-like or hex ID
                ":id".to_string()
            } else if s.chars().all(|c| c.is_ascii_digit()) && !s.is_empty() {
                // Numeric ID
                ":id".to_string()
            } else {
                s.to_string()
            }
        })
        .collect();
    let result = normalized.join("/");
    if result.is_empty() {
        "/".to_string()
    } else {
        result
    }
}

/// Force-initialize all Lazy metrics so they appear in /metrics output
/// even before any traffic arrives. Call this once at startup.
pub fn init_all_metrics() {
    // Touch each Lazy static to force registration with the global Prometheus registry
    Lazy::force(&HTTP_REQUESTS_TOTAL);
    Lazy::force(&HTTP_REQUEST_DURATION);
    Lazy::force(&MCP_TOOL_DURATION);
    Lazy::force(&MCP_TOOL_CALLS_TOTAL);
    Lazy::force(&MCP_SSE_CONNECTION_DURATION);
    Lazy::force(&MCP_SSE_CONNECTIONS_ACTIVE);
    Lazy::force(&MCP_SESSIONS_ACTIVE);
    Lazy::force(&RATE_LIMIT_HITS);
    Lazy::force(&RATE_LIMIT_BUCKETS);
    Lazy::force(&CIRCUIT_BREAKER_STATE);
    Lazy::force(&QUOTA_REMAINING);
    Lazy::force(&GUARDRAILS_PII_DETECTED);
    Lazy::force(&GUARDRAILS_INJECTION_BLOCKED);
    Lazy::force(&GUARDRAILS_CONTENT_FILTERED);
    Lazy::force(&TOKEN_BUDGET_TOKENS_TOTAL);
    Lazy::force(&TOKEN_BUDGET_EXCEEDED_TOTAL);
    Lazy::force(&TOOL_DISCOVERY_DURATION);
    Lazy::force(&TOOL_DISCOVERY_FAILURES_TOTAL);
    Lazy::force(&FALLBACK_ATTEMPTS);
    Lazy::force(&FALLBACK_EXHAUSTED);
    Lazy::force(&UPSTREAM_LATENCY);
    Lazy::force(&API_PROXY_REQUESTS_TOTAL);
    Lazy::force(&API_PROXY_DURATION);
    Lazy::force(&API_PROXY_RATE_LIMITED);
    Lazy::force(&API_PROXY_CIRCUIT_OPEN);
    Lazy::force(&MTLS_VALIDATIONS_TOTAL);
    Lazy::force(&MTLS_BINDING_CHECKS_TOTAL);
    Lazy::force(&MTLS_CERTS_EXPIRING_SOON);
    Lazy::force(&FEDERATION_REQUESTS_TOTAL);
    Lazy::force(&DPOP_VALIDATIONS_TOTAL);
    Lazy::force(&SENDER_CONSTRAINT_CHECKS_TOTAL);
    Lazy::force(&SUPERVISION_DECISIONS_TOTAL);
    Lazy::force(&HEGEMON_DISPATCHES_TOTAL);
    Lazy::force(&HEGEMON_DISPATCH_ACTIVE);
    Lazy::force(&HEGEMON_DISPATCH_DURATION);
    Lazy::force(&HEGEMON_DISPATCH_COST);
    Lazy::force(&HEGEMON_BUDGET_DAILY_USD);
}

/// Get the total number of MCP tool calls across all labels.
pub fn get_requests_total() -> u64 {
    use prometheus::core::Collector;
    let families = MCP_TOOL_CALLS_TOTAL.collect();
    let mut total = 0u64;
    for family in &families {
        for metric in family.get_metric() {
            total += metric.get_counter().get_value() as u64;
        }
    }
    total
}

/// Get the error rate (errors / total) across all MCP tool calls.
/// Returns 0.0 if no requests have been processed yet.
pub fn get_error_rate() -> f64 {
    use prometheus::core::Collector;
    let families = MCP_TOOL_CALLS_TOTAL.collect();
    let mut total = 0.0_f64;
    let mut errors = 0.0_f64;
    for family in &families {
        for metric in family.get_metric() {
            let val = metric.get_counter().get_value();
            total += val;
            // Convention: status label "error" or "failure" counts as error
            for label in metric.get_label() {
                if label.get_name() == "status" && label.get_value() != "success" {
                    errors += val;
                }
            }
        }
    }
    if total == 0.0 {
        0.0
    } else {
        errors / total
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_record_tool_call() {
        // Should not panic
        record_tool_call("test_tool", "tenant-1", "success", 0.05, "consumer-1");
    }

    #[test]
    fn test_sse_tracking() {
        track_sse_connect();
        track_sse_disconnect("tenant-1", 30.0);
    }

    #[test]
    fn test_get_requests_total() {
        // Record some calls and verify total is non-negative
        record_tool_call(
            "metric_test_tool",
            "metric-tenant",
            "success",
            0.01,
            "consumer-1",
        );
        let total = get_requests_total();
        assert!(total >= 1, "Expected at least 1 request, got {}", total);
    }

    #[test]
    fn test_get_error_rate_with_no_errors() {
        // Record only success calls
        record_tool_call(
            "rate_test_tool",
            "rate-tenant",
            "success",
            0.01,
            "consumer-1",
        );
        let rate = get_error_rate();
        // Rate should be between 0.0 and 1.0
        assert!(
            (0.0..=1.0).contains(&rate),
            "Error rate out of range: {}",
            rate
        );
    }

    #[test]
    fn test_get_error_rate_with_errors() {
        // Record both success and error calls
        record_tool_call("err_test_tool", "err-tenant", "success", 0.01, "consumer-1");
        record_tool_call("err_test_tool", "err-tenant", "error", 0.05, "consumer-1");
        let rate = get_error_rate();
        assert!(rate > 0.0, "Expected non-zero error rate, got {}", rate);
        assert!(rate <= 1.0, "Error rate out of range: {}", rate);
    }

    #[test]
    fn test_record_http_request() {
        // Should not panic
        record_http_request("GET", "/health", 200, 0.001);
        record_http_request("POST", "/mcp/tools/call", 200, 0.05);
        record_http_request("GET", "/mcp/tools/list", 401, 0.002);
    }

    #[test]
    fn test_normalize_path_static() {
        assert_eq!(normalize_path("/health"), "/health");
        assert_eq!(normalize_path("/mcp/tools/list"), "/mcp/tools/list");
        assert_eq!(normalize_path("/admin/apis"), "/admin/apis");
        assert_eq!(normalize_path("/metrics"), "/metrics");
    }

    #[test]
    fn test_normalize_path_uuid() {
        assert_eq!(
            normalize_path("/admin/apis/550e8400-e29b-41d4-a716-446655440000"),
            "/admin/apis/:id"
        );
        assert_eq!(
            normalize_path("/admin/quotas/abcdef12-3456-7890-abcd-ef1234567890/reset"),
            "/admin/quotas/:id/reset"
        );
    }

    #[test]
    fn test_normalize_path_numeric_id() {
        assert_eq!(normalize_path("/admin/apis/42"), "/admin/apis/:id");
        assert_eq!(
            normalize_path("/admin/circuit-breakers/12345/reset"),
            "/admin/circuit-breakers/:id/reset"
        );
    }

    #[test]
    fn test_normalize_path_root() {
        assert_eq!(normalize_path("/"), "/");
    }

    #[test]
    fn test_normalize_path_preserves_short_hex() {
        // Short segments that happen to be hex should NOT be normalized
        // (e.g., "mcp", "sse", "v1" are fine)
        assert_eq!(normalize_path("/mcp/v1/tools"), "/mcp/v1/tools");
        assert_eq!(normalize_path("/mcp/sse"), "/mcp/sse");
    }

    #[test]
    fn test_record_federation_request() {
        record_federation_request("sub-acct-1", "master-acct-1", "success");
        record_federation_request("sub-acct-1", "master-acct-1", "denied");
        record_federation_request("sub-acct-2", "master-acct-1", "rate_limited");
    }

    #[test]
    fn test_record_token_budget_usage() {
        record_token_budget_usage("tenant-budget-test", "input", 100);
        record_token_budget_usage("tenant-budget-test", "output", 50);
    }

    #[test]
    fn test_record_token_budget_exceeded() {
        record_token_budget_exceeded("tenant-exceeded-test");
    }

    #[test]
    fn test_init_all_metrics_no_panic() {
        // Should not panic — forces all Lazy statics to initialize
        init_all_metrics();
    }
}
