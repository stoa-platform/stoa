//! UAC contract administration and startup restoration.

use std::collections::HashSet;
use std::io;
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
            rest: RestBinder::with_policies(
                state.route_registry.clone(),
                state.policy_registry.clone(),
            ),
            mcp: McpBinder::new(state.tool_registry.clone())
                .with_credential_store(state.credential_store.clone()),
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
    // Complete an active mutation even if the client drops the request.
    tokio::spawn(async move {
        let binders = RealBinders::from_state(&state);
        perform_upsert(
            state.contract_registry,
            &binders,
            state.config.llm_enabled,
            contract,
        )
        .await
    })
    .await
    .unwrap_or_else(|_| StatusCode::INTERNAL_SERVER_ERROR.into_response())
}

fn validate_contract(contract: &mut UacContractSpec) -> Result<(), Vec<String>> {
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
        return Err(errors);
    }

    contract.refresh_policies();
    Ok(())
}

fn expand_contract(contract: &mut UacContractSpec, llm_enabled: bool) -> usize {
    let Some(llm_config) = &contract.llm_config else {
        return 0;
    };
    if !llm_enabled {
        warn!("Contract has llm_config but STOA_LLM_ENABLED=false, skipping LLM expansion");
        return 0;
    }
    let synthetic = llm_config.expand_endpoints();
    let count = synthetic.len();
    contract.endpoints.extend(synthetic);
    count
}

/// Restore pushed contracts and rebuild their bindings before serving requests.
pub async fn restore_contracts(state: &AppState) -> io::Result<()> {
    let registry = &state.contract_registry;
    let _mutation = registry.bindings.write().await;
    let mut contracts = registry.read_snapshot().await?;
    let mut keys = HashSet::with_capacity(contracts.len());
    for contract in &mut contracts {
        validate_contract(contract).map_err(|_| {
            io::Error::new(io::ErrorKind::InvalidData, "invalid contract in snapshot")
        })?;
        if !keys.insert(contract.canonical_key()) {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "duplicate contract in snapshot",
            ));
        }
    }

    let binders = RealBinders::from_state(state);
    for declarative in contracts {
        let mut contract = declarative.clone();
        let expanded = expand_contract(&mut contract, state.config.llm_enabled) > 0;
        binders
            .bind_rest(&contract)
            .await
            .map_err(io::Error::other)?;
        binders
            .bind_mcp(&contract)
            .await
            .map_err(io::Error::other)?;
        registry.upsert_bound(contract, expanded.then_some(declarative));
    }
    Ok(())
}

pub(crate) async fn perform_upsert(
    registry: Arc<ContractRegistry>,
    binders: &dyn ContractBinders,
    llm_enabled: bool,
    mut contract: UacContractSpec,
) -> Response {
    if let Err(errors) = validate_contract(&mut contract) {
        return (
            StatusCode::BAD_REQUEST,
            Json(serde_json::json!({"status": "error", "errors": errors})),
        )
            .into_response();
    }
    let declarative = contract.clone();
    let llm_capabilities = expand_contract(&mut contract, llm_enabled);
    let key = contract.canonical_key();
    let _mutation = registry.bindings.write().await;
    let previous = registry.get(&key);

    // ── bind-first ────────────────────────────────────────────
    let routes_count = match binders.bind_rest(&contract).await {
        Ok(n) => n,
        Err(e) => {
            warn!(error = %e, contract = %key, "REST bind failed; contract NOT persisted");
            // Restore the previous contract's bindings if this was an update.
            // On a create, there's nothing to restore — the REST registry
            // is still whatever state bind_rest left it in (today: no
            // mutation before the Err return; defensively: restore_to_nothing
            // via best-effort unbind).
            if let Some(ref old) = previous {
                restore_previous_bindings(binders, old, &key).await;
            } else if let Err(rb) = binders.unbind_rest(&key).await {
                warn!(error = %rb, contract = %key, "REST bind cleanup after failure also failed");
            }
            return binder_failure_response(&key, "REST", &e);
        }
    };

    let tools_count = match binders.bind_mcp(&contract).await {
        Ok(n) => n,
        Err(e) => {
            warn!(error = %e, contract = %key, "MCP bind failed; rolling back bindings");
            if let Some(ref old) = previous {
                // Update case: restore the previous contract's REST + MCP
                // bindings so the registry stays consistent with the artefact
                // stores. Best-effort — failures are logged, response is 500.
                restore_previous_bindings(binders, old, &key).await;
            } else {
                // Create case: unbind the REST routes we just registered.
                if let Err(rb) = binders.unbind_rest(&key).await {
                    warn!(error = %rb, contract = %key, "REST rollback unbind also failed");
                }
            }
            return binder_failure_response(&key, "MCP", &e);
        }
    };

    if let Err(error) = registry
        .persist_change(&key, Some(declarative.clone()))
        .await
    {
        if let Some(ref old) = previous {
            restore_previous_bindings(binders, old, &key).await;
        } else {
            if let Err(error) = binders.unbind_rest(&key).await {
                warn!(%error, contract = %key, "REST rollback failed");
            }
            if let Err(error) = binders.unbind_mcp(&key).await {
                warn!(%error, contract = %key, "MCP rollback failed");
            }
        }
        return storage_failure_response(&error);
    }

    let response_key = contract.key.clone().unwrap_or(key);
    let existed = registry
        .upsert_bound(contract, (llm_capabilities > 0).then_some(declarative))
        .is_some();
    let status = if existed {
        StatusCode::OK
    } else {
        StatusCode::CREATED
    };
    (
        status,
        Json(serde_json::json!({
            "key": response_key,
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
    tokio::spawn(async move {
        let binders = RealBinders::from_state(&state);
        perform_delete(state.contract_registry, &binders, key).await
    })
    .await
    .unwrap_or_else(|_| StatusCode::INTERNAL_SERVER_ERROR.into_response())
}

/// Transactional delete — extracted for testing.
pub(crate) async fn perform_delete(
    registry: Arc<ContractRegistry>,
    binders: &dyn ContractBinders,
    key: String,
) -> Response {
    let _mutation = registry.bindings.write().await;
    // Snapshot the contract up-front: if `unbind_mcp` fails after
    // `unbind_rest` succeeded, we need the contract spec in hand to
    // restore REST bindings (GW-1 P1-2 partial-state extension).
    let old_contract = match registry.get(&key) {
        Some(c) => c,
        None => return (StatusCode::NOT_FOUND, "Contract not found").into_response(),
    };

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
            warn!(
                error = %e,
                contract = %key,
                "MCP unbind failed; restoring REST routes and leaving contract in registry"
            );
            // Best-effort restore of the REST routes we just removed so
            // the registry+REST view stays consistent. MCP state is
            // indeterminate (the unbind failure means we can't predict
            // what's there) — the caller sees 500 and can retry.
            if let Err(rb) = binders.bind_rest(&old_contract).await {
                warn!(error = %rb, contract = %key, "REST rollback bind(old) also failed");
            }
            return binder_failure_response(&key, "MCP", &e);
        }
    };

    if let Err(error) = registry.persist_change(&key, None).await {
        restore_previous_bindings(binders, &old_contract, &key).await;
        return storage_failure_response(&error);
    }

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

fn storage_failure_response(error: &io::Error) -> Response {
    warn!(%error, "Could not save contract snapshot");
    (
        StatusCode::INTERNAL_SERVER_ERROR,
        Json(serde_json::json!({"status": "error", "message": "Could not save contract snapshot"})),
    )
        .into_response()
}

/// Best-effort rollback that reinstalls the previous contract's REST
/// routes and MCP tools. Used when an upsert's binder step fails on a
/// contract that already existed. Each sub-step is independent and
/// failures are only logged — the caller still returns 500 to the
/// client, so partial restore is surfaced via server-side traces
/// rather than a divergent response shape.
async fn restore_previous_bindings(
    binders: &dyn ContractBinders,
    old: &UacContractSpec,
    key: &str,
) {
    if let Err(e) = binders.bind_rest(old).await {
        warn!(error = %e, contract = %key, "REST rollback bind(old) failed");
    }
    if let Err(e) = binders.bind_mcp(old).await {
        warn!(error = %e, contract = %key, "MCP rollback bind(old) failed");
    }
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
