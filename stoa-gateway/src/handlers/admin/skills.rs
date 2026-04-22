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
pub async fn skills_health(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> impl IntoResponse {
    Json(state.skill_health.stats(&id))
}

/// GET /admin/skills/health — health stats for all tracked skills (CAB-1551)
pub async fn skills_health_all(State(state): State<AppState>) -> impl IntoResponse {
    Json(state.skill_health.stats_all())
}

/// POST /admin/skills/:id/health/reset — reset circuit breaker for a skill (CAB-1551)
pub async fn skills_health_reset(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> impl IntoResponse {
    if state.skill_health.reset_circuit_breaker(&id) {
        Json(serde_json::json!({"key": id, "circuit_state": "closed"})).into_response()
    } else {
        (
            StatusCode::NOT_FOUND,
            Json(serde_json::json!({"error": "no circuit breaker found", "key": id})),
        )
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
