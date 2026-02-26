//! Dynamic proxy handler for Control Plane managed API routes.
//!
//! Catch-all fallback: looks up the request path in RouteRegistry,
//! proxies to the matched backend if found, returns 404 otherwise.

use axum::{
    body::Body,
    extract::{Request, State},
    http::{HeaderMap, HeaderValue, Method, StatusCode},
    response::{IntoResponse, Response},
};
use std::net::IpAddr;
use std::time::Duration;
use tracing::{debug, error, instrument, warn};

use rand::rngs::SmallRng;
use rand::{Rng, SeedableRng};
use std::cell::RefCell;

use crate::proxy::credentials::{AuthType, BackendCredential};
use crate::proxy::hop_detection;
use crate::resilience::RetryConfig;
use crate::state::AppState;

/// Resolve a BackendCredential into a (header_name, header_value) tuple.
/// For OAuth2ClientCredentials, fetches/caches a token via the credential store.
async fn resolve_credential_header(
    state: &AppState,
    route_id: &str,
    credential: Option<&BackendCredential>,
) -> Option<(String, String)> {
    let cred = credential?;
    if cred.auth_type == AuthType::OAuth2ClientCredentials {
        match state
            .credential_store
            .get_oauth2_token(route_id, get_proxy_client())
            .await
        {
            Ok(token) => Some(("Authorization".to_string(), format!("Bearer {token}"))),
            Err(e) => {
                warn!(
                    route_id = %route_id,
                    error = %e,
                    "OAuth2 token fetch failed — skipping credential injection"
                );
                None
            }
        }
    } else {
        Some((cred.header_name.clone(), cred.header_value.clone()))
    }
}

thread_local! {
    /// Thread-local fast PRNG for traceparent ID generation.
    /// Avoids 2x `getrandom()` syscall per request (uuid::Uuid::new_v4).
    static TRACE_RNG: RefCell<SmallRng> = RefCell::new(SmallRng::from_os_rng());
}

/// Shared reqwest client for dynamic proxy (created once, reused).
static PROXY_CLIENT: std::sync::OnceLock<reqwest::Client> = std::sync::OnceLock::new();

fn get_proxy_client() -> &'static reqwest::Client {
    PROXY_CLIENT.get_or_init(|| {
        reqwest::Client::builder()
            .timeout(Duration::from_secs(30))
            .connect_timeout(Duration::from_secs(5))
            .pool_max_idle_per_host(256)
            .pool_idle_timeout(Duration::from_secs(90))
            .tcp_keepalive(Duration::from_secs(60))
            .tcp_nodelay(true)
            // Force HTTP/1.1: echo-backend and most legacy APIs don't speak h2.
            // Avoids ALPN negotiation overhead on every new connection.
            .http1_only()
            .build()
            .expect("Failed to create proxy HTTP client")
    })
}

/// Dynamic proxy handler — catch-all fallback route.
///
/// 1. Look up request path in RouteRegistry (longest prefix match)
/// 2. If found + activated: proxy to backend_url
/// 3. If found but not activated: 503
/// 4. If not found: 404
#[instrument(name = "proxy.dynamic", skip(state, request), fields(otel.kind = "client"))]
pub async fn dynamic_proxy(State(state): State<AppState>, request: Request<Body>) -> Response {
    let path = request.uri().path().to_string();
    let method = request.method().clone();

    // Find matching route
    let route = match state.route_registry.find_by_path(&path) {
        Some(r) => r,
        None => {
            return (StatusCode::NOT_FOUND, "No matching API route").into_response();
        }
    };

    if !route.activated {
        return (StatusCode::SERVICE_UNAVAILABLE, "API not activated").into_response();
    }

    // Check method allowed (empty methods list = all methods allowed)
    // Compare Method::as_str() directly — avoids method.to_string() allocation (CAB-1332)
    if !route.methods.is_empty() && !route.methods.iter().any(|m| m == method.as_str()) {
        return (
            StatusCode::METHOD_NOT_ALLOWED,
            "Method not allowed for this API",
        )
            .into_response();
    }

    // Soft-mode classification enforcement (CAB-1299)
    // If a route has a classification (from a UAC contract), log the enforcement
    // decision but do NOT deny — this is observability-only until graduation.
    if let (Some(classification), Some(ref enforcer)) =
        (route.classification, &state.classification_enforcer)
    {
        let user_id = extract_user_id(request.extensions());
        let ctx = crate::uac::enforcer::EnforcementContext::new(&route.tenant_id, &user_id);
        let decision = enforcer.enforce(classification, &route.methods, &ctx);
        if decision.is_allowed() {
            debug!(
                route_id = %route.id,
                classification = %classification,
                policy_version = ?decision.policy_version(),
                "Classification enforcement: ALLOW (soft mode)"
            );
        } else {
            warn!(
                route_id = %route.id,
                classification = %classification,
                "Classification enforcement: DENY logged (soft mode — not blocking)"
            );
        }
    }

    // Per-upstream circuit breaker (CAB-362)
    let cb = state.circuit_breakers.get_or_create(&route.id);
    if !cb.allow_request() {
        warn!(
            route_id = %route.id,
            route_name = %route.name,
            "Circuit breaker open for upstream"
        );
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            format!("Circuit breaker open for upstream: {}", route.name),
        )
            .into_response();
    }

    // Build target URL: replace path_prefix with backend_url (pre-allocated)
    let remaining_path = path.strip_prefix(&route.path_prefix).unwrap_or("");
    let backend = route.backend_url.trim_end_matches('/');
    let query = request.uri().query();
    let capacity = backend.len() + remaining_path.len() + query.map_or(0, |q| 1 + q.len());
    let mut target_url = String::with_capacity(capacity);
    target_url.push_str(backend);
    target_url.push_str(remaining_path);
    if let Some(q) = query {
        target_url.push('?');
        target_url.push_str(q);
    }

    // SSRF protection: block requests to private/internal IP ranges (defense-in-depth)
    if is_blocked_url(&target_url) {
        warn!(
            route_id = %route.id,
            target_url = %target_url,
            "SSRF blocked: backend URL resolves to private/internal IP range"
        );
        return (
            StatusCode::FORBIDDEN,
            "Backend URL blocked: private/internal IP range",
        )
            .into_response();
    }

    debug!(
        method = %method,
        route_id = %route.id,
        target_url = %target_url,
        "Dynamic proxy: forwarding request"
    );

    // Per-consumer credential injection (CAB-1432) with BYOK fallback (CAB-1250 + CAB-1317)
    // 1. Try consumer-specific credential (from JWT sub claim)
    // 2. Fall back to route-level BYOK credential
    let consumer_id = extract_user_id(request.extensions());
    let consumer_cred = if consumer_id != "anonymous" {
        state.consumer_credential_store.get(&route.id, &consumer_id)
    } else {
        None
    };
    let resolved_header = if let Some(ref cc) = consumer_cred {
        Some((cc.header_name.clone(), cc.header_value.clone()))
    } else {
        let credential = state.credential_store.get(&route.id);
        resolve_credential_header(&state, &route.id, credential.as_ref()).await
    };

    // CAB-1455 Phase 2: extract incoming W3C trace context (injected by
    // trace_context_middleware) so we propagate the same trace_id to backends.
    let trace_ctx = request
        .extensions()
        .get::<crate::trace_context::RequestTraceContext>()
        .cloned();

    // Save headers only if retry might be needed (idempotent methods with
    // retryable responses). Deferred clone avoids HeaderMap copy on every
    // request — only pays the cost when retry actually happens. (CAB-1332)
    let save_headers_for_retry = is_idempotent(&method);
    let saved_headers = if save_headers_for_retry {
        Some(request.headers().clone())
    } else {
        None
    };

    let upstream_start = std::time::Instant::now();
    let mut response = forward_request(
        request,
        &method,
        &target_url,
        resolved_header.as_ref(),
        trace_ctx.as_ref(),
    )
    .await;

    // Retry transient errors on idempotent methods (CAB-362)
    if is_retryable_status(response.status()) {
        if let Some(ref headers) = saved_headers {
            let retry_config = RetryConfig {
                max_attempts: 2,
                initial_delay: Duration::from_millis(100),
                max_delay: Duration::from_secs(1),
                ..Default::default()
            };
            for attempt in 1..=retry_config.max_attempts {
                let delay = retry_config.delay_for_attempt(attempt);
                warn!(
                    method = %method,
                    route_id = %route.id,
                    target_url = %target_url,
                    attempt = attempt,
                    status = response.status().as_u16(),
                    "Retrying transient upstream error"
                );
                tokio::time::sleep(delay).await;
                response = retry_forward(
                    &method,
                    &target_url,
                    headers,
                    resolved_header.as_ref(),
                    trace_ctx.as_ref(),
                )
                .await;
                if !is_retryable_status(response.status()) {
                    break;
                }
            }
        }
    }

    let upstream_duration = upstream_start.elapsed().as_secs_f64();

    // Record upstream latency metric
    crate::metrics::record_upstream_latency(
        &route.name,
        response.status().as_u16(),
        upstream_duration,
    );

    // Record success/failure for circuit breaker
    if response.status().is_server_error() {
        cb.record_failure();
    } else {
        cb.record_success();
    }

    // Inject X-Stoa-Timing debug header with gateway/upstream timing
    // and hop count from Via headers (CAB-1316 Phase 2).
    let hop_chain = hop_detection::parse_via_headers(response.headers());
    let gw_ms = (upstream_duration * 1000.0) as u64;
    let timing_value = format!("gw={gw_ms};hops={}", hop_chain.total_hops);
    if let Ok(hv) = HeaderValue::from_str(&timing_value) {
        response.headers_mut().insert("x-stoa-timing", hv);
    }

    response
}

/// Forward request to the backend, reusing the webMethods proxy pattern.
///
/// When a resolved header tuple is provided, it is injected into the
/// outgoing request (BYOK credential proxy — CAB-1250, OAuth2 — CAB-1317).
async fn forward_request(
    request: Request<Body>,
    method: &Method,
    target_url: &str,
    resolved_header: Option<&(String, String)>,
    trace_ctx: Option<&crate::trace_context::RequestTraceContext>,
) -> Response {
    let client = get_proxy_client();
    let headers = request.headers().clone();

    // Build the proxied request
    let mut req_builder = match *method {
        Method::GET => client.get(target_url),
        Method::POST => client.post(target_url),
        Method::PUT => client.put(target_url),
        Method::DELETE => client.delete(target_url),
        Method::PATCH => client.patch(target_url),
        Method::HEAD => client.head(target_url),
        Method::OPTIONS => client.request(Method::OPTIONS, target_url),
        _ => {
            warn!(method = %method, "Unsupported HTTP method in dynamic proxy");
            return (StatusCode::METHOD_NOT_ALLOWED, "Method not allowed").into_response();
        }
    };

    // Copy headers, excluding hop-by-hop headers
    req_builder = copy_headers(req_builder, &headers);

    // Inject W3C traceparent header for distributed tracing propagation.
    // This allows downstream services (Control-Plane API, backends) to
    // correlate their spans with the gateway's trace.
    req_builder = inject_traceparent(req_builder, trace_ctx);

    // Inject RFC 9110 §7.6.3 Via header for hop detection (CAB-1316 Phase 2)
    req_builder = req_builder.header("Via", hop_detection::build_via_value());

    // BYOK: inject resolved credential header (CAB-1250 + CAB-1317)
    if let Some((name, value)) = resolved_header {
        if let (Ok(header_name), Ok(header_value)) = (
            reqwest::header::HeaderName::from_bytes(name.as_bytes()),
            reqwest::header::HeaderValue::from_str(value),
        ) {
            req_builder = req_builder.header(header_name, header_value);
        }
    }

    // Forward body as a stream for methods that support it (zero-copy)
    if matches!(*method, Method::POST | Method::PUT | Method::PATCH) {
        let body_stream = request.into_body().into_data_stream();
        req_builder = req_builder.body(reqwest::Body::wrap_stream(body_stream));
    }

    // Send the request
    match req_builder.send().await {
        Ok(resp) => convert_response(resp),
        Err(e) => {
            error!(
                error = %e,
                target_url = %target_url,
                "Failed to forward request to backend"
            );

            if e.is_timeout() {
                (StatusCode::GATEWAY_TIMEOUT, "Gateway timeout").into_response()
            } else if e.is_connect() {
                (StatusCode::BAD_GATEWAY, "Failed to connect to upstream").into_response()
            } else {
                (StatusCode::BAD_GATEWAY, "Bad gateway").into_response()
            }
        }
    }
}

/// Copy headers excluding hop-by-hop headers.
///
/// reqwest 0.12 and axum 0.7 share the same `http` 1.0 types,
/// so HeaderName/HeaderValue can be cloned directly (no conversion needed).
fn copy_headers(
    mut builder: reqwest::RequestBuilder,
    headers: &HeaderMap<HeaderValue>,
) -> reqwest::RequestBuilder {
    for (name, value) in headers.iter() {
        if !is_hop_by_hop(name.as_str()) {
            builder = builder.header(name.clone(), value.clone());
        }
    }

    builder
}

/// O(1) hop-by-hop header check. HeaderName::as_str() is already lowercase.
fn is_hop_by_hop(name: &str) -> bool {
    matches!(
        name,
        "connection"
            | "keep-alive"
            | "proxy-authenticate"
            | "proxy-authorization"
            | "te"
            | "trailer"
            | "transfer-encoding"
            | "upgrade"
            | "host"
    )
}

/// Convert a reqwest response to an axum response (streaming, zero-copy).
///
/// reqwest 0.12 shares `http` 1.0 types with axum 0.7, so StatusCode
/// and HeaderName/HeaderValue pass through without conversion.
fn convert_response(resp: reqwest::Response) -> Response {
    let status = resp.status();
    let headers = resp.headers().clone();

    let mut response = Response::builder().status(status);

    // Copy response headers (excluding hop-by-hop) — direct clone, same types
    for (name, value) in headers.iter() {
        if !is_hop_by_hop(name.as_str()) {
            response = response.header(name.clone(), value.clone());
        }
    }

    // Stream the response body (no buffering)
    let body = Body::from_stream(resp.bytes_stream());

    response
        .body(body)
        .unwrap_or_else(|_| (StatusCode::INTERNAL_SERVER_ERROR, "Internal error").into_response())
}

/// Check if an HTTP status code is retryable (transient upstream error).
fn is_retryable_status(status: StatusCode) -> bool {
    matches!(status.as_u16(), 502 | 503)
}

/// Check if an HTTP method is idempotent (safe to retry without side effects).
fn is_idempotent(method: &Method) -> bool {
    matches!(
        *method,
        Method::GET | Method::HEAD | Method::DELETE | Method::OPTIONS
    )
}

/// Simple retry request for idempotent methods (no body).
///
/// Rebuilds the outgoing request from saved headers — used when the original
/// request body has already been consumed by the first attempt.
async fn retry_forward(
    method: &Method,
    target_url: &str,
    headers: &HeaderMap<HeaderValue>,
    resolved_header: Option<&(String, String)>,
    trace_ctx: Option<&crate::trace_context::RequestTraceContext>,
) -> Response {
    let client = get_proxy_client();
    let mut builder = match *method {
        Method::GET => client.get(target_url),
        Method::HEAD => client.head(target_url),
        Method::DELETE => client.delete(target_url),
        _ => {
            let m = reqwest::Method::from_bytes(method.as_str().as_bytes())
                .unwrap_or(reqwest::Method::GET);
            client.request(m, target_url)
        }
    };
    builder = copy_headers(builder, headers);
    builder = inject_traceparent(builder, trace_ctx);

    // BYOK: inject resolved credential header (CAB-1250 + CAB-1317)
    if let Some((name, value)) = resolved_header {
        if let (Ok(header_name), Ok(header_value)) = (
            reqwest::header::HeaderName::from_bytes(name.as_bytes()),
            reqwest::header::HeaderValue::from_str(value),
        ) {
            builder = builder.header(header_name, header_value);
        }
    }

    match builder.send().await {
        Ok(resp) => convert_response(resp),
        Err(e) => {
            if e.is_timeout() {
                (StatusCode::GATEWAY_TIMEOUT, "Gateway timeout").into_response()
            } else {
                (StatusCode::BAD_GATEWAY, "Bad gateway").into_response()
            }
        }
    }
}

/// Check if a URL targets a private/internal IP range (SSRF protection).
///
/// Blocks RFC 1918 private IPs, loopback, link-local (including AWS metadata
/// at 169.254.169.254), and IPv6 loopback/unique-local addresses.
///
/// This is defense-in-depth: backend URLs come from the Control Plane (admin-configured),
/// not from user input. But a compromised or misconfigured CP could still inject
/// internal targets, so we block them at the proxy level.
pub fn is_blocked_url(url: &str) -> bool {
    // Parse the URL to extract the host
    let parsed = match reqwest::Url::parse(url) {
        Ok(u) => u,
        Err(_) => return true, // Unparseable URL = blocked
    };

    let host = match parsed.host_str() {
        Some(h) => h,
        None => return true, // No host = blocked
    };

    // Try to parse as IP address (strip brackets for IPv6)
    let host_clean = host.trim_start_matches('[').trim_end_matches(']');
    if let Ok(ip) = host_clean.parse::<IpAddr>() {
        return is_blocked_ip(ip);
    }

    // Hostname "localhost" is always blocked
    if host == "localhost" {
        return true;
    }

    // Non-IP hostnames are allowed (DNS resolution happens at request time)
    false
}

/// Check if an IP address is in a blocked range.
fn is_blocked_ip(ip: IpAddr) -> bool {
    match ip {
        IpAddr::V4(v4) => {
            v4.is_loopback()               // 127.0.0.0/8
                || v4.is_private()          // 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16
                || v4.is_link_local()       // 169.254.0.0/16 (AWS metadata)
                || v4.is_unspecified()      // 0.0.0.0
                || v4.is_broadcast() // 255.255.255.255
        }
        IpAddr::V6(v6) => {
            v6.is_loopback()               // ::1
                || v6.is_unspecified()      // ::
                // Unique local (fd00::/8) — check first byte
                || (v6.segments()[0] & 0xfe00) == 0xfc00
        }
    }
}

/// Inject W3C Trace Context `traceparent` header into outgoing request.
///
/// When OTel is active (CAB-1374), propagates the current OTel span context
/// so downstream services share the same trace_id (visible in Tempo/Grafana).
///
/// CAB-1455 Phase 2: when an incoming RequestTraceContext is provided,
/// propagates the same trace_id with a fresh span_id (new hop in the chain).
///
/// Fallback (OTel disabled, no incoming context): generates random traceparent
/// using thread-local SmallRng to avoid `getrandom()` syscalls per request.
fn inject_traceparent(
    builder: reqwest::RequestBuilder,
    incoming_ctx: Option<&crate::trace_context::RequestTraceContext>,
) -> reqwest::RequestBuilder {
    #[cfg(feature = "otel")]
    {
        if crate::telemetry::is_otel_active() {
            use opentelemetry::propagation::TextMapPropagator;
            use opentelemetry_sdk::propagation::TraceContextPropagator;
            use tracing_opentelemetry::OpenTelemetrySpanExt;

            let cx = tracing::Span::current().context();
            let propagator = TraceContextPropagator::new();
            let mut inject_map = std::collections::HashMap::new();
            propagator.inject_context(&cx, &mut inject_map);

            let mut b = builder;
            for (key, value) in inject_map {
                b = b.header(key, value);
            }
            return b;
        }
    }

    // CAB-1455 Phase 2: propagate incoming trace_id with a fresh span_id so
    // the entire distributed trace chain shares one trace_id.
    if let Some(ctx) = incoming_ctx {
        let traceparent = TRACE_RNG.with(|rng| {
            let mut rng = rng.borrow_mut();
            let mut span_bytes = [0u8; 8];
            rng.fill(&mut span_bytes);
            let mut buf = String::with_capacity(55);
            buf.push_str("00-");
            buf.push_str(&ctx.trace_id);
            buf.push('-');
            hex_encode_into(&span_bytes, &mut buf);
            buf.push_str("-01");
            buf
        });
        return builder.header("traceparent", traceparent);
    }

    // Fallback: random traceparent (no OTel, no incoming context)
    // Optimized: single 24-byte RNG fill + direct hex write into pre-sized
    // buffer. Avoids 2 separate String allocations. (CAB-1332)
    let traceparent = TRACE_RNG.with(|rng| {
        let mut rng = rng.borrow_mut();
        let mut bytes = [0u8; 24]; // 16 trace + 8 span in one fill
        rng.fill(&mut bytes);

        // "00-" (3) + 32 hex (trace) + "-" (1) + 16 hex (span) + "-01" (3) = 55
        let mut buf = String::with_capacity(55);
        buf.push_str("00-");
        hex_encode_into(&bytes[..16], &mut buf);
        buf.push('-');
        hex_encode_into(&bytes[16..], &mut buf);
        buf.push_str("-01");
        buf
    });
    builder.header("traceparent", traceparent)
}

/// Extract the authenticated user's ID from request extensions.
///
/// Returns the `user_id` from the JWT-populated `AuthenticatedUser` extension,
/// or `"anonymous"` when no authenticated user is present (CAB-1389).
fn extract_user_id(extensions: &axum::http::Extensions) -> String {
    extensions
        .get::<crate::auth::middleware::AuthenticatedUser>()
        .map(|u| u.user_id.clone())
        .unwrap_or_else(|| "anonymous".to_string())
}

/// Encode bytes as lowercase hex directly into an existing String.
/// Zero extra allocation — writes into the caller's buffer.
fn hex_encode_into(bytes: &[u8], buf: &mut String) {
    const HEX_CHARS: &[u8; 16] = b"0123456789abcdef";
    for &b in bytes {
        buf.push(HEX_CHARS[(b >> 4) as usize] as char);
        buf.push(HEX_CHARS[(b & 0x0f) as usize] as char);
    }
}

#[cfg(test)]
mod tests {
    use axum::http::{Method, StatusCode};

    use super::*;

    #[test]
    fn test_is_retryable_status() {
        assert!(is_retryable_status(StatusCode::BAD_GATEWAY)); // 502
        assert!(is_retryable_status(StatusCode::SERVICE_UNAVAILABLE)); // 503
        assert!(!is_retryable_status(StatusCode::OK)); // 200
        assert!(!is_retryable_status(StatusCode::NOT_FOUND)); // 404
        assert!(!is_retryable_status(StatusCode::INTERNAL_SERVER_ERROR)); // 500
        assert!(!is_retryable_status(StatusCode::GATEWAY_TIMEOUT)); // 504
    }

    #[test]
    fn test_is_idempotent() {
        assert!(is_idempotent(&Method::GET));
        assert!(is_idempotent(&Method::HEAD));
        assert!(is_idempotent(&Method::DELETE));
        assert!(is_idempotent(&Method::OPTIONS));
        assert!(!is_idempotent(&Method::POST));
        assert!(!is_idempotent(&Method::PUT));
        assert!(!is_idempotent(&Method::PATCH));
    }

    #[test]
    fn test_is_hop_by_hop() {
        assert!(is_hop_by_hop("connection"));
        assert!(is_hop_by_hop("transfer-encoding"));
        assert!(is_hop_by_hop("host"));
        assert!(!is_hop_by_hop("content-type"));
        assert!(!is_hop_by_hop("authorization"));
    }

    #[test]
    fn test_ssrf_blocked_private_ips() {
        assert!(is_blocked_url("http://127.0.0.1:8080/api"));
        assert!(is_blocked_url("http://10.0.0.1/internal"));
        assert!(is_blocked_url("http://192.168.1.1/api"));
        assert!(is_blocked_url("http://localhost:3000"));
        assert!(!is_blocked_url("http://example.com/api"));
        assert!(!is_blocked_url("http://51.83.45.13:8080/health"));
    }

    #[test]
    fn test_traceparent_format() {
        let client = reqwest::Client::new();
        let builder = client.get("http://example.com");
        let builder = inject_traceparent(builder, None);
        // Build request to inspect headers
        let req = builder.build().expect("build request");
        let tp = req
            .headers()
            .get("traceparent")
            .expect("traceparent header")
            .to_str()
            .expect("valid string");

        // Format: 00-{32hex}-{16hex}-01
        let parts: Vec<&str> = tp.split('-').collect();
        assert_eq!(parts.len(), 4, "traceparent should have 4 parts");
        assert_eq!(parts[0], "00", "version should be 00");
        assert_eq!(parts[1].len(), 32, "trace-id should be 32 hex chars");
        assert_eq!(parts[2].len(), 16, "span-id should be 16 hex chars");
        assert_eq!(parts[3], "01", "flags should be 01 (sampled)");
    }

    #[test]
    fn test_extract_user_id_anonymous_fallback() {
        let extensions = axum::http::Extensions::new();
        let user_id = extract_user_id(&extensions);
        assert_eq!(user_id, "anonymous");
    }

    #[test]
    fn test_extract_user_id_from_authenticated_user() {
        use crate::auth::claims::Claims;
        use crate::auth::middleware::AuthenticatedUser;

        let user = AuthenticatedUser {
            user_id: "user-abc-123".to_string(),
            username: Some("alice".to_string()),
            email: None,
            tenant_id: Some("acme".to_string()),
            claims: Claims {
                sub: "user-abc-123".to_string(),
                exp: 9999999999,
                iat: 0,
                iss: "https://auth.example.com".to_string(),
                aud: Default::default(),
                azp: None,
                preferred_username: Some("alice".to_string()),
                email: None,
                email_verified: None,
                name: None,
                given_name: None,
                family_name: None,
                tenant: None,
                realm_access: None,
                resource_access: None,
                sid: None,
                typ: None,
                scope: None,
                cnf: None,
                sub_account_id: None,
                master_account_id: None,
            },
            raw_token: "test.jwt.token".to_string(),
        };

        let mut extensions = axum::http::Extensions::new();
        extensions.insert(user);

        let user_id = extract_user_id(&extensions);
        assert_eq!(user_id, "user-abc-123");
    }

    #[test]
    fn test_traceparent_uniqueness() {
        let client = reqwest::Client::new();

        let b1 = inject_traceparent(client.get("http://example.com"), None);
        let b2 = inject_traceparent(client.get("http://example.com"), None);

        let r1 = b1.build().expect("build");
        let r2 = b2.build().expect("build");

        let tp1 = r1.headers().get("traceparent").unwrap().to_str().unwrap();
        let tp2 = r2.headers().get("traceparent").unwrap().to_str().unwrap();

        assert_ne!(tp1, tp2, "each request should get a unique traceparent");
    }

    #[test]
    fn test_traceparent_propagation_preserves_trace_id() {
        let incoming = crate::trace_context::RequestTraceContext {
            trace_id: "4bf92f3577b34da6a3ce929d0e0e4736".to_string(),
            parent_span_id: "00f067aa0ba902b7".to_string(),
            traceparent: "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01".to_string(),
        };

        let client = reqwest::Client::new();
        let builder = inject_traceparent(client.get("http://example.com"), Some(&incoming));
        let req = builder.build().expect("build request");
        let tp = req
            .headers()
            .get("traceparent")
            .expect("traceparent header")
            .to_str()
            .expect("valid string");

        let parts: Vec<&str> = tp.split('-').collect();
        assert_eq!(parts.len(), 4);
        assert_eq!(parts[0], "00", "version preserved");
        assert_eq!(
            parts[1], "4bf92f3577b34da6a3ce929d0e0e4736",
            "trace_id must be propagated from incoming context"
        );
        assert_eq!(parts[2].len(), 16, "span_id is 16 hex chars");
        assert_ne!(
            parts[2], "00f067aa0ba902b7",
            "span_id must differ from incoming (new hop)"
        );
        assert_eq!(parts[3], "01", "flags sampled");
    }

    #[test]
    fn test_traceparent_propagation_unique_span_ids() {
        let incoming = crate::trace_context::RequestTraceContext {
            trace_id: "abcdef1234567890abcdef1234567890".to_string(),
            parent_span_id: "1111111111111111".to_string(),
            traceparent: "00-abcdef1234567890abcdef1234567890-1111111111111111-01".to_string(),
        };

        let client = reqwest::Client::new();
        let b1 = inject_traceparent(client.get("http://example.com"), Some(&incoming));
        let b2 = inject_traceparent(client.get("http://example.com"), Some(&incoming));

        let r1 = b1.build().expect("build");
        let r2 = b2.build().expect("build");

        let tp1 = r1.headers().get("traceparent").unwrap().to_str().unwrap();
        let tp2 = r2.headers().get("traceparent").unwrap().to_str().unwrap();

        let span1 = tp1.split('-').nth(2).unwrap();
        let span2 = tp2.split('-').nth(2).unwrap();

        // Same trace_id for both
        assert_eq!(
            tp1.split('-').nth(1).unwrap(),
            tp2.split('-').nth(1).unwrap(),
            "both should share the same trace_id"
        );
        // Different span_ids
        assert_ne!(span1, span2, "each call must generate a unique span_id");
    }
}
