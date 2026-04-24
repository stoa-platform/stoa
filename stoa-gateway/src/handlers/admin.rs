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
//!   GET    /admin/llm/status       - LLM routing status + provider health
//!   GET    /admin/llm/providers    - Enabled providers with pricing
//!   GET    /admin/llm/costs        - Prometheus cost metric snapshots
//!
//! All endpoints are protected by bearer token auth (admin_auth middleware).
//!
//! Implementation is split per responsibility under `src/handlers/admin/`.
//! This file is a thin façade: submodule declarations + re-exports so that
//! `crate::handlers::admin::<symbol>` paths used by `lib.rs`, `main.rs` and
//! `state.rs` remain stable.

mod apis;
mod auth;
mod cache;
mod circuit_breaker;
mod contracts;
mod credentials;
mod federation;
mod health;
mod llm;
mod mtls;
mod policies;
mod quotas;
mod reload;
mod sessions;
mod skills;
mod tracing;

pub use apis::{delete_api, get_api, list_apis, upsert_api};
pub use auth::{admin_auth, admin_rate_limit};
pub use cache::{
    cache_clear, cache_stats, prompt_cache_get, prompt_cache_invalidate, prompt_cache_load,
    prompt_cache_patterns, prompt_cache_stats, CacheStatsResponse, PromptCacheLoadEntry,
    PromptCacheLoadPayload,
};
pub use circuit_breaker::{
    circuit_breaker_reset, circuit_breaker_reset_by_name, circuit_breaker_stats,
    circuit_breakers_list, CircuitBreakerStatsResponse,
};
pub use contracts::{delete_contract, get_contract, list_contracts, upsert_contract};
pub use credentials::{
    delete_backend_credential, delete_consumer_credential, list_backend_credentials,
    list_consumer_credentials, upsert_backend_credential, upsert_consumer_credential,
    ConsumerCredentialPath,
};
pub use federation::{
    federation_cache_invalidate, federation_cache_stats, federation_status, federation_upstreams,
    FederationStatusResponse, FederationUpstreamEntry, FederationUpstreamsResponse,
};
pub use health::{admin_health, AdminHealthResponse};
pub use llm::{
    llm_costs, llm_providers, llm_status, LlmCostMetricEntry, LlmCostSnapshot, LlmProviderDetail,
    LlmProviderStatus, LlmStatusResponse,
};
pub use mtls::{mtls_config, mtls_stats};
pub use policies::{delete_policy, list_policies, upsert_policy};
pub use quotas::{get_consumer_quota, list_quotas, reset_consumer_quota};
pub use reload::{reload_routes_from_cp, routes_reload};
pub use sessions::{session_stats, SessionStatsResponse};
pub use skills::{
    skills_delete, skills_delete_by_id, skills_get_by_id, skills_health, skills_health_all,
    skills_health_reset, skills_list, skills_resolve, skills_status, skills_sync, skills_update,
    skills_upsert, SkillAdminEntry, SkillDeleteParams, SkillResolveParams, SkillUpsertPayload,
    SkillsStatusResponse,
};
pub use tracing::{tracing_status, TracingStatusResponse};

#[cfg(test)]
mod test_helpers;
