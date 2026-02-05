//! OAuth Token + DCR Proxy
//!
//! CAB-1094: Proxy OAuth endpoints to Keycloak for Claude.ai MCP connector.
//!
//! - POST /oauth/token — transparent proxy to Keycloak token endpoint
//! - POST /oauth/register — DCR proxy + public client patch for PKCE

use axum::{
    body::Bytes,
    extract::State,
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};
use tracing::{debug, error, info, warn};

use crate::state::AppState;

/// POST /oauth/token
///
/// Transparent proxy to Keycloak token endpoint.
/// Forwards body as-is, returns Keycloak response as-is.
pub async fn token_proxy(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    let config = &state.config;

    let keycloak_url = match config.keycloak_url.as_deref() {
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

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .build()
        .unwrap();

    // Forward content-type from original request (axum HeaderMap uses http 1.x)
    let content_type = headers
        .get("content-type")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("application/x-www-form-urlencoded");

    let resp = match client
        .post(&token_url)
        .header("content-type", content_type)
        .body(body.to_vec())
        .send()
        .await
    {
        Ok(r) => r,
        Err(e) => {
            error!(error = %e, "Failed to proxy token request to Keycloak");
            return (
                StatusCode::BAD_GATEWAY,
                Json(json!({"error": "server_error", "error_description": "Identity provider unreachable"})),
            )
                .into_response();
        }
    };

    let status = StatusCode::from_u16(resp.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);

    // Extract content-type from reqwest response before consuming body
    let resp_content_type = resp
        .headers()
        .get("content-type")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("application/json")
        .to_string();

    let body = resp.bytes().await.unwrap_or_default();

    // Build axum response
    let mut response = (status, body).into_response();
    if let Ok(ct_val) = resp_content_type.parse() {
        response
            .headers_mut()
            .insert("content-type", ct_val);
    }

    response
}

/// POST /oauth/register
///
/// Dynamic Client Registration proxy to Keycloak.
/// After registration, patches the client to be public (no client_secret)
/// with S256 PKCE support — required for Claude.ai PKCE flow.
pub async fn register_proxy(
    State(state): State<AppState>,
    Json(payload): Json<Value>,
) -> Response {
    let config = &state.config;

    let keycloak_url = match config.keycloak_url.as_deref() {
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

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .build()
        .unwrap();

    // Step 1: Forward DCR to Keycloak
    let dcr_resp = match client
        .post(&dcr_url)
        .header("content-type", "application/json")
        .json(&payload)
        .send()
        .await
    {
        Ok(r) => r,
        Err(e) => {
            error!(error = %e, "Failed to proxy DCR request to Keycloak");
            return (
                StatusCode::BAD_GATEWAY,
                Json(json!({"error": "server_error", "error_description": "Identity provider unreachable"})),
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
        let status =
            StatusCode::from_u16(dcr_status_code).unwrap_or(StatusCode::BAD_GATEWAY);
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
    let status =
        StatusCode::from_u16(dcr_status_code).unwrap_or(StatusCode::CREATED);
    (status, Json(dcr_body)).into_response()
}

/// Patch a Keycloak client to be public (no client_secret) with PKCE S256.
///
/// Steps:
/// 1. Get admin token via Resource Owner Password Grant
/// 2. Find the client by clientId
/// 3. PUT client config with publicClient=true + pkce.code.challenge.method=S256
async fn patch_public_client(
    client: &reqwest::Client,
    keycloak_url: &str,
    realm: &str,
    admin_password: &str,
    dcr_body: &Value,
) -> Result<(), String> {
    let client_id_str = dcr_body
        .get("client_id")
        .and_then(|v| v.as_str())
        .ok_or("Missing client_id in DCR response")?;

    // 1. Get admin token
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
    let admin_token = token_data
        .get("access_token")
        .and_then(|v| v.as_str())
        .ok_or("Missing access_token in admin response")?;

    // 2. Find client by clientId
    let clients_url = format!(
        "{}/admin/realms/{}/clients?clientId={}",
        keycloak_url, realm, client_id_str
    );

    let clients_resp = client
        .get(&clients_url)
        .header("Authorization", format!("Bearer {}", admin_token))
        .send()
        .await
        .map_err(|e| format!("Client lookup failed: {}", e))?;

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
        let attrs = obj
            .entry("attributes")
            .or_insert_with(|| json!({}));
        if let Some(attrs_obj) = attrs.as_object_mut() {
            attrs_obj.insert(
                "pkce.code.challenge.method".to_string(),
                json!("S256"),
            );
        }
    }

    let patch_resp = client
        .put(&update_url)
        .header("Authorization", format!("Bearer {}", admin_token))
        .json(&patch_body)
        .send()
        .await
        .map_err(|e| format!("Client patch failed: {}", e))?;

    let patch_status = patch_resp.status();
    if !patch_status.is_success() {
        let body = patch_resp.text().await.unwrap_or_default();
        return Err(format!(
            "Client patch returned {}: {}",
            patch_status, body
        ));
    }

    Ok(())
}
