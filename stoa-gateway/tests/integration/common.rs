//! Shared test helpers for integration tests.

use axum::body::Body;
use axum::http::{HeaderMap, Request, StatusCode};
use axum::Router;
use tower::ServiceExt;

use stoa_gateway::config::Config;
use stoa_gateway::state::AppState;

/// A test application wrapping the gateway router.
///
/// Provides convenience methods for making HTTP requests.
pub struct TestApp {
    router: Router,
    pub state: AppState,
    mcp_token: Option<String>,
    _mcp_oidc: Option<wiremock::MockServer>,
    _mcp_key_dir: Option<tempfile::TempDir>,
}

impl TestApp {
    /// Create a test app with default config (EdgeMcp mode, no auth, no CP).
    pub fn new() -> Self {
        let config = Config::default();
        let state = AppState::new(config);
        let router = stoa_gateway::build_router(state.clone());
        Self {
            router,
            state,
            mcp_token: None,
            _mcp_oidc: None,
            _mcp_key_dir: None,
        }
    }

    /// Create a test app with a custom config.
    pub fn with_config(config: Config) -> Self {
        let state = AppState::new(config);
        let router = stoa_gateway::build_router(state.clone());
        Self {
            router,
            state,
            mcp_token: None,
            _mcp_oidc: None,
            _mcp_key_dir: None,
        }
    }

    /// Real JWT authentication for protocol contract tests, with local OIDC only.
    pub async fn with_mcp_auth() -> Self {
        Self::with_mcp_auth_config(Config::default()).await
    }

    pub async fn with_mcp_auth_config(mut config: Config) -> Self {
        use wiremock::matchers::{method, path};
        use wiremock::{Mock, MockServer, ResponseTemplate};
        let oidc = MockServer::start().await;
        let issuer = format!("{}/realms/stoa", oidc.uri());
        // Reference the original fixture without adding its key material to a patch.
        // Rust string continuations are removed before decoding the escaped newlines.
        let source = include_str!("../../src/auth/jwt.rs");
        let fixture = source
            .split("const TEST_PEM: &str = \"")
            .nth(1)
            .unwrap()
            .split("\";")
            .next()
            .unwrap();
        let pem = fixture
            .lines()
            .map(|line| line.trim().trim_end_matches('\\'))
            .collect::<String>()
            .replace("\\n", "\n");
        let modulus = source
            .split("const TEST_N: &str = \"")
            .nth(1)
            .unwrap()
            .split("\";")
            .next()
            .unwrap();
        Mock::given(method("GET"))
            .and(path("/realms/stoa/.well-known/openid-configuration"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "issuer": issuer, "authorization_endpoint": format!("{issuer}/auth"),
                "token_endpoint": format!("{issuer}/token"),
                "jwks_uri": format!("{}/jwks", oidc.uri())
            })))
            .mount(&oidc)
            .await;
        Mock::given(method("GET"))
            .and(path("/jwks"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "keys": [{"kty": "RSA", "kid": "test-key", "use": "sig", "alg": "RS256",
                    "n": modulus, "e": "AQAB"}]
            })))
            .mount(&oidc)
            .await;
        let mut jwt_header = jsonwebtoken::Header::new(jsonwebtoken::Algorithm::RS256);
        jwt_header.kid = Some("test-key".into());
        let now = chrono::Utc::now().timestamp();
        let token = jsonwebtoken::encode(
            &jwt_header,
            &serde_json::json!({
                "sub": "contract-user", "iss": issuer, "aud": "control-plane-api",
                "exp": now + 300, "iat": now, "tenant_id": "contract-tenant", "scope": "stoa:read"
            }),
            &jsonwebtoken::EncodingKey::from_rsa_pem(pem.as_bytes()).unwrap(),
        )
        .unwrap();
        Mock::given(method("POST"))
            .and(path("/realms/stoa/protocol/openid-connect/token"))
            .and(wiremock::matchers::body_string_contains(
                "client_assertion=",
            ))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "access_token": "fixture-service-access", "expires_in": 300
            })))
            .mount(&oidc)
            .await;
        Mock::given(method("GET")).and(path("/v1/tenants/contract-tenant/tool-permissions"))
            .and(wiremock::matchers::header("Authorization", "Bearer fixture-service-access"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "items": [{"mcp_server_id": "fixture", "tool_name": "phase62_echo", "allowed": true}], "total": 1
            }))).mount(&oidc).await;
        config.keycloak_url = Some(oidc.uri());
        config.keycloak_realm = Some("stoa".into());
        config.keycloak_client_id = Some("stoa-mcp-gateway".into());
        // Service identity: private_key_jwt with a key file, as mounted from a Secret.
        let key_dir = tempfile::tempdir().unwrap();
        let key_path = key_dir.path().join("service-key.pem");
        std::fs::write(&key_path, &pem).unwrap();
        config.keycloak_client_key_path = Some(key_path.display().to_string());
        config.mcp_audience = Some("control-plane-api".into());
        config.control_plane_url = Some(oidc.uri());
        let mut app = Self::with_config(config);
        app.mcp_token = Some(token);
        app._mcp_oidc = Some(oidc);
        app._mcp_key_dir = Some(key_dir);
        app
    }

    pub fn mcp_token(&self) -> &str {
        self.mcp_token
            .as_deref()
            .expect("authenticated MCP fixture")
    }

    /// Send a GET request and return (status, body).
    pub async fn get(&self, uri: &str) -> (StatusCode, String) {
        let request = Request::builder()
            .method("GET")
            .uri(uri)
            .body(Body::empty())
            .expect("valid request");

        let response = self
            .router
            .clone()
            .oneshot(request)
            .await
            .expect("router should not error");

        let status = response.status();
        let body = axum::body::to_bytes(response.into_body(), 1_048_576)
            .await
            .expect("read body");
        (status, String::from_utf8_lossy(&body).to_string())
    }

    /// Send a GET request with Authorization header.
    pub async fn get_with_bearer(&self, uri: &str, token: &str) -> (StatusCode, String) {
        let request = Request::builder()
            .method("GET")
            .uri(uri)
            .header("Authorization", format!("Bearer {}", token))
            .body(Body::empty())
            .expect("valid request");

        let response = self
            .router
            .clone()
            .oneshot(request)
            .await
            .expect("router should not error");

        let status = response.status();
        let body = axum::body::to_bytes(response.into_body(), 1_048_576)
            .await
            .expect("read body");
        (status, String::from_utf8_lossy(&body).to_string())
    }

    /// Send a POST request with JSON body.
    pub async fn post_json(&self, uri: &str, json_body: &str) -> (StatusCode, String) {
        let request = Request::builder()
            .method("POST")
            .uri(uri)
            .header("Content-Type", "application/json")
            .body(Body::from(json_body.to_string()))
            .expect("valid request");

        let response = self
            .router
            .clone()
            .oneshot(request)
            .await
            .expect("router should not error");

        let status = response.status();
        let body = axum::body::to_bytes(response.into_body(), 1_048_576)
            .await
            .expect("read body");
        (status, String::from_utf8_lossy(&body).to_string())
    }

    /// Send a POST request with JSON body and Authorization header.
    pub async fn post_json_with_bearer(
        &self,
        uri: &str,
        json_body: &str,
        token: &str,
    ) -> (StatusCode, String) {
        let request = Request::builder()
            .method("POST")
            .uri(uri)
            .header("Content-Type", "application/json")
            .header("Authorization", format!("Bearer {}", token))
            .body(Body::from(json_body.to_string()))
            .expect("valid request");

        let response = self
            .router
            .clone()
            .oneshot(request)
            .await
            .expect("router should not error");

        let status = response.status();
        let body = axum::body::to_bytes(response.into_body(), 1_048_576)
            .await
            .expect("read body");
        (status, String::from_utf8_lossy(&body).to_string())
    }

    /// Send a POST request with JSON body + optional Accept/Authorization and
    /// return the full `(status, headers, body)` tuple so callers can assert on
    /// `Content-Type`, `Mcp-Session-Id`, etc.
    #[allow(dead_code)] // only consumed from the `contract` test harness
    pub async fn post_raw(
        &self,
        uri: &str,
        json_body: &str,
        accept: Option<&str>,
        bearer: Option<&str>,
    ) -> (StatusCode, HeaderMap, String) {
        let mut builder = Request::builder()
            .method("POST")
            .uri(uri)
            .header("Content-Type", "application/json");
        if let Some(a) = accept {
            builder = builder.header("Accept", a);
        }
        if let Some(t) = bearer {
            builder = builder.header("Authorization", format!("Bearer {}", t));
        }
        let request = builder
            .body(Body::from(json_body.to_string()))
            .expect("valid request");

        let response = self
            .router
            .clone()
            .oneshot(request)
            .await
            .expect("router should not error");

        let status = response.status();
        let headers = response.headers().clone();
        let body = axum::body::to_bytes(response.into_body(), 1_048_576)
            .await
            .expect("read body");
        (status, headers, String::from_utf8_lossy(&body).to_string())
    }
}

/// Create a Config with admin API token configured.
pub fn config_with_admin_token(token: &str) -> Config {
    Config {
        admin_api_token: Some(token.to_string()),
        auto_register: false,
        ..Config::default()
    }
}

/// Create a Config with quota enforcement enabled.
pub fn config_with_quota(rate_per_minute: u32, daily_limit: u32) -> Config {
    Config {
        admin_api_token: Some("test-admin-token".to_string()),
        quota_enforcement_enabled: true,
        quota_default_rate_per_minute: rate_per_minute,
        quota_default_daily_limit: daily_limit,
        auto_register: false,
        ..Config::default()
    }
}
