//! UAC contract CRUD admin endpoints (CAB-1299).
//!
//! GW-1 P1-1 / P1-2 / P2-2: contract mutations are transactional
//! across three stores (contract registry, REST route registry, MCP
//! tool registry). The previous implementation persisted the contract
//! *before* the binders ran, so a binder failure left the registry
//! claiming routes/tools that did not exist. This module now enforces:
//!
//! - **upsert**: *bind-first*. Only commit to `contract_registry` once
//!   both REST and MCP binds have succeeded. On failure, best-effort
//!   unbind of the partial artefacts is attempted and the handler
//!   returns `500`.
//! - **delete**: *unbind-first*. Only remove from `contract_registry`
//!   once both unbinds have succeeded. On failure, the contract stays
//!   in the registry and the handler returns `500`.
//! - **counts**: `routes_generated` / `tools_generated` come from the
//!   real `BindingOutput` length, never from `contract.endpoints.len()`.
//!
//! The `ContractBinders` trait is a local abstraction used to inject
//! test doubles; the production path wraps `RestBinder` + `McpBinder`
//! via `RealBinders`.

use std::sync::Arc;

use async_trait::async_trait;
use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use tracing::warn;

use crate::state::AppState;
use crate::uac::binders::{mcp::McpBinder, rest::RestBinder, BindingOutput, ProtocolBinder};
use crate::uac::registry::ContractRegistry;
use crate::uac::UacContractSpec;

/// Local abstraction over the REST + MCP binders so the handler logic
/// can be tested with injected failures.
#[async_trait]
pub(crate) trait ContractBinders: Send + Sync {
    async fn bind_rest(&self, contract: &UacContractSpec) -> Result<usize, String>;
    async fn bind_mcp(&self, contract: &UacContractSpec) -> Result<usize, String>;
    async fn unbind_rest(&self, key: &str) -> Result<usize, String>;
    async fn unbind_mcp(&self, key: &str) -> Result<usize, String>;
}

/// Production impl backed by the real binders.
pub(crate) struct RealBinders {
    rest: RestBinder,
    mcp: McpBinder,
}

impl RealBinders {
    pub(crate) fn from_state(state: &AppState) -> Self {
        Self {
            rest: RestBinder::new(state.route_registry.clone()),
            mcp: McpBinder::new(state.tool_registry.clone()),
        }
    }
}

#[async_trait]
impl ContractBinders for RealBinders {
    async fn bind_rest(&self, contract: &UacContractSpec) -> Result<usize, String> {
        match self.rest.bind(contract).await? {
            BindingOutput::Routes(r) => Ok(r.len()),
            BindingOutput::Tools(_) => Err("REST binder returned Tools output".into()),
        }
    }
    async fn bind_mcp(&self, contract: &UacContractSpec) -> Result<usize, String> {
        match self.mcp.bind(contract).await? {
            BindingOutput::Tools(t) => Ok(t.len()),
            BindingOutput::Routes(_) => Err("MCP binder returned Routes output".into()),
        }
    }
    async fn unbind_rest(&self, key: &str) -> Result<usize, String> {
        self.rest.unbind(key).await
    }
    async fn unbind_mcp(&self, key: &str) -> Result<usize, String> {
        self.mcp.unbind(key).await
    }
}

/// POST /admin/contracts — register or update a UAC contract.
pub async fn upsert_contract(
    State(state): State<AppState>,
    Json(contract): Json<UacContractSpec>,
) -> Response {
    let binders = RealBinders::from_state(&state);
    perform_upsert(
        state.contract_registry.clone(),
        &binders,
        state.config.llm_enabled,
        contract,
    )
    .await
}

/// Transactional upsert — extracted so tests can inject `ContractBinders`.
pub(crate) async fn perform_upsert(
    registry: Arc<ContractRegistry>,
    binders: &dyn ContractBinders,
    llm_enabled: bool,
    mut contract: UacContractSpec,
) -> Response {
    // Normalize endpoint shorthand: merge `method` into `methods` if provided.
    for ep in &mut contract.endpoints {
        if let Some(method) = ep.method.take() {
            if ep.methods.is_empty() {
                ep.methods.push(method);
            }
        }
    }

    // Validate the contract.
    let errors = contract.validate();
    if !errors.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(serde_json::json!({"status": "error", "errors": errors})),
        )
            .into_response();
    }

    contract.refresh_policies();

    // Expand LLM capabilities into synthetic endpoints (CAB-709).
    let llm_capabilities = if let Some(ref llm_config) = contract.llm_config {
        if llm_enabled {
            let synthetic = llm_config.expand_endpoints();
            let count = synthetic.len();
            contract.endpoints.extend(synthetic);
            count
        } else {
            warn!("Contract has llm_config but STOA_LLM_ENABLED=false, skipping LLM expansion");
            0
        }
    } else {
        0
    };

    let key = contract
        .key
        .clone()
        .unwrap_or_else(|| format!("{}:{}", contract.tenant_id, contract.name));

    // ── bind-first ────────────────────────────────────────────
    let routes_count = match binders.bind_rest(&contract).await {
        Ok(n) => n,
        Err(e) => {
            warn!(error = %e, contract = %key, "REST bind failed; contract NOT persisted");
            // No partial state to clean: bind_rest failed before registering any route.
            return binder_failure_response(&key, "REST", &e);
        }
    };

    let tools_count = match binders.bind_mcp(&contract).await {
        Ok(n) => n,
        Err(e) => {
            warn!(error = %e, contract = %key, "MCP bind failed; rolling back REST routes");
            // Best-effort rollback of the REST routes we just registered.
            if let Err(rb) = binders.unbind_rest(&key).await {
                warn!(error = %rb, contract = %key, "REST rollback unbind also failed");
            }
            return binder_failure_response(&key, "MCP", &e);
        }
    };

    // ── commit ────────────────────────────────────────────────
    let existed = registry.upsert(contract).is_some();
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
            "llm_capabilities": llm_capabilities,
        })),
    )
        .into_response()
}

/// GET /admin/contracts — list all UAC contracts.
pub async fn list_contracts(State(state): State<AppState>) -> Json<Vec<UacContractSpec>> {
    Json(state.contract_registry.list())
}

/// GET /admin/contracts/:key — get a single UAC contract by key.
pub async fn get_contract(
    State(state): State<AppState>,
    Path(key): Path<String>,
) -> impl IntoResponse {
    match state.contract_registry.get(&key) {
        Some(contract) => Json(contract).into_response(),
        None => StatusCode::NOT_FOUND.into_response(),
    }
}

/// DELETE /admin/contracts/:key — remove a UAC contract.
///
/// Cascade-unbinds REST routes and MCP tools **before** removing the
/// contract from the registry. If either unbind fails, the registry is
/// left untouched and the caller receives a `500` — prevents orphaned
/// routes/tools persisting after the contract disappears.
pub async fn delete_contract(State(state): State<AppState>, Path(key): Path<String>) -> Response {
    let binders = RealBinders::from_state(&state);
    perform_delete(state.contract_registry.clone(), &binders, key).await
}

/// Transactional delete — extracted for testing.
pub(crate) async fn perform_delete(
    registry: Arc<ContractRegistry>,
    binders: &dyn ContractBinders,
    key: String,
) -> Response {
    if registry.get(&key).is_none() {
        return (StatusCode::NOT_FOUND, "Contract not found").into_response();
    }

    // ── unbind-first ──────────────────────────────────────────
    let routes_removed = match binders.unbind_rest(&key).await {
        Ok(n) => n,
        Err(e) => {
            warn!(error = %e, contract = %key, "REST unbind failed; contract NOT removed");
            return binder_failure_response(&key, "REST", &e);
        }
    };

    let tools_removed = match binders.unbind_mcp(&key).await {
        Ok(n) => n,
        Err(e) => {
            warn!(error = %e, contract = %key, "MCP unbind failed; contract NOT removed");
            // REST routes are already gone; best we can do is surface the error.
            return binder_failure_response(&key, "MCP", &e);
        }
    };

    // ── commit ────────────────────────────────────────────────
    registry.remove(&key);
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

fn binder_failure_response(key: &str, which: &str, _err: &str) -> Response {
    // Client message is deliberately generic; full error is already in
    // `tracing::warn!` server-side (see callers).
    (
        StatusCode::INTERNAL_SERVER_ERROR,
        Json(serde_json::json!({
            "status": "error",
            "message": format!("{} binder failed", which),
            "key": key,
        })),
    )
        .into_response()
}

#[cfg(test)]
mod tests;
