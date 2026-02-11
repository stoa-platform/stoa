//! Sidecar Mode Implementation
//!
//! Runs alongside an existing API gateway (Kong, Envoy, Apigee, NGINX)
//! to provide policy enforcement, metering, and observability.
//!
//! # Architecture
//!
//! ```text
//!                     ┌──────────────────┐
//!    Client Request   │   Main Gateway   │
//!         ────────────▶  (Kong/Envoy)   │
//!                     │                  │
//!                     │   ┌──────────┐   │
//!                     │   │ ext_authz│   │
//!                     │   │  plugin  │───┼──────▶ STOA Sidecar
//!                     │   └──────────┘   │              │
//!                     │                  │              ▼
//!                     │                  │        ┌──────────┐
//!                     │                  │        │   OPA    │
//!                     │                  │        │  Policy  │
//!                     │                  │        └──────────┘
//!                     │        ◀─────────┼────── allow/deny
//!                     │                  │
//!                     │   ┌──────────┐   │
//!                     │   │ Backend  │   │
//!                     │   │ Service  │   │
//!                     │   └──────────┘   │
//!                     └──────────────────┘
//! ```
//!
//! # Supported Gateways
//!
//! - **Envoy**: ext_authz filter (gRPC or HTTP)
//! - **Kong**: Custom authorization plugin
//! - **NGINX**: auth_request module
//! - **Apigee**: Policy callout
//! - **AWS API Gateway**: Lambda authorizer format

use super::{DecisionFormat, SidecarSettings};
use axum::{
    body::Body,
    extract::State,
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tracing::{debug, info, instrument, warn};

/// Sidecar authorization request (from upstream gateway)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuthzRequest {
    /// HTTP method
    pub method: String,

    /// Request path
    pub path: String,

    /// Request headers (selected headers forwarded by gateway)
    #[serde(default)]
    pub headers: std::collections::HashMap<String, String>,

    /// Source IP address
    #[serde(skip_serializing_if = "Option::is_none")]
    pub source_ip: Option<String>,

    /// Pre-validated user information (from gateway's auth)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub user: Option<UserInfo>,

    /// Tenant ID (from header or path)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tenant_id: Option<String>,

    /// Request context (gateway-specific metadata)
    #[serde(default)]
    pub context: serde_json::Value,
}

/// Pre-validated user information from upstream gateway
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UserInfo {
    /// User ID (sub claim from JWT)
    pub id: String,

    /// User email
    #[serde(skip_serializing_if = "Option::is_none")]
    pub email: Option<String>,

    /// User roles
    #[serde(default)]
    pub roles: Vec<String>,

    /// OAuth scopes
    #[serde(default)]
    pub scopes: Vec<String>,

    /// Additional claims
    #[serde(default)]
    pub claims: std::collections::HashMap<String, serde_json::Value>,
}

/// Authorization decision response
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuthzResponse {
    /// Whether the request is allowed
    pub allowed: bool,

    /// Status code to return if denied
    #[serde(skip_serializing_if = "Option::is_none")]
    pub status_code: Option<u16>,

    /// Headers to add to the request (if allowed)
    #[serde(default)]
    pub headers_to_add: std::collections::HashMap<String, String>,

    /// Headers to remove from the request
    #[serde(default)]
    pub headers_to_remove: Vec<String>,

    /// Denial reason (if not allowed)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub denial_reason: Option<String>,

    /// Policy that caused denial
    #[serde(skip_serializing_if = "Option::is_none")]
    pub denied_by_policy: Option<String>,

    /// Request metadata for logging/metering
    #[serde(skip_serializing_if = "Option::is_none")]
    pub metadata: Option<RequestMetadata>,
}

/// Request metadata for observability
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RequestMetadata {
    /// Unique request ID
    pub request_id: String,

    /// Evaluated policies
    pub policies_evaluated: Vec<String>,

    /// Evaluation time in microseconds
    pub evaluation_time_us: u64,

    /// Rate limit state
    #[serde(skip_serializing_if = "Option::is_none")]
    pub rate_limit: Option<RateLimitState>,
}

/// Rate limit state information
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RateLimitState {
    /// Current request count
    pub current: u64,

    /// Maximum allowed
    pub limit: u64,

    /// Window reset time (Unix timestamp)
    pub reset_at: u64,

    /// Remaining requests in window
    pub remaining: u64,
}

impl AuthzResponse {
    /// Create an allow response
    pub fn allow() -> Self {
        Self {
            allowed: true,
            status_code: None,
            headers_to_add: std::collections::HashMap::new(),
            headers_to_remove: Vec::new(),
            denial_reason: None,
            denied_by_policy: None,
            metadata: None,
        }
    }

    /// Create a deny response
    pub fn deny(reason: impl Into<String>) -> Self {
        Self {
            allowed: false,
            status_code: Some(403),
            headers_to_add: std::collections::HashMap::new(),
            headers_to_remove: Vec::new(),
            denial_reason: Some(reason.into()),
            denied_by_policy: None,
            metadata: None,
        }
    }

    /// Create an unauthorized response (missing auth)
    pub fn unauthorized(reason: impl Into<String>) -> Self {
        Self {
            allowed: false,
            status_code: Some(401),
            headers_to_add: std::collections::HashMap::new(),
            headers_to_remove: Vec::new(),
            denial_reason: Some(reason.into()),
            denied_by_policy: None,
            metadata: None,
        }
    }

    /// Create a rate limited response
    pub fn rate_limited(state: RateLimitState) -> Self {
        Self {
            allowed: false,
            status_code: Some(429),
            headers_to_add: [
                ("X-RateLimit-Limit".to_string(), state.limit.to_string()),
                (
                    "X-RateLimit-Remaining".to_string(),
                    state.remaining.to_string(),
                ),
                ("X-RateLimit-Reset".to_string(), state.reset_at.to_string()),
            ]
            .into_iter()
            .collect(),
            headers_to_remove: Vec::new(),
            denial_reason: Some("Rate limit exceeded".to_string()),
            denied_by_policy: Some("rate_limit".to_string()),
            metadata: Some(RequestMetadata {
                request_id: uuid::Uuid::new_v4().to_string(),
                policies_evaluated: vec!["rate_limit".to_string()],
                evaluation_time_us: 0,
                rate_limit: Some(state),
            }),
        }
    }

    /// Add a header to the allowed request
    pub fn with_header(mut self, name: impl Into<String>, value: impl Into<String>) -> Self {
        self.headers_to_add.insert(name.into(), value.into());
        self
    }

    /// Set the denied-by policy
    pub fn with_policy(mut self, policy: impl Into<String>) -> Self {
        self.denied_by_policy = Some(policy.into());
        self
    }

    /// Set metadata
    pub fn with_metadata(mut self, metadata: RequestMetadata) -> Self {
        self.metadata = Some(metadata);
        self
    }
}

/// Sidecar service state
pub struct SidecarService {
    /// Configuration
    settings: SidecarSettings,
    // TODO: Add these when wiring up:
    // policy_engine: Arc<PolicyEngine>,
    // rate_limiter: Arc<RateLimiter>,
    // metrics: Arc<SidecarMetrics>,
}

impl SidecarService {
    /// Create a new sidecar service
    pub fn new(settings: SidecarSettings) -> Self {
        Self { settings }
    }

    /// Handle authorization request
    #[instrument(skip(self, request))]
    pub async fn authorize(&self, request: AuthzRequest) -> AuthzResponse {
        let start = std::time::Instant::now();
        let request_id = uuid::Uuid::new_v4().to_string();

        debug!(
            request_id = %request_id,
            method = %request.method,
            path = %request.path,
            "Processing authorization request"
        );

        // 1. Validate user info is present
        let user = match &request.user {
            Some(u) => u,
            None => {
                warn!(request_id = %request_id, "No user info in request");
                return AuthzResponse::unauthorized("Missing user information");
            }
        };

        // 2. Validate tenant
        let tenant_id = match &request.tenant_id {
            Some(t) => t,
            None => {
                warn!(request_id = %request_id, "No tenant ID in request");
                return AuthzResponse::deny("Missing tenant ID");
            }
        };

        // 3. Check rate limit (placeholder)
        // let rate_limit_result = self.rate_limiter.check(tenant_id, &user.id).await;
        // if let Some(state) = rate_limit_result.exceeded() {
        //     return AuthzResponse::rate_limited(state);
        // }

        // 4. Evaluate OPA policy (placeholder)
        // let policy_input = PolicyInput {
        //     user: user.clone(),
        //     tenant_id: tenant_id.clone(),
        //     method: request.method.clone(),
        //     path: request.path.clone(),
        //     scopes: user.scopes.clone(),
        // };
        // let policy_result = self.policy_engine.evaluate(&policy_input).await;
        // if !policy_result.allowed {
        //     return AuthzResponse::deny(policy_result.reason)
        //         .with_policy(policy_result.policy_name);
        // }

        let evaluation_time = start.elapsed().as_micros() as u64;

        // 5. Build allow response with enrichment headers
        let mut response = AuthzResponse::allow()
            .with_header("X-User-ID", &user.id)
            .with_header("X-Tenant-ID", tenant_id)
            .with_header("X-Request-ID", &request_id);

        // Add scopes header if present
        if !user.scopes.is_empty() {
            response = response.with_header("X-User-Scopes", user.scopes.join(","));
        }

        // Add roles header if present
        if !user.roles.is_empty() {
            response = response.with_header("X-User-Roles", user.roles.join(","));
        }

        // Add metadata
        response = response.with_metadata(RequestMetadata {
            request_id,
            policies_evaluated: vec!["default".to_string()],
            evaluation_time_us: evaluation_time,
            rate_limit: None,
        });

        info!(
            evaluation_time_us = evaluation_time,
            "Authorization allowed"
        );

        response
    }

    /// Convert response to gateway-specific format
    pub fn format_response(&self, response: AuthzResponse) -> Response<Body> {
        match self.settings.decision_format {
            DecisionFormat::StatusCode => {
                if response.allowed {
                    StatusCode::OK.into_response()
                } else {
                    StatusCode::from_u16(response.status_code.unwrap_or(403))
                        .unwrap_or(StatusCode::FORBIDDEN)
                        .into_response()
                }
            }
            DecisionFormat::JsonBody => {
                if response.allowed {
                    (StatusCode::OK, Json(response)).into_response()
                } else {
                    let status = StatusCode::from_u16(response.status_code.unwrap_or(403))
                        .unwrap_or(StatusCode::FORBIDDEN);
                    (status, Json(response)).into_response()
                }
            }
            DecisionFormat::EnvoyExtAuthz => {
                // Envoy ext_authz expects specific format
                self.format_envoy_response(response)
            }
            DecisionFormat::KongPlugin => {
                // Kong expects specific format
                self.format_kong_response(response)
            }
        }
    }

    /// Format response for Envoy ext_authz
    fn format_envoy_response(&self, response: AuthzResponse) -> Response<Body> {
        // Envoy ext_authz HTTP service expects:
        // - 200 OK with headers to add/remove for allowed
        // - 403/401 with body for denied
        if response.allowed {
            let mut builder = Response::builder().status(StatusCode::OK);

            // Add headers to inject into upstream request
            for (key, value) in &response.headers_to_add {
                builder = builder.header(format!("x-ext-authz-{}", key.to_lowercase()), value);
            }

            builder.body(Body::empty()).unwrap()
        } else {
            let status = StatusCode::from_u16(response.status_code.unwrap_or(403))
                .unwrap_or(StatusCode::FORBIDDEN);

            let body = serde_json::json!({
                "error": response.denial_reason.unwrap_or_else(|| "Forbidden".to_string()),
                "policy": response.denied_by_policy
            });

            (status, Json(body)).into_response()
        }
    }

    /// Format response for Kong authorization plugin
    fn format_kong_response(&self, response: AuthzResponse) -> Response<Body> {
        // Kong expects specific response format
        if response.allowed {
            let body = serde_json::json!({
                "status": "ok",
                "headers": response.headers_to_add,
                "remove_headers": response.headers_to_remove
            });
            (StatusCode::OK, Json(body)).into_response()
        } else {
            let body = serde_json::json!({
                "status": "denied",
                "message": response.denial_reason.unwrap_or_else(|| "Forbidden".to_string())
            });
            let status = StatusCode::from_u16(response.status_code.unwrap_or(403))
                .unwrap_or(StatusCode::FORBIDDEN);
            (status, Json(body)).into_response()
        }
    }
}

/// Axum handler for sidecar authorization endpoint
pub async fn handle_authz(
    State(service): State<Arc<SidecarService>>,
    Json(request): Json<AuthzRequest>,
) -> Response<Body> {
    let response = service.authorize(request).await;
    service.format_response(response)
}

/// Health check for sidecar mode
pub async fn health() -> &'static str {
    "OK"
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_sidecar(format: DecisionFormat) -> SidecarService {
        SidecarService::new(SidecarSettings {
            decision_format: format,
            ..Default::default()
        })
    }

    fn make_authz_request(user: Option<UserInfo>, tenant_id: Option<&str>) -> AuthzRequest {
        AuthzRequest {
            method: "GET".to_string(),
            path: "/api/v1/users".to_string(),
            headers: std::collections::HashMap::new(),
            source_ip: None,
            user,
            tenant_id: tenant_id.map(|s| s.to_string()),
            context: serde_json::Value::Null,
        }
    }

    fn make_user(roles: Vec<&str>, scopes: Vec<&str>) -> UserInfo {
        UserInfo {
            id: "user-456".to_string(),
            email: Some("user@example.com".to_string()),
            roles: roles.into_iter().map(|s| s.to_string()).collect(),
            scopes: scopes.into_iter().map(|s| s.to_string()).collect(),
            claims: std::collections::HashMap::new(),
        }
    }

    // === Existing tests ===

    #[test]
    fn test_authz_response_allow() {
        let response = AuthzResponse::allow();
        assert!(response.allowed);
        assert!(response.status_code.is_none());
    }

    #[test]
    fn test_authz_response_deny() {
        let response = AuthzResponse::deny("Policy violation");
        assert!(!response.allowed);
        assert_eq!(response.status_code, Some(403));
        assert_eq!(response.denial_reason, Some("Policy violation".to_string()));
    }

    #[test]
    fn test_authz_response_unauthorized() {
        let response = AuthzResponse::unauthorized("Missing token");
        assert!(!response.allowed);
        assert_eq!(response.status_code, Some(401));
    }

    #[test]
    fn test_authz_response_rate_limited() {
        let state = RateLimitState {
            current: 101,
            limit: 100,
            reset_at: 1700000000,
            remaining: 0,
        };
        let response = AuthzResponse::rate_limited(state);
        assert!(!response.allowed);
        assert_eq!(response.status_code, Some(429));
        assert!(response.headers_to_add.contains_key("X-RateLimit-Limit"));
        assert!(response
            .headers_to_add
            .contains_key("X-RateLimit-Remaining"));
        assert!(response.headers_to_add.contains_key("X-RateLimit-Reset"));
        assert_eq!(
            response.denial_reason,
            Some("Rate limit exceeded".to_string())
        );
        assert_eq!(response.denied_by_policy, Some("rate_limit".to_string()));
        assert!(response.metadata.is_some());
    }

    #[test]
    fn test_authz_response_with_headers() {
        let response = AuthzResponse::allow()
            .with_header("X-Custom", "value")
            .with_header("X-Another", "test");

        assert!(response.allowed);
        assert_eq!(
            response.headers_to_add.get("X-Custom"),
            Some(&"value".to_string())
        );
        assert_eq!(
            response.headers_to_add.get("X-Another"),
            Some(&"test".to_string())
        );
    }

    #[test]
    fn test_authz_response_with_policy() {
        let response = AuthzResponse::deny("forbidden").with_policy("rate_limit_policy");
        assert_eq!(
            response.denied_by_policy,
            Some("rate_limit_policy".to_string())
        );
    }

    #[test]
    fn test_authz_response_with_metadata() {
        let metadata = RequestMetadata {
            request_id: "req-1".to_string(),
            policies_evaluated: vec!["default".to_string()],
            evaluation_time_us: 100,
            rate_limit: None,
        };
        let response = AuthzResponse::allow().with_metadata(metadata);
        assert!(response.metadata.is_some());
        assert_eq!(response.metadata.unwrap().request_id, "req-1");
    }

    #[test]
    fn test_authz_request_deserialize() {
        let json = r#"{
            "method": "GET",
            "path": "/api/v1/users",
            "headers": {"Authorization": "Bearer token"},
            "tenant_id": "tenant-123",
            "user": {
                "id": "user-456",
                "email": "user@example.com",
                "roles": ["admin"],
                "scopes": ["read", "write"]
            }
        }"#;

        let request: AuthzRequest = serde_json::from_str(json).unwrap();
        assert_eq!(request.method, "GET");
        assert_eq!(request.path, "/api/v1/users");
        assert_eq!(request.tenant_id, Some("tenant-123".to_string()));
        assert!(request.user.is_some());
        assert_eq!(request.user.unwrap().id, "user-456");
    }

    #[test]
    fn test_authz_request_deserialize_minimal() {
        let json = r#"{"method":"POST","path":"/api"}"#;
        let request: AuthzRequest = serde_json::from_str(json).unwrap();
        assert_eq!(request.method, "POST");
        assert_eq!(request.path, "/api");
        assert!(request.user.is_none());
        assert!(request.tenant_id.is_none());
        assert!(request.headers.is_empty());
    }

    // === Authorize flow tests ===

    #[tokio::test]
    async fn test_authorize_no_user_returns_unauthorized() {
        let service = make_sidecar(DecisionFormat::JsonBody);
        let request = make_authz_request(None, Some("tenant-1"));

        let response = service.authorize(request).await;
        assert!(!response.allowed);
        assert_eq!(response.status_code, Some(401));
        assert!(response
            .denial_reason
            .as_ref()
            .unwrap()
            .contains("Missing user"));
    }

    #[tokio::test]
    async fn test_authorize_no_tenant_returns_deny() {
        let service = make_sidecar(DecisionFormat::JsonBody);
        let user = make_user(vec!["admin"], vec!["read"]);
        let request = make_authz_request(Some(user), None);

        let response = service.authorize(request).await;
        assert!(!response.allowed);
        assert_eq!(response.status_code, Some(403));
        assert!(response
            .denial_reason
            .as_ref()
            .unwrap()
            .contains("Missing tenant"));
    }

    #[tokio::test]
    async fn test_authorize_success_with_enrichment() {
        let service = make_sidecar(DecisionFormat::JsonBody);
        let user = make_user(vec!["admin", "devops"], vec!["read", "write"]);
        let request = make_authz_request(Some(user), Some("acme"));

        let response = service.authorize(request).await;
        assert!(response.allowed);
        assert_eq!(
            response.headers_to_add.get("X-User-ID"),
            Some(&"user-456".to_string())
        );
        assert_eq!(
            response.headers_to_add.get("X-Tenant-ID"),
            Some(&"acme".to_string())
        );
        assert!(response.headers_to_add.contains_key("X-Request-ID"));
        assert_eq!(
            response.headers_to_add.get("X-User-Scopes"),
            Some(&"read,write".to_string())
        );
        assert_eq!(
            response.headers_to_add.get("X-User-Roles"),
            Some(&"admin,devops".to_string())
        );
        assert!(response.metadata.is_some());
    }

    #[tokio::test]
    async fn test_authorize_no_scopes_no_roles() {
        let service = make_sidecar(DecisionFormat::JsonBody);
        let user = make_user(vec![], vec![]);
        let request = make_authz_request(Some(user), Some("acme"));

        let response = service.authorize(request).await;
        assert!(response.allowed);
        assert!(!response.headers_to_add.contains_key("X-User-Scopes"));
        assert!(!response.headers_to_add.contains_key("X-User-Roles"));
    }

    // === Format response tests ===

    #[test]
    fn test_format_status_code_allow() {
        let service = make_sidecar(DecisionFormat::StatusCode);
        let response = AuthzResponse::allow();
        let http_resp = service.format_response(response);
        assert_eq!(http_resp.status(), StatusCode::OK);
    }

    #[test]
    fn test_format_status_code_deny() {
        let service = make_sidecar(DecisionFormat::StatusCode);
        let response = AuthzResponse::deny("forbidden");
        let http_resp = service.format_response(response);
        assert_eq!(http_resp.status(), StatusCode::FORBIDDEN);
    }

    #[test]
    fn test_format_status_code_unauthorized() {
        let service = make_sidecar(DecisionFormat::StatusCode);
        let response = AuthzResponse::unauthorized("no token");
        let http_resp = service.format_response(response);
        assert_eq!(http_resp.status(), StatusCode::UNAUTHORIZED);
    }

    #[test]
    fn test_format_json_body_allow() {
        let service = make_sidecar(DecisionFormat::JsonBody);
        let response = AuthzResponse::allow();
        let http_resp = service.format_response(response);
        assert_eq!(http_resp.status(), StatusCode::OK);
    }

    #[test]
    fn test_format_json_body_deny() {
        let service = make_sidecar(DecisionFormat::JsonBody);
        let response = AuthzResponse::deny("blocked");
        let http_resp = service.format_response(response);
        assert_eq!(http_resp.status(), StatusCode::FORBIDDEN);
    }

    #[test]
    fn test_format_envoy_allow() {
        let service = make_sidecar(DecisionFormat::EnvoyExtAuthz);
        let response = AuthzResponse::allow().with_header("X-User-ID", "uid-1");
        let http_resp = service.format_response(response);
        assert_eq!(http_resp.status(), StatusCode::OK);
        // Envoy headers should be prefixed with x-ext-authz-
        assert!(http_resp.headers().get("x-ext-authz-x-user-id").is_some());
    }

    #[test]
    fn test_format_envoy_deny() {
        let service = make_sidecar(DecisionFormat::EnvoyExtAuthz);
        let response = AuthzResponse::deny("policy violation").with_policy("rbac");
        let http_resp = service.format_response(response);
        assert_eq!(http_resp.status(), StatusCode::FORBIDDEN);
    }

    #[test]
    fn test_format_kong_allow() {
        let service = make_sidecar(DecisionFormat::KongPlugin);
        let response = AuthzResponse::allow().with_header("X-Tenant", "acme");
        let http_resp = service.format_response(response);
        assert_eq!(http_resp.status(), StatusCode::OK);
    }

    #[test]
    fn test_format_kong_deny() {
        let service = make_sidecar(DecisionFormat::KongPlugin);
        let response = AuthzResponse::deny("rate exceeded");
        let http_resp = service.format_response(response);
        assert_eq!(http_resp.status(), StatusCode::FORBIDDEN);
    }

    #[test]
    fn test_health_endpoint() {
        let rt = tokio::runtime::Runtime::new().unwrap();
        let result = rt.block_on(health());
        assert_eq!(result, "OK");
    }
}
