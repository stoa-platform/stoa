//! Security headers middleware.
//!
//! Adds standard security headers to every HTTP response:
//! - X-Content-Type-Options: nosniff
//! - X-Frame-Options: DENY
//! - X-XSS-Protection: 0 (disable legacy XSS filter — modern best practice)
//! - Referrer-Policy: strict-origin-when-cross-origin
//! - Permissions-Policy: camera=(), microphone=(), geolocation=()

use axum::extract::Request;
use axum::http::{HeaderName, HeaderValue};
use axum::middleware::Next;
use axum::response::Response;
use once_cell::sync::Lazy;

/// Pre-computed security header pairs — built once at startup, cloned per response.
/// Avoids per-request string parsing and HeaderValue::from_static() allocation.
static SECURITY_HEADERS: Lazy<Vec<(HeaderName, HeaderValue)>> = Lazy::new(|| {
    vec![
        (
            HeaderName::from_static("x-content-type-options"),
            HeaderValue::from_static("nosniff"),
        ),
        (
            HeaderName::from_static("x-frame-options"),
            HeaderValue::from_static("DENY"),
        ),
        (
            HeaderName::from_static("x-xss-protection"),
            HeaderValue::from_static("0"),
        ),
        (
            HeaderName::from_static("referrer-policy"),
            HeaderValue::from_static("strict-origin-when-cross-origin"),
        ),
        (
            HeaderName::from_static("permissions-policy"),
            HeaderValue::from_static("camera=(), microphone=(), geolocation=()"),
        ),
    ]
});

/// Middleware that adds security headers to every response.
pub async fn security_headers_middleware(request: Request, next: Next) -> Response {
    let mut response = next.run(request).await;
    let headers = response.headers_mut();

    for (name, value) in SECURITY_HEADERS.iter() {
        headers.insert(name.clone(), value.clone());
    }

    response
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{body::Body, http::Request, middleware, routing::get, Router};
    use tower::ServiceExt;

    async fn dummy_handler() -> &'static str {
        "ok"
    }

    fn app() -> Router {
        Router::new()
            .route("/test", get(dummy_handler))
            .layer(middleware::from_fn(security_headers_middleware))
    }

    fn test_request() -> Request<Body> {
        Request::builder().uri("/test").body(Body::empty()).unwrap()
    }

    #[tokio::test]
    async fn adds_x_content_type_options() {
        let resp = app().oneshot(test_request()).await.unwrap();
        assert_eq!(
            resp.headers().get("x-content-type-options").unwrap(),
            "nosniff"
        );
    }

    #[tokio::test]
    async fn adds_x_frame_options() {
        let resp = app().oneshot(test_request()).await.unwrap();
        assert_eq!(resp.headers().get("x-frame-options").unwrap(), "DENY");
    }

    #[tokio::test]
    async fn adds_xss_protection_disabled() {
        let resp = app().oneshot(test_request()).await.unwrap();
        assert_eq!(resp.headers().get("x-xss-protection").unwrap(), "0");
    }

    #[tokio::test]
    async fn adds_referrer_policy() {
        let resp = app().oneshot(test_request()).await.unwrap();
        assert_eq!(
            resp.headers().get("referrer-policy").unwrap(),
            "strict-origin-when-cross-origin"
        );
    }

    #[tokio::test]
    async fn adds_permissions_policy() {
        let resp = app().oneshot(test_request()).await.unwrap();
        assert_eq!(
            resp.headers().get("permissions-policy").unwrap(),
            "camera=(), microphone=(), geolocation=()"
        );
    }
}
