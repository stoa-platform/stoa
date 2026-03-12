//! Latency Attribution (CAB-1316 Phase 2)
//!
//! Captures checkpoint timestamps at each processing stage and attributes
//! latency to: auth, policy evaluation, backend call, and serialization.

use std::sync::{Arc, Mutex};
use std::time::Instant;

use serde::{Deserialize, Serialize};

/// Named processing stage for latency attribution.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Stage {
    Auth,
    PolicyEval,
    BackendCall,
    Serialization,
    Total,
    /// Per-layer stages for multi-span tracing (CAB-1790)
    Transport,
    Identity,
    Routing,
    Quota,
    Supervision,
}

impl std::fmt::Display for Stage {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Auth => write!(f, "auth"),
            Self::PolicyEval => write!(f, "policy_eval"),
            Self::BackendCall => write!(f, "backend_call"),
            Self::Serialization => write!(f, "serialization"),
            Self::Total => write!(f, "total"),
            Self::Transport => write!(f, "transport"),
            Self::Identity => write!(f, "identity"),
            Self::Routing => write!(f, "routing"),
            Self::Quota => write!(f, "quota"),
            Self::Supervision => write!(f, "supervision"),
        }
    }
}

/// A single checkpoint recording stage name and elapsed time.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Checkpoint {
    pub stage: Stage,
    pub duration_ms: f64,
}

/// Timing breakdown with per-stage durations.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct TimingBreakdown {
    pub auth_ms: Option<f64>,
    pub policy_eval_ms: Option<f64>,
    pub backend_ms: Option<f64>,
    pub serialization_ms: Option<f64>,
    pub total_ms: f64,
    pub checkpoints: Vec<Checkpoint>,
    /// Per-layer timings for multi-span tracing (CAB-1790)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub transport_ms: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub identity_ms: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub routing_ms: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub quota_ms: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub supervision_ms: Option<f64>,
}

/// Identifies a stage that consumed a disproportionate amount of total latency.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LatencyOutlier {
    pub stage: Stage,
    pub duration_ms: f64,
    pub percentage: f64,
}

/// Tracks timing checkpoints during request processing and produces a breakdown.
#[derive(Debug)]
pub struct LatencyTracker {
    start: Instant,
    checkpoints: Vec<(Stage, Instant, Instant)>,
    current_stage: Option<(Stage, Instant)>,
    overrides: Vec<(Stage, f64)>,
}

impl LatencyTracker {
    /// Create a new tracker starting now.
    pub fn new() -> Self {
        Self {
            start: Instant::now(),
            checkpoints: Vec::new(),
            current_stage: None,
            overrides: Vec::new(),
        }
    }

    /// Begin timing a new stage.
    pub fn begin_stage(&mut self, stage: Stage) {
        // Auto-close any open stage
        if let Some((prev_stage, prev_start)) = self.current_stage.take() {
            self.checkpoints
                .push((prev_stage, prev_start, Instant::now()));
        }
        self.current_stage = Some((stage, Instant::now()));
    }

    /// End the current stage.
    pub fn end_stage(&mut self) {
        if let Some((stage, start)) = self.current_stage.take() {
            self.checkpoints.push((stage, start, Instant::now()));
        }
    }

    /// Record a completed stage with a pre-measured duration.
    ///
    /// Use this when the caller already measured timing externally
    /// (e.g., from HTTP headers or upstream telemetry). The duration
    /// is stored in `overrides` and merged during `finalize()`.
    pub fn record_stage(&mut self, stage: Stage, duration_ms: f64) {
        self.overrides.push((stage, duration_ms));
    }

    /// Finalize the tracker and produce a timing breakdown.
    pub fn finalize(&mut self) -> TimingBreakdown {
        // Close any open stage
        self.end_stage();

        let total_ms = self.start.elapsed().as_secs_f64() * 1000.0;

        let mut auth_ms = None;
        let mut policy_ms = None;
        let mut backend_ms = None;
        let mut serialization_ms = None;
        let mut transport_ms = None;
        let mut identity_ms = None;
        let mut routing_ms = None;
        let mut quota_ms = None;
        let mut supervision_ms = None;
        let mut checkpoints = Vec::new();

        // Helper macro to accumulate optional durations
        macro_rules! accum {
            ($field:ident, $dur:expr) => {
                $field = Some($field.unwrap_or(0.0) + $dur)
            };
        }

        for (stage, start, end) in &self.checkpoints {
            let dur = end.duration_since(*start).as_secs_f64() * 1000.0;
            match stage {
                Stage::Auth => accum!(auth_ms, dur),
                Stage::PolicyEval => accum!(policy_ms, dur),
                Stage::BackendCall => accum!(backend_ms, dur),
                Stage::Serialization => accum!(serialization_ms, dur),
                Stage::Transport => accum!(transport_ms, dur),
                Stage::Identity => accum!(identity_ms, dur),
                Stage::Routing => accum!(routing_ms, dur),
                Stage::Quota => accum!(quota_ms, dur),
                Stage::Supervision => accum!(supervision_ms, dur),
                Stage::Total => {}
            }
            checkpoints.push(Checkpoint {
                stage: *stage,
                duration_ms: dur,
            });
        }

        // Merge externally measured durations from record_stage()
        for (stage, dur) in &self.overrides {
            match stage {
                Stage::Auth => accum!(auth_ms, *dur),
                Stage::PolicyEval => accum!(policy_ms, *dur),
                Stage::BackendCall => accum!(backend_ms, *dur),
                Stage::Serialization => accum!(serialization_ms, *dur),
                Stage::Transport => accum!(transport_ms, *dur),
                Stage::Identity => accum!(identity_ms, *dur),
                Stage::Routing => accum!(routing_ms, *dur),
                Stage::Quota => accum!(quota_ms, *dur),
                Stage::Supervision => accum!(supervision_ms, *dur),
                Stage::Total => {}
            }
            checkpoints.push(Checkpoint {
                stage: *stage,
                duration_ms: *dur,
            });
        }

        TimingBreakdown {
            auth_ms,
            policy_eval_ms: policy_ms,
            backend_ms,
            serialization_ms,
            total_ms,
            checkpoints,
            transport_ms,
            identity_ms,
            routing_ms,
            quota_ms,
            supervision_ms,
        }
    }

    /// Detect outliers: stages consuming > threshold% of total latency.
    pub fn detect_outliers(breakdown: &TimingBreakdown, threshold_pct: f64) -> Vec<LatencyOutlier> {
        if breakdown.total_ms <= 0.0 {
            return Vec::new();
        }

        let mut outliers = Vec::new();
        let stages = [
            (Stage::Auth, breakdown.auth_ms),
            (Stage::PolicyEval, breakdown.policy_eval_ms),
            (Stage::BackendCall, breakdown.backend_ms),
            (Stage::Serialization, breakdown.serialization_ms),
            (Stage::Transport, breakdown.transport_ms),
            (Stage::Identity, breakdown.identity_ms),
            (Stage::Routing, breakdown.routing_ms),
            (Stage::Quota, breakdown.quota_ms),
            (Stage::Supervision, breakdown.supervision_ms),
        ];

        for (stage, duration_opt) in stages {
            if let Some(dur) = duration_opt {
                let pct = (dur / breakdown.total_ms) * 100.0;
                if pct > threshold_pct {
                    outliers.push(LatencyOutlier {
                        stage,
                        duration_ms: dur,
                        percentage: pct,
                    });
                }
            }
        }

        outliers
    }
}

impl Default for LatencyTracker {
    fn default() -> Self {
        Self::new()
    }
}

/// Thread-safe wrapper for passing `LatencyTracker` through request extensions.
///
/// Inserted by `access_log_middleware` before `next.run()`, each downstream
/// middleware calls `begin_stage()`/`end_stage()` through the mutex.
/// On the response path, `access_log_middleware` finalizes the tracker and
/// serializes to a `Server-Timing` response header.
pub type SharedTracker = Arc<Mutex<LatencyTracker>>;

/// Create a new shared tracker for use as a request extension.
pub fn new_shared_tracker() -> SharedTracker {
    Arc::new(Mutex::new(LatencyTracker::new()))
}

/// Serialize a `TimingBreakdown` into a `Server-Timing` header value.
///
/// Format per RFC 7231 / W3C Server-Timing spec:
///   `stage;dur=12.34, stage2;dur=5.67`
///
/// Only includes stages with measured durations (skips None values).
pub fn to_server_timing(breakdown: &TimingBreakdown) -> String {
    let mut parts = Vec::new();

    let stages: &[(&str, Option<f64>)] = &[
        ("identity", breakdown.identity_ms),
        ("auth", breakdown.auth_ms),
        ("quota", breakdown.quota_ms),
        ("supervision", breakdown.supervision_ms),
        ("policy_eval", breakdown.policy_eval_ms),
        ("routing", breakdown.routing_ms),
        ("backend_call", breakdown.backend_ms),
        ("serialization", breakdown.serialization_ms),
        ("transport", breakdown.transport_ms),
        ("total", Some(breakdown.total_ms)),
    ];

    for (name, duration) in stages {
        if let Some(dur) = duration {
            parts.push(format!("{};dur={:.2}", name, dur));
        }
    }

    parts.join(", ")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tracker_new_starts_cleanly() {
        let tracker = LatencyTracker::new();
        assert!(tracker.checkpoints.is_empty());
        assert!(tracker.current_stage.is_none());
    }

    #[test]
    fn begin_and_end_stage() {
        let mut tracker = LatencyTracker::new();
        tracker.begin_stage(Stage::Auth);
        std::thread::sleep(std::time::Duration::from_millis(5));
        tracker.end_stage();

        assert_eq!(tracker.checkpoints.len(), 1);
        assert_eq!(tracker.checkpoints[0].0, Stage::Auth);
    }

    #[test]
    fn auto_close_on_new_begin() {
        let mut tracker = LatencyTracker::new();
        tracker.begin_stage(Stage::Auth);
        tracker.begin_stage(Stage::PolicyEval);
        tracker.end_stage();

        // Auth was auto-closed when PolicyEval began
        assert_eq!(tracker.checkpoints.len(), 2);
        assert_eq!(tracker.checkpoints[0].0, Stage::Auth);
        assert_eq!(tracker.checkpoints[1].0, Stage::PolicyEval);
    }

    #[test]
    fn finalize_produces_breakdown() {
        let mut tracker = LatencyTracker::new();
        tracker.begin_stage(Stage::Auth);
        std::thread::sleep(std::time::Duration::from_millis(2));
        tracker.end_stage();
        tracker.begin_stage(Stage::BackendCall);
        std::thread::sleep(std::time::Duration::from_millis(5));
        tracker.end_stage();

        let breakdown = tracker.finalize();
        assert!(breakdown.total_ms > 0.0);
        assert!(breakdown.auth_ms.is_some());
        assert!(breakdown.backend_ms.is_some());
        assert!(breakdown.policy_eval_ms.is_none());
    }

    #[test]
    fn finalize_auto_closes_open_stage() {
        let mut tracker = LatencyTracker::new();
        tracker.begin_stage(Stage::Serialization);
        // Don't end it — finalize should auto-close
        let breakdown = tracker.finalize();
        assert!(breakdown.serialization_ms.is_some());
    }

    #[test]
    fn detect_outliers_finds_dominant_stage() {
        let breakdown = TimingBreakdown {
            auth_ms: Some(5.0),
            policy_eval_ms: Some(2.0),
            backend_ms: Some(90.0),
            serialization_ms: Some(3.0),
            total_ms: 100.0,
            ..TimingBreakdown::default()
        };

        let outliers = LatencyTracker::detect_outliers(&breakdown, 80.0);
        assert_eq!(outliers.len(), 1);
        assert_eq!(outliers[0].stage, Stage::BackendCall);
        assert!(outliers[0].percentage > 80.0);
    }

    #[test]
    fn detect_outliers_empty_on_balanced() {
        let breakdown = TimingBreakdown {
            auth_ms: Some(25.0),
            policy_eval_ms: Some(25.0),
            backend_ms: Some(25.0),
            serialization_ms: Some(25.0),
            total_ms: 100.0,
            ..TimingBreakdown::default()
        };

        let outliers = LatencyTracker::detect_outliers(&breakdown, 80.0);
        assert!(outliers.is_empty());
    }

    #[test]
    fn detect_outliers_zero_total_returns_empty() {
        let outliers = LatencyTracker::detect_outliers(&TimingBreakdown::default(), 80.0);
        assert!(outliers.is_empty());
    }

    #[test]
    fn multiple_stages_of_same_type_are_summed() {
        let mut tracker = LatencyTracker::new();

        tracker.begin_stage(Stage::Auth);
        std::thread::sleep(std::time::Duration::from_millis(2));
        tracker.end_stage();
        tracker.begin_stage(Stage::Auth);
        std::thread::sleep(std::time::Duration::from_millis(2));
        tracker.end_stage();

        let breakdown = tracker.finalize();
        // Both Auth checkpoints should be summed
        assert!(breakdown.auth_ms.unwrap_or(0.0) > 2.0);
    }

    #[test]
    fn stage_display_names() {
        assert_eq!(Stage::Auth.to_string(), "auth");
        assert_eq!(Stage::PolicyEval.to_string(), "policy_eval");
        assert_eq!(Stage::BackendCall.to_string(), "backend_call");
        assert_eq!(Stage::Serialization.to_string(), "serialization");
        assert_eq!(Stage::Total.to_string(), "total");
        assert_eq!(Stage::Transport.to_string(), "transport");
        assert_eq!(Stage::Identity.to_string(), "identity");
        assert_eq!(Stage::Routing.to_string(), "routing");
        assert_eq!(Stage::Quota.to_string(), "quota");
        assert_eq!(Stage::Supervision.to_string(), "supervision");
    }

    #[test]
    fn checkpoint_serializes_to_json() {
        let cp = Checkpoint {
            stage: Stage::Auth,
            duration_ms: 12.5,
        };
        let json = serde_json::to_string(&cp).expect("serialize");
        assert!(json.contains("auth"));
        assert!(json.contains("12.5"));
    }

    #[test]
    fn timing_breakdown_serializes() {
        let tb = TimingBreakdown {
            auth_ms: Some(5.0),
            backend_ms: Some(50.0),
            total_ms: 60.0,
            ..TimingBreakdown::default()
        };
        let json = serde_json::to_string(&tb).expect("serialize");
        assert!(json.contains("auth_ms"));
        assert!(json.contains("backend_ms"));
        assert!(json.contains("total_ms"));
        // New fields with None are skipped (skip_serializing_if)
        assert!(!json.contains("transport_ms"));
    }

    #[test]
    fn default_tracker_works() {
        let tracker = LatencyTracker::default();
        assert!(tracker.checkpoints.is_empty());
    }

    #[test]
    fn server_timing_header_format() {
        let breakdown = TimingBreakdown {
            auth_ms: Some(5.50),
            quota_ms: Some(0.12),
            backend_ms: Some(42.00),
            total_ms: 50.00,
            ..TimingBreakdown::default()
        };
        let header = to_server_timing(&breakdown);
        assert!(header.contains("auth;dur=5.50"));
        assert!(header.contains("quota;dur=0.12"));
        assert!(header.contains("backend_call;dur=42.00"));
        assert!(header.contains("total;dur=50.00"));
        // Stages with None are not included
        assert!(!header.contains("identity"));
        assert!(!header.contains("transport"));
    }

    #[test]
    fn server_timing_empty_breakdown() {
        let breakdown = TimingBreakdown::default();
        let header = to_server_timing(&breakdown);
        // Only total (0.00) should be present
        assert_eq!(header, "total;dur=0.00");
    }

    #[test]
    fn shared_tracker_can_be_cloned_and_used() {
        let tracker = new_shared_tracker();
        let clone = tracker.clone();

        {
            let mut t = tracker.lock().expect("lock");
            t.begin_stage(Stage::Identity);
        }
        std::thread::sleep(std::time::Duration::from_millis(2));
        {
            let mut t = clone.lock().expect("lock");
            t.end_stage();
            let breakdown = t.finalize();
            assert!(breakdown.identity_ms.is_some());
        }
    }

    #[test]
    fn new_stages_tracked_in_finalize() {
        let mut tracker = LatencyTracker::new();
        tracker.begin_stage(Stage::Identity);
        std::thread::sleep(std::time::Duration::from_millis(2));
        tracker.end_stage();
        tracker.begin_stage(Stage::Quota);
        std::thread::sleep(std::time::Duration::from_millis(2));
        tracker.end_stage();
        tracker.begin_stage(Stage::Supervision);
        std::thread::sleep(std::time::Duration::from_millis(2));
        tracker.end_stage();

        let breakdown = tracker.finalize();
        assert!(breakdown.identity_ms.is_some());
        assert!(breakdown.quota_ms.is_some());
        assert!(breakdown.supervision_ms.is_some());
        assert!(breakdown.transport_ms.is_none());
        assert!(breakdown.routing_ms.is_none());
    }
}
