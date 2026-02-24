//! Latency Attribution (CAB-1316 Phase 2)
//!
//! Captures checkpoint timestamps at each processing stage and attributes
//! latency to: auth, policy evaluation, backend call, and serialization.

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
}

impl std::fmt::Display for Stage {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Auth => write!(f, "auth"),
            Self::PolicyEval => write!(f, "policy_eval"),
            Self::BackendCall => write!(f, "backend_call"),
            Self::Serialization => write!(f, "serialization"),
            Self::Total => write!(f, "total"),
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
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TimingBreakdown {
    pub auth_ms: Option<f64>,
    pub policy_eval_ms: Option<f64>,
    pub backend_ms: Option<f64>,
    pub serialization_ms: Option<f64>,
    pub total_ms: f64,
    pub checkpoints: Vec<Checkpoint>,
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
        let mut checkpoints = Vec::new();

        for (stage, start, end) in &self.checkpoints {
            let dur = end.duration_since(*start).as_secs_f64() * 1000.0;
            match stage {
                Stage::Auth => auth_ms = Some(auth_ms.unwrap_or(0.0) + dur),
                Stage::PolicyEval => policy_ms = Some(policy_ms.unwrap_or(0.0) + dur),
                Stage::BackendCall => backend_ms = Some(backend_ms.unwrap_or(0.0) + dur),
                Stage::Serialization => {
                    serialization_ms = Some(serialization_ms.unwrap_or(0.0) + dur)
                }
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
                Stage::Auth => auth_ms = Some(auth_ms.unwrap_or(0.0) + dur),
                Stage::PolicyEval => policy_ms = Some(policy_ms.unwrap_or(0.0) + dur),
                Stage::BackendCall => backend_ms = Some(backend_ms.unwrap_or(0.0) + dur),
                Stage::Serialization => {
                    serialization_ms = Some(serialization_ms.unwrap_or(0.0) + dur)
                }
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
            checkpoints: Vec::new(),
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
            checkpoints: Vec::new(),
        };

        let outliers = LatencyTracker::detect_outliers(&breakdown, 80.0);
        assert!(outliers.is_empty());
    }

    #[test]
    fn detect_outliers_zero_total_returns_empty() {
        let breakdown = TimingBreakdown {
            auth_ms: None,
            policy_eval_ms: None,
            backend_ms: None,
            serialization_ms: None,
            total_ms: 0.0,
            checkpoints: Vec::new(),
        };

        let outliers = LatencyTracker::detect_outliers(&breakdown, 80.0);
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
            policy_eval_ms: None,
            backend_ms: Some(50.0),
            serialization_ms: None,
            total_ms: 60.0,
            checkpoints: vec![],
        };
        let json = serde_json::to_string(&tb).expect("serialize");
        assert!(json.contains("auth_ms"));
        assert!(json.contains("backend_ms"));
        assert!(json.contains("total_ms"));
    }

    #[test]
    fn default_tracker_works() {
        let tracker = LatencyTracker::default();
        assert!(tracker.checkpoints.is_empty());
    }
}
