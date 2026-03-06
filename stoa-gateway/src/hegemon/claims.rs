//! HEGEMON Claims — Atomic claim coordination for phase ownership.
//!
//! Replaces local `.claude/claims/*.json` + `mkdir` locks with
//! gateway-coordinated atomic claims. Prevents race conditions
//! when multiple instances work on the same MEGA ticket.
//!
//! - `POST /hegemon/claims/:mega_id/reserve` — atomic reserve (409 on conflict)
//! - `POST /hegemon/claims/:mega_id/release` — owner-validated release
//! - `POST /hegemon/claims/:mega_id/heartbeat` — extend claim liveness
//! - `GET /hegemon/claims` — all active claims
//! - `GET /hegemon/claims/:mega_id` — single MEGA claim state

use std::collections::HashMap;
use std::time::Instant;

use axum::extract::{Path, State};
use axum::http::StatusCode;
use axum::response::IntoResponse;
use axum::Json;
use parking_lot::RwLock;
use serde::{Deserialize, Serialize};

// =============================================================================
// Types
// =============================================================================

/// A claim on a MEGA phase.
#[derive(Debug, Clone)]
struct ClaimEntry {
    /// MEGA ticket ID (e.g., "CAB-1709").
    mega_id: String,
    /// Phase number within the MEGA.
    phase_id: u32,
    /// Instance ID that owns this claim (e.g., "t48217-a3f2").
    owner: String,
    /// Hostname of the claiming machine.
    hostname: String,
    /// When the claim was created.
    claimed_at: Instant,
    /// Last heartbeat timestamp.
    last_heartbeat: Instant,
    /// Whether this claim has been completed.
    completed: bool,
}

/// Request body for `POST /hegemon/claims/:mega_id/reserve`.
#[derive(Debug, Deserialize)]
pub struct ReserveRequest {
    pub phase_id: u32,
    pub owner: String,
    #[serde(default)]
    pub hostname: Option<String>,
}

/// Request body for `POST /hegemon/claims/:mega_id/release`.
#[derive(Debug, Deserialize)]
pub struct ReleaseRequest {
    pub phase_id: u32,
    pub owner: String,
    #[serde(default = "default_false")]
    pub completed: bool,
}

fn default_false() -> bool {
    false
}

/// Request body for `POST /hegemon/claims/:mega_id/heartbeat`.
#[derive(Debug, Deserialize)]
pub struct HeartbeatRequest {
    pub phase_id: u32,
    pub owner: String,
}

/// Response for reserve/release/heartbeat operations.
#[derive(Debug, Serialize)]
pub struct ClaimResponse {
    pub mega_id: String,
    pub phase_id: u32,
    pub status: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub owner: Option<String>,
}

/// Serializable claim summary for list/get endpoints.
#[derive(Debug, Serialize)]
pub struct ClaimSummary {
    pub mega_id: String,
    pub phase_id: u32,
    pub owner: String,
    pub hostname: String,
    pub claimed_secs_ago: u64,
    pub last_heartbeat_secs_ago: u64,
    pub completed: bool,
    pub stale: bool,
}

/// Response for `GET /hegemon/claims`.
#[derive(Debug, Serialize)]
struct ClaimListResponse {
    claims: Vec<ClaimSummary>,
    count: usize,
    stale_count: usize,
}

/// Error response.
#[derive(Serialize)]
struct ErrorResponse {
    error: String,
    message: String,
}

// =============================================================================
// ClaimTracker
// =============================================================================

/// Stale timeout: claims without heartbeat for 2 hours are considered stale.
const STALE_TIMEOUT_SECS: u64 = 2 * 60 * 60; // 2 hours

/// In-memory claim tracker for MEGA phase coordination.
///
/// Thread-safe via `parking_lot::RwLock`. Claims are keyed by
/// `(mega_id, phase_id)` to allow per-phase ownership within a MEGA.
pub struct ClaimTracker {
    /// Claims indexed by composite key "mega_id:phase_id".
    claims: RwLock<HashMap<String, ClaimEntry>>,
}

impl Default for ClaimTracker {
    fn default() -> Self {
        Self::new()
    }
}

impl ClaimTracker {
    pub fn new() -> Self {
        Self {
            claims: RwLock::new(HashMap::new()),
        }
    }

    /// Reserve a claim on a MEGA phase. Returns Ok(()) on success,
    /// Err(current_owner) if already claimed.
    pub fn reserve(
        &self,
        mega_id: &str,
        phase_id: u32,
        owner: &str,
        hostname: &str,
    ) -> Result<(), String> {
        let key = claim_key(mega_id, phase_id);
        let now = Instant::now();
        let mut claims = self.claims.write();

        if let Some(existing) = claims.get(&key) {
            if !existing.completed && !is_stale(existing, now) {
                return Err(existing.owner.clone());
            }
            // Stale or completed — allow re-claim
        }

        claims.insert(
            key,
            ClaimEntry {
                mega_id: mega_id.to_string(),
                phase_id,
                owner: owner.to_string(),
                hostname: hostname.to_string(),
                claimed_at: now,
                last_heartbeat: now,
                completed: false,
            },
        );
        Ok(())
    }

    /// Release a claim. Only the owner can release.
    /// Returns (found, owner_matches, was_completed).
    pub fn release(
        &self,
        mega_id: &str,
        phase_id: u32,
        owner: &str,
        completed: bool,
    ) -> (bool, bool) {
        let key = claim_key(mega_id, phase_id);
        let mut claims = self.claims.write();

        if let Some(entry) = claims.get_mut(&key) {
            if entry.owner != owner {
                return (true, false);
            }
            if completed {
                entry.completed = true;
            } else {
                claims.remove(&key);
            }
            (true, true)
        } else {
            (false, false)
        }
    }

    /// Update heartbeat for a claim. Only the owner can heartbeat.
    /// Returns (found, owner_matches).
    pub fn heartbeat(&self, mega_id: &str, phase_id: u32, owner: &str) -> (bool, bool) {
        let key = claim_key(mega_id, phase_id);
        let mut claims = self.claims.write();

        if let Some(entry) = claims.get_mut(&key) {
            if entry.owner != owner {
                return (true, false);
            }
            entry.last_heartbeat = Instant::now();
            (true, true)
        } else {
            (false, false)
        }
    }

    /// List all claims as summaries.
    pub fn list(&self) -> Vec<ClaimSummary> {
        let now = Instant::now();
        let claims = self.claims.read();
        let mut result: Vec<_> = claims.values().map(|e| to_summary(e, now)).collect();
        result.sort_by(|a, b| a.mega_id.cmp(&b.mega_id).then(a.phase_id.cmp(&b.phase_id)));
        result
    }

    /// Get claims for a specific MEGA.
    pub fn get(&self, mega_id: &str) -> Vec<ClaimSummary> {
        let now = Instant::now();
        let claims = self.claims.read();
        let mut result: Vec<_> = claims
            .values()
            .filter(|e| e.mega_id == mega_id)
            .map(|e| to_summary(e, now))
            .collect();
        result.sort_by_key(|s| s.phase_id);
        result
    }

    /// Release all stale claims (no heartbeat for > 2h). Returns count released.
    pub fn release_stale(&self) -> usize {
        let now = Instant::now();
        let mut claims = self.claims.write();
        let stale_keys: Vec<String> = claims
            .iter()
            .filter(|(_, e)| !e.completed && is_stale(e, now))
            .map(|(k, _)| k.clone())
            .collect();
        let count = stale_keys.len();
        for key in stale_keys {
            claims.remove(&key);
        }
        count
    }

    /// Get total claim count.
    pub fn count(&self) -> usize {
        self.claims.read().len()
    }

    /// Get active (non-completed, non-stale) claim count.
    pub fn active_count(&self) -> usize {
        let now = Instant::now();
        let claims = self.claims.read();
        claims
            .values()
            .filter(|e| !e.completed && !is_stale(e, now))
            .count()
    }
}

fn claim_key(mega_id: &str, phase_id: u32) -> String {
    format!("{}:{}", mega_id, phase_id)
}

fn is_stale(entry: &ClaimEntry, now: Instant) -> bool {
    now.duration_since(entry.last_heartbeat).as_secs() > STALE_TIMEOUT_SECS
}

fn to_summary(entry: &ClaimEntry, now: Instant) -> ClaimSummary {
    ClaimSummary {
        mega_id: entry.mega_id.clone(),
        phase_id: entry.phase_id,
        owner: entry.owner.clone(),
        hostname: entry.hostname.clone(),
        claimed_secs_ago: now.duration_since(entry.claimed_at).as_secs(),
        last_heartbeat_secs_ago: now.duration_since(entry.last_heartbeat).as_secs(),
        completed: entry.completed,
        stale: !entry.completed && is_stale(entry, now),
    }
}

// =============================================================================
// Handlers
// =============================================================================

/// `POST /hegemon/claims/:mega_id/reserve` — atomic claim reserve.
pub async fn reserve_claim(
    State(state): State<crate::state::AppState>,
    Path(mega_id): Path<String>,
    Json(body): Json<ReserveRequest>,
) -> impl IntoResponse {
    match &state.hegemon {
        Some(heg) => {
            let hostname = body.hostname.as_deref().unwrap_or("unknown");
            match heg
                .claim_tracker
                .reserve(&mega_id, body.phase_id, &body.owner, hostname)
            {
                Ok(()) => {
                    // Emit Kafka event
                    if let Some(ref producer) = state.metering_producer {
                        let event = serde_json::json!({
                            "type": "claim_reserved",
                            "mega_id": mega_id,
                            "phase_id": body.phase_id,
                            "owner": body.owner,
                            "hostname": hostname,
                            "timestamp": chrono::Utc::now().to_rfc3339(),
                        });
                        if let Ok(payload) = serde_json::to_string(&event) {
                            producer.send_raw("hegemon.claims", &mega_id, &payload);
                        }
                    }

                    Json(ClaimResponse {
                        mega_id,
                        phase_id: body.phase_id,
                        status: "reserved".to_string(),
                        owner: Some(body.owner),
                    })
                    .into_response()
                }
                Err(current_owner) => (
                    StatusCode::CONFLICT,
                    Json(ErrorResponse {
                        error: "claim_conflict".to_string(),
                        message: format!(
                            "Phase {} of {} already claimed by '{}'",
                            body.phase_id, mega_id, current_owner
                        ),
                    }),
                )
                    .into_response(),
            }
        }
        None => hegemon_disabled_response(),
    }
}

/// `POST /hegemon/claims/:mega_id/release` — release a claim.
pub async fn release_claim(
    State(state): State<crate::state::AppState>,
    Path(mega_id): Path<String>,
    Json(body): Json<ReleaseRequest>,
) -> impl IntoResponse {
    match &state.hegemon {
        Some(heg) => {
            let (found, owner_matches) =
                heg.claim_tracker
                    .release(&mega_id, body.phase_id, &body.owner, body.completed);

            if !found {
                return (
                    StatusCode::NOT_FOUND,
                    Json(ErrorResponse {
                        error: "claim_not_found".to_string(),
                        message: format!(
                            "No claim found for phase {} of {}",
                            body.phase_id, mega_id
                        ),
                    }),
                )
                    .into_response();
            }

            if !owner_matches {
                return (
                    StatusCode::FORBIDDEN,
                    Json(ErrorResponse {
                        error: "not_owner".to_string(),
                        message: format!(
                            "Only the claim owner can release phase {} of {}",
                            body.phase_id, mega_id
                        ),
                    }),
                )
                    .into_response();
            }

            // Emit Kafka event
            if let Some(ref producer) = state.metering_producer {
                let event = serde_json::json!({
                    "type": "claim_released",
                    "mega_id": mega_id,
                    "phase_id": body.phase_id,
                    "owner": body.owner,
                    "completed": body.completed,
                    "timestamp": chrono::Utc::now().to_rfc3339(),
                });
                if let Ok(payload) = serde_json::to_string(&event) {
                    producer.send_raw("hegemon.claims", &mega_id, &payload);
                }
            }

            let status = if body.completed {
                "completed"
            } else {
                "released"
            };
            Json(ClaimResponse {
                mega_id,
                phase_id: body.phase_id,
                status: status.to_string(),
                owner: None,
            })
            .into_response()
        }
        None => hegemon_disabled_response(),
    }
}

/// `POST /hegemon/claims/:mega_id/heartbeat` — extend claim liveness.
pub async fn heartbeat_claim(
    State(state): State<crate::state::AppState>,
    Path(mega_id): Path<String>,
    Json(body): Json<HeartbeatRequest>,
) -> impl IntoResponse {
    match &state.hegemon {
        Some(heg) => {
            let (found, owner_matches) =
                heg.claim_tracker
                    .heartbeat(&mega_id, body.phase_id, &body.owner);

            if !found {
                return (
                    StatusCode::NOT_FOUND,
                    Json(ErrorResponse {
                        error: "claim_not_found".to_string(),
                        message: format!(
                            "No claim found for phase {} of {}",
                            body.phase_id, mega_id
                        ),
                    }),
                )
                    .into_response();
            }

            if !owner_matches {
                return (
                    StatusCode::FORBIDDEN,
                    Json(ErrorResponse {
                        error: "not_owner".to_string(),
                        message: format!(
                            "Only the claim owner can heartbeat phase {} of {}",
                            body.phase_id, mega_id
                        ),
                    }),
                )
                    .into_response();
            }

            Json(ClaimResponse {
                mega_id,
                phase_id: body.phase_id,
                status: "heartbeat_ok".to_string(),
                owner: Some(body.owner),
            })
            .into_response()
        }
        None => hegemon_disabled_response(),
    }
}

/// `GET /hegemon/claims` — list all claims (admin).
pub async fn list_claims(State(state): State<crate::state::AppState>) -> impl IntoResponse {
    match &state.hegemon {
        Some(heg) => {
            let claims = heg.claim_tracker.list();
            let stale_count = claims.iter().filter(|c| c.stale).count();
            let count = claims.len();
            Json(ClaimListResponse {
                claims,
                count,
                stale_count,
            })
            .into_response()
        }
        None => hegemon_disabled_response(),
    }
}

/// `GET /hegemon/claims/:mega_id` — get claims for a specific MEGA (admin).
pub async fn get_claims(
    State(state): State<crate::state::AppState>,
    Path(mega_id): Path<String>,
) -> impl IntoResponse {
    match &state.hegemon {
        Some(heg) => {
            let claims = heg.claim_tracker.get(&mega_id);
            Json(claims).into_response()
        }
        None => hegemon_disabled_response(),
    }
}

fn hegemon_disabled_response() -> axum::response::Response {
    (
        StatusCode::SERVICE_UNAVAILABLE,
        Json(ErrorResponse {
            error: "hegemon_disabled".to_string(),
            message: "HEGEMON module is disabled".to_string(),
        }),
    )
        .into_response()
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_new_tracker_empty() {
        let tracker = ClaimTracker::new();
        assert_eq!(tracker.count(), 0);
        assert_eq!(tracker.active_count(), 0);
        assert!(tracker.list().is_empty());
    }

    #[test]
    fn test_reserve_success() {
        let tracker = ClaimTracker::new();
        assert!(tracker
            .reserve("CAB-1709", 1, "t48217-a3f2", "macbook")
            .is_ok());
        assert_eq!(tracker.count(), 1);
        assert_eq!(tracker.active_count(), 1);
    }

    #[test]
    fn test_reserve_conflict() {
        let tracker = ClaimTracker::new();
        assert!(tracker
            .reserve("CAB-1709", 1, "t48217-a3f2", "macbook")
            .is_ok());

        let result = tracker.reserve("CAB-1709", 1, "t99999-beef", "other-machine");
        assert!(result.is_err());
        assert_eq!(result.unwrap_err(), "t48217-a3f2");
    }

    #[test]
    fn test_reserve_different_phases_ok() {
        let tracker = ClaimTracker::new();
        assert!(tracker
            .reserve("CAB-1709", 1, "t48217-a3f2", "macbook")
            .is_ok());
        assert!(tracker
            .reserve("CAB-1709", 2, "t99999-beef", "other")
            .is_ok());
        assert_eq!(tracker.count(), 2);
    }

    #[test]
    fn test_reserve_different_megas_ok() {
        let tracker = ClaimTracker::new();
        assert!(tracker
            .reserve("CAB-1709", 1, "t48217-a3f2", "macbook")
            .is_ok());
        assert!(tracker
            .reserve("CAB-1800", 1, "t99999-beef", "other")
            .is_ok());
        assert_eq!(tracker.count(), 2);
    }

    #[test]
    fn test_reserve_after_completed_ok() {
        let tracker = ClaimTracker::new();
        tracker
            .reserve("CAB-1709", 1, "t48217-a3f2", "macbook")
            .unwrap();
        // Complete the claim
        tracker.release("CAB-1709", 1, "t48217-a3f2", true);
        // Another instance can now claim the completed phase
        assert!(tracker
            .reserve("CAB-1709", 1, "t99999-beef", "other")
            .is_ok());
    }

    #[test]
    fn test_release_success() {
        let tracker = ClaimTracker::new();
        tracker
            .reserve("CAB-1709", 1, "t48217-a3f2", "macbook")
            .unwrap();
        let (found, owner_ok) = tracker.release("CAB-1709", 1, "t48217-a3f2", false);
        assert!(found);
        assert!(owner_ok);
        assert_eq!(tracker.count(), 0); // Removed (not completed)
    }

    #[test]
    fn test_release_completed_keeps_entry() {
        let tracker = ClaimTracker::new();
        tracker
            .reserve("CAB-1709", 1, "t48217-a3f2", "macbook")
            .unwrap();
        let (found, owner_ok) = tracker.release("CAB-1709", 1, "t48217-a3f2", true);
        assert!(found);
        assert!(owner_ok);
        assert_eq!(tracker.count(), 1); // Kept as completed
        let claims = tracker.list();
        assert!(claims[0].completed);
    }

    #[test]
    fn test_release_wrong_owner() {
        let tracker = ClaimTracker::new();
        tracker
            .reserve("CAB-1709", 1, "t48217-a3f2", "macbook")
            .unwrap();
        let (found, owner_ok) = tracker.release("CAB-1709", 1, "t99999-beef", false);
        assert!(found);
        assert!(!owner_ok);
        assert_eq!(tracker.count(), 1); // Still claimed
    }

    #[test]
    fn test_release_not_found() {
        let tracker = ClaimTracker::new();
        let (found, _) = tracker.release("CAB-9999", 1, "owner", false);
        assert!(!found);
    }

    #[test]
    fn test_heartbeat_success() {
        let tracker = ClaimTracker::new();
        tracker
            .reserve("CAB-1709", 1, "t48217-a3f2", "macbook")
            .unwrap();
        std::thread::sleep(std::time::Duration::from_millis(10));
        let (found, owner_ok) = tracker.heartbeat("CAB-1709", 1, "t48217-a3f2");
        assert!(found);
        assert!(owner_ok);
    }

    #[test]
    fn test_heartbeat_wrong_owner() {
        let tracker = ClaimTracker::new();
        tracker
            .reserve("CAB-1709", 1, "t48217-a3f2", "macbook")
            .unwrap();
        let (found, owner_ok) = tracker.heartbeat("CAB-1709", 1, "t99999-beef");
        assert!(found);
        assert!(!owner_ok);
    }

    #[test]
    fn test_heartbeat_not_found() {
        let tracker = ClaimTracker::new();
        let (found, _) = tracker.heartbeat("CAB-9999", 1, "owner");
        assert!(!found);
    }

    #[test]
    fn test_list_sorted() {
        let tracker = ClaimTracker::new();
        tracker.reserve("CAB-1800", 2, "owner-c", "host").unwrap();
        tracker.reserve("CAB-1709", 1, "owner-a", "host").unwrap();
        tracker.reserve("CAB-1709", 3, "owner-b", "host").unwrap();

        let claims = tracker.list();
        assert_eq!(claims.len(), 3);
        assert_eq!(claims[0].mega_id, "CAB-1709");
        assert_eq!(claims[0].phase_id, 1);
        assert_eq!(claims[1].mega_id, "CAB-1709");
        assert_eq!(claims[1].phase_id, 3);
        assert_eq!(claims[2].mega_id, "CAB-1800");
    }

    #[test]
    fn test_get_filters_by_mega() {
        let tracker = ClaimTracker::new();
        tracker.reserve("CAB-1709", 1, "owner-a", "host").unwrap();
        tracker.reserve("CAB-1709", 2, "owner-b", "host").unwrap();
        tracker.reserve("CAB-1800", 1, "owner-c", "host").unwrap();

        let claims = tracker.get("CAB-1709");
        assert_eq!(claims.len(), 2);
        assert_eq!(claims[0].phase_id, 1);
        assert_eq!(claims[1].phase_id, 2);

        let claims = tracker.get("CAB-9999");
        assert!(claims.is_empty());
    }

    #[test]
    fn test_stale_detection() {
        // We can't easily test 2h timeout without mocking time,
        // but we can verify the is_stale function directly
        let now = Instant::now();
        let fresh_entry = ClaimEntry {
            mega_id: "CAB-1709".to_string(),
            phase_id: 1,
            owner: "owner".to_string(),
            hostname: "host".to_string(),
            claimed_at: now,
            last_heartbeat: now,
            completed: false,
        };
        assert!(!is_stale(&fresh_entry, now));

        // Simulate 3h old entry
        let old_entry = ClaimEntry {
            mega_id: "CAB-1709".to_string(),
            phase_id: 1,
            owner: "owner".to_string(),
            hostname: "host".to_string(),
            claimed_at: now,
            last_heartbeat: now - std::time::Duration::from_secs(3 * 60 * 60),
            completed: false,
        };
        assert!(is_stale(&old_entry, now));
    }

    #[test]
    fn test_release_stale() {
        let tracker = ClaimTracker::new();
        // Fresh claim — should not be released
        tracker.reserve("CAB-1709", 1, "owner", "host").unwrap();
        let released = tracker.release_stale();
        assert_eq!(released, 0);
        assert_eq!(tracker.count(), 1);
    }

    #[test]
    fn test_reserve_reclaims_stale() {
        let tracker = ClaimTracker::new();
        // Insert a claim and manually make it stale
        {
            let mut claims = tracker.claims.write();
            let now = Instant::now();
            claims.insert(
                "CAB-1709:1".to_string(),
                ClaimEntry {
                    mega_id: "CAB-1709".to_string(),
                    phase_id: 1,
                    owner: "old-owner".to_string(),
                    hostname: "old-host".to_string(),
                    claimed_at: now,
                    last_heartbeat: now - std::time::Duration::from_secs(3 * 60 * 60),
                    completed: false,
                },
            );
        }
        // New reservation should succeed because old claim is stale
        assert!(tracker
            .reserve("CAB-1709", 1, "new-owner", "new-host")
            .is_ok());
        let claims = tracker.get("CAB-1709");
        assert_eq!(claims[0].owner, "new-owner");
    }

    #[test]
    fn test_concurrent_reserves() {
        use std::sync::Arc;
        use std::thread;

        let tracker = Arc::new(ClaimTracker::new());
        let mut handles = vec![];

        // 10 threads try to reserve the same phase simultaneously
        for i in 0..10 {
            let t = Arc::clone(&tracker);
            handles.push(thread::spawn(move || {
                t.reserve("CAB-1709", 1, &format!("owner-{}", i), "host")
                    .is_ok()
            }));
        }

        let results: Vec<bool> = handles.into_iter().map(|h| h.join().unwrap()).collect();
        let success_count = results.iter().filter(|&&r| r).count();

        // Exactly one should succeed
        assert_eq!(success_count, 1);
        assert_eq!(tracker.count(), 1);
    }

    #[test]
    fn test_active_count_excludes_completed() {
        let tracker = ClaimTracker::new();
        tracker.reserve("CAB-1709", 1, "owner-a", "host").unwrap();
        tracker.reserve("CAB-1709", 2, "owner-b", "host").unwrap();
        assert_eq!(tracker.active_count(), 2);

        tracker.release("CAB-1709", 1, "owner-a", true); // complete
        assert_eq!(tracker.count(), 2); // still in map
        assert_eq!(tracker.active_count(), 1); // but not active
    }

    #[test]
    fn test_claim_key_format() {
        assert_eq!(claim_key("CAB-1709", 1), "CAB-1709:1");
        assert_eq!(claim_key("CAB-1800", 42), "CAB-1800:42");
    }
}
