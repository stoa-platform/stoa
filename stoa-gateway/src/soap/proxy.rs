//! SOAP Proxy Passthrough (CAB-1762)
//!
//! Forwards SOAP requests (HTTP POST with text/xml) to backend services
//! with auth validation, metrics, and SOAP fault detection.
//!
//! Route: `POST /soap/:route_id` — looks up backend URL from RouteRegistry.

use axum::{
    body::Body,
    extract::{Path, State},
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
};
use tracing::{info, warn};

use crate::auth::tenant::{request_identity, require_tenant};
use crate::metrics;
use crate::state::AppState;

/// POST /soap/:route_id — SOAP proxy passthrough.
///
/// 1. Validates the signed identity and required tenant
/// 2. Looks up the backend URL and verifies route tenant ownership
/// 3. Forwards the raw SOAP request body to the backend
/// 4. Returns the raw SOAP response with metrics tracking
pub async fn soap_proxy(
    State(state): State<AppState>,
    Path(route_id): Path<String>,
    headers: HeaderMap,
    body: Body,
) -> Response {
    // Feature gate
    if !state.config.soap_proxy_enabled {
        return (StatusCode::NOT_FOUND, "SOAP proxy is not enabled").into_response();
    }

    let (claims, _) = match request_identity(&state, &headers).await {
        Ok(identity) => identity,
        Err(error) => return error.into_response(),
    };
    let tenant_id = match require_tenant(&claims) {
        Ok(tenant) => tenant,
        Err(error) => return error.into_response(),
    };

    // Look up backend URL from route registry
    let route = state.route_registry.get(&route_id);
    let Some(route) = route else {
        return (
            StatusCode::NOT_FOUND,
            format!("Route not found: {route_id}"),
        )
            .into_response();
    };

    if route.tenant_id != tenant_id {
        return (StatusCode::FORBIDDEN, "Route belongs to another tenant").into_response();
    }

    if !route.activated {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            format!("Route {} is not active", route_id),
        )
            .into_response();
    }

    let backend_url = &route.backend_url;

    // Extract SOAPAction header (optional, forwarded to backend)
    let soap_action = headers
        .get("soapaction")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("")
        .to_string();

    info!(
        route_id = %route_id,
        backend = %backend_url,
        tenant = %tenant_id,
        soap_action = %soap_action,
        "SOAP proxy request"
    );

    metrics::track_soap_proxy_request(&route_id);

    // Read body bytes
    let body_bytes = match axum::body::to_bytes(body, 10 * 1024 * 1024).await {
        Ok(bytes) => bytes,
        Err(e) => {
            warn!(error = %e, "Failed to read SOAP request body");
            return (StatusCode::BAD_REQUEST, "Failed to read request body").into_response();
        }
    };

    // Forward to backend
    let mut request = state
        .http_client
        .post(backend_url)
        .header("Content-Type", "text/xml; charset=utf-8")
        .body(body_bytes);

    if !soap_action.is_empty() {
        request = request.header("SOAPAction", &soap_action);
    }

    // Forward correlation only; client headers never assert a backend tenant.
    for key in &["x-request-id", "x-correlation-id"] {
        if let Some(val) = headers.get(*key) {
            if let Ok(val_str) = val.to_str() {
                request = request.header(*key, val_str);
            }
        }
    }

    match request.send().await {
        Ok(response) => {
            let status = response.status();
            let is_success = status.is_success();

            // Read response body
            match response.bytes().await {
                Ok(response_body) => {
                    metrics::track_soap_proxy_response(&route_id, is_success);

                    // Check for SOAP fault in body (even on HTTP 200, SOAP can return faults)
                    if let Ok(body_str) = std::str::from_utf8(&response_body) {
                        if body_str.contains("soap:Fault") || body_str.contains("Fault>") {
                            metrics::track_soap_proxy_fault(&route_id);
                        }
                    }

                    let mut builder = axum::http::Response::builder()
                        .status(StatusCode::from_u16(status.as_u16()).unwrap_or(StatusCode::OK))
                        .header("Content-Type", "text/xml; charset=utf-8");

                    // Forward CORS headers if present
                    if let Some(origin) = headers.get("origin") {
                        if let Ok(origin_str) = origin.to_str() {
                            builder = builder
                                .header("Access-Control-Allow-Origin", origin_str)
                                .header("Access-Control-Allow-Methods", "POST, OPTIONS")
                                .header(
                                    "Access-Control-Allow-Headers",
                                    "Content-Type, SOAPAction, Authorization",
                                );
                        }
                    }

                    builder.body(Body::from(response_body)).unwrap_or_else(|_| {
                        (StatusCode::INTERNAL_SERVER_ERROR, "Response build error").into_response()
                    })
                }
                Err(e) => {
                    warn!(error = %e, route_id = %route_id, "Failed to read backend response");
                    metrics::track_soap_proxy_response(&route_id, false);
                    (StatusCode::BAD_GATEWAY, "Failed to read backend response").into_response()
                }
            }
        }
        Err(e) => {
            warn!(error = %e, route_id = %route_id, backend = %backend_url, "SOAP backend request failed");
            metrics::track_soap_proxy_response(&route_id, false);
            (
                StatusCode::BAD_GATEWAY,
                format!("SOAP backend unreachable: {e}"),
            )
                .into_response()
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::{HeaderValue, Request};
    use serde_json::{json, Value};
    use tower::ServiceExt;
    use wiremock::matchers::{method, path};
    use wiremock::{Mock, MockServer, ResponseTemplate};

    use crate::auth::jwt::tests::{mcp_test_jwks, mcp_test_mint};
    use crate::config::Config;

    const SOAP_BODY: &str = "<soap:Envelope>request</soap:Envelope>";

    struct Fixture {
        server: MockServer,
        state: AppState,
        _spool: tempfile::TempDir,
    }

    impl Fixture {
        async fn new() -> Self {
            let server = MockServer::start().await;
            let issuer = format!("{}/realms/stoa", server.uri());
            Mock::given(method("GET"))
                .and(path("/realms/stoa/.well-known/openid-configuration"))
                .respond_with(ResponseTemplate::new(200).set_body_json(json!({
                    "issuer": issuer,
                    "authorization_endpoint": format!("{issuer}/auth"),
                    "token_endpoint": format!("{issuer}/token"),
                    "jwks_uri": format!("{}/jwks", server.uri())
                })))
                .mount(&server)
                .await;
            Mock::given(method("GET"))
                .and(path("/jwks"))
                .respond_with(ResponseTemplate::new(200).set_body_json(mcp_test_jwks()))
                .mount(&server)
                .await;
            Mock::given(method("POST"))
                .and(path("/backend"))
                .respond_with(ResponseTemplate::new(200).set_body_string("<reply>ok</reply>"))
                .mount(&server)
                .await;
            let spool = tempfile::tempdir().unwrap();
            let state = AppState::new(Config {
                soap_proxy_enabled: true,
                keycloak_url: Some(server.uri()),
                keycloak_realm: Some("stoa".into()),
                mcp_audience: Some("control-plane-api".into()),
                audit_spool_dir: spool.path().into(),
                ..Config::default()
            });
            for tenant in ["tenant-a", "tenant-b", ""] {
                state.route_registry.upsert(
                    serde_json::from_value(json!({
                        "id": format!("route-{tenant}"), "name": "SOAP test",
                        "tenant_id": tenant, "path_prefix": "/soap",
                        "backend_url": format!("{}/backend", server.uri()),
                        "methods": ["POST"], "spec_hash": "", "activated": true
                    }))
                    .unwrap(),
                );
            }
            Self {
                server,
                state,
                _spool: spool,
            }
        }

        fn token(&self, overrides: Value) -> String {
            mcp_test_mint(&format!("{}/realms/stoa", self.server.uri()), overrides)
        }

        async fn post(
            &self,
            route_tenant: &str,
            token: Option<&str>,
            tenants: &[HeaderValue],
        ) -> Response {
            let mut request = Request::builder()
                .method("POST")
                .uri(format!("/soap/route-{route_tenant}"))
                .header("content-type", "text/xml")
                .header("soapaction", "urn:echo")
                .header("x-request-id", "soap-request")
                .header("x-correlation-id", "soap-correlation");
            if let Some(token) = token {
                request = request.header("authorization", format!("Bearer {token}"));
            }
            for tenant in tenants {
                request = request.header("x-tenant-id", tenant);
            }
            crate::build_router(self.state.clone())
                .oneshot(request.body(Body::from(SOAP_BODY)).unwrap())
                .await
                .unwrap()
        }

        async fn backend_requests(&self) -> Vec<wiremock::Request> {
            self.server
                .received_requests()
                .await
                .unwrap()
                .into_iter()
                .filter(|request| request.url.path() == "/backend")
                .collect()
        }
    }

    #[tokio::test]
    async fn client_tenant_headers_never_reach_soap_backend() {
        let fixture = Fixture::new().await;
        let token = fixture.token(json!({}));
        let header_cases = [
            vec![],
            vec![HeaderValue::from_static("tenant-a")],
            vec![HeaderValue::from_static("tenant-b")],
            vec![
                HeaderValue::from_static("tenant-b"),
                HeaderValue::from_static("tenant-a"),
            ],
            vec![HeaderValue::from_static(" ")],
            vec![HeaderValue::from_bytes(&[0xff]).unwrap()],
        ];
        for tenants in &header_cases {
            let response = fixture.post("tenant-a", Some(&token), tenants).await;
            assert_eq!(response.status(), StatusCode::OK);
            assert_eq!(
                axum::body::to_bytes(response.into_body(), 1024)
                    .await
                    .unwrap(),
                "<reply>ok</reply>"
            );
        }
        let requests = fixture.backend_requests().await;
        assert_eq!(requests.len(), header_cases.len());
        for request in requests {
            assert!(!request.headers.contains_key("x-tenant-id"));
            assert_eq!(request.headers["x-request-id"], "soap-request");
            assert_eq!(request.headers["x-correlation-id"], "soap-correlation");
            assert_eq!(request.headers["soapaction"], "urn:echo");
            assert_eq!(request.body, SOAP_BODY.as_bytes());
        }
    }

    #[tokio::test]
    async fn soap_requires_verified_identity_and_matching_route_tenant() {
        let fixture = Fixture::new().await;
        let cases =
            [
                (None, "tenant-a", StatusCode::UNAUTHORIZED),
                (Some("invalid".into()), "tenant-a", StatusCode::UNAUTHORIZED),
                (
                    Some(fixture.token(json!({"tenant_id": null}))),
                    "tenant-a",
                    StatusCode::FORBIDDEN,
                ),
                (
                    Some(fixture.token(
                        json!({"tenant_id": null, "realm_access": {"roles": ["cpi-admin"]}}),
                    )),
                    "tenant-a",
                    StatusCode::FORBIDDEN,
                ),
                (
                    Some(fixture.token(json!({"tenant_id": "tenant-b"}))),
                    "tenant-a",
                    StatusCode::FORBIDDEN,
                ),
                (
                    Some(fixture.token(json!({}))),
                    "tenant-b",
                    StatusCode::FORBIDDEN,
                ),
                (Some(fixture.token(json!({}))), "", StatusCode::FORBIDDEN),
                (
                    Some(fixture.token(json!({"exp": chrono::Utc::now().timestamp() - 120}))),
                    "tenant-a",
                    StatusCode::UNAUTHORIZED,
                ),
                (
                    Some(fixture.token(json!({"aud": "other-resource"}))),
                    "tenant-a",
                    StatusCode::UNAUTHORIZED,
                ),
                (
                    Some(fixture.token(json!({"iss": "https://other.example/realms/stoa"}))),
                    "tenant-a",
                    StatusCode::UNAUTHORIZED,
                ),
                (
                    Some(fixture.token(json!({"sub": ""}))),
                    "tenant-a",
                    StatusCode::UNAUTHORIZED,
                ),
                (
                    Some(fixture.token(json!({"cnf": {"jkt": "unverified-proof"}}))),
                    "tenant-a",
                    StatusCode::UNAUTHORIZED,
                ),
            ];
        for (token, route_tenant, status) in cases {
            let response = fixture
                .post(
                    route_tenant,
                    token.as_deref(),
                    &[HeaderValue::from_static("tenant-a")],
                )
                .await;
            assert_eq!(response.status(), status, "route tenant: {route_tenant}");
        }
        assert!(fixture.backend_requests().await.is_empty());
    }

    #[tokio::test]
    async fn soap_fails_closed_without_jwt_validator() {
        let mut fixture = Fixture::new().await;
        fixture.state.jwt_validator = None;
        let token = fixture.token(json!({}));
        let response = fixture.post("tenant-a", Some(&token), &[]).await;
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        assert!(fixture.backend_requests().await.is_empty());
    }
}
