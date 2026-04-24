//! Admin sub-router factory (GW-1 P2-test-1).
//!
//! Single source of truth for the wiring of the `/admin/*` surface.
//! `lib.rs` mounts the returned router under `.nest("/admin", ...)`; the
//! test harness in `test_helpers.rs` reuses the same factory un-nested so
//! unit tests hit the exact set of routes + middleware that production
//! serves. Keeping the wiring in one place removes the drift between the
//! prod router and the previous hand-rolled `build_full_admin_router`.
//!
//! Middleware order (innermost → outermost): `handler` → `admin_auth` →
//! `admin_rate_limit` → `admin_audit_log`. Axum's `Router::layer` only
//! applies to routes declared *before* the layer call, so every `.route`
//! must stay above the three `.layer` calls at the end of this function.

use axum::{
    middleware,
    routing::{delete, get, post},
    Router,
};

use super::{
    admin_audit_log, admin_auth, admin_health, admin_rate_limit, cache_clear, cache_stats,
    circuit_breaker_reset, circuit_breaker_reset_by_name, circuit_breaker_stats,
    circuit_breakers_list, delete_api, delete_backend_credential, delete_consumer_credential,
    delete_contract, delete_policy, federation_cache_invalidate, federation_cache_stats,
    federation_status, federation_upstreams, get_api, get_consumer_quota, get_contract, list_apis,
    list_backend_credentials, list_consumer_credentials, list_contracts, list_policies,
    list_quotas, llm_costs, llm_providers, llm_status, mtls_config, mtls_stats, prompt_cache_get,
    prompt_cache_invalidate, prompt_cache_load, prompt_cache_patterns, prompt_cache_stats,
    reset_consumer_quota, routes_reload, session_stats, skills_delete, skills_delete_by_id,
    skills_get_by_id, skills_health, skills_health_all, skills_health_reset, skills_list,
    skills_resolve, skills_status, skills_sync, skills_update, skills_upsert, tracing_status,
    upsert_api, upsert_backend_credential, upsert_consumer_credential, upsert_contract,
    upsert_policy,
};
use crate::{
    a2a, ebpf, handlers,
    hegemon::{budget, claims, dashboard, dispatch, messaging, metering, registry},
    proxy::list_api_proxy_backends,
    state::AppState,
};

/// Build the admin sub-router.
///
/// Routes are declared **before** the three middleware layers at the end
/// of the builder chain; layers added after `.route(...)` only apply to
/// routes already present (Axum `Router::layer` contract). Callers are
/// expected to mount the returned router under `/admin` (see `lib.rs`
/// `build_router` and the test harness).
///
/// The returned router is **un-stated** (`Router<AppState>`) — the
/// caller is responsible for attaching `.with_state(...)` at the top of
/// its tree, matching the `build_router` composition in `lib.rs`.
pub(crate) fn build_admin_router(state: AppState) -> Router<AppState> {
    Router::<AppState>::new()
        .route("/health", get(admin_health))
        .route("/apis", get(list_apis).post(upsert_api))
        .route("/apis/:id", get(get_api).delete(delete_api))
        .route("/policies", get(list_policies).post(upsert_policy))
        .route("/policies/:id", delete(delete_policy))
        // Phase 6: Circuit Breaker admin
        .route("/circuit-breaker/stats", get(circuit_breaker_stats))
        .route("/circuit-breaker/reset", post(circuit_breaker_reset))
        // Phase 6: Cache admin
        .route("/cache/stats", get(cache_stats))
        .route("/cache/clear", post(cache_clear))
        // CAB-362: Session stats + per-upstream circuit breakers
        .route("/sessions/stats", get(session_stats))
        .route("/circuit-breakers", get(circuit_breakers_list))
        .route(
            "/circuit-breakers/:name/reset",
            post(circuit_breaker_reset_by_name),
        )
        // CAB-864: mTLS admin
        .route("/mtls/config", get(mtls_config))
        .route("/mtls/stats", get(mtls_stats))
        // CAB-1121 P4: Quota enforcement admin
        .route("/quotas", get(list_quotas))
        .route("/quotas/:consumer_id", get(get_consumer_quota))
        .route("/quotas/:consumer_id/reset", post(reset_consumer_quota))
        // CAB-1250: BYOK backend credentials
        .route(
            "/backend-credentials",
            get(list_backend_credentials).post(upsert_backend_credential),
        )
        .route(
            "/backend-credentials/:route_id",
            delete(delete_backend_credential),
        )
        // CAB-1250 P3: Consumer credentials
        .route(
            "/consumer-credentials",
            get(list_consumer_credentials).post(upsert_consumer_credential),
        )
        .route(
            "/consumer-credentials/:route_id/:consumer_id",
            delete(delete_consumer_credential),
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
        .route("/prompt-cache/load", post(prompt_cache_load))
        .route("/prompt-cache/get/:key", get(prompt_cache_get))
        .route("/prompt-cache/invalidate", post(prompt_cache_invalidate))
        .route("/prompt-cache/patterns", get(prompt_cache_patterns))
        // CAB-1365/1366: Skills admin (literal paths before parametric `:id`)
        .route("/skills/status", get(skills_status))
        .route("/skills/resolve", get(skills_resolve))
        .route("/skills/sync", post(skills_sync))
        .route(
            "/skills",
            get(skills_list).post(skills_upsert).delete(skills_delete),
        )
        // CAB-1551: Skills health (literal path before parametric `:id`)
        .route("/skills/health", get(skills_health_all))
        .route(
            "/skills/:id",
            get(skills_get_by_id)
                .put(skills_update)
                .delete(skills_delete_by_id),
        )
        .route("/skills/:id/health", get(skills_health))
        .route("/skills/:id/health/reset", post(skills_health_reset))
        // CAB-1487: LLM cost-aware routing admin
        .route("/llm/status", get(llm_status))
        .route("/llm/providers", get(llm_providers))
        .route("/llm/costs", get(llm_costs))
        // CAB-1752: Distributed tracing admin
        .route("/tracing/status", get(tracing_status))
        // CAB-1752: Federation upstreams listing
        .route("/federation/upstreams", get(federation_upstreams))
        // CAB-1316: Diagnostic endpoint (CB states, uptime, route stats)
        .route("/diagnostic", get(handlers::diagnostic::diagnostic_handler))
        // CAB-1316: Per-request diagnostic report + aggregated summary
        .route(
            "/diagnostics/summary",
            get(handlers::diagnostic::diagnostic_summary_handler),
        )
        .route(
            "/diagnostics/:request_id",
            get(handlers::diagnostic::diagnostic_report_handler),
        )
        // CAB-1710/1711: HEGEMON agent registry admin
        .route("/hegemon/agents", get(registry::list_agents))
        .route("/hegemon/agents/:name", get(registry::get_agent))
        .route(
            "/hegemon/agents/:name/tier",
            post(registry::update_agent_tier),
        )
        // CAB-1713/1714: HEGEMON dispatch admin
        .route("/hegemon/dispatches", get(dispatch::list_dispatches))
        .route("/hegemon/dispatches/:id", get(dispatch::get_dispatch))
        // CAB-1716: HEGEMON budget admin
        .route("/hegemon/budget", get(budget::list_budgets))
        // CAB-1718: HEGEMON claims admin
        .route("/hegemon/claims", get(claims::list_claims))
        .route("/hegemon/claims/:mega_id", get(claims::get_claims))
        // CAB-1720/1721: HEGEMON metering + dashboard admin
        .route("/hegemon/dashboard", get(dashboard::fleet_dashboard))
        .route("/hegemon/events", get(metering::list_events))
        // CAB-1709 P6: HEGEMON messaging admin
        .route("/hegemon/messages", get(messaging::list_inboxes))
        // CAB-1754: A2A agent registry admin
        .route(
            "/a2a/agents",
            get(a2a::admin::list_agents).post(a2a::admin::register_agent),
        )
        .route(
            "/a2a/agents/:name",
            get(a2a::admin::get_agent).delete(a2a::admin::unregister_agent),
        )
        // CAB-1722: API proxy backends admin (moved here for admin_auth coverage — GW-1 P0-2)
        .route("/api-proxy/backends", get(list_api_proxy_backends))
        // CAB-1828: Route hot-reload
        .route("/routes/reload", post(routes_reload))
        // CAB-1645: Error snapshot capture
        .route(
            "/snapshots",
            get(handlers::snapshot::list_snapshots).delete(handlers::snapshot::clear_snapshots),
        )
        .route(
            "/snapshots/:request_id",
            get(handlers::snapshot::get_snapshot),
        )
        // CAB-1848: eBPF kernel policy sync
        .route("/ebpf/sync", post(ebpf::ebpf_sync))
        .route("/ebpf/status", get(ebpf::ebpf_status))
        // GW-1 P0-1 / P1-3-lite / P1-4 — middleware order from innermost
        // (runs last) to outermost (runs first):
        //   handler → admin_auth → admin_rate_limit → admin_audit_log
        // Audit layer is outermost so rate-limited (429) and unauthenticated
        // (401) attempts are part of the audit trail too. Rate-limit runs
        // before auth so bearer probing is throttled without reaching the
        // constant-time compare.
        .layer(middleware::from_fn_with_state(state.clone(), admin_auth))
        .layer(middleware::from_fn_with_state(state, admin_rate_limit))
        .layer(middleware::from_fn(admin_audit_log))
}

#[cfg(test)]
mod tests {
    //! Factory-level regression tests.
    //!
    //! - `regression_delete_skills_status_returns_405_not_delete_by_id`
    //!   verifies matchit's literal-over-param priority + Axum's default
    //!   `MethodRouter` 405 behaviour (GW-1 P1-7): seeding a skill with
    //!   key `"status"` and sending `DELETE /skills/status` must yield
    //!   405 (no DELETE on `/skills/status`, which is GET-only) rather
    //!   than dispatching to `skills_delete_by_id("status")`.
    //! - The other tests verify that the factory produces a router that
    //!   actually exposes routes previously missing from the old
    //!   hand-rolled `build_full_admin_router` (GW-1 P2-test-1).
    use axum::{
        body::Body,
        http::{Request, StatusCode},
    };
    use tower::ServiceExt;

    use super::build_admin_router;
    use crate::handlers::admin::test_helpers::create_test_state;
    use crate::skills::resolver::{SkillScope, StoredSkill};

    fn auth_req(method: &str, uri: &str) -> Request<Body> {
        Request::builder()
            .method(method)
            .uri(uri)
            .header("Authorization", "Bearer secret")
            .body(Body::empty())
            .unwrap()
    }

    // GW-1 P1-7: `DELETE /skills/status` must be 405, not a delete-by-id
    // on a skill keyed `"status"`.
    #[tokio::test]
    async fn regression_delete_skills_status_returns_405_not_delete_by_id() {
        let state = create_test_state(Some("secret"));
        state.skill_resolver.upsert(StoredSkill {
            key: "status".into(),
            name: "canary".into(),
            description: None,
            tenant_id: "acme".into(),
            scope: SkillScope::Tenant,
            priority: 50,
            instructions: None,
            tool_ref: None,
            user_ref: None,
            enabled: true,
        });

        let app = build_admin_router(state.clone()).with_state(state.clone());
        let response = app
            .oneshot(auth_req("DELETE", "/skills/status"))
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::METHOD_NOT_ALLOWED);
        assert!(
            response.headers().contains_key(axum::http::header::ALLOW),
            "Axum MethodRouter must set `Allow` on 405 responses"
        );
        assert_eq!(
            state.skill_resolver.get("status").map(|s| s.key.clone()),
            Some("status".to_string()),
            "DELETE /skills/status must not have removed the skill keyed `status`"
        );
    }

    // GW-1 P2-test-1: `/skills/*` routes are reachable through the full
    // factory router (they were absent from the old `build_full_admin_router`).
    #[tokio::test]
    async fn test_prod_admin_router_skills_routes_reachable_via_full_harness() {
        let state = create_test_state(Some("secret"));
        let app = build_admin_router(state.clone()).with_state(state);

        let response = app
            .oneshot(auth_req("GET", "/skills/status"))
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
    }

    // GW-1 P2-test-1: `/llm/*` routes are reachable through the factory
    // router (previously absent from the test harness).
    #[tokio::test]
    async fn test_prod_admin_router_llm_routes_reachable_via_full_harness() {
        let state = create_test_state(Some("secret"));
        let app = build_admin_router(state.clone()).with_state(state);

        let response = app.oneshot(auth_req("GET", "/llm/status")).await.unwrap();

        assert_eq!(response.status(), StatusCode::OK);
    }
}
