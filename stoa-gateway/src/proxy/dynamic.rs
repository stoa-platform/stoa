//! Dynamic proxy handler for Control Plane managed API routes.
//!
//! Catch-all fallback: looks up the request path in RouteRegistry,
//! proxies to the matched backend if found, returns 404 otherwise.

use axum::{
    body::Body,
    extract::{Request, State},
    http::{header, HeaderMap, HeaderValue, Method, StatusCode},
    response::{IntoResponse, Response},
};
use std::net::IpAddr;
use std::time::Duration;
use tracing::{debug, error, instrument, warn};

use crate::state::AppState;

/// Shared reqwest client for dynamic proxy (created once, reused).
static PROXY_CLIENT: std::sync::OnceLock<reqwest::Client> = std::sync::OnceLock::new();

fn get_proxy_client() -> &'static reqwest::Client {
    PROXY_CLIENT.get_or_init(|| {
        reqwest::Client::builder()
            .timeout(Duration::from_secs(30))
            .connect_timeout(Duration::from_secs(5))
            .pool_max_idle_per_host(128)
            .pool_idle_timeout(Duration::from_secs(90))
            .tcp_keepalive(Duration::from_secs(60))
            .tcp_nodelay(true)
            .http2_keep_alive_interval(Duration::from_secs(30))
            .http2_keep_alive_timeout(Duration::from_secs(10))
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
    let method_str = method.to_string();
    if !route.methods.is_empty() && !route.methods.contains(&method_str) {
        return (
            StatusCode::METHOD_NOT_ALLOWED,
            "Method not allowed for this API",
        )
            .into_response();
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

    let upstream_start = std::time::Instant::now();
    let response = forward_request(request, &method, &target_url).await;
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

    response
}

/// Forward request to the backend, reusing the webMethods proxy pattern.
async fn forward_request(request: Request<Body>, method: &Method, target_url: &str) -> Response {
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
        Method::OPTIONS => {
            let m = reqwest::Method::from_bytes(b"OPTIONS").unwrap();
            client.request(m, target_url)
        }
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
    req_builder = inject_traceparent(req_builder);

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
/// HeaderName is already lowercase in http crate, so no `.to_lowercase()` needed.
fn copy_headers(
    mut builder: reqwest::RequestBuilder,
    headers: &HeaderMap<HeaderValue>,
) -> reqwest::RequestBuilder {
    for (name, value) in headers.iter() {
        if !is_hop_by_hop(name.as_str()) {
            if let Ok(header_name) = reqwest::header::HeaderName::from_bytes(name.as_ref()) {
                if let Ok(header_value) = reqwest::header::HeaderValue::from_bytes(value.as_bytes())
                {
                    builder = builder.header(header_name, header_value);
                }
            }
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
fn convert_response(resp: reqwest::Response) -> Response {
    let status = resp.status();
    let headers = resp.headers().clone();

    let mut response =
        Response::builder().status(StatusCode::from_u16(status.as_u16()).unwrap_or(StatusCode::OK));

    // Copy response headers (excluding hop-by-hop)
    for (name, value) in headers.iter() {
        if !is_hop_by_hop(name.as_str()) {
            if let Ok(header_name) = header::HeaderName::from_bytes(name.as_ref()) {
                if let Ok(header_value) = header::HeaderValue::from_bytes(value.as_bytes()) {
                    response = response.header(header_name, header_value);
                }
            }
        }
    }

    // Stream the response body (no buffering)
    let body = Body::from_stream(resp.bytes_stream());

    response
        .body(body)
        .unwrap_or_else(|_| (StatusCode::INTERNAL_SERVER_ERROR, "Internal error").into_response())
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
/// Format: `00-{trace_id}-{span_id}-{flags}`
/// This propagates the current trace context to downstream services,
/// enabling end-to-end distributed tracing visible in Tempo/Grafana.
/// TODO: Re-enable traceparent injection once OpenTelemetry deps are stabilized (CAB-1088).
fn inject_traceparent(builder: reqwest::RequestBuilder) -> reqwest::RequestBuilder {
    // Disabled: opentelemetry crate removed pending API stabilization
    builder
}
