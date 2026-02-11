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
