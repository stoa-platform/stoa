//! LLM Admin Handlers (CAB-1487)
//!
//! Endpoints for LLM provider routing, listing, and cost reporting.
//! All routes are behind the admin_auth middleware.

use axum::extract::State;
use axum::response::IntoResponse;
use axum::Json;

use crate::llm::provider::ProviderSummary;
use crate::state::AppState;

/// POST /admin/llm/route — select the next provider for a request.
pub async fn route_request(State(state): State<AppState>) -> impl IntoResponse {
    let Some(ref llm_router) = state.llm_router else {
        return Json(serde_json::json!({"error": "LLM routing is disabled"}));
    };

    match llm_router.select_provider() {
        Some(provider) => Json(serde_json::json!({
            "provider_id": provider.config.id,
            "endpoint": provider.config.endpoint,
            "strategy": format!("{:?}", llm_router.strategy()),
        })),
        None => Json(serde_json::json!({"error": "no healthy provider available"})),
    }
}

/// GET /admin/llm/providers — list all registered providers with status.
pub async fn list_providers(State(state): State<AppState>) -> impl IntoResponse {
    let Some(ref llm_router) = state.llm_router else {
        return Json(serde_json::json!({"providers": [], "enabled": false}));
    };

    let summaries: Vec<ProviderSummary> = llm_router
        .providers()
        .iter()
        .map(ProviderSummary::from_state)
        .collect();

    Json(serde_json::json!({"providers": summaries, "enabled": true}))
}

/// GET /admin/llm/costs — return per-provider cost breakdown.
pub async fn get_costs(State(state): State<AppState>) -> impl IntoResponse {
    let Some(ref llm_router) = state.llm_router else {
        return Json(serde_json::json!({
            "costs": [],
            "total_cost_microcents": 0,
            "budget_enforcement": false
        }));
    };

    let costs = llm_router.cost_tracker.snapshot().await;
    let total = llm_router.cost_tracker.total_cost_microcents().await;

    Json(serde_json::json!({
        "costs": costs,
        "total_cost_microcents": total,
        "budget_enforcement": llm_router.budget_enforcement
    }))
}
