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

/// An MCP endpoint a client can be configured with. Each one is a protected
/// resource of its own (RFC 9728 §3.1): its metadata document carries the
/// endpoint URL in `resource`, and a client compares that value with the URL
/// it was given, path included.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum McpEndpoint {
    /// `POST /mcp`, Streamable HTTP. Also stands for the REST routes under
    /// `/mcp/`, which are not endpoints a client is configured with.
    StreamableHttp,
    /// `/mcp/sse`, the older SSE transport.
    Sse,
}

impl McpEndpoint {
    /// Path of the endpoint, as it follows the gateway base URL.
    pub fn path(self) -> &'static str {
        match self {
            McpEndpoint::StreamableHttp => "/mcp",
            McpEndpoint::Sse => "/mcp/sse",
        }
    }
}

/// Base URL of the documents and of the challenge. A blank value counts as
/// unset; `Config::validate` refuses anything else that is not a URL.
fn external_base(config: &crate::config::Config) -> &str {
    config
        .gateway_external_url
        .as_deref()
        .map(str::trim)
        .filter(|url| !url.is_empty())
        .unwrap_or("http://localhost:8080")
        .trim_end_matches('/')
}

/// `authorization_servers` of the protected resource metadata (RFC 9728):
/// the configured issuers, or the gateway itself when none is configured.
///
/// A client fetches the metadata of the first entry and checks that its
/// `issuer` is that entry (RFC 8414 §3.3). The gateway's own document
/// (`/.well-known/oauth-authorization-server`) carries the realm as issuer
/// and the gateway's OAuth proxy as token endpoint: it suits clients that
/// do not make that check, and needs `/oauth/...` to be reachable by them.
fn authorization_servers(config: &crate::config::Config) -> Vec<String> {
    if config.oauth_authorization_servers.is_empty() {
        vec![external_base(config).to_string()]
    } else {
        config.oauth_authorization_servers.clone()
    }
}

/// `WWW-Authenticate` value for a 401 on an MCP route (RFC 9728 §5.1).
///
/// `resource_metadata` is the absolute URL of the protected resource
/// metadata of `endpoint`, built from `gateway_external_url`: a client
/// fetches it as is, and a relative reference is not a URL it can request.
pub fn bearer_challenge(
    config: &crate::config::Config,
    endpoint: McpEndpoint,
    error: Option<&str>,
) -> String {
    let base = external_base(config);
    let metadata = format!(
        "{base}/.well-known/oauth-protected-resource{}",
        endpoint.path()
    );
    match error {
        Some(error) => format!(r#"Bearer error="{error}", resource_metadata="{metadata}""#),
        None => format!(r#"Bearer resource_metadata="{metadata}""#),
    }
}

/// GET /.well-known/oauth-protected-resource
///
/// RFC 9728 — tells clients (e.g. Claude.ai) where to authenticate.
pub async fn protected_resource_metadata(State(state): State<AppState>) -> Json<Value> {
    let config = &state.config;

    let gateway_url = config
        .gateway_external_url
        .as_deref()
        .unwrap_or("http://localhost:8080");

    // RFC 9728: authorization_servers MUST point to where the client can discover
    // OAuth metadata. Unless `oauth_authorization_servers` names the issuer,
    // we point to the gateway itself (not Keycloak) because:
    // 1. Gateway serves curated metadata with token_endpoint_auth_methods: ["none"] (public clients)
    // 2. Gateway proxies token/register endpoints (adding PKCE, Trusted Hosts bypass, etc.)
    // 3. Keycloak's metadata doesn't advertise "none" auth method, breaking public MCP clients
    let authorization_servers = authorization_servers(config);

    debug!(resource = %gateway_url, authorization_servers = ?authorization_servers, "Serving protected resource metadata");

    Json(json!({
        "resource": gateway_url,
        "authorization_servers": authorization_servers,
        "scopes_supported": config.oauth_scopes_supported,
        "bearer_methods_supported": ["header"]
    }))
}

/// GET /.well-known/oauth-protected-resource/mcp
///
/// RFC 9728 §3.1 — metadata of the Streamable HTTP endpoint. `resource` is
/// the endpoint URL, which is what a client configured with it expects.
pub async fn mcp_protected_resource_metadata(State(state): State<AppState>) -> Json<Value> {
    endpoint_resource_metadata(&state.config, McpEndpoint::StreamableHttp)
}

/// GET /.well-known/oauth-protected-resource/mcp/sse
///
/// Same document for the SSE endpoint.
pub async fn mcp_sse_protected_resource_metadata(State(state): State<AppState>) -> Json<Value> {
    endpoint_resource_metadata(&state.config, McpEndpoint::Sse)
}

fn endpoint_resource_metadata(
    config: &crate::config::Config,
    endpoint: McpEndpoint,
) -> Json<Value> {
    let base = external_base(config);
    Json(json!({
        "resource": format!("{base}{}", endpoint.path()),
        "authorization_servers": authorization_servers(config),
        "scopes_supported": config.oauth_scopes_supported,
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
        "pushed_authorization_request_endpoint": format!("{}/oauth/par", gateway_url),
        "registration_endpoint": format!("{}/oauth/register", gateway_url),
        "jwks_uri": format!("{}/protocol/openid-connect/certs", kc_base),
        "scopes_supported": config.oauth_scopes_supported,
        "response_types_supported": ["code"],
        "grant_types_supported": [
            "authorization_code",
            "client_credentials",
            "refresh_token"
        ],
        "token_endpoint_auth_methods_supported": [
            "none",
            "client_secret_basic",
            "client_secret_post",
            "private_key_jwt"
        ],
        "code_challenge_methods_supported": ["S256"],
        "subject_types_supported": ["public"],
        "require_pushed_authorization_requests": false
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

    let keycloak_backend = match config.keycloak_backend_url() {
        Some(url) => url.trim_end_matches('/'),
        None => {
            warn!("Keycloak URL not configured — cannot serve OIDC discovery");
            return Err(StatusCode::SERVICE_UNAVAILABLE);
        }
    };
    let realm = config.keycloak_realm.as_deref().unwrap_or("stoa");
    let discovery_url = format!(
        "{}/realms/{}/.well-known/openid-configuration",
        keycloak_backend, realm
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

    // Override token, registration, and PAR endpoints to point to gateway proxy
    if let Some(obj) = oidc_config.as_object_mut() {
        obj.insert(
            "token_endpoint".to_string(),
            json!(format!("{}/oauth/token", gateway_url)),
        );
        obj.insert(
            "pushed_authorization_request_endpoint".to_string(),
            json!(format!("{}/oauth/par", gateway_url)),
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
        // authorization_servers points to the gateway itself
        assert_eq!(meta["authorization_servers"][0], "http://localhost:8080");
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
        // RFC 9728: authorization_servers points to the gateway (not Keycloak)
        // so clients discover our curated metadata with public client support
        assert_eq!(meta["authorization_servers"][0], "https://mcp.gostoa.dev");
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
    async fn test_authorization_server_metadata_par_endpoint() {
        let state = test_state(Some("https://kc.test"), Some("https://gw.test"));
        let Json(meta) = authorization_server_metadata(State(state)).await;
        // RFC 9126: PAR endpoint advertised in metadata (FAPI 2.0)
        assert_eq!(
            meta["pushed_authorization_request_endpoint"],
            "https://gw.test/oauth/par"
        );
        // FAPI 2.0: private_key_jwt supported
        let auth_methods = meta["token_endpoint_auth_methods_supported"]
            .as_array()
            .unwrap();
        assert!(auth_methods.iter().any(|v| v == "private_key_jwt"));
        // PAR not required by default (dual-mode transition)
        assert_eq!(meta["require_pushed_authorization_requests"], false);
    }

    #[tokio::test]
    async fn test_openid_configuration_no_keycloak_returns_503() {
        let state = test_state(None, None);
        let result = openid_configuration(State(state)).await;
        assert!(result.is_err());
        assert_eq!(result.unwrap_err(), StatusCode::SERVICE_UNAVAILABLE);
    }

    #[tokio::test]
    async fn advertised_scopes_follow_the_configuration() {
        let config = Config {
            keycloak_url: Some("https://auth.example.test".to_string()),
            gateway_external_url: Some("https://mcp.example.test".to_string()),
            oauth_scopes_supported: vec!["openid".to_string(), "stoa:read".to_string()],
            ..Config::default()
        };
        let state = AppState::new(config);
        let expected = json!(["openid", "stoa:read"]);

        let Json(resource) = protected_resource_metadata(State(state.clone())).await;
        assert_eq!(resource["scopes_supported"], expected);
        assert_eq!(resource["resource"], "https://mcp.example.test");

        let Json(server) = authorization_server_metadata(State(state)).await;
        assert_eq!(server["scopes_supported"], expected);
        assert_eq!(
            server["registration_endpoint"],
            "https://mcp.example.test/oauth/register"
        );
    }

    #[test]
    fn bearer_challenge_carries_an_absolute_metadata_url() {
        let config = Config {
            gateway_external_url: Some("https://mcp.example.test/".to_string()),
            ..Config::default()
        };
        assert_eq!(
            bearer_challenge(&config, McpEndpoint::StreamableHttp, None),
            r#"Bearer resource_metadata="https://mcp.example.test/.well-known/oauth-protected-resource/mcp""#
        );
        assert_eq!(
            bearer_challenge(&config, McpEndpoint::Sse, Some("invalid_token")),
            r#"Bearer error="invalid_token", resource_metadata="https://mcp.example.test/.well-known/oauth-protected-resource/mcp/sse""#
        );
        let default = bearer_challenge(&Config::default(), McpEndpoint::StreamableHttp, None);
        assert!(
            default.contains(r#"="http://localhost:8080/.well-known/"#),
            "{default}"
        );
    }

    /// With `oauth_authorization_servers`, every protected resource document
    /// names those issuers, in order, instead of the gateway.
    #[tokio::test]
    async fn configured_authorization_servers_replace_the_gateway() {
        let config = Config {
            keycloak_url: Some("https://auth.example.test".to_string()),
            gateway_external_url: Some("https://mcp.example.test".to_string()),
            oauth_authorization_servers: vec![
                "https://auth.example.test/realms/stoa".to_string(),
                "https://other.example.test".to_string(),
            ],
            ..Config::default()
        };
        let state = AppState::new(config);
        let expected = json!([
            "https://auth.example.test/realms/stoa",
            "https://other.example.test"
        ]);

        let Json(root) = protected_resource_metadata(State(state.clone())).await;
        assert_eq!(root["authorization_servers"], expected);
        assert_eq!(root["resource"], "https://mcp.example.test");
        let Json(mcp) = mcp_protected_resource_metadata(State(state.clone())).await;
        assert_eq!(mcp["authorization_servers"], expected);
        assert_eq!(mcp["resource"], "https://mcp.example.test/mcp");
        let Json(sse) = mcp_sse_protected_resource_metadata(State(state)).await;
        assert_eq!(sse["authorization_servers"], expected);
    }

    /// The document a challenge names must describe the endpoint that sent
    /// it: same `resource` as the endpoint URL, path included.
    #[tokio::test]
    async fn endpoint_metadata_names_the_endpoint_url() {
        let config = Config {
            keycloak_url: Some("https://auth.example.test".to_string()),
            gateway_external_url: Some("https://mcp.example.test/".to_string()),
            oauth_scopes_supported: vec!["openid".to_string()],
            ..Config::default()
        };
        let state = AppState::new(config);

        let Json(mcp) = mcp_protected_resource_metadata(State(state.clone())).await;
        assert_eq!(mcp["resource"], "https://mcp.example.test/mcp");
        assert_eq!(
            mcp["authorization_servers"],
            json!(["https://mcp.example.test"])
        );
        assert_eq!(mcp["scopes_supported"], json!(["openid"]));

        let Json(sse) = mcp_sse_protected_resource_metadata(State(state.clone())).await;
        assert_eq!(sse["resource"], "https://mcp.example.test/mcp/sse");
        assert_eq!(sse["authorization_servers"], mcp["authorization_servers"]);

        for endpoint in [McpEndpoint::StreamableHttp, McpEndpoint::Sse] {
            let challenge = bearer_challenge(&state.config, endpoint, None);
            let expected = format!(
                r#"resource_metadata="https://mcp.example.test/.well-known/oauth-protected-resource{}""#,
                endpoint.path()
            );
            assert!(challenge.contains(&expected), "{challenge}");
        }
    }
}
