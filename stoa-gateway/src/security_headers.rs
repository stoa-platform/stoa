//! Security headers middleware.
//!
//! Adds standard security headers to every HTTP response:
//! - X-Content-Type-Options: nosniff
//! - X-Frame-Options: DENY
//! - X-XSS-Protection: 0 (disable legacy XSS filter — modern best practice)
//! - Referrer-Policy: strict-origin-when-cross-origin
//! - Permissions-Policy: camera=(), microphone=(), geolocation=()

use axum::{extract::Request, middleware::Next, response::Response};

/// Middleware that adds security headers to every response.
pub async fn security_headers_middleware(request: Request, next: Next) -> Response {
    let mut response = next.run(request).await;
    let headers = response.headers_mut();

    headers.insert(
        "x-content-type-options",
        "nosniff".parse().expect("valid header value"),
    );
    headers.insert(
        "x-frame-options",
        "DENY".parse().expect("valid header value"),
    );
    headers.insert("x-xss-protection", "0".parse().expect("valid header value"));
    headers.insert(
        "referrer-policy",
        "strict-origin-when-cross-origin"
            .parse()
            .expect("valid header value"),
    );
    headers.insert(
        "permissions-policy",
        "camera=(), microphone=(), geolocation=()"
            .parse()
            .expect("valid header value"),
    );

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
