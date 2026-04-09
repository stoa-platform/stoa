//! OAuth Token + DCR + PAR Proxy
//!
//! CAB-1094: Proxy OAuth endpoints to Keycloak for Claude.ai MCP connector.
//! CAB-1606: RFC 7592 — Dynamic Client Registration Management Protocol.
//! CAB-1733: RFC 9126 — Pushed Authorization Requests (PAR) for FAPI 2.0.
//! CAB-1740: RFC 7523 — JWT Bearer client assertion detection + validation.
//!
//! - POST /oauth/token — transparent proxy to Keycloak token endpoint
//! - POST /oauth/par — PAR proxy to Keycloak (RFC 9126, FAPI 2.0)
//! - POST /oauth/register — DCR proxy + public client patch for PKCE (RFC 7591)
//! - GET  /oauth/register/:client_id — read client metadata (RFC 7592)
//! - PUT  /oauth/register/:client_id — update client metadata (RFC 7592)
//! - DELETE /oauth/register/:client_id — revoke/delete client (RFC 7592)

use axum::{
    body::Bytes,
    extract::State,
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};
use tracing::{debug, error, info, instrument, warn};

use super::client_auth;
use crate::proxy::hardening::{build_via_value, with_keycloak_resilience};
use crate::state::AppState;

/// POST /oauth/token
///
/// Transparent proxy to Keycloak token endpoint.
/// Forwards body as-is, returns Keycloak response as-is.
///
/// When the request contains `client_assertion` + `client_assertion_type` (RFC 7523),
/// the gateway validates the assertion format and claims before forwarding to Keycloak.
/// Keycloak performs the actual signature verification using the client's registered JWKS.
#[instrument(name = "oauth.token_proxy", skip_all, fields(otel.kind = "client"))]
pub async fn token_proxy(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    let config = &state.config;

    // RFC 7523: Detect and validate JWT Bearer client assertion (private_key_jwt)
    // Parse early for format validation + observability; Keycloak handles signature verification.
    match client_auth::parse_client_assertion(&body) {
        Ok(Some(assertion)) => {
            let client_id = if assertion.client_id.is_empty() {
                "(from JWT iss)"
            } else {
                &assertion.client_id
            };
            info!(
                client_id = %client_id,
                auth_method = "private_key_jwt",
                "Token request using JWT Bearer client authentication (RFC 7523)"
            );
        }
        Ok(None) => {
            // Standard auth (client_secret_basic, client_secret_post, or none/public)
            debug!("Token request using standard client authentication");
        }
        Err(e) => {
            warn!(error = %e, "Invalid client_assertion in token request");
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({
                    "error": "invalid_client",
                    "error_description": format!("Client assertion validation failed: {}", e)
                })),
            )
                .into_response();
        }
    }

    let keycloak_url = match config.keycloak_backend_url() {
        Some(url) => url.trim_end_matches('/'),
        None => {
            warn!("Keycloak URL not configured — cannot proxy token request");
            return (
                StatusCode::SERVICE_UNAVAILABLE,
                Json(json!({"error": "server_error", "error_description": "Identity provider not configured"})),
            )
                .into_response();
        }
    };
    let realm = config.keycloak_realm.as_deref().unwrap_or("stoa");
    let token_url = format!(
        "{}/realms/{}/protocol/openid-connect/token",
        keycloak_url, realm
    );

    debug!(url = %token_url, "Proxying token request to Keycloak");

    let client = state.http_client.clone();
    let via_value = build_via_value();

    // Forward content-type from original request (axum HeaderMap uses http 1.x)
    let content_type = headers
        .get("content-type")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("application/x-www-form-urlencoded")
        .to_string();

    // Wrap the Keycloak call with circuit breaker + retry
    let result = with_keycloak_resilience(&state.circuit_breakers, "oauth-token", || {
        let c = client.clone();
        let url = token_url.clone();
        let ct = content_type.clone();
        let b = body.clone();
        let via = via_value;
        async move {
            c.post(&url)
                .header("content-type", ct)
                .header("Via", via)
                .body(b.to_vec())
                .send()
                .await
                .map_err(|e| e.to_string())
        }
    })
    .await;

    match result {
        Ok(resp) => {
            let status = resp.status();
            let resp_content_type = resp
                .headers()
                .get("content-type")
                .and_then(|v| v.to_str().ok())
                .unwrap_or("application/json")
                .to_string();
            let body = resp.bytes().await.unwrap_or_default();
            let mut response = (status, body).into_response();
            if let Ok(ct_val) = resp_content_type.parse() {
                response.headers_mut().insert("content-type", ct_val);
            }
            response
        }
        Err((status, msg)) => (
            status,
            Json(json!({"error": "server_error", "error_description": msg})),
        )
            .into_response(),
    }
}

/// POST /oauth/par
///
/// RFC 9126 — Pushed Authorization Requests.
/// Proxies PAR requests to Keycloak, enabling FAPI 2.0 clients to push
/// authorization parameters server-to-server before redirecting the user agent.
/// Returns a `request_uri` that the client uses in the authorization request.
pub async fn par_proxy(State(state): State<AppState>, headers: HeaderMap, body: Bytes) -> Response {
    let config = &state.config;

    let keycloak_url = match config.keycloak_backend_url() {
        Some(url) => url.trim_end_matches('/'),
        None => {
            warn!("Keycloak URL not configured — cannot proxy PAR request");
            return (
                StatusCode::SERVICE_UNAVAILABLE,
                Json(json!({"error": "server_error", "error_description": "Identity provider not configured"})),
            )
                .into_response();
        }
    };
    let realm = config.keycloak_realm.as_deref().unwrap_or("stoa");
    let par_url = format!(
        "{}/realms/{}/protocol/openid-connect/ext/par/request",
        keycloak_url, realm
    );

    debug!(url = %par_url, "Proxying PAR request to Keycloak");

    let client = state.http_client.clone();
    let via_value = build_via_value();

    let content_type = headers
        .get("content-type")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("application/x-www-form-urlencoded")
        .to_string();

    let result = with_keycloak_resilience(&state.circuit_breakers, "oauth-par", || {
        let c = client.clone();
        let url = par_url.clone();
        let ct = content_type.clone();
        let b = body.clone();
        let via = via_value;
        async move {
            c.post(&url)
                .header("content-type", ct)
                .header("Via", via)
                .body(b.to_vec())
                .send()
                .await
                .map_err(|e| e.to_string())
        }
    })
    .await;

    match result {
        Ok(resp) => {
            let status = resp.status();
            let resp_content_type = resp
                .headers()
                .get("content-type")
                .and_then(|v| v.to_str().ok())
                .unwrap_or("application/json")
                .to_string();
            let body = resp.bytes().await.unwrap_or_default();

            info!(
                status = %status,
                "PAR proxy response from Keycloak"
            );

            let mut response = (status, body).into_response();
            if let Ok(ct_val) = resp_content_type.parse() {
                response.headers_mut().insert("content-type", ct_val);
            }
            response
        }
        Err((status, msg)) => {
            error!(error = %msg, "PAR proxy failed");
            (
                status,
                Json(json!({"error": "server_error", "error_description": msg})),
            )
                .into_response()
        }
    }
}

/// POST /oauth/register
///
/// Dynamic Client Registration proxy to Keycloak.
/// After registration, patches the client to be public (no client_secret)
/// with S256 PKCE support — required for Claude.ai PKCE flow.
pub async fn register_proxy(State(state): State<AppState>, Json(payload): Json<Value>) -> Response {
    let config = &state.config;

    let keycloak_url = match config.keycloak_backend_url() {
        Some(url) => url.trim_end_matches('/'),
        None => {
            warn!("Keycloak URL not configured — cannot proxy DCR request");
            return (
                StatusCode::SERVICE_UNAVAILABLE,
                Json(json!({"error": "server_error", "error_description": "Identity provider not configured"})),
            )
                .into_response();
        }
    };
    let realm = config.keycloak_realm.as_deref().unwrap_or("stoa");

    let dcr_url = format!(
        "{}/realms/{}/clients-registrations/openid-connect",
        keycloak_url, realm
    );

    debug!(url = %dcr_url, "Proxying DCR request to Keycloak");

    // Strip `scope` from DCR payload before forwarding.
    // When Keycloak receives `scope` in DCR, it replaces the realm default scopes
    // with ONLY the requested ones — losing profile, email, roles, etc.
    // By removing it, Keycloak assigns ALL realm defaults + makes optionals available.
    // Claude.ai can then request any scope during the authorization step.
    let mut cleaned_payload = payload;
    if let Some(obj) = cleaned_payload.as_object_mut() {
        if obj.contains_key("scope") {
            debug!("Stripping 'scope' from DCR payload to preserve Keycloak realm defaults");
            obj.remove("scope");
        }
    }

    let client = state.http_client.clone();
    let via_value = build_via_value();

    // Step 1: Forward DCR to Keycloak with circuit breaker + retry
    let dcr_resp = match with_keycloak_resilience(&state.circuit_breakers, "oauth-register", || {
        let c = client.clone();
        let url = dcr_url.clone();
        let payload = cleaned_payload.clone();
        let via = via_value;
        async move {
            c.post(&url)
                .header("content-type", "application/json")
                .header("Via", via)
                .json(&payload)
                .send()
                .await
                .map_err(|e| e.to_string())
        }
    })
    .await
    {
        Ok(resp) => resp,
        Err((status, msg)) => {
            error!(error = %msg, "Failed to proxy DCR request to Keycloak");
            return (
                status,
                Json(json!({"error": "server_error", "error_description": msg})),
            )
                .into_response();
        }
    };

    let dcr_status_code = dcr_resp.status().as_u16();
    let dcr_body: Value = match dcr_resp.json().await {
        Ok(b) => b,
        Err(e) => {
            error!(error = %e, "Failed to parse DCR response");
            return (
                StatusCode::BAD_GATEWAY,
                Json(json!({"error": "server_error", "error_description": "Invalid response from identity provider"})),
            )
                .into_response();
        }
    };

    if dcr_status_code >= 400 {
        let status = StatusCode::from_u16(dcr_status_code).unwrap_or(StatusCode::BAD_GATEWAY);
        return (status, Json(dcr_body)).into_response();
    }

    let client_id = dcr_body
        .get("client_id")
        .and_then(|v| v.as_str())
        .unwrap_or("");

    info!(client_id = %client_id, "DCR client registered in Keycloak");

    // Step 2: Patch to public client with PKCE (if admin password configured)
    if let Some(ref admin_password) = config.keycloak_admin_password {
        match patch_public_client(
            &client,
            &state.admin_token_cache,
            keycloak_url,
            realm,
            admin_password,
            &dcr_body,
        )
        .await
        {
            Ok(()) => {
                info!(client_id = %client_id, "Client patched to public + PKCE S256");
            }
            Err(e) => {
                warn!(
                    client_id = %client_id,
                    error = %e,
                    "Failed to patch client to public — client may require client_secret"
                );
            }
        }
    } else {
        warn!(
            client_id = %client_id,
            "KEYCLOAK_ADMIN_PASSWORD not configured — skipping public client patch"
        );
    }

    // Return original DCR response (Claude.ai needs client_id, registration_access_token, etc.)
    let status = StatusCode::from_u16(dcr_status_code).unwrap_or(StatusCode::CREATED);
    (status, Json(dcr_body)).into_response()
}

/// Fetch a Keycloak admin token, using the moka cache for TTL-based reuse.
/// On cache miss, performs ROPG against Keycloak master realm.
async fn fetch_admin_token(
    client: &reqwest::Client,
    cache: &moka::sync::Cache<String, String>,
    keycloak_url: &str,
    admin_password: &str,
) -> Result<String, String> {
    let cache_key = format!("admin:{}", keycloak_url);

    if let Some(token) = cache.get(&cache_key) {
        return Ok(token);
    }

    let admin_token_url = format!(
        "{}/realms/master/protocol/openid-connect/token",
        keycloak_url
    );

    let token_resp = client
        .post(&admin_token_url)
        .form(&[
            ("grant_type", "password"),
            ("client_id", "admin-cli"),
            ("username", "admin"),
            ("password", admin_password),
        ])
        .send()
        .await
        .map_err(|e| format!("Admin token request failed: {}", e))?;

    if !token_resp.status().is_success() {
        let body = token_resp.text().await.unwrap_or_default();
        return Err(format!("Admin token failed: {}", body));
    }

    let token_data: Value = token_resp
        .json()
        .await
        .map_err(|e| format!("Parse admin token: {}", e))?;
    let token = token_data
        .get("access_token")
        .and_then(|v| v.as_str())
        .ok_or("Missing access_token in admin response")?
        .to_string();

    cache.insert(cache_key, token.clone());
    Ok(token)
}

/// Patch a Keycloak client to be public (no client_secret) with PKCE S256.
///
/// Steps:
/// 1. Get admin token (cached with TTL, retry on 401)
/// 2. Find the client by clientId
/// 3. PUT client config with publicClient=true + pkce.code.challenge.method=S256
async fn patch_public_client(
    client: &reqwest::Client,
    token_cache: &moka::sync::Cache<String, String>,
    keycloak_url: &str,
    realm: &str,
    admin_password: &str,
    dcr_body: &Value,
) -> Result<(), String> {
    let client_id_str = dcr_body
        .get("client_id")
        .and_then(|v| v.as_str())
        .ok_or("Missing client_id in DCR response")?;

    // 1. Get admin token (cached)
    let admin_token = fetch_admin_token(client, token_cache, keycloak_url, admin_password).await?;

    // 2. Find client by clientId
    let clients_url = format!(
        "{}/admin/realms/{}/clients?clientId={}",
        keycloak_url, realm, client_id_str
    );

    let clients_resp = client
        .get(&clients_url)
        .header("Authorization", format!("Bearer {}", &admin_token))
        .send()
        .await
        .map_err(|e| format!("Client lookup failed: {}", e))?;

    // Retry on 401: evict cached token and re-fetch
    if clients_resp.status().as_u16() == 401 {
        debug!("Admin token expired (401) — evicting cache and retrying");
        let cache_key = format!("admin:{}", keycloak_url);
        token_cache.invalidate(&cache_key);
        let fresh_token =
            fetch_admin_token(client, token_cache, keycloak_url, admin_password).await?;
        return patch_client_inner(
            client,
            keycloak_url,
            realm,
            &fresh_token,
            client_id_str,
            dcr_body,
        )
        .await;
    }

    let clients: Vec<Value> = clients_resp
        .json()
        .await
        .map_err(|e| format!("Parse clients: {}", e))?;

    let kc_client = clients
        .first()
        .ok_or_else(|| format!("Client '{}' not found in Keycloak", client_id_str))?;

    let internal_id = kc_client
        .get("id")
        .and_then(|v| v.as_str())
        .ok_or("Missing internal id")?;

    // 3. Patch: publicClient=true + PKCE S256
    let update_url = format!(
        "{}/admin/realms/{}/clients/{}",
        keycloak_url, realm, internal_id
    );

    let mut patch_body = kc_client.clone();
    if let Some(obj) = patch_body.as_object_mut() {
        obj.insert("publicClient".to_string(), json!(true));
        obj.remove("clientSecret");
        obj.remove("secret");

        // Set PKCE code challenge method
        let attrs = obj.entry("attributes").or_insert_with(|| json!({}));
        if let Some(attrs_obj) = attrs.as_object_mut() {
            attrs_obj.insert("pkce.code.challenge.method".to_string(), json!("S256"));
        }
    }

    let patch_resp = client
        .put(&update_url)
        .header("Authorization", format!("Bearer {}", &admin_token))
        .json(&patch_body)
        .send()
        .await
        .map_err(|e| format!("Client patch failed: {}", e))?;

    let patch_status = patch_resp.status();
    if !patch_status.is_success() {
        let body = patch_resp.text().await.unwrap_or_default();
        return Err(format!("Client patch returned {}: {}", patch_status, body));
    }

    Ok(())
}

/// Inner helper for client patching after token refresh (retry path).
async fn patch_client_inner(
    client: &reqwest::Client,
    keycloak_url: &str,
    realm: &str,
    admin_token: &str,
    client_id_str: &str,
    _dcr_body: &Value,
) -> Result<(), String> {
    let clients_url = format!(
        "{}/admin/realms/{}/clients?clientId={}",
        keycloak_url, realm, client_id_str
    );

    let clients_resp = client
        .get(&clients_url)
        .header("Authorization", format!("Bearer {}", admin_token))
        .send()
        .await
        .map_err(|e| format!("Client lookup failed (retry): {}", e))?;

    if !clients_resp.status().is_success() {
        let body = clients_resp.text().await.unwrap_or_default();
        return Err(format!("Client lookup failed on retry: {}", body));
    }

    let clients: Vec<Value> = clients_resp
        .json()
        .await
        .map_err(|e| format!("Parse clients (retry): {}", e))?;

    let kc_client = clients
        .first()
        .ok_or_else(|| format!("Client '{}' not found in Keycloak (retry)", client_id_str))?;

    let internal_id = kc_client
        .get("id")
        .and_then(|v| v.as_str())
        .ok_or("Missing internal id (retry)")?;

    let update_url = format!(
        "{}/admin/realms/{}/clients/{}",
        keycloak_url, realm, internal_id
    );

    let mut patch_body = kc_client.clone();
    if let Some(obj) = patch_body.as_object_mut() {
        obj.insert("publicClient".to_string(), json!(true));
        obj.remove("clientSecret");
        obj.remove("secret");

        let attrs = obj.entry("attributes").or_insert_with(|| json!({}));
        if let Some(attrs_obj) = attrs.as_object_mut() {
            attrs_obj.insert("pkce.code.challenge.method".to_string(), json!("S256"));
        }
    }

    let patch_resp = client
        .put(&update_url)
        .header("Authorization", format!("Bearer {}", admin_token))
        .json(&patch_body)
        .send()
        .await
        .map_err(|e| format!("Client patch failed (retry): {}", e))?;

    let patch_status = patch_resp.status();
    if !patch_status.is_success() {
        let body = patch_resp.text().await.unwrap_or_default();
        return Err(format!(
            "Client patch returned {} (retry): {}",
            patch_status, body
        ));
    }

    Ok(())
}

// ---------------------------------------------------------------------------
// RFC 7592 — Dynamic Client Registration Management Protocol (CAB-1606)
// ---------------------------------------------------------------------------

/// Build the Keycloak DCR management URL for a specific client.
fn dcr_client_url(keycloak_url: &str, realm: &str, client_id: &str) -> String {
    format!(
        "{}/realms/{}/clients-registrations/openid-connect/{}",
        keycloak_url.trim_end_matches('/'),
        realm,
        client_id,
    )
}

/// Extract and validate the Registration Access Token from the Authorization header.
/// Returns `Err(Response)` with a 401 if missing or malformed.
fn extract_rat(headers: &HeaderMap) -> Result<String, Box<Response>> {
    let auth = headers
        .get("authorization")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");

    if let Some(token) = auth.strip_prefix("Bearer ") {
        if !token.is_empty() {
            return Ok(token.to_string());
        }
    }

    Err(Box::new(
        (
            StatusCode::UNAUTHORIZED,
            Json(json!({
                "error": "invalid_token",
                "error_description": "Registration Access Token required (RFC 7592)"
            })),
        )
            .into_response(),
    ))
}

/// Return a 503 response when Keycloak is not configured.
fn keycloak_not_configured() -> Response {
    (
        StatusCode::SERVICE_UNAVAILABLE,
        Json(json!({
            "error": "server_error",
            "error_description": "Identity provider not configured"
        })),
    )
        .into_response()
}

/// GET /oauth/register/:client_id  (RFC 7592)
///
/// Read client metadata. The caller must present the Registration Access Token
/// (RAT) obtained during initial DCR registration.
pub async fn register_get_proxy(
    State(state): State<AppState>,
    axum::extract::Path(client_id): axum::extract::Path<String>,
    headers: HeaderMap,
) -> Response {
    let rat = match extract_rat(&headers) {
        Ok(t) => t,
        Err(resp) => return *resp,
    };

    let config = &state.config;
    let keycloak_url = match config.keycloak_backend_url() {
        Some(url) => url,
        None => return keycloak_not_configured(),
    };
    let realm = config.keycloak_realm.as_deref().unwrap_or("stoa");
    let url = dcr_client_url(keycloak_url, realm, &client_id);

    debug!(client_id = %client_id, "RFC 7592: reading client metadata");

    let client = state.http_client.clone();
    let via_value = build_via_value();

    let result = with_keycloak_resilience(&state.circuit_breakers, "oauth-register-get", || {
        let c = client.clone();
        let u = url.clone();
        let r = rat.clone();
        let via = via_value;
        async move {
            c.get(&u)
                .header("Authorization", format!("Bearer {}", r))
                .header("Via", via)
                .send()
                .await
                .map_err(|e| e.to_string())
        }
    })
    .await;

    forward_keycloak_json(result).await
}

/// PUT /oauth/register/:client_id  (RFC 7592)
///
/// Update client metadata. Applies the same scope-stripping logic as
/// POST /oauth/register to prevent Keycloak from replacing realm defaults.
pub async fn register_update_proxy(
    State(state): State<AppState>,
    axum::extract::Path(client_id): axum::extract::Path<String>,
    headers: HeaderMap,
    Json(payload): Json<Value>,
) -> Response {
    let rat = match extract_rat(&headers) {
        Ok(t) => t,
        Err(resp) => return *resp,
    };

    let config = &state.config;
    let keycloak_url = match config.keycloak_backend_url() {
        Some(url) => url,
        None => return keycloak_not_configured(),
    };
    let realm = config.keycloak_realm.as_deref().unwrap_or("stoa");
    let url = dcr_client_url(keycloak_url, realm, &client_id);

    // Strip `scope` — same rationale as POST /oauth/register (PR #541).
    let mut cleaned = payload;
    if let Some(obj) = cleaned.as_object_mut() {
        if obj.remove("scope").is_some() {
            debug!("Stripping 'scope' from client update payload (RFC 7592)");
        }
    }

    debug!(client_id = %client_id, "RFC 7592: updating client metadata");

    let client = state.http_client.clone();
    let via_value = build_via_value();

    let result = with_keycloak_resilience(&state.circuit_breakers, "oauth-register-update", || {
        let c = client.clone();
        let u = url.clone();
        let r = rat.clone();
        let p = cleaned.clone();
        let via = via_value;
        async move {
            c.put(&u)
                .header("Authorization", format!("Bearer {}", r))
                .header("content-type", "application/json")
                .header("Via", via)
                .json(&p)
                .send()
                .await
                .map_err(|e| e.to_string())
        }
    })
    .await;

    forward_keycloak_json(result).await
}

/// DELETE /oauth/register/:client_id  (RFC 7592)
///
/// Revoke/delete a dynamically registered client.
pub async fn register_delete_proxy(
    State(state): State<AppState>,
    axum::extract::Path(client_id): axum::extract::Path<String>,
    headers: HeaderMap,
) -> Response {
    let rat = match extract_rat(&headers) {
        Ok(t) => t,
        Err(resp) => return *resp,
    };

    let config = &state.config;
    let keycloak_url = match config.keycloak_backend_url() {
        Some(url) => url,
        None => return keycloak_not_configured(),
    };
    let realm = config.keycloak_realm.as_deref().unwrap_or("stoa");
    let url = dcr_client_url(keycloak_url, realm, &client_id);

    debug!(client_id = %client_id, "RFC 7592: deleting client");

    let client = state.http_client.clone();
    let via_value = build_via_value();

    let result = with_keycloak_resilience(&state.circuit_breakers, "oauth-register-delete", || {
        let c = client.clone();
        let u = url.clone();
        let r = rat.clone();
        let via = via_value;
        async move {
            c.delete(&u)
                .header("Authorization", format!("Bearer {}", r))
                .header("Via", via)
                .send()
                .await
                .map_err(|e| e.to_string())
        }
    })
    .await;

    match result {
        Ok(resp) => {
            let status = resp.status();
            // DELETE typically returns 204 No Content
            if status == reqwest::StatusCode::NO_CONTENT {
                StatusCode::NO_CONTENT.into_response()
            } else {
                forward_keycloak_json(Ok(resp)).await
            }
        }
        Err((status, msg)) => (
            status,
            Json(json!({"error": "server_error", "error_description": msg})),
        )
            .into_response(),
    }
}

/// Forward a Keycloak JSON response, preserving status code and body.
async fn forward_keycloak_json(
    result: Result<reqwest::Response, (StatusCode, String)>,
) -> Response {
    match result {
        Ok(resp) => {
            let status = resp.status();
            let body_bytes = resp.bytes().await.unwrap_or_default();
            let axum_status =
                StatusCode::from_u16(status.as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);

            if body_bytes.is_empty() {
                return axum_status.into_response();
            }

            match serde_json::from_slice::<Value>(&body_bytes) {
                Ok(json_body) => (axum_status, Json(json_body)).into_response(),
                Err(_) => {
                    let mut response = (axum_status, body_bytes).into_response();
                    if let Ok(ct) = "application/json".parse() {
                        response.headers_mut().insert("content-type", ct);
                    }
                    response
                }
            }
        }
        Err((status, msg)) => (
            status,
            Json(json!({"error": "server_error", "error_description": msg})),
        )
            .into_response(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::Config;
    use axum::{body::Body, http::Request, routing::post, Router};
    use tower::ServiceExt;
    use wiremock::matchers::{method, path};
    use wiremock::{Mock, MockServer, ResponseTemplate};

    fn test_state_with_keycloak(keycloak_url: Option<&str>) -> AppState {
        let config = Config {
            keycloak_url: keycloak_url.map(|s| s.to_string()),
            keycloak_realm: Some("stoa".to_string()),
            keycloak_admin_password: Some("admin-pass".to_string()),
            ..Config::default()
        };
        AppState::new(config)
    }

    fn build_oauth_router(state: AppState) -> Router {
        use axum::routing::get;
        Router::new()
            .route("/oauth/token", post(token_proxy))
            .route("/oauth/par", post(par_proxy))
            .route("/oauth/register", post(register_proxy))
            .route(
                "/oauth/register/:client_id",
                get(register_get_proxy)
                    .put(register_update_proxy)
                    .delete(register_delete_proxy),
            )
            .with_state(state)
    }

    // === token_proxy tests ===

    #[tokio::test]
    async fn test_token_proxy_no_keycloak_url() {
        let state = test_state_with_keycloak(None);
        let app = build_oauth_router(state);
        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/oauth/token")
                    .header("content-type", "application/x-www-form-urlencoded")
                    .body(Body::from("grant_type=client_credentials"))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let json: Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["error"], "server_error");
    }

    #[tokio::test]
    async fn test_token_proxy_success() {
        let mock_server = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/realms/stoa/protocol/openid-connect/token"))
            .respond_with(
                ResponseTemplate::new(200)
                    .set_body_json(json!({"access_token": "test-token", "token_type": "Bearer"})),
            )
            .mount(&mock_server)
            .await;

        let state = test_state_with_keycloak(Some(&mock_server.uri()));
        let app = build_oauth_router(state);
        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/oauth/token")
                    .header("content-type", "application/x-www-form-urlencoded")
                    .body(Body::from("grant_type=client_credentials&client_id=test"))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let json: Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["access_token"], "test-token");
    }

    #[tokio::test]
    async fn test_token_proxy_keycloak_error() {
        let mock_server = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/realms/stoa/protocol/openid-connect/token"))
            .respond_with(
                ResponseTemplate::new(401).set_body_json(json!({"error": "invalid_client"})),
            )
            .mount(&mock_server)
            .await;

        let state = test_state_with_keycloak(Some(&mock_server.uri()));
        let app = build_oauth_router(state);
        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/oauth/token")
                    .header("content-type", "application/x-www-form-urlencoded")
                    .body(Body::from("grant_type=client_credentials"))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn test_token_proxy_keycloak_unreachable() {
        // Point to a non-existent server
        let state = test_state_with_keycloak(Some("http://127.0.0.1:1"));
        let app = build_oauth_router(state);
        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/oauth/token")
                    .header("content-type", "application/x-www-form-urlencoded")
                    .body(Body::from("grant_type=client_credentials"))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::BAD_GATEWAY);
    }

    // === register_proxy tests ===

    #[tokio::test]
    async fn test_register_proxy_no_keycloak_url() {
        let state = test_state_with_keycloak(None);
        let app = build_oauth_router(state);
        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/oauth/register")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        serde_json::to_string(&json!({"client_name": "test"})).unwrap(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
    }

    #[tokio::test]
    async fn test_register_proxy_dcr_success() {
        let mock_server = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/realms/stoa/clients-registrations/openid-connect"))
            .respond_with(ResponseTemplate::new(201).set_body_json(json!({
                "client_id": "new-client-abc",
                "client_secret": "secret-123",
                "registration_access_token": "rat-xyz"
            })))
            .mount(&mock_server)
            .await;

        // Admin token for public client patch
        Mock::given(method("POST"))
            .and(path("/realms/master/protocol/openid-connect/token"))
            .respond_with(
                ResponseTemplate::new(200).set_body_json(json!({"access_token": "admin-jwt"})),
            )
            .mount(&mock_server)
            .await;

        // Client lookup
        Mock::given(method("GET"))
            .and(path("/admin/realms/stoa/clients"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!([{
                "id": "internal-uuid",
                "clientId": "new-client-abc"
            }])))
            .mount(&mock_server)
            .await;

        // Client update (PKCE patch)
        Mock::given(method("PUT"))
            .and(path("/admin/realms/stoa/clients/internal-uuid"))
            .respond_with(ResponseTemplate::new(204))
            .mount(&mock_server)
            .await;

        let state = test_state_with_keycloak(Some(&mock_server.uri()));
        let app = build_oauth_router(state);
        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/oauth/register")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        serde_json::to_string(&json!({"client_name": "claude-mcp"})).unwrap(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::CREATED);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let json: Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["client_id"], "new-client-abc");
    }

    #[tokio::test]
    async fn test_register_proxy_dcr_keycloak_error() {
        let mock_server = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/realms/stoa/clients-registrations/openid-connect"))
            .respond_with(ResponseTemplate::new(403).set_body_json(json!({
                "error": "forbidden",
                "error_description": "DCR disabled"
            })))
            .mount(&mock_server)
            .await;

        let state = test_state_with_keycloak(Some(&mock_server.uri()));
        let app = build_oauth_router(state);
        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/oauth/register")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        serde_json::to_string(&json!({"client_name": "test"})).unwrap(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::FORBIDDEN);
    }

    /// Verify that the `scope` field is stripped from DCR payload before forwarding to Keycloak.
    ///
    /// When Claude.ai sends `scope: "openid profile stoa:read..."` in DCR,
    /// Keycloak REPLACES all realm defaults with ONLY those scopes —
    /// losing profile, email, roles, etc. Stripping scope preserves Keycloak defaults.
    /// Regression guard for PR #541 (CAB-1094).
    #[tokio::test]
    async fn test_register_proxy_strips_scope_from_dcr_payload() {
        let mock_server = MockServer::start().await;

        // DCR endpoint — we'll inspect the request body it receives
        Mock::given(method("POST"))
            .and(path("/realms/stoa/clients-registrations/openid-connect"))
            .respond_with(ResponseTemplate::new(201).set_body_json(json!({
                "client_id": "scope-test-client",
                "client_secret": "secret",
                "registration_access_token": "rat"
            })))
            .expect(1)
            .mount(&mock_server)
            .await;

        // Admin token for public client patch
        Mock::given(method("POST"))
            .and(path("/realms/master/protocol/openid-connect/token"))
            .respond_with(
                ResponseTemplate::new(200).set_body_json(json!({"access_token": "admin-jwt"})),
            )
            .mount(&mock_server)
            .await;

        Mock::given(method("GET"))
            .and(path("/admin/realms/stoa/clients"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!([{
                "id": "internal-uuid",
                "clientId": "scope-test-client"
            }])))
            .mount(&mock_server)
            .await;

        Mock::given(method("PUT"))
            .and(path("/admin/realms/stoa/clients/internal-uuid"))
            .respond_with(ResponseTemplate::new(204))
            .mount(&mock_server)
            .await;

        let state = test_state_with_keycloak(Some(&mock_server.uri()));
        let app = build_oauth_router(state);

        // Send DCR with scope field (as Claude.ai does)
        let payload = json!({
            "client_name": "claude-mcp-test",
            "redirect_uris": ["https://claude.ai/oauth/callback"],
            "grant_types": ["authorization_code"],
            "scope": "openid profile email stoa:read stoa:write"
        });

        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/oauth/register")
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_string(&payload).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::CREATED);

        // Verify the scope field was stripped from the forwarded request
        let requests = mock_server.received_requests().await.unwrap();
        let dcr_request = requests
            .iter()
            .find(|r| r.url.path() == "/realms/stoa/clients-registrations/openid-connect")
            .expect("DCR request should have been sent");

        let forwarded_body: Value =
            serde_json::from_slice(&dcr_request.body).expect("DCR body should be valid JSON");

        assert!(
            forwarded_body.get("scope").is_none(),
            "scope field must be stripped from DCR payload (PR #541 regression)"
        );
        // Other fields must be preserved
        assert_eq!(forwarded_body["client_name"], "claude-mcp-test");
        assert!(forwarded_body["redirect_uris"].is_array());
    }

    /// Verify that DCR payloads without `scope` are forwarded unchanged.
    #[tokio::test]
    async fn test_register_proxy_preserves_payload_without_scope() {
        let mock_server = MockServer::start().await;

        Mock::given(method("POST"))
            .and(path("/realms/stoa/clients-registrations/openid-connect"))
            .respond_with(ResponseTemplate::new(201).set_body_json(json!({
                "client_id": "no-scope-client",
                "registration_access_token": "rat"
            })))
            .expect(1)
            .mount(&mock_server)
            .await;

        Mock::given(method("POST"))
            .and(path("/realms/master/protocol/openid-connect/token"))
            .respond_with(
                ResponseTemplate::new(200).set_body_json(json!({"access_token": "admin-jwt"})),
            )
            .mount(&mock_server)
            .await;

        Mock::given(method("GET"))
            .and(path("/admin/realms/stoa/clients"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!([{
                "id": "internal-uuid-2",
                "clientId": "no-scope-client"
            }])))
            .mount(&mock_server)
            .await;

        Mock::given(method("PUT"))
            .and(path("/admin/realms/stoa/clients/internal-uuid-2"))
            .respond_with(ResponseTemplate::new(204))
            .mount(&mock_server)
            .await;

        let state = test_state_with_keycloak(Some(&mock_server.uri()));
        let app = build_oauth_router(state);

        // Send DCR WITHOUT scope field
        let payload = json!({
            "client_name": "normal-client",
            "redirect_uris": ["https://example.com/callback"],
            "grant_types": ["authorization_code"],
            "token_endpoint_auth_method": "none"
        });

        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/oauth/register")
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_string(&payload).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::CREATED);

        // Verify the payload was forwarded with all original fields intact
        let requests = mock_server.received_requests().await.unwrap();
        let dcr_request = requests
            .iter()
            .find(|r| r.url.path() == "/realms/stoa/clients-registrations/openid-connect")
            .expect("DCR request should have been sent");

        let forwarded_body: Value = serde_json::from_slice(&dcr_request.body).unwrap();
        assert_eq!(forwarded_body["client_name"], "normal-client");
        assert_eq!(forwarded_body["token_endpoint_auth_method"], "none");
        assert!(forwarded_body.get("scope").is_none());
    }

    #[tokio::test]
    async fn test_register_proxy_keycloak_unreachable() {
        let state = test_state_with_keycloak(Some("http://127.0.0.1:1"));
        let app = build_oauth_router(state);
        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/oauth/register")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        serde_json::to_string(&json!({"client_name": "test"})).unwrap(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::BAD_GATEWAY);
    }

    // === RFC 7592 — Client Management tests (CAB-1606) ===

    #[tokio::test]
    async fn test_rfc7592_get_client_success() {
        let mock_server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path(
                "/realms/stoa/clients-registrations/openid-connect/my-client",
            ))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({
                "client_id": "my-client",
                "client_name": "My App",
                "redirect_uris": ["https://app.example.com/callback"]
            })))
            .expect(1)
            .mount(&mock_server)
            .await;

        let state = test_state_with_keycloak(Some(&mock_server.uri()));
        let app = build_oauth_router(state);
        let response = app
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/oauth/register/my-client")
                    .header("Authorization", "Bearer rat-valid-token")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let json: Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["client_id"], "my-client");
        assert_eq!(json["client_name"], "My App");
    }

    #[tokio::test]
    async fn test_rfc7592_get_client_missing_rat() {
        let state = test_state_with_keycloak(Some("http://127.0.0.1:9999"));
        let app = build_oauth_router(state);
        let response = app
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/oauth/register/my-client")
                    // No Authorization header
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let json: Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["error"], "invalid_token");
    }

    #[tokio::test]
    async fn test_rfc7592_get_client_not_found() {
        let mock_server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path(
                "/realms/stoa/clients-registrations/openid-connect/nonexistent",
            ))
            .respond_with(ResponseTemplate::new(404).set_body_json(
                json!({"error": "invalid_client", "error_description": "Client not found"}),
            ))
            .mount(&mock_server)
            .await;

        let state = test_state_with_keycloak(Some(&mock_server.uri()));
        let app = build_oauth_router(state);
        let response = app
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/oauth/register/nonexistent")
                    .header("Authorization", "Bearer rat-some-token")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn test_rfc7592_get_client_invalid_rat() {
        let mock_server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path(
                "/realms/stoa/clients-registrations/openid-connect/my-client",
            ))
            .respond_with(
                ResponseTemplate::new(401).set_body_json(json!({"error": "unauthorized_client"})),
            )
            .mount(&mock_server)
            .await;

        let state = test_state_with_keycloak(Some(&mock_server.uri()));
        let app = build_oauth_router(state);
        let response = app
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/oauth/register/my-client")
                    .header("Authorization", "Bearer wrong-rat")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn test_rfc7592_update_client_success() {
        let mock_server = MockServer::start().await;
        Mock::given(method("PUT"))
            .and(path(
                "/realms/stoa/clients-registrations/openid-connect/my-client",
            ))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({
                "client_id": "my-client",
                "client_name": "Updated App",
                "redirect_uris": ["https://new.example.com/callback"]
            })))
            .expect(1)
            .mount(&mock_server)
            .await;

        let state = test_state_with_keycloak(Some(&mock_server.uri()));
        let app = build_oauth_router(state);
        let response = app
            .oneshot(
                Request::builder()
                    .method("PUT")
                    .uri("/oauth/register/my-client")
                    .header("Authorization", "Bearer rat-valid-token")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        serde_json::to_string(&json!({
                            "client_name": "Updated App",
                            "redirect_uris": ["https://new.example.com/callback"]
                        }))
                        .unwrap(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let json: Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["client_name"], "Updated App");
    }

    /// Verify scope stripping on PUT (same protection as POST — PR #541 regression guard).
    #[tokio::test]
    async fn test_rfc7592_update_strips_scope() {
        let mock_server = MockServer::start().await;
        Mock::given(method("PUT"))
            .and(path(
                "/realms/stoa/clients-registrations/openid-connect/scope-client",
            ))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({
                "client_id": "scope-client",
                "client_name": "Scope Test"
            })))
            .expect(1)
            .mount(&mock_server)
            .await;

        let state = test_state_with_keycloak(Some(&mock_server.uri()));
        let app = build_oauth_router(state);
        let response = app
            .oneshot(
                Request::builder()
                    .method("PUT")
                    .uri("/oauth/register/scope-client")
                    .header("Authorization", "Bearer rat-valid")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        serde_json::to_string(&json!({
                            "client_name": "Scope Test",
                            "scope": "openid profile stoa:read stoa:write"
                        }))
                        .unwrap(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);

        // Verify scope was stripped from the forwarded request
        let requests = mock_server.received_requests().await.unwrap();
        let update_req = requests
            .iter()
            .find(|r| r.method == wiremock::http::Method::PUT)
            .expect("PUT request should have been sent");
        let forwarded: Value = serde_json::from_slice(&update_req.body).unwrap();
        assert!(
            forwarded.get("scope").is_none(),
            "scope must be stripped from PUT payload (RFC 7592)"
        );
        assert_eq!(forwarded["client_name"], "Scope Test");
    }

    #[tokio::test]
    async fn test_rfc7592_delete_client_success() {
        let mock_server = MockServer::start().await;
        Mock::given(method("DELETE"))
            .and(path(
                "/realms/stoa/clients-registrations/openid-connect/my-client",
            ))
            .respond_with(ResponseTemplate::new(204))
            .expect(1)
            .mount(&mock_server)
            .await;

        let state = test_state_with_keycloak(Some(&mock_server.uri()));
        let app = build_oauth_router(state);
        let response = app
            .oneshot(
                Request::builder()
                    .method("DELETE")
                    .uri("/oauth/register/my-client")
                    .header("Authorization", "Bearer rat-valid-token")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::NO_CONTENT);
    }

    #[tokio::test]
    async fn test_rfc7592_delete_client_not_found() {
        let mock_server = MockServer::start().await;
        Mock::given(method("DELETE"))
            .and(path(
                "/realms/stoa/clients-registrations/openid-connect/nonexistent",
            ))
            .respond_with(
                ResponseTemplate::new(404).set_body_json(json!({"error": "invalid_client"})),
            )
            .mount(&mock_server)
            .await;

        let state = test_state_with_keycloak(Some(&mock_server.uri()));
        let app = build_oauth_router(state);
        let response = app
            .oneshot(
                Request::builder()
                    .method("DELETE")
                    .uri("/oauth/register/nonexistent")
                    .header("Authorization", "Bearer rat-some-token")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn test_rfc7592_no_keycloak_configured() {
        let state = test_state_with_keycloak(None);
        let app = build_oauth_router(state);

        // GET
        let response = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/oauth/register/any-client")
                    .header("Authorization", "Bearer rat")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);

        // DELETE
        let response = app
            .oneshot(
                Request::builder()
                    .method("DELETE")
                    .uri("/oauth/register/any-client")
                    .header("Authorization", "Bearer rat")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
    }

    // === par_proxy tests (RFC 9126, CAB-1733) ===

    #[tokio::test]
    async fn test_par_proxy_no_keycloak_url() {
        let state = test_state_with_keycloak(None);
        let app = build_oauth_router(state);
        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/oauth/par")
                    .header("content-type", "application/x-www-form-urlencoded")
                    .body(Body::from(
                        "client_id=test&response_type=code&redirect_uri=http://localhost/cb",
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let json: Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["error"], "server_error");
    }

    #[tokio::test]
    async fn test_par_proxy_success() {
        let mock_server = MockServer::start().await;

        // Keycloak returns a PAR response with request_uri
        Mock::given(method("POST"))
            .and(path("/realms/stoa/protocol/openid-connect/ext/par/request"))
            .respond_with(ResponseTemplate::new(201).set_body_json(json!({
                "request_uri": "urn:ietf:params:oauth:request_uri:abc123",
                "expires_in": 60
            })))
            .mount(&mock_server)
            .await;

        let state = test_state_with_keycloak(Some(&mock_server.uri()));
        let app = build_oauth_router(state);
        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/oauth/par")
                    .header("content-type", "application/x-www-form-urlencoded")
                    .body(Body::from(
                        "client_id=test&response_type=code&redirect_uri=http://localhost/cb&code_challenge=abc&code_challenge_method=S256",
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::CREATED);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let json: Value = serde_json::from_slice(&body).unwrap();
        assert!(json["request_uri"]
            .as_str()
            .unwrap()
            .starts_with("urn:ietf:params:oauth:request_uri:"));
        assert_eq!(json["expires_in"], 60);
    }

    #[tokio::test]
    async fn test_par_proxy_forwards_content_type() {
        let mock_server = MockServer::start().await;

        Mock::given(method("POST"))
            .and(path("/realms/stoa/protocol/openid-connect/ext/par/request"))
            .respond_with(ResponseTemplate::new(400).set_body_json(json!({
                "error": "invalid_request",
                "error_description": "Missing required parameter"
            })))
            .mount(&mock_server)
            .await;

        let state = test_state_with_keycloak(Some(&mock_server.uri()));
        let app = build_oauth_router(state);
        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/oauth/par")
                    .header("content-type", "application/x-www-form-urlencoded")
                    .body(Body::from("client_id=test"))
                    .unwrap(),
            )
            .await
            .unwrap();
        // PAR returns 400 for invalid requests — proxy passes it through
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    // === client_assertion (RFC 7523) in token_proxy tests ===

    #[tokio::test]
    async fn test_token_proxy_rejects_invalid_assertion_type() {
        let state = test_state_with_keycloak(Some("http://127.0.0.1:1"));
        let app = build_oauth_router(state);
        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/oauth/token")
                    .header("content-type", "application/x-www-form-urlencoded")
                    .body(Body::from(
                        "grant_type=authorization_code&client_assertion_type=wrong&client_assertion=eyJ.test.jwt"
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let json: Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["error"], "invalid_client");
    }

    #[tokio::test]
    async fn test_token_proxy_rejects_assertion_without_type() {
        let state = test_state_with_keycloak(Some("http://127.0.0.1:1"));
        let app = build_oauth_router(state);
        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/oauth/token")
                    .header("content-type", "application/x-www-form-urlencoded")
                    .body(Body::from(
                        "grant_type=authorization_code&client_assertion=eyJ.test.jwt",
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn test_token_proxy_forwards_valid_assertion_to_keycloak() {
        let mock_server = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/realms/stoa/protocol/openid-connect/token"))
            .respond_with(
                ResponseTemplate::new(200)
                    .set_body_json(json!({"access_token": "fapi-token", "token_type": "Bearer"})),
            )
            .mount(&mock_server)
            .await;

        let state = test_state_with_keycloak(Some(&mock_server.uri()));
        let app = build_oauth_router(state);

        // Valid assertion type + assertion — should be forwarded to KC
        let body = format!(
            "grant_type=authorization_code&client_id=fapi-client&client_assertion_type={}&client_assertion=eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3QifQ.eyJpc3MiOiJmYXBpLWNsaWVudCIsInN1YiI6ImZhcGktY2xpZW50IiwiYXVkIjoiaHR0cHM6Ly9tY3AuZ29zdG9hLmRldi9vYXV0aC90b2tlbiIsImV4cCI6OTk5OTk5OTk5OSwianRpIjoidW5pcXVlLWlkIn0.fake-signature",
            super::client_auth::JWT_BEARER_ASSERTION_TYPE
        );

        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/oauth/token")
                    .header("content-type", "application/x-www-form-urlencoded")
                    .body(Body::from(body))
                    .unwrap(),
            )
            .await
            .unwrap();

        // Gateway forwards to KC (format is valid, KC does signature check)
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let json: Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["access_token"], "fapi-token");
    }
}
