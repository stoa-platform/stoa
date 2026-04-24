//! Bearer-token admin authentication middleware + pre-auth rate-limit.

use std::net::SocketAddr;

use axum::{
    body::Body,
    extract::{ConnectInfo, State},
    http::{header::AUTHORIZATION, Request, StatusCode},
    middleware::Next,
    response::{IntoResponse, Response},
};
use subtle::ConstantTimeEq;
use tracing::warn;

use crate::state::AppState;

/// Bearer token authentication for admin API.
///
/// Validates the `Authorization: Bearer <token>` header against
/// `config.admin_api_token`. If no token is configured, returns 503
/// (admin API disabled -- no token configured).
///
/// Comparison is performed in constant time via `subtle::ConstantTimeEq`
/// (GW-1 P0-1): prevents byte-by-byte timing-leak brute-force of the
/// admin token. The length pre-check is a deliberate early-exit that
/// leaks only the token length, which is not secret-derived.
pub async fn admin_auth(
    State(state): State<AppState>,
    request: Request<Body>,
    next: Next,
) -> Result<Response, Response> {
    let expected = match state.config.admin_api_token.as_deref() {
        Some(token) if !token.is_empty() => token,
        _ => {
            warn!("Admin API request rejected: no admin_api_token configured");
            return Err((
                StatusCode::SERVICE_UNAVAILABLE,
                "Admin API disabled - no admin_api_token configured",
            )
                .into_response());
        }
    };

    let auth_header = request
        .headers()
        .get(AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");

    let expected_header = format!("Bearer {}", expected);

    let matches = auth_header.len() == expected_header.len()
        && auth_header
            .as_bytes()
            .ct_eq(expected_header.as_bytes())
            .into();

    if matches {
        Ok(next.run(request).await)
    } else {
        warn!("Admin API request rejected: invalid bearer token");
        Err(StatusCode::UNAUTHORIZED.into_response())
    }
}

/// Per-peer rate limit for the admin API, applied **before** `admin_auth`
/// (GW-1 P1-3-lite). Keyed by `admin:<peer_ip>` in the shared
/// `state.rate_limiter` so admin buckets stay separate from tenant ones.
///
/// Without this gate, the bearer-token compare (even in constant time)
/// can be probed as fast as the network allows — the compare cost is
/// fixed, not the request cadence. This middleware caps requests per
/// peer IP at the configured default tenant rate (`rate_limit_default`).
///
/// Fail-open when `ConnectInfo` is missing (local tests, unusual
/// transport configs). In prod, `main.rs` wires
/// `into_make_service_with_connect_info::<SocketAddr>`, so the
/// extension is always present.
pub async fn admin_rate_limit(
    State(state): State<AppState>,
    request: Request<Body>,
    next: Next,
) -> Result<Response, Response> {
    let peer_ip = request
        .extensions()
        .get::<ConnectInfo<SocketAddr>>()
        .map(|ci| ci.0.ip());

    if let Some(ip) = peer_ip {
        let key = format!("admin:{}", ip);
        let result = state.rate_limiter.check(&key);
        if !result.allowed {
            warn!(peer = %ip, "Admin API request rate-limited");
            let mut response = (
                StatusCode::TOO_MANY_REQUESTS,
                axum::Json(serde_json::json!({
                    "status": "error",
                    "message": "Admin API rate limit exceeded",
                })),
            )
                .into_response();
            // Surface X-RateLimit-* headers built by RateLimitResult.
            for (name, value) in result.headers() {
                if let Ok(val) = value.parse() {
                    response.headers_mut().insert(name, val);
                }
            }
            return Err(response);
        }
    }

    Ok(next.run(request).await)
}

#[cfg(test)]
mod tests {
    use axum::{
        body::Body,
        http::{Request, StatusCode},
    };
    use tower::ServiceExt;

    use crate::handlers::admin::test_helpers::{build_admin_router, create_test_state};

    #[tokio::test]
    async fn test_admin_auth_valid_token() {
        let state = create_test_state(Some("test-secret"));
        let app = build_admin_router(state);

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/health")
                    .header("Authorization", "Bearer test-secret")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_admin_auth_invalid_token() {
        let state = create_test_state(Some("test-secret"));
        let app = build_admin_router(state);

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/health")
                    .header("Authorization", "Bearer wrong-token")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn test_admin_auth_no_token_configured() {
        let state = create_test_state(None);
        let app = build_admin_router(state);

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/health")
                    .header("Authorization", "Bearer anything")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
    }

    #[tokio::test]
    async fn test_admin_auth_missing_header() {
        let state = create_test_state(Some("secret"));
        let app = build_admin_router(state);
        let response = app
            .oneshot(
                Request::builder()
                    .uri("/health")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    // GW-1 P0-1 regression: constant-time comparison — wrong byte at same length
    // must not leak information via early-exit memcmp.
    #[tokio::test]
    async fn test_admin_auth_same_length_wrong_byte() {
        let state = create_test_state(Some("abcdefghij"));
        let app = build_admin_router(state);
        // Header len == "Bearer abcdefghij" len, last byte differs.
        let response = app
            .oneshot(
                Request::builder()
                    .uri("/health")
                    .header("Authorization", "Bearer abcdefghiX")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    // GW-1 P0-1 regression: the length-based short-circuit must reject
    // tokens of different lengths without invoking byte comparison.
    #[tokio::test]
    async fn test_admin_auth_wrong_length_is_rejected() {
        let state = create_test_state(Some("long-secret-1234"));
        let app = build_admin_router(state);
        let response = app
            .oneshot(
                Request::builder()
                    .uri("/health")
                    .header("Authorization", "Bearer short")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    // GW-1 P0-2 regression: /admin/api-proxy/backends must live behind
    // admin_auth (previously orphaned on edge_base). This builds the
    // endpoint with the same auth layer as the production admin_router
    // and asserts anonymous requests get 401.
    #[tokio::test]
    async fn regression_api_proxy_backends_behind_admin_auth_401_anon() {
        use crate::proxy::list_api_proxy_backends;
        use axum::{middleware, routing::get as axum_get, Router};

        let state = create_test_state(Some("secret"));
        let router: Router = Router::new()
            .route("/api-proxy/backends", axum_get(list_api_proxy_backends))
            .layer(middleware::from_fn_with_state(
                state.clone(),
                super::admin_auth,
            ))
            .with_state(state);

        // Anonymous request (no Authorization header) must be rejected.
        let response = router
            .oneshot(
                Request::builder()
                    .uri("/api-proxy/backends")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn test_api_proxy_backends_behind_admin_auth_200_with_token() {
        use crate::proxy::list_api_proxy_backends;
        use axum::{middleware, routing::get as axum_get, Router};

        let state = create_test_state(Some("secret"));
        let router: Router = Router::new()
            .route("/api-proxy/backends", axum_get(list_api_proxy_backends))
            .layer(middleware::from_fn_with_state(
                state.clone(),
                super::admin_auth,
            ))
            .with_state(state);

        let response = router
            .oneshot(
                Request::builder()
                    .uri("/api-proxy/backends")
                    .header("Authorization", "Bearer secret")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

    // GW-1 P1-3-lite: per-IP pre-auth rate-limit must reject once the
    // bucket is exhausted, so byte-by-byte probing stays bounded.
    #[tokio::test]
    async fn regression_admin_rate_limit_returns_429_once_bucket_is_full() {
        use axum::{extract::ConnectInfo, middleware, routing::get as axum_get, Router};
        use std::net::{IpAddr, Ipv4Addr, SocketAddr};

        // Low bucket so the test runs fast (2 requests/60s).
        let mut config = crate::config::Config {
            admin_api_token: Some("secret".into()),
            ..crate::config::Config::default()
        };
        config.rate_limit_default = Some(2);
        config.rate_limit_window_seconds = Some(60);
        let state = crate::state::AppState::new(config);

        let router: Router = Router::new()
            .route("/health", axum_get(super::super::admin_health))
            // Only the rate-limit layer is under test here.
            .layer(middleware::from_fn_with_state(
                state.clone(),
                super::admin_rate_limit,
            ))
            .with_state(state);

        let peer: SocketAddr = (IpAddr::V4(Ipv4Addr::new(10, 0, 0, 42)), 12345).into();

        // 2 allowed requests.
        for _ in 0..2 {
            let mut req = Request::builder()
                .uri("/health")
                .body(Body::empty())
                .unwrap();
            req.extensions_mut().insert(ConnectInfo(peer));
            let resp = router.clone().oneshot(req).await.unwrap();
            assert_eq!(resp.status(), StatusCode::OK);
        }
        // 3rd must be throttled.
        let mut req = Request::builder()
            .uri("/health")
            .body(Body::empty())
            .unwrap();
        req.extensions_mut().insert(ConnectInfo(peer));
        let resp = router.oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::TOO_MANY_REQUESTS);
    }

    // GW-1 P1-3-lite: absent ConnectInfo (e.g. test harnesses without
    // `into_make_service_with_connect_info`), the middleware must fail
    // open — admin_auth is still the hard gate, we don't want to
    // accidentally 429 every request in tests.
    #[tokio::test]
    async fn test_admin_rate_limit_fails_open_without_connect_info() {
        use axum::{middleware, routing::get as axum_get, Router};

        let state = create_test_state(Some("secret"));
        let router: Router = Router::new()
            .route("/health", axum_get(super::super::admin_health))
            .layer(middleware::from_fn_with_state(
                state.clone(),
                super::admin_rate_limit,
            ))
            .with_state(state);

        // No ConnectInfo, lots of requests — none should be throttled.
        for _ in 0..5 {
            let resp = router
                .clone()
                .oneshot(
                    Request::builder()
                        .uri("/health")
                        .body(Body::empty())
                        .unwrap(),
                )
                .await
                .unwrap();
            assert_eq!(resp.status(), StatusCode::OK);
        }
    }

    #[tokio::test]
    async fn test_admin_auth_empty_configured_token() {
        let state = create_test_state(Some(""));
        let app = build_admin_router(state);
        let response = app
            .oneshot(
                Request::builder()
                    .uri("/health")
                    .header("Authorization", "Bearer ")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        // Empty token = disabled
        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
    }
}
