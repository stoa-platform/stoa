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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_record_diagnostic_all_categories() {
        // Verify that record_diagnostic maps every ErrorCategory variant
        // to a Prometheus label without panicking.
        let categories = [
            ErrorCategory::Auth,
            ErrorCategory::Network,
            ErrorCategory::Backend,
            ErrorCategory::Timeout,
            ErrorCategory::Policy,
            ErrorCategory::RateLimit,
            ErrorCategory::Certificate,
            ErrorCategory::Unknown,
        ];
        for category in &categories {
            record_diagnostic(category);
        }
    }

    #[test]
    fn test_record_diagnostic_increments_counter() {
        // Record twice for the same category and verify the counter increases.
        let before = DIAGNOSTICS_TOTAL.with_label_values(&["auth"]).get();
        record_diagnostic(&ErrorCategory::Auth);
        record_diagnostic(&ErrorCategory::Auth);
        let after = DIAGNOSTICS_TOTAL.with_label_values(&["auth"]).get();
        assert!(after >= before + 2.0);
    }

    #[test]
    fn test_reexports_are_accessible() {
        // Verify all public re-exports from sub-modules are accessible.
        let _engine = DiagnosticEngine::new(100);
        let _hop = Hop {
            name: "test".to_string(),
            address: None,
            latency_ms: Some(1.0),
            hop_type: HopType::Gateway,
        };
        let _chain = HopChain {
            hops: vec![],
            total_detected: 0,
            total_latency_ms: None,
        };
        let _detector = HopDetector;
        let _tracker = LatencyTracker::new();
        let _category = ErrorCategory::Auth;
    }
}
