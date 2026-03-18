//! Observability — Error Snapshot Capture (CAB-1645)
//!
//! Opt-in system that captures PII-masked body excerpts + sanitized headers
//! for 5xx responses, retrievable via admin API.
//! Separate from diagnostics/ (GDPR-safe metadata only).

pub mod capture;
pub mod snapshot;

pub use snapshot::SnapshotStore;

use once_cell::sync::Lazy;
use prometheus::{register_counter, register_int_gauge, Counter, IntGauge};

/// Counter of snapshots captured.
pub static SNAPSHOTS_CAPTURED_TOTAL: Lazy<Counter> = Lazy::new(|| {
    register_counter!(
        "stoa_snapshots_captured_total",
        "Total error snapshots captured"
    )
    .expect("Failed to create stoa_snapshots_captured_total metric")
});

/// Gauge of current snapshot store size.
pub static SNAPSHOT_STORE_SIZE: Lazy<IntGauge> = Lazy::new(|| {
    register_int_gauge!(
        "stoa_snapshot_store_size",
        "Current number of snapshots in the store"
    )
    .expect("Failed to create stoa_snapshot_store_size metric")
});

/// Counter of snapshots evicted (TTL expiry or capacity overflow).
pub static SNAPSHOTS_EVICTED_TOTAL: Lazy<Counter> = Lazy::new(|| {
    register_counter!(
        "stoa_snapshots_evicted_total",
        "Total snapshots evicted from store"
    )
    .expect("Failed to create stoa_snapshots_evicted_total metric")
});

/// Record a snapshot capture event.
pub fn record_snapshot_captured() {
    SNAPSHOTS_CAPTURED_TOTAL.inc();
}

/// Update the store size gauge.
pub fn update_store_size(size: usize) {
    SNAPSHOT_STORE_SIZE.set(size as i64);
}

/// Record eviction events.
pub fn record_evictions(count: usize) {
    SNAPSHOTS_EVICTED_TOTAL.inc_by(count as f64);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_metrics_register_without_panic() {
        record_snapshot_captured();
        update_store_size(5);
        record_evictions(2);
    }

    #[test]
    fn test_metrics_increment() {
        let before = SNAPSHOTS_CAPTURED_TOTAL.get();
        record_snapshot_captured();
        record_snapshot_captured();
        let after = SNAPSHOTS_CAPTURED_TOTAL.get();
        assert!(after >= before + 2.0);
    }

    #[test]
    fn test_store_size_gauge() {
        update_store_size(42);
        assert_eq!(SNAPSHOT_STORE_SIZE.get(), 42);
    }
}
