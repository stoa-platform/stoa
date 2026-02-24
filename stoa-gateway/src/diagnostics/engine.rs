//! Diagnostic Engine (CAB-1316 Phase 1)
//!
//! Processes failed requests, correlates error type + timing + headers
//! to determine root cause. GDPR-compliant: no request/response payloads.

use std::collections::HashMap;
use std::sync::Arc;
use std::time::Instant;

use parking_lot::RwLock;
use serde::{Deserialize, Serialize};

use super::hops::{HopChain, HopDetector, HopHeaders};
use super::latency::{LatencyOutlier, LatencyTracker, TimingBreakdown};
use super::taxonomy::ErrorCategory;

/// GDPR-safe request summary for diagnostic reports.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RequestMeta {
    pub request_id: String,
    pub method: String,
    pub path: String,
    pub status_code: u16,
    pub timestamp: String,
}

/// A classified root cause with evidence and confidence.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RootCause {
    pub category: ErrorCategory,
    pub confidence: f64,
    pub description: String,
    pub evidence: Vec<String>,
    pub suggested_action: String,
}

/// Full diagnostic report for a failed request.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DiagnosticReport {
    pub request_id: String,
    pub error_category: ErrorCategory,
    pub root_cause: RootCause,
    pub hop_chain: HopChain,
    pub timing: TimingBreakdown,
    pub outliers: Vec<LatencyOutlier>,
    pub request_meta: RequestMeta,
    pub redacted: bool,
}

/// Input data for a diagnostic analysis.
pub struct DiagnosticInput {
    pub request_id: String,
    pub method: String,
    pub path: String,
    pub status_code: u16,
    pub error_message: Option<String>,
    pub hop_headers: HopHeaders,
    pub timing: TimingBreakdown,
    pub timestamp: String,
}

/// In-memory ring buffer for recent diagnostic reports.
struct ReportBuffer {
    reports: Vec<DiagnosticReport>,
    capacity: usize,
    next_index: usize,
}

impl ReportBuffer {
    fn new(capacity: usize) -> Self {
        Self {
            reports: Vec::with_capacity(capacity),
            capacity,
            next_index: 0,
        }
    }

    fn push(&mut self, report: DiagnosticReport) {
        if self.reports.len() < self.capacity {
            self.reports.push(report);
        } else {
            self.reports[self.next_index] = report;
        }
        self.next_index = (self.next_index + 1) % self.capacity;
    }

    fn get(&self, request_id: &str) -> Option<&DiagnosticReport> {
        self.reports.iter().find(|r| r.request_id == request_id)
    }

    fn recent(&self, limit: usize) -> Vec<&DiagnosticReport> {
        // Return most recent reports, newest first
        let len = self.reports.len();
        if len == 0 {
            return Vec::new();
        }
        let mut result = Vec::with_capacity(limit.min(len));
        let mut idx = if self.next_index == 0 {
            len.saturating_sub(1)
        } else {
            self.next_index - 1
        };
        for _ in 0..limit.min(len) {
            result.push(&self.reports[idx]);
            if idx == 0 {
                idx = len.saturating_sub(1);
            } else {
                idx -= 1;
            }
        }
        result
    }

    fn summary(&self) -> HashMap<ErrorCategory, usize> {
        let mut counts = HashMap::new();
        for report in &self.reports {
            *counts.entry(report.error_category).or_insert(0) += 1;
        }
        counts
    }
}

/// The main diagnostic engine.
pub struct DiagnosticEngine {
    buffer: Arc<RwLock<ReportBuffer>>,
    /// Outlier detection threshold (% of total latency).
    outlier_threshold_pct: f64,
}

impl DiagnosticEngine {
    /// Create a new engine with the given report buffer capacity.
    pub fn new(buffer_capacity: usize) -> Self {
        Self {
            buffer: Arc::new(RwLock::new(ReportBuffer::new(buffer_capacity))),
            outlier_threshold_pct: 80.0,
        }
    }

    /// Process a failed request and store the diagnostic report.
    pub fn diagnose(&self, input: DiagnosticInput) -> DiagnosticReport {
        let rca_start = Instant::now();
        let category =
            ErrorCategory::classify(Some(input.status_code), input.error_message.as_deref());

        let confidence = Self::compute_confidence(&category, &input);

        let root_cause = RootCause {
            category,
            confidence,
            description: Self::build_description(&category, &input),
            evidence: Self::build_evidence(&input),
            suggested_action: category.suggested_action().to_string(),
        };

        let hop_chain = HopDetector::detect(&input.hop_headers);
        let outliers = LatencyTracker::detect_outliers(&input.timing, self.outlier_threshold_pct);

        let report = DiagnosticReport {
            request_id: input.request_id.clone(),
            error_category: category,
            root_cause,
            hop_chain,
            timing: input.timing,
            outliers,
            request_meta: RequestMeta {
                request_id: input.request_id,
                method: input.method,
                path: input.path,
                status_code: input.status_code,
                timestamp: input.timestamp,
            },
            redacted: true,
        };

        self.buffer.write().push(report.clone());

        // Record Prometheus metrics
        super::record_diagnostic(&category);
        super::DIAGNOSTICS_RCA_LATENCY.observe(rca_start.elapsed().as_secs_f64());

        report
    }

    /// Look up a stored report by request ID.
    pub fn get_report(&self, request_id: &str) -> Option<DiagnosticReport> {
        self.buffer.read().get(request_id).cloned()
    }

    /// Get the most recent diagnostic reports.
    pub fn recent_reports(&self, limit: usize) -> Vec<DiagnosticReport> {
        self.buffer
            .read()
            .recent(limit)
            .into_iter()
            .cloned()
            .collect()
    }

    /// Get aggregated error category summary.
    pub fn summary(&self) -> HashMap<ErrorCategory, usize> {
        self.buffer.read().summary()
    }

    /// Compute confidence based on how specific the evidence is.
    fn compute_confidence(category: &ErrorCategory, input: &DiagnosticInput) -> f64 {
        let base = category.default_confidence();

        // Boost confidence if message explicitly matches the category
        if let Some(ref msg) = input.error_message {
            let lower = msg.to_lowercase();
            let has_explicit_match = match category {
                ErrorCategory::Auth => {
                    lower.contains("jwt") || lower.contains("token") || lower.contains("auth")
                }
                ErrorCategory::Network => {
                    lower.contains("dns") || lower.contains("connection refused")
                }
                ErrorCategory::Backend => lower.contains("upstream") || lower.contains("backend"),
                ErrorCategory::Timeout => lower.contains("timeout") || lower.contains("timed out"),
                ErrorCategory::Policy => lower.contains("policy") || lower.contains("guardrail"),
                ErrorCategory::RateLimit => {
                    lower.contains("rate") || lower.contains("quota") || lower.contains("throttl")
                }
                ErrorCategory::Certificate => {
                    lower.contains("certificate") || lower.contains("tls") || lower.contains("ssl")
                }
                ErrorCategory::Unknown => false,
            };
            if has_explicit_match {
                return (base + 0.10).min(0.99);
            }
        }

        base
    }

    /// Build a human-readable description of the root cause.
    fn build_description(category: &ErrorCategory, input: &DiagnosticInput) -> String {
        let base = match category {
            ErrorCategory::Auth => "Authentication or authorization failure",
            ErrorCategory::Network => "Network connectivity failure",
            ErrorCategory::Backend => "Backend service error",
            ErrorCategory::Timeout => "Request processing timed out",
            ErrorCategory::Policy => "Request denied by policy engine",
            ErrorCategory::RateLimit => "Rate limit or quota exceeded",
            ErrorCategory::Certificate => "TLS/certificate error",
            ErrorCategory::Unknown => "Unclassified error",
        };
        if let Some(ref msg) = input.error_message {
            format!("{}: {}", base, msg)
        } else {
            format!("{} (HTTP {})", base, input.status_code)
        }
    }

    /// Collect evidence for the diagnostic report.
    fn build_evidence(input: &DiagnosticInput) -> Vec<String> {
        let mut evidence = Vec::new();
        evidence.push(format!(
            "HTTP {} {} -> {}",
            input.method, input.path, input.status_code
        ));
        if let Some(ref msg) = input.error_message {
            evidence.push(format!("Error: {}", msg));
        }
        if input.timing.total_ms > 0.0 {
            evidence.push(format!("Total latency: {:.1}ms", input.timing.total_ms));
        }
        evidence
    }
}

impl Default for DiagnosticEngine {
    fn default() -> Self {
        Self::new(1000)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::diagnostics::latency::TimingBreakdown;

    fn make_input(status: u16, msg: Option<&str>) -> DiagnosticInput {
        DiagnosticInput {
            request_id: format!("req-{}", status),
            method: "POST".into(),
            path: "/api/tools/call".into(),
            status_code: status,
            error_message: msg.map(String::from),
            hop_headers: HopHeaders::default(),
            timing: TimingBreakdown {
                auth_ms: Some(2.0),
                policy_eval_ms: Some(1.0),
                backend_ms: Some(50.0),
                serialization_ms: Some(1.0),
                total_ms: 54.0,
                checkpoints: vec![],
            },
            timestamp: "2026-02-24T12:00:00Z".into(),
        }
    }

    #[test]
    fn diagnose_auth_error() {
        let engine = DiagnosticEngine::new(10);
        let report = engine.diagnose(make_input(401, Some("JWT expired")));
        assert_eq!(report.error_category, ErrorCategory::Auth);
        assert!(report.root_cause.confidence > 0.8);
        assert!(report.root_cause.description.contains("JWT expired"));
        assert!(report.redacted);
    }

    #[test]
    fn diagnose_rate_limit() {
        let engine = DiagnosticEngine::new(10);
        let report = engine.diagnose(make_input(429, Some("rate limit exceeded")));
        assert_eq!(report.error_category, ErrorCategory::RateLimit);
        assert!(report.root_cause.confidence > 0.9);
    }

    #[test]
    fn diagnose_backend_error() {
        let engine = DiagnosticEngine::new(10);
        let report = engine.diagnose(make_input(502, Some("upstream connection failed")));
        assert_eq!(report.error_category, ErrorCategory::Backend);
    }

    #[test]
    fn diagnose_timeout() {
        let engine = DiagnosticEngine::new(10);
        let report = engine.diagnose(make_input(504, Some("request timed out")));
        assert_eq!(report.error_category, ErrorCategory::Timeout);
    }

    #[test]
    fn diagnose_policy_denial() {
        let engine = DiagnosticEngine::new(10);
        let report = engine.diagnose(make_input(403, Some("OPA policy denied")));
        assert_eq!(report.error_category, ErrorCategory::Policy);
    }

    #[test]
    fn diagnose_certificate_error() {
        let engine = DiagnosticEngine::new(10);
        let report = engine.diagnose(make_input(502, Some("TLS handshake failed")));
        assert_eq!(report.error_category, ErrorCategory::Certificate);
    }

    #[test]
    fn diagnose_network_error() {
        let engine = DiagnosticEngine::new(10);
        let report = engine.diagnose(make_input(502, Some("DNS resolution failed")));
        assert_eq!(report.error_category, ErrorCategory::Network);
    }

    #[test]
    fn diagnose_unknown_error() {
        let engine = DiagnosticEngine::new(10);
        let report = engine.diagnose(make_input(418, None));
        assert_eq!(report.error_category, ErrorCategory::Unknown);
    }

    #[test]
    fn report_stored_and_retrievable() {
        let engine = DiagnosticEngine::new(10);
        engine.diagnose(make_input(500, Some("server error")));
        let report = engine.get_report("req-500");
        assert!(report.is_some());
        assert_eq!(report.as_ref().unwrap().request_meta.status_code, 500);
    }

    #[test]
    fn report_not_found() {
        let engine = DiagnosticEngine::new(10);
        assert!(engine.get_report("nonexistent").is_none());
    }

    #[test]
    fn recent_reports_returns_newest_first() {
        let engine = DiagnosticEngine::new(10);
        engine.diagnose(make_input(401, Some("first")));
        engine.diagnose(make_input(500, Some("second")));
        engine.diagnose(make_input(503, Some("third")));

        let recent = engine.recent_reports(2);
        assert_eq!(recent.len(), 2);
        assert_eq!(recent[0].request_meta.status_code, 503);
        assert_eq!(recent[1].request_meta.status_code, 500);
    }

    #[test]
    fn buffer_wraps_at_capacity() {
        let engine = DiagnosticEngine::new(3);
        for i in 0..5 {
            let mut input = make_input(500, Some("error"));
            input.request_id = format!("req-{}", i);
            engine.diagnose(input);
        }
        // Buffer capacity 3 — only last 3 should be stored
        assert!(engine.get_report("req-0").is_none());
        assert!(engine.get_report("req-1").is_none());
        assert!(engine.get_report("req-2").is_some());
        assert!(engine.get_report("req-3").is_some());
        assert!(engine.get_report("req-4").is_some());
    }

    #[test]
    fn summary_counts_categories() {
        let engine = DiagnosticEngine::new(100);
        engine.diagnose(make_input(401, Some("auth fail")));
        engine.diagnose(make_input(401, Some("jwt expired")));
        engine.diagnose(make_input(502, Some("backend down")));

        let summary = engine.summary();
        assert_eq!(summary.get(&ErrorCategory::Auth), Some(&2));
        assert_eq!(summary.get(&ErrorCategory::Backend), Some(&1));
    }

    #[test]
    fn evidence_includes_http_info() {
        let engine = DiagnosticEngine::new(10);
        let report = engine.diagnose(make_input(401, Some("unauthorized")));
        assert!(report.root_cause.evidence.iter().any(|e| e.contains("401")));
        assert!(report
            .root_cause
            .evidence
            .iter()
            .any(|e| e.contains("POST")));
    }

    #[test]
    fn evidence_includes_error_message() {
        let engine = DiagnosticEngine::new(10);
        let report = engine.diagnose(make_input(500, Some("internal failure")));
        assert!(report
            .root_cause
            .evidence
            .iter()
            .any(|e| e.contains("internal failure")));
    }

    #[test]
    fn evidence_includes_latency() {
        let engine = DiagnosticEngine::new(10);
        let report = engine.diagnose(make_input(500, None));
        assert!(report
            .root_cause
            .evidence
            .iter()
            .any(|e| e.contains("54.0ms")));
    }

    #[test]
    fn hop_chain_populated_from_headers() {
        let engine = DiagnosticEngine::new(10);
        let mut input = make_input(502, Some("backend error"));
        input.hop_headers = HopHeaders {
            x_forwarded_for: Some("10.0.0.1, 10.0.0.2".into()),
            via: Some("1.1 stoa-gateway".into()),
            ..Default::default()
        };
        let report = engine.diagnose(input);
        assert!(report.hop_chain.total_detected >= 2);
    }

    #[test]
    fn outliers_detected_when_backend_dominates() {
        let engine = DiagnosticEngine::new(10);
        let mut input = make_input(502, Some("slow backend"));
        input.timing = TimingBreakdown {
            auth_ms: Some(1.0),
            policy_eval_ms: Some(1.0),
            backend_ms: Some(900.0),
            serialization_ms: Some(1.0),
            total_ms: 903.0,
            checkpoints: vec![],
        };
        let report = engine.diagnose(input);
        assert!(!report.outliers.is_empty());
        assert_eq!(
            report.outliers[0].stage,
            crate::diagnostics::latency::Stage::BackendCall
        );
    }

    #[test]
    fn default_engine_has_reasonable_capacity() {
        let engine = DiagnosticEngine::default();
        // Store 10 reports and verify they're retrievable
        for i in 0..10 {
            let mut input = make_input(500, None);
            input.request_id = format!("test-{}", i);
            engine.diagnose(input);
        }
        let recent = engine.recent_reports(10);
        assert_eq!(recent.len(), 10);
    }

    #[test]
    fn description_with_message() {
        let engine = DiagnosticEngine::new(10);
        let report = engine.diagnose(make_input(401, Some("Token expired at 12:00")));
        assert!(report
            .root_cause
            .description
            .contains("Token expired at 12:00"));
    }

    #[test]
    fn description_without_message() {
        let engine = DiagnosticEngine::new(10);
        let report = engine.diagnose(make_input(500, None));
        assert!(report.root_cause.description.contains("HTTP 500"));
    }

    #[test]
    fn confidence_boosted_by_explicit_match() {
        let engine = DiagnosticEngine::new(10);
        // With explicit JWT message, confidence should be higher
        let report_explicit = engine.diagnose(make_input(401, Some("JWT token invalid")));
        // Without message, rely on status code alone
        let report_status = engine.diagnose(make_input(401, None));
        assert!(report_explicit.root_cause.confidence > report_status.root_cause.confidence);
    }

    #[test]
    fn serde_roundtrip_report() {
        let engine = DiagnosticEngine::new(10);
        let report = engine.diagnose(make_input(502, Some("upstream error")));
        let json = serde_json::to_string(&report).expect("serialize");
        let back: DiagnosticReport = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(back.request_id, report.request_id);
        assert_eq!(back.error_category, report.error_category);
    }

    #[test]
    fn recent_reports_empty_engine() {
        let engine = DiagnosticEngine::new(10);
        let recent = engine.recent_reports(5);
        assert!(recent.is_empty());
    }

    #[test]
    fn request_meta_populated() {
        let engine = DiagnosticEngine::new(10);
        let report = engine.diagnose(make_input(403, Some("forbidden")));
        assert_eq!(report.request_meta.method, "POST");
        assert_eq!(report.request_meta.path, "/api/tools/call");
        assert_eq!(report.request_meta.status_code, 403);
    }
}
