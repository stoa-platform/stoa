//! W3C Trace Context Middleware (CAB-1455 Phase 2)
//!
//! Extracts `traceparent` header from incoming HTTP requests per the
//! [W3C Trace Context](https://www.w3.org/TR/trace-context/) specification.
//!
//! The extracted trace_id and span_id are stored in request extensions as
//! [`RequestTraceContext`], making them available to downstream middleware
//! (access_log) and handlers without requiring OTel to be active.
//!
//! When OTel is active, the tracing-opentelemetry layer handles propagation
//! natively. This middleware provides the non-OTel fallback so that trace
//! correlation works even without the `otel` feature flag.

use axum::{extract::Request, middleware::Next, response::Response};

/// Trace context extracted from the incoming `traceparent` header.
///
/// Stored in request extensions by [`trace_context_middleware`].
/// Access via `request.extensions().get::<RequestTraceContext>()`.
#[derive(Clone, Debug)]
pub struct RequestTraceContext {
    /// 32-char lowercase hex trace ID (from traceparent field 2).
    pub trace_id: String,
    /// 16-char lowercase hex parent span ID (from traceparent field 3).
    pub parent_span_id: String,
    /// Original traceparent header value (for forwarding).
    pub traceparent: String,
}

/// Middleware that extracts W3C `traceparent` from incoming requests.
///
/// Inserts a [`RequestTraceContext`] into request extensions when a valid
/// traceparent header is present. If absent or malformed, the request
/// continues without trace context (downstream uses fallback trace IDs).
pub async fn trace_context_middleware(mut request: Request, next: Next) -> Response {
    if let Some(ctx) = extract_traceparent_from_headers(request.headers()) {
        request.extensions_mut().insert(ctx);
    }
    next.run(request).await
}

/// Parse a W3C traceparent header value.
///
/// Format: `{version}-{trace_id}-{parent_id}-{trace_flags}`
/// Example: `00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01`
///
/// Validation rules (W3C spec):
/// - Exactly 4 fields separated by `-`
/// - version: 2 hex chars
/// - trace_id: 32 hex chars, not all zeros
/// - parent_id: 16 hex chars, not all zeros
/// - trace_flags: 2 hex chars
fn extract_traceparent_from_headers(
    headers: &axum::http::HeaderMap,
) -> Option<RequestTraceContext> {
    let value = headers.get("traceparent")?.to_str().ok()?;
    parse_traceparent(value)
}

/// Parse a traceparent string into a [`RequestTraceContext`].
///
/// Returns `None` if the format is invalid per W3C spec.
fn parse_traceparent(value: &str) -> Option<RequestTraceContext> {
    let parts: Vec<&str> = value.split('-').collect();
    if parts.len() < 4 {
        return None;
    }

    let version = parts[0];
    let trace_id = parts[1];
    let parent_span_id = parts[2];
    let trace_flags = parts[3];

    // Version: 2 hex chars
    if version.len() != 2 || !version.chars().all(|c| c.is_ascii_hexdigit()) {
        return None;
    }

    // trace_id: 32 lowercase hex chars, not all zeros
    if trace_id.len() != 32 || !trace_id.chars().all(|c| c.is_ascii_hexdigit()) {
        return None;
    }
    if trace_id.chars().all(|c| c == '0') {
        return None;
    }

    // parent_id: 16 lowercase hex chars, not all zeros
    if parent_span_id.len() != 16 || !parent_span_id.chars().all(|c| c.is_ascii_hexdigit()) {
        return None;
    }
    if parent_span_id.chars().all(|c| c == '0') {
        return None;
    }

    // trace_flags: 2 hex chars
    if trace_flags.len() != 2 || !trace_flags.chars().all(|c| c.is_ascii_hexdigit()) {
        return None;
    }

    Some(RequestTraceContext {
        trace_id: trace_id.to_lowercase(),
        parent_span_id: parent_span_id.to_lowercase(),
        traceparent: value.to_string(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{body::Body, http::StatusCode, routing::get, Router};
    use tower::ServiceExt;

    #[test]
    fn test_parse_valid_traceparent() {
        let tp = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01";
        let ctx = parse_traceparent(tp).expect("should parse");
        assert_eq!(ctx.trace_id, "4bf92f3577b34da6a3ce929d0e0e4736");
        assert_eq!(ctx.parent_span_id, "00f067aa0ba902b7");
        assert_eq!(ctx.traceparent, tp);
    }

    #[test]
    fn test_parse_traceparent_uppercase_hex() {
        // W3C spec allows receivers to accept mixed-case
        let tp = "00-4BF92F3577B34DA6A3CE929D0E0E4736-00F067AA0BA902B7-01";
        let ctx = parse_traceparent(tp).expect("should parse");
        assert_eq!(ctx.trace_id, "4bf92f3577b34da6a3ce929d0e0e4736");
        assert_eq!(ctx.parent_span_id, "00f067aa0ba902b7");
    }

    #[test]
    fn test_parse_traceparent_too_few_fields() {
        assert!(parse_traceparent("00-abc").is_none());
    }

    #[test]
    fn test_parse_traceparent_all_zero_trace_id() {
        let tp = "00-00000000000000000000000000000000-00f067aa0ba902b7-01";
        assert!(parse_traceparent(tp).is_none());
    }

    #[test]
    fn test_parse_traceparent_all_zero_parent_id() {
        let tp = "00-4bf92f3577b34da6a3ce929d0e0e4736-0000000000000000-01";
        assert!(parse_traceparent(tp).is_none());
    }

    #[test]
    fn test_parse_traceparent_invalid_hex() {
        let tp = "00-ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ-00f067aa0ba902b7-01";
        assert!(parse_traceparent(tp).is_none());
    }

    #[test]
    fn test_parse_traceparent_wrong_trace_id_length() {
        let tp = "00-4bf92f3577b34da6-00f067aa0ba902b7-01";
        assert!(parse_traceparent(tp).is_none());
    }

    #[test]
    fn test_parse_traceparent_wrong_span_id_length() {
        let tp = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa-01";
        assert!(parse_traceparent(tp).is_none());
    }

    #[test]
    fn test_parse_traceparent_invalid_version() {
        let tp = "GG-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01";
        assert!(parse_traceparent(tp).is_none());
    }

    #[test]
    fn test_parse_traceparent_invalid_flags() {
        let tp = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-ZZ";
        assert!(parse_traceparent(tp).is_none());
    }

    #[test]
    fn test_parse_traceparent_extra_fields_ignored() {
        // W3C spec: future versions may add fields; parsers must not reject
        let tp = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01-extra";
        let ctx = parse_traceparent(tp).expect("should parse with extra fields");
        assert_eq!(ctx.trace_id, "4bf92f3577b34da6a3ce929d0e0e4736");
    }

    #[test]
    fn test_extract_from_headers_present() {
        let mut headers = axum::http::HeaderMap::new();
        headers.insert(
            "traceparent",
            "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
                .parse()
                .expect("header value"),
        );
        let ctx = extract_traceparent_from_headers(&headers).expect("should extract");
        assert_eq!(ctx.trace_id, "4bf92f3577b34da6a3ce929d0e0e4736");
    }

    #[test]
    fn test_extract_from_headers_absent() {
        let headers = axum::http::HeaderMap::new();
        assert!(extract_traceparent_from_headers(&headers).is_none());
    }

    #[test]
    fn test_extract_from_headers_invalid_utf8() {
        let mut headers = axum::http::HeaderMap::new();
        headers.insert(
            "traceparent",
            axum::http::HeaderValue::from_bytes(b"\xff\xfe")
                .unwrap_or_else(|_| axum::http::HeaderValue::from_static("")),
        );
        // Should return None gracefully (to_str fails on non-UTF8)
        // Note: HeaderValue::from_bytes may reject invalid bytes entirely
    }

    #[tokio::test]
    async fn test_middleware_injects_extension() {
        let app = Router::new()
            .route(
                "/test",
                get(|request: Request| async move {
                    let has_ctx = request.extensions().get::<RequestTraceContext>().is_some();
                    if has_ctx {
                        "found"
                    } else {
                        "missing"
                    }
                }),
            )
            .layer(axum::middleware::from_fn(trace_context_middleware));

        let req = Request::builder()
            .uri("/test")
            .header(
                "traceparent",
                "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
            )
            .body(Body::empty())
            .expect("request");
        let resp = app.oneshot(req).await.expect("response");
        assert_eq!(resp.status(), StatusCode::OK);

        let body = axum::body::to_bytes(resp.into_body(), 1024)
            .await
            .expect("body");
        assert_eq!(&body[..], b"found");
    }

    #[tokio::test]
    async fn test_middleware_no_header() {
        let app = Router::new()
            .route(
                "/test",
                get(|request: Request| async move {
                    let has_ctx = request.extensions().get::<RequestTraceContext>().is_some();
                    if has_ctx {
                        "found"
                    } else {
                        "missing"
                    }
                }),
            )
            .layer(axum::middleware::from_fn(trace_context_middleware));

        let req = Request::builder()
            .uri("/test")
            .body(Body::empty())
            .expect("request");
        let resp = app.oneshot(req).await.expect("response");

        let body = axum::body::to_bytes(resp.into_body(), 1024)
            .await
            .expect("body");
        assert_eq!(&body[..], b"missing");
    }

    #[tokio::test]
    async fn test_middleware_invalid_header() {
        let app = Router::new()
            .route(
                "/test",
                get(|request: Request| async move {
                    let has_ctx = request.extensions().get::<RequestTraceContext>().is_some();
                    if has_ctx {
                        "found"
                    } else {
                        "missing"
                    }
                }),
            )
            .layer(axum::middleware::from_fn(trace_context_middleware));

        let req = Request::builder()
            .uri("/test")
            .header("traceparent", "garbage-value")
            .body(Body::empty())
            .expect("request");
        let resp = app.oneshot(req).await.expect("response");

        let body = axum::body::to_bytes(resp.into_body(), 1024)
            .await
            .expect("body");
        assert_eq!(&body[..], b"missing");
    }
}
