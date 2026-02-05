//! OAuth Discovery Endpoints
//!
//! CAB-1094: Well-known discovery endpoints for OAuth 2.1 / OIDC.
//!
//! - GET /.well-known/oauth-protected-resource (RFC 9728)
//! - GET /.well-known/oauth-authorization-server (RFC 8414)
//! - GET /.well-known/openid-configuration (OIDC Discovery proxy)

use axum::{extract::State, http::StatusCode, Json};
use serde_json::{json, Value};
use tracing::{debug, warn};

use crate::state::AppState;

/// GET /.well-known/oauth-protected-resource
///
/// RFC 9728 — tells clients (e.g. Claude.ai) where to authenticate.
pub async fn protected_resource_metadata(
    State(state): State<AppState>,
) -> Json<Value> {
    let config = &state.config;

    let gateway_url = config
        .gateway_external_url
        .as_deref()
        .unwrap_or("http://localhost:8080");

    let keycloak_url = config.keycloak_url.as_deref().unwrap_or("");
    let realm = config.keycloak_realm.as_deref().unwrap_or("stoa");
    let issuer = format!("{}/realms/{}", keycloak_url.trim_end_matches('/'), realm);

    debug!(resource = %gateway_url, issuer = %issuer, "Serving protected resource metadata");

    Json(json!({
        "resource": gateway_url,
        "authorization_servers": [issuer],
        "scopes_supported": [
            "openid",
            "profile",
            "email",
            "stoa:read",
            "stoa:write",
            "stoa:admin"
        ],
        "bearer_methods_supported": ["header"]
    }))
}

/// GET /.well-known/oauth-authorization-server
///
/// RFC 8414 — authorization server metadata.
/// token_endpoint and registration_endpoint point to the gateway (proxy),
/// authorization_endpoint points to Keycloak (browser-facing).
pub async fn authorization_server_metadata(
    State(state): State<AppState>,
) -> Json<Value> {
    let config = &state.config;

    let gateway_url = config
        .gateway_external_url
        .as_deref()
        .unwrap_or("http://localhost:8080");
    let gateway_url = gateway_url.trim_end_matches('/');

    let keycloak_url = config.keycloak_url.as_deref().unwrap_or("");
    let realm = config.keycloak_realm.as_deref().unwrap_or("stoa");
    let kc_base = format!(
        "{}/realms/{}",
        keycloak_url.trim_end_matches('/'),
        realm
    );

    debug!(
        issuer = %kc_base,
        token_endpoint = %format!("{}/oauth/token", gateway_url),
        "Serving authorization server metadata"
    );

    Json(json!({
        "issuer": kc_base,
        "authorization_endpoint": format!("{}/protocol/openid-connect/auth", kc_base),
        "token_endpoint": format!("{}/oauth/token", gateway_url),
        "registration_endpoint": format!("{}/oauth/register", gateway_url),
        "jwks_uri": format!("{}/protocol/openid-connect/certs", kc_base),
        "scopes_supported": [
            "openid",
            "profile",
            "email",
            "stoa:read",
            "stoa:write",
            "stoa:admin"
        ],
        "response_types_supported": ["code"],
        "grant_types_supported": [
            "authorization_code",
            "client_credentials",
            "refresh_token"
        ],
        "token_endpoint_auth_methods_supported": [
            "none",
            "client_secret_basic",
            "client_secret_post"
        ],
        "code_challenge_methods_supported": ["S256"],
        "subject_types_supported": ["public"]
    }))
}

/// GET /.well-known/openid-configuration
///
/// OIDC Discovery — proxy Keycloak's config with overridden token/registration endpoints.
pub async fn openid_configuration(
    State(state): State<AppState>,
) -> Result<Json<Value>, StatusCode> {
    let config = &state.config;

    let gateway_url = config
        .gateway_external_url
        .as_deref()
        .unwrap_or("http://localhost:8080");
    let gateway_url = gateway_url.trim_end_matches('/');

    let keycloak_url = match config.keycloak_url.as_deref() {
        Some(url) => url.trim_end_matches('/'),
        None => {
            warn!("Keycloak URL not configured — cannot serve OIDC discovery");
            return Err(StatusCode::SERVICE_UNAVAILABLE);
        }
    };
    let realm = config.keycloak_realm.as_deref().unwrap_or("stoa");
    let discovery_url = format!(
        "{}/realms/{}/.well-known/openid-configuration",
        keycloak_url, realm
    );

    debug!(url = %discovery_url, "Proxying OIDC discovery from Keycloak");

    // Fetch from Keycloak
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(10))
        .build()
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

    let resp = client
        .get(&discovery_url)
        .send()
        .await
        .map_err(|e| {
            warn!(error = %e, "Failed to fetch Keycloak OIDC config");
            StatusCode::BAD_GATEWAY
        })?;

    if !resp.status().is_success() {
        warn!(status = %resp.status(), "Keycloak OIDC config returned error");
        return Err(StatusCode::BAD_GATEWAY);
    }

    let mut oidc_config: Value = resp.json().await.map_err(|e| {
        warn!(error = %e, "Failed to parse Keycloak OIDC config");
        StatusCode::BAD_GATEWAY
    })?;

    // Override token and registration endpoints to point to gateway proxy
    if let Some(obj) = oidc_config.as_object_mut() {
        obj.insert(
            "token_endpoint".to_string(),
            json!(format!("{}/oauth/token", gateway_url)),
        );
        obj.insert(
            "registration_endpoint".to_string(),
            json!(format!("{}/oauth/register", gateway_url)),
        );
    }

    Ok(Json(oidc_config))
}
