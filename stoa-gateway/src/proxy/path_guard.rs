//! Reject ambiguous paths and hide every non-API route from a reverse proxy.
//!
//! ingress-nginx forwards the original request target. A path such as
//! `/apis/../admin` or `/apis/%2e%2e/admin` must not be normalised onto
//! `/admin` (that would be a 401 from the admin bearer check). A proxied
//! request is public only for `/apis` and `/apis/...`. `/admin`, `/metrics`,
//! `/mcp`, `/oauth/register`, and `/v1/messages` stay on the pod and are
//! reachable without `X-Forwarded-For` / `X-Forwarded-Host` (kubelet probes,
//! ClusterIP, port-forward).
//!
//! `STOA_PUBLIC_MCP_ENABLED=true` widens that public surface to the MCP
//! endpoint: `/mcp` and `/mcp/...`, the three OAuth discovery documents, and
//! the health and readiness probes. Nothing else changes: `/admin`,
//! `/metrics`, `/oauth/...` and `/v1/messages` are still 404 behind a proxy,
//! and each MCP route keeps its own authentication.

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

/// Extra paths a reverse proxy may deliver when `STOA_PUBLIC_MCP_ENABLED` is
/// set. Discovery documents and probes are exact matches: a new route under
/// `/.well-known/` or `/health/` is not public until it is listed here.
pub fn is_public_mcp_path(path: &str) -> bool {
    path == "/mcp"
        || path.starts_with("/mcp/")
        || matches!(
            path,
            "/.well-known/oauth-protected-resource"
                | "/.well-known/oauth-authorization-server"
                | "/.well-known/openid-configuration"
                | "/health"
                | "/health/ready"
                | "/health/live"
                | "/ready"
        )
}

fn forwarded_by_proxy(request: &Request<Body>) -> bool {
    request.headers().get("x-forwarded-for").is_some()
        || request.headers().get("x-forwarded-host").is_some()
}

/// Outermost HTTP guard. Ambiguous paths are 400. A proxied request whose
/// path is not under `/apis` is 404, before admin auth can answer 401.
/// With `public_mcp` (`STOA_PUBLIC_MCP_ENABLED`), the paths accepted by
/// [`is_public_mcp_path`] pass as well.
pub async fn public_surface_middleware(
    public_mcp: bool,
    request: Request<Body>,
    next: Next,
) -> Response {
    let path = request.uri().path();
    if ambiguous_path(path) {
        return (StatusCode::BAD_REQUEST, "ambiguous path").into_response();
    }
    if forwarded_by_proxy(&request) {
        let public = is_public_api_path(path) || (public_mcp && is_public_mcp_path(path));
        if !public {
            return StatusCode::NOT_FOUND.into_response();
        }
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
            .layer(axum::middleware::from_fn(|request, next| {
                public_surface_middleware(false, request, next)
            }));

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

    /// Every route the gateway serves outside `/apis`, one handler each.
    fn surface_app(public_mcp: bool) -> Router {
        let mut app = Router::new();
        for path in PRIVATE_PATHS.iter().chain(MCP_PATHS).chain(API_PATHS) {
            app = app.route(path, get(ok).post(ok));
        }
        app.fallback(ok)
            .layer(axum::middleware::from_fn(move |request, next| {
                public_surface_middleware(public_mcp, request, next)
            }))
    }

    const API_PATHS: &[&str] = &["/apis/demo/live-api/ping"];

    /// Opened by `STOA_PUBLIC_MCP_ENABLED`.
    const MCP_PATHS: &[&str] = &[
        "/mcp",
        "/mcp/sse",
        "/mcp/capabilities",
        "/mcp/health",
        "/mcp/tools/list",
        "/mcp/v1/tools",
        "/mcp/ws",
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-authorization-server",
        "/.well-known/openid-configuration",
        "/health",
        "/health/ready",
        "/health/live",
        "/ready",
    ];

    /// Never delivered by a proxy, whatever the option says.
    const PRIVATE_PATHS: &[&str] = &[
        "/admin/health",
        "/admin/contracts",
        "/admin/policies",
        "/metrics",
        "/oauth/token",
        "/oauth/par",
        "/oauth/register",
        "/oauth/register/some-client",
        "/v1/messages",
        "/v1/chat/completions",
        "/proxy/anything",
        "/hegemon/dispatch",
        "/a2a",
        "/.well-known/agent.json",
        "/soap/route",
        "/ws/route",
        // Lookalikes of the opened prefixes and exact paths.
        "/mcpx",
        "/mcp-admin",
        "/mcp;/admin/health",
        "/healthz",
        "/health/other",
        "/ready/x",
        "/readyz",
        "/.well-known",
        "/.well-known/",
        "/.well-known/other",
        "/.well-known/oauth-protected-resource/extra",
        "/MCP",
        "/",
    ];

    async fn status(app: &Router, path: &str, headers: &[(&str, &str)]) -> StatusCode {
        let mut request = Request::builder().uri(path);
        for (name, value) in headers {
            request = request.header(*name, *value);
        }
        app.clone()
            .oneshot(request.body(Body::empty()).unwrap())
            .await
            .unwrap()
            .status()
    }

    const PROXY_HEADER_SETS: &[&[(&str, &str)]] = &[
        &[("x-forwarded-for", "203.0.113.10")],
        &[("x-forwarded-host", "mcp.gostoa.dev")],
        &[
            ("x-forwarded-for", "203.0.113.10"),
            ("x-forwarded-host", "mcp.gostoa.dev"),
        ],
    ];

    #[test]
    fn public_mcp_path_list_is_exact() {
        for path in MCP_PATHS {
            assert!(is_public_mcp_path(path), "{path}");
        }
        for path in PRIVATE_PATHS.iter().chain(API_PATHS) {
            assert!(!is_public_mcp_path(path), "{path}");
        }
    }

    #[tokio::test]
    async fn option_off_keeps_the_mcp_surface_private_behind_a_proxy() {
        let app = surface_app(false);
        for headers in PROXY_HEADER_SETS {
            for path in MCP_PATHS.iter().chain(PRIVATE_PATHS) {
                assert_eq!(
                    status(&app, path, headers).await,
                    StatusCode::NOT_FOUND,
                    "{path} {headers:?}"
                );
            }
            for path in API_PATHS {
                assert_eq!(status(&app, path, headers).await, StatusCode::OK, "{path}");
            }
        }
    }

    #[tokio::test]
    async fn option_on_opens_only_the_mcp_surface_behind_a_proxy() {
        let app = surface_app(true);
        for headers in PROXY_HEADER_SETS {
            for path in MCP_PATHS.iter().chain(API_PATHS) {
                assert_eq!(
                    status(&app, path, headers).await,
                    StatusCode::OK,
                    "{path} {headers:?}"
                );
            }
            for path in PRIVATE_PATHS {
                assert_eq!(
                    status(&app, path, headers).await,
                    StatusCode::NOT_FOUND,
                    "{path} {headers:?}"
                );
            }
        }
    }

    #[tokio::test]
    async fn option_on_still_rejects_ambiguous_paths() {
        let app = surface_app(true);
        for path in [
            "/mcp/../admin/health",
            "/mcp/%2e%2e/admin/health",
            "/mcp/%2E%2E/metrics",
            "/mcp//admin/health",
            "/mcp/..%2fadmin/health",
            "/mcp/%252e%252e/admin",
            "/health/../metrics",
            "/.well-known/../admin/health",
        ] {
            for headers in PROXY_HEADER_SETS {
                assert_eq!(
                    status(&app, path, headers).await,
                    StatusCode::BAD_REQUEST,
                    "{path} {headers:?}"
                );
            }
            assert_eq!(
                status(&app, path, &[]).await,
                StatusCode::BAD_REQUEST,
                "{path}"
            );
        }
    }

    #[tokio::test]
    async fn direct_calls_are_unaffected_by_the_option() {
        for public_mcp in [false, true] {
            let app = surface_app(public_mcp);
            for path in [
                "/admin/health",
                "/metrics",
                "/mcp",
                "/oauth/register",
                "/health",
            ] {
                assert_eq!(status(&app, path, &[]).await, StatusCode::OK, "{path}");
            }
        }
    }
}
