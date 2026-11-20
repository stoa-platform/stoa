//! Autonomous PoC HTTP/MCP endpoints backed by dedicated local RS256 + DPoP auth.
//!
//! Routes (mounted only when `STOA_POC_AGENTS_ENABLED=true`):
//! - `POST /mcp/poc/bootstrap`: mints a DPoP-bound `depth=0` parent token for the
//!   designated parent container (`X-Stoa-Poc-Bootstrap-Secret` + valid DPoP proof).
//! - `POST /mcp/poc`: Streamable HTTP JSON-RPC 2.0 entrypoint enforcing strict local
//!   RS256 validation (separate from OIDC), atomic DPoP verification (`htm`, `htu`,
//!   `ath`, `cnf.jkt`), and the shared tool authorization chain.

use std::path::Path;

use axum::{
    body::Bytes,
    extract::State,
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    Json,
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use subtle::ConstantTimeEq;
use tracing::{info, warn};
use uuid::Uuid;

use crate::auth::local_agent_token::{
    IssueParentTokenRequest, LocalAgentClaims, LocalTokenError, LOCAL_AGENT_ISSUER,
};
use crate::mcp::handlers::{check_tool_permission, check_tool_policy, ToolsCallRequest};
use crate::mcp::sse::{
    JsonRpcRequest, JsonRpcResponse, INVALID_PARAMS, INVALID_REQUEST, METHOD_NOT_FOUND, PARSE_ERROR,
};
use crate::mcp::tools::ToolContext;
use crate::proxy::credentials::{normalize_origin, BackendCredential, MCP_TOOL_KEY_PREFIX};
use crate::state::AppState;
use crate::uac::binders::mcp::McpBinder;
use crate::uac::binders::{BindingOutput, ProtocolBinder};
use crate::uac::schema::UacContractSpec;
use crate::uac::Action;

/// Summary of local PoC fixtures loaded at gateway boot.
#[derive(Debug, Default, Clone, PartialEq, Eq)]
pub struct PocFixturesSummary {
    pub credentials_loaded: usize,
    pub contracts_loaded: usize,
    pub tools_registered: usize,
}

/// Load local backend credentials and UAC contracts configured for autonomous PoC mode.
pub async fn load_poc_fixtures(state: &AppState) -> Result<PocFixturesSummary, String> {
    let mut summary = PocFixturesSummary::default();

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
            .with_credential_store(state.credential_store.clone());

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

#[derive(Debug, Serialize)]
struct PocBootstrapResponse {
    access_token: String,
    token_type: &'static str,
    expires_in: i64,
    kid: String,
    chain_id: String,
    jti: String,
    depth: u8,
    aud: String,
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

    let aud = req
        .aud
        .filter(|a| !a.trim().is_empty())
        .unwrap_or_else(|| format!("{base}/mcp/poc"));
    let ttl_secs = req.ttl_secs.unwrap_or(300);

    match auth.issue_parent_token(IssueParentTokenRequest {
        sub: req.sub,
        tenant_id: req.tenant_id,
        role: req.role,
        aud: aud.clone(),
        cnf_jkt,
        ttl_secs,
    }) {
        Ok(issued) => (
            StatusCode::OK,
            Json(PocBootstrapResponse {
                access_token: issued.as_str().to_string(),
                token_type: "DPoP",
                expires_in: ttl_secs,
                kid: auth.kid().to_string(),
                chain_id: issued.claims.chain_id,
                jti: issued.claims.jti,
                depth: issued.claims.depth,
                aud: issued.claims.aud,
            }),
        )
            .into_response(),
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

/// `POST /mcp/poc` — Streamable HTTP JSON-RPC 2.0 entrypoint with local RS256 + DPoP.
pub async fn handle_poc_mcp(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    let Some(ref auth) = state.local_agent_auth else {
        return StatusCode::NOT_FOUND.into_response();
    };

    let request: JsonRpcRequest = match serde_json::from_slice(&body) {
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

    let base = public_base_url(&state);
    let mcp_htu = format!("{base}/mcp/poc");
    let claims = match auth.validate_mcp_request(&headers, "POST", &mcp_htu, &mcp_htu) {
        Ok(claims) => claims,
        Err(err) => {
            warn!(error = %err, "Rejected PoC MCP request");
            return (
                StatusCode::UNAUTHORIZED,
                Json(JsonRpcResponse::error(request.id, -32001, "Unauthorized")),
            )
                .into_response();
        }
    };

    // Child tokens (`depth > 0`) must never target the generic MCP endpoint audience.
    if claims.depth > 0 || claims.iss != LOCAL_AGENT_ISSUER {
        return (
            StatusCode::FORBIDDEN,
            Json(JsonRpcResponse::error(
                request.id,
                -32003,
                "Delegated token requires a resource-scoped audience",
            )),
        )
            .into_response();
    }

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
        "tools/list" => {
            let tools: Vec<Value> = state
                .tool_registry
                .list(Some(&claims.tenant_id))
                .into_iter()
                .map(|def| {
                    json!({
                        "name": def.name,
                        "description": def.description,
                        "inputSchema": def.input_schema
                    })
                })
                .collect();
            JsonRpcResponse::success(request.id, json!({ "tools": tools }))
        }
        "tools/call" => handle_poc_tool_call(&state, &claims, request).await,
        other => JsonRpcResponse::error(
            request.id,
            METHOD_NOT_FOUND,
            format!("Method '{other}' not found"),
        ),
    };

    (StatusCode::OK, Json(response)).into_response()
}

async fn handle_poc_tool_call(
    state: &AppState,
    claims: &LocalAgentClaims,
    request: JsonRpcRequest,
) -> JsonRpcResponse {
    let params = match request.params {
        Some(p) => p,
        None => return JsonRpcResponse::error(request.id, INVALID_PARAMS, "Missing params"),
    };
    let call_req: ToolsCallRequest = match serde_json::from_value(params) {
        Ok(r) => r,
        Err(e) => {
            return JsonRpcResponse::error(
                request.id,
                INVALID_PARAMS,
                format!("Invalid tools/call params: {e}"),
            );
        }
    };

    // 1. Resolve tenant-scoped tool.
    let tool = state
        .tool_registry
        .get_for_tenant(&call_req.name, &claims.tenant_id);
    let canonical_name = tool.as_ref().map_or(call_req.name.as_str(), |t| t.name());

    // 2. Signed tool permission check (fail-closed).
    if check_tool_permission(state, &claims.tenant_id, &call_req.name, canonical_name)
        .await
        .is_err()
    {
        return JsonRpcResponse::error(request.id, -32003, "Tool call rejected");
    }

    let Some(tool) = tool else {
        return JsonRpcResponse::error(request.id, -32004, "Tool not found");
    };

    // 3. Admin actions are never granted to local agent tokens.
    if matches!(
        tool.required_action(),
        Action::ManageTenants | Action::ManageUsers | Action::ManageContracts
    ) {
        return JsonRpcResponse::error(request.id, -32003, "Admin action not permitted");
    }

    // 4. Build local ToolContext: no raw_token, provenance strictly from signed claims
    //    (X-Stoa-Source and any provenance headers are ignored).
    let ctx = ToolContext {
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
    };

    // 5. OPA policy check.
    if check_tool_policy(state, tool.as_ref(), &ctx).is_err() {
        return JsonRpcResponse::error(request.id, -32003, "Tool call rejected by policy");
    }

    // 6. Execute tool (DynamicTool injects backend credential from CredentialStore
    //    without ever forwarding the caller token).
    match tool.execute(call_req.arguments, &ctx).await {
        Ok(result) => JsonRpcResponse::success(
            request.id,
            json!({
                "content": result.content,
                "isError": result.is_error.unwrap_or(false)
            }),
        ),
        Err(err) => {
            warn!(tool = %tool.name(), error = %err, "PoC tool execution failed");
            JsonRpcResponse::error(request.id, -32000, "Tool execution failed")
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::auth::dpop::{compute_ath, compute_jwk_thumbprint, DpopJwk};
    use crate::build_router;
    use crate::config::Config;
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

    fn write_signed_policy_fixtures(dir: &Path, tenant: &str, tool_name: &str) -> (String, String) {
        let pkcs8 = Ed25519KeyPair::generate_pkcs8(&aws_lc_rs::rand::SystemRandom::new()).unwrap();
        let kp = Ed25519KeyPair::from_pkcs8(pkcs8.as_ref()).unwrap();
        let x = URL_SAFE_NO_PAD.encode(kp.public_key().as_ref());
        let kid = "cp-policy-202611-1";

        let trust_path = dir.join("trust-jwks.json");
        std::fs::write(
            &trust_path,
            serde_json::to_string(&json!({
                "keys": [{
                    "kty": "OKP",
                    "crv": "Ed25519",
                    "alg": "EdDSA",
                    "use": "sig",
                    "kid": kid,
                    "x": x
                }]
            }))
            .unwrap(),
        )
        .unwrap();

        let now = chrono::Utc::now();
        let jws_header = URL_SAFE_NO_PAD.encode(
            serde_json::to_vec(&json!({
                "alg": "EdDSA",
                "typ": "stoa-tool-policy+jws",
                "kid": kid
            }))
            .unwrap(),
        );
        let jws_payload = URL_SAFE_NO_PAD.encode(
            serde_json::to_vec(&json!({
                "iss": "stoa-poc-policy",
                "aud": "stoa-gateway",
                "tenant_id": tenant,
                "tenant_uuid": Uuid::new_v4().to_string(),
                "version": 1,
                "issued_at": now.to_rfc3339(),
                "expires_at": (now + chrono::Duration::minutes(10)).to_rfc3339(),
                "permissions": [{
                    "mcp_server": "poc-payments",
                    "tool": tool_name,
                    "allowed": true
                }]
            }))
            .unwrap(),
        );
        let signing_input = format!("{jws_header}.{jws_payload}");
        let sig = kp.sign(signing_input.as_bytes());
        let compact = format!("{signing_input}.{}", URL_SAFE_NO_PAD.encode(sig.as_ref()));

        let policies_dir = dir.join("policies");
        std::fs::create_dir_all(&policies_dir).unwrap();
        std::fs::write(policies_dir.join(format!("{tenant}.jws")), compact).unwrap();

        (
            trust_path.to_string_lossy().to_string(),
            policies_dir.to_string_lossy().to_string(),
        )
    }

    #[tokio::test]
    async fn jalon1_autonomous_bootstrap_dpop_ready_and_admin_isolation() {
        let upstream = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/payments"))
            .and(header("X-API-Key", "backend-vault-secret"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({"status": "ok"})))
            .expect(1)
            .mount(&upstream)
            .await;

        let tmp = tempfile::tempdir().unwrap();
        let tool_name = "payments_list";
        let (trust_file, policies_dir) =
            write_signed_policy_fixtures(tmp.path(), "acme", tool_name);

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
                "header_value": "backend-vault-secret",
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
            policy_local_artifacts_dir: Some(policies_dir),
            policy_expected_issuer: "stoa-poc-policy".to_string(),
            policy_audience: "stoa-gateway".to_string(),
            poc_agents_enabled: true,
            poc_bootstrap_secret: Some("parent-only-bootstrap-secret".to_string()),
            poc_uac_contracts_dir: Some(contracts_dir.to_string_lossy().to_string()),
            poc_credentials_file: Some(creds_file.to_string_lossy().to_string()),
            poc_public_base_url: Some(base_url.to_string()),
            ..Config::default()
        };

        let state = AppState::new(config);
        let loaded = load_poc_fixtures(&state).await.expect("load poc fixtures");
        assert_eq!(loaded.credentials_loaded, 1);
        assert_eq!(loaded.contracts_loaded, 1);
        assert_eq!(loaded.tools_registered, 1);

        let app = build_router(state.clone());

        // 1. /ready fails before startup policy load, succeeds once local signed policy is loaded.
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

        // 2. /admin/* is completely absent (404) when admin_routes_disabled=true.
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

        // 3. Bootstrap rejected without parent secret (child cannot mint a parent token).
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

        // 4. Bootstrap succeeds with parent secret + valid DPoP proof.
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
        assert_eq!(boot_json["token_type"], "DPoP");
        assert_eq!(boot_json["depth"], 0);

        // 5. MCP tools/call with valid RS256 token + DPoP proof succeeds and injects vault key
        //    without forwarding the caller token.
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

        // 6. Replaying the exact same DPoP proof is rejected (and upstream still saw only 1 request).
        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/mcp/poc")
                    .header("content-type", "application/json")
                    .header("Authorization", format!("DPoP {token}"))
                    .header("DPoP", &proof)
                    .body(Body::from(call_body.clone()))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);

        // Verify wiremock saw NO Authorization header on the single upstream request.
        let received = upstream.received_requests().await.unwrap();
        assert_eq!(received.len(), 1);
        assert!(received[0].headers.get("authorization").is_none());
        assert_eq!(
            received[0]
                .headers
                .get("x-api-key")
                .and_then(|v| v.to_str().ok()),
            Some("backend-vault-secret")
        );
        // Verify compute_jwk_thumbprint matches non-empty output
        assert!(!compute_jwk_thumbprint(&dpop.jwk).is_empty());
    }
}
