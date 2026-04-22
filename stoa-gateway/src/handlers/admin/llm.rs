//! LLM cost-aware routing admin endpoints (CAB-1487 wiring).

use axum::{extract::State, Json};
use serde::Serialize;

use crate::state::AppState;

/// GET /admin/llm/status — routing strategy, provider count, circuit breaker states.
#[derive(Serialize)]
pub struct LlmStatusResponse {
    pub enabled: bool,
    pub routing_strategy: Option<String>,
    pub provider_count: usize,
    pub providers: Vec<LlmProviderStatus>,
}

#[derive(Serialize)]
pub struct LlmProviderStatus {
    pub provider: String,
    pub base_url: String,
    pub default_model: Option<String>,
    pub priority: u32,
    pub healthy: bool,
}

pub async fn llm_status(State(state): State<AppState>) -> Json<LlmStatusResponse> {
    let Some(ref router) = state.llm_router else {
        return Json(LlmStatusResponse {
            enabled: false,
            routing_strategy: None,
            provider_count: 0,
            providers: vec![],
        });
    };

    let registry = router.registry();
    let providers: Vec<LlmProviderStatus> = registry
        .all()
        .iter()
        .map(|p| LlmProviderStatus {
            provider: p.provider.to_string(),
            base_url: p.base_url.clone(),
            default_model: p.default_model.clone(),
            priority: p.priority,
            healthy: router.is_healthy(p.provider),
        })
        .collect();

    Json(LlmStatusResponse {
        enabled: true,
        routing_strategy: Some(format!("{:?}", router.default_strategy())),
        provider_count: providers.len(),
        providers,
    })
}

/// GET /admin/llm/providers — enabled providers with pricing metadata.
#[derive(Serialize)]
pub struct LlmProviderDetail {
    pub provider: String,
    pub backend_id: Option<String>,
    pub base_url: String,
    pub default_model: Option<String>,
    pub max_concurrent: u32,
    pub priority: u32,
    pub cost_per_1m_input: f64,
    pub cost_per_1m_output: f64,
    pub cost_per_1m_cache_read: f64,
    pub cost_per_1m_cache_write: f64,
    pub healthy: bool,
}

pub async fn llm_providers(State(state): State<AppState>) -> Json<Vec<LlmProviderDetail>> {
    let Some(ref router) = state.llm_router else {
        return Json(vec![]);
    };

    let registry = router.registry();
    let providers: Vec<LlmProviderDetail> = registry
        .all()
        .iter()
        .map(|p| LlmProviderDetail {
            provider: p.provider.to_string(),
            backend_id: p.backend_id.clone(),
            base_url: p.base_url.clone(),
            default_model: p.default_model.clone(),
            max_concurrent: p.max_concurrent,
            priority: p.priority,
            cost_per_1m_input: p.cost_per_1m_input,
            cost_per_1m_output: p.cost_per_1m_output,
            cost_per_1m_cache_read: p.cost_per_1m_cache_read,
            cost_per_1m_cache_write: p.cost_per_1m_cache_write,
            healthy: router.is_healthy(p.provider),
        })
        .collect();

    Json(providers)
}

/// GET /admin/llm/costs — current Prometheus cost metric snapshots.
#[derive(Serialize)]
pub struct LlmCostSnapshot {
    pub cost_tracking_enabled: bool,
    pub metrics: Vec<LlmCostMetricEntry>,
}

#[derive(Serialize)]
pub struct LlmCostMetricEntry {
    pub provider: String,
    pub model: String,
    pub total_cost_usd: f64,
}

pub async fn llm_costs(State(state): State<AppState>) -> Json<LlmCostSnapshot> {
    if state.cost_calculator.is_none() {
        return Json(LlmCostSnapshot {
            cost_tracking_enabled: false,
            metrics: vec![],
        });
    }

    // Gather current metric values from Prometheus counters
    let mut metrics = Vec::new();
    let metric_families = prometheus::gather();
    for mf in &metric_families {
        if mf.get_name() == "gateway_llm_cost_total" {
            for m in mf.get_metric() {
                let labels = m.get_label();
                let provider = labels
                    .iter()
                    .find(|l| l.get_name() == "provider")
                    .map(|l| l.get_value().to_string())
                    .unwrap_or_default();
                let model = labels
                    .iter()
                    .find(|l| l.get_name() == "model")
                    .map(|l| l.get_value().to_string())
                    .unwrap_or_default();
                metrics.push(LlmCostMetricEntry {
                    provider,
                    model,
                    total_cost_usd: m.get_counter().get_value(),
                });
            }
        }
    }

    Json(LlmCostSnapshot {
        cost_tracking_enabled: true,
        metrics,
    })
}
