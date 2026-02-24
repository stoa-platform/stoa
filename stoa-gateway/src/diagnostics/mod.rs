//! Self-Diagnostic Engine (CAB-1316)
//!
//! Error classification taxonomy, auto-RCA, hop detection, and latency attribution.
//! GDPR-compliant: only headers + timing + error codes, no request/response payloads.

pub mod engine;
pub mod hops;
pub mod latency;
pub mod taxonomy;

pub use engine::{DiagnosticEngine, DiagnosticReport};
pub use hops::{Hop, HopChain, HopDetector, HopType};
pub use latency::{LatencyOutlier, LatencyTracker, TimingBreakdown};
pub use taxonomy::ErrorCategory;

use once_cell::sync::Lazy;
use prometheus::{register_counter_vec, register_histogram, CounterVec, Histogram};

/// Counter of diagnostic reports by error category.
static DIAGNOSTICS_TOTAL: Lazy<CounterVec> = Lazy::new(|| {
    register_counter_vec!(
        "stoa_diagnostics_total",
        "Total diagnostic reports by error category",
        &["category"]
    )
    .expect("Failed to create stoa_diagnostics_total metric")
});

/// Histogram of auto-RCA processing latency in seconds.
static DIAGNOSTICS_RCA_LATENCY: Lazy<Histogram> = Lazy::new(|| {
    register_histogram!(
        "stoa_diagnostics_rca_latency_seconds",
        "Latency of auto-RCA diagnostic processing",
        vec![0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1]
    )
    .expect("Failed to create stoa_diagnostics_rca_latency_seconds metric")
});

/// Record a diagnostic event for Prometheus.
fn record_diagnostic(category: &ErrorCategory) {
    let label = match category {
        ErrorCategory::Auth => "auth",
        ErrorCategory::Network => "network",
        ErrorCategory::Backend => "backend",
        ErrorCategory::Timeout => "timeout",
        ErrorCategory::Policy => "policy",
        ErrorCategory::RateLimit => "rate_limit",
        ErrorCategory::Certificate => "certificate",
        ErrorCategory::Unknown => "unknown",
    };
    DIAGNOSTICS_TOTAL.with_label_values(&[label]).inc();
}
