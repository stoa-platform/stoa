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

    // GW-1 P2-7: collect the `gateway_llm_cost_total` metric family
    // directly from the `CounterVec` that owns it, instead of scanning
    // every metric family in the global Prometheus registry with
    // `prometheus::gather()`. The old implementation was an O(N) walk
    // over the entire registry on every admin call; this one reads
    // exactly the counter vec we care about. Lecteur-side only — no
    // change to where `LLM_COST_TOTAL` is incremented, no change to
    // labels or registration.
    use prometheus::core::Collector;

    let metrics: Vec<LlmCostMetricEntry> = crate::llm::cost::LLM_COST_TOTAL
        .collect()
        .iter()
        .flat_map(|mf| mf.get_metric().to_vec())
        .map(|m| {
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
            LlmCostMetricEntry {
                provider,
                model,
                total_cost_usd: m.get_counter().get_value(),
            }
        })
        .collect();

    Json(LlmCostSnapshot {
        cost_tracking_enabled: true,
        metrics,
    })
}

#[cfg(test)]
mod tests {
    //! GW-1 P2-7 regression tests for the LLM cost reader.
    //!
    //! The global Prometheus registry is a single process-wide
    //! singleton, so these tests do not register ad-hoc metrics — they
    //! would leak across parallel `cargo test` invocations. Instead
    //! they exercise the production `LLM_COST_TOTAL` counter vec and
    //! assert that the handler reads it correctly **without** doing a
    //! full-registry scan.

    use std::sync::Arc;

    use axum::http::StatusCode;
    use tower::ServiceExt;

    use crate::config::Config;
    use crate::handlers::admin::test_helpers::{auth_req, build_full_admin_router};
    use crate::llm::cost::{CostCalculator, LLM_COST_TOTAL};
    use crate::llm::providers::{ProviderConfig, ProviderRegistry};
    use crate::state::AppState;

    fn state_with_cost_tracking() -> AppState {
        let config = Config {
            admin_api_token: Some("secret".into()),
            ..Config::default()
        };
        let mut state = AppState::new(config);
        // `llm_costs` takes the "enabled" branch as soon as
        // `cost_calculator` is `Some(_)`. Point it at an empty provider
        // registry — the handler never reads the registry, only the
        // Prometheus counter vec.
        let registry = Arc::new(ProviderRegistry::new(Vec::<ProviderConfig>::new()));
        state.cost_calculator = Some(Arc::new(CostCalculator::new(registry)));
        state
    }

    // GW-1 P2-7: `/admin/llm/costs` captures recorded cost increments
    // from `LLM_COST_TOTAL`. The unique `{provider, model}` label pair
    // avoids collisions with other tests reusing the same counter vec.
    #[tokio::test]
    async fn regression_llm_costs_captures_recorded_increments() {
        // Use a label pair no other test touches to stay deterministic.
        let provider = "p2-7-regression";
        let model = "canary-model";
        LLM_COST_TOTAL
            .with_label_values(&[provider, model])
            .inc_by(2.5);

        let state = state_with_cost_tracking();
        let app = build_full_admin_router(state);
        let response = app.oneshot(auth_req("GET", "/llm/costs")).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["cost_tracking_enabled"], true);

        let entry = data["metrics"]
            .as_array()
            .expect("metrics must be an array")
            .iter()
            .find(|m| m["provider"] == provider && m["model"] == model)
            .expect("our canary (provider, model) must appear in the response");
        assert!(
            entry["total_cost_usd"].as_f64().unwrap_or(0.0) >= 2.5,
            "total_cost_usd must reflect at least the 2.5 increment, got {:?}",
            entry["total_cost_usd"]
        );
    }

    // GW-1 P2-7: non-LLM metrics registered in the global registry must
    // NOT leak into the `/admin/llm/costs` response. The handler reads
    // `LLM_COST_TOTAL.collect()` directly, so any cross-pollution would
    // indicate the old full-registry scan crept back in.
    #[tokio::test]
    async fn test_llm_costs_does_not_leak_unrelated_metrics() {
        let state = state_with_cost_tracking();
        let app = build_full_admin_router(state);
        let response = app.oneshot(auth_req("GET", "/llm/costs")).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        // Every entry must be shaped for cost — presence of `provider`,
        // `model`, `total_cost_usd` fields.
        for entry in data["metrics"].as_array().unwrap_or(&vec![]) {
            assert!(entry.get("provider").is_some());
            assert!(entry.get("model").is_some());
            assert!(entry.get("total_cost_usd").is_some());
            assert_eq!(entry.as_object().unwrap().len(), 3);
        }
    }
}
