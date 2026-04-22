//! UAC contract CRUD admin endpoints (CAB-1299).

use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::IntoResponse,
    Json,
};
use tracing::warn;

use crate::state::AppState;
use crate::uac::binders::{mcp::McpBinder, rest::RestBinder, ProtocolBinder};
use crate::uac::UacContractSpec;

/// POST /admin/contracts — register or update a UAC contract
pub async fn upsert_contract(
    State(state): State<AppState>,
    Json(mut contract): Json<UacContractSpec>,
) -> impl IntoResponse {
    // Normalize endpoint shorthand: merge `method` into `methods` if provided
    for ep in &mut contract.endpoints {
        if let Some(method) = ep.method.take() {
            if ep.methods.is_empty() {
                ep.methods.push(method);
            }
        }
    }

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

    // Expand LLM capabilities into synthetic endpoints (CAB-709)
    let llm_capabilities = if let Some(ref llm_config) = contract.llm_config {
        if state.config.llm_enabled {
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
            "llm_capabilities": llm_capabilities,
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

#[cfg(test)]
mod tests;
