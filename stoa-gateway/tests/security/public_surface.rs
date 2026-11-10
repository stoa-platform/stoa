//! Public surface behind a reverse proxy, through the real router.
//!
//! ingress-nginx sets `X-Forwarded-For` and `X-Forwarded-Host`. With those
//! headers a request reaches `/apis` only, plus the MCP surface when
//! `STOA_PUBLIC_MCP_ENABLED` is set. `/admin`, `/metrics`, `/oauth/...` and
//! `/v1/messages` are 404 in both cases, even with a valid admin bearer.

use axum::body::Body;
use axum::http::{Method, Request, StatusCode};
use axum::Router;
use tower::ServiceExt;

use stoa_gateway::config::Config;
use stoa_gateway::state::AppState;

const ADMIN_TOKEN: &str = "public-surface-admin-token";

/// `keycloak_url` points at an unroutable address: a JWT validator exists, so
/// the MCP auth gate is engaged, and no token can ever validate.
fn router(public_mcp_enabled: bool) -> Router {
    router_with_keycloak(public_mcp_enabled, Some("http://127.0.0.1:1".to_string()))
}

fn router_with_keycloak(public_mcp_enabled: bool, keycloak_url: Option<String>) -> Router {
    let config = Config {
        admin_api_token: Some(ADMIN_TOKEN.to_string()),
        auto_register: false,
        public_mcp_enabled,
        keycloak_url,
        ..Config::default()
    };
    stoa_gateway::build_router(AppState::new(config))
}

struct Call<'a> {
    method: Method,
    path: &'a str,
    body: &'a str,
    proxied: bool,
    admin_bearer: bool,
}

impl<'a> Call<'a> {
    fn get(path: &'a str) -> Self {
        Self {
            method: Method::GET,
            path,
            body: "",
            proxied: true,
            admin_bearer: false,
        }
    }

    fn post(path: &'a str, body: &'a str) -> Self {
        Self {
            method: Method::POST,
            body,
            ..Self::get(path)
        }
    }

    fn direct(mut self) -> Self {
        self.proxied = false;
        self
    }

    fn with_admin_bearer(mut self) -> Self {
        self.admin_bearer = true;
        self
    }

    async fn status(self, router: &Router) -> StatusCode {
        let mut request = Request::builder()
            .method(self.method)
            .uri(self.path)
            .header("content-type", "application/json")
            .header("accept", "application/json, text/event-stream");
        if self.proxied {
            request = request
                .header("x-forwarded-for", "203.0.113.10")
                .header("x-forwarded-host", "mcp.gostoa.dev");
        }
        if self.admin_bearer {
            request = request.header("authorization", format!("Bearer {ADMIN_TOKEN}"));
        }
        router
            .clone()
            .oneshot(
                request
                    .body(Body::from(self.body.to_string()))
                    .expect("valid request"),
            )
            .await
            .expect("router answers")
            .status()
    }
}

const INITIALIZE: &str = r#"{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"public-surface-test","version":"0"}}}"#;
const TOOLS_LIST: &str = r#"{"jsonrpc":"2.0","id":2,"method":"tools/list"}"#;

#[tokio::test]
async fn proxied_mcp_surface_is_closed_by_default() {
    let router = router(false);
    for path in [
        "/mcp",
        "/mcp/capabilities",
        "/mcp/health",
        "/.well-known/oauth-protected-resource",
        "/health",
        "/ready",
    ] {
        assert_eq!(
            Call::get(path).status(&router).await,
            StatusCode::NOT_FOUND,
            "{path}"
        );
    }
    assert_eq!(
        Call::post("/mcp", INITIALIZE).status(&router).await,
        StatusCode::NOT_FOUND
    );
}

#[tokio::test]
async fn option_opens_the_mcp_surface_to_a_proxy() {
    let router = router(true);
    for path in ["/mcp", "/mcp/capabilities", "/mcp/health", "/health"] {
        assert_eq!(
            Call::get(path).status(&router).await,
            StatusCode::OK,
            "{path}"
        );
    }
    // Served by the router: whatever they answer, it is not the guard's 404.
    for path in [
        "/ready",
        "/health/ready",
        "/health/live",
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-authorization-server",
        "/.well-known/openid-configuration",
    ] {
        assert_ne!(
            Call::get(path).status(&router).await,
            StatusCode::NOT_FOUND,
            "{path}"
        );
    }
    assert_eq!(
        Call::post("/mcp", INITIALIZE).status(&router).await,
        StatusCode::OK
    );
}

/// Without a JWT validator the `/mcp` auth gate lets every request through,
/// so the option must not open the surface.
#[tokio::test]
async fn option_is_ignored_without_a_jwt_validator() {
    let router = router_with_keycloak(true, None);
    for path in ["/mcp", "/mcp/capabilities", "/mcp/v1/tools", "/health"] {
        assert_eq!(
            Call::get(path).status(&router).await,
            StatusCode::NOT_FOUND,
            "{path}"
        );
    }
    assert_eq!(
        Call::post("/mcp", TOOLS_LIST).status(&router).await,
        StatusCode::NOT_FOUND
    );
}

#[tokio::test]
async fn option_does_not_remove_mcp_authentication() {
    let router = router(true);
    assert_eq!(
        Call::post("/mcp", TOOLS_LIST).status(&router).await,
        StatusCode::UNAUTHORIZED
    );
    assert_eq!(
        Call::post("/mcp/sse", TOOLS_LIST).status(&router).await,
        StatusCode::UNAUTHORIZED
    );
    assert_eq!(
        Call::get("/mcp/v1/tools").status(&router).await,
        StatusCode::UNAUTHORIZED
    );
    assert_eq!(
        Call::post("/mcp/tools/list", "{}").status(&router).await,
        StatusCode::UNAUTHORIZED
    );
}

#[tokio::test]
async fn private_routes_stay_hidden_from_a_proxy_with_the_option_on() {
    let router = router(true);
    for path in ["/admin/health", "/admin/contracts", "/metrics"] {
        assert_eq!(
            Call::get(path).with_admin_bearer().status(&router).await,
            StatusCode::NOT_FOUND,
            "{path}"
        );
    }
    for path in [
        "/oauth/token",
        "/oauth/par",
        "/oauth/register",
        "/v1/messages",
        "/v1/chat/completions",
        "/a2a",
        "/hegemon/dispatch",
    ] {
        assert_eq!(
            Call::post(path, "{}")
                .with_admin_bearer()
                .status(&router)
                .await,
            StatusCode::NOT_FOUND,
            "{path}"
        );
    }
    assert_eq!(
        Call::get("/.well-known/agent.json").status(&router).await,
        StatusCode::NOT_FOUND
    );
    for path in ["/mcp/../admin/health", "/mcp/%2e%2e/metrics"] {
        assert_eq!(
            Call::get(path).with_admin_bearer().status(&router).await,
            StatusCode::BAD_REQUEST,
            "{path}"
        );
    }
}

#[tokio::test]
async fn direct_admin_and_metrics_still_answer_with_the_option_on() {
    let router = router(true);
    assert_eq!(
        Call::get("/admin/health")
            .direct()
            .with_admin_bearer()
            .status(&router)
            .await,
        StatusCode::OK
    );
    assert_eq!(
        Call::get("/metrics").direct().status(&router).await,
        StatusCode::OK
    );
    assert_eq!(
        Call::get("/admin/health").direct().status(&router).await,
        StatusCode::UNAUTHORIZED
    );
}
