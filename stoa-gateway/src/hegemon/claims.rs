//! Claim Coordination Endpoints (CAB-1718)
//!
//! Atomic claim reservation for HEGEMON multi-agent phase ownership.
//! Replaces local `mkdir`-based locks with gateway-coordinated state.
//!
//! Endpoints:
//! - `POST /hegemon/claims/:mega_id/reserve` — atomic reserve (409 on conflict)
//! - `POST /hegemon/claims/:mega_id/release` — owner-validated release
//! - `POST /hegemon/claims/:mega_id/heartbeat` — extend claim liveness
//! - `GET  /hegemon/claims` — list all active claims
//! - `GET  /hegemon/claims/:mega_id` — single MEGA claim state

use std::collections::HashMap;
use std::sync::Arc;

use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::IntoResponse,
    Json,
};
use chrono::{DateTime, Utc};
use parking_lot::RwLock;
use serde::{Deserialize, Serialize};
use tracing::{info, warn};

/// Stale claim timeout: claims without heartbeat for 2 hours are auto-released.
const STALE_TIMEOUT_SECS: i64 = 7200;

/// Shared claim store — in-memory, coordinated across all workers via HTTP.
#[derive(Debug, Clone)]
pub struct ClaimStore {
    inner: Arc<RwLock<HashMap<String, MegaClaim>>>,
}

/// Top-level MEGA claim containing phase-level ownership.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MegaClaim {
    pub mega_id: String,
    pub title: Option<String>,
    pub created_at: DateTime<Utc>,
    pub phases: Vec<PhaseClaim>,
}

/// Single phase claim within a MEGA.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PhaseClaim {
    pub phase_id: u32,
    pub name: Option<String>,
    pub owner: Option<String>,
    pub claimed_at: Option<DateTime<Utc>>,
    pub last_heartbeat: Option<DateTime<Utc>>,
    pub hostname: Option<String>,
    pub branch: Option<String>,
    pub completed_at: Option<DateTime<Utc>>,
}

/// Request body for reserve.
#[derive(Debug, Deserialize)]
pub struct ReserveRequest {
    pub phase_id: u32,
    pub owner: String,
    pub hostname: Option<String>,
    pub branch: Option<String>,
    /// Optional: initialize MEGA claim with title and phases if not yet created.
    pub title: Option<String>,
    pub phases: Option<Vec<PhaseInit>>,
}

/// Phase initialization data (used when MEGA claim doesn't exist yet).
#[derive(Debug, Deserialize)]
pub struct PhaseInit {
    pub phase_id: u32,
    pub name: Option<String>,
}

/// Request body for release.
#[derive(Debug, Deserialize)]
pub struct ReleaseRequest {
    pub phase_id: u32,
    pub owner: String,
}

/// Request body for heartbeat.
#[derive(Debug, Deserialize)]
pub struct HeartbeatRequest {
    pub phase_id: u32,
    pub owner: String,
}

/// Structured error response.
#[derive(Debug, Serialize)]
pub struct ClaimError {
    pub error: String,
    pub code: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub current_owner: Option<String>,
}

impl Default for ClaimStore {
    fn default() -> Self {
        Self::new()
    }
}

impl ClaimStore {
    pub fn new() -> Self {
        Self {
            inner: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    /// Spawn background task that releases stale claims every 60 seconds.
    pub fn spawn_stale_reaper(store: Arc<ClaimStore>) {
        tokio::spawn(async move {
            let mut interval = tokio::time::interval(tokio::time::Duration::from_secs(60));
            loop {
                interval.tick().await;
                store.release_stale_claims();
            }
        });
    }

    /// Release claims with no heartbeat for > STALE_TIMEOUT_SECS.
    fn release_stale_claims(&self) {
        let now = Utc::now();
        let mut store = self.inner.write();
        let mut released = 0u32;
        for mega in store.values_mut() {
            for phase in &mut mega.phases {
                if phase.owner.is_some() && phase.completed_at.is_none() {
                    let last_activity = phase
                        .last_heartbeat
                        .or(phase.claimed_at)
                        .unwrap_or(mega.created_at);
                    if (now - last_activity).num_seconds() > STALE_TIMEOUT_SECS {
                        warn!(
                            mega_id = %mega.mega_id,
                            phase_id = phase.phase_id,
                            owner = ?phase.owner,
                            "Auto-releasing stale claim (no heartbeat for >2h)"
                        );
                        phase.owner = None;
                        phase.claimed_at = None;
                        phase.last_heartbeat = None;
                        phase.hostname = None;
                        phase.branch = None;
                        released += 1;
                    }
                }
            }
        }
        if released > 0 {
            info!(released, "Stale claims auto-released");
        }
    }

    /// Flush all claims to JSON bytes (for graceful shutdown persistence).
    pub fn flush_to_json(&self) -> Vec<u8> {
        let store = self.inner.read();
        let claims: Vec<&MegaClaim> = store.values().collect();
        serde_json::to_vec_pretty(&claims).unwrap_or_default()
    }

    /// Restore claims from JSON bytes (startup load).
    pub fn load_from_json(&self, data: &[u8]) {
        if let Ok(claims) = serde_json::from_slice::<Vec<MegaClaim>>(data) {
            let mut store = self.inner.write();
            for claim in claims {
                store.insert(claim.mega_id.clone(), claim);
            }
            info!(count = store.len(), "Claims restored from persistence");
        }
    }
}

// === Handlers ===

/// POST /hegemon/claims/:mega_id/reserve
///
/// Atomically reserve a phase. Returns 200 on success, 409 on conflict.
pub async fn reserve_claim(
    State(store): State<Arc<ClaimStore>>,
    Path(mega_id): Path<String>,
    Json(req): Json<ReserveRequest>,
) -> impl IntoResponse {
    let now = Utc::now();
    let mut map = store.inner.write();

    // Initialize MEGA claim if it doesn't exist yet
    let mega = map.entry(mega_id.clone()).or_insert_with(|| {
        let phases = req
            .phases
            .as_ref()
            .map(|inits| {
                inits
                    .iter()
                    .map(|p| PhaseClaim {
                        phase_id: p.phase_id,
                        name: p.name.clone(),
                        owner: None,
                        claimed_at: None,
                        last_heartbeat: None,
                        hostname: None,
                        branch: None,
                        completed_at: None,
                    })
                    .collect()
            })
            .unwrap_or_default();
        MegaClaim {
            mega_id: mega_id.clone(),
            title: req.title.clone(),
            created_at: now,
            phases,
        }
    });

    // Find the requested phase
    let phase = mega.phases.iter_mut().find(|p| p.phase_id == req.phase_id);
    let phase = match phase {
        Some(p) => p,
        None => {
            // Auto-create the phase if it doesn't exist
            mega.phases.push(PhaseClaim {
                phase_id: req.phase_id,
                name: None,
                owner: None,
                claimed_at: None,
                last_heartbeat: None,
                hostname: None,
                branch: None,
                completed_at: None,
            });
            mega.phases.last_mut().expect("just pushed")
        }
    };

    // Check if already claimed by someone else
    if let Some(ref current_owner) = phase.owner {
        if current_owner != &req.owner {
            return (
                StatusCode::CONFLICT,
                Json(ClaimError {
                    error: format!(
                        "Phase {} already claimed by {}",
                        req.phase_id, current_owner
                    ),
                    code: "CLAIM_CONFLICT".to_string(),
                    current_owner: Some(current_owner.clone()),
                }),
            )
                .into_response();
        }
        // Same owner re-reserving — treat as heartbeat
        phase.last_heartbeat = Some(now);
        return (StatusCode::OK, Json(mega.clone())).into_response();
    }

    // Reserve it
    phase.owner = Some(req.owner.clone());
    phase.claimed_at = Some(now);
    phase.last_heartbeat = Some(now);
    phase.hostname = req.hostname;
    phase.branch = req.branch;

    info!(
        mega_id = %mega.mega_id,
        phase_id = req.phase_id,
        owner = %req.owner,
        "Phase claimed"
    );

    (StatusCode::OK, Json(mega.clone())).into_response()
}

/// POST /hegemon/claims/:mega_id/release
///
/// Release a phase claim. Owner must match.
pub async fn release_claim(
    State(store): State<Arc<ClaimStore>>,
    Path(mega_id): Path<String>,
    Json(req): Json<ReleaseRequest>,
) -> impl IntoResponse {
    let mut map = store.inner.write();

    let mega = match map.get_mut(&mega_id) {
        Some(m) => m,
        None => {
            return (
                StatusCode::NOT_FOUND,
                Json(ClaimError {
                    error: format!("MEGA {} not found", mega_id),
                    code: "NOT_FOUND".to_string(),
                    current_owner: None,
                }),
            )
                .into_response();
        }
    };

    let phase = mega.phases.iter_mut().find(|p| p.phase_id == req.phase_id);
    let phase = match phase {
        Some(p) => p,
        None => {
            return (
                StatusCode::NOT_FOUND,
                Json(ClaimError {
                    error: format!("Phase {} not found", req.phase_id),
                    code: "PHASE_NOT_FOUND".to_string(),
                    current_owner: None,
                }),
            )
                .into_response();
        }
    };

    // Owner check
    match &phase.owner {
        Some(current) if current != &req.owner => {
            return (
                StatusCode::FORBIDDEN,
                Json(ClaimError {
                    error: "Only the owner can release a claim".to_string(),
                    code: "NOT_OWNER".to_string(),
                    current_owner: Some(current.clone()),
                }),
            )
                .into_response();
        }
        None => {
            return (
                StatusCode::OK,
                Json(serde_json::json!({"status": "already_released"})),
            )
                .into_response();
        }
        _ => {}
    }

    // Release
    phase.owner = None;
    phase.claimed_at = None;
    phase.last_heartbeat = None;
    phase.hostname = None;
    phase.branch = None;
    phase.completed_at = Some(Utc::now());

    info!(
        mega_id = %mega.mega_id,
        phase_id = req.phase_id,
        owner = %req.owner,
        "Phase released"
    );

    (StatusCode::OK, Json(mega.clone())).into_response()
}

/// POST /hegemon/claims/:mega_id/heartbeat
///
/// Extend claim liveness. Owner must match.
pub async fn heartbeat_claim(
    State(store): State<Arc<ClaimStore>>,
    Path(mega_id): Path<String>,
    Json(req): Json<HeartbeatRequest>,
) -> impl IntoResponse {
    let mut map = store.inner.write();

    let mega = match map.get_mut(&mega_id) {
        Some(m) => m,
        None => {
            return (
                StatusCode::NOT_FOUND,
                Json(ClaimError {
                    error: format!("MEGA {} not found", mega_id),
                    code: "NOT_FOUND".to_string(),
                    current_owner: None,
                }),
            )
                .into_response();
        }
    };

    let phase = mega.phases.iter_mut().find(|p| p.phase_id == req.phase_id);
    let phase = match phase {
        Some(p) => p,
        None => {
            return (
                StatusCode::NOT_FOUND,
                Json(ClaimError {
                    error: format!("Phase {} not found", req.phase_id),
                    code: "PHASE_NOT_FOUND".to_string(),
                    current_owner: None,
                }),
            )
                .into_response();
        }
    };

    match &phase.owner {
        Some(current) if current != &req.owner => {
            return (
                StatusCode::FORBIDDEN,
                Json(ClaimError {
                    error: "Only the owner can heartbeat".to_string(),
                    code: "NOT_OWNER".to_string(),
                    current_owner: Some(current.clone()),
                }),
            )
                .into_response();
        }
        None => {
            return (
                StatusCode::CONFLICT,
                Json(ClaimError {
                    error: "Phase is not claimed".to_string(),
                    code: "NOT_CLAIMED".to_string(),
                    current_owner: None,
                }),
            )
                .into_response();
        }
        _ => {}
    }

    phase.last_heartbeat = Some(Utc::now());

    (StatusCode::OK, Json(serde_json::json!({"status": "ok"}))).into_response()
}

/// GET /hegemon/claims
///
/// List all active MEGA claims.
pub async fn list_claims(State(store): State<Arc<ClaimStore>>) -> impl IntoResponse {
    let map = store.inner.read();
    let claims: Vec<MegaClaim> = map.values().cloned().collect();
    Json(claims)
}

/// GET /hegemon/claims/:mega_id
///
/// Get a single MEGA claim state.
pub async fn get_claim(
    State(store): State<Arc<ClaimStore>>,
    Path(mega_id): Path<String>,
) -> impl IntoResponse {
    let map = store.inner.read();
    match map.get(&mega_id) {
        Some(mega) => (StatusCode::OK, Json(serde_json::to_value(mega).unwrap())).into_response(),
        None => (
            StatusCode::NOT_FOUND,
            Json(ClaimError {
                error: format!("MEGA {} not found", mega_id),
                code: "NOT_FOUND".to_string(),
                current_owner: None,
            }),
        )
            .into_response(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{
        body::Body,
        http::{Method, Request},
        routing::{get, post},
        Router,
    };
    use tower::ServiceExt;

    fn test_store() -> Arc<ClaimStore> {
        Arc::new(ClaimStore::new())
    }

    fn test_router(store: Arc<ClaimStore>) -> Router {
        Router::new()
            .route("/hegemon/claims", get(list_claims))
            .route("/hegemon/claims/:mega_id", get(get_claim))
            .route("/hegemon/claims/:mega_id/reserve", post(reserve_claim))
            .route("/hegemon/claims/:mega_id/release", post(release_claim))
            .route("/hegemon/claims/:mega_id/heartbeat", post(heartbeat_claim))
            .with_state(store)
    }

    async fn json_response(resp: axum::response::Response) -> serde_json::Value {
        let body = axum::body::to_bytes(resp.into_body(), 1024 * 1024)
            .await
            .unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    #[tokio::test]
    async fn reserve_returns_200_first_call() {
        let store = test_store();
        let app = test_router(store);

        let body = serde_json::json!({
            "phase_id": 1,
            "owner": "t12345-abcd",
            "hostname": "test-host",
            "title": "Test MEGA",
            "phases": [{"phase_id": 1, "name": "Phase 1"}, {"phase_id": 2, "name": "Phase 2"}]
        });

        let resp = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/hegemon/claims/CAB-1234/reserve")
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_vec(&body).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(resp.status(), StatusCode::OK);
        let json = json_response(resp).await;
        assert_eq!(json["mega_id"], "CAB-1234");
        assert_eq!(json["phases"][0]["owner"], "t12345-abcd");
    }

    #[tokio::test]
    async fn reserve_returns_409_on_conflict() {
        let store = test_store();
        let app = test_router(store.clone());

        let body1 = serde_json::json!({
            "phase_id": 1,
            "owner": "t12345-abcd",
            "phases": [{"phase_id": 1}]
        });
        let body2 = serde_json::json!({
            "phase_id": 1,
            "owner": "t99999-zzzz",
        });

        // First call succeeds
        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/hegemon/claims/CAB-1234/reserve")
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_vec(&body1).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);

        // Second call by different owner conflicts
        let resp = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/hegemon/claims/CAB-1234/reserve")
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_vec(&body2).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::CONFLICT);
        let json = json_response(resp).await;
        assert_eq!(json["code"], "CLAIM_CONFLICT");
        assert_eq!(json["current_owner"], "t12345-abcd");
    }

    #[tokio::test]
    async fn list_claims_shows_all_active() {
        let store = test_store();
        let app = test_router(store.clone());

        // Reserve a claim
        let body = serde_json::json!({
            "phase_id": 1,
            "owner": "t12345-abcd",
            "phases": [{"phase_id": 1}]
        });
        let _ = app
            .clone()
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/hegemon/claims/CAB-100/reserve")
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_vec(&body).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();

        // List claims
        let resp = app
            .oneshot(
                Request::builder()
                    .method(Method::GET)
                    .uri("/hegemon/claims")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let json = json_response(resp).await;
        let arr = json.as_array().unwrap();
        assert_eq!(arr.len(), 1);
        assert_eq!(arr[0]["mega_id"], "CAB-100");
    }

    #[tokio::test]
    async fn stale_claims_auto_release() {
        let store = ClaimStore::new();

        // Insert a claim with old heartbeat
        {
            let mut map = store.inner.write();
            map.insert(
                "CAB-OLD".to_string(),
                MegaClaim {
                    mega_id: "CAB-OLD".to_string(),
                    title: None,
                    created_at: Utc::now() - chrono::Duration::hours(3),
                    phases: vec![PhaseClaim {
                        phase_id: 1,
                        name: None,
                        owner: Some("t00001-dead".to_string()),
                        claimed_at: Some(Utc::now() - chrono::Duration::hours(3)),
                        last_heartbeat: Some(Utc::now() - chrono::Duration::hours(3)),
                        hostname: None,
                        branch: None,
                        completed_at: None,
                    }],
                },
            );
        }

        store.release_stale_claims();

        let map = store.inner.read();
        let mega = map.get("CAB-OLD").unwrap();
        assert!(
            mega.phases[0].owner.is_none(),
            "Stale claim should be released"
        );
    }

    #[tokio::test]
    async fn release_requires_owner_match() {
        let store = test_store();
        let app = test_router(store.clone());

        // Reserve
        let reserve = serde_json::json!({
            "phase_id": 1,
            "owner": "t12345-abcd",
            "phases": [{"phase_id": 1}]
        });
        let _ = app
            .clone()
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/hegemon/claims/CAB-200/reserve")
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_vec(&reserve).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();

        // Release by wrong owner
        let release = serde_json::json!({
            "phase_id": 1,
            "owner": "t99999-zzzz",
        });
        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/hegemon/claims/CAB-200/release")
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_vec(&release).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::FORBIDDEN);

        // Release by correct owner
        let release_ok = serde_json::json!({
            "phase_id": 1,
            "owner": "t12345-abcd",
        });
        let resp = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/hegemon/claims/CAB-200/release")
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_vec(&release_ok).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn heartbeat_extends_liveness() {
        let store = test_store();
        let app = test_router(store.clone());

        // Reserve
        let reserve = serde_json::json!({
            "phase_id": 1,
            "owner": "t12345-abcd",
            "phases": [{"phase_id": 1}]
        });
        let _ = app
            .clone()
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/hegemon/claims/CAB-300/reserve")
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_vec(&reserve).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();

        // Heartbeat
        let hb = serde_json::json!({
            "phase_id": 1,
            "owner": "t12345-abcd",
        });
        let resp = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/hegemon/claims/CAB-300/heartbeat")
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_vec(&hb).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
    }

    #[test]
    fn flush_and_load_roundtrip() {
        let store = ClaimStore::new();
        {
            let mut map = store.inner.write();
            map.insert(
                "CAB-RT".to_string(),
                MegaClaim {
                    mega_id: "CAB-RT".to_string(),
                    title: Some("Roundtrip Test".to_string()),
                    created_at: Utc::now(),
                    phases: vec![PhaseClaim {
                        phase_id: 1,
                        name: Some("P1".to_string()),
                        owner: Some("t11111-aaaa".to_string()),
                        claimed_at: Some(Utc::now()),
                        last_heartbeat: Some(Utc::now()),
                        hostname: Some("host-1".to_string()),
                        branch: Some("feat/test".to_string()),
                        completed_at: None,
                    }],
                },
            );
        }

        let json = store.flush_to_json();
        assert!(!json.is_empty());

        let store2 = ClaimStore::new();
        store2.load_from_json(&json);
        let map = store2.inner.read();
        assert!(map.contains_key("CAB-RT"));
        assert_eq!(
            map["CAB-RT"].phases[0].owner.as_deref(),
            Some("t11111-aaaa")
        );
    }

    #[tokio::test]
    async fn get_claim_returns_404_for_unknown() {
        let store = test_store();
        let app = test_router(store);

        let resp = app
            .oneshot(
                Request::builder()
                    .method(Method::GET)
                    .uri("/hegemon/claims/CAB-NONEXIST")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    }
}
