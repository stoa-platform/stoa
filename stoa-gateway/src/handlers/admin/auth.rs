//! Bearer-token admin authentication middleware.

use axum::{
    body::Body,
    extract::State,
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
