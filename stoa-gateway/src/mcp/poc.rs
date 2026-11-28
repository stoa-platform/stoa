//! Autonomous PoC HTTP/MCP endpoints backed by dedicated local RS256 + DPoP auth,
//! signed role policies with durable anti-rollback (`0600`, 15 min max), v1 argument
//! constraints, gateway-native delegation, and outbound address policy enforcement.
//!
//! Routes (mounted only when `STOA_POC_AGENTS_ENABLED=true`):
//! - `POST /mcp/poc/bootstrap`: mints a DPoP-bound `depth=0` parent token for the
//!   designated parent container (`X-Stoa-Poc-Bootstrap-Secret` + valid DPoP proof).
//! - `POST /mcp/poc/delegate`: mints a strictly narrowed DPoP-bound child token
//!   (`iss=stoa-poc-delegation`, `aud=mcp-tool:{tenant}:{tool}`, `depth<=3`,
//!   `exp<=parent.exp`, inherited tenant, `act`, `chain_id`, `jti`, `parent_jti`).
//! - `POST /mcp/poc`: Streamable HTTP JSON-RPC 2.0 entrypoint enforcing strict local
//!   RS256 validation (separate from OIDC), atomic DPoP verification (`htm`, `htu`,
//!   `ath`, `cnf.jkt`), and the full shared tool authorization chain.

use std::collections::{HashMap, HashSet};
use std::path::Path;

use axum::{
    body::Bytes,
    extract::State,
    http::{header::CACHE_CONTROL, HeaderMap, HeaderValue, StatusCode},
    response::{IntoResponse, Response},
    Json,
};
use serde::{Deserialize, Serialize};
use serde_json::value::RawValue;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use subtle::ConstantTimeEq;
use tracing::{info, warn};
use uuid::Uuid;

use crate::auth::dpop::DpopJwk;
use crate::auth::local_agent_token::{
    canonical_tool_audience, DelegateChildTokenRequest, IssueParentTokenRequest, LocalAgentClaims,
    LocalTokenError, DELEGATION_ISSUER, LOCAL_AGENT_ISSUER,
};
use crate::auth::poc_admission::{AdmissionError, AdmitCallRequest};
use crate::control_plane::role_policy::{
    ArgumentConstraint, RoleEvalInput, RolePolicySpec, RolePolicyStore,
};
use crate::mcp::handlers::{check_tool_permission, check_tool_permission_quiet, check_tool_policy};
use crate::mcp::sse::{
    JsonRpcResponse, INVALID_PARAMS, INVALID_REQUEST, METHOD_NOT_FOUND, PARSE_ERROR,
};
use crate::mcp::tools::native_tool::{
    is_my_limits_action, my_limits_result, poc_security_definition, POC_SECURITY_TOOL,
};
use crate::mcp::tools::{Tool, ToolContext, ToolDefinition};
use crate::proxy::credentials::{normalize_origin, BackendCredential, MCP_TOOL_KEY_PREFIX};
use crate::state::AppState;
use crate::uac::binders::mcp::McpBinder;
use crate::uac::binders::{BindingOutput, ProtocolBinder};
use crate::uac::schema::UacContractSpec;
use crate::uac::Action;

type PocToolRejection = (i32, &'static str);

/// Summary of local PoC fixtures loaded at gateway boot.
#[derive(Debug, Default, Clone, PartialEq, Eq)]
pub struct PocFixturesSummary {
    pub credentials_loaded: usize,
    pub contracts_loaded: usize,
    pub tools_registered: usize,
    pub role_policies_loaded: usize,
}

/// Load local backend credentials, UAC contracts (with outbound address policy), and signed
/// role policies configured for autonomous PoC mode.
pub async fn load_poc_fixtures(state: &AppState) -> Result<PocFixturesSummary, String> {
    let mut summary = PocFixturesSummary::default();
    let role_store = state
        .role_policy_store
        .as_ref()
        .ok_or_else(|| "Role policy is not configured".to_string())?;
    for tenant in &state.config.policy_boot_tenants {
        role_store
            .refresh_tenant(tenant)
            .await
            .map_err(|e| format!("failed to load signed role policy for '{tenant}': {e}"))?;
        summary.role_policies_loaded += 1;
    }

    if let Some(ref cred_path) = state.config.poc_credentials_file {
        let raw = tokio::fs::read_to_string(cred_path)
            .await
            .map_err(|e| format!("failed to read poc_credentials_file '{cred_path}': {e}"))?;
        let mut creds: Vec<BackendCredential> = serde_json::from_str(&raw)
            .map_err(|e| format!("failed to parse poc_credentials_file '{cred_path}': {e}"))?;
        for cred in &mut creds {
            if cred.route_id.starts_with(MCP_TOOL_KEY_PREFIX) {
                let normalized = cred
                    .allowed_origin
                    .as_deref()
                    .and_then(normalize_origin)
                    .ok_or_else(|| {
                        format!(
                            "mcp-tool credential '{}' requires a valid allowed_origin",
                            cred.route_id
                        )
                    })?;
                cred.allowed_origin = Some(normalized);
            }
            state.credential_store.upsert(cred.clone());
            summary.credentials_loaded += 1;
        }
    }

    if let Some(ref contracts_dir) = state.config.poc_uac_contracts_dir {
        let mut entries = tokio::fs::read_dir(contracts_dir)
            .await
            .map_err(|e| format!("failed to read poc_uac_contracts_dir '{contracts_dir}': {e}"))?;
        let mut paths = Vec::new();
        while let Some(entry) = entries
            .next_entry()
            .await
            .map_err(|e| format!("failed to iterate '{contracts_dir}': {e}"))?
        {
            let path = entry.path();
            if path.is_file() && is_contract_file(&path) {
                paths.push(path);
            }
        }
        paths.sort();

        let binder = McpBinder::new(state.tool_registry.clone())
            .with_credential_store(state.credential_store.clone())
            .with_outbound_policy(state.outbound_policy.clone());

        for path in paths {
            let raw = tokio::fs::read_to_string(&path)
                .await
                .map_err(|e| format!("failed to read contract '{}': {e}", path.display()))?;
            let contract: UacContractSpec = match path.extension().and_then(|e| e.to_str()) {
                Some("yaml") | Some("yml") => serde_yaml::from_str(&raw).map_err(|e| {
                    format!("failed to parse YAML contract '{}': {e}", path.display())
                })?,
                _ => serde_json::from_str(&raw).map_err(|e| {
                    format!("failed to parse JSON contract '{}': {e}", path.display())
                })?,
            };
            let output = binder.bind(&contract).await?;
            summary.contracts_loaded += 1;
            if let BindingOutput::Tools(defs) = output {
                summary.tools_registered += defs.len();
            }
        }
    }

    info!(
        credentials = summary.credentials_loaded,
        contracts = summary.contracts_loaded,
        tools = summary.tools_registered,
        role_policies = summary.role_policies_loaded,
        "Loaded autonomous PoC fixtures"
    );
    Ok(summary)
}

fn is_contract_file(path: &Path) -> bool {
    matches!(
        path.extension().and_then(|e| e.to_str()),
        Some("json" | "yaml" | "yml")
    )
}

fn public_base_url(state: &AppState) -> String {
    state
        .config
        .poc_public_base_url
        .as_deref()
        .map(|s| s.trim_end_matches('/').to_string())
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| format!("http://127.0.0.1:{}", state.config.port))
}

#[derive(Debug, Deserialize)]
pub struct PocBootstrapRequest {
    pub sub: String,
    pub tenant_id: String,
    pub role: String,
    #[serde(default)]
    pub aud: Option<String>,
    #[serde(default)]
    pub ttl_secs: Option<i64>,
}

#[derive(Debug, Deserialize)]
pub struct PocDelegateRequest {
    pub sub: String,
    pub target_tool: String,
    pub child_dpop_jwk: DpopJwk,
    #[serde(default)]
    pub allowed_tools: Vec<String>,
    #[serde(default)]
    pub arg_constraints: Option<HashMap<String, ArgumentConstraint>>,
    #[serde(default)]
    pub ttl_secs: Option<i64>,
}

#[derive(Debug, Serialize)]
struct PocTokenResponse {
    access_token: String,
    token_type: &'static str,
    expires_in: i64,
    kid: String,
    iss: String,
    chain_id: String,
    jti: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    parent_jti: Option<String>,
    depth: u8,
    aud: String,
    tenant_id: String,
    role: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    act: Option<Value>,
}

/// `POST /mcp/poc/bootstrap` — mint a DPoP-bound `depth=0` parent token.
pub async fn handle_poc_bootstrap(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<PocBootstrapRequest>,
) -> Response {
    let Some(ref auth) = state.local_agent_auth else {
        return StatusCode::NOT_FOUND.into_response();
    };

    let Some(expected_secret) = state
        .config
        .poc_bootstrap_secret
        .as_deref()
        .filter(|s| !s.is_empty())
    else {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({ "error": "bootstrap_unconfigured" })),
        )
            .into_response();
    };

    let provided_secret = headers
        .get("X-Stoa-Poc-Bootstrap-Secret")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");
    if !bool::from(provided_secret.as_bytes().ct_eq(expected_secret.as_bytes())) {
        warn!("Rejected PoC bootstrap request: invalid bootstrap secret");
        return (
            StatusCode::UNAUTHORIZED,
            Json(json!({ "error": "invalid_bootstrap_secret" })),
        )
            .into_response();
    }

    let base = public_base_url(&state);
    let bootstrap_htu = format!("{base}/mcp/poc/bootstrap");
    let cnf_jkt = match auth.validate_bootstrap_dpop(&headers, "POST", &bootstrap_htu) {
        Ok(jkt) => jkt,
        Err(err) => {
            warn!(error = %err, "Rejected PoC bootstrap DPoP proof");
            return (
                StatusCode::UNAUTHORIZED,
                Json(json!({ "error": "invalid_dpop_proof" })),
            )
                .into_response();
        }
    };

    let Some(role_store) = state.role_policy_store.as_ref() else {
        return (
            StatusCode::FORBIDDEN,
            Json(json!({ "error": "role_not_permitted" })),
        )
            .into_response();
    };
    if role_store.refresh_tenant(&req.tenant_id).await.is_err() {
        return (
            StatusCode::FORBIDDEN,
            Json(json!({ "error": "role_not_permitted" })),
        )
            .into_response();
    }
    let Ok((policy_version, _)) = role_store.current_role_snapshot(&req.tenant_id, &req.role)
    else {
        return (
            StatusCode::FORBIDDEN,
            Json(json!({ "error": "role_not_permitted" })),
        )
            .into_response();
    };

    let aud = req
        .aud
        .filter(|a| !a.trim().is_empty())
        .unwrap_or_else(|| format!("{base}/mcp/poc"));
    let ttl_secs = req.ttl_secs.unwrap_or(300);

    match auth.issue_parent_token(IssueParentTokenRequest {
        sub: req.sub,
        tenant_id: req.tenant_id,
        role: req.role,
        aud,
        cnf_jkt,
        ttl_secs,
        policy_version: Some(policy_version),
    }) {
        Ok(issued) => {
            if let Err(err) = state.poc_admission.register_chain_for_tenant(
                &issued.claims.chain_id,
                &issued.claims.tenant_id,
                issued.claims.exp,
                chrono::Utc::now().timestamp(),
            ) {
                return admission_http_rejection(err);
            }
            (
                StatusCode::OK,
                Json(PocTokenResponse {
                    access_token: issued.as_str().to_string(),
                    token_type: "DPoP",
                    expires_in: issued.claims.exp - issued.claims.iat,
                    kid: auth.kid().to_string(),
                    iss: issued.claims.iss,
                    chain_id: issued.claims.chain_id,
                    jti: issued.claims.jti,
                    parent_jti: issued.claims.parent_jti,
                    depth: issued.claims.depth,
                    aud: issued.claims.aud,
                    tenant_id: issued.claims.tenant_id,
                    role: issued.claims.role,
                    act: issued.claims.act,
                }),
            )
                .into_response()
        }
        Err(LocalTokenError::InvalidRequest(msg)) => {
            (StatusCode::BAD_REQUEST, Json(json!({ "error": msg }))).into_response()
        }
        Err(_) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({ "error": "token_issuance_failed" })),
        )
            .into_response(),
    }
}

/// `POST /mcp/poc/delegate` — mint a strictly narrowed, DPoP-bound child token.
pub async fn handle_poc_delegate(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<PocDelegateRequest>,
) -> Response {
    let Some(ref auth) = state.local_agent_auth else {
        return StatusCode::NOT_FOUND.into_response();
    };

    let base = public_base_url(&state);
    let delegate_htu = format!("{base}/mcp/poc/delegate");
    let mcp_aud = format!("{base}/mcp/poc");
    let target_tool = req.target_tool.trim().to_string();

    // Parent may be a root token (`aud == {base}/mcp/poc`) or a child token re-delegating
    // its own canonical tool audience (`aud == mcp-tool:{tenant}:{target_tool}`).
    let parent_claims = match auth.validate_mcp_request_with_audience_fn(
        &headers,
        "POST",
        &delegate_htu,
        |claims| {
            if claims.depth == 0 && claims.iss == LOCAL_AGENT_ISSUER {
                Ok(mcp_aud.clone())
            } else if claims.depth > 0 && claims.iss == DELEGATION_ISSUER {
                Ok(canonical_tool_audience(&claims.tenant_id, &target_tool))
            } else {
                Err(LocalTokenError::InvalidClaims("unsupported token issuer"))
            }
        },
    ) {
        Ok(claims) => claims,
        Err(err) => {
            if matches!(err, LocalTokenError::InvalidToken) {
                state
                    .poc_admission
                    .observe_time(chrono::Utc::now().timestamp());
            }
            warn!(error = %err, "Rejected PoC delegate caller authentication");
            return (
                StatusCode::UNAUTHORIZED,
                Json(json!({ "error": "unauthorized" })),
            )
                .into_response();
        }
    };

    // Check the chain before evaluating the narrower child scope.
    let now_epoch = chrono::Utc::now().timestamp();
    if let Err(err) = state.poc_admission.check_chain_active(
        &parent_claims.chain_id,
        parent_claims.exp,
        now_epoch,
    ) {
        return admission_http_rejection(err);
    }

    let Ok((_, parent_effective_tools, active_role)) =
        effective_poc_allowed_tools(&state, &parent_claims).await
    else {
        return (
            StatusCode::FORBIDDEN,
            Json(json!({ "error": "role_policy_denied" })),
        )
            .into_response();
    };

    let target = state
        .tool_registry
        .get_for_tenant(&target_tool, &parent_claims.tenant_id);
    let permitted = check_poc_tool_access(
        &state,
        &poc_tool_context(&parent_claims),
        &target_tool,
        target.as_deref(),
    )
    .await
    .is_ok_and(|tool| tool.name() == target_tool);
    if !permitted {
        return (
            StatusCode::FORBIDDEN,
            Json(json!({ "error": "tool_not_permitted" })),
        )
            .into_response();
    }

    let parent_tool_constraints = active_role.argument_constraints.get(&target_tool);

    let allowed_tools = if req.allowed_tools.is_empty() {
        vec![target_tool.clone()]
    } else {
        req.allowed_tools
    };

    match auth.issue_child_token(
        &parent_claims,
        &parent_effective_tools,
        parent_tool_constraints,
        DelegateChildTokenRequest {
            sub: req.sub,
            target_tool,
            child_dpop_jwk: req.child_dpop_jwk,
            allowed_tools,
            arg_constraints: req.arg_constraints,
            ttl_secs: req.ttl_secs,
        },
    ) {
        Ok(issued) => {
            if let Err(err) = state.poc_admission.check_chain_active(
                &issued.claims.chain_id,
                issued.claims.exp,
                chrono::Utc::now().timestamp(),
            ) {
                return admission_http_rejection(err);
            }
            (
                StatusCode::OK,
                Json(PocTokenResponse {
                    access_token: issued.as_str().to_string(),
                    token_type: "DPoP",
                    expires_in: issued.claims.exp - issued.claims.iat,
                    kid: auth.kid().to_string(),
                    iss: issued.claims.iss,
                    chain_id: issued.claims.chain_id,
                    jti: issued.claims.jti,
                    parent_jti: issued.claims.parent_jti,
                    depth: issued.claims.depth,
                    aud: issued.claims.aud,
                    tenant_id: issued.claims.tenant_id,
                    role: issued.claims.role,
                    act: issued.claims.act,
                }),
            )
                .into_response()
        }
        Err(LocalTokenError::DelegationDenied(msg)) => {
            (StatusCode::FORBIDDEN, Json(json!({ "error": msg }))).into_response()
        }
        Err(LocalTokenError::InvalidRequest(msg)) => {
            (StatusCode::BAD_REQUEST, Json(json!({ "error": msg }))).into_response()
        }
        Err(_) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({ "error": "delegation_failed" })),
        )
            .into_response(),
    }
}

#[derive(Debug, Deserialize)]
pub struct PocRevokeRequest {
    pub chain_id: String,
    #[serde(default)]
    pub tenant_id: Option<String>,
}

enum RevokeAuth {
    BootstrapSecret,
    ParentToken,
}

/// `POST /mcp/poc/revoke` — atomically revoke a `chain_id` across tokens and chain budget.
pub async fn handle_poc_revoke(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<PocRevokeRequest>,
) -> Response {
    let Some(ref auth) = state.local_agent_auth else {
        return StatusCode::NOT_FOUND.into_response();
    };

    let secret_authorized = state
        .config
        .poc_bootstrap_secret
        .as_deref()
        .filter(|s| !s.is_empty())
        .zip(
            headers
                .get("X-Stoa-Poc-Bootstrap-Secret")
                .and_then(|v| v.to_str().ok()),
        )
        .is_some_and(|(expected, provided)| {
            bool::from(provided.as_bytes().ct_eq(expected.as_bytes()))
        });

    let auth_kind = if secret_authorized {
        Some(RevokeAuth::BootstrapSecret)
    } else {
        let base = public_base_url(&state);
        let revoke_htu = format!("{base}/mcp/poc/revoke");
        let mcp_aud = format!("{base}/mcp/poc");
        match auth.validate_mcp_request(&headers, "POST", &revoke_htu, &mcp_aud) {
            Ok(claims) if claims.depth == 0 && claims.chain_id == req.chain_id.trim() => {
                Some(RevokeAuth::ParentToken)
            }
            _ => None,
        }
    };

    let Some(auth_kind) = auth_kind else {
        return (
            StatusCode::UNAUTHORIZED,
            Json(json!({ "error": "unauthorized" })),
        )
            .into_response();
    };

    let now_epoch = chrono::Utc::now().timestamp();
    let revoke_result = match auth_kind {
        RevokeAuth::BootstrapSecret => state.poc_admission.revoke_known_chain(
            &req.chain_id,
            req.tenant_id.as_deref(),
            None,
            now_epoch,
        ),
        RevokeAuth::ParentToken => state
            .poc_admission
            .revoke_chain(&req.chain_id, None, now_epoch),
    };
    match revoke_result {
        Ok(receipt) => (
            StatusCode::OK,
            Json(json!({
                "revoked": true,
                "chain_id": receipt.chain_id,
                "retain_until_epoch": receipt.retain_until_epoch
            })),
        )
            .into_response(),
        Err(AdmissionError::UnknownChain) => (
            StatusCode::NOT_FOUND,
            Json(json!({ "error": "unknown_chain" })),
        )
            .into_response(),
        Err(AdmissionError::TenantMismatch) => (
            StatusCode::FORBIDDEN,
            Json(json!({ "error": "tenant_mismatch" })),
        )
            .into_response(),
        Err(AdmissionError::RevocationTableFull) => (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({ "error": "revocation_table_full" })),
        )
            .into_response(),
        Err(err) => (
            StatusCode::BAD_REQUEST,
            Json(json!({ "error": err.to_string() })),
        )
            .into_response(),
    }
}

#[derive(Debug, Deserialize)]
struct PocJsonRpcRequest {
    jsonrpc: String,
    method: String,
    #[serde(default)]
    params: Option<Box<RawValue>>,
    id: Option<Value>,
}

#[derive(Debug, Deserialize)]
struct PocToolNameOnly {
    #[serde(default)]
    name: Option<String>,
}

/// `POST /mcp/poc` — Streamable HTTP JSON-RPC 2.0 entrypoint with local RS256 + DPoP.
pub async fn handle_poc_mcp(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    let Some(ref auth) = state.local_agent_auth else {
        return StatusCode::NOT_FOUND.into_response();
    };

    let request: PocJsonRpcRequest = match serde_json::from_slice(&body) {
        Ok(req) => req,
        Err(_) => {
            return (
                StatusCode::BAD_REQUEST,
                Json(JsonRpcResponse::error(None, PARSE_ERROR, "Parse error")),
            )
                .into_response();
        }
    };

    if request.jsonrpc != "2.0" {
        return (
            StatusCode::BAD_REQUEST,
            Json(JsonRpcResponse::error(
                request.id,
                INVALID_REQUEST,
                "Invalid JSON-RPC version",
            )),
        )
            .into_response();
    }

    // Pre-extract requested tool name for `tools/call` so child token canonical resource
    // audience (`mcp-tool:{tenant}:{canonical_tool}`) is validated strictly at auth time
    // without losing raw `params` lexemes.
    let requested_tool_name = if request.method == "tools/call" {
        request
            .params
            .as_deref()
            .and_then(|p| serde_json::from_str::<PocToolNameOnly>(p.get()).ok())
            .and_then(|p| p.name)
    } else {
        None
    };
    let is_limits_call = requested_tool_name.as_deref() == Some(POC_SECURITY_TOOL);

    let base = public_base_url(&state);
    let mcp_htu = format!("{base}/mcp/poc");
    let claims =
        match auth.validate_mcp_request_with_audience_fn(&headers, "POST", &mcp_htu, |claims| {
            if claims.depth == 0 && claims.iss == LOCAL_AGENT_ISSUER {
                Ok(mcp_htu.clone())
            } else if claims.depth > 0 && claims.iss == DELEGATION_ISSUER {
                let Some(ref req_name) = requested_tool_name else {
                    return Err(LocalTokenError::InvalidClaims(
                        "child token is only valid for tool calls targeting its resource",
                    ));
                };
                if is_limits_call {
                    // Introspection is local and read-only. Validate the child's
                    // audience against its signed tool grant even for this call.
                    let tool = child_audience_tool(claims).ok_or(
                        LocalTokenError::InvalidClaims("child token is missing its resource grant"),
                    )?;
                    return Ok(canonical_tool_audience(&claims.tenant_id, tool));
                }
                let canonical = state
                    .tool_registry
                    .get_for_tenant(req_name, &claims.tenant_id)
                    .map(|t| t.name().to_string())
                    .unwrap_or_else(|| req_name.clone());
                Ok(canonical_tool_audience(&claims.tenant_id, &canonical))
            } else {
                Err(LocalTokenError::InvalidClaims("unsupported token issuer"))
            }
        }) {
            Ok(claims) => claims,
            Err(err) => {
                if matches!(err, LocalTokenError::InvalidToken) {
                    state
                        .poc_admission
                        .observe_time(chrono::Utc::now().timestamp());
                }
                warn!(error = %err, "Rejected PoC MCP request");
                return (
                    StatusCode::UNAUTHORIZED,
                    Json(JsonRpcResponse::error(request.id, -32001, "Unauthorized")),
                )
                    .into_response();
            }
        };

    let response = match request.method.as_str() {
        "ping" => JsonRpcResponse::success(request.id, json!({})),
        "initialize" => JsonRpcResponse::success(
            request.id,
            json!({
                "protocolVersion": "2025-03-26",
                "capabilities": { "tools": { "listChanged": false } },
                "serverInfo": { "name": "stoa-gateway-poc", "version": env!("CARGO_PKG_VERSION") }
            }),
        ),
        "tools/list" => handle_poc_tools_list(&state, &claims, request.id).await,
        "tools/call" => handle_poc_tool_call(&state, &claims, request).await,
        "poc/subcalls" => handle_poc_subcalls(&state, &claims, request).await,
        other => JsonRpcResponse::error(
            request.id,
            METHOD_NOT_FOUND,
            format!("Method '{other}' not found"),
        ),
    };

    let mut response = (StatusCode::OK, Json(response)).into_response();
    if is_limits_call {
        response
            .headers_mut()
            .insert(CACHE_CONTROL, HeaderValue::from_static("no-store"));
    }
    response
}

fn child_audience_tool(claims: &LocalAgentClaims) -> Option<&str> {
    claims
        .allowed_tools
        .as_ref()?
        .iter()
        .find(|tool| canonical_tool_audience(&claims.tenant_id, tool) == claims.aud)
        .map(String::as_str)
}

fn poc_tool_context(claims: &LocalAgentClaims) -> ToolContext {
    ToolContext {
        tenant_id: claims.tenant_id.clone(),
        user_id: Some(claims.sub.clone()),
        user_email: None,
        request_id: Uuid::new_v4().to_string(),
        roles: vec![claims.role.clone()],
        scopes: vec![],
        raw_token: None,
        skill_instructions: None,
        progress_token: None,
        consumer_id: claims.sub.clone(),
        from_control_plane: false,
    }
}

async fn effective_poc_allowed_tools(
    state: &AppState,
    claims: &LocalAgentClaims,
) -> Result<(u64, HashSet<String>, RolePolicySpec), PocToolRejection> {
    let (store, version) = refreshed_poc_role_policy(state, claims).await?;
    store
        .effective_allowed_tools(
            &claims.tenant_id,
            &claims.role,
            version,
            claims.allowed_tools.as_deref(),
        )
        .map_err(|_| (-32003, "Role policy unavailable"))
}

async fn refreshed_poc_role_policy<'a>(
    state: &'a AppState,
    claims: &LocalAgentClaims,
) -> Result<(&'a RolePolicyStore, u64), PocToolRejection> {
    let store = state
        .role_policy_store
        .as_ref()
        .ok_or((-32003, "Role policy unavailable"))?;
    let version = claims
        .policy_version
        .ok_or((-32003, "Role policy unavailable"))?;
    store
        .refresh_tenant(&claims.tenant_id)
        .await
        .map_err(|_| (-32003, "Role policy unavailable"))?;
    Ok((store, version))
}

fn poc_caller_id(claims: &LocalAgentClaims) -> String {
    caller_identity_key(&claims.tenant_id, claims.root_caller_sub())
}

fn caller_identity_key(tenant: &str, root_subject: &str) -> String {
    let mut hash = Sha256::new();
    hash.update((tenant.len() as u64).to_be_bytes());
    hash.update(tenant.as_bytes());
    hash.update(root_subject.as_bytes());
    hash.finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn admission_http_rejection(err: AdmissionError) -> Response {
    let status = match err {
        AdmissionError::AdmissionTableFull | AdmissionError::RevocationTableFull => {
            StatusCode::SERVICE_UNAVAILABLE
        }
        AdmissionError::SessionExpired => StatusCode::UNAUTHORIZED,
        _ => StatusCode::FORBIDDEN,
    };
    (status, Json(json!({ "error": err.to_string() }))).into_response()
}

fn admission_rejection(err: AdmissionError) -> PocToolRejection {
    match err {
        AdmissionError::SessionExpired => (-32001, "Session expired"),
        AdmissionError::ChainRevoked => (-32003, "Chain revoked"),
        AdmissionError::ChainInactive => (-32003, "Chain inactive"),
        AdmissionError::ChainBudgetExceeded => (-32003, "Chain budget exceeded"),
        AdmissionError::CallerBudgetExceeded => (-32003, "Caller budget exceeded"),
        AdmissionError::AdmissionTableFull | AdmissionError::RevocationTableFull => {
            (-32005, "Admission unavailable")
        }
        AdmissionError::UnknownChain
        | AdmissionError::TenantMismatch
        | AdmissionError::InvalidInput(_) => (-32003, "Admission rejected"),
    }
}

async fn handle_poc_tools_list(
    state: &AppState,
    claims: &LocalAgentClaims,
    request_id: Option<Value>,
) -> JsonRpcResponse {
    if let Err(err) = state.poc_admission.check_chain_active(
        &claims.chain_id,
        claims.exp,
        chrono::Utc::now().timestamp(),
    ) {
        let (code, msg) = admission_rejection(err);
        return JsonRpcResponse::error(request_id, code, msg);
    }
    let allowed_tools = match effective_poc_allowed_tools(state, claims).await {
        Ok((_, allowed_tools, _)) => allowed_tools,
        Err((code, msg)) => return JsonRpcResponse::error(request_id, code, msg),
    };

    let mut tools: Vec<_> = visible_poc_tools(state, claims, &allowed_tools)
        .await
        .into_iter()
        .map(|def| {
            json!({
                "name": def.name,
                "description": def.description,
                "inputSchema": def.input_schema
            })
        })
        .collect();
    tools.push(poc_security_definition());
    JsonRpcResponse::success(request_id, json!({ "tools": tools }))
}

async fn visible_poc_tools(
    state: &AppState,
    claims: &LocalAgentClaims,
    allowed_tools: &HashSet<String>,
) -> Vec<ToolDefinition> {
    let ctx = poc_tool_context(claims);
    let mut tools = Vec::new();
    for def in state.tool_registry.list(Some(&claims.tenant_id)) {
        if !allowed_tools.contains(&def.name) {
            continue;
        }
        let registered = state
            .tool_registry
            .get_for_tenant(&def.name, &claims.tenant_id);
        if decide_poc_tool_access(state, &ctx, &def.name, registered.as_deref(), false)
            .await
            .is_ok()
        {
            tools.push(def);
        }
    }
    tools
}

async fn handle_poc_my_limits(
    state: &AppState,
    claims: &LocalAgentClaims,
    args: &Value,
) -> Result<Value, PocToolRejection> {
    if !is_my_limits_action(args) {
        return Err((INVALID_PARAMS, "Expected only action get_my_limits"));
    }
    let (store, issued_version) = refreshed_poc_role_policy(state, claims).await?;
    let (version, mut allowed_tools, mut constraints) = store
        .effective_limits(
            &claims.tenant_id,
            &claims.role,
            issued_version,
            claims.allowed_tools.as_deref(),
            claims.arg_constraints.as_ref(),
        )
        .map_err(|_| (-32003, "Role policy unavailable"))?;
    if claims.depth > 0 {
        let audience_tool = child_audience_tool(claims);
        allowed_tools.retain(|tool| Some(tool.as_str()) == audience_tool);
    }

    let mut visible_names: Vec<_> = visible_poc_tools(state, claims, &allowed_tools)
        .await
        .into_iter()
        .map(|def| def.name)
        .collect();
    constraints.retain(|tool, _| visible_names.contains(tool));
    visible_names.push(POC_SECURITY_TOOL.to_string());
    visible_names.sort_unstable();

    let budget = state
        .poc_admission
        .budget_snapshot(
            &claims.chain_id,
            &poc_caller_id(claims),
            claims.exp,
            chrono::Utc::now().timestamp(),
        )
        .map_err(admission_rejection)?;
    Ok(my_limits_result(json!({
        "role": claims.role,
        "issued_policy_version": issued_version,
        "policy_version": version,
        "allowed_tools": visible_names,
        "argument_constraints": constraints,
        "budgets": {
            "chain_remaining": budget.chain_remaining,
            "caller_remaining": budget.caller_remaining
        }
    })))
}

async fn decide_poc_tool_access<'a>(
    state: &AppState,
    ctx: &ToolContext,
    requested_name: &str,
    tool: Option<&'a dyn Tool>,
    audit_denial: bool,
) -> Result<&'a dyn Tool, PocToolRejection> {
    // Check signed tenant permissions with requested and canonical names.
    let canonical_name = tool.map_or(requested_name, Tool::name);
    if requested_name == POC_SECURITY_TOOL || canonical_name == POC_SECURITY_TOOL {
        return Err((-32003, "Security introspection requires a direct tool call"));
    }
    let perm_res = if audit_denial {
        check_tool_permission(state, &ctx.tenant_id, requested_name, canonical_name).await
    } else {
        check_tool_permission_quiet(state, &ctx.tenant_id, requested_name, canonical_name).await
    };
    perm_res.map_err(|_| (-32003, "Tool call rejected"))?;
    let tool = tool.ok_or((-32004, "Tool not found"))?;

    // Admin actions are never granted to local agent tokens.
    if matches!(
        tool.required_action(),
        Action::ManageTenants | Action::ManageUsers | Action::ManageContracts
    ) {
        return Err((-32003, "Admin action not permitted"));
    }

    check_tool_policy(state, tool, ctx).map_err(|_| (-32003, "Tool call rejected by policy"))?;
    Ok(tool)
}

async fn check_poc_tool_access<'a>(
    state: &AppState,
    ctx: &ToolContext,
    requested_name: &str,
    tool: Option<&'a dyn Tool>,
) -> Result<&'a dyn Tool, PocToolRejection> {
    decide_poc_tool_access(state, ctx, requested_name, tool, true).await
}

/// Parsed tool arguments paired with exact raw JSON lexemes for direct numeric fields.
#[derive(Debug, Default)]
struct PocCallArguments {
    value: Value,
    raw_number_fields: HashMap<String, String>,
}

impl PocCallArguments {
    fn from_raw_json(raw: &str) -> Result<Self, serde_json::Error> {
        let value: Value = serde_json::from_str(raw)?;
        let mut raw_number_fields = HashMap::new();
        if value.is_object() {
            let raw_fields: HashMap<String, Box<RawValue>> = serde_json::from_str(raw)?;
            for (key, field_raw) in raw_fields {
                if value.get(&key).is_some_and(Value::is_number) {
                    raw_number_fields.insert(key, field_raw.get().to_string());
                }
            }
        }
        Ok(Self {
            value,
            raw_number_fields,
        })
    }

    fn set_mapped_string(&mut self, key: String, text: String) {
        if let Some(obj) = self.value.as_object_mut() {
            obj.insert(key.clone(), Value::String(text));
            self.raw_number_fields.remove(&key);
        }
    }
}

impl<'de> Deserialize<'de> for PocCallArguments {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        let raw = Box::<RawValue>::deserialize(deserializer)?;
        Self::from_raw_json(raw.get()).map_err(serde::de::Error::custom)
    }
}

/// Shared authorization and execution pipeline for primary calls, sub-call steps, and fallbacks.
async fn authorize_and_execute_poc_tool(
    state: &AppState,
    claims: &LocalAgentClaims,
    requested_name: &str,
    arguments: PocCallArguments,
) -> Result<Value, PocToolRejection> {
    // Provenance comes from signed claims. The local context carries no raw token.
    let ctx = poc_tool_context(claims);
    let registered = state
        .tool_registry
        .get_for_tenant(requested_name, &claims.tenant_id);
    let tool = check_poc_tool_access(state, &ctx, requested_name, registered.as_deref()).await?;
    let canonical_name = tool.name();

    // 6. Signed role policy intersection (restrictive only) + anti-rollback + session
    //    anti-widening + deterministic v1 argument constraints + delegated token narrowing.
    let role_store = state
        .role_policy_store
        .as_ref()
        .ok_or((-32003, "Role policy unavailable"))?;
    let issued_ver = claims
        .policy_version
        .ok_or((-32003, "Role policy unavailable"))?;
    if let Err(err) = role_store.refresh_tenant(&claims.tenant_id).await {
        warn!(
            tool = %canonical_name,
            role = %claims.role,
            error = %err,
            "PoC call denied: role policy refresh failed"
        );
        return Err((-32003, "Tool call rejected by role policy"));
    }
    if let Err(err) = role_store.evaluate_call_with_raw(
        &RoleEvalInput {
            tenant_id: &claims.tenant_id,
            role: &claims.role,
            tool_name: canonical_name,
            args: &arguments.value,
            issued_policy_version: issued_ver,
            token_allowed_tools: claims.allowed_tools.as_deref(),
            token_constraints: claims.arg_constraints.as_ref(),
        },
        &arguments.raw_number_fields,
    ) {
        warn!(
            tool = %canonical_name,
            role = %claims.role,
            error = %err,
            "PoC call denied by role policy or argument constraint"
        );
        return Err((-32003, "Tool call rejected by role policy"));
    }

    // 7. Unified atomic admission: bounded chain revocation + all-or-nothing 2-level budget debit
    //    (chain + stable root caller). Executed AFTER authorization passes and BEFORE any upstream call.
    let caller_id = poc_caller_id(claims);
    if let Err(err) = state.poc_admission.admit_call(&AdmitCallRequest {
        chain_id: &claims.chain_id,
        caller_id: &caller_id,
        cost: 1,
        chain_limit: None,
        caller_limit: None,
        session_expires_at: claims.exp,
        now_epoch: chrono::Utc::now().timestamp(),
    }) {
        warn!(
            chain_id = %claims.chain_id,
            caller_id = %caller_id,
            error = %err,
            "PoC call rejected by atomic admission controller"
        );
        return Err(admission_rejection(err));
    }

    // 8. Execute tool (DynamicTool applies OutboundAddressPolicy to final URL and OAuth2 URL,
    //    disables redirects, injects backend credential without forwarding caller token,
    //    and scrubs error bodies).
    match tool.execute(arguments.value, &ctx).await {
        Ok(result) => Ok(json!({
            "content": result.content,
            "isError": result.is_error.unwrap_or(false)
        })),
        Err(err) => {
            warn!(tool = %tool.name(), error = %err, "PoC tool execution failed");
            Err((-32000, "Tool execution failed"))
        }
    }
}

#[derive(Debug, Deserialize)]
struct PocToolsCallParams {
    name: String,
    #[serde(default)]
    arguments: PocCallArguments,
}

#[derive(Debug, Deserialize)]
struct SubcallFallbackSpec {
    name: String,
    #[serde(default)]
    arguments: PocCallArguments,
}

#[derive(Debug, Deserialize)]
struct SubcallStepSpec {
    name: String,
    #[serde(default)]
    arguments: PocCallArguments,
    /// Optional argument key populated from the previous step's text output before authorization.
    #[serde(default)]
    map_prev_into_arg: Option<String>,
    /// Optional fallback step evaluated through the exact same authorization & constraint pipeline.
    #[serde(default)]
    fallback: Option<SubcallFallbackSpec>,
}

#[derive(Debug, Deserialize)]
struct PocSubcallsParams {
    steps: Vec<SubcallStepSpec>,
}

/// Execute sequential sub-calls without using `ComposedTool`: every step and any activated
/// fallback runs through [`authorize_and_execute_poc_tool`] on its final mapped arguments.
async fn handle_poc_subcalls(
    state: &AppState,
    claims: &LocalAgentClaims,
    request: PocJsonRpcRequest,
) -> JsonRpcResponse {
    let params = match request.params {
        Some(p) => p,
        None => return JsonRpcResponse::error(request.id, INVALID_PARAMS, "Missing params"),
    };
    let parsed: PocSubcallsParams = match serde_json::from_str(params.get()) {
        Ok(p) => p,
        Err(e) => {
            return JsonRpcResponse::error(
                request.id,
                INVALID_PARAMS,
                format!("Invalid poc/subcalls params: {e}"),
            );
        }
    };
    if parsed.steps.is_empty() || parsed.steps.len() > 16 {
        return JsonRpcResponse::error(
            request.id,
            INVALID_PARAMS,
            "steps must contain between 1 and 16 entries",
        );
    }

    let mut results = Vec::with_capacity(parsed.steps.len());
    let mut prev_text: Option<String> = None;

    for (idx, step) in parsed.steps.into_iter().enumerate() {
        let mut final_args = step.arguments;
        if let (Some(ref arg_key), Some(ref prev)) = (&step.map_prev_into_arg, &prev_text) {
            final_args.set_mapped_string(arg_key.clone(), prev.clone());
        }

        match authorize_and_execute_poc_tool(state, claims, &step.name, final_args).await {
            Ok(val) => {
                prev_text = val
                    .get("content")
                    .and_then(|c| c.get(0))
                    .and_then(|c| c.get("text"))
                    .and_then(Value::as_str)
                    .map(str::to_string);
                results.push(json!({ "step": idx, "tool": step.name, "result": val }));
            }
            // Only execution failures (-32000) may activate a fallback; authorization/budget
            // denials (-32003 / -32004) terminate immediately without calling fallback.
            Err((-32000, _)) if step.fallback.is_some() => {
                let fb = step.fallback.unwrap();
                match authorize_and_execute_poc_tool(state, claims, &fb.name, fb.arguments).await {
                    Ok(val) => {
                        prev_text = val
                            .get("content")
                            .and_then(|c| c.get(0))
                            .and_then(|c| c.get("text"))
                            .and_then(Value::as_str)
                            .map(str::to_string);
                        results.push(json!({
                            "step": idx,
                            "tool": fb.name,
                            "fallback_used": true,
                            "result": val
                        }));
                    }
                    Err((code, msg)) => return JsonRpcResponse::error(request.id, code, msg),
                }
            }
            Err((code, msg)) => return JsonRpcResponse::error(request.id, code, msg),
        }
    }

    JsonRpcResponse::success(request.id, json!({ "steps": results }))
}

async fn handle_poc_tool_call(
    state: &AppState,
    claims: &LocalAgentClaims,
    request: PocJsonRpcRequest,
) -> JsonRpcResponse {
    let params = match request.params {
        Some(p) => p,
        None => return JsonRpcResponse::error(request.id, INVALID_PARAMS, "Missing params"),
    };
    let call_req: PocToolsCallParams = match serde_json::from_str(params.get()) {
        Ok(r) => r,
        Err(e) => {
            return JsonRpcResponse::error(
                request.id,
                INVALID_PARAMS,
                format!("Invalid tools/call params: {e}"),
            );
        }
    };

    let result = if call_req.name == POC_SECURITY_TOOL {
        handle_poc_my_limits(state, claims, &call_req.arguments.value).await
    } else {
        authorize_and_execute_poc_tool(state, claims, &call_req.name, call_req.arguments).await
    };
    match result {
        Ok(result) => JsonRpcResponse::success(request.id, result),
        Err((code, msg)) => JsonRpcResponse::error(request.id, code, msg),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::auth::dpop::{compute_ath, compute_jwk_thumbprint};
    use crate::auth::local_agent_token::FORBIDDEN_CHILD_AUDIENCE;
    use crate::build_router;
    use crate::config::Config;
    use crate::control_plane::role_policy::ROLE_POLICY_ARTIFACT_TYP;
    use aws_lc_rs::signature::{
        EcdsaKeyPair, Ed25519KeyPair, KeyPair as _, ECDSA_P256_SHA256_FIXED_SIGNING,
    };
    use axum::body::Body;
    use axum::http::Request;
    use base64::engine::general_purpose::URL_SAFE_NO_PAD;
    use base64::Engine;
    use tower::ServiceExt;
    use wiremock::matchers::{header, method, path};
    use wiremock::{Mock, MockServer, ResponseTemplate};

    struct TestDpop {
        kp: EcdsaKeyPair,
        jwk: DpopJwk,
    }

    impl TestDpop {
        fn new() -> Self {
            let pkcs8 = EcdsaKeyPair::generate_pkcs8(
                &ECDSA_P256_SHA256_FIXED_SIGNING,
                &aws_lc_rs::rand::SystemRandom::new(),
            )
            .unwrap();
            let kp =
                EcdsaKeyPair::from_pkcs8(&ECDSA_P256_SHA256_FIXED_SIGNING, pkcs8.as_ref()).unwrap();
            let pub_bytes = kp.public_key().as_ref();
            let jwk = DpopJwk {
                kty: "EC".to_string(),
                crv: Some("P-256".to_string()),
                x: Some(URL_SAFE_NO_PAD.encode(&pub_bytes[1..33])),
                y: Some(URL_SAFE_NO_PAD.encode(&pub_bytes[33..65])),
                n: None,
                e: None,
                d: None,
                p: None,
                q: None,
            };
            Self { kp, jwk }
        }

        fn proof(&self, htm: &str, htu: &str, jti: &str, token: Option<&str>) -> String {
            let header = json!({
                "typ": "dpop+jwt",
                "alg": "ES256",
                "jwk": {
                    "kty": self.jwk.kty,
                    "crv": self.jwk.crv,
                    "x": self.jwk.x,
                    "y": self.jwk.y,
                }
            });
            let mut claims = json!({
                "jti": jti,
                "htm": htm,
                "htu": htu,
                "iat": chrono::Utc::now().timestamp(),
            });
            if let Some(t) = token {
                claims["ath"] = json!(compute_ath(t));
            }
            let h = URL_SAFE_NO_PAD.encode(serde_json::to_vec(&header).unwrap());
            let c = URL_SAFE_NO_PAD.encode(serde_json::to_vec(&claims).unwrap());
            let input = format!("{h}.{c}");
            let sig = self
                .kp
                .sign(&aws_lc_rs::rand::SystemRandom::new(), input.as_bytes())
                .unwrap();
            format!("{input}.{}", URL_SAFE_NO_PAD.encode(sig.as_ref()))
        }
    }

    struct PolicyFixtureSigner {
        kp: Ed25519KeyPair,
        kid: String,
        tenant_uuid: Uuid,
    }

    impl PolicyFixtureSigner {
        fn new() -> Self {
            let pkcs8 =
                Ed25519KeyPair::generate_pkcs8(&aws_lc_rs::rand::SystemRandom::new()).unwrap();
            let kp = Ed25519KeyPair::from_pkcs8(pkcs8.as_ref()).unwrap();
            Self {
                kp,
                kid: "cp-policy-202611-1".to_string(),
                tenant_uuid: Uuid::new_v4(),
            }
        }

        fn write_trust(&self, dir: &Path) -> String {
            let x = URL_SAFE_NO_PAD.encode(self.kp.public_key().as_ref());
            let trust_path = dir.join("trust-jwks.json");
            std::fs::write(
                &trust_path,
                serde_json::to_string(&json!({
                    "keys": [{
                        "kty": "OKP",
                        "crv": "Ed25519",
                        "alg": "EdDSA",
                        "use": "sig",
                        "kid": self.kid,
                        "x": x
                    }]
                }))
                .unwrap(),
            )
            .unwrap();
            trust_path.to_string_lossy().to_string()
        }

        fn sign_tool_policy(&self, tenant: &str, tools: &[&str]) -> String {
            let now = chrono::Utc::now();
            let h = URL_SAFE_NO_PAD.encode(
                serde_json::to_vec(&json!({
                    "alg": "EdDSA",
                    "typ": "stoa-tool-policy+jws",
                    "kid": self.kid
                }))
                .unwrap(),
            );
            let perms: Vec<Value> = tools
                .iter()
                .map(|t| json!({"mcp_server": "poc-payments", "tool": t, "allowed": true}))
                .collect();
            let p = URL_SAFE_NO_PAD.encode(
                serde_json::to_vec(&json!({
                    "iss": "stoa-poc-policy",
                    "aud": "stoa-gateway",
                    "tenant_id": tenant,
                    "tenant_uuid": self.tenant_uuid.to_string(),
                    "version": 1,
                    "issued_at": now.to_rfc3339(),
                    "expires_at": (now + chrono::Duration::minutes(10)).to_rfc3339(),
                    "permissions": perms
                }))
                .unwrap(),
            );
            let input = format!("{h}.{p}");
            let sig = self.kp.sign(input.as_bytes());
            format!("{input}.{}", URL_SAFE_NO_PAD.encode(sig.as_ref()))
        }

        fn sign_role_policy(&self, tenant: &str, version: u64, roles: Value) -> String {
            let now = chrono::Utc::now();
            let h = URL_SAFE_NO_PAD.encode(
                serde_json::to_vec(&json!({
                    "alg": "EdDSA",
                    "typ": ROLE_POLICY_ARTIFACT_TYP,
                    "kid": self.kid
                }))
                .unwrap(),
            );
            let p = URL_SAFE_NO_PAD.encode(
                serde_json::to_vec(&json!({
                    "iss": "stoa-poc-policy",
                    "aud": "stoa-gateway",
                    "tenant_id": tenant,
                    "tenant_uuid": self.tenant_uuid.to_string(),
                    "version": version,
                    "issued_at": now.to_rfc3339(),
                    "expires_at": (now + chrono::Duration::minutes(10)).to_rfc3339(),
                    "roles": roles
                }))
                .unwrap(),
            );
            let input = format!("{h}.{p}");
            let sig = self.kp.sign(input.as_bytes());
            format!("{input}.{}", URL_SAFE_NO_PAD.encode(sig.as_ref()))
        }
    }

    #[tokio::test]
    async fn local_fixtures_require_a_role_policy_store() {
        let state = AppState::new(Config {
            poc_agents_enabled: true,
            auto_register: false,
            ..Config::default()
        });
        let error = load_poc_fixtures(&state).await.unwrap_err();
        assert_eq!(error, "Role policy is not configured");
    }

    #[test]
    fn caller_budgets_use_qualified_identities() {
        use crate::auth::poc_admission::{PocAdmissionController, MAX_ADMISSION_ID_LEN};

        let first = caller_identity_key("example:lab", "operator");
        let second = caller_identity_key("example", "lab:operator");
        assert_ne!(first, second);
        assert!(
            caller_identity_key(&"x".repeat(128), &"y".repeat(256)).len() <= MAX_ADMISSION_ID_LEN
        );

        let admission = PocAdmissionController::new(Default::default());
        for (chain, caller) in [("first-chain", &first), ("second-chain", &second)] {
            admission.register_chain(chain, 61, 1).unwrap();
            admission
                .admit_call(&AdmitCallRequest {
                    chain_id: chain,
                    caller_id: caller,
                    cost: 1,
                    chain_limit: Some(1),
                    caller_limit: Some(1),
                    session_expires_at: 61,
                    now_epoch: 1,
                })
                .unwrap();
        }
        assert_eq!(admission.caller_used(&first), 1);
        assert_eq!(admission.caller_used(&second), 1);
    }

    #[tokio::test]
    async fn jalon1_autonomous_bootstrap_dpop_ready_and_admin_isolation() {
        let upstream = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/payments"))
            .and(header("X-API-Key", "backend-key-secret"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({"status": "ok"})))
            .expect(1)
            .mount(&upstream)
            .await;

        let tmp = tempfile::tempdir().unwrap();
        let tool_name = "payments_list";
        let signer = PolicyFixtureSigner::new();
        let trust_file = signer.write_trust(tmp.path());
        let policies_dir = tmp.path().join("policies");
        std::fs::create_dir_all(&policies_dir).unwrap();
        std::fs::write(
            policies_dir.join("acme.jws"),
            signer.sign_tool_policy("acme", &[tool_name]),
        )
        .unwrap();

        let roles_dir = tmp.path().join("roles");
        std::fs::create_dir(&roles_dir).unwrap();
        std::fs::write(
            roles_dir.join("acme.roles.jws"),
            signer.sign_role_policy(
                "acme",
                1,
                json!({
                    "reader": { "allowed_tools": [tool_name] }
                }),
            ),
        )
        .unwrap();

        let contracts_dir = tmp.path().join("contracts");
        std::fs::create_dir_all(&contracts_dir).unwrap();
        std::fs::write(
            contracts_dir.join("payments.uac.json"),
            serde_json::to_string(&json!({
                "name": "payments",
                "version": "1.0.0",
                "tenant_id": "acme",
                "display_name": "Payments",
                "description": "PoC payments API",
                "classification": "H",
                "endpoints": [{
                    "path": "/payments",
                    "methods": ["GET"],
                    "backend_url": format!("{}/payments", upstream.uri()),
                    "operation_id": "list_payments",
                    "llm": {
                        "summary": "List payments",
                        "intent": "Read payments",
                        "tool_name": tool_name,
                        "side_effects": "read",
                        "safe_for_agents": true,
                        "requires_human_approval": false,
                        "examples": []
                    }
                }],
                "required_policies": [],
                "status": "published"
            }))
            .unwrap(),
        )
        .unwrap();

        let creds_file = tmp.path().join("credentials.json");
        std::fs::write(
            &creds_file,
            serde_json::to_string(&json!([{
                "route_id": format!("mcp-tool:acme:{tool_name}"),
                "auth_type": "api_key",
                "header_name": "X-API-Key",
                "header_value": "backend-key-secret",
                "allowed_origin": upstream.uri(),
                "shared_with_tenants": false
            }]))
            .unwrap(),
        )
        .unwrap();

        let base_url = "http://stoa-gateway:8080";
        let config = Config {
            auto_register: false,
            admin_routes_disabled: true,
            policy_enabled: false,
            policy_boot_tenants: vec!["acme".to_string()],
            policy_trust_jwks_file: Some(trust_file),
            policy_local_artifacts_dir: Some(policies_dir.to_string_lossy().to_string()),
            policy_expected_issuer: "stoa-poc-policy".to_string(),
            policy_audience: "stoa-gateway".to_string(),
            poc_agents_enabled: true,
            poc_bootstrap_secret: Some("parent-only-bootstrap-secret".to_string()),
            poc_role_artifacts_dir: Some(roles_dir.to_string_lossy().into_owned()),
            poc_uac_contracts_dir: Some(contracts_dir.to_string_lossy().to_string()),
            poc_credentials_file: Some(creds_file.to_string_lossy().to_string()),
            poc_public_base_url: Some(base_url.to_string()),
            poc_outbound_allowed_origins: vec![upstream.uri()],
            ..Config::default()
        };

        let state = AppState::new(config);
        let loaded = load_poc_fixtures(&state).await.expect("load poc fixtures");
        assert_eq!(loaded.credentials_loaded, 1);
        assert_eq!(loaded.contracts_loaded, 1);
        assert_eq!(loaded.role_policies_loaded, 1);
        assert_eq!(loaded.tools_registered, 1);

        let app = build_router(state.clone());

        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .uri("/ready")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::SERVICE_UNAVAILABLE);

        state
            .tool_permissions
            .as_ref()
            .unwrap()
            .load_policy("acme")
            .await
            .expect("load signed local policy");

        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .uri("/ready")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);

        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .uri("/admin/health")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::NOT_FOUND);

        let dpop = TestDpop::new();
        let boot_htu = format!("{base_url}/mcp/poc/bootstrap");
        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/mcp/poc/bootstrap")
                    .header("content-type", "application/json")
                    .header(
                        "DPoP",
                        dpop.proof("POST", &boot_htu, "boot-no-secret", None),
                    )
                    .body(Body::from(
                        json!({"sub":"agent-child","tenant_id":"acme","role":"reader"}).to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);

        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/mcp/poc/bootstrap")
                    .header("content-type", "application/json")
                    .header(
                        "X-Stoa-Poc-Bootstrap-Secret",
                        "parent-only-bootstrap-secret",
                    )
                    .header("DPoP", dpop.proof("POST", &boot_htu, "boot-1", None))
                    .body(Body::from(
                        json!({"sub":"agent-parent","tenant_id":"acme","role":"reader"})
                            .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let body = axum::body::to_bytes(resp.into_body(), 16 * 1024)
            .await
            .unwrap();
        let boot_json: Value = serde_json::from_slice(&body).unwrap();
        let token = boot_json["access_token"].as_str().unwrap().to_string();

        let mcp_htu = format!("{base_url}/mcp/poc");
        let call_body = json!({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": { "name": tool_name, "arguments": {} }
        })
        .to_string();
        let proof = dpop.proof("POST", &mcp_htu, "call-1", Some(&token));
        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/mcp/poc")
                    .header("content-type", "application/json")
                    .header("Authorization", format!("DPoP {token}"))
                    .header("DPoP", &proof)
                    .header("X-Stoa-Source", "control-plane")
                    .body(Body::from(call_body.clone()))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let body = axum::body::to_bytes(resp.into_body(), 16 * 1024)
            .await
            .unwrap();
        let rpc: Value = serde_json::from_slice(&body).unwrap();
        assert!(rpc.get("error").is_none(), "unexpected RPC error: {rpc}");

        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/mcp/poc")
                    .header("content-type", "application/json")
                    .header("Authorization", format!("DPoP {token}"))
                    .header("DPoP", &proof)
                    .body(Body::from(call_body))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);

        let received = upstream.received_requests().await.unwrap();
        assert_eq!(received.len(), 1);
        assert!(received[0].headers.get("authorization").is_none());
        assert!(!compute_jwk_thumbprint(&dpop.jwk).is_empty());
    }

    #[tokio::test]
    async fn jalon2_vertical_proof_roles_delegation_constraints_opa_outbound_and_redirects() {
        let upstream = MockServer::start().await;
        let redirect_target = MockServer::start().await;
        let blocked_internal = MockServer::start().await;

        // Allowed upstream endpoint
        Mock::given(method("GET"))
            .and(path("/payments"))
            .and(header("X-API-Key", "backend-secret-j2"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({"ok": true})))
            .mount(&upstream)
            .await;

        // 3xx redirect endpoint (must NOT follow redirect to redirect_target)
        Mock::given(method("GET"))
            .and(path("/redirect"))
            .respond_with(
                ResponseTemplate::new(302)
                    .insert_header("Location", format!("{}/secret", redirect_target.uri()))
                    .set_body_string("sensitive-upstream-redirect-body"),
            )
            .mount(&upstream)
            .await;
        Mock::given(method("GET"))
            .and(path("/secret"))
            .respond_with(ResponseTemplate::new(200).set_body_string("should-not-reach"))
            .expect(0)
            .mount(&redirect_target)
            .await;

        // Blocked internal target (NOT in poc_outbound_allowed_origins)
        Mock::given(method("GET"))
            .and(path("/internal"))
            .respond_with(ResponseTemplate::new(200).set_body_string("internal-data"))
            .expect(0)
            .mount(&blocked_internal)
            .await;

        let tmp = tempfile::tempdir().unwrap();
        let signer = PolicyFixtureSigner::new();
        let trust_file = signer.write_trust(tmp.path());

        let policies_dir = tmp.path().join("policies");
        let roles_dir = tmp.path().join("roles");
        let floor_dir = tmp.path().join("floors");
        let contracts_dir = tmp.path().join("contracts");
        let opa_dir = tmp.path().join("opa");
        for d in [&policies_dir, &roles_dir, &contracts_dir, &opa_dir] {
            std::fs::create_dir_all(d).unwrap();
        }

        // Tenant tool permissions allow all 4 fixture tools; OPA & role policy restrict further!
        std::fs::write(
            policies_dir.join("acme.jws"),
            signer.sign_tool_policy(
                "acme",
                &[
                    "payments_list",
                    "payments_opa_denied",
                    "payments_redirect",
                    "payments_outbound_blocked",
                ],
            ),
        )
        .unwrap();

        // OPA allows payments_list, payments_redirect, payments_outbound_blocked; explicitly denies payments_opa_denied.
        let opa_file = opa_dir.join("policy.rego");
        std::fs::write(
            &opa_file,
            r#"package stoa.authz
import future.keywords.if
default allow := false
allow if {
    input.tenant_id == "acme"
    input.resource_tenant_id == "acme"
    input.tool_name != "payments_opa_denied"
    input.action == "Read"
}
"#,
        )
        .unwrap();

        // Signed role artifact v1 with all 3 argument constraint types on payments_list.
        std::fs::write(
            roles_dir.join("acme.roles.jws"),
            signer.sign_role_policy(
                "acme",
                1,
                json!({
                    "reader": {
                        "allowed_tools": [
                            "payments_list",
                            "payments_opa_denied",
                            "payments_redirect",
                            "payments_outbound_blocked"
                        ],
                        "argument_constraints": {
                            "payments_list": {
                                "currency": { "type": "allowed_values", "values": ["EUR", "USD"] },
                                "account": { "type": "prefix", "prefix": "acct-" },
                                "limit": { "type": "max_number", "max": 100.0 }
                            }
                        }
                    }
                }),
            ),
        )
        .unwrap();

        std::fs::write(
            contracts_dir.join("payments.uac.json"),
            serde_json::to_string(&json!({
                "name": "payments",
                "version": "1.0.0",
                "tenant_id": "acme",
                "display_name": "Payments",
                "description": "Jalon 2 fixture",
                "classification": "H",
                "endpoints": [
                    {
                        "path": "/payments",
                        "methods": ["GET"],
                        "backend_url": format!("{}/payments", upstream.uri()),
                        "operation_id": "list_payments",
                        "llm": {
                            "summary": "List payments",
                            "intent": "Read payments",
                            "tool_name": "payments_list",
                            "side_effects": "read",
                            "safe_for_agents": true,
                            "requires_human_approval": false,
                            "examples": []
                        }
                    },
                    {
                        "path": "/opa-denied",
                        "methods": ["GET"],
                        "backend_url": format!("{}/payments", upstream.uri()),
                        "operation_id": "opa_denied",
                        "llm": {
                            "summary": "OPA denied tool",
                            "intent": "Negative OPA test",
                            "tool_name": "payments_opa_denied",
                            "side_effects": "read",
                            "safe_for_agents": true,
                            "requires_human_approval": false,
                            "examples": []
                        }
                    },
                    {
                        "path": "/redirect",
                        "methods": ["GET"],
                        "backend_url": format!("{}/redirect", upstream.uri()),
                        "operation_id": "redirect_tool",
                        "llm": {
                            "summary": "Redirect test tool",
                            "intent": "Verify redirects are not followed",
                            "tool_name": "payments_redirect",
                            "side_effects": "read",
                            "safe_for_agents": true,
                            "requires_human_approval": false,
                            "examples": []
                        }
                    },
                    {
                        "path": "/internal",
                        "methods": ["GET"],
                        "backend_url": format!("{}/internal", blocked_internal.uri()),
                        "operation_id": "outbound_blocked",
                        "llm": {
                            "summary": "Blocked internal tool",
                            "intent": "Verify outbound address policy blocks non-allowlisted loopback",
                            "tool_name": "payments_outbound_blocked",
                            "side_effects": "read",
                            "safe_for_agents": true,
                            "requires_human_approval": false,
                            "examples": []
                        }
                    }
                ],
                "required_policies": [],
                "status": "published"
            }))
            .unwrap(),
        )
        .unwrap();

        let creds_file = tmp.path().join("credentials.json");
        std::fs::write(
            &creds_file,
            serde_json::to_string(&json!([{
                "route_id": "mcp-tool:acme:payments_list",
                "auth_type": "api_key",
                "header_name": "X-API-Key",
                "header_value": "backend-secret-j2",
                "allowed_origin": upstream.uri(),
                "shared_with_tenants": false
            }]))
            .unwrap(),
        )
        .unwrap();

        let base_url = "http://stoa-gateway:8080";
        let config = Config {
            auto_register: false,
            admin_routes_disabled: true,
            policy_enabled: true,
            policy_path: Some(opa_file.to_string_lossy().to_string()),
            policy_boot_tenants: vec!["acme".to_string()],
            policy_trust_jwks_file: Some(trust_file),
            policy_local_artifacts_dir: Some(policies_dir.to_string_lossy().to_string()),
            policy_expected_issuer: "stoa-poc-policy".to_string(),
            policy_audience: "stoa-gateway".to_string(),
            poc_agents_enabled: true,
            poc_bootstrap_secret: Some("boot-secret-j2".to_string()),
            poc_uac_contracts_dir: Some(contracts_dir.to_string_lossy().to_string()),
            poc_credentials_file: Some(creds_file.to_string_lossy().to_string()),
            poc_public_base_url: Some(base_url.to_string()),
            poc_role_artifacts_dir: Some(roles_dir.to_string_lossy().to_string()),
            poc_role_floor_dir: Some(floor_dir.to_string_lossy().to_string()),
            // Allow ONLY `upstream`; `blocked_internal` and `redirect_target` are NOT allowed!
            poc_outbound_allowed_origins: vec![upstream.uri()],
            ..Config::default()
        };

        let state = AppState::new(config);
        let summary = load_poc_fixtures(&state).await.expect("load j2 fixtures");
        assert_eq!(summary.role_policies_loaded, 1);
        state
            .tool_permissions
            .as_ref()
            .unwrap()
            .load_policy("acme")
            .await
            .unwrap();
        let app = build_router(state);

        // 1. Parent bootstraps token.
        let parent_dpop = TestDpop::new();
        let child_dpop = TestDpop::new();
        let boot_htu = format!("{base_url}/mcp/poc/bootstrap");
        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/mcp/poc/bootstrap")
                    .header("content-type", "application/json")
                    .header("X-Stoa-Poc-Bootstrap-Secret", "boot-secret-j2")
                    .header("DPoP", parent_dpop.proof("POST", &boot_htu, "b1", None))
                    .body(Body::from(
                        json!({"sub":"agent-parent","tenant_id":"acme","role":"reader","ttl_secs":300})
                            .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let parent_tok = serde_json::from_slice::<Value>(
            &axum::body::to_bytes(resp.into_body(), 16 * 1024)
                .await
                .unwrap(),
        )
        .unwrap()["access_token"]
            .as_str()
            .unwrap()
            .to_string();

        // 2. Parent delegates narrowed child token (EUR only, limit <= 25).
        let del_htu = format!("{base_url}/mcp/poc/delegate");
        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/mcp/poc/delegate")
                    .header("content-type", "application/json")
                    .header("Authorization", format!("DPoP {parent_tok}"))
                    .header(
                        "DPoP",
                        parent_dpop.proof("POST", &del_htu, "d1", Some(&parent_tok)),
                    )
                    .body(Body::from(
                        json!({
                            "sub": "agent-child",
                            "target_tool": "payments_list",
                            "child_dpop_jwk": {
                                "kty": child_dpop.jwk.kty,
                                "crv": child_dpop.jwk.crv,
                                "x": child_dpop.jwk.x,
                                "y": child_dpop.jwk.y
                            },
                            "allowed_tools": ["payments_list", "payments_redirect"],
                            "arg_constraints": {
                                "currency": { "type": "allowed_values", "values": ["EUR"] },
                                "limit": { "type": "max_number", "max": 25.0 }
                            },
                            "ttl_secs": 120
                        })
                        .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let child_json: Value = serde_json::from_slice(
            &axum::body::to_bytes(resp.into_body(), 16 * 1024)
                .await
                .unwrap(),
        )
        .unwrap();
        assert_eq!(child_json["iss"], DELEGATION_ISSUER);
        assert_eq!(child_json["aud"], "mcp-tool:acme:payments_list");
        assert_eq!(child_json["depth"], 1);
        assert_eq!(child_json["tenant_id"], "acme");
        let child_tok = child_json["access_token"].as_str().unwrap().to_string();

        let mcp_htu = format!("{base_url}/mcp/poc");
        let read_limits = |proof_id: &str, args: Value| {
            app.clone().oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/mcp/poc")
                    .header("content-type", "application/json")
                    .header("Authorization", format!("DPoP {child_tok}"))
                    .header(
                        "DPoP",
                        child_dpop.proof("POST", &mcp_htu, proof_id, Some(&child_tok)),
                    )
                    .body(Body::from(
                        json!({
                            "jsonrpc": "2.0", "id": 100, "method": "tools/call",
                            "params": { "name": POC_SECURITY_TOOL, "arguments": args }
                        })
                        .to_string(),
                    ))
                    .unwrap(),
            )
        };
        let args = json!({"action": "get_my_limits"});
        let mut initial_budgets = None;
        for proof_id in ["limits-child-1", "limits-child-2"] {
            let resp = read_limits(proof_id, args.clone()).await.unwrap();
            assert_eq!(resp.status(), StatusCode::OK);
            assert_eq!(resp.headers()[CACHE_CONTROL], "no-store");
            let rpc: Value = serde_json::from_slice(
                &axum::body::to_bytes(resp.into_body(), 16 * 1024)
                    .await
                    .unwrap(),
            )
            .unwrap();
            let result = &rpc["result"];
            let limits = &result["structuredContent"];
            assert_eq!(
                serde_json::from_str::<Value>(result["content"][0]["text"].as_str().unwrap())
                    .unwrap(),
                *limits
            );
            assert_eq!(limits["role"], "reader");
            assert_eq!(limits["issued_policy_version"], 1);
            assert_eq!(limits["policy_version"], 1);
            assert_eq!(
                limits["allowed_tools"],
                json!(["payments_list", POC_SECURITY_TOOL])
            );
            assert_eq!(
                limits["argument_constraints"],
                json!({
                    "payments_list": {
                        "currency": [
                            {"type": "allowed_values", "values": ["EUR", "USD"]},
                            {"type": "allowed_values", "values": ["EUR"]}
                        ],
                        "account": [{"type": "prefix", "prefix": "acct-"}],
                        "limit": [
                            {"type": "max_number", "max": 100.0},
                            {"type": "max_number", "max": 25.0}
                        ]
                    }
                })
            );
            let budgets = initial_budgets.get_or_insert_with(|| limits["budgets"].clone());
            assert_eq!(limits["budgets"], *budgets);
        }

        let resp = read_limits(
            "limits-invalid-args",
            json!({
                "action": "get_my_limits", "role": "someone_else"
            }),
        )
        .await
        .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let rpc: Value = serde_json::from_slice(
            &axum::body::to_bytes(resp.into_body(), 16 * 1024)
                .await
                .unwrap(),
        )
        .unwrap();
        assert_eq!(rpc["error"]["code"], INVALID_PARAMS);

        // 3. Child call with conforming args succeeds!
        let ok_call = json!({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "payments_list",
                "arguments": { "currency": "EUR", "account": "acct-123", "limit": 20 }
            }
        })
        .to_string();
        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/mcp/poc")
                    .header("content-type", "application/json")
                    .header("Authorization", format!("DPoP {child_tok}"))
                    .header(
                        "DPoP",
                        child_dpop.proof("POST", &mcp_htu, "c1", Some(&child_tok)),
                    )
                    .body(Body::from(ok_call))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let rpc: Value = serde_json::from_slice(
            &axum::body::to_bytes(resp.into_body(), 16 * 1024)
                .await
                .unwrap(),
        )
        .unwrap();
        assert!(rpc.get("error").is_none(), "child call should pass: {rpc}");

        // 4. Child call violating narrowed child constraint (USD allowed by parent, denied for child;
        //    limit=50 allowed by parent, denied for child; bad prefix) -> denied with ZERO upstream calls!
        let bad_args_cases = [
            json!({ "currency": "USD", "account": "acct-123", "limit": 20 }),
            json!({ "currency": "EUR", "account": "other-123", "limit": 20 }),
            json!({ "currency": "EUR", "account": "acct-123", "limit": 50 }),
        ];
        for (idx, args) in bad_args_cases.iter().enumerate() {
            let body = json!({
                "jsonrpc": "2.0",
                "id": 10 + idx,
                "method": "tools/call",
                "params": { "name": "payments_list", "arguments": args }
            })
            .to_string();
            let resp = app
                .clone()
                .oneshot(
                    Request::builder()
                        .method("POST")
                        .uri("/mcp/poc")
                        .header("content-type", "application/json")
                        .header("Authorization", format!("DPoP {child_tok}"))
                        .header(
                            "DPoP",
                            child_dpop.proof(
                                "POST",
                                &mcp_htu,
                                &format!("bad-{idx}"),
                                Some(&child_tok),
                            ),
                        )
                        .body(Body::from(body))
                        .unwrap(),
                )
                .await
                .unwrap();
            assert_eq!(resp.status(), StatusCode::OK);
            let rpc: Value = serde_json::from_slice(
                &axum::body::to_bytes(resp.into_body(), 16 * 1024)
                    .await
                    .unwrap(),
            )
            .unwrap();
            assert_eq!(rpc["error"]["code"], -32003, "arguments: {args}");
            assert_eq!(rpc["error"]["message"], "Tool call rejected by role policy");
        }

        // 5. OPA negative case (parent calls payments_opa_denied -> denied, zero upstream calls!)
        let opa_denied_body = json!({
            "jsonrpc": "2.0",
            "id": 20,
            "method": "tools/call",
            "params": { "name": "payments_opa_denied", "arguments": {} }
        })
        .to_string();
        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/mcp/poc")
                    .header("content-type", "application/json")
                    .header("Authorization", format!("DPoP {parent_tok}"))
                    .header(
                        "DPoP",
                        parent_dpop.proof("POST", &mcp_htu, "opa-neg", Some(&parent_tok)),
                    )
                    .body(Body::from(opa_denied_body))
                    .unwrap(),
            )
            .await
            .unwrap();
        let rpc: Value = serde_json::from_slice(
            &axum::body::to_bytes(resp.into_body(), 16 * 1024)
                .await
                .unwrap(),
        )
        .unwrap();
        assert_eq!(rpc["error"]["message"], "Tool call rejected by policy");

        // 6. Outbound address policy blocks non-allowlisted internal target (zero requests to blocked_internal!)
        let blocked_body = json!({
            "jsonrpc": "2.0",
            "id": 21,
            "method": "tools/call",
            "params": { "name": "payments_outbound_blocked", "arguments": {} }
        })
        .to_string();
        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/mcp/poc")
                    .header("content-type", "application/json")
                    .header("Authorization", format!("DPoP {parent_tok}"))
                    .header(
                        "DPoP",
                        parent_dpop.proof("POST", &mcp_htu, "outbound-neg", Some(&parent_tok)),
                    )
                    .body(Body::from(blocked_body))
                    .unwrap(),
            )
            .await
            .unwrap();
        let rpc: Value = serde_json::from_slice(
            &axum::body::to_bytes(resp.into_body(), 16 * 1024)
                .await
                .unwrap(),
        )
        .unwrap();
        assert!(rpc.get("error").is_some());

        // 7. 3xx redirect is NOT followed and upstream body is scrubbed!
        let redir_body = json!({
            "jsonrpc": "2.0",
            "id": 22,
            "method": "tools/call",
            "params": { "name": "payments_redirect", "arguments": {} }
        })
        .to_string();
        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/mcp/poc")
                    .header("content-type", "application/json")
                    .header("Authorization", format!("DPoP {parent_tok}"))
                    .header(
                        "DPoP",
                        parent_dpop.proof("POST", &mcp_htu, "redir-neg", Some(&parent_tok)),
                    )
                    .body(Body::from(redir_body))
                    .unwrap(),
            )
            .await
            .unwrap();
        let body_str = String::from_utf8(
            axum::body::to_bytes(resp.into_body(), 16 * 1024)
                .await
                .unwrap()
                .to_vec(),
        )
        .unwrap();
        assert!(body_str.contains("Tool execution failed"));
        assert!(!body_str.contains("sensitive-upstream-redirect-body"));

        // Verify exact upstream counters:
        // - upstream saw ONLY 1 /payments call (from child) + 1 /redirect call (302 not followed)
        // - redirect_target saw 0 calls
        // - blocked_internal saw 0 calls
        let up_reqs = upstream.received_requests().await.unwrap();
        let payment_calls: Vec<_> = up_reqs
            .iter()
            .filter(|r| r.url.path() == "/payments")
            .collect();
        assert_eq!(payment_calls.len(), 1);
        assert!(payment_calls[0].headers.get("authorization").is_none());
        assert_eq!(redirect_target.received_requests().await.unwrap().len(), 0);
        assert_eq!(blocked_internal.received_requests().await.unwrap().len(), 0);
    }

    #[tokio::test]
    async fn jalon3_subcalls_fallback_revocation_two_level_budgets_and_filtered_list() {
        let primary_up = MockServer::start().await;
        let denied_up = MockServer::start().await;
        let failing_up = MockServer::start().await;

        Mock::given(method("GET"))
            .and(path("/payments"))
            .and(header("X-API-Key", "backend-key-j3"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({"ok": true})))
            .mount(&primary_up)
            .await;
        Mock::given(method("GET"))
            .and(path("/forbidden"))
            .respond_with(ResponseTemplate::new(200).set_body_string("forbidden-reached"))
            .expect(0)
            .mount(&denied_up)
            .await;
        Mock::given(method("GET"))
            .and(path("/fail"))
            .respond_with(ResponseTemplate::new(502).set_body_string("upstream-err"))
            .mount(&failing_up)
            .await;

        let tmp = tempfile::tempdir().unwrap();
        let signer = PolicyFixtureSigner::new();
        let trust_file = signer.write_trust(tmp.path());

        let policies_dir = tmp.path().join("policies");
        let roles_dir = tmp.path().join("roles");
        let floor_dir = tmp.path().join("floors");
        let contracts_dir = tmp.path().join("contracts");
        let opa_dir = tmp.path().join("opa");
        for d in [&policies_dir, &roles_dir, &contracts_dir, &opa_dir] {
            std::fs::create_dir_all(d).unwrap();
        }

        // Tenant allows all 3 tools; role omits `payments_hidden` so tools/list hides it and
        // direct / sub-call invocation is refused with 0 requests to `denied_up`!
        std::fs::write(
            policies_dir.join("acme.jws"),
            signer.sign_tool_policy(
                "acme",
                &["payments_list", "payments_fail", "payments_hidden"],
            ),
        )
        .unwrap();
        std::fs::write(
            roles_dir.join("acme.roles.jws"),
            signer.sign_role_policy(
                "acme",
                1,
                json!({
                    "reader": {
                        "allowed_tools": ["payments_list", "payments_fail"],
                        "argument_constraints": {
                            "payments_list": {
                                "currency": { "type": "allowed_values", "values": ["EUR"] },
                                "account": { "type": "prefix", "prefix": "acct-" },
                                "limit": { "type": "max_number", "max": 50.0 }
                            }
                        }
                    }
                }),
            ),
        )
        .unwrap();
        let opa_file = opa_dir.join("policy.rego");
        std::fs::write(
            &opa_file,
            r#"package stoa.authz
import future.keywords.if
default allow := false
allow if {
    input.tenant_id == "acme"
    input.resource_tenant_id == "acme"
    input.action == "Read"
}
"#,
        )
        .unwrap();
        std::fs::write(
            contracts_dir.join("payments.uac.json"),
            serde_json::to_string(&json!({
                "name": "payments",
                "version": "1.0.0",
                "tenant_id": "acme",
                "display_name": "Payments J3",
                "description": "Jalon 3 fixture",
                "classification": "H",
                "endpoints": [
                    {
                        "path": "/payments",
                        "methods": ["GET"],
                        "backend_url": format!("{}/payments", primary_up.uri()),
                        "operation_id": "list_payments",
                        "llm": {
                            "summary": "List payments",
                            "intent": "Read payments",
                            "tool_name": "payments_list",
                            "side_effects": "read",
                            "safe_for_agents": true,
                            "requires_human_approval": false,
                            "examples": []
                        }
                    },
                    {
                        "path": "/fail",
                        "methods": ["GET"],
                        "backend_url": format!("{}/fail", failing_up.uri()),
                        "operation_id": "failing_tool",
                        "llm": {
                            "summary": "Failing tool",
                            "intent": "Trigger fallback",
                            "tool_name": "payments_fail",
                            "side_effects": "read",
                            "safe_for_agents": true,
                            "requires_human_approval": false,
                            "examples": []
                        }
                    },
                    {
                        "path": "/forbidden",
                        "methods": ["GET"],
                        "backend_url": format!("{}/forbidden", denied_up.uri()),
                        "operation_id": "hidden_tool",
                        "llm": {
                            "summary": "Hidden tool",
                            "intent": "Forbidden by role",
                            "tool_name": "payments_hidden",
                            "side_effects": "read",
                            "safe_for_agents": true,
                            "requires_human_approval": false,
                            "examples": []
                        }
                    }
                ],
                "required_policies": [],
                "status": "published"
            }))
            .unwrap(),
        )
        .unwrap();

        let creds_file = tmp.path().join("credentials.json");
        std::fs::write(
            &creds_file,
            serde_json::to_string(&json!([{
                "route_id": "mcp-tool:acme:payments_list",
                "auth_type": "api_key",
                "header_name": "X-API-Key",
                "header_value": "backend-key-j3",
                "allowed_origin": primary_up.uri(),
                "shared_with_tenants": false
            }]))
            .unwrap(),
        )
        .unwrap();

        let base_url = "http://stoa-gateway:8080";
        let config = Config {
            auto_register: false,
            admin_routes_disabled: true,
            policy_enabled: true,
            policy_path: Some(opa_file.to_string_lossy().to_string()),
            policy_boot_tenants: vec!["acme".to_string()],
            policy_trust_jwks_file: Some(trust_file),
            policy_local_artifacts_dir: Some(policies_dir.to_string_lossy().to_string()),
            policy_expected_issuer: "stoa-poc-policy".to_string(),
            policy_audience: "stoa-gateway".to_string(),
            poc_agents_enabled: true,
            poc_bootstrap_secret: Some("boot-secret-j3".to_string()),
            poc_uac_contracts_dir: Some(contracts_dir.to_string_lossy().to_string()),
            poc_credentials_file: Some(creds_file.to_string_lossy().to_string()),
            poc_public_base_url: Some(base_url.to_string()),
            poc_role_artifacts_dir: Some(roles_dir.to_string_lossy().to_string()),
            poc_role_floor_dir: Some(floor_dir.to_string_lossy().to_string()),
            poc_outbound_allowed_origins: vec![primary_up.uri(), failing_up.uri(), denied_up.uri()],
            poc_chain_budget: 4,
            poc_caller_budget: 6,
            ..Config::default()
        };

        let state = AppState::new(config);
        load_poc_fixtures(&state).await.unwrap();
        state
            .tool_permissions
            .as_ref()
            .unwrap()
            .load_policy("acme")
            .await
            .unwrap();
        let app = build_router(state.clone());

        let dpop_a = TestDpop::new();
        let dpop_b = TestDpop::new();
        let child_dpop = TestDpop::new();
        let boot_htu = format!("{base_url}/mcp/poc/bootstrap");
        let mcp_htu = format!("{base_url}/mcp/poc");
        let del_htu = format!("{base_url}/mcp/poc/delegate");
        let rev_htu = format!("{base_url}/mcp/poc/revoke");

        // Mint chain A and chain B for the SAME stable caller `agent-parent`.
        let mint_parent = |dpop: &TestDpop, jti: &str| {
            let app = app.clone();
            let proof = dpop.proof("POST", &boot_htu, jti, None);
            async move {
                let resp = app
                    .oneshot(
                        Request::builder()
                            .method("POST")
                            .uri("/mcp/poc/bootstrap")
                            .header("content-type", "application/json")
                            .header("X-Stoa-Poc-Bootstrap-Secret", "boot-secret-j3")
                            .header("DPoP", proof)
                            .body(Body::from(
                                json!({"sub":"agent-parent","tenant_id":"acme","role":"reader"})
                                    .to_string(),
                            ))
                            .unwrap(),
                    )
                    .await
                    .unwrap();
                assert_eq!(resp.status(), StatusCode::OK);
                serde_json::from_slice::<Value>(
                    &axum::body::to_bytes(resp.into_body(), 16 * 1024)
                        .await
                        .unwrap(),
                )
                .unwrap()
            }
        };

        let chain_a = mint_parent(&dpop_a, "ba1").await;
        let tok_a = chain_a["access_token"].as_str().unwrap().to_string();
        let chain_a_id = chain_a["chain_id"].as_str().unwrap().to_string();

        let chain_b = mint_parent(&dpop_b, "bb1").await;
        let tok_b = chain_b["access_token"].as_str().unwrap().to_string();

        // 1. tools/list filters out `payments_hidden`; direct call is also denied (0 requests to denied_up).
        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/mcp/poc")
                    .header("content-type", "application/json")
                    .header("Authorization", format!("DPoP {tok_a}"))
                    .header("DPoP", dpop_a.proof("POST", &mcp_htu, "tl1", Some(&tok_a)))
                    .body(Body::from(
                        json!({"jsonrpc":"2.0","id":1,"method":"tools/list"}).to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        let list_rpc: Value = serde_json::from_slice(
            &axum::body::to_bytes(resp.into_body(), 16 * 1024)
                .await
                .unwrap(),
        )
        .unwrap();
        let names: Vec<&str> = list_rpc["result"]["tools"]
            .as_array()
            .unwrap()
            .iter()
            .filter_map(|t| t["name"].as_str())
            .collect();
        assert!(names.contains(&"payments_list"));
        assert!(!names.contains(&"payments_hidden"));

        // 2. Sequential sub-calls: step 1 succeeds (budget 1/4), step 2 (`payments_hidden`) denied
        //    with ZERO requests to `denied_up` and NO budget charged for denied step!
        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/mcp/poc")
                    .header("content-type", "application/json")
                    .header("Authorization", format!("DPoP {tok_a}"))
                    .header("DPoP", dpop_a.proof("POST", &mcp_htu, "sc1", Some(&tok_a)))
                    .body(Body::from(
                        json!({
                            "jsonrpc": "2.0",
                            "id": 2,
                            "method": "poc/subcalls",
                            "params": {
                                "steps": [
                                    {
                                        "name": "payments_list",
                                        "arguments": {"currency":"EUR","account":"acct-1","limit":10}
                                    },
                                    {
                                        "name": "payments_hidden",
                                        "arguments": {}
                                    }
                                ]
                            }
                        })
                        .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        let sc_rpc: Value = serde_json::from_slice(
            &axum::body::to_bytes(resp.into_body(), 16 * 1024)
                .await
                .unwrap(),
        )
        .unwrap();
        assert!(sc_rpc.get("error").is_some());
        assert_eq!(denied_up.received_requests().await.unwrap().len(), 0);
        assert_eq!(state.poc_admission.chain_used(&chain_a_id), 1);

        // 3. Fallback step: `payments_fail` fails (502 -> budget 2/4), triggers fallback `payments_list`
        //    with invalid constraint args (limit 99 > 50) -> denied BEFORE hitting primary_up!
        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/mcp/poc")
                    .header("content-type", "application/json")
                    .header("Authorization", format!("DPoP {tok_a}"))
                    .header("DPoP", dpop_a.proof("POST", &mcp_htu, "fb1", Some(&tok_a)))
                    .body(Body::from(
                        json!({
                            "jsonrpc": "2.0",
                            "id": 3,
                            "method": "poc/subcalls",
                            "params": {
                                "steps": [{
                                    "name": "payments_fail",
                                    "arguments": {},
                                    "fallback": {
                                        "name": "payments_list",
                                        "arguments": {"currency":"EUR","account":"acct-1","limit":99}
                                    }
                                }]
                            }
                        })
                        .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        let fb_rpc: Value = serde_json::from_slice(
            &axum::body::to_bytes(resp.into_body(), 16 * 1024)
                .await
                .unwrap(),
        )
        .unwrap();
        assert!(fb_rpc.get("error").is_some());
        // primary_up still has ONLY 1 call (from step 1 of sc1), proving fallback constraint ran!
        assert_eq!(primary_up.received_requests().await.unwrap().len(), 1);
        assert_eq!(state.poc_admission.chain_used(&chain_a_id), 2);

        // 4. Delegate a child on chain A, then revoke chain A -> BOTH parent and child on chain A
        //    are immediately rejected, while chain B of the same caller retains caller_used=2!
        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/mcp/poc/delegate")
                    .header("content-type", "application/json")
                    .header("Authorization", format!("DPoP {tok_a}"))
                    .header("DPoP", dpop_a.proof("POST", &del_htu, "da1", Some(&tok_a)))
                    .body(Body::from(
                        json!({
                            "sub": "agent-child",
                            "target_tool": "payments_list",
                            "child_dpop_jwk": {
                                "kty": child_dpop.jwk.kty,
                                "crv": child_dpop.jwk.crv,
                                "x": child_dpop.jwk.x,
                                "y": child_dpop.jwk.y
                            },
                            "allowed_tools": ["payments_list"],
                            "ttl_secs": 120
                        })
                        .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let child_tok = serde_json::from_slice::<Value>(
            &axum::body::to_bytes(resp.into_body(), 16 * 1024)
                .await
                .unwrap(),
        )
        .unwrap()["access_token"]
            .as_str()
            .unwrap()
            .to_string();

        // Revoke chain A via DPoP-authenticated POST /mcp/poc/revoke
        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/mcp/poc/revoke")
                    .header("content-type", "application/json")
                    .header("Authorization", format!("DPoP {tok_a}"))
                    .header("DPoP", dpop_a.proof("POST", &rev_htu, "rv1", Some(&tok_a)))
                    .body(Body::from(json!({"chain_id": chain_a_id}).to_string()))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);

        // Child on revoked chain A is denied with "Chain revoked" and 0 upstream calls.
        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/mcp/poc")
                    .header("content-type", "application/json")
                    .header("Authorization", format!("DPoP {child_tok}"))
                    .header(
                        "DPoP",
                        child_dpop.proof("POST", &mcp_htu, "ch-rev", Some(&child_tok)),
                    )
                    .body(Body::from(
                        json!({
                            "jsonrpc": "2.0",
                            "id": 4,
                            "method": "tools/call",
                            "params": {
                                "name": "payments_list",
                                "arguments": {"currency":"EUR","account":"acct-1","limit":10}
                            }
                        })
                        .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        let rev_rpc: Value = serde_json::from_slice(
            &axum::body::to_bytes(resp.into_body(), 16 * 1024)
                .await
                .unwrap(),
        )
        .unwrap();
        assert_eq!(rev_rpc["error"]["message"], "Chain revoked");

        // Chain B (same caller `agent-parent`, caller_used already 2 out of 6):
        // 4 calls succeed (caller_used -> 6 == caller_budget AND chain_b_used == 4 == chain_budget),
        // 5th call fails with budget exceeded!
        for i in 0..4 {
            let resp = app
                .clone()
                .oneshot(
                    Request::builder()
                        .method("POST")
                        .uri("/mcp/poc")
                        .header("content-type", "application/json")
                        .header("Authorization", format!("DPoP {tok_b}"))
                        .header(
                            "DPoP",
                            dpop_b.proof("POST", &mcp_htu, &format!("cb-{i}"), Some(&tok_b)),
                        )
                        .body(Body::from(
                            json!({
                                "jsonrpc": "2.0",
                                "id": 10 + i,
                                "method": "tools/call",
                                "params": {
                                    "name": "payments_list",
                                    "arguments": {"currency":"EUR","account":"acct-1","limit":10}
                                }
                            })
                            .to_string(),
                        ))
                        .unwrap(),
                )
                .await
                .unwrap();
            let rpc: Value = serde_json::from_slice(
                &axum::body::to_bytes(resp.into_body(), 16 * 1024)
                    .await
                    .unwrap(),
            )
            .unwrap();
            assert!(rpc.get("error").is_none(), "chain B call {i} failed: {rpc}");
        }
        assert_eq!(
            state
                .poc_admission
                .caller_used(&caller_identity_key("acme", "agent-parent")),
            6
        );

        // 5th call on chain B exceeds budget -> denied, zero extra upstream request!
        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/mcp/poc")
                    .header("content-type", "application/json")
                    .header("Authorization", format!("DPoP {tok_b}"))
                    .header(
                        "DPoP",
                        dpop_b.proof("POST", &mcp_htu, "cb-over", Some(&tok_b)),
                    )
                    .body(Body::from(
                        json!({
                            "jsonrpc": "2.0",
                            "id": 99,
                            "method": "tools/call",
                            "params": {
                                "name": "payments_list",
                                "arguments": {"currency":"EUR","account":"acct-1","limit":10}
                            }
                        })
                        .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        let over_rpc: Value = serde_json::from_slice(
            &axum::body::to_bytes(resp.into_body(), 16 * 1024)
                .await
                .unwrap(),
        )
        .unwrap();
        assert!(over_rpc["error"]["message"]
            .as_str()
            .unwrap()
            .contains("budget exceeded"));
        assert_eq!(primary_up.received_requests().await.unwrap().len(), 5);
    }

    #[tokio::test]
    async fn ch5_max_number_precision_direct_fallback_delegation_and_mapping() {
        let primary_up = MockServer::start().await;
        let failing_up = MockServer::start().await;

        Mock::given(method("GET"))
            .and(path("/payments"))
            .and(header("X-API-Key", "backend-key-ch5"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({"ok": true})))
            .mount(&primary_up)
            .await;
        Mock::given(method("GET"))
            .and(path("/fail"))
            .respond_with(ResponseTemplate::new(502).set_body_string("upstream-err"))
            .mount(&failing_up)
            .await;

        let tmp = tempfile::tempdir().unwrap();
        let signer = PolicyFixtureSigner::new();
        let trust_file = signer.write_trust(tmp.path());

        let policies_dir = tmp.path().join("policies");
        let roles_dir = tmp.path().join("roles");
        let floor_dir = tmp.path().join("floors");
        let contracts_dir = tmp.path().join("contracts");
        let opa_dir = tmp.path().join("opa");
        for d in [&policies_dir, &roles_dir, &contracts_dir, &opa_dir] {
            std::fs::create_dir_all(d).unwrap();
        }

        std::fs::write(
            policies_dir.join("acme.jws"),
            signer.sign_tool_policy("acme", &["payments_list", "payments_fail"]),
        )
        .unwrap();
        std::fs::write(
            roles_dir.join("acme.roles.jws"),
            signer.sign_role_policy(
                "acme",
                1,
                json!({
                    "reader": {
                        "allowed_tools": ["payments_list", "payments_fail"],
                        "argument_constraints": {
                            "payments_list": {
                                "currency": { "type": "allowed_values", "values": ["EUR"] },
                                "account": { "type": "prefix", "prefix": "acct-" },
                                "amount": { "type": "max_number", "max": 50.01 }
                            }
                        }
                    }
                }),
            ),
        )
        .unwrap();

        let opa_file = opa_dir.join("policy.rego");
        std::fs::write(
            &opa_file,
            r#"package stoa.authz
import future.keywords.if
default allow := false
allow if {
    input.tenant_id == "acme"
    input.resource_tenant_id == "acme"
    input.action == "Read"
}
"#,
        )
        .unwrap();

        std::fs::write(
            contracts_dir.join("payments.uac.json"),
            serde_json::to_string(&json!({
                "name": "payments",
                "version": "1.0.0",
                "tenant_id": "acme",
                "display_name": "Payments CH5",
                "description": "CH5 precision fixture",
                "classification": "H",
                "endpoints": [
                    {
                        "path": "/payments",
                        "methods": ["GET"],
                        "backend_url": format!("{}/payments", primary_up.uri()),
                        "operation_id": "list_payments",
                        "llm": {
                            "summary": "List payments",
                            "intent": "Read payments",
                            "tool_name": "payments_list",
                            "side_effects": "read",
                            "safe_for_agents": true,
                            "requires_human_approval": false,
                            "examples": []
                        }
                    },
                    {
                        "path": "/fail",
                        "methods": ["GET"],
                        "backend_url": format!("{}/fail", failing_up.uri()),
                        "operation_id": "failing_tool",
                        "llm": {
                            "summary": "Failing tool",
                            "intent": "Trigger fallback",
                            "tool_name": "payments_fail",
                            "side_effects": "read",
                            "safe_for_agents": true,
                            "requires_human_approval": false,
                            "examples": []
                        }
                    }
                ],
                "required_policies": [],
                "status": "published"
            }))
            .unwrap(),
        )
        .unwrap();

        let creds_file = tmp.path().join("credentials.json");
        std::fs::write(
            &creds_file,
            serde_json::to_string(&json!([{
                "route_id": "mcp-tool:acme:payments_list",
                "auth_type": "api_key",
                "header_name": "X-API-Key",
                "header_value": "backend-key-ch5",
                "allowed_origin": primary_up.uri(),
                "shared_with_tenants": false
            }]))
            .unwrap(),
        )
        .unwrap();

        let base_url = "http://stoa-gateway:8080";
        let config = Config {
            auto_register: false,
            admin_routes_disabled: true,
            policy_enabled: true,
            policy_path: Some(opa_file.to_string_lossy().to_string()),
            policy_boot_tenants: vec!["acme".to_string()],
            policy_trust_jwks_file: Some(trust_file),
            policy_local_artifacts_dir: Some(policies_dir.to_string_lossy().to_string()),
            policy_expected_issuer: "stoa-poc-policy".to_string(),
            policy_audience: "stoa-gateway".to_string(),
            poc_agents_enabled: true,
            poc_bootstrap_secret: Some("boot-secret-ch5".to_string()),
            poc_uac_contracts_dir: Some(contracts_dir.to_string_lossy().to_string()),
            poc_credentials_file: Some(creds_file.to_string_lossy().to_string()),
            poc_public_base_url: Some(base_url.to_string()),
            poc_role_artifacts_dir: Some(roles_dir.to_string_lossy().to_string()),
            poc_role_floor_dir: Some(floor_dir.to_string_lossy().to_string()),
            poc_outbound_allowed_origins: vec![primary_up.uri(), failing_up.uri()],
            poc_chain_budget: 10,
            poc_caller_budget: 10,
            ..Config::default()
        };

        let state = AppState::new(config);
        load_poc_fixtures(&state).await.unwrap();
        state
            .tool_permissions
            .as_ref()
            .unwrap()
            .load_policy("acme")
            .await
            .unwrap();
        let app = build_router(state.clone());

        let parent_dpop = TestDpop::new();
        let child_dpop = TestDpop::new();
        let boot_htu = format!("{base_url}/mcp/poc/bootstrap");
        let mcp_htu = format!("{base_url}/mcp/poc");
        let del_htu = format!("{base_url}/mcp/poc/delegate");

        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/mcp/poc/bootstrap")
                    .header("content-type", "application/json")
                    .header("X-Stoa-Poc-Bootstrap-Secret", "boot-secret-ch5")
                    .header("DPoP", parent_dpop.proof("POST", &boot_htu, "ch5-b1", None))
                    .body(Body::from(
                        json!({"sub":"agent-parent","tenant_id":"acme","role":"reader"})
                            .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let boot_json: Value = serde_json::from_slice(
            &axum::body::to_bytes(resp.into_body(), 16 * 1024)
                .await
                .unwrap(),
        )
        .unwrap();
        let parent_tok = boot_json["access_token"].as_str().unwrap().to_string();
        let chain_id = boot_json["chain_id"].as_str().unwrap().to_string();

        let send_raw_mcp = |raw_body: &str, jti: &str| {
            let app = app.clone();
            let proof = parent_dpop.proof("POST", &mcp_htu, jti, Some(&parent_tok));
            let auth_header = format!("DPoP {parent_tok}");
            let body = raw_body.to_string();
            async move {
                let resp = app
                    .oneshot(
                        Request::builder()
                            .method("POST")
                            .uri("/mcp/poc")
                            .header("content-type", "application/json")
                            .header("Authorization", auth_header)
                            .header("DPoP", proof)
                            .body(Body::from(body))
                            .unwrap(),
                    )
                    .await
                    .unwrap();
                assert_eq!(resp.status(), StatusCode::OK);
                serde_json::from_slice::<Value>(
                    &axum::body::to_bytes(resp.into_body(), 16 * 1024)
                        .await
                        .unwrap(),
                )
                .unwrap()
            }
        };

        // 1. Conforming direct call using equivalent scientific notation (`5001e-2`) and an
        //    unbounded numeric field (`9007199254740993`) passes normally.
        let ok_rpc = send_raw_mcp(
            r#"{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"payments_list","arguments":{"currency":"EUR","account":"acct-1","amount":5001e-2,"unbounded_ref":9007199254740993}}}"#,
            "ch5-ok-1",
        )
        .await;
        assert!(ok_rpc.get("error").is_none(), "expected success: {ok_rpc}");
        assert_eq!(primary_up.received_requests().await.unwrap().len(), 1);
        assert_eq!(state.poc_admission.chain_used(&chain_id), 1);

        // 2. Direct calls with imprecise or positive-underflow bounded arguments are refused
        //    BEFORE budget debit and BEFORE reaching upstream.
        for (jti, bad_amount) in [
            ("ch5-bad-1", "50.0100000000000000001"),
            ("ch5-bad-2", "1e-400"),
        ] {
            let body = format!(
                r#"{{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{{"name":"payments_list","arguments":{{"currency":"EUR","account":"acct-1","amount":{bad_amount}}}}}}}"#
            );
            let rpc = send_raw_mcp(&body, jti).await;
            assert_eq!(rpc["error"]["code"], -32003);
            assert_eq!(rpc["error"]["message"], "Tool call rejected by role policy");
        }
        assert_eq!(primary_up.received_requests().await.unwrap().len(), 1);
        assert_eq!(state.poc_admission.chain_used(&chain_id), 1);

        // 3. Fallback step with an imprecise raw number is refused BEFORE hitting primary_up.
        let fb_rpc = send_raw_mcp(
            r#"{"jsonrpc":"2.0","id":3,"method":"poc/subcalls","params":{"steps":[{"name":"payments_fail","arguments":{},"fallback":{"name":"payments_list","arguments":{"currency":"EUR","account":"acct-1","amount":50.0100000000000000001}}}]}}"#,
            "ch5-fb-1",
        )
        .await;
        assert_eq!(fb_rpc["error"]["code"], -32003);
        assert_eq!(
            fb_rpc["error"]["message"],
            "Tool call rejected by role policy"
        );
        assert_eq!(primary_up.received_requests().await.unwrap().len(), 1);
        assert_eq!(state.poc_admission.chain_used(&chain_id), 2);

        // 4. `map_prev_into_arg` replaces a numeric field with text and must NOT reuse the
        //    replaced numeric lexeme to satisfy `max_number`.
        let map_rpc = send_raw_mcp(
            r#"{"jsonrpc":"2.0","id":4,"method":"poc/subcalls","params":{"steps":[{"name":"payments_list","arguments":{"currency":"EUR","account":"acct-1","amount":10}},{"name":"payments_list","arguments":{"currency":"EUR","account":"acct-1","amount":10},"map_prev_into_arg":"amount"}]}}"#,
            "ch5-map-1",
        )
        .await;
        assert_eq!(map_rpc["error"]["code"], -32003);
        assert_eq!(
            map_rpc["error"]["message"],
            "Tool call rejected by role policy"
        );
        assert_eq!(primary_up.received_requests().await.unwrap().len(), 2);
        assert_eq!(state.poc_admission.chain_used(&chain_id), 3);

        // 5. Delegation route rejects an imprecise max_number bound (preventing silent rounding
        //    widening) while accepting an exact equivalent bound (`5001e-2`).
        let child_jwk_json = json!({
            "kty": child_dpop.jwk.kty,
            "crv": child_dpop.jwk.crv,
            "x": child_dpop.jwk.x,
            "y": child_dpop.jwk.y
        })
        .to_string();
        let bad_delegate_body = format!(
            r#"{{"sub":"agent-child","target_tool":"payments_list","child_dpop_jwk":{child_jwk_json},"allowed_tools":["payments_list"],"arg_constraints":{{"amount":{{"type":"max_number","max":50.0100000000000000001}}}},"ttl_secs":120}}"#
        );
        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/mcp/poc/delegate")
                    .header("content-type", "application/json")
                    .header("Authorization", format!("DPoP {parent_tok}"))
                    .header(
                        "DPoP",
                        parent_dpop.proof("POST", &del_htu, "ch5-del-bad", Some(&parent_tok)),
                    )
                    .body(Body::from(bad_delegate_body))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::UNPROCESSABLE_ENTITY);

        let ok_delegate_body = format!(
            r#"{{"sub":"agent-child","target_tool":"payments_list","child_dpop_jwk":{child_jwk_json},"allowed_tools":["payments_list"],"arg_constraints":{{"amount":{{"type":"max_number","max":5001e-2}}}},"ttl_secs":120}}"#
        );
        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/mcp/poc/delegate")
                    .header("content-type", "application/json")
                    .header("Authorization", format!("DPoP {parent_tok}"))
                    .header(
                        "DPoP",
                        parent_dpop.proof("POST", &del_htu, "ch5-del-ok", Some(&parent_tok)),
                    )
                    .body(Body::from(ok_delegate_body))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);

        // Direct strict deserialization checks for delegation request and delegated JWT claims.
        let imprecise_req = format!(
            r#"{{"sub":"agent-child","target_tool":"payments_list","child_dpop_jwk":{child_jwk_json},"allowed_tools":["payments_list"],"arg_constraints":{{"amount":{{"type":"max_number","max":9007199254740993}}}}}}"#
        );
        assert!(serde_json::from_str::<PocDelegateRequest>(&imprecise_req).is_err());

        let imprecise_claims = r#"{
            "iss":"stoa-poc-delegation",
            "sub":"agent-child",
            "aud":"mcp-tool:acme:payments_list",
            "tenant_id":"acme",
            "role":"reader",
            "chain_id":"chain-1",
            "jti":"jti-1",
            "depth":1,
            "parent_jti":"jti-0",
            "act":{"sub":"agent-parent"},
            "policy_version":1,
            "allowed_tools":["payments_list"],
            "arg_constraints":{"amount":{"type":"max_number","max":9007199254740993}},
            "iat":1700000000,
            "exp":1700000300,
            "cnf":{"jkt":"thumbprint"}
        }"#;
        assert!(serde_json::from_str::<LocalAgentClaims>(imprecise_claims).is_err());
    }

    #[tokio::test]
    async fn bootstrap_refuses_empty_and_whitespace_tenant_id() {
        let tmp = tempfile::tempdir().unwrap();
        let signer = PolicyFixtureSigner::new();
        let trust_file = signer.write_trust(tmp.path());

        let policies_dir = tmp.path().join("policies");
        let roles_dir = tmp.path().join("roles");
        let floor_dir = tmp.path().join("floors");
        std::fs::create_dir_all(&policies_dir).unwrap();
        std::fs::create_dir_all(&roles_dir).unwrap();

        std::fs::write(
            policies_dir.join("acme.jws"),
            signer.sign_tool_policy("acme", &["payments_list"]),
        )
        .unwrap();
        std::fs::write(
            roles_dir.join("acme.roles.jws"),
            signer.sign_role_policy(
                "acme",
                1,
                json!({
                    "reader": { "allowed_tools": ["payments_list"] }
                }),
            ),
        )
        .unwrap();

        let base_url = "http://stoa-gateway:8080";
        let config = Config {
            auto_register: false,
            admin_routes_disabled: true,
            policy_enabled: false,
            policy_boot_tenants: vec!["acme".to_string()],
            policy_trust_jwks_file: Some(trust_file),
            policy_local_artifacts_dir: Some(policies_dir.to_string_lossy().to_string()),
            policy_expected_issuer: "stoa-poc-policy".to_string(),
            policy_audience: "stoa-gateway".to_string(),
            poc_agents_enabled: true,
            poc_bootstrap_secret: Some("boot-r7".to_string()),
            poc_public_base_url: Some(base_url.to_string()),
            poc_role_artifacts_dir: Some(roles_dir.to_string_lossy().to_string()),
            poc_role_floor_dir: Some(floor_dir.to_string_lossy().to_string()),
            ..Config::default()
        };

        let state = AppState::new(config);
        load_poc_fixtures(&state).await.unwrap();
        let app = build_router(state);

        let dpop = TestDpop::new();
        let boot_htu = format!("{base_url}/mcp/poc/bootstrap");

        for (label, bad_tenant) in [("empty", ""), ("spaces", "   ")] {
            let resp = app
                .clone()
                .oneshot(
                    Request::builder()
                        .method("POST")
                        .uri("/mcp/poc/bootstrap")
                        .header("content-type", "application/json")
                        .header("X-Stoa-Poc-Bootstrap-Secret", "boot-r7")
                        .header(
                            "DPoP",
                            dpop.proof("POST", &boot_htu, &format!("boot-{label}"), None),
                        )
                        .body(Body::from(
                            json!({
                                "sub": "agent-parent",
                                "tenant_id": bad_tenant,
                                "role": "reader"
                            })
                            .to_string(),
                        ))
                        .unwrap(),
                )
                .await
                .unwrap();
            // `current_role_snapshot` rejects empty/blank tenant IDs before `issue_parent_token`
            // runs, returning 403 `role_not_permitted`. The `issue_parent_token` tenant rule
            // itself is covered directly by the unit test in `local_agent_token.rs`.
            assert_eq!(
                resp.status(),
                StatusCode::FORBIDDEN,
                "expected 403 for {label} tenant_id, got {}",
                resp.status()
            );
            let body = axum::body::to_bytes(resp.into_body(), 16 * 1024)
                .await
                .unwrap();
            let body_json: Value = serde_json::from_slice(&body).unwrap();
            assert_eq!(
                body_json["error"], "role_not_permitted",
                "expected role_not_permitted for {label} tenant_id, got {body_json}"
            );
            assert!(
                body_json.get("access_token").is_none(),
                "unexpected access_token for {label} tenant_id"
            );
        }

        // Control check: a valid tenant_id on the same router succeeds.
        let resp = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/mcp/poc/bootstrap")
                    .header("content-type", "application/json")
                    .header("X-Stoa-Poc-Bootstrap-Secret", "boot-r7")
                    .header("DPoP", dpop.proof("POST", &boot_htu, "boot-valid", None))
                    .body(Body::from(
                        json!({
                            "sub": "agent-parent",
                            "tenant_id": "acme",
                            "role": "reader"
                        })
                        .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let body = axum::body::to_bytes(resp.into_body(), 16 * 1024)
            .await
            .unwrap();
        let ok_json: Value = serde_json::from_slice(&body).unwrap();
        assert!(ok_json["access_token"].as_str().is_some());
        assert_eq!(ok_json["tenant_id"], "acme");
    }

    #[tokio::test]
    async fn revocation_table_saturation_fails_closed_at_router_level() {
        let upstream = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/payments"))
            .and(header("X-API-Key", "ky-sat"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({"ok": true})))
            .mount(&upstream)
            .await;

        let tmp = tempfile::tempdir().unwrap();
        let signer = PolicyFixtureSigner::new();
        let trust_file = signer.write_trust(tmp.path());

        let policies_dir = tmp.path().join("policies");
        let roles_dir = tmp.path().join("roles");
        let floor_dir = tmp.path().join("floors");
        let contracts_dir = tmp.path().join("contracts");
        for d in [&policies_dir, &roles_dir, &contracts_dir] {
            std::fs::create_dir_all(d).unwrap();
        }

        std::fs::write(
            policies_dir.join("acme.jws"),
            signer.sign_tool_policy("acme", &["payments_list"]),
        )
        .unwrap();
        std::fs::write(
            roles_dir.join("acme.roles.jws"),
            signer.sign_role_policy(
                "acme",
                1,
                json!({
                    "reader": { "allowed_tools": ["payments_list"] }
                }),
            ),
        )
        .unwrap();
        std::fs::write(
            contracts_dir.join("payments.uac.json"),
            serde_json::to_string(&json!({
                "name": "payments",
                "version": "1.0.0",
                "tenant_id": "acme",
                "display_name": "Payments Sat",
                "description": "Revocation saturation fixture",
                "classification": "H",
                "endpoints": [{
                    "path": "/payments",
                    "methods": ["GET"],
                    "backend_url": format!("{}/payments", upstream.uri()),
                    "operation_id": "list_payments",
                    "llm": {
                        "summary": "List payments",
                        "intent": "Read payments",
                        "tool_name": "payments_list",
                        "side_effects": "read",
                        "safe_for_agents": true,
                        "requires_human_approval": false,
                        "examples": []
                    }
                }],
                "required_policies": [],
                "status": "published"
            }))
            .unwrap(),
        )
        .unwrap();

        let creds_file = tmp.path().join("credentials.json");
        std::fs::write(
            &creds_file,
            serde_json::to_string(&json!([{
                "route_id": "mcp-tool:acme:payments_list",
                "auth_type": "api_key",
                "header_name": "X-API-Key",
                "header_value": "ky-sat",
                "allowed_origin": upstream.uri(),
                "shared_with_tenants": false
            }]))
            .unwrap(),
        )
        .unwrap();

        let base_url = "http://stoa-gateway:8080";
        let config = Config {
            auto_register: false,
            admin_routes_disabled: true,
            policy_enabled: false,
            policy_boot_tenants: vec!["acme".to_string()],
            policy_trust_jwks_file: Some(trust_file),
            policy_local_artifacts_dir: Some(policies_dir.to_string_lossy().to_string()),
            policy_expected_issuer: "stoa-poc-policy".to_string(),
            policy_audience: "stoa-gateway".to_string(),
            poc_agents_enabled: true,
            poc_bootstrap_secret: Some("bt-sat".to_string()),
            poc_uac_contracts_dir: Some(contracts_dir.to_string_lossy().to_string()),
            poc_credentials_file: Some(creds_file.to_string_lossy().to_string()),
            poc_public_base_url: Some(base_url.to_string()),
            poc_role_artifacts_dir: Some(roles_dir.to_string_lossy().to_string()),
            poc_role_floor_dir: Some(floor_dir.to_string_lossy().to_string()),
            poc_outbound_allowed_origins: vec![upstream.uri()],
            poc_max_revoked_chains: 2,
            ..Config::default()
        };

        let state = AppState::new(config);
        load_poc_fixtures(&state).await.unwrap();
        state
            .tool_permissions
            .as_ref()
            .unwrap()
            .load_policy("acme")
            .await
            .unwrap();
        let app = build_router(state.clone());

        let boot_htu = format!("{base_url}/mcp/poc/bootstrap");
        let rev_htu = format!("{base_url}/mcp/poc/revoke");
        let del_htu = format!("{base_url}/mcp/poc/delegate");
        let mcp_htu = format!("{base_url}/mcp/poc");

        let mint_parent = |dpop: &TestDpop, sub: &str, jti: &str| {
            let app = app.clone();
            let proof = dpop.proof("POST", &boot_htu, jti, None);
            let payload = json!({
                "sub": sub,
                "tenant_id": "acme",
                "role": "reader"
            })
            .to_string();
            async move {
                let resp = app
                    .oneshot(
                        Request::builder()
                            .method("POST")
                            .uri("/mcp/poc/bootstrap")
                            .header("content-type", "application/json")
                            .header("X-Stoa-Poc-Bootstrap-Secret", "bt-sat")
                            .header("DPoP", proof)
                            .body(Body::from(payload))
                            .unwrap(),
                    )
                    .await
                    .unwrap();
                let status = resp.status();
                let body = axum::body::to_bytes(resp.into_body(), 16 * 1024)
                    .await
                    .unwrap();
                let json_body: Value = serde_json::from_slice(&body).unwrap();
                (status, json_body)
            }
        };

        let revoke_chain = |dpop: &TestDpop, tok: &str, chain_id: &str, jti: &str| {
            let app = app.clone();
            let auth_header = format!("DPoP {tok}");
            let proof = dpop.proof("POST", &rev_htu, jti, Some(tok));
            let payload = json!({ "chain_id": chain_id }).to_string();
            async move {
                let resp = app
                    .oneshot(
                        Request::builder()
                            .method("POST")
                            .uri("/mcp/poc/revoke")
                            .header("content-type", "application/json")
                            .header("Authorization", auth_header)
                            .header("DPoP", proof)
                            .body(Body::from(payload))
                            .unwrap(),
                    )
                    .await
                    .unwrap();
                let status = resp.status();
                let body = axum::body::to_bytes(resp.into_body(), 16 * 1024)
                    .await
                    .unwrap();
                let json_body: Value = serde_json::from_slice(&body).unwrap();
                (status, json_body)
            }
        };

        let call_payments = |dpop: &TestDpop, tok: &str, jti: &str, id: i64| {
            let app = app.clone();
            let auth_header = format!("DPoP {tok}");
            let proof = dpop.proof("POST", &mcp_htu, jti, Some(tok));
            let payload = json!({
                "jsonrpc": "2.0",
                "id": id,
                "method": "tools/call",
                "params": { "name": "payments_list", "arguments": {} }
            })
            .to_string();
            async move {
                let resp = app
                    .oneshot(
                        Request::builder()
                            .method("POST")
                            .uri("/mcp/poc")
                            .header("content-type", "application/json")
                            .header("Authorization", auth_header)
                            .header("DPoP", proof)
                            .body(Body::from(payload))
                            .unwrap(),
                    )
                    .await
                    .unwrap();
                let status = resp.status();
                let body = axum::body::to_bytes(resp.into_body(), 16 * 1024)
                    .await
                    .unwrap();
                let json_body: Value = serde_json::from_slice(&body).unwrap();
                (status, json_body)
            }
        };

        let dpop1 = TestDpop::new();
        let dpop2 = TestDpop::new();
        let dpop3 = TestDpop::new();
        let dpop4 = TestDpop::new();
        let child_dpop = TestDpop::new();

        let (s1, b1) = mint_parent(&dpop1, "agent-sat-1", "sat-b1").await;
        assert_eq!(s1, StatusCode::OK);
        let tok1 = b1["access_token"].as_str().unwrap().to_string();
        let cid1 = b1["chain_id"].as_str().unwrap().to_string();

        let (s2, b2) = mint_parent(&dpop2, "agent-sat-2", "sat-b2").await;
        assert_eq!(s2, StatusCode::OK);
        let tok2 = b2["access_token"].as_str().unwrap().to_string();
        let cid2 = b2["chain_id"].as_str().unwrap().to_string();

        let (s3, b3) = mint_parent(&dpop3, "agent-sat-3", "sat-b3").await;
        assert_eq!(s3, StatusCode::OK);
        let tok3 = b3["access_token"].as_str().unwrap().to_string();
        let cid3 = b3["chain_id"].as_str().unwrap().to_string();

        // Baseline: chain 3 works normally before the revocation table saturates.
        let (st, rpc) = call_payments(&dpop3, &tok3, "sat-c3-pre", 1).await;
        assert_eq!(st, StatusCode::OK);
        assert!(rpc.get("error").is_none(), "baseline call failed: {rpc}");
        assert_eq!(upstream.received_requests().await.unwrap().len(), 1);

        // Revoke chain 1 (1/2) and confirm it is immediately refused without hitting upstream.
        let (rs1, rb1) = revoke_chain(&dpop1, &tok1, &cid1, "sat-r1").await;
        assert_eq!(rs1, StatusCode::OK);
        assert_eq!(rb1["revoked"], json!(true));
        let (st, rpc) = call_payments(&dpop1, &tok1, "sat-c1-rev", 2).await;
        assert_eq!(st, StatusCode::OK);
        assert_eq!(rpc["error"]["code"], -32003);
        assert_eq!(rpc["error"]["message"], "Chain revoked");

        // Revoke chain 2 (2/2): revocation table is now at capacity.
        let (rs2, rb2) = revoke_chain(&dpop2, &tok2, &cid2, "sat-r2").await;
        assert_eq!(rs2, StatusCode::OK);
        assert_eq!(rb2["revoked"], json!(true));
        assert_eq!(state.poc_admission.revoked_count(), 2);

        // 3rd revoke fails closed with 503 and revocation_table_full.
        let (rs3, rb3) = revoke_chain(&dpop3, &tok3, &cid3, "sat-r3").await;
        assert_eq!(rs3, StatusCode::SERVICE_UNAVAILABLE);
        assert_eq!(rb3["error"], "revocation_table_full");

        // Delegation on the 3rd chain and a 4th bootstrap both fail closed via
        // admission_http_rejection with 503 and the saturation reason.
        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/mcp/poc/delegate")
                    .header("content-type", "application/json")
                    .header("Authorization", format!("DPoP {tok3}"))
                    .header(
                        "DPoP",
                        dpop3.proof("POST", &del_htu, "sat-del3", Some(&tok3)),
                    )
                    .body(Body::from(
                        json!({
                            "sub": "agent-sat-child",
                            "target_tool": "payments_list",
                            "child_dpop_jwk": {
                                "kty": child_dpop.jwk.kty,
                                "crv": child_dpop.jwk.crv,
                                "x": child_dpop.jwk.x,
                                "y": child_dpop.jwk.y
                            },
                            "allowed_tools": ["payments_list"],
                            "ttl_secs": 60
                        })
                        .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::SERVICE_UNAVAILABLE);
        let del_body = axum::body::to_bytes(resp.into_body(), 16 * 1024)
            .await
            .unwrap();
        let del_json: Value = serde_json::from_slice(&del_body).unwrap();
        assert_eq!(
            del_json["error"],
            "revocation table is saturated; failing closed"
        );

        let (s4, b4) = mint_parent(&dpop4, "agent-sat-4", "sat-b4").await;
        assert_eq!(s4, StatusCode::SERVICE_UNAVAILABLE);
        assert_eq!(b4["error"], "revocation table is saturated; failing closed");

        // Tool call on the non-revoked 3rd chain fails closed without reaching upstream.
        let (st, rpc) = call_payments(&dpop3, &tok3, "sat-c3-post", 3).await;
        assert_eq!(st, StatusCode::OK);
        assert_eq!(rpc["error"]["code"], -32005);
        assert_eq!(rpc["error"]["message"], "Admission unavailable");

        // Previously revoked chains stay refused without reaching upstream.
        let (st, rpc) = call_payments(&dpop1, &tok1, "sat-c1-post", 4).await;
        assert_eq!(st, StatusCode::OK);
        assert_eq!(rpc["error"]["code"], -32005);
        assert_eq!(rpc["error"]["message"], "Admission unavailable");

        let (st, rpc) = call_payments(&dpop2, &tok2, "sat-c2-post", 5).await;
        assert_eq!(st, StatusCode::OK);
        assert_eq!(rpc["error"]["code"], -32005);
        assert_eq!(rpc["error"]["message"], "Admission unavailable");

        // Only the pre-saturation baseline call reached upstream.
        assert_eq!(upstream.received_requests().await.unwrap().len(), 1);
    }

    #[tokio::test]
    async fn child_token_wrong_tool_and_generic_mcp_audience_are_refused() {
        let upstream = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/payments"))
            .and(header("X-API-Key", "ky-aud"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({"ok": "payments"})))
            .mount(&upstream)
            .await;
        Mock::given(method("GET"))
            .and(path("/other"))
            .and(header("X-API-Key", "ky-aud"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({"ok": "other"})))
            .expect(0)
            .mount(&upstream)
            .await;

        let tmp = tempfile::tempdir().unwrap();
        let signer = PolicyFixtureSigner::new();
        let trust_file = signer.write_trust(tmp.path());

        let policies_dir = tmp.path().join("policies");
        let roles_dir = tmp.path().join("roles");
        let floor_dir = tmp.path().join("floors");
        let contracts_dir = tmp.path().join("contracts");
        for d in [&policies_dir, &roles_dir, &contracts_dir] {
            std::fs::create_dir_all(d).unwrap();
        }

        std::fs::write(
            policies_dir.join("acme.jws"),
            signer.sign_tool_policy("acme", &["payments_list", "payments_other"]),
        )
        .unwrap();
        std::fs::write(
            roles_dir.join("acme.roles.jws"),
            signer.sign_role_policy(
                "acme",
                1,
                json!({
                    "reader": { "allowed_tools": ["payments_list", "payments_other"] }
                }),
            ),
        )
        .unwrap();
        std::fs::write(
            contracts_dir.join("payments.uac.json"),
            serde_json::to_string(&json!({
                "name": "payments",
                "version": "1.0.0",
                "tenant_id": "acme",
                "display_name": "Payments Audience",
                "description": "Child audience fixture",
                "classification": "H",
                "endpoints": [
                    {
                        "path": "/payments",
                        "methods": ["GET"],
                        "backend_url": format!("{}/payments", upstream.uri()),
                        "operation_id": "list_payments",
                        "llm": {
                            "summary": "List payments",
                            "intent": "Read payments",
                            "tool_name": "payments_list",
                            "side_effects": "read",
                            "safe_for_agents": true,
                            "requires_human_approval": false,
                            "examples": []
                        }
                    },
                    {
                        "path": "/other",
                        "methods": ["GET"],
                        "backend_url": format!("{}/other", upstream.uri()),
                        "operation_id": "other_payments",
                        "llm": {
                            "summary": "Other payments tool",
                            "intent": "Read other payments",
                            "tool_name": "payments_other",
                            "side_effects": "read",
                            "safe_for_agents": true,
                            "requires_human_approval": false,
                            "examples": []
                        }
                    }
                ],
                "required_policies": [],
                "status": "published"
            }))
            .unwrap(),
        )
        .unwrap();

        let creds_file = tmp.path().join("credentials.json");
        std::fs::write(
            &creds_file,
            serde_json::to_string(&json!([
                {
                    "route_id": "mcp-tool:acme:payments_list",
                    "auth_type": "api_key",
                    "header_name": "X-API-Key",
                    "header_value": "ky-aud",
                    "allowed_origin": upstream.uri(),
                    "shared_with_tenants": false
                },
                {
                    "route_id": "mcp-tool:acme:payments_other",
                    "auth_type": "api_key",
                    "header_name": "X-API-Key",
                    "header_value": "ky-aud",
                    "allowed_origin": upstream.uri(),
                    "shared_with_tenants": false
                }
            ]))
            .unwrap(),
        )
        .unwrap();

        let base_url = "http://stoa-gateway:8080";
        let config = Config {
            auto_register: false,
            admin_routes_disabled: true,
            policy_enabled: false,
            policy_boot_tenants: vec!["acme".to_string()],
            policy_trust_jwks_file: Some(trust_file),
            policy_local_artifacts_dir: Some(policies_dir.to_string_lossy().to_string()),
            policy_expected_issuer: "stoa-poc-policy".to_string(),
            policy_audience: "stoa-gateway".to_string(),
            poc_agents_enabled: true,
            poc_bootstrap_secret: Some("bt-aud".to_string()),
            poc_uac_contracts_dir: Some(contracts_dir.to_string_lossy().to_string()),
            poc_credentials_file: Some(creds_file.to_string_lossy().to_string()),
            poc_public_base_url: Some(base_url.to_string()),
            poc_role_artifacts_dir: Some(roles_dir.to_string_lossy().to_string()),
            poc_role_floor_dir: Some(floor_dir.to_string_lossy().to_string()),
            poc_outbound_allowed_origins: vec![upstream.uri()],
            ..Config::default()
        };

        let state = AppState::new(config);
        load_poc_fixtures(&state).await.unwrap();
        state
            .tool_permissions
            .as_ref()
            .unwrap()
            .load_policy("acme")
            .await
            .unwrap();
        let app = build_router(state.clone());

        let parent_dpop = TestDpop::new();
        let child_dpop = TestDpop::new();
        let boot_htu = format!("{base_url}/mcp/poc/bootstrap");
        let del_htu = format!("{base_url}/mcp/poc/delegate");
        let mcp_htu = format!("{base_url}/mcp/poc");

        // 1. Bootstrap parent and delegate a child scoped to `payments_list`.
        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/mcp/poc/bootstrap")
                    .header("content-type", "application/json")
                    .header("X-Stoa-Poc-Bootstrap-Secret", "bt-aud")
                    .header("DPoP", parent_dpop.proof("POST", &boot_htu, "aud-b1", None))
                    .body(Body::from(
                        json!({
                            "sub": "agent-parent",
                            "tenant_id": "acme",
                            "role": "reader"
                        })
                        .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let parent_tok = serde_json::from_slice::<Value>(
            &axum::body::to_bytes(resp.into_body(), 16 * 1024)
                .await
                .unwrap(),
        )
        .unwrap()["access_token"]
            .as_str()
            .unwrap()
            .to_string();

        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/mcp/poc/delegate")
                    .header("content-type", "application/json")
                    .header("Authorization", format!("DPoP {parent_tok}"))
                    .header(
                        "DPoP",
                        parent_dpop.proof("POST", &del_htu, "aud-d1", Some(&parent_tok)),
                    )
                    .body(Body::from(
                        json!({
                            "sub": "agent-child",
                            "target_tool": "payments_list",
                            "child_dpop_jwk": {
                                "kty": child_dpop.jwk.kty,
                                "crv": child_dpop.jwk.crv,
                                "x": child_dpop.jwk.x,
                                "y": child_dpop.jwk.y
                            },
                            "allowed_tools": ["payments_list", "payments_other"],
                            "ttl_secs": 120
                        })
                        .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let child_json: Value = serde_json::from_slice(
            &axum::body::to_bytes(resp.into_body(), 16 * 1024)
                .await
                .unwrap(),
        )
        .unwrap();
        assert_eq!(child_json["aud"], "mcp-tool:acme:payments_list");
        let child_tok = child_json["access_token"].as_str().unwrap().to_string();

        let send_mcp = |tok: &str, jti: &str, payload: Value| {
            let app = app.clone();
            let auth_header = format!("DPoP {tok}");
            let proof = child_dpop.proof("POST", &mcp_htu, jti, Some(tok));
            let body = payload.to_string();
            async move {
                app.oneshot(
                    Request::builder()
                        .method("POST")
                        .uri("/mcp/poc")
                        .header("content-type", "application/json")
                        .header("Authorization", auth_header)
                        .header("DPoP", proof)
                        .body(Body::from(body))
                        .unwrap(),
                )
                .await
                .unwrap()
            }
        };

        // 2. Child call on its target tool succeeds (baseline).
        let resp = send_mcp(
            &child_tok,
            "aud-ok",
            json!({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": { "name": "payments_list", "arguments": {} }
            }),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::OK);
        let rpc: Value = serde_json::from_slice(
            &axum::body::to_bytes(resp.into_body(), 16 * 1024)
                .await
                .unwrap(),
        )
        .unwrap();
        assert!(rpc.get("error").is_none(), "target tool failed: {rpc}");
        assert_eq!(upstream.received_requests().await.unwrap().len(), 1);

        // 3. Valid child token used on a tool other than its target is refused (401).
        let resp = send_mcp(
            &child_tok,
            "aud-wrong-tool",
            json!({
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": { "name": "payments_other", "arguments": {} }
            }),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);

        // 4. Valid child token used on a non-tool method (`tools/list`) is refused (401).
        let resp = send_mcp(
            &child_tok,
            "aud-list",
            json!({
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/list",
                "params": {}
            }),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);

        // 5. Forged gateway-signed child token carrying FORBIDDEN_CHILD_AUDIENCE is refused with
        //    401 on POST /mcp/poc without upstream calls: `tools/call` is rejected through the
        //    audience check ("audience mismatch" against the canonical tool audience), and `ping`
        //    is rejected as a non-tool method for a child token. The FORBIDDEN_CHILD_AUDIENCE
        //    invariant itself is exercised directly by the unit test in `local_agent_token.rs`.
        let auth = state.local_agent_auth.as_ref().unwrap();
        let mut generic_claims = auth
            .validate_token(
                &child_tok,
                Some(DELEGATION_ISSUER),
                "mcp-tool:acme:payments_list",
            )
            .unwrap();
        generic_claims.aud = FORBIDDEN_CHILD_AUDIENCE.to_string();
        let generic_child = auth.sign_claims_for_test(generic_claims).unwrap();

        let resp = send_mcp(
            generic_child.as_str(),
            "aud-generic-call",
            json!({
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": { "name": "payments_list", "arguments": {} }
            }),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);

        let resp = send_mcp(
            generic_child.as_str(),
            "aud-generic-ping",
            json!({
                "jsonrpc": "2.0",
                "id": 5,
                "method": "ping",
                "params": {}
            }),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);

        // Only the initial target-tool call reached upstream.
        assert_eq!(upstream.received_requests().await.unwrap().len(), 1);
    }

    #[derive(Clone, Default)]
    struct AuditBuffer(std::sync::Arc<std::sync::Mutex<Vec<u8>>>);

    impl AuditBuffer {
        fn capture() -> (Self, tracing::Dispatch) {
            static IDLE_DISPATCH: std::sync::OnceLock<tracing::Dispatch> =
                std::sync::OnceLock::new();
            // Keep a second dispatcher registered so callsite interest is computed
            // across dispatchers when another thread first visits a callsite.
            IDLE_DISPATCH
                .get_or_init(|| tracing::Dispatch::new(tracing::subscriber::NoSubscriber::new()));

            let buffer = Self::default();
            let writer = buffer.clone();
            let subscriber = tracing_subscriber::fmt()
                .json()
                .with_writer(move || writer.clone())
                .with_max_level(tracing::Level::WARN)
                .finish();
            (buffer, tracing::Dispatch::new(subscriber))
        }

        fn offset(&self) -> usize {
            self.0.lock().unwrap().len()
        }

        fn events_since(&self, start: usize) -> Vec<Value> {
            let bytes = self.0.lock().unwrap();
            String::from_utf8_lossy(&bytes[start..])
                .lines()
                .filter_map(|line| serde_json::from_str::<Value>(line).ok())
                .collect()
        }
    }

    impl std::io::Write for AuditBuffer {
        fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> {
            self.0.lock().unwrap().extend_from_slice(bytes);
            Ok(bytes.len())
        }

        fn flush(&mut self) -> std::io::Result<()> {
            Ok(())
        }
    }

    #[tokio::test]
    async fn tools_list_applies_tenant_and_opa_decisions_without_consuming_budget() {
        use tracing::instrument::WithSubscriber;
        let upstream = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/payments"))
            .and(header("X-API-Key", "ky-list"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({"ok": true})))
            .mount(&upstream)
            .await;
        Mock::given(method("GET"))
            .and(path("/tenant-denied"))
            .respond_with(ResponseTemplate::new(200).set_body_string("must-not-reach"))
            .expect(0)
            .mount(&upstream)
            .await;
        Mock::given(method("GET"))
            .and(path("/opa-denied"))
            .respond_with(ResponseTemplate::new(200).set_body_string("must-not-reach"))
            .expect(0)
            .mount(&upstream)
            .await;

        let tmp = tempfile::tempdir().unwrap();
        let signer = PolicyFixtureSigner::new();
        let trust_file = signer.write_trust(tmp.path());

        let policies_dir = tmp.path().join("policies");
        let roles_dir = tmp.path().join("roles");
        let floor_dir = tmp.path().join("floors");
        let contracts_dir = tmp.path().join("contracts");
        let opa_dir = tmp.path().join("opa");
        for d in [&policies_dir, &roles_dir, &contracts_dir, &opa_dir] {
            std::fs::create_dir_all(d).unwrap();
        }

        // Signed tenant policy allows `payments_list` and `payments_opa_denied`,
        // omitting `payments_tenant_denied` even though the role allows all three.
        std::fs::write(
            policies_dir.join("acme.jws"),
            signer.sign_tool_policy("acme", &["payments_list", "payments_opa_denied"]),
        )
        .unwrap();

        let opa_file = opa_dir.join("policy.rego");
        std::fs::write(
            &opa_file,
            r#"package stoa.authz
import future.keywords.if
default allow := false
allow if {
    input.tenant_id == "acme"
    input.resource_tenant_id == "acme"
    input.tool_name != "payments_opa_denied"
    input.action == "Read"
}
"#,
        )
        .unwrap();

        std::fs::write(
            roles_dir.join("acme.roles.jws"),
            signer.sign_role_policy(
                "acme",
                1,
                json!({
                    "reader": {
                        "allowed_tools": [
                            "payments_list",
                            "payments_tenant_denied",
                            "payments_opa_denied"
                        ]
                    }
                }),
            ),
        )
        .unwrap();

        std::fs::write(
            contracts_dir.join("payments.uac.json"),
            serde_json::to_string(&json!({
                "name": "payments",
                "version": "1.0.0",
                "tenant_id": "acme",
                "display_name": "Payments List Filter",
                "description": "Filter tools/list by tenant and OPA policy",
                "classification": "H",
                "endpoints": [
                    {
                        "path": "/payments",
                        "methods": ["GET"],
                        "backend_url": format!("{}/payments", upstream.uri()),
                        "operation_id": "list_payments",
                        "llm": {
                            "summary": "List payments",
                            "intent": "Read payments",
                            "tool_name": "payments_list",
                            "side_effects": "read",
                            "safe_for_agents": true,
                            "requires_human_approval": false,
                            "examples": []
                        }
                    },
                    {
                        "path": "/tenant-denied",
                        "methods": ["GET"],
                        "backend_url": format!("{}/tenant-denied", upstream.uri()),
                        "operation_id": "tenant_denied",
                        "llm": {
                            "summary": "Tenant denied tool",
                            "intent": "Denied by signed tenant policy",
                            "tool_name": "payments_tenant_denied",
                            "side_effects": "read",
                            "safe_for_agents": true,
                            "requires_human_approval": false,
                            "examples": []
                        }
                    },
                    {
                        "path": "/opa-denied",
                        "methods": ["GET"],
                        "backend_url": format!("{}/opa-denied", upstream.uri()),
                        "operation_id": "opa_denied",
                        "llm": {
                            "summary": "OPA denied tool",
                            "intent": "Denied by OPA policy",
                            "tool_name": "payments_opa_denied",
                            "side_effects": "read",
                            "safe_for_agents": true,
                            "requires_human_approval": false,
                            "examples": []
                        }
                    }
                ],
                "required_policies": [],
                "status": "published"
            }))
            .unwrap(),
        )
        .unwrap();

        let creds_file = tmp.path().join("credentials.json");
        std::fs::write(
            &creds_file,
            serde_json::to_string(&json!([{
                "route_id": "mcp-tool:acme:payments_list",
                "auth_type": "api_key",
                "header_name": "X-API-Key",
                "header_value": "ky-list",
                "allowed_origin": upstream.uri(),
                "shared_with_tenants": false
            }]))
            .unwrap(),
        )
        .unwrap();

        let base_url = "http://stoa-gateway:8080";
        let config = Config {
            auto_register: false,
            admin_routes_disabled: true,
            policy_enabled: true,
            policy_path: Some(opa_file.to_string_lossy().to_string()),
            policy_boot_tenants: vec!["acme".to_string()],
            policy_trust_jwks_file: Some(trust_file),
            policy_local_artifacts_dir: Some(policies_dir.to_string_lossy().to_string()),
            policy_expected_issuer: "stoa-poc-policy".to_string(),
            policy_audience: "stoa-gateway".to_string(),
            poc_agents_enabled: true,
            poc_bootstrap_secret: Some("bt-list".to_string()),
            poc_uac_contracts_dir: Some(contracts_dir.to_string_lossy().to_string()),
            poc_credentials_file: Some(creds_file.to_string_lossy().to_string()),
            poc_public_base_url: Some(base_url.to_string()),
            poc_role_artifacts_dir: Some(roles_dir.to_string_lossy().to_string()),
            poc_role_floor_dir: Some(floor_dir.to_string_lossy().to_string()),
            poc_outbound_allowed_origins: vec![upstream.uri()],
            poc_chain_budget: 1,
            poc_caller_budget: 1,
            ..Config::default()
        };

        let state = AppState::new(config);
        load_poc_fixtures(&state).await.unwrap();
        state
            .tool_permissions
            .as_ref()
            .unwrap()
            .load_policy("acme")
            .await
            .unwrap();
        let app = build_router(state.clone());

        let dpop = TestDpop::new();
        let boot_htu = format!("{base_url}/mcp/poc/bootstrap");
        let mcp_htu = format!("{base_url}/mcp/poc");

        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/mcp/poc/bootstrap")
                    .header("content-type", "application/json")
                    .header("X-Stoa-Poc-Bootstrap-Secret", "bt-list")
                    .header("DPoP", dpop.proof("POST", &boot_htu, "list-b1", None))
                    .body(Body::from(
                        json!({
                            "sub": "agent-list-test",
                            "tenant_id": "acme",
                            "role": "reader"
                        })
                        .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let boot_json: Value = serde_json::from_slice(
            &axum::body::to_bytes(resp.into_body(), 16 * 1024)
                .await
                .unwrap(),
        )
        .unwrap();
        let token = boot_json["access_token"].as_str().unwrap().to_string();
        let chain_id = boot_json["chain_id"].as_str().unwrap().to_string();
        let caller_key = caller_identity_key("acme", "agent-list-test");

        let send_mcp = |jti: &str, payload: Value| {
            let app = app.clone();
            let auth_header = format!("DPoP {token}");
            let proof = dpop.proof("POST", &mcp_htu, jti, Some(&token));
            let body = payload.to_string();
            async move {
                let resp = app
                    .oneshot(
                        Request::builder()
                            .method("POST")
                            .uri("/mcp/poc")
                            .header("content-type", "application/json")
                            .header("Authorization", auth_header)
                            .header("DPoP", proof)
                            .body(Body::from(body))
                            .unwrap(),
                    )
                    .await
                    .unwrap();
                assert_eq!(resp.status(), StatusCode::OK);
                serde_json::from_slice::<Value>(
                    &axum::body::to_bytes(resp.into_body(), 16 * 1024)
                        .await
                        .unwrap(),
                )
                .unwrap()
            }
        };

        let (audit_buffer, subscriber) = AuditBuffer::capture();
        async {
            // Call tools/list twice (exceeding the chain/caller budget of 1 if it debited).
            let list_start = audit_buffer.offset();
            for (idx, jti) in ["list-1", "list-2"].iter().enumerate() {
                let rpc = send_mcp(
                    jti,
                    json!({"jsonrpc": "2.0", "id": idx + 1, "method": "tools/list", "params": {}}),
                )
                .await;
                assert!(rpc.get("error").is_none(), "tools/list failed: {rpc}");
                let names: Vec<&str> = rpc["result"]["tools"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .filter_map(|t| t["name"].as_str())
                    .collect();
                assert_eq!(names, vec!["payments_list", POC_SECURITY_TOOL]);
            }
            let list_denials: Vec<Value> = audit_buffer
                .events_since(list_start)
                .into_iter()
                .filter(|event| event["fields"]["audit_event"] == "tool_call_denied")
                .collect();
            assert!(
                list_denials.is_empty(),
                "tools/list must not emit tool_call_denied audit events: {list_denials:?}"
            );
            assert_eq!(state.poc_admission.chain_used(&chain_id), 0);
            assert_eq!(state.poc_admission.caller_used(&caller_key), 0);

            // Calling the tenant-denied tool is refused without hitting upstream or debiting budget,
            // and still emits a tool_call_denied audit event.
            let tenant_deny_start = audit_buffer.offset();
            let tenant_rpc = send_mcp(
                "call-tenant-denied",
                json!({
                    "jsonrpc": "2.0",
                    "id": 10,
                    "method": "tools/call",
                    "params": {"name": "payments_tenant_denied", "arguments": {}}
                }),
            )
            .await;
            assert_eq!(tenant_rpc["error"]["code"], -32003);
            assert_eq!(tenant_rpc["error"]["message"], "Tool call rejected");
            let tenant_call_denials: Vec<Value> = audit_buffer
                .events_since(tenant_deny_start)
                .into_iter()
                .filter(|event| event["fields"]["audit_event"] == "tool_call_denied")
                .collect();
            assert_eq!(
                tenant_call_denials.len(),
                1,
                "explicit denied tools/call must emit tool_call_denied: {tenant_call_denials:?}"
            );
            assert_eq!(
                tenant_call_denials[0]["fields"]["tool_name"],
                "payments_tenant_denied"
            );
            assert_eq!(tenant_call_denials[0]["fields"]["tenant_id"], "acme");

            // Calling the OPA-denied tool is refused without hitting upstream or debiting budget.
            let opa_rpc = send_mcp(
                "call-opa-denied",
                json!({
                    "jsonrpc": "2.0",
                    "id": 11,
                    "method": "tools/call",
                    "params": {"name": "payments_opa_denied", "arguments": {}}
                }),
            )
            .await;
            assert_eq!(opa_rpc["error"]["code"], -32003);
            assert_eq!(opa_rpc["error"]["message"], "Tool call rejected by policy");
            assert_eq!(state.poc_admission.chain_used(&chain_id), 0);
            assert_eq!(state.poc_admission.caller_used(&caller_key), 0);

            // Calling the allowed tool succeeds and consumes the single available budget slot.
            let ok_rpc = send_mcp(
                "call-ok",
                json!({
                    "jsonrpc": "2.0",
                    "id": 12,
                    "method": "tools/call",
                    "params": {"name": "payments_list", "arguments": {}}
                }),
            )
            .await;
            assert!(
                ok_rpc.get("error").is_none(),
                "allowed call failed: {ok_rpc}"
            );
            assert_eq!(state.poc_admission.chain_used(&chain_id), 1);
            assert_eq!(state.poc_admission.caller_used(&caller_key), 1);
        }
        .with_subscriber(subscriber)
        .await;

        let reqs = upstream.received_requests().await.unwrap();
        assert_eq!(reqs.len(), 1);
        assert_eq!(reqs[0].url.path(), "/payments");
    }

    #[tokio::test]
    async fn role_policy_reduction_takes_effect_on_next_call_and_tools_list() {
        let upstream = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/payments"))
            .and(header("X-API-Key", "ky-red"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({"ok": "list"})))
            .mount(&upstream)
            .await;
        Mock::given(method("GET"))
            .and(path("/export"))
            .and(header("X-API-Key", "ky-red"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({"ok": "export"})))
            .mount(&upstream)
            .await;

        let tmp = tempfile::tempdir().unwrap();
        let signer = PolicyFixtureSigner::new();
        let trust_file = signer.write_trust(tmp.path());

        let policies_dir = tmp.path().join("policies");
        let roles_dir = tmp.path().join("roles");
        let floor_dir = tmp.path().join("floors");
        let contracts_dir = tmp.path().join("contracts");
        for d in [&policies_dir, &roles_dir, &contracts_dir] {
            std::fs::create_dir_all(d).unwrap();
        }

        std::fs::write(
            policies_dir.join("acme.jws"),
            signer.sign_tool_policy("acme", &["payments_list", "payments_export"]),
        )
        .unwrap();

        let role_file = roles_dir.join("acme.roles.jws");
        std::fs::write(
            &role_file,
            signer.sign_role_policy(
                "acme",
                1,
                json!({
                    "reader": {
                        "allowed_tools": ["payments_list", "payments_export"]
                    }
                }),
            ),
        )
        .unwrap();

        std::fs::write(
            contracts_dir.join("payments.uac.json"),
            serde_json::to_string(&json!({
                "name": "payments",
                "version": "1.0.0",
                "tenant_id": "acme",
                "display_name": "Payments Reduction",
                "description": "Immediate role reduction fixture",
                "classification": "H",
                "endpoints": [
                    {
                        "path": "/payments",
                        "methods": ["GET"],
                        "backend_url": format!("{}/payments", upstream.uri()),
                        "operation_id": "list_payments",
                        "llm": {
                            "summary": "List payments",
                            "intent": "Read payments",
                            "tool_name": "payments_list",
                            "side_effects": "read",
                            "safe_for_agents": true,
                            "requires_human_approval": false,
                            "examples": []
                        }
                    },
                    {
                        "path": "/export",
                        "methods": ["GET"],
                        "backend_url": format!("{}/export", upstream.uri()),
                        "operation_id": "export_payments",
                        "llm": {
                            "summary": "Export payments",
                            "intent": "Export payments",
                            "tool_name": "payments_export",
                            "side_effects": "read",
                            "safe_for_agents": true,
                            "requires_human_approval": false,
                            "examples": []
                        }
                    }
                ],
                "required_policies": [],
                "status": "published"
            }))
            .unwrap(),
        )
        .unwrap();

        let creds_file = tmp.path().join("credentials.json");
        std::fs::write(
            &creds_file,
            serde_json::to_string(&json!([
                {
                    "route_id": "mcp-tool:acme:payments_list",
                    "auth_type": "api_key",
                    "header_name": "X-API-Key",
                    "header_value": "ky-red",
                    "allowed_origin": upstream.uri(),
                    "shared_with_tenants": false
                },
                {
                    "route_id": "mcp-tool:acme:payments_export",
                    "auth_type": "api_key",
                    "header_name": "X-API-Key",
                    "header_value": "ky-red",
                    "allowed_origin": upstream.uri(),
                    "shared_with_tenants": false
                }
            ]))
            .unwrap(),
        )
        .unwrap();

        let base_url = "http://stoa-gateway:8080";
        let config = Config {
            auto_register: false,
            admin_routes_disabled: true,
            policy_enabled: false,
            policy_boot_tenants: vec!["acme".to_string()],
            policy_trust_jwks_file: Some(trust_file),
            policy_local_artifacts_dir: Some(policies_dir.to_string_lossy().to_string()),
            policy_expected_issuer: "stoa-poc-policy".to_string(),
            policy_audience: "stoa-gateway".to_string(),
            poc_agents_enabled: true,
            poc_bootstrap_secret: Some("bt-red".to_string()),
            poc_uac_contracts_dir: Some(contracts_dir.to_string_lossy().to_string()),
            poc_credentials_file: Some(creds_file.to_string_lossy().to_string()),
            poc_public_base_url: Some(base_url.to_string()),
            poc_role_artifacts_dir: Some(roles_dir.to_string_lossy().to_string()),
            poc_role_floor_dir: Some(floor_dir.to_string_lossy().to_string()),
            poc_outbound_allowed_origins: vec![upstream.uri()],
            ..Config::default()
        };

        let state = AppState::new(config);
        load_poc_fixtures(&state).await.unwrap();
        state
            .tool_permissions
            .as_ref()
            .unwrap()
            .load_policy("acme")
            .await
            .unwrap();
        let app = build_router(state);

        let dpop = TestDpop::new();
        let boot_htu = format!("{base_url}/mcp/poc/bootstrap");
        let mcp_htu = format!("{base_url}/mcp/poc");

        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/mcp/poc/bootstrap")
                    .header("content-type", "application/json")
                    .header("X-Stoa-Poc-Bootstrap-Secret", "bt-red")
                    .header("DPoP", dpop.proof("POST", &boot_htu, "red-b1", None))
                    .body(Body::from(
                        json!({
                            "sub": "agent-reduction",
                            "tenant_id": "acme",
                            "role": "reader"
                        })
                        .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let token = serde_json::from_slice::<Value>(
            &axum::body::to_bytes(resp.into_body(), 16 * 1024)
                .await
                .unwrap(),
        )
        .unwrap()["access_token"]
            .as_str()
            .unwrap()
            .to_string();

        let send_mcp = |jti: &str, payload: Value| {
            let app = app.clone();
            let auth_header = format!("DPoP {token}");
            let proof = dpop.proof("POST", &mcp_htu, jti, Some(&token));
            let body = payload.to_string();
            async move {
                let resp = app
                    .oneshot(
                        Request::builder()
                            .method("POST")
                            .uri("/mcp/poc")
                            .header("content-type", "application/json")
                            .header("Authorization", auth_header)
                            .header("DPoP", proof)
                            .body(Body::from(body))
                            .unwrap(),
                    )
                    .await
                    .unwrap();
                assert_eq!(resp.status(), StatusCode::OK);
                serde_json::from_slice::<Value>(
                    &axum::body::to_bytes(resp.into_body(), 16 * 1024)
                        .await
                        .unwrap(),
                )
                .unwrap()
            }
        };

        // Baseline: payments_export is listed and callable under v1.
        let list_v1 = send_mcp(
            "red-list-1",
            json!({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}),
        )
        .await;
        let names_v1: Vec<&str> = list_v1["result"]["tools"]
            .as_array()
            .unwrap()
            .iter()
            .filter_map(|t| t["name"].as_str())
            .collect();
        assert!(names_v1.contains(&"payments_list"));
        assert!(names_v1.contains(&"payments_export"));

        let call_v1 = send_mcp(
            "red-call-1",
            json!({
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": { "name": "payments_export", "arguments": {} }
            }),
        )
        .await;
        assert!(
            call_v1.get("error").is_none(),
            "baseline export failed: {call_v1}"
        );

        // Overwrite with signed v2 removing payments_export (no sleep).
        let next_role_file = roles_dir.join("acme.roles.jws.next");
        std::fs::write(
            &next_role_file,
            signer.sign_role_policy(
                "acme",
                2,
                json!({
                    "reader": {
                        "allowed_tools": ["payments_list"]
                    }
                }),
            ),
        )
        .unwrap();
        std::fs::rename(&next_role_file, &role_file).unwrap();

        // Immediately refused on the very next tools/call without hitting upstream.
        let call_v2 = send_mcp(
            "red-call-2",
            json!({
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": { "name": "payments_export", "arguments": {} }
            }),
        )
        .await;
        assert_eq!(call_v2["error"]["code"], -32003);
        assert_eq!(
            call_v2["error"]["message"],
            "Tool call rejected by role policy"
        );

        // Immediately absent from tools/list, while payments_list stays listed and callable.
        let list_v2 = send_mcp(
            "red-list-2",
            json!({"jsonrpc": "2.0", "id": 4, "method": "tools/list", "params": {}}),
        )
        .await;
        let names_v2: Vec<&str> = list_v2["result"]["tools"]
            .as_array()
            .unwrap()
            .iter()
            .filter_map(|t| t["name"].as_str())
            .collect();
        assert_eq!(names_v2, vec!["payments_list", POC_SECURITY_TOOL]);
        let limits_v2 = send_mcp(
            "red-limits-2",
            json!({
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {
                    "name": POC_SECURITY_TOOL,
                    "arguments": {"action": "get_my_limits"}
                }
            }),
        )
        .await;
        let limits = &limits_v2["result"]["structuredContent"];
        assert_eq!(limits["issued_policy_version"], 1);
        assert_eq!(limits["policy_version"], 2);
        assert_eq!(limits["allowed_tools"], json!(names_v2));

        let list_call_v2 = send_mcp(
            "red-call-3",
            json!({
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": { "name": "payments_list", "arguments": {} }
            }),
        )
        .await;
        assert!(
            list_call_v2.get("error").is_none(),
            "remaining allowed tool failed: {list_call_v2}"
        );

        let reqs = upstream.received_requests().await.unwrap();
        let export_calls = reqs.iter().filter(|r| r.url.path() == "/export").count();
        let list_calls = reqs.iter().filter(|r| r.url.path() == "/payments").count();
        assert_eq!(export_calls, 1);
        assert_eq!(list_calls, 1);
    }

    #[tokio::test]
    async fn secret_revocation_requires_known_active_chain_and_respects_tenant() {
        let upstream = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/payments"))
            .and(header("X-API-Key", "ky-rev"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({"ok": true})))
            .mount(&upstream)
            .await;

        let tmp = tempfile::tempdir().unwrap();
        let signer = PolicyFixtureSigner::new();
        let trust_file = signer.write_trust(tmp.path());

        let policies_dir = tmp.path().join("policies");
        let roles_dir = tmp.path().join("roles");
        let floor_dir = tmp.path().join("floors");
        let contracts_dir = tmp.path().join("contracts");
        for d in [&policies_dir, &roles_dir, &contracts_dir] {
            std::fs::create_dir_all(d).unwrap();
        }

        for tenant in ["acme", "beta"] {
            let tool_name = format!("{tenant}_payments_list");
            std::fs::write(
                policies_dir.join(format!("{tenant}.jws")),
                signer.sign_tool_policy(tenant, &[tool_name.as_str()]),
            )
            .unwrap();
            std::fs::write(
                roles_dir.join(format!("{tenant}.roles.jws")),
                signer.sign_role_policy(
                    tenant,
                    1,
                    json!({
                        "reader": { "allowed_tools": [tool_name] }
                    }),
                ),
            )
            .unwrap();
            std::fs::write(
                contracts_dir.join(format!("{tenant}.uac.json")),
                serde_json::to_string(&json!({
                    "name": format!("payments-{tenant}"),
                    "version": "1.0.0",
                    "tenant_id": tenant,
                    "display_name": "Payments Revoke",
                    "description": "Revocation fixture",
                    "classification": "H",
                    "endpoints": [{
                        "path": "/payments",
                        "methods": ["GET"],
                        "backend_url": format!("{}/payments", upstream.uri()),
                        "operation_id": format!("list_payments_{tenant}"),
                        "llm": {
                            "summary": "List payments",
                            "intent": "Read payments",
                            "tool_name": tool_name,
                            "side_effects": "read",
                            "safe_for_agents": true,
                            "requires_human_approval": false,
                            "examples": []
                        }
                    }],
                    "required_policies": [],
                    "status": "published"
                }))
                .unwrap(),
            )
            .unwrap();
        }

        let creds_file = tmp.path().join("credentials.json");
        std::fs::write(
            &creds_file,
            serde_json::to_string(&json!([
                {
                    "route_id": "mcp-tool:acme:acme_payments_list",
                    "auth_type": "api_key",
                    "header_name": "X-API-Key",
                    "header_value": "ky-rev",
                    "allowed_origin": upstream.uri(),
                    "shared_with_tenants": false
                },
                {
                    "route_id": "mcp-tool:beta:beta_payments_list",
                    "auth_type": "api_key",
                    "header_name": "X-API-Key",
                    "header_value": "ky-rev",
                    "allowed_origin": upstream.uri(),
                    "shared_with_tenants": false
                }
            ]))
            .unwrap(),
        )
        .unwrap();

        let base_url = "http://stoa-gateway:8080";
        let config = Config {
            auto_register: false,
            admin_routes_disabled: true,
            policy_enabled: false,
            policy_boot_tenants: vec!["acme".to_string(), "beta".to_string()],
            policy_trust_jwks_file: Some(trust_file),
            policy_local_artifacts_dir: Some(policies_dir.to_string_lossy().to_string()),
            policy_expected_issuer: "stoa-poc-policy".to_string(),
            policy_audience: "stoa-gateway".to_string(),
            poc_agents_enabled: true,
            poc_bootstrap_secret: Some("bt-rev".to_string()),
            poc_uac_contracts_dir: Some(contracts_dir.to_string_lossy().to_string()),
            poc_credentials_file: Some(creds_file.to_string_lossy().to_string()),
            poc_public_base_url: Some(base_url.to_string()),
            poc_role_artifacts_dir: Some(roles_dir.to_string_lossy().to_string()),
            poc_role_floor_dir: Some(floor_dir.to_string_lossy().to_string()),
            poc_outbound_allowed_origins: vec![upstream.uri()],
            poc_max_revoked_chains: 3,
            ..Config::default()
        };

        let state = AppState::new(config);
        load_poc_fixtures(&state).await.unwrap();
        let perms = state.tool_permissions.as_ref().unwrap();
        perms.load_policy("acme").await.unwrap();
        perms.load_policy("beta").await.unwrap();
        let app = build_router(state.clone());

        let boot_htu = format!("{base_url}/mcp/poc/bootstrap");
        let rev_htu = format!("{base_url}/mcp/poc/revoke");
        let mcp_htu = format!("{base_url}/mcp/poc");

        let secret_revoke = |payload: Value| {
            let app = app.clone();
            let body = payload.to_string();
            async move {
                let resp = app
                    .oneshot(
                        Request::builder()
                            .method("POST")
                            .uri("/mcp/poc/revoke")
                            .header("content-type", "application/json")
                            .header("X-Stoa-Poc-Bootstrap-Secret", "bt-rev")
                            .body(Body::from(body))
                            .unwrap(),
                    )
                    .await
                    .unwrap();
                let status = resp.status();
                let bytes = axum::body::to_bytes(resp.into_body(), 16 * 1024)
                    .await
                    .unwrap();
                let json_body: Value = serde_json::from_slice(&bytes).unwrap();
                (status, json_body)
            }
        };

        let mint_parent = |dpop: &TestDpop, tenant: &str, sub: &str, jti: &str| {
            let app = app.clone();
            let proof = dpop.proof("POST", &boot_htu, jti, None);
            let payload = json!({
                "sub": sub,
                "tenant_id": tenant,
                "role": "reader"
            })
            .to_string();
            async move {
                let resp = app
                    .oneshot(
                        Request::builder()
                            .method("POST")
                            .uri("/mcp/poc/bootstrap")
                            .header("content-type", "application/json")
                            .header("X-Stoa-Poc-Bootstrap-Secret", "bt-rev")
                            .header("DPoP", proof)
                            .body(Body::from(payload))
                            .unwrap(),
                    )
                    .await
                    .unwrap();
                assert_eq!(resp.status(), StatusCode::OK);
                let bytes = axum::body::to_bytes(resp.into_body(), 16 * 1024)
                    .await
                    .unwrap();
                serde_json::from_slice::<Value>(&bytes).unwrap()
            }
        };

        let call_payments = |dpop: &TestDpop, tok: &str, jti: &str, id: i64| {
            let app = app.clone();
            let auth_header = format!("DPoP {tok}");
            let proof = dpop.proof("POST", &mcp_htu, jti, Some(tok));
            let payload = json!({
                "jsonrpc": "2.0",
                "id": id,
                "method": "tools/call",
                "params": { "name": "acme_payments_list", "arguments": {} }
            })
            .to_string();
            async move {
                let resp = app
                    .oneshot(
                        Request::builder()
                            .method("POST")
                            .uri("/mcp/poc")
                            .header("content-type", "application/json")
                            .header("Authorization", auth_header)
                            .header("DPoP", proof)
                            .body(Body::from(payload))
                            .unwrap(),
                    )
                    .await
                    .unwrap();
                assert_eq!(resp.status(), StatusCode::OK);
                let bytes = axum::body::to_bytes(resp.into_body(), 16 * 1024)
                    .await
                    .unwrap();
                serde_json::from_slice::<Value>(&bytes).unwrap()
            }
        };

        // 1. Unknown chain_ids via bootstrap secret return 404 unknown_chain and insert nothing.
        for idx in 0..5 {
            let (status, body) = secret_revoke(json!({
                "chain_id": format!("unknown-chain-{idx}"),
                "tenant_id": "acme"
            }))
            .await;
            assert_eq!(status, StatusCode::NOT_FOUND);
            assert_eq!(body["error"], "unknown_chain");
        }
        assert_eq!(state.poc_admission.revoked_count(), 0);

        // 2. Bootstrap a chain for acme and refuse secret revocation with another tenant_id.
        let dpop_acme = TestDpop::new();
        let acme_boot = mint_parent(&dpop_acme, "acme", "agent-acme", "rev-b1").await;
        let tok_acme = acme_boot["access_token"].as_str().unwrap().to_string();
        let cid_acme = acme_boot["chain_id"].as_str().unwrap().to_string();

        let (status, body) = secret_revoke(json!({
            "chain_id": cid_acme,
            "tenant_id": "beta"
        }))
        .await;
        assert_eq!(status, StatusCode::FORBIDDEN);
        assert_eq!(body["error"], "tenant_mismatch");
        assert_eq!(state.poc_admission.revoked_count(), 0);

        // Chain remains usable after rejected tenant mismatch.
        let rpc_ok = call_payments(&dpop_acme, &tok_acme, "rev-c1", 1).await;
        assert!(
            rpc_ok.get("error").is_none(),
            "expected active chain: {rpc_ok}"
        );

        // 3. Secret revocation with matching tenant succeeds and blocks subsequent calls.
        let (status, body) = secret_revoke(json!({
            "chain_id": cid_acme,
            "tenant_id": "acme"
        }))
        .await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(body["revoked"], json!(true));
        assert_eq!(state.poc_admission.revoked_count(), 1);

        let rpc_revoked = call_payments(&dpop_acme, &tok_acme, "rev-c2", 2).await;
        assert_eq!(rpc_revoked["error"]["code"], -32003);
        assert_eq!(rpc_revoked["error"]["message"], "Chain revoked");

        // Re-revoking an already-revoked chain via secret returns 404 unknown_chain.
        let (status, body) = secret_revoke(json!({
            "chain_id": cid_acme,
            "tenant_id": "acme"
        }))
        .await;
        assert_eq!(status, StatusCode::NOT_FOUND);
        assert_eq!(body["error"], "unknown_chain");
        assert_eq!(state.poc_admission.revoked_count(), 1);

        // 4. Secret revocation without optional tenant_id still revokes a known active chain.
        let dpop_beta1 = TestDpop::new();
        let beta1_boot = mint_parent(&dpop_beta1, "beta", "agent-beta-1", "rev-b2").await;
        let cid_beta1 = beta1_boot["chain_id"].as_str().unwrap().to_string();
        let (status, body) = secret_revoke(json!({ "chain_id": cid_beta1 })).await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(body["revoked"], json!(true));
        assert_eq!(state.poc_admission.revoked_count(), 2);

        // 5. Token-based self-revoke path remains unchanged.
        let dpop_beta2 = TestDpop::new();
        let beta2_boot = mint_parent(&dpop_beta2, "beta", "agent-beta-2", "rev-b3").await;
        let tok_beta2 = beta2_boot["access_token"].as_str().unwrap().to_string();
        let cid_beta2 = beta2_boot["chain_id"].as_str().unwrap().to_string();
        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/mcp/poc/revoke")
                    .header("content-type", "application/json")
                    .header("Authorization", format!("DPoP {tok_beta2}"))
                    .header(
                        "DPoP",
                        dpop_beta2.proof("POST", &rev_htu, "rev-self", Some(&tok_beta2)),
                    )
                    .body(Body::from(json!({ "chain_id": cid_beta2 }).to_string()))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        assert_eq!(state.poc_admission.revoked_count(), 3);
        assert_eq!(upstream.received_requests().await.unwrap().len(), 1);
    }
}
