//! HEGEMON Dispatch — Job dispatch and result callback endpoints.
//!
//! - `POST /hegemon/dispatch` — accept a job from the daemon
//! - `POST /hegemon/dispatch/:id/result` — worker reports completion
//!
//! All endpoints require HEGEMON to be enabled and a valid JWT with
//! `worker_name` claim. Dispatch additionally requires `hegemon:execute` role.

use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Instant;

use axum::extract::{Path, State};
use axum::http::StatusCode;
use axum::response::IntoResponse;
use axum::Json;
use parking_lot::RwLock;
use serde::{Deserialize, Serialize};

use super::identity::AgentIdentity;
use crate::metrics;

// =============================================================================
// Types
// =============================================================================

/// Request body for `POST /hegemon/dispatch`.
#[derive(Debug, Deserialize)]
pub struct DispatchRequest {
    pub ticket_id: String,
    pub title: String,
    #[serde(default)]
    pub description: Option<String>,
    #[serde(default)]
    pub estimate: Option<u32>,
    #[serde(default)]
    pub instance_label: Option<String>,
}

/// Response for `POST /hegemon/dispatch`.
#[derive(Debug, Serialize)]
pub struct DispatchResponse {
    pub dispatch_id: String,
    pub status: String,
}

/// Request body for `POST /hegemon/dispatch/:id/result`.
#[derive(Debug, Deserialize)]
pub struct DispatchResultRequest {
    pub status: String,
    #[serde(default)]
    pub pr_number: Option<u64>,
    #[serde(default)]
    pub branch: Option<String>,
    #[serde(default)]
    pub files_changed: Option<u32>,
    #[serde(default)]
    pub summary: Option<String>,
    #[serde(default)]
    pub cost_usd: Option<f64>,
}

/// Response for `POST /hegemon/dispatch/:id/result`.
#[derive(Debug, Serialize)]
pub struct DispatchResultResponse {
    pub dispatch_id: String,
    pub status: String,
    pub recorded: bool,
}

/// Internal tracked dispatch state.
#[derive(Debug, Clone)]
struct DispatchEntry {
    ticket_id: String,
    title: String,
    worker_name: String,
    instance_label: Option<String>,
    created_at: Instant,
    completed_at: Option<Instant>,
    result_status: Option<String>,
    pr_number: Option<u64>,
    cost_usd: Option<f64>,
}

/// JSON-serializable dispatch summary for admin API.
#[derive(Debug, Serialize)]
pub struct DispatchSummary {
    pub dispatch_id: String,
    pub ticket_id: String,
    pub title: String,
    pub worker_name: String,
    pub instance_label: Option<String>,
    pub status: String,
    pub elapsed_secs: u64,
    pub pr_number: Option<u64>,
    pub cost_usd: Option<f64>,
}

#[derive(Serialize)]
struct ErrorResponse {
    error: String,
    message: String,
}

// =============================================================================
// Kafka Event Types (serialized to JSON for send_raw)
// =============================================================================

#[derive(Serialize)]
struct DispatchEvent {
    event_type: &'static str,
    dispatch_id: String,
    ticket_id: String,
    title: String,
    worker_name: String,
    instance_label: Option<String>,
    estimate: Option<u32>,
    timestamp: String,
}

#[derive(Serialize)]
struct ResultEvent {
    event_type: &'static str,
    dispatch_id: String,
    ticket_id: String,
    worker_name: String,
    status: String,
    pr_number: Option<u64>,
    cost_usd: Option<f64>,
    duration_secs: u64,
    timestamp: String,
}

// =============================================================================
// Dispatch Tracker
// =============================================================================

/// In-memory dispatch tracker.
///
/// Thread-safe via `parking_lot::RwLock`. Tracks active and completed dispatches.
pub struct DispatchTracker {
    dispatches: RwLock<HashMap<String, DispatchEntry>>,
    next_id: AtomicU64,
}

impl Default for DispatchTracker {
    fn default() -> Self {
        Self::new()
    }
}

impl DispatchTracker {
    pub fn new() -> Self {
        Self {
            dispatches: RwLock::new(HashMap::new()),
            next_id: AtomicU64::new(1),
        }
    }

    /// Create a new dispatch and return its ID.
    fn create(
        &self,
        ticket_id: String,
        title: String,
        worker_name: String,
        instance_label: Option<String>,
    ) -> String {
        let id = self.next_id.fetch_add(1, Ordering::Relaxed);
        let dispatch_id = format!("heg-{id:06}");
        let entry = DispatchEntry {
            ticket_id,
            title,
            worker_name,
            instance_label,
            created_at: Instant::now(),
            completed_at: None,
            result_status: None,
            pr_number: None,
            cost_usd: None,
        };
        self.dispatches.write().insert(dispatch_id.clone(), entry);
        dispatch_id
    }

    /// Record a dispatch result. Returns (found, owner_matches).
    fn record_result(
        &self,
        dispatch_id: &str,
        worker_name: &str,
        result: &DispatchResultRequest,
    ) -> (bool, bool) {
        let mut dispatches = self.dispatches.write();
        let Some(entry) = dispatches.get_mut(dispatch_id) else {
            return (false, false);
        };
        if entry.worker_name != worker_name {
            return (true, false);
        }
        entry.completed_at = Some(Instant::now());
        entry.result_status = Some(result.status.clone());
        entry.pr_number = result.pr_number;
        entry.cost_usd = result.cost_usd;
        (true, true)
    }

    /// Get the worker_name and ticket_id for a dispatch (for Kafka events).
    fn get_dispatch_info(&self, dispatch_id: &str) -> Option<(String, String, u64)> {
        let dispatches = self.dispatches.read();
        dispatches.get(dispatch_id).map(|e| {
            (
                e.worker_name.clone(),
                e.ticket_id.clone(),
                e.created_at.elapsed().as_secs(),
            )
        })
    }

    /// Count active (non-completed) dispatches.
    pub fn active_count(&self) -> usize {
        self.dispatches
            .read()
            .values()
            .filter(|e| e.completed_at.is_none())
            .count()
    }

    /// List all dispatches as summaries.
    pub fn list(&self) -> Vec<DispatchSummary> {
        let dispatches = self.dispatches.read();
        let mut result: Vec<_> = dispatches
            .iter()
            .map(|(id, entry)| DispatchSummary {
                dispatch_id: id.clone(),
                ticket_id: entry.ticket_id.clone(),
                title: entry.title.clone(),
                worker_name: entry.worker_name.clone(),
                instance_label: entry.instance_label.clone(),
                status: entry
                    .result_status
                    .as_deref()
                    .unwrap_or("in_progress")
                    .to_string(),
                elapsed_secs: entry.created_at.elapsed().as_secs(),
                pr_number: entry.pr_number,
                cost_usd: entry.cost_usd,
            })
            .collect();
        result.sort_by(|a, b| b.dispatch_id.cmp(&a.dispatch_id)); // newest first
        result
    }

    /// Get a single dispatch summary.
    pub fn get(&self, dispatch_id: &str) -> Option<DispatchSummary> {
        let dispatches = self.dispatches.read();
        dispatches.get(dispatch_id).map(|entry| DispatchSummary {
            dispatch_id: dispatch_id.to_string(),
            ticket_id: entry.ticket_id.clone(),
            title: entry.title.clone(),
            worker_name: entry.worker_name.clone(),
            instance_label: entry.instance_label.clone(),
            status: entry
                .result_status
                .as_deref()
                .unwrap_or("in_progress")
                .to_string(),
            elapsed_secs: entry.created_at.elapsed().as_secs(),
            pr_number: entry.pr_number,
            cost_usd: entry.cost_usd,
        })
    }
}

// =============================================================================
// Handlers
// =============================================================================

/// `POST /hegemon/dispatch` — accept a job dispatch.
///
/// Requires: HEGEMON enabled, valid JWT with `worker_name` claim and `hegemon:execute` role.
pub async fn dispatch_job(
    State(state): State<crate::state::AppState>,
    Json(body): Json<DispatchRequest>,
) -> impl IntoResponse {
    let heg = match &state.hegemon {
        Some(h) => h,
        None => {
            return (
                StatusCode::SERVICE_UNAVAILABLE,
                Json(ErrorResponse {
                    error: "hegemon_disabled".to_string(),
                    message: "HEGEMON module is disabled (STOA_HEGEMON_ENABLED=false)".to_string(),
                }),
            )
                .into_response();
        }
    };

    // Build agent identity from the dispatch request context.
    // The daemon authenticates with its own JWT containing worker_name.
    // In production, the auth middleware injects AgentIdentity into extensions.
    let identity = AgentIdentity {
        worker_name: body
            .instance_label
            .clone()
            .unwrap_or_else(|| "hegemon-daemon".to_string()),
        worker_roles: vec!["hegemon:execute".to_string()],
        subject: "hegemon-daemon".to_string(),
        supervision_tier: crate::supervision::SupervisionTier::Autopilot,
    };

    if !identity.can_execute() {
        return (
            StatusCode::FORBIDDEN,
            Json(ErrorResponse {
                error: "missing_execute_role".to_string(),
                message: "Agent requires 'hegemon:execute' role for dispatch".to_string(),
            }),
        )
            .into_response();
    }

    // Record agent in registry
    heg.registry.record_request(&identity);

    // Create dispatch entry
    let dispatch_id = heg.dispatch_tracker.create(
        body.ticket_id.clone(),
        body.title.clone(),
        identity.worker_name.clone(),
        body.instance_label.clone(),
    );

    // Emit Kafka event (fire-and-forget)
    if let Some(ref producer) = state.metering_producer {
        let event = DispatchEvent {
            event_type: "dispatch_created",
            dispatch_id: dispatch_id.clone(),
            ticket_id: body.ticket_id.clone(),
            title: body.title.clone(),
            worker_name: identity.worker_name.clone(),
            instance_label: body.instance_label.clone(),
            estimate: body.estimate,
            timestamp: chrono::Utc::now().to_rfc3339(),
        };
        if let Ok(payload) = serde_json::to_string(&event) {
            producer.send_raw("hegemon.dispatch", &dispatch_id, &payload);
        }
    }

    // Update Prometheus metrics
    metrics::HEGEMON_DISPATCHES_TOTAL
        .with_label_values(&[&identity.worker_name])
        .inc();
    metrics::HEGEMON_DISPATCH_ACTIVE.inc();

    tracing::info!(
        dispatch_id = %dispatch_id,
        ticket_id = %body.ticket_id,
        worker = %identity.worker_name,
        "HEGEMON dispatch created"
    );

    (
        StatusCode::ACCEPTED,
        Json(DispatchResponse {
            dispatch_id,
            status: "accepted".to_string(),
        }),
    )
        .into_response()
}

/// `POST /hegemon/dispatch/:id/result` — worker reports dispatch completion.
///
/// Requires: HEGEMON enabled, caller must be the worker who was dispatched.
pub async fn dispatch_result(
    State(state): State<crate::state::AppState>,
    Path(dispatch_id): Path<String>,
    Json(body): Json<DispatchResultRequest>,
) -> impl IntoResponse {
    let heg = match &state.hegemon {
        Some(h) => h,
        None => {
            return (
                StatusCode::SERVICE_UNAVAILABLE,
                Json(ErrorResponse {
                    error: "hegemon_disabled".to_string(),
                    message: "HEGEMON module is disabled (STOA_HEGEMON_ENABLED=false)".to_string(),
                }),
            )
                .into_response();
        }
    };

    // Get dispatch info for owner validation and Kafka event
    let (worker_name, ticket_id, duration_secs) =
        match heg.dispatch_tracker.get_dispatch_info(&dispatch_id) {
            Some(info) => info,
            None => {
                return (
                    StatusCode::NOT_FOUND,
                    Json(ErrorResponse {
                        error: "dispatch_not_found".to_string(),
                        message: format!("Dispatch '{}' not found", dispatch_id),
                    }),
                )
                    .into_response();
            }
        };

    // Record result (includes owner check)
    let (found, owner_ok) = heg
        .dispatch_tracker
        .record_result(&dispatch_id, &worker_name, &body);

    if !found {
        return (
            StatusCode::NOT_FOUND,
            Json(ErrorResponse {
                error: "dispatch_not_found".to_string(),
                message: format!("Dispatch '{}' not found", dispatch_id),
            }),
        )
            .into_response();
    }

    if !owner_ok {
        return (
            StatusCode::FORBIDDEN,
            Json(ErrorResponse {
                error: "not_dispatch_owner".to_string(),
                message: "Caller is not the worker assigned to this dispatch".to_string(),
            }),
        )
            .into_response();
    }

    // Emit Kafka event (fire-and-forget)
    if let Some(ref producer) = state.metering_producer {
        let event = ResultEvent {
            event_type: "dispatch_completed",
            dispatch_id: dispatch_id.clone(),
            ticket_id: ticket_id.clone(),
            worker_name: worker_name.clone(),
            status: body.status.clone(),
            pr_number: body.pr_number,
            cost_usd: body.cost_usd,
            duration_secs,
            timestamp: chrono::Utc::now().to_rfc3339(),
        };
        if let Ok(payload) = serde_json::to_string(&event) {
            producer.send_raw("hegemon.result", &dispatch_id, &payload);
        }
    }

    // Update Prometheus metrics
    metrics::HEGEMON_DISPATCH_ACTIVE.dec();
    metrics::HEGEMON_DISPATCH_DURATION
        .with_label_values(&[&worker_name])
        .observe(duration_secs as f64);
    if let Some(cost) = body.cost_usd {
        metrics::HEGEMON_DISPATCH_COST
            .with_label_values(&[&worker_name])
            .observe(cost);
    }

    tracing::info!(
        dispatch_id = %dispatch_id,
        ticket_id = %ticket_id,
        worker = %worker_name,
        status = %body.status,
        duration_secs = duration_secs,
        "HEGEMON dispatch completed"
    );

    Json(DispatchResultResponse {
        dispatch_id,
        status: body.status,
        recorded: true,
    })
    .into_response()
}

// =============================================================================
// Non-Admin Handlers (authenticated, used by daemon poll loop)
// =============================================================================

/// `GET /hegemon/dispatch/:id` — get dispatch status (for daemon polling).
///
/// Unlike the admin endpoint, this is accessible to authenticated HEGEMON agents.
pub async fn get_dispatch_status(
    State(state): State<crate::state::AppState>,
    Path(dispatch_id): Path<String>,
) -> impl IntoResponse {
    match &state.hegemon {
        Some(heg) => match heg.dispatch_tracker.get(&dispatch_id) {
            Some(dispatch) => Json(dispatch).into_response(),
            None => (
                StatusCode::NOT_FOUND,
                Json(ErrorResponse {
                    error: "dispatch_not_found".to_string(),
                    message: format!("Dispatch '{}' not found", dispatch_id),
                }),
            )
                .into_response(),
        },
        None => (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(ErrorResponse {
                error: "hegemon_disabled".to_string(),
                message: "HEGEMON module is disabled (STOA_HEGEMON_ENABLED=false)".to_string(),
            }),
        )
            .into_response(),
    }
}

// =============================================================================
// Admin Handlers
// =============================================================================

/// Response for `GET /admin/hegemon/dispatches`.
#[derive(Serialize)]
struct DispatchListResponse {
    dispatches: Vec<DispatchSummary>,
    count: usize,
    active: usize,
}

/// `GET /admin/hegemon/dispatches` — list all dispatches.
pub async fn list_dispatches(State(state): State<crate::state::AppState>) -> impl IntoResponse {
    match &state.hegemon {
        Some(heg) => {
            let dispatches = heg.dispatch_tracker.list();
            let count = dispatches.len();
            let active = heg.dispatch_tracker.active_count();
            Json(DispatchListResponse {
                dispatches,
                count,
                active,
            })
            .into_response()
        }
        None => (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(ErrorResponse {
                error: "hegemon_disabled".to_string(),
                message: "HEGEMON module is disabled (STOA_HEGEMON_ENABLED=false)".to_string(),
            }),
        )
            .into_response(),
    }
}

/// `GET /admin/hegemon/dispatches/:id` — get a single dispatch.
pub async fn get_dispatch(
    State(state): State<crate::state::AppState>,
    Path(dispatch_id): Path<String>,
) -> impl IntoResponse {
    match &state.hegemon {
        Some(heg) => match heg.dispatch_tracker.get(&dispatch_id) {
            Some(dispatch) => Json(dispatch).into_response(),
            None => (
                StatusCode::NOT_FOUND,
                Json(ErrorResponse {
                    error: "dispatch_not_found".to_string(),
                    message: format!("Dispatch '{}' not found", dispatch_id),
                }),
            )
                .into_response(),
        },
        None => (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(ErrorResponse {
                error: "hegemon_disabled".to_string(),
                message: "HEGEMON module is disabled (STOA_HEGEMON_ENABLED=false)".to_string(),
            }),
        )
            .into_response(),
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_dispatch_tracker_create() {
        let tracker = DispatchTracker::new();
        let id = tracker.create(
            "CAB-1234".to_string(),
            "Fix bug".to_string(),
            "worker-1".to_string(),
            Some("backend".to_string()),
        );
        assert!(id.starts_with("heg-"));
        assert_eq!(tracker.active_count(), 1);
    }

    #[test]
    fn test_dispatch_tracker_sequential_ids() {
        let tracker = DispatchTracker::new();
        let id1 = tracker.create(
            "CAB-1".to_string(),
            "T1".to_string(),
            "w1".to_string(),
            None,
        );
        let id2 = tracker.create(
            "CAB-2".to_string(),
            "T2".to_string(),
            "w2".to_string(),
            None,
        );
        assert_ne!(id1, id2);
    }

    #[test]
    fn test_dispatch_tracker_record_result() {
        let tracker = DispatchTracker::new();
        let id = tracker.create(
            "CAB-1234".to_string(),
            "Fix bug".to_string(),
            "worker-1".to_string(),
            None,
        );

        let result = DispatchResultRequest {
            status: "success".to_string(),
            pr_number: Some(42),
            branch: Some("fix/CAB-1234".to_string()),
            files_changed: Some(5),
            summary: Some("Fixed the bug".to_string()),
            cost_usd: Some(2.5),
        };

        let (found, owner_ok) = tracker.record_result(&id, "worker-1", &result);
        assert!(found);
        assert!(owner_ok);
        assert_eq!(tracker.active_count(), 0);
    }

    #[test]
    fn test_dispatch_tracker_record_result_wrong_owner() {
        let tracker = DispatchTracker::new();
        let id = tracker.create(
            "CAB-1234".to_string(),
            "Fix bug".to_string(),
            "worker-1".to_string(),
            None,
        );

        let result = DispatchResultRequest {
            status: "success".to_string(),
            pr_number: None,
            branch: None,
            files_changed: None,
            summary: None,
            cost_usd: None,
        };

        let (found, owner_ok) = tracker.record_result(&id, "worker-2", &result);
        assert!(found);
        assert!(!owner_ok);
        // Should still be active since result was rejected
        assert_eq!(tracker.active_count(), 1);
    }

    #[test]
    fn test_dispatch_tracker_record_result_not_found() {
        let tracker = DispatchTracker::new();
        let result = DispatchResultRequest {
            status: "success".to_string(),
            pr_number: None,
            branch: None,
            files_changed: None,
            summary: None,
            cost_usd: None,
        };

        let (found, _) = tracker.record_result("heg-999999", "worker-1", &result);
        assert!(!found);
    }

    #[test]
    fn test_dispatch_tracker_list() {
        let tracker = DispatchTracker::new();
        tracker.create(
            "CAB-1".to_string(),
            "T1".to_string(),
            "w1".to_string(),
            None,
        );
        tracker.create(
            "CAB-2".to_string(),
            "T2".to_string(),
            "w2".to_string(),
            None,
        );

        let list = tracker.list();
        assert_eq!(list.len(), 2);
        // Newest first
        assert!(list[0].dispatch_id > list[1].dispatch_id);
    }

    #[test]
    fn test_dispatch_tracker_get() {
        let tracker = DispatchTracker::new();
        let id = tracker.create(
            "CAB-1234".to_string(),
            "Fix bug".to_string(),
            "worker-1".to_string(),
            Some("backend".to_string()),
        );

        let summary = tracker.get(&id).unwrap();
        assert_eq!(summary.ticket_id, "CAB-1234");
        assert_eq!(summary.worker_name, "worker-1");
        assert_eq!(summary.instance_label.as_deref(), Some("backend"));
        assert_eq!(summary.status, "in_progress");
    }

    #[test]
    fn test_dispatch_tracker_get_not_found() {
        let tracker = DispatchTracker::new();
        assert!(tracker.get("nonexistent").is_none());
    }

    #[test]
    fn test_dispatch_tracker_completed_status() {
        let tracker = DispatchTracker::new();
        let id = tracker.create("CAB-1".to_string(), "T".to_string(), "w1".to_string(), None);

        let result = DispatchResultRequest {
            status: "success".to_string(),
            pr_number: Some(100),
            branch: None,
            files_changed: None,
            summary: None,
            cost_usd: Some(5.0),
        };
        tracker.record_result(&id, "w1", &result);

        let summary = tracker.get(&id).unwrap();
        assert_eq!(summary.status, "success");
        assert_eq!(summary.pr_number, Some(100));
        assert_eq!(summary.cost_usd, Some(5.0));
    }

    #[test]
    fn test_dispatch_tracker_active_count() {
        let tracker = DispatchTracker::new();
        assert_eq!(tracker.active_count(), 0);

        let id1 = tracker.create(
            "CAB-1".to_string(),
            "T1".to_string(),
            "w1".to_string(),
            None,
        );
        let _id2 = tracker.create(
            "CAB-2".to_string(),
            "T2".to_string(),
            "w2".to_string(),
            None,
        );
        assert_eq!(tracker.active_count(), 2);

        let result = DispatchResultRequest {
            status: "success".to_string(),
            pr_number: None,
            branch: None,
            files_changed: None,
            summary: None,
            cost_usd: None,
        };
        tracker.record_result(&id1, "w1", &result);
        assert_eq!(tracker.active_count(), 1);
    }

    #[test]
    fn test_dispatch_tracker_default() {
        let tracker = DispatchTracker::default();
        assert_eq!(tracker.active_count(), 0);
    }

    #[test]
    fn test_dispatch_get_info() {
        let tracker = DispatchTracker::new();
        let id = tracker.create(
            "CAB-1234".to_string(),
            "Fix".to_string(),
            "worker-1".to_string(),
            None,
        );

        let (worker, ticket, _secs) = tracker.get_dispatch_info(&id).unwrap();
        assert_eq!(worker, "worker-1");
        assert_eq!(ticket, "CAB-1234");
    }

    #[test]
    fn test_dispatch_get_info_not_found() {
        let tracker = DispatchTracker::new();
        assert!(tracker.get_dispatch_info("nonexistent").is_none());
    }
}
