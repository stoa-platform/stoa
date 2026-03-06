//! API Proxy handler — routes `/apis/{backend}/*` to upstream (CAB-1724).
//!
//! Credential injection: reads the backend API key from CredentialStore
//! (keyed by backend name) and injects it into the upstream request.
//! Consumers authenticate via OAuth2 (Keycloak) — never see backend keys.

use axum::{
    body::Body,
    extract::{Path, Request, State},
    http::{HeaderValue, StatusCode},
    response::{IntoResponse, Response},
};
use std::time::Duration;
use tracing::{debug, error, info, warn};

use crate::state::AppState;

/// Shared reqwest client for API proxy (separate from dynamic proxy).
static API_PROXY_CLIENT: std::sync::OnceLock<reqwest::Client> = std::sync::OnceLock::new();

fn get_api_proxy_client() -> &'static reqwest::Client {
    API_PROXY_CLIENT.get_or_init(|| {
        reqwest::Client::builder()
            .timeout(Duration::from_secs(60))
            .connect_timeout(Duration::from_secs(5))
            .pool_max_idle_per_host(64)
            .pool_idle_timeout(Duration::from_secs(90))
            .tcp_keepalive(Duration::from_secs(60))
            .tcp_nodelay(true)
            .build()
            .expect("Failed to create API proxy HTTP client")
    })
}

/// Handler for `/apis/{backend}/{path}` — proxy to upstream with credential injection.
///
/// Flow:
/// 1. Look up backend in ApiProxyRegistry
/// 2. Check allowed paths (if configured)
/// 3. Fetch credential from CredentialStore (keyed by "api-proxy:{backend}")
/// 4. Build upstream request with injected auth header
/// 5. Forward request, return response
pub async fn api_proxy_handler(
    State(state): State<AppState>,
    Path(path): Path<String>,
    request: Request<Body>,
) -> Response {
    // Parse backend name and rest from catch-all path: "backend/rest/of/path"
    let (backend_name, rest) = match path.find('/') {
        Some(idx) => (path[..idx].to_string(), path[idx + 1..].to_string()),
        None => (path, String::new()),
    };

    // 1. Check master switch
    if !state.config.api_proxy.enabled {
        return (StatusCode::NOT_FOUND, "API proxy disabled").into_response();
    }

    // 2. Look up backend in registry
    let registry = match &state.api_proxy_registry {
        Some(r) => r,
        None => {
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                "API proxy not initialized",
            )
                .into_response();
        }
    };

    let backend = match registry.get(&backend_name) {
        Some(b) => b,
        None => {
            debug!(backend = %backend_name, "API proxy: backend not found or disabled");
            return (StatusCode::NOT_FOUND, "Backend not found").into_response();
        }
    };

    // 3. Check allowed paths (if configured)
    if !backend.config.allowed_paths.is_empty() {
        let path_with_slash = format!("/{rest}");
        let allowed = backend
            .config
            .allowed_paths
            .iter()
            .any(|prefix| path_with_slash.starts_with(prefix));
        if !allowed {
            warn!(
                backend = %backend_name,
                path = %rest,
                "API proxy: path not in allowed list"
            );
            return (StatusCode::FORBIDDEN, "Path not allowed for this backend").into_response();
        }
    }

    // 4. Build upstream URL
    let upstream_url = format!("{}/{}", backend.config.base_url.trim_end_matches('/'), rest);

    // Preserve query string
    let upstream_url = if let Some(query) = request.uri().query() {
        format!("{upstream_url}?{query}")
    } else {
        upstream_url
    };

    debug!(
        backend = %backend_name,
        upstream = %upstream_url,
        method = %request.method(),
        "API proxy: forwarding request"
    );

    // 5. Fetch credential from store (keyed by "api-proxy:{backend}")
    let credential_key = format!("api-proxy:{backend_name}");
    let credential = state.credential_store.get(&credential_key);

    // 6. Build upstream request
    let method = request.method().clone();
    let client = get_api_proxy_client();

    let mut upstream_req = client.request(method, &upstream_url);

    // Set timeout from backend config
    upstream_req = upstream_req.timeout(Duration::from_secs(backend.config.timeout_secs));

    // Copy relevant headers (skip hop-by-hop headers)
    let skip_headers = [
        "host",
        "connection",
        "transfer-encoding",
        "te",
        "trailer",
        "upgrade",
        "keep-alive",
        "proxy-authorization",
        "proxy-authenticate",
    ];

    for (name, value) in request.headers() {
        let name_lower = name.as_str().to_lowercase();
        if !skip_headers.contains(&name_lower.as_str())
            && !name_lower.starts_with("x-stoa-")
            && name_lower != backend.config.auth_header.to_lowercase()
        {
            if let Ok(v) = reqwest::header::HeaderValue::from_bytes(value.as_bytes()) {
                upstream_req = upstream_req.header(name.as_str(), v);
            }
        }
    }

    // Inject backend credential
    if let Some(cred) = &credential {
        if cred.auth_type == crate::proxy::credentials::AuthType::OAuth2ClientCredentials {
            // Fetch OAuth2 token
            match state
                .credential_store
                .get_oauth2_token(&credential_key, get_api_proxy_client())
                .await
            {
                Ok(token) => {
                    upstream_req =
                        upstream_req.header(&cred.header_name, format!("Bearer {token}"));
                }
                Err(e) => {
                    error!(backend = %backend_name, error = %e, "OAuth2 token fetch failed");
                    return (
                        StatusCode::BAD_GATEWAY,
                        "Failed to authenticate with upstream",
                    )
                        .into_response();
                }
            }
        } else {
            upstream_req = upstream_req.header(&cred.header_name, &cred.header_value);
        }
    } else {
        warn!(
            backend = %backend_name,
            credential_key = %credential_key,
            "No credential configured — proxying without auth"
        );
    }

    // Forward body
    let body_bytes = match axum::body::to_bytes(request.into_body(), 10 * 1024 * 1024).await {
        Ok(b) => b,
        Err(e) => {
            error!(error = %e, "Failed to read request body");
            return (StatusCode::BAD_REQUEST, "Failed to read request body").into_response();
        }
    };

    if !body_bytes.is_empty() {
        upstream_req = upstream_req.body(body_bytes);
    }

    // 7. Send upstream request
    let upstream_resp = match upstream_req.send().await {
        Ok(r) => r,
        Err(e) => {
            error!(
                backend = %backend_name,
                upstream = %upstream_url,
                error = %e,
                "API proxy: upstream request failed"
            );
            if e.is_timeout() {
                return (StatusCode::GATEWAY_TIMEOUT, "Upstream timeout").into_response();
            }
            return (StatusCode::BAD_GATEWAY, "Upstream request failed").into_response();
        }
    };

    // 8. Build response
    let status = upstream_resp.status();
    let mut response_builder = Response::builder().status(status.as_u16());

    // Copy response headers (strip hop-by-hop)
    for (name, value) in upstream_resp.headers() {
        let name_lower = name.as_str().to_lowercase();
        if !skip_headers.contains(&name_lower.as_str()) {
            if let Ok(v) = HeaderValue::from_bytes(value.as_bytes()) {
                response_builder = response_builder.header(name.as_str(), v);
            }
        }
    }

    // Add proxy metadata header
    response_builder = response_builder.header("X-Stoa-Proxy-Backend", &backend_name);

    let body_bytes = match upstream_resp.bytes().await {
        Ok(b) => b,
        Err(e) => {
            error!(error = %e, "Failed to read upstream response body");
            return (StatusCode::BAD_GATEWAY, "Failed to read upstream response").into_response();
        }
    };

    info!(
        backend = %backend_name,
        status = status.as_u16(),
        body_size = body_bytes.len(),
        "API proxy: response received"
    );

    match response_builder.body(Body::from(body_bytes)) {
        Ok(response) => response,
        Err(e) => {
            error!(error = %e, "Failed to build proxy response");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                "Failed to build response",
            )
                .into_response()
        }
    }
}

/// Handler for listing registered API proxy backends (admin endpoint).
/// Returns JSON array of backend names + status.
pub async fn list_api_proxy_backends(State(state): State<AppState>) -> Response {
    let registry = match &state.api_proxy_registry {
        Some(r) => r,
        None => {
            return (
                StatusCode::OK,
                axum::Json(serde_json::json!({"enabled": false, "backends": []})),
            )
                .into_response();
        }
    };

    let backends: Vec<serde_json::Value> = registry
        .list_names()
        .iter()
        .map(|name| {
            let backend = registry.get(name);
            serde_json::json!({
                "name": name,
                "base_url": backend.as_ref().map(|b| b.config.base_url.as_str()),
                "rate_limit_rpm": backend.as_ref().map(|b| b.config.rate_limit_rpm),
                "circuit_breaker": backend.as_ref().map(|b| b.config.circuit_breaker_enabled),
                "fallback_direct": backend.as_ref().map(|b| b.config.fallback_direct),
            })
        })
        .collect();

    (
        StatusCode::OK,
        axum::Json(serde_json::json!({
            "enabled": state.config.api_proxy.enabled,
            "require_auth": state.config.api_proxy.require_auth,
            "backends": backends,
        })),
    )
        .into_response()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_api_proxy_client_created() {
        let client = get_api_proxy_client();
        // Verify the client was created (no panic)
        let _ = client;
    }
}
