//! Shared test helpers for integration tests.

use axum::body::Body;
use axum::http::{Request, StatusCode};
use axum::Router;
use tower::ServiceExt;

use stoa_gateway::config::Config;
use stoa_gateway::state::AppState;

/// A test application wrapping the gateway router.
///
/// Provides convenience methods for making HTTP requests.
pub struct TestApp {
    router: Router,
}

impl TestApp {
    /// Create a test app with default config (EdgeMcp mode, no auth, no CP).
    pub fn new() -> Self {
        let config = Config::default();
        let state = AppState::new(config);
        let router = stoa_gateway::build_router(state);
        Self { router }
    }

    /// Create a test app with a custom config.
    pub fn with_config(config: Config) -> Self {
        let state = AppState::new(config);
        let router = stoa_gateway::build_router(state);
        Self { router }
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
