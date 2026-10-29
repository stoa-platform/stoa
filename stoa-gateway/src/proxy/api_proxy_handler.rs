//! API Proxy handler — routes `/apis/{backend}/*` to upstream (CAB-1724).
//!
//! Credential injection: reads the backend API key from CredentialStore
//! (keyed by backend name) and injects it into the upstream request.
//! Consumers authenticate via OAuth2 (Keycloak) — never see backend keys.
//!
//! Resilience layer (CAB-1726):
//! - Per-backend circuit breaker via CircuitBreakerRegistry
//! - Per-backend RPM rate limiting (token bucket)
//! - Prometheus metrics (requests, duration, rate limits, circuit opens)

use axum::{
    body::Body,
    extract::{Path, Request, State},
    http::{HeaderValue, StatusCode},
    response::{IntoResponse, Response},
};
use parking_lot::Mutex;
use std::collections::HashMap;
use std::time::{Duration, Instant};
use tracing::{debug, error, info, warn};

use crate::auth::access_requirement::{authorize, Identity, TypClaimPolicy};
use crate::auth::middleware::AuthenticatedUser;
use crate::metrics;
use crate::state::AppState;

use super::observe_only_guardrails;

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

// ---------------------------------------------------------------------------
// Per-backend RPM rate limiter (CAB-1726)
// ---------------------------------------------------------------------------

/// Simple per-backend token bucket rate limiter keyed by backend name.
/// Tokens refill at `rate_limit_rpm / 60` per second.
struct BackendBucket {
    tokens: f64,
    max_tokens: f64,
    refill_rate: f64, // tokens per second
    last_refill: Instant,
}

impl BackendBucket {
    fn new(rpm: u32) -> Self {
        let max = rpm as f64;
        Self {
            tokens: max,
            max_tokens: max,
            refill_rate: max / 60.0,
            last_refill: Instant::now(),
        }
    }

    /// Try to consume one token. Returns true if allowed, false if rate limited.
    fn try_acquire(&mut self) -> bool {
        let now = Instant::now();
        let elapsed = now.duration_since(self.last_refill).as_secs_f64();
        self.tokens = (self.tokens + elapsed * self.refill_rate).min(self.max_tokens);
        self.last_refill = now;

        if self.tokens >= 1.0 {
            self.tokens -= 1.0;
            true
        } else {
            false
        }
    }
}

/// Global per-backend rate limiter registry.
static BACKEND_RATE_LIMITERS: std::sync::OnceLock<Mutex<HashMap<String, BackendBucket>>> =
    std::sync::OnceLock::new();

fn get_rate_limiters() -> &'static Mutex<HashMap<String, BackendBucket>> {
    BACKEND_RATE_LIMITERS.get_or_init(|| Mutex::new(HashMap::new()))
}

/// Check per-backend rate limit. Returns true if request is allowed.
fn check_backend_rate_limit(backend_name: &str, rpm: u32) -> bool {
    if rpm == 0 {
        return true; // 0 = unlimited
    }
    let mut limiters = get_rate_limiters().lock();
    let bucket = limiters
        .entry(backend_name.to_string())
        .or_insert_with(|| BackendBucket::new(rpm));
    // Update max if config changed (hot-reload)
    if (bucket.max_tokens - rpm as f64).abs() > f64::EPSILON {
        bucket.max_tokens = rpm as f64;
        bucket.refill_rate = rpm as f64 / 60.0;
    }
    bucket.try_acquire()
}

/// Handler for `/apis/{backend}/{path}` — proxy to upstream with credential injection.
///
/// Flow:
/// 1. Look up backend in ApiProxyRegistry
/// 2. Check allowed paths (if configured)
/// 3. Check circuit breaker (fast-fail if open)
/// 4. Check per-backend rate limit (429 if exceeded)
/// 5. Fetch credential from CredentialStore (keyed by "api-proxy:{backend}")
/// 6. Build upstream request with injected auth header
/// 7. Forward request, record circuit breaker outcome + metrics
pub async fn api_proxy_handler(
    State(state): State<AppState>,
    Path(path): Path<String>,
    request: Request<Body>,
) -> Response {
    let start = Instant::now();

    // Parse backend name and rest from catch-all path: "backend/rest/of/path"
    let (backend_name, rest) = match path.find('/') {
        Some(idx) => (path[..idx].to_string(), path[idx + 1..].to_string()),
        None => (path, String::new()),
    };

    let method_str = request.method().to_string();

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

    // Access requirement: before allowed paths, quota, credential and upstream.
    // The reason stays in the log only; no token, claim or identity is logged.
    let decision = authorize(
        proxy_identity(&request),
        (&backend.config).into(),
        TypClaimPolicy::default(),
    );
    if let Err(reason) = decision {
        warn!(backend = %backend_name, reason = ?reason, "API proxy: access refused");
        metrics::record_api_proxy_request(
            &backend_name,
            &method_str,
            403,
            start.elapsed().as_secs_f64(),
        );
        return (StatusCode::FORBIDDEN, "Access denied").into_response();
    }

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

    // 4. Circuit breaker check (CAB-1726)
    if backend.config.circuit_breaker_enabled {
        let cb_name = format!("api-proxy:{backend_name}");
        if state.circuit_breakers.is_open(&cb_name) {
            warn!(backend = %backend_name, "API proxy: circuit breaker open, fast-failing");
            metrics::record_api_proxy_circuit_open(&backend_name);
            metrics::record_api_proxy_request(
                &backend_name,
                &method_str,
                503,
                start.elapsed().as_secs_f64(),
            );
            return Response::builder()
                .status(StatusCode::SERVICE_UNAVAILABLE)
                .header("Retry-After", "30")
                .header("X-Stoa-Proxy-Backend", &backend_name)
                .body(Body::from("Backend circuit breaker open"))
                .unwrap_or_else(|_| {
                    (
                        StatusCode::SERVICE_UNAVAILABLE,
                        "Backend circuit breaker open",
                    )
                        .into_response()
                });
        }
    }

    // 5. Per-backend rate limit check (CAB-1726)
    if !check_backend_rate_limit(&backend_name, backend.config.rate_limit_rpm) {
        warn!(
            backend = %backend_name,
            rpm = backend.config.rate_limit_rpm,
            "API proxy: rate limit exceeded"
        );
        metrics::record_api_proxy_rate_limited(&backend_name);
        metrics::record_api_proxy_request(
            &backend_name,
            &method_str,
            429,
            start.elapsed().as_secs_f64(),
        );
        let retry_after = 60u32
            .checked_div(backend.config.rate_limit_rpm)
            .unwrap_or(1)
            .max(1);
        return Response::builder()
            .status(StatusCode::TOO_MANY_REQUESTS)
            .header("Retry-After", retry_after.to_string())
            .header("X-Stoa-Proxy-Backend", &backend_name)
            .body(Body::from("Rate limit exceeded"))
            .unwrap_or_else(|_| {
                (StatusCode::TOO_MANY_REQUESTS, "Rate limit exceeded").into_response()
            });
    }

    // 6. Build upstream URL
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
        method = %method_str,
        "API proxy: forwarding request"
    );

    // 7. Fetch credential from store (keyed by "api-proxy:{backend}")
    let credential_key = format!("api-proxy:{backend_name}");
    let credential = state.credential_store.get(&credential_key);
    if backend.config.public && credential.is_some() {
        error!(backend = %backend_name, "API proxy: public backend has a service credential");
        metrics::record_api_proxy_request(
            &backend_name,
            &method_str,
            403,
            start.elapsed().as_secs_f64(),
        );
        return (StatusCode::FORBIDDEN, "Access denied").into_response();
    }

    // 8. Build upstream request
    let method = request.method().clone();
    let client = get_api_proxy_client();

    let mut upstream_req = client.request(method, &upstream_url);

    // Set timeout from backend config
    upstream_req = upstream_req.timeout(Duration::from_secs(backend.config.timeout_secs));

    // Copy relevant headers. Gateway-level credentials stay at the gateway;
    // the backend credential is injected below.
    for (name, value) in request.headers() {
        if is_forwarded_request_header(name.as_str(), &backend.config.auth_header) {
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
                    metrics::record_api_proxy_request(
                        &backend_name,
                        &method_str,
                        502,
                        start.elapsed().as_secs_f64(),
                    );
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
    let request_headers = request.headers().clone();
    let body_bytes = match axum::body::to_bytes(request.into_body(), 10 * 1024 * 1024).await {
        Ok(b) => b,
        Err(e) => {
            error!(error = %e, "Failed to read request body");
            metrics::record_api_proxy_request(
                &backend_name,
                &method_str,
                400,
                start.elapsed().as_secs_f64(),
            );
            return (StatusCode::BAD_REQUEST, "Failed to read request body").into_response();
        }
    };
    let guardrail_body =
        observe_only_guardrails::classify_buffered_json_body(&request_headers, &body_bytes);
    let guardrails_config = observe_only_guardrails::resolve_guardrails_config(&state, None);
    observe_only_guardrails::record_observe_only_guardrails(
        "api_proxy",
        &guardrails_config,
        &guardrail_body,
        backend.config.rate_limit_rpm > 0,
    );

    if !body_bytes.is_empty() {
        upstream_req = upstream_req.body(body_bytes);
    }

    // 9. Send upstream request
    let cb_name = format!("api-proxy:{backend_name}");
    let upstream_resp = match upstream_req.send().await {
        Ok(r) => {
            // Record success on circuit breaker
            if backend.config.circuit_breaker_enabled {
                let cb = state.circuit_breakers.get_or_create(&cb_name);
                if r.status().is_server_error() {
                    cb.record_failure();
                } else {
                    cb.record_success();
                }
            }
            r
        }
        Err(e) => {
            // Record failure on circuit breaker
            if backend.config.circuit_breaker_enabled {
                let cb = state.circuit_breakers.get_or_create(&cb_name);
                cb.record_failure();
            }

            error!(
                backend = %backend_name,
                upstream = %upstream_url,
                error = %e,
                "API proxy: upstream request failed"
            );
            if e.is_timeout() {
                metrics::record_api_proxy_request(
                    &backend_name,
                    &method_str,
                    504,
                    start.elapsed().as_secs_f64(),
                );
                return (StatusCode::GATEWAY_TIMEOUT, "Upstream timeout").into_response();
            }
            metrics::record_api_proxy_request(
                &backend_name,
                &method_str,
                502,
                start.elapsed().as_secs_f64(),
            );
            return (StatusCode::BAD_GATEWAY, "Upstream request failed").into_response();
        }
    };

    // 10. Build response
    let status = upstream_resp.status();
    let mut response_builder = Response::builder().status(status.as_u16());

    // Copy response headers (strip hop-by-hop)
    for (name, value) in upstream_resp.headers() {
        let name_lower = name.as_str().to_lowercase();
        if !HOP_BY_HOP_HEADERS.contains(&name_lower.as_str()) {
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
            metrics::record_api_proxy_request(
                &backend_name,
                &method_str,
                502,
                start.elapsed().as_secs_f64(),
            );
            return (StatusCode::BAD_GATEWAY, "Failed to read upstream response").into_response();
        }
    };

    let duration = start.elapsed().as_secs_f64();

    info!(
        backend = %backend_name,
        status = status.as_u16(),
        body_size = body_bytes.len(),
        duration_ms = format_args!("{:.1}", duration * 1000.0),
        "API proxy: response received"
    );

    // Record Prometheus metrics (CAB-1726)
    metrics::record_api_proxy_request(&backend_name, &method_str, status.as_u16(), duration);
    metrics::record_upstream_latency(&cb_name, status.as_u16(), duration);

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

/// Identity seen by the proxy. A validated user comes from the auth layer.
/// Any Authorization header without a validated user (malformed, another
/// scheme, or a Bearer not validated upstream) counts as rejected, never absent.
fn proxy_identity(request: &Request<Body>) -> Identity<'_> {
    if let Some(user) = request.extensions().get::<AuthenticatedUser>() {
        Identity::Present(user)
    } else if request
        .headers()
        .contains_key(axum::http::header::AUTHORIZATION)
    {
        Identity::Rejected
    } else {
        Identity::Absent
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
            let cb_name = format!("api-proxy:{name}");
            let cb_open = state.circuit_breakers.is_open(&cb_name);
            serde_json::json!({
                "name": name,
                "base_url": backend.as_ref().map(|b| b.config.base_url.as_str()),
                "rate_limit_rpm": backend.as_ref().map(|b| b.config.rate_limit_rpm),
                "circuit_breaker": backend.as_ref().map(|b| b.config.circuit_breaker_enabled),
                "circuit_breaker_open": cb_open,
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

/// Hop-by-hop headers, never copied in either direction.
const HOP_BY_HOP_HEADERS: [&str; 9] = [
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

/// Caller credentials for the gateway itself, not relayed to a backend.
const GATEWAY_CREDENTIAL_HEADERS: [&str; 3] = ["authorization", "cookie", "dpop"];

/// Whether a caller request header is relayed to the backend.
///
/// Hop-by-hop headers, gateway credentials, `x-stoa-*` headers and the backend's own credential header are also
/// dropped, since the gateway sets them itself.
fn is_forwarded_request_header(name: &str, backend_auth_header: &str) -> bool {
    let name = name.to_ascii_lowercase();
    !HOP_BY_HOP_HEADERS.contains(&name.as_str())
        && !GATEWAY_CREDENTIAL_HEADERS.contains(&name.as_str())
        && !name.starts_with("x-stoa-")
        && !name.eq_ignore_ascii_case(backend_auth_header)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::proxy::credentials::{AuthType, BackendCredential};
    use axum::http::header::AUTHORIZATION;
    use wiremock::{matchers::any, Mock, MockServer, ResponseTemplate};

    fn user(scope: &str) -> AuthenticatedUser {
        let claims = serde_json::from_value(serde_json::json!({
            "sub": "u", "exp": 4_102_444_800i64, "iat": 0, "iss": "https://issuer.example",
            "aud": "stoa", "typ": "Bearer", "scope": scope
        }))
        .unwrap();
        AuthenticatedUser {
            user_id: "u".into(),
            username: None,
            email: None,
            tenant_id: None,
            claims,
            raw_token: String::new(),
        }
    }

    async fn call(
        backend: serde_json::Value,
        who: Option<&str>,
        authz: Option<&str>,
    ) -> (StatusCode, usize) {
        let upstream = MockServer::start().await;
        Mock::given(any())
            .respond_with(ResponseTemplate::new(200))
            .mount(&upstream)
            .await;
        let mut b = serde_json::json!({ "enabled": true, "base_url": upstream.uri() });
        b.as_object_mut()
            .unwrap()
            .extend(backend.as_object().unwrap().clone());
        let api = serde_json::json!({ "enabled": true, "backends": { "t": b } });
        let config = crate::config::Config {
            api_proxy: serde_json::from_value(api).unwrap(),
            ..Default::default()
        };
        let state = AppState::new(config);
        state.credential_store.upsert(BackendCredential {
            route_id: "api-proxy:t".into(),
            auth_type: AuthType::ApiKey,
            header_name: "X-Service-Key".into(),
            header_value: "fixture-service-value".into(),
            oauth2: None,
        });
        let mut req = Request::builder().uri("/proxy/t/echo");
        if let Some(a) = authz {
            req = req.header(AUTHORIZATION, a);
        }
        let mut req = req.body(Body::empty()).unwrap();
        if let Some(scope) = who {
            req.extensions_mut().insert(user(scope));
        }
        let res = api_proxy_handler(State(state), Path("t/echo".into()), req).await;
        (
            res.status(),
            upstream.received_requests().await.unwrap().len(),
        )
    }

    #[tokio::test]
    async fn regression_proxy_token_without_required_scope_is_403_without_upstream_call() {
        let guarded = serde_json::json!({ "required_scopes": ["proxy:read"], "rate_limit_rpm": 1 });
        assert_eq!(
            call(guarded.clone(), Some("openid"), None).await,
            (StatusCode::FORBIDDEN, 0)
        );
        // The refusal did not consume the single RPM token of a fresh backend.
        assert_eq!(
            call(guarded, Some("proxy:read"), None).await,
            (StatusCode::OK, 1)
        );
    }

    #[tokio::test]
    async fn proxy_backend_without_requirement_is_403() {
        let r = call(serde_json::json!({}), Some("proxy:read"), None).await;
        assert_eq!(r, (StatusCode::FORBIDDEN, 0));
    }

    #[tokio::test]
    async fn regression_proxy_unvalidated_authorization_is_rejected_not_absent() {
        let public = serde_json::json!({ "public": true, "auth_type": "none" });
        for header in ["Basic dTpw", "Bearer", "Bearer not-validated", ""] {
            assert_eq!(
                call(public.clone(), None, Some(header)).await,
                (StatusCode::FORBIDDEN, 0),
                "{header:?}"
            );
        }
    }

    #[tokio::test]
    async fn regression_proxy_public_backend_never_injects_service_credential() {
        let public = serde_json::json!({ "public": true, "auth_type": "none" });
        assert_eq!(call(public, None, None).await, (StatusCode::FORBIDDEN, 0));
    }

    #[test]
    fn test_forwarded_request_headers() {
        for name in ["Authorization", "authorization", "Cookie", "DPoP", "dpop"] {
            assert!(!is_forwarded_request_header(name, "X-API-Key"), "{name}");
        }
        for name in ["Host", "Connection", "Proxy-Authorization", "X-Stoa-Tenant"] {
            assert!(!is_forwarded_request_header(name, "X-API-Key"), "{name}");
        }
        assert!(!is_forwarded_request_header("x-api-key", "X-API-Key"));
        for name in ["Content-Type", "Accept", "X-Request-Id", "X-Custom"] {
            assert!(is_forwarded_request_header(name, "X-API-Key"), "{name}");
        }
    }

    #[test]
    fn test_api_proxy_client_created() {
        let client = get_api_proxy_client();
        // Verify the client was created (no panic)
        let _ = client;
    }

    #[test]
    fn test_rate_limiter_allows_within_limit() {
        // 60 RPM = 1 per second
        assert!(check_backend_rate_limit("test-rl-allow", 60));
        assert!(check_backend_rate_limit("test-rl-allow", 60));
    }

    #[test]
    fn test_rate_limiter_unlimited_when_zero() {
        // 0 RPM = unlimited
        for _ in 0..1000 {
            assert!(check_backend_rate_limit("test-rl-unlimited", 0));
        }
    }

    #[test]
    fn test_rate_limiter_blocks_when_exhausted() {
        // 1 RPM = very restrictive. First request passes, rest blocked.
        assert!(check_backend_rate_limit("test-rl-block", 1));
        // Immediately after, should be blocked
        assert!(!check_backend_rate_limit("test-rl-block", 1));
    }

    #[test]
    fn test_rate_limiter_different_backends_independent() {
        assert!(check_backend_rate_limit("test-rl-a", 1));
        assert!(check_backend_rate_limit("test-rl-b", 1));
        // Backend A exhausted, B should still be independent
        assert!(!check_backend_rate_limit("test-rl-a", 1));
        assert!(!check_backend_rate_limit("test-rl-b", 1));
    }

    #[test]
    fn test_backend_bucket_new() {
        let bucket = BackendBucket::new(120);
        assert!((bucket.max_tokens - 120.0).abs() < f64::EPSILON);
        assert!((bucket.refill_rate - 2.0).abs() < f64::EPSILON); // 120/60 = 2/sec
    }

    #[test]
    fn test_backend_bucket_try_acquire() {
        let mut bucket = BackendBucket::new(60);
        // Should allow many requests (bucket starts full at 60 tokens)
        for _ in 0..60 {
            assert!(bucket.try_acquire());
        }
        // Now should be empty
        assert!(!bucket.try_acquire());
    }
}
