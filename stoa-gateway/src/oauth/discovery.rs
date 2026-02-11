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
pub async fn protected_resource_metadata(State(state): State<AppState>) -> Json<Value> {
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
pub async fn authorization_server_metadata(State(state): State<AppState>) -> Json<Value> {
    let config = &state.config;

    let gateway_url = config
        .gateway_external_url
        .as_deref()
        .unwrap_or("http://localhost:8080");
    let gateway_url = gateway_url.trim_end_matches('/');

    let keycloak_url = config.keycloak_url.as_deref().unwrap_or("");
    let realm = config.keycloak_realm.as_deref().unwrap_or("stoa");
    let kc_base = format!("{}/realms/{}", keycloak_url.trim_end_matches('/'), realm);

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

    let resp = client.get(&discovery_url).send().await.map_err(|e| {
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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::Config;

    fn test_state(keycloak_url: Option<&str>, gateway_url: Option<&str>) -> AppState {
        let config = Config {
            keycloak_url: keycloak_url.map(|s| s.to_string()),
            keycloak_realm: Some("test-realm".to_string()),
            gateway_external_url: gateway_url.map(|s| s.to_string()),
            ..Config::default()
        };
        AppState::new(config)
    }

    #[tokio::test]
    async fn test_protected_resource_metadata_defaults() {
        let state = test_state(None, None);
        let Json(meta) = protected_resource_metadata(State(state)).await;
        assert_eq!(meta["resource"], "http://localhost:8080");
        assert!(meta["authorization_servers"].is_array());
        assert!(meta["scopes_supported"].is_array());
        assert_eq!(meta["bearer_methods_supported"][0], "header");
    }

    #[tokio::test]
    async fn test_protected_resource_metadata_custom_urls() {
        let state = test_state(
            Some("https://auth.gostoa.dev"),
            Some("https://mcp.gostoa.dev"),
        );
        let Json(meta) = protected_resource_metadata(State(state)).await;
        assert_eq!(meta["resource"], "https://mcp.gostoa.dev");
        assert_eq!(
            meta["authorization_servers"][0],
            "https://auth.gostoa.dev/realms/test-realm"
        );
    }

    #[tokio::test]
    async fn test_authorization_server_metadata_defaults() {
        let state = test_state(None, None);
        let Json(meta) = authorization_server_metadata(State(state)).await;
        assert_eq!(meta["token_endpoint"], "http://localhost:8080/oauth/token");
        assert_eq!(
            meta["registration_endpoint"],
            "http://localhost:8080/oauth/register"
        );
        assert!(meta["scopes_supported"].is_array());
        assert!(meta["grant_types_supported"].is_array());
    }

    #[tokio::test]
    async fn test_authorization_server_metadata_custom_urls() {
        let state = test_state(
            Some("https://auth.gostoa.dev"),
            Some("https://mcp.gostoa.dev"),
        );
        let Json(meta) = authorization_server_metadata(State(state)).await;
        assert_eq!(meta["issuer"], "https://auth.gostoa.dev/realms/test-realm");
        assert_eq!(meta["token_endpoint"], "https://mcp.gostoa.dev/oauth/token");
        assert_eq!(
            meta["authorization_endpoint"],
            "https://auth.gostoa.dev/realms/test-realm/protocol/openid-connect/auth"
        );
        assert_eq!(
            meta["jwks_uri"],
            "https://auth.gostoa.dev/realms/test-realm/protocol/openid-connect/certs"
        );
    }

    #[tokio::test]
    async fn test_authorization_server_metadata_has_required_fields() {
        let state = test_state(Some("https://kc.test"), Some("https://gw.test"));
        let Json(meta) = authorization_server_metadata(State(state)).await;
        // RFC 8414 required fields
        assert!(meta.get("issuer").is_some());
        assert!(meta.get("authorization_endpoint").is_some());
        assert!(meta.get("token_endpoint").is_some());
        assert!(meta.get("response_types_supported").is_some());
        assert_eq!(meta["response_types_supported"][0], "code");
        assert_eq!(meta["code_challenge_methods_supported"][0], "S256");
        assert_eq!(meta["subject_types_supported"][0], "public");
    }

    #[tokio::test]
    async fn test_openid_configuration_no_keycloak_returns_503() {
        let state = test_state(None, None);
        let result = openid_configuration(State(state)).await;
        assert!(result.is_err());
        assert_eq!(result.unwrap_err(), StatusCode::SERVICE_UNAVAILABLE);
    }
}
