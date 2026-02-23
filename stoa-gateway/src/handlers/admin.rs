//! Admin API handlers for Control Plane → Gateway communication.
//!
//! Endpoints:
//!   GET    /admin/health           - Gateway health + stats
//!   POST   /admin/apis             - Register/update an API route
//!   GET    /admin/apis             - List all API routes
//!   GET    /admin/apis/:id         - Get a single API route
//!   DELETE /admin/apis/:id         - Remove an API route
//!   POST   /admin/policies         - Register/update a policy
//!   GET    /admin/policies         - List all policies
//!   DELETE /admin/policies/:id     - Remove a policy
//!
//! All endpoints are protected by bearer token auth (admin_auth middleware).

use axum::{
    body::Body,
    extract::{Path, State},
    http::{header::AUTHORIZATION, Request, StatusCode},
    middleware::Next,
    response::{IntoResponse, Response},
    Json,
};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tracing::warn;
use uuid::Uuid;

use crate::proxy::credentials::{AuthType, BackendCredential};
use crate::proxy::dynamic::is_blocked_url;
use crate::routes::{ApiRoute, PolicyEntry};
use crate::state::AppState;
use crate::telemetry::deploy::DeployStep;
use crate::uac::binders::{mcp::McpBinder, rest::RestBinder, ProtocolBinder};
use crate::uac::UacContractSpec;

// =============================================================================
// Admin Auth Middleware
// =============================================================================

/// Bearer token authentication for admin API.
///
/// Validates the `Authorization: Bearer <token>` header against
/// `config.admin_api_token`. If no token is configured, returns 503
/// (admin API disabled -- no token configured).
pub async fn admin_auth(
    State(state): State<AppState>,
    request: Request<Body>,
    next: Next,
) -> Result<Response, Response> {
    let expected = match state.config.admin_api_token.as_deref() {
        Some(token) if !token.is_empty() => token,
        _ => {
            warn!("Admin API request rejected: no admin_api_token configured");
            return Err((
                StatusCode::SERVICE_UNAVAILABLE,
                "Admin API disabled - no admin_api_token configured",
            )
                .into_response());
        }
    };

    let auth_header = request
        .headers()
        .get(AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");

    let expected_header = format!("Bearer {}", expected);
    if auth_header == expected_header {
        Ok(next.run(request).await)
    } else {
        warn!("Admin API request rejected: invalid bearer token");
        Err(StatusCode::UNAUTHORIZED.into_response())
    }
}

// =============================================================================
// Health
// =============================================================================

#[derive(Serialize)]
pub struct AdminHealthResponse {
    pub status: String,
    pub version: String,
    pub routes_count: usize,
    pub policies_count: usize,
}

pub async fn admin_health(State(state): State<AppState>) -> Json<AdminHealthResponse> {
    Json(AdminHealthResponse {
        status: "ok".to_string(),
        version: env!("CARGO_PKG_VERSION").to_string(),
        routes_count: state.route_registry.count(),
        policies_count: state.policy_registry.count(),
    })
}

// =============================================================================
// API Routes CRUD
// =============================================================================

pub async fn upsert_api(
    State(state): State<AppState>,
    Json(route): Json<ApiRoute>,
) -> impl IntoResponse {
    let deployment_id = Uuid::new_v4();
    let api_id = route.id.clone();
    let tenant = route.tenant_id.clone();
    let emitter = &state.deploy_progress;
    let aid = Some(api_id.as_str());
    let tid = Some(tenant.as_str());

    // Step 1: Validating
    emitter.step_started(
        deployment_id,
        DeployStep::Validating,
        format!("Validating API route '{}'", api_id),
        aid,
        tid,
    );
    emitter.step_completed(
        deployment_id,
        DeployStep::Validating,
        format!("API route '{}' validated", api_id),
        aid,
        tid,
    );

    // Step 2: Applying routes
    emitter.step_started(
        deployment_id,
        DeployStep::ApplyingRoutes,
        format!("Applying route '{}'", api_id),
        aid,
        tid,
    );
    let existed = state.route_registry.upsert(route).is_some();
    emitter.step_completed(
        deployment_id,
        DeployStep::ApplyingRoutes,
        format!(
            "Route '{}' {}",
            api_id,
            if existed { "updated" } else { "created" }
        ),
        aid,
        tid,
    );

    // Step 3: Applying policies (no-op for direct route upsert, but signals step)
    emitter.step_started(
        deployment_id,
        DeployStep::ApplyingPolicies,
        "Checking associated policies",
        aid,
        tid,
    );
    emitter.step_completed(
        deployment_id,
        DeployStep::ApplyingPolicies,
        "Policy check complete",
        aid,
        tid,
    );

    // Step 4: Activating
    emitter.step_started(
        deployment_id,
        DeployStep::Activating,
        format!("Activating route '{}'", api_id),
        aid,
        tid,
    );
    emitter.step_completed(
        deployment_id,
        DeployStep::Activating,
        format!("Route '{}' active", api_id),
        aid,
        tid,
    );

    // Step 5: Done
    emitter.step_completed(
        deployment_id,
        DeployStep::Done,
        format!("API sync complete for '{}'", api_id),
        aid,
        tid,
    );

    let status = if existed {
        StatusCode::OK
    } else {
        StatusCode::CREATED
    };
    (
        status,
        Json(serde_json::json!({
            "id": api_id,
            "status": "ok",
            "deployment_id": deployment_id.to_string()
        })),
    )
}

pub async fn list_apis(State(state): State<AppState>) -> Json<Vec<Arc<ApiRoute>>> {
    Json(state.route_registry.list())
}

pub async fn get_api(State(state): State<AppState>, Path(id): Path<String>) -> impl IntoResponse {
    match state.route_registry.get(&id) {
        Some(route) => Json(route).into_response(),
        None => StatusCode::NOT_FOUND.into_response(),
    }
}

pub async fn delete_api(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> impl IntoResponse {
    match state.route_registry.remove(&id) {
        Some(_) => StatusCode::NO_CONTENT.into_response(),
        None => (StatusCode::NOT_FOUND, "API not found").into_response(),
    }
}

// =============================================================================
// Policies CRUD
// =============================================================================

pub async fn upsert_policy(
    State(state): State<AppState>,
    Json(policy): Json<PolicyEntry>,
) -> impl IntoResponse {
    let id = policy.id.clone();
    let existed = state.policy_registry.upsert(policy).is_some();
    let status = if existed {
        StatusCode::OK
    } else {
        StatusCode::CREATED
    };
    (status, Json(serde_json::json!({"id": id, "status": "ok"})))
}

pub async fn list_policies(State(state): State<AppState>) -> Json<Vec<PolicyEntry>> {
    Json(state.policy_registry.list())
}

pub async fn delete_policy(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> impl IntoResponse {
    match state.policy_registry.remove(&id) {
        Some(_) => StatusCode::NO_CONTENT.into_response(),
        None => (StatusCode::NOT_FOUND, "Policy not found").into_response(),
    }
}

// =============================================================================
// Circuit Breaker (Phase 6)
// =============================================================================

#[derive(Serialize)]
pub struct CircuitBreakerStatsResponse {
    pub name: String,
    pub state: String,
    pub success_count: u64,
    pub failure_count: u64,
    pub failures_in_window: u32,
    pub open_count: u64,
    pub rejected_count: u64,
}

/// GET /admin/circuit-breaker/stats
pub async fn circuit_breaker_stats(
    State(state): State<AppState>,
) -> Json<CircuitBreakerStatsResponse> {
    let stats = state.cp_circuit_breaker.stats();
    Json(CircuitBreakerStatsResponse {
        name: state.cp_circuit_breaker.name().to_string(),
        state: stats.state.to_string(),
        success_count: stats.success_count,
        failure_count: stats.failure_count,
        failures_in_window: stats.failures_in_window,
        open_count: stats.open_count,
        rejected_count: stats.rejected_count,
    })
}

/// POST /admin/circuit-breaker/reset
pub async fn circuit_breaker_reset(State(state): State<AppState>) -> impl IntoResponse {
    state.cp_circuit_breaker.reset();
    (
        StatusCode::OK,
        Json(serde_json::json!({"status": "ok", "message": "Circuit breaker reset to closed"})),
    )
}

// =============================================================================
// Semantic Cache (Phase 6)
// =============================================================================

#[derive(Serialize)]
pub struct CacheStatsResponse {
    pub hits: u64,
    pub misses: u64,
    pub entry_count: u64,
    pub hit_rate: f64,
}

/// GET /admin/cache/stats
pub async fn cache_stats(State(state): State<AppState>) -> Json<CacheStatsResponse> {
    let stats = state.semantic_cache.stats();
    Json(CacheStatsResponse {
        hits: stats.hits,
        misses: stats.misses,
        entry_count: stats.entry_count,
        hit_rate: stats.hit_rate,
    })
}

/// POST /admin/cache/clear
pub async fn cache_clear(State(state): State<AppState>) -> impl IntoResponse {
    state.semantic_cache.clear().await;
    (
        StatusCode::OK,
        Json(serde_json::json!({"status": "ok", "message": "Cache cleared"})),
    )
}

// =============================================================================
// Prompt Cache (CAB-1123)
// =============================================================================

pub async fn prompt_cache_stats(State(state): State<AppState>) -> Json<serde_json::Value> {
    let stats = state.prompt_cache.stats();
    Json(serde_json::json!({
        "hits": stats.hits,
        "misses": stats.misses,
        "entry_count": stats.entry_count,
        "hit_rate": stats.hit_rate,
    }))
}

#[derive(serde::Deserialize)]
pub struct PromptCacheLoadEntry {
    pub key: String,
    pub value: String,
}

#[derive(serde::Deserialize)]
pub struct PromptCacheLoadPayload {
    pub entries: Vec<PromptCacheLoadEntry>,
}

pub async fn prompt_cache_load(
    State(state): State<AppState>,
    Json(payload): Json<PromptCacheLoadPayload>,
) -> Json<serde_json::Value> {
    let patterns: Vec<(String, String)> = payload
        .entries
        .into_iter()
        .map(|e| (e.key, e.value))
        .collect();
    let count = state.prompt_cache.load_patterns(patterns);
    Json(serde_json::json!({"loaded": count, "status": "ok"}))
}

pub async fn prompt_cache_get(
    State(state): State<AppState>,
    axum::extract::Path(key): axum::extract::Path<String>,
) -> impl IntoResponse {
    match state.prompt_cache.get(&key) {
        Some(value) => (
            StatusCode::OK,
            Json(serde_json::json!({"key": key, "value": value})),
        ),
        None => (
            StatusCode::NOT_FOUND,
            Json(serde_json::json!({"error": "Pattern not found", "key": key})),
        ),
    }
}

pub async fn prompt_cache_invalidate(State(state): State<AppState>) -> Json<serde_json::Value> {
    state.prompt_cache.clear();
    Json(serde_json::json!({"status": "cleared"}))
}

pub async fn prompt_cache_patterns(State(state): State<AppState>) -> Json<serde_json::Value> {
    let keys = state.prompt_cache.list_keys();
    Json(serde_json::json!({"keys": keys, "count": keys.len()}))
}

// =============================================================================
// Session Stats (CAB-362)
// =============================================================================

#[derive(Serialize)]
pub struct SessionStatsResponse {
    pub active_sessions: usize,
    pub zombie_count: usize,
    pub tracked_sessions: usize,
}

/// GET /admin/sessions/stats
pub async fn session_stats(State(state): State<AppState>) -> Json<SessionStatsResponse> {
    if let Some(ref zd) = state.zombie_detector {
        let stats = zd.stats().await;
        Json(SessionStatsResponse {
            active_sessions: stats.healthy + stats.warning,
            zombie_count: stats.zombie,
            tracked_sessions: stats.total_sessions,
        })
    } else {
        Json(SessionStatsResponse {
            active_sessions: state.session_manager.count(),
            zombie_count: 0,
            tracked_sessions: 0,
        })
    }
}

// =============================================================================
// Per-Upstream Circuit Breakers (CAB-362)
// =============================================================================

/// GET /admin/circuit-breakers
pub async fn circuit_breakers_list(
    State(state): State<AppState>,
) -> Json<Vec<crate::resilience::CircuitBreakerStatsEntry>> {
    Json(state.circuit_breakers.stats_all())
}

/// POST /admin/circuit-breakers/:name/reset
pub async fn circuit_breaker_reset_by_name(
    State(state): State<AppState>,
    Path(name): Path<String>,
) -> impl IntoResponse {
    if state.circuit_breakers.reset(&name) {
        (
            StatusCode::OK,
            Json(
                serde_json::json!({"status": "ok", "message": format!("Circuit breaker '{}' reset", name)}),
            ),
        )
    } else {
        (
            StatusCode::NOT_FOUND,
            Json(
                serde_json::json!({"status": "error", "message": format!("Circuit breaker '{}' not found", name)}),
            ),
        )
    }
}

// =============================================================================
// mTLS Admin (CAB-864)
// =============================================================================

/// GET /admin/mtls/config — current mTLS configuration (trusted_proxies redacted)
pub async fn mtls_config(
    State(state): State<AppState>,
) -> Json<crate::auth::mtls::MtlsConfigResponse> {
    Json(crate::auth::mtls::MtlsConfigResponse::from(
        &state.config.mtls,
    ))
}

/// GET /admin/mtls/stats — mTLS validation stats
pub async fn mtls_stats(
    State(state): State<AppState>,
) -> Json<crate::auth::mtls::MtlsStatsSnapshot> {
    Json(state.mtls_stats.snapshot())
}

// =============================================================================
// Quota Enforcement (CAB-1121 P4)
// =============================================================================

/// GET /admin/quotas — list all consumer quota stats
pub async fn list_quotas(State(state): State<AppState>) -> Json<Vec<crate::quota::QuotaStats>> {
    Json(state.quota_manager.list_all_stats())
}

/// GET /admin/quotas/:consumer_id — get quota stats for a specific consumer
pub async fn get_consumer_quota(
    State(state): State<AppState>,
    Path(consumer_id): Path<String>,
) -> impl IntoResponse {
    match state.quota_manager.get_stats(&consumer_id) {
        Some(stats) => Json(serde_json::json!(stats)).into_response(),
        None => StatusCode::NOT_FOUND.into_response(),
    }
}

/// POST /admin/quotas/:consumer_id/reset — reset quota counters for a consumer
pub async fn reset_consumer_quota(
    State(state): State<AppState>,
    Path(consumer_id): Path<String>,
) -> impl IntoResponse {
    if state.quota_manager.reset_consumer(&consumer_id) {
        (
            StatusCode::OK,
            Json(
                serde_json::json!({"status": "ok", "message": format!("Quota reset for consumer '{}'", consumer_id)}),
            ),
        )
    } else {
        (
            StatusCode::NOT_FOUND,
            Json(
                serde_json::json!({"status": "error", "message": format!("Consumer '{}' not found", consumer_id)}),
            ),
        )
    }
}

// =============================================================================
// Backend Credentials CRUD (CAB-1250: BYOK)
// =============================================================================

/// POST /admin/backend-credentials — upsert a backend credential
pub async fn upsert_backend_credential(
    State(state): State<AppState>,
    Json(cred): Json<BackendCredential>,
) -> impl IntoResponse {
    // Validate OAuth2 credentials: require config, HTTPS, and SSRF check
    if cred.auth_type == AuthType::OAuth2ClientCredentials {
        match &cred.oauth2 {
            None => {
                return (
                    StatusCode::BAD_REQUEST,
                    Json(serde_json::json!({
                        "status": "error",
                        "message": "oauth2 config required for auth_type oauth2_client_credentials"
                    })),
                )
                    .into_response();
            }
            Some(oauth2) => {
                if !oauth2.token_url.starts_with("https://") {
                    return (
                        StatusCode::BAD_REQUEST,
                        Json(serde_json::json!({
                            "status": "error",
                            "message": "oauth2 token_url must use HTTPS"
                        })),
                    )
                        .into_response();
                }
                if is_blocked_url(&oauth2.token_url) {
                    return (
                        StatusCode::BAD_REQUEST,
                        Json(serde_json::json!({
                            "status": "error",
                            "message": "oauth2 token_url is blocked (SSRF protection)"
                        })),
                    )
                        .into_response();
                }
            }
        }
    }

    let route_id = cred.route_id.clone();
    let existed = state.credential_store.upsert(cred).is_some();
    let status = if existed {
        StatusCode::OK
    } else {
        StatusCode::CREATED
    };
    (
        status,
        Json(serde_json::json!({"route_id": route_id, "status": "ok"})),
    )
        .into_response()
}

/// GET /admin/backend-credentials — list all backend credentials
pub async fn list_backend_credentials(
    State(state): State<AppState>,
) -> Json<Vec<BackendCredential>> {
    Json(state.credential_store.list())
}

/// DELETE /admin/backend-credentials/:route_id — remove a credential
pub async fn delete_backend_credential(
    State(state): State<AppState>,
    Path(route_id): Path<String>,
) -> impl IntoResponse {
    match state.credential_store.remove(&route_id) {
        Some(_) => StatusCode::NO_CONTENT.into_response(),
        None => (StatusCode::NOT_FOUND, "Credential not found").into_response(),
    }
}

// =============================================================================
// UAC Contract CRUD (CAB-1299)
// =============================================================================

/// POST /admin/contracts — register or update a UAC contract
pub async fn upsert_contract(
    State(state): State<AppState>,
    Json(mut contract): Json<UacContractSpec>,
) -> impl IntoResponse {
    // Validate the contract
    let errors = contract.validate();
    if !errors.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(serde_json::json!({"status": "error", "errors": errors})),
        )
            .into_response();
    }

    // Ensure required_policies are up to date with classification
    contract.refresh_policies();

    let key = format!("{}:{}", contract.tenant_id, contract.name);
    let existed = state.contract_registry.upsert(contract.clone()).is_some();

    // Auto-generate REST routes from contract (CAB-1299 PR3)
    let rest_binder = RestBinder::new(state.route_registry.clone());
    let routes_count = match rest_binder.bind(&contract).await {
        Ok(_) => contract.endpoints.len(),
        Err(e) => {
            warn!(error = %e, contract = %key, "REST binder failed");
            0
        }
    };

    // Auto-generate MCP tools from contract (CAB-1299 PR4)
    let mcp_binder = McpBinder::new(state.tool_registry.clone());
    let tools_count = match mcp_binder.bind(&contract).await {
        Ok(_) => contract.endpoints.len(),
        Err(e) => {
            warn!(error = %e, contract = %key, "MCP binder failed");
            0
        }
    };

    let status = if existed {
        StatusCode::OK
    } else {
        StatusCode::CREATED
    };
    (
        status,
        Json(serde_json::json!({
            "key": key,
            "status": "ok",
            "routes_generated": routes_count,
            "tools_generated": tools_count,
        })),
    )
        .into_response()
}

/// GET /admin/contracts — list all UAC contracts
pub async fn list_contracts(State(state): State<AppState>) -> Json<Vec<UacContractSpec>> {
    Json(state.contract_registry.list())
}

/// GET /admin/contracts/:key — get a single UAC contract by key (tenant_id:name)
pub async fn get_contract(
    State(state): State<AppState>,
    Path(key): Path<String>,
) -> impl IntoResponse {
    match state.contract_registry.get(&key) {
        Some(contract) => Json(contract).into_response(),
        None => StatusCode::NOT_FOUND.into_response(),
    }
}

/// DELETE /admin/contracts/:key — remove a UAC contract by key (tenant_id:name)
///
/// Cascade-deletes all REST routes generated from this contract.
pub async fn delete_contract(
    State(state): State<AppState>,
    Path(key): Path<String>,
) -> impl IntoResponse {
    match state.contract_registry.remove(&key) {
        Some(_) => {
            // Cascade-delete generated routes (CAB-1299 PR3)
            let rest_binder = RestBinder::new(state.route_registry.clone());
            let routes_removed = rest_binder.unbind(&key).await.unwrap_or(0);

            // Cascade-delete generated MCP tools (CAB-1299 PR4)
            let mcp_binder = McpBinder::new(state.tool_registry.clone());
            let tools_removed = mcp_binder.unbind(&key).await.unwrap_or(0);

            (
                StatusCode::OK,
                Json(serde_json::json!({
                    "status": "deleted",
                    "routes_removed": routes_removed,
                    "tools_removed": tools_removed,
                })),
            )
                .into_response()
        }
        None => (StatusCode::NOT_FOUND, "Contract not found").into_response(),
    }
}

// =============================================================================
// Federation Admin (CAB-1362)
// =============================================================================

#[derive(Serialize)]
pub struct FederationStatusResponse {
    pub enabled: bool,
    pub cache_size: u64,
    pub cache_ttl_secs: u64,
}

/// GET /admin/federation/status
pub async fn federation_status(State(state): State<AppState>) -> Json<FederationStatusResponse> {
    Json(FederationStatusResponse {
        enabled: state.config.federation_enabled,
        cache_size: state.federation_cache.entry_count(),
        cache_ttl_secs: state.config.federation_cache_ttl_secs,
    })
}

/// GET /admin/federation/cache
pub async fn federation_cache_stats(
    State(state): State<AppState>,
) -> Json<crate::federation::cache::FederationCacheStats> {
    Json(state.federation_cache.stats())
}

/// DELETE /admin/federation/cache/:sub_account_id -- invalidate cache for a sub-account (CAB-1371)
pub async fn federation_cache_invalidate(
    State(state): State<AppState>,
    Path(sub_account_id): Path<String>,
) -> impl IntoResponse {
    state.federation_cache.invalidate(&sub_account_id).await;
    (
        StatusCode::OK,
        Json(serde_json::json!({
            "status": "ok",
            "message": format!("Cache invalidated for sub-account '{}'", sub_account_id)
        })),
    )
}

// =============================================================================
// Skills Admin (CAB-1365)
// =============================================================================

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

/// DELETE /admin/skills?key=X — remove a skill by key (CAB-1366)
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

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::Config;
    use axum::{
        body::Body,
        http::{Request, StatusCode},
        middleware,
        routing::{delete, get},
        Router,
    };
    use tower::ServiceExt;

    fn create_test_state(admin_token: Option<&str>) -> AppState {
        let config = Config {
            admin_api_token: admin_token.map(|s| s.to_string()),
            ..Config::default()
        };
        AppState::new(config)
    }

    fn build_admin_router(state: AppState) -> Router {
        Router::new()
            .route("/health", get(admin_health))
            .route("/apis", get(list_apis).post(upsert_api))
            .route("/apis/:id", get(get_api).delete(delete_api))
            .route("/policies", get(list_policies).post(upsert_policy))
            .route("/policies/:id", delete(delete_policy))
            .layer(middleware::from_fn_with_state(state.clone(), admin_auth))
            .with_state(state)
    }

    #[tokio::test]
    async fn test_admin_auth_valid_token() {
        let state = create_test_state(Some("test-secret"));
        let app = build_admin_router(state);

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/health")
                    .header("Authorization", "Bearer test-secret")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_admin_auth_invalid_token() {
        let state = create_test_state(Some("test-secret"));
        let app = build_admin_router(state);

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/health")
                    .header("Authorization", "Bearer wrong-token")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn test_admin_auth_no_token_configured() {
        let state = create_test_state(None);
        let app = build_admin_router(state);

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/health")
                    .header("Authorization", "Bearer anything")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
    }

    #[tokio::test]
    async fn test_admin_health() {
        let state = create_test_state(Some("secret"));
        let app = build_admin_router(state);

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/health")
                    .header("Authorization", "Bearer secret")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["status"], "ok");
        assert!(data["version"].is_string());
        assert_eq!(data["routes_count"], 0);
        assert_eq!(data["policies_count"], 0);
    }

    #[tokio::test]
    async fn test_upsert_and_list_api() {
        let state = create_test_state(Some("secret"));
        let app = build_admin_router(state);

        // Upsert a route
        let route = serde_json::json!({
            "id": "r1",
            "name": "payments",
            "tenant_id": "acme",
            "path_prefix": "/apis/acme/payments",
            "backend_url": "https://backend.test",
            "methods": ["GET", "POST"],
            "spec_hash": "abc123",
            "activated": true
        });

        let response = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/apis")
                    .header("Authorization", "Bearer secret")
                    .header("Content-Type", "application/json")
                    .body(Body::from(serde_json::to_string(&route).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::CREATED);

        // List routes
        let response = app
            .oneshot(
                Request::builder()
                    .uri("/apis")
                    .header("Authorization", "Bearer secret")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: Vec<serde_json::Value> = serde_json::from_slice(&body).unwrap();
        assert_eq!(data.len(), 1);
        assert_eq!(data[0]["name"], "payments");
    }

    fn build_full_admin_router(state: AppState) -> Router {
        Router::new()
            .route("/health", get(admin_health))
            .route("/apis", get(list_apis).post(upsert_api))
            .route("/apis/:id", get(get_api).delete(delete_api))
            .route("/policies", get(list_policies).post(upsert_policy))
            .route("/policies/:id", delete(delete_policy))
            .route("/circuit-breaker/stats", get(circuit_breaker_stats))
            .route(
                "/circuit-breaker/reset",
                axum::routing::post(circuit_breaker_reset),
            )
            .route("/cache/stats", get(cache_stats))
            .route("/cache/clear", axum::routing::post(cache_clear))
            .route("/sessions/stats", get(session_stats))
            .route("/circuit-breakers", get(circuit_breakers_list))
            .route(
                "/circuit-breakers/:name/reset",
                axum::routing::post(circuit_breaker_reset_by_name),
            )
            .route("/quotas", get(list_quotas))
            .route("/quotas/:consumer_id", get(get_consumer_quota))
            .route(
                "/quotas/:consumer_id/reset",
                axum::routing::post(reset_consumer_quota),
            )
            .route("/mtls/config", get(mtls_config))
            .route("/mtls/stats", get(mtls_stats))
            .route(
                "/backend-credentials",
                get(list_backend_credentials).post(upsert_backend_credential),
            )
            .route(
                "/backend-credentials/:route_id",
                delete(delete_backend_credential),
            )
            // CAB-1299: UAC contracts
            .route("/contracts", get(list_contracts).post(upsert_contract))
            .route("/contracts/:key", get(get_contract).delete(delete_contract))
            // CAB-1362: Federation admin
            .route("/federation/status", get(federation_status))
            .route("/federation/cache", get(federation_cache_stats))
            // CAB-1371: Federation cache invalidation
            .route(
                "/federation/cache/:sub_account_id",
                delete(federation_cache_invalidate),
            )
            // CAB-1123: Prompt cache admin
            .route("/prompt-cache/stats", get(prompt_cache_stats))
            .route("/prompt-cache/load", axum::routing::post(prompt_cache_load))
            .route("/prompt-cache/get/:key", get(prompt_cache_get))
            .route(
                "/prompt-cache/invalidate",
                axum::routing::post(prompt_cache_invalidate),
            )
            .route("/prompt-cache/patterns", get(prompt_cache_patterns))
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

    fn auth_json_req(method: &str, uri: &str, body: serde_json::Value) -> Request<Body> {
        Request::builder()
            .method(method)
            .uri(uri)
            .header("Authorization", "Bearer secret")
            .header("Content-Type", "application/json")
            .body(Body::from(serde_json::to_string(&body).unwrap()))
            .unwrap()
    }

    #[tokio::test]
    async fn test_admin_auth_missing_header() {
        let state = create_test_state(Some("secret"));
        let app = build_admin_router(state);
        let response = app
            .oneshot(
                Request::builder()
                    .uri("/health")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn test_admin_auth_empty_configured_token() {
        let state = create_test_state(Some(""));
        let app = build_admin_router(state);
        let response = app
            .oneshot(
                Request::builder()
                    .uri("/health")
                    .header("Authorization", "Bearer ")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        // Empty token = disabled
        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
    }

    #[tokio::test]
    async fn test_get_api_not_found() {
        let state = create_test_state(Some("secret"));
        let app = build_admin_router(state);
        let response = app
            .oneshot(auth_req("GET", "/apis/nonexistent"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn test_upsert_update_existing_returns_200() {
        let state = create_test_state(Some("secret"));
        let app = build_admin_router(state);
        let route = serde_json::json!({
            "id": "r1", "name": "payments", "tenant_id": "acme",
            "path_prefix": "/apis/acme/payments", "backend_url": "https://backend.test",
            "methods": ["GET"], "spec_hash": "abc", "activated": true
        });
        // First insert → CREATED
        let _ = app
            .clone()
            .oneshot(auth_json_req("POST", "/apis", route.clone()))
            .await
            .unwrap();
        // Second insert (update) → OK
        let response = app
            .oneshot(auth_json_req("POST", "/apis", route))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_delete_api_not_found() {
        let state = create_test_state(Some("secret"));
        let app = build_admin_router(state);
        let response = app
            .oneshot(auth_req("DELETE", "/apis/ghost"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn test_upsert_and_list_policies() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let policy = serde_json::json!({
            "id": "p1", "name": "rate-limit",
            "policy_type": "rate_limit", "config": {"limit": 100},
            "priority": 1, "api_id": "r1"
        });
        let response = app
            .clone()
            .oneshot(auth_json_req("POST", "/policies", policy))
            .await
            .unwrap();
        assert!(response.status() == StatusCode::CREATED || response.status() == StatusCode::OK);
        let response = app.oneshot(auth_req("GET", "/policies")).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: Vec<serde_json::Value> = serde_json::from_slice(&body).unwrap();
        assert_eq!(data.len(), 1);
    }

    #[tokio::test]
    async fn test_delete_policy_not_found() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("DELETE", "/policies/ghost"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn test_circuit_breaker_stats() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("GET", "/circuit-breaker/stats"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["state"], "closed");
        assert_eq!(data["success_count"], 0);
    }

    #[tokio::test]
    async fn test_circuit_breaker_reset() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("POST", "/circuit-breaker/reset"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["status"], "ok");
    }

    #[tokio::test]
    async fn test_cache_stats() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app.oneshot(auth_req("GET", "/cache/stats")).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["hits"], 0);
        assert_eq!(data["misses"], 0);
    }

    #[tokio::test]
    async fn test_cache_clear() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app.oneshot(auth_req("POST", "/cache/clear")).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_session_stats() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("GET", "/sessions/stats"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["active_sessions"], 0);
    }

    #[tokio::test]
    async fn test_circuit_breakers_list_empty() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("GET", "/circuit-breakers"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: Vec<serde_json::Value> = serde_json::from_slice(&body).unwrap();
        assert!(data.is_empty());
    }

    #[tokio::test]
    async fn test_circuit_breaker_reset_by_name_not_found() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("POST", "/circuit-breakers/unknown/reset"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn test_list_quotas_empty() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app.oneshot(auth_req("GET", "/quotas")).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: Vec<serde_json::Value> = serde_json::from_slice(&body).unwrap();
        assert!(data.is_empty());
    }

    #[tokio::test]
    async fn test_get_consumer_quota_not_found() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("GET", "/quotas/unknown-consumer"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn test_reset_consumer_quota_not_found() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("POST", "/quotas/unknown-consumer/reset"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn test_mtls_config_endpoint() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app.oneshot(auth_req("GET", "/mtls/config")).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_mtls_stats_endpoint() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app.oneshot(auth_req("GET", "/mtls/stats")).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

    // === Backend Credentials (CAB-1250) ===

    #[tokio::test]
    async fn test_upsert_and_list_backend_credentials() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);

        let cred = serde_json::json!({
            "route_id": "r1",
            "auth_type": "bearer",
            "header_name": "Authorization",
            "header_value": "Bearer test-token"
        });

        let response = app
            .clone()
            .oneshot(auth_json_req("POST", "/backend-credentials", cred))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::CREATED);

        let response = app
            .oneshot(auth_req("GET", "/backend-credentials"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: Vec<serde_json::Value> = serde_json::from_slice(&body).unwrap();
        assert_eq!(data.len(), 1);
        assert_eq!(data[0]["route_id"], "r1");
    }

    #[tokio::test]
    async fn test_upsert_backend_credential_update() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);

        let cred = serde_json::json!({
            "route_id": "r1", "auth_type": "bearer",
            "header_name": "Authorization", "header_value": "Bearer v1"
        });
        let _ = app
            .clone()
            .oneshot(auth_json_req("POST", "/backend-credentials", cred))
            .await
            .unwrap();

        let cred2 = serde_json::json!({
            "route_id": "r1", "auth_type": "api_key",
            "header_name": "X-API-Key", "header_value": "key-v2"
        });
        let response = app
            .oneshot(auth_json_req("POST", "/backend-credentials", cred2))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK); // update, not create
    }

    #[tokio::test]
    async fn test_delete_backend_credential() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);

        let cred = serde_json::json!({
            "route_id": "r1", "auth_type": "bearer",
            "header_name": "Authorization", "header_value": "Bearer t"
        });
        let _ = app
            .clone()
            .oneshot(auth_json_req("POST", "/backend-credentials", cred))
            .await
            .unwrap();

        let response = app
            .clone()
            .oneshot(auth_req("DELETE", "/backend-credentials/r1"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::NO_CONTENT);
    }

    #[tokio::test]
    async fn test_delete_backend_credential_not_found() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("DELETE", "/backend-credentials/ghost"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn test_delete_api() {
        let state = create_test_state(Some("secret"));
        let app = build_admin_router(state);

        // Upsert a route first
        let route = serde_json::json!({
            "id": "r1",
            "name": "payments",
            "tenant_id": "acme",
            "path_prefix": "/apis/acme/payments",
            "backend_url": "https://backend.test",
            "methods": [],
            "spec_hash": "abc",
            "activated": true
        });

        let _ = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/apis")
                    .header("Authorization", "Bearer secret")
                    .header("Content-Type", "application/json")
                    .body(Body::from(serde_json::to_string(&route).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();

        // Delete it
        let response = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("DELETE")
                    .uri("/apis/r1")
                    .header("Authorization", "Bearer secret")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::NO_CONTENT);

        // Verify it's gone
        let response = app
            .oneshot(
                Request::builder()
                    .uri("/apis")
                    .header("Authorization", "Bearer secret")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: Vec<serde_json::Value> = serde_json::from_slice(&body).unwrap();
        assert_eq!(data.len(), 0);
    }

    // =========================================================================
    // Contract CRUD tests (CAB-1299)
    // =========================================================================

    fn sample_contract_json() -> serde_json::Value {
        serde_json::json!({
            "name": "payment-api",
            "version": "1.0.0",
            "tenant_id": "acme",
            "classification": "H",
            "endpoints": [{
                "path": "/payments/{id}",
                "methods": ["GET", "POST"],
                "backend_url": "https://backend.acme.com/v1/payments"
            }],
            "status": "draft"
        })
    }

    #[tokio::test]
    async fn test_contract_upsert_create() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);

        let response = app
            .oneshot(auth_json_req("POST", "/contracts", sample_contract_json()))
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::CREATED);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["key"], "acme:payment-api");
        assert_eq!(data["status"], "ok");
    }

    #[tokio::test]
    async fn test_contract_upsert_update() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);

        // Create
        let _ = app
            .clone()
            .oneshot(auth_json_req("POST", "/contracts", sample_contract_json()))
            .await
            .unwrap();

        // Update (same name+tenant = update)
        let response = app
            .oneshot(auth_json_req("POST", "/contracts", sample_contract_json()))
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_contract_list_empty() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);

        let response = app.oneshot(auth_req("GET", "/contracts")).await.unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: Vec<serde_json::Value> = serde_json::from_slice(&body).unwrap();
        assert!(data.is_empty());
    }

    #[tokio::test]
    async fn test_contract_get_by_key() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);

        // Create
        let _ = app
            .clone()
            .oneshot(auth_json_req("POST", "/contracts", sample_contract_json()))
            .await
            .unwrap();

        // Get by key
        let response = app
            .oneshot(auth_req("GET", "/contracts/acme:payment-api"))
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["name"], "payment-api");
        assert_eq!(data["tenant_id"], "acme");
        assert_eq!(data["classification"], "H");
    }

    #[tokio::test]
    async fn test_contract_get_not_found() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);

        let response = app
            .oneshot(auth_req("GET", "/contracts/nope:nada"))
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn test_contract_delete() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);

        // Create
        let _ = app
            .clone()
            .oneshot(auth_json_req("POST", "/contracts", sample_contract_json()))
            .await
            .unwrap();

        // Delete
        let response = app
            .clone()
            .oneshot(auth_req("DELETE", "/contracts/acme:payment-api"))
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["status"], "deleted");

        // Verify gone
        let response = app
            .oneshot(auth_req("GET", "/contracts/acme:payment-api"))
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn test_contract_delete_not_found() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);

        let response = app
            .oneshot(auth_req("DELETE", "/contracts/unknown:key"))
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn test_contract_validation_error() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);

        // Contract with empty name
        let invalid = serde_json::json!({
            "name": "",
            "version": "1.0.0",
            "tenant_id": "acme",
            "classification": "H",
            "endpoints": [],
            "status": "draft"
        });

        let response = app
            .oneshot(auth_json_req("POST", "/contracts", invalid))
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["status"], "error");
        assert!(data["errors"].is_array());
    }

    #[tokio::test]
    async fn test_contract_policies_auto_refreshed() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);

        let vvh_contract = serde_json::json!({
            "name": "critical-api",
            "version": "1.0.0",
            "tenant_id": "acme",
            "classification": "VVH",
            "endpoints": [{
                "path": "/critical",
                "methods": ["POST"],
                "backend_url": "https://backend.acme.com/critical"
            }],
            "status": "draft"
        });

        let _ = app
            .clone()
            .oneshot(auth_json_req("POST", "/contracts", vvh_contract))
            .await
            .unwrap();

        let response = app
            .oneshot(auth_req("GET", "/contracts/acme:critical-api"))
            .await
            .unwrap();

        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        let policies = data["required_policies"].as_array().unwrap();
        assert!(policies.contains(&serde_json::json!("mtls")));
        assert!(policies.contains(&serde_json::json!("audit-logging")));
    }

    // =========================================================================
    // REST Binder integration tests (CAB-1299 PR3)
    // =========================================================================

    #[tokio::test]
    async fn test_contract_upsert_generates_routes() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state.clone());

        let response = app
            .oneshot(auth_json_req("POST", "/contracts", sample_contract_json()))
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::CREATED);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["routes_generated"], 1); // 1 endpoint in sample_contract_json
        assert_eq!(data["tools_generated"], 1);

        // Verify route is in the route registry
        assert_eq!(state.route_registry.count(), 1);
        let route = state.route_registry.get("uac:acme:payment-api:0");
        assert!(route.is_some());
        let route = route.unwrap();
        assert_eq!(route.path_prefix, "/apis/acme/payment-api/payments/{id}");
        assert_eq!(route.contract_key.as_deref(), Some("acme:payment-api"));

        // Verify MCP tool is in the tool registry (no operation_id → fallback name)
        assert_eq!(state.tool_registry.count(), 1);
        assert!(state
            .tool_registry
            .exists("uac:acme:payment-api:payment-api-0"));
    }

    #[tokio::test]
    async fn test_contract_delete_cascades_routes() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state.clone());

        // Create contract → generates route
        let _ = app
            .clone()
            .oneshot(auth_json_req("POST", "/contracts", sample_contract_json()))
            .await
            .unwrap();
        assert_eq!(state.route_registry.count(), 1);

        // Delete contract → cascades route removal
        let response = app
            .oneshot(auth_req("DELETE", "/contracts/acme:payment-api"))
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["routes_removed"], 1);
        assert_eq!(data["tools_removed"], 1);
        assert_eq!(state.route_registry.count(), 0);
        assert_eq!(state.tool_registry.count(), 0);
    }

    #[tokio::test]
    async fn test_contract_re_upsert_replaces_routes() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state.clone());

        // Create with 1 endpoint
        let _ = app
            .clone()
            .oneshot(auth_json_req("POST", "/contracts", sample_contract_json()))
            .await
            .unwrap();
        assert_eq!(state.route_registry.count(), 1);

        // Re-upsert with 2 endpoints
        let two_endpoints = serde_json::json!({
            "name": "payment-api",
            "version": "2.0.0",
            "tenant_id": "acme",
            "classification": "H",
            "endpoints": [
                {
                    "path": "/payments",
                    "methods": ["GET", "POST"],
                    "backend_url": "https://backend.acme.com/v2/payments"
                },
                {
                    "path": "/payments/{id}",
                    "methods": ["GET", "DELETE"],
                    "backend_url": "https://backend.acme.com/v2/payments"
                }
            ],
            "status": "published"
        });

        let response = app
            .oneshot(auth_json_req("POST", "/contracts", two_endpoints))
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["routes_generated"], 2);

        // Old route should be gone, 2 new routes present
        assert_eq!(state.route_registry.count(), 2);
    }

    #[tokio::test]
    async fn test_contract_routes_have_classification() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state.clone());

        let vh_contract = serde_json::json!({
            "name": "sensitive-api",
            "version": "1.0.0",
            "tenant_id": "acme",
            "classification": "VH",
            "endpoints": [{
                "path": "/data",
                "methods": ["GET"],
                "backend_url": "https://backend.acme.com/data"
            }],
            "status": "draft"
        });

        let _ = app
            .oneshot(auth_json_req("POST", "/contracts", vh_contract))
            .await
            .unwrap();

        let route = state
            .route_registry
            .get("uac:acme:sensitive-api:0")
            .unwrap();
        assert_eq!(route.classification, Some(crate::uac::Classification::VH));
    }

    #[tokio::test]
    async fn test_contract_upsert_generates_mcp_tools() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state.clone());

        let contract = serde_json::json!({
            "name": "orders",
            "version": "1.0.0",
            "tenant_id": "acme",
            "classification": "H",
            "endpoints": [
                {
                    "path": "/orders",
                    "methods": ["GET"],
                    "backend_url": "https://backend.acme.com/orders",
                    "operation_id": "list_orders"
                },
                {
                    "path": "/orders",
                    "methods": ["POST"],
                    "backend_url": "https://backend.acme.com/orders",
                    "operation_id": "create_order"
                }
            ],
            "status": "published"
        });

        let response = app
            .oneshot(auth_json_req("POST", "/contracts", contract))
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::CREATED);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["tools_generated"], 2);

        // Both tools registered
        assert_eq!(state.tool_registry.count(), 2);
        assert!(state.tool_registry.exists("uac:acme:orders:list_orders"));
        assert!(state.tool_registry.exists("uac:acme:orders:create_order"));
    }

    #[tokio::test]
    async fn test_contract_delete_cascades_tools() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state.clone());

        // Create contract → generates tools
        let _ = app
            .clone()
            .oneshot(auth_json_req("POST", "/contracts", sample_contract_json()))
            .await
            .unwrap();
        assert_eq!(state.tool_registry.count(), 1);

        // Delete contract → cascades tool removal
        let response = app
            .oneshot(auth_req("DELETE", "/contracts/acme:payment-api"))
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(state.tool_registry.count(), 0);
    }

    #[tokio::test]
    async fn test_mcp_tools_visible_via_list() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state.clone());

        let _ = app
            .oneshot(auth_json_req("POST", "/contracts", sample_contract_json()))
            .await
            .unwrap();

        // Tool should be visible in tool registry
        let tools = state.tool_registry.list(Some("acme"));
        assert_eq!(tools.len(), 1);
        assert_eq!(tools[0].name, "uac:acme:payment-api:payment-api-0");
        assert_eq!(tools[0].tenant_id.as_deref(), Some("acme"));
    }

    // =========================================================================
    // Federation Admin (CAB-1362)
    // =========================================================================

    #[tokio::test]
    async fn test_federation_cache_invalidate() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("DELETE", "/federation/cache/sub-acct-123"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["status"], "ok");
        assert!(data["message"].as_str().unwrap().contains("sub-acct-123"));
    }

    #[tokio::test]
    async fn test_federation_status_disabled() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("GET", "/federation/status"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["enabled"], false);
        assert_eq!(data["cache_size"], 0);
        assert_eq!(data["cache_ttl_secs"], 300);
    }

    #[tokio::test]
    async fn test_federation_status_enabled() {
        let config = Config {
            admin_api_token: Some("secret".to_string()),
            federation_enabled: true,
            federation_cache_ttl_secs: 600,
            ..Config::default()
        };
        let state = AppState::new(config);
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("GET", "/federation/status"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["enabled"], true);
        assert_eq!(data["cache_ttl_secs"], 600);
    }

    #[tokio::test]
    async fn test_federation_cache_stats() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("GET", "/federation/cache"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["entries"], 0);
        assert_eq!(data["hits"], 0);
        assert_eq!(data["misses"], 0);
        assert_eq!(data["hit_rate"], 0.0);
    }

    // ─── Prompt Cache (CAB-1123) ──────────────────────────────

    #[tokio::test]
    async fn test_prompt_cache_stats_empty() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("GET", "/prompt-cache/stats"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["entry_count"], 0);
        assert_eq!(data["hits"], 0);
        assert_eq!(data["misses"], 0);
    }

    #[tokio::test]
    async fn test_prompt_cache_load() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_json_req(
                "POST",
                "/prompt-cache/load",
                serde_json::json!({
                    "entries": [
                        {"key": "greet", "value": "Hello!"},
                        {"key": "bye", "value": "Goodbye!"}
                    ]
                }),
            ))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["loaded"], 2);
    }

    #[tokio::test]
    async fn test_prompt_cache_get_miss() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("GET", "/prompt-cache/get/nonexistent"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn test_prompt_cache_load_then_get() {
        let state = create_test_state(Some("secret"));
        // Load first
        state
            .prompt_cache
            .load_patterns(vec![("hello".into(), "world".into())]);
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_req("GET", "/prompt-cache/get/hello"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["value"], "world");
    }

    #[tokio::test]
    async fn test_prompt_cache_invalidate() {
        let state = create_test_state(Some("secret"));
        state
            .prompt_cache
            .load_patterns(vec![("x".into(), "y".into())]);
        let app = build_full_admin_router(state);
        let response = app
            .oneshot(auth_json_req(
                "POST",
                "/prompt-cache/invalidate",
                serde_json::json!({}),
            ))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["status"], "cleared");
    }
}
