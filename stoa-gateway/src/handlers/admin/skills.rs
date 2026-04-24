//! Skills admin endpoints (CAB-1365, CAB-1366, CAB-1542, CAB-1551).

use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::IntoResponse,
    Json,
};
use serde::{Deserialize, Serialize};

use crate::state::AppState;

#[derive(Serialize)]
pub struct SkillsStatusResponse {
    pub enabled: bool,
    pub cache_ttl_secs: u64,
    pub skill_count: usize,
}

/// GET /admin/skills/status
pub async fn skills_status(State(state): State<AppState>) -> Json<SkillsStatusResponse> {
    Json(SkillsStatusResponse {
        enabled: state.config.skill_context_enabled,
        cache_ttl_secs: state.config.skill_cache_ttl_secs,
        skill_count: state.skill_resolver.skill_count(),
    })
}

/// GET /admin/skills/resolve?tenant_id=X&tool_ref=Y&user_ref=Z
pub async fn skills_resolve(
    State(state): State<AppState>,
    axum::extract::Query(params): axum::extract::Query<SkillResolveParams>,
) -> impl IntoResponse {
    use crate::skills::context::SkillContext;

    let resolved = state.skill_resolver.resolve(
        &params.tenant_id,
        params.tool_ref.as_deref(),
        params.user_ref.as_deref(),
    );
    let ctx = SkillContext::from_resolved(&resolved);
    Json(serde_json::json!({
        "tenant_id": params.tenant_id,
        "tool_ref": params.tool_ref,
        "user_ref": params.user_ref,
        "skills": ctx.skills,
        "merged_instructions": ctx.merged_instructions,
        "count": ctx.count,
    }))
}

#[derive(Deserialize)]
pub struct SkillResolveParams {
    pub tenant_id: String,
    pub tool_ref: Option<String>,
    pub user_ref: Option<String>,
}

/// GET /admin/skills — list all stored skills (CAB-1366)
pub async fn skills_list(State(state): State<AppState>) -> Json<Vec<SkillAdminEntry>> {
    let entries: Vec<SkillAdminEntry> = state
        .skill_resolver
        .list_all()
        .into_iter()
        .map(|s| SkillAdminEntry {
            key: s.key,
            name: s.name,
            description: s.description,
            tenant_id: s.tenant_id,
            scope: s.scope.to_string(),
            priority: s.priority,
            instructions: s.instructions,
            tool_ref: s.tool_ref,
            user_ref: s.user_ref,
            enabled: s.enabled,
        })
        .collect();
    Json(entries)
}

/// POST /admin/skills — upsert a skill (CAB-1366)
pub async fn skills_upsert(
    State(state): State<AppState>,
    Json(payload): Json<SkillUpsertPayload>,
) -> impl IntoResponse {
    use crate::skills::resolver::{SkillScope, StoredSkill};

    let scope = match SkillScope::from_crd(&payload.scope) {
        Some(s) => s,
        None => {
            return (
                StatusCode::BAD_REQUEST,
                Json(serde_json::json!({"error": format!("invalid scope: {}", payload.scope)})),
            )
                .into_response();
        }
    };

    let skill = StoredSkill {
        key: payload.key.clone(),
        name: payload.name,
        description: payload.description,
        tenant_id: payload.tenant_id,
        scope,
        priority: payload.priority.unwrap_or(50),
        instructions: payload.instructions,
        tool_ref: payload.tool_ref,
        user_ref: payload.user_ref,
        enabled: payload.enabled.unwrap_or(true),
    };

    state.skill_resolver.upsert(skill);
    (
        StatusCode::OK,
        Json(serde_json::json!({"key": payload.key})),
    )
        .into_response()
}

/// GET /admin/skills/:id — get a single skill by key (CAB-1542)
pub async fn skills_get_by_id(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> impl IntoResponse {
    match state.skill_resolver.get(&id) {
        Some(s) => Json(SkillAdminEntry {
            key: s.key,
            name: s.name,
            description: s.description,
            tenant_id: s.tenant_id,
            scope: s.scope.to_string(),
            priority: s.priority,
            instructions: s.instructions,
            tool_ref: s.tool_ref,
            user_ref: s.user_ref,
            enabled: s.enabled,
        })
        .into_response(),
        None => (
            StatusCode::NOT_FOUND,
            Json(serde_json::json!({"error": "skill not found", "key": id})),
        )
            .into_response(),
    }
}

/// POST /admin/skills/sync — bulk replace all skills (CAB-1542)
pub async fn skills_sync(
    State(state): State<AppState>,
    Json(payload): Json<Vec<SkillUpsertPayload>>,
) -> impl IntoResponse {
    use crate::skills::resolver::{SkillScope, StoredSkill};

    let mut skills = Vec::with_capacity(payload.len());
    for item in payload {
        let scope = match SkillScope::from_crd(&item.scope) {
            Some(s) => s,
            None => {
                return (
                    StatusCode::BAD_REQUEST,
                    Json(serde_json::json!({"error": format!("invalid scope: {}", item.scope), "key": item.key})),
                )
                    .into_response();
            }
        };
        skills.push(StoredSkill {
            key: item.key,
            name: item.name,
            description: item.description,
            tenant_id: item.tenant_id,
            scope,
            priority: item.priority.unwrap_or(50),
            instructions: item.instructions,
            tool_ref: item.tool_ref,
            user_ref: item.user_ref,
            enabled: item.enabled.unwrap_or(true),
        });
    }

    let count = skills.len();
    state.skill_resolver.sync(skills);
    (StatusCode::OK, Json(serde_json::json!({"synced": count}))).into_response()
}

/// DELETE /admin/skills?key=X — remove a skill by key (CAB-1366, legacy)
pub async fn skills_delete(
    State(state): State<AppState>,
    axum::extract::Query(params): axum::extract::Query<SkillDeleteParams>,
) -> impl IntoResponse {
    if state.skill_resolver.remove(&params.key) {
        StatusCode::NO_CONTENT
    } else {
        StatusCode::NOT_FOUND
    }
}

/// PUT /admin/skills/:id — update an existing skill (CAB-1551)
pub async fn skills_update(
    State(state): State<AppState>,
    Path(id): Path<String>,
    Json(payload): Json<SkillUpsertPayload>,
) -> impl IntoResponse {
    use crate::skills::resolver::{SkillScope, StoredSkill};

    // Verify the skill exists
    if state.skill_resolver.get(&id).is_none() {
        return (
            StatusCode::NOT_FOUND,
            Json(serde_json::json!({"error": "skill not found", "key": id})),
        )
            .into_response();
    }

    let scope = match SkillScope::from_crd(&payload.scope) {
        Some(s) => s,
        None => {
            return (
                StatusCode::BAD_REQUEST,
                Json(serde_json::json!({"error": format!("invalid scope: {}", payload.scope)})),
            )
                .into_response();
        }
    };

    let skill = StoredSkill {
        key: id.clone(),
        name: payload.name,
        description: payload.description,
        tenant_id: payload.tenant_id,
        scope,
        priority: payload.priority.unwrap_or(50),
        instructions: payload.instructions,
        tool_ref: payload.tool_ref,
        user_ref: payload.user_ref,
        enabled: payload.enabled.unwrap_or(true),
    };

    state.skill_resolver.upsert(skill);
    Json(serde_json::json!({"key": id, "updated": true})).into_response()
}

/// DELETE /admin/skills/:id — remove a skill by path param (CAB-1551)
pub async fn skills_delete_by_id(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> impl IntoResponse {
    if state.skill_resolver.remove(&id) {
        StatusCode::NO_CONTENT
    } else {
        StatusCode::NOT_FOUND
    }
}

/// GET /admin/skills/:id/health — skill health + circuit breaker status (CAB-1551)
///
/// GW-1 P1-5: this used to call `state.skill_health.stats(&id)` which
/// *creates* counters + a circuit breaker for any probed key, giving an
/// unbounded memory growth vector and returning a fake-positive
/// `success_rate: 1.0` / `closed` for skills that don't exist. Now we
/// 404 when the resolver has no skill under `id`, and use
/// `SkillHealthTracker::stats_opt` to read without mutating. Known
/// skills that have never been called get an honest zero-stats shape.
pub async fn skills_health(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> impl IntoResponse {
    use crate::skills::health::SkillHealthStats;

    if state.skill_resolver.get(&id).is_none() {
        return (
            StatusCode::NOT_FOUND,
            Json(serde_json::json!({"error": "skill not found", "key": id})),
        )
            .into_response();
    }

    // Skill exists: return whatever has been recorded so far. A missing
    // stats entry (skill never executed) is honestly reported as zero
    // counts and a "closed" CB, without inserting anything.
    let stats = state
        .skill_health
        .stats_opt(&id)
        .unwrap_or(SkillHealthStats {
            skill_key: id.clone(),
            success_count: 0,
            failure_count: 0,
            circuit_state: "closed".to_string(),
            total_calls: 0,
            success_rate: 1.0,
        });
    Json(stats).into_response()
}

/// GET /admin/skills/health — health stats for all tracked skills (CAB-1551)
pub async fn skills_health_all(State(state): State<AppState>) -> impl IntoResponse {
    Json(state.skill_health.stats_all())
}

/// POST /admin/skills/:id/health/reset — reset circuit breaker for a skill (CAB-1551)
///
/// GW-1 P1-5: symmetric with `skills_health`, we 404 for unknown skills
/// up-front so admins can distinguish "no such skill" (resolver miss)
/// from "skill exists but has no CB to reset yet" (never called).
pub async fn skills_health_reset(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> impl IntoResponse {
    if state.skill_resolver.get(&id).is_none() {
        return (
            StatusCode::NOT_FOUND,
            Json(serde_json::json!({"error": "skill not found", "key": id})),
        )
            .into_response();
    }

    if state.skill_health.reset_circuit_breaker(&id) {
        Json(serde_json::json!({"key": id, "circuit_state": "closed"})).into_response()
    } else {
        // Skill exists per the resolver, but it has no circuit breaker
        // because nothing has been recorded yet. Still a clean 200 — the
        // caller's intent (ensure the CB is closed) is satisfied.
        Json(serde_json::json!({
            "key": id,
            "circuit_state": "closed",
            "noop": true,
        }))
        .into_response()
    }
}

#[derive(Serialize)]
pub struct SkillAdminEntry {
    pub key: String,
    pub name: String,
    pub description: Option<String>,
    pub tenant_id: String,
    pub scope: String,
    pub priority: u8,
    pub instructions: Option<String>,
    pub tool_ref: Option<String>,
    pub user_ref: Option<String>,
    pub enabled: bool,
}

#[derive(Deserialize)]
pub struct SkillUpsertPayload {
    pub key: String,
    pub name: String,
    pub description: Option<String>,
    pub tenant_id: String,
    pub scope: String,
    pub priority: Option<u8>,
    pub instructions: Option<String>,
    pub tool_ref: Option<String>,
    pub user_ref: Option<String>,
    pub enabled: Option<bool>,
}

#[derive(Deserialize)]
pub struct SkillDeleteParams {
    pub key: String,
}

#[cfg(test)]
mod tests {
    //! GW-1 P1-5: `GET /admin/skills/:id/health` and `POST
    //! /admin/skills/:id/health/reset` must 404 for unknown skills and
    //! must not create counters / circuit breakers as a side effect of
    //! a read.
    //!
    //! `test_helpers::build_full_admin_router` does not wire the
    //! `/skills/*` routes (tracked as GW-1 P2-test-1), so these tests
    //! build a minimal inline router per scenario.

    use axum::{
        body::Body,
        http::{Request, StatusCode},
        middleware,
        routing::{get, post},
        Router,
    };
    use tower::ServiceExt;

    use super::{skills_health, skills_health_reset};
    use crate::handlers::admin::admin_auth;
    use crate::handlers::admin::test_helpers::create_test_state;
    use crate::skills::resolver::{SkillScope, StoredSkill};
    use crate::state::AppState;

    fn seed_skill(state: &AppState, key: &str) {
        state.skill_resolver.upsert(StoredSkill {
            key: key.to_string(),
            name: "seeded".into(),
            description: None,
            tenant_id: "acme".into(),
            scope: SkillScope::Tenant,
            priority: 50,
            instructions: None,
            tool_ref: None,
            user_ref: None,
            enabled: true,
        });
    }

    fn router_with_health(state: AppState) -> Router {
        Router::new()
            .route("/skills/:id/health", get(skills_health))
            .route("/skills/:id/health/reset", post(skills_health_reset))
            .layer(middleware::from_fn_with_state(state.clone(), admin_auth))
            .with_state(state)
    }

    fn auth_req(method: &str, uri: &str) -> Request<Body> {
        Request::builder()
            .method(method)
            .uri(uri)
            .header("Authorization", "Bearer secret")
            .body(Body::empty())
            .unwrap()
    }

    // Primary P1-5 regression: unknown skill → 404, no counters/CB created.
    #[tokio::test]
    async fn regression_skills_health_returns_404_for_unknown_skill_and_does_not_grow_state() {
        let state = create_test_state(Some("secret"));
        let app = router_with_health(state.clone());

        // Hit the endpoint 100 times with distinct UUID-ish keys.
        for i in 0..100 {
            let resp = app
                .clone()
                .oneshot(auth_req("GET", &format!("/skills/ghost-{}/health", i)))
                .await
                .unwrap();
            assert_eq!(resp.status(), StatusCode::NOT_FOUND);
        }

        // Tracker must still be empty — no side-effect insertions.
        assert!(state.skill_health.stats_all().is_empty());
    }

    // A known skill with no recorded calls yet: 200 OK with honest zero
    // counts, still no side-effect insertion.
    #[tokio::test]
    async fn test_skills_health_returns_zero_stats_for_known_skill_without_growing_state() {
        let state = create_test_state(Some("secret"));
        seed_skill(&state, "acme/seen");
        let app = router_with_health(state.clone());

        let resp = app
            .oneshot(auth_req("GET", "/skills/acme%2Fseen/health"))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let bytes = axum::body::to_bytes(resp.into_body(), 64 * 1024)
            .await
            .unwrap();
        let json: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(json["success_count"], 0);
        assert_eq!(json["failure_count"], 0);
        assert_eq!(json["circuit_state"], "closed");

        // Read did not insert anything — tracker still reports empty.
        assert!(state.skill_health.stats_all().is_empty());
    }

    // After a real record, the health read must reflect the recorded
    // counts. Covers the "skill exists AND has history" path.
    #[tokio::test]
    async fn test_skills_health_reports_recorded_counts_for_known_skill() {
        let state = create_test_state(Some("secret"));
        seed_skill(&state, "acme/busy");
        state.skill_health.record_success("acme/busy");
        state.skill_health.record_success("acme/busy");
        state.skill_health.record_failure("acme/busy");
        let app = router_with_health(state);

        let resp = app
            .oneshot(auth_req("GET", "/skills/acme%2Fbusy/health"))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let bytes = axum::body::to_bytes(resp.into_body(), 64 * 1024)
            .await
            .unwrap();
        let json: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(json["success_count"], 2);
        assert_eq!(json["failure_count"], 1);
        assert_eq!(json["total_calls"], 3);
    }

    // /health/reset on an unknown skill → 404 AND no side effect.
    #[tokio::test]
    async fn test_skills_health_reset_returns_404_for_unknown_skill() {
        let state = create_test_state(Some("secret"));
        let app = router_with_health(state.clone());

        let resp = app
            .oneshot(auth_req("POST", "/skills/ghost/health/reset"))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::NOT_FOUND);
        assert!(state.skill_health.stats_all().is_empty());
    }

    // /health/reset on a known skill with no prior call → 200 with noop=true.
    // Distinguishes "skill unknown" from "skill has no CB yet"
    // without exposing the implementation detail to the client.
    #[tokio::test]
    async fn test_skills_health_reset_noop_on_known_skill_without_prior_call() {
        let state = create_test_state(Some("secret"));
        seed_skill(&state, "acme/untouched");
        let app = router_with_health(state);

        let resp = app
            .oneshot(auth_req("POST", "/skills/acme%2Funtouched/health/reset"))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let bytes = axum::body::to_bytes(resp.into_body(), 64 * 1024)
            .await
            .unwrap();
        let json: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(json["circuit_state"], "closed");
        assert_eq!(json["noop"], true);
    }
}
