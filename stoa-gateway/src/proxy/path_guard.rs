//! Reject ambiguous paths and hide every non-API route from a reverse proxy.
//!
//! ingress-nginx forwards the original request target. A path such as
//! `/apis/../admin` or `/apis/%2e%2e/admin` must not be normalised onto
//! `/admin` (that would be a 401 from the admin bearer check). A proxied
//! request is public only for `/apis` and `/apis/...`. `/admin`, `/metrics`,
//! `/mcp`, `/oauth/register`, and `/v1/messages` stay on the pod and are
//! reachable without `X-Forwarded-For` / `X-Forwarded-Host` (kubelet probes,
//! ClusterIP, port-forward).

use axum::body::Body;
use axum::http::{Request, StatusCode};
use axum::middleware::Next;
use axum::response::{IntoResponse, Response};

/// True when the path can be read as a traversal, a double slash, or an
/// encoded `.` / `/` / `\`.
pub fn ambiguous_path(raw: &str) -> bool {
    if raw.is_empty() || looks_encoded(raw) {
        return true;
    }
    let mut current = raw.to_string();
    for _ in 0..3 {
        let decoded = match urlencoding::decode(&current) {
            Ok(value) => value.into_owned(),
            Err(_) => return true,
        };
        if looks_encoded(&decoded) {
            return true;
        }
        if decoded == current {
            break;
        }
        current = decoded;
    }
    false
}

fn looks_encoded(path: &str) -> bool {
    let lower = path.to_ascii_lowercase();
    path.contains("//")
        || path.contains('\\')
        || path.contains("..")
        || lower.contains("%2e")
        || lower.contains("%2f")
        || lower.contains("%5c")
        || lower.contains("%00")
}

/// The only path a reverse proxy is allowed to deliver.
pub fn is_public_api_path(path: &str) -> bool {
    path == "/apis" || path.starts_with("/apis/")
}

fn forwarded_by_proxy(request: &Request<Body>) -> bool {
    request.headers().get("x-forwarded-for").is_some()
        || request.headers().get("x-forwarded-host").is_some()
}

/// Outermost HTTP guard. Ambiguous paths are 400. A proxied request whose
/// path is not under `/apis` is 404, before admin auth can answer 401.
pub async fn public_surface_middleware(request: Request<Body>, next: Next) -> Response {
    let path = request.uri().path();
    if ambiguous_path(path) {
        return (StatusCode::BAD_REQUEST, "ambiguous path").into_response();
    }
    if forwarded_by_proxy(&request) && !is_public_api_path(path) {
        return StatusCode::NOT_FOUND.into_response();
    }
    next.run(request).await
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::Body;
    use axum::http::{Request, StatusCode};
    use axum::routing::get;
    use axum::Router;
    use tower::ServiceExt;

    #[test]
    fn traversal_forms_are_ambiguous() {
        for path in [
            "/apis/../admin/health",
            "/apis/%2e%2e/admin/health",
            "/apis/%2E%2E/admin/health",
            "//admin/health",
            "/apis/..%2fadmin/health",
            "/apis/%2fadmin/health",
            "/apis/%252e%252e/admin",
        ] {
            assert!(ambiguous_path(path), "{path}");
        }
        assert!(!ambiguous_path("/apis/demo/live-api/ping"));
        assert!(!ambiguous_path("/admin/health"));
    }

    async fn ok() -> StatusCode {
        StatusCode::OK
    }

    #[tokio::test]
    async fn proxied_traversal_and_private_paths_never_hit_the_handler() {
        let app = Router::new()
            .route("/admin/health", get(ok))
            .route("/admin/contracts", get(ok))
            .route("/metrics", get(ok))
            .route("/mcp", get(ok))
            .route("/oauth/register", get(ok))
            .route("/v1/messages", get(ok))
            .route("/apis/demo/live-api/ping", get(ok))
            .fallback(ok)
            .layer(axum::middleware::from_fn(public_surface_middleware));

        for path in [
            "/apis/../admin/health",
            "/apis/%2e%2e/admin/health",
            "//admin/health",
            "/apis/..%2fadmin/health",
        ] {
            let response = app
                .clone()
                .oneshot(
                    Request::builder()
                        .uri(path)
                        .header("x-forwarded-for", "203.0.113.10")
                        .body(Body::empty())
                        .unwrap(),
                )
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::BAD_REQUEST, "{path}");
        }

        for path in [
            "/admin/health",
            "/admin/contracts",
            "/metrics",
            "/mcp",
            "/oauth/register",
            "/v1/messages",
            "/",
        ] {
            let response = app
                .clone()
                .oneshot(
                    Request::builder()
                        .uri(path)
                        .header("x-forwarded-for", "203.0.113.10")
                        .header("x-forwarded-host", "api.gostoa.dev")
                        .body(Body::empty())
                        .unwrap(),
                )
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::NOT_FOUND, "{path}");
        }

        let public = app
            .clone()
            .oneshot(
                Request::builder()
                    .uri("/apis/demo/live-api/ping")
                    .header("x-forwarded-for", "203.0.113.10")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(public.status(), StatusCode::OK);

        let direct_admin = app
            .oneshot(
                Request::builder()
                    .uri("/admin/health")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(direct_admin.status(), StatusCode::OK);
    }
}
