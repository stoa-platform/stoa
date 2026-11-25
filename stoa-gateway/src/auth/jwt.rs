//! JWT Validation
//!
//! CAB-912 P2: JWT token validation with RS256 signature verification.
//!
//! Features:
//! - RS256 signature verification using JWKS
//! - Expiration check
//! - Issuer validation
//! - Audience validation
//! - Claims extraction
use jsonwebtoken::{decode, decode_header, Algorithm, Validation};
use std::sync::Arc;
use thiserror::Error;
use tracing::{debug, warn};

use super::claims::Claims;
use super::oidc::{OidcError, OidcProvider};

// =============================================================================
// Errors
// =============================================================================

#[derive(Debug, Error)]
pub enum JwtError {
    #[error("tenant_required")]
    TenantRequired,

    #[error("Missing Authorization header")]
    MissingHeader,

    #[error("Invalid Authorization header format (expected 'Bearer <token>')")]
    InvalidHeaderFormat,

    #[error("Token expired")]
    Expired,

    #[error("Invalid issuer: expected {expected}")]
    InvalidIssuer { expected: String },

    #[error("Invalid audience: expected {expected}")]
    InvalidAudience { expected: String },

    #[error("Invalid signature")]
    InvalidSignature,

    #[error("Token decode error: {0}")]
    DecodeError(String),

    #[error("Key not found for kid: {0}")]
    KeyNotFound(String),

    #[error("OIDC error: {0}")]
    OidcError(#[from] OidcError),

    #[error("Missing required claim: {0}")]
    MissingClaim(String),
}

// =============================================================================
// JWT Validator
// =============================================================================

/// JWT Validator configuration.
#[derive(Debug, Clone)]
pub struct JwtValidatorConfig {
    /// Clock skew tolerance in seconds
    pub leeway_seconds: u64,

    /// Temporary signed legacy claim compatibility (default: disabled).
    pub allow_legacy_tenant_claim: bool,

    /// Required scopes (if any)
    pub required_scopes: Vec<String>,
}

impl Default for JwtValidatorConfig {
    fn default() -> Self {
        Self {
            leeway_seconds: 30,
            required_scopes: vec![],
            allow_legacy_tenant_claim: false,
        }
    }
}

/// JWT Validator using OIDC provider for key fetching.
pub struct JwtValidator {
    oidc_provider: Arc<OidcProvider>,
    config: JwtValidatorConfig,
}

impl JwtValidator {
    /// Create a new JWT validator.
    pub fn new(oidc_provider: Arc<OidcProvider>) -> Self {
        Self {
            oidc_provider,
            config: JwtValidatorConfig::default(),
        }
    }

    /// Create with custom configuration.
    pub fn with_config(oidc_provider: Arc<OidcProvider>, config: JwtValidatorConfig) -> Self {
        Self {
            oidc_provider,
            config,
        }
    }

    /// Validate a JWT token using the configured policy.
    pub async fn validate(&self, token: &str) -> Result<Claims, JwtError> {
        self.validate_inner(token, None).await
    }

    /// Validate a token for MCP entrypoints: signature, issuer, lifetime and
    /// the configured MCP audience.
    pub async fn validate_mcp(&self, token: &str, audience: &str) -> Result<Claims, JwtError> {
        self.validate_with_audience(token, audience).await
    }

    /// Validate signature, issuer, lifetime and an explicit resource audience.
    pub async fn validate_with_audience(
        &self,
        token: &str,
        audience: &str,
    ) -> Result<Claims, JwtError> {
        if audience.trim().is_empty() {
            return Err(JwtError::MissingClaim(
                "configured resource audience".into(),
            ));
        }
        self.validate_inner(token, Some(audience)).await
    }

    async fn validate_inner(
        &self,
        token: &str,
        mcp_audience: Option<&str>,
    ) -> Result<Claims, JwtError> {
        // Decode header to get kid
        let header = decode_header(token)
            .map_err(|e| JwtError::DecodeError(format!("Invalid token header: {}", e)))?;

        debug!(
            alg = ?header.alg,
            kid = ?header.kid,
            "Decoding JWT header"
        );

        // Only support RS256
        if header.alg != Algorithm::RS256 {
            return Err(JwtError::DecodeError(format!(
                "Unsupported algorithm: {:?}. Only RS256 is supported.",
                header.alg
            )));
        }

        // Get the signing key
        let jwk = if let Some(kid) = &header.kid {
            self.oidc_provider.get_key(kid).await?
        } else {
            warn!("No kid in token header, using default key");
            self.oidc_provider.get_default_key().await?
        };

        // Convert to decoding key
        let decoding_key = jwk.to_decoding_key()?;

        // Build validation
        let mut validation = Validation::new(Algorithm::RS256);
        validation.validate_exp = true;
        validation.validate_nbf = true;
        validation.set_required_spec_claims(&["exp", "iss", "aud"]);
        validation.leeway = self.config.leeway_seconds;

        // These trust checks cannot be disabled by a custom validator config.
        validation.set_issuer(&[self.oidc_provider.issuer_url()]);
        validation.set_audience(&[mcp_audience.unwrap_or_else(|| self.oidc_provider.audience())]);

        // Decode and validate
        let token_data =
            decode::<Claims>(token, &decoding_key, &validation).map_err(|e| match e.kind() {
                jsonwebtoken::errors::ErrorKind::ExpiredSignature => JwtError::Expired,
                jsonwebtoken::errors::ErrorKind::InvalidIssuer => JwtError::InvalidIssuer {
                    expected: self.oidc_provider.issuer_url().to_string(),
                },
                jsonwebtoken::errors::ErrorKind::InvalidAudience => JwtError::InvalidAudience {
                    expected: mcp_audience
                        .unwrap_or_else(|| self.oidc_provider.audience())
                        .to_string(),
                },
                jsonwebtoken::errors::ErrorKind::InvalidSignature => JwtError::InvalidSignature,
                jsonwebtoken::errors::ErrorKind::Json(error)
                    if error.to_string().starts_with("invalid_tenant_claim") =>
                {
                    JwtError::TenantRequired
                }
                jsonwebtoken::errors::ErrorKind::Json(error)
                    if error.to_string().starts_with("missing field `sub`") =>
                {
                    JwtError::MissingClaim("sub".into())
                }
                _ => JwtError::DecodeError(e.to_string()),
            })?;

        let mut claims = token_data.claims;
        claims.validate_tenant(self.config.allow_legacy_tenant_claim)?;

        // Check required scopes
        if !self.config.required_scopes.is_empty() {
            for scope in &self.config.required_scopes {
                if !claims.has_scope(scope) {
                    return Err(JwtError::MissingClaim(format!("scope:{}", scope)));
                }
            }
        }

        debug!(
            sub = %claims.sub,
            tenant = ?claims.tenant_id(),
            "JWT validated successfully"
        );

        Ok(claims)
    }

    /// Extract a token from an Authorization header value.
    pub fn extract_token(auth_header: &str) -> Result<&str, JwtError> {
        let parts: Vec<&str> = auth_header.splitn(2, ' ').collect();

        if parts.len() != 2 {
            return Err(JwtError::InvalidHeaderFormat);
        }

        if parts[0].to_lowercase() != "bearer" {
            return Err(JwtError::InvalidHeaderFormat);
        }

        Ok(parts[1].trim())
    }

    /// Get the OIDC provider.
    pub fn oidc_provider(&self) -> &Arc<OidcProvider> {
        &self.oidc_provider
    }
}

// =============================================================================
// Token Extraction Helper
// =============================================================================

/// Extract token from various sources (header, cookie, query).
pub struct TokenExtractor;

impl TokenExtractor {
    /// Extract token from Authorization header.
    pub fn from_header(value: &str) -> Result<String, JwtError> {
        JwtValidator::extract_token(value).map(|s| s.to_string())
    }

    /// Extract token from cookie value.
    pub fn from_cookie(cookies: &str, cookie_name: &str) -> Option<String> {
        for cookie in cookies.split(';') {
            let parts: Vec<&str> = cookie.trim().splitn(2, '=').collect();
            if parts.len() == 2 && parts[0] == cookie_name {
                return Some(parts[1].to_string());
            }
        }
        None
    }
}

// =============================================================================
// Validated Token
// =============================================================================

/// A validated token with claims.
#[derive(Debug, Clone)]
pub struct ValidatedToken {
    /// The original token string
    pub raw_token: String,

    /// The validated claims
    pub claims: Claims,
}

impl ValidatedToken {
    /// Create a new validated token.
    pub fn new(raw_token: String, claims: Claims) -> Self {
        Self { raw_token, claims }
    }

    /// Get the user ID.
    pub fn user_id(&self) -> &str {
        self.claims.user_id()
    }

    /// Get the tenant ID.
    pub fn tenant_id(&self) -> Option<&str> {
        self.claims.tenant_id()
    }

    /// Get the username.
    pub fn username(&self) -> Option<&str> {
        self.claims.username()
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
pub(crate) mod tests {
    use super::*;

    #[test]
    fn test_extract_token_bearer() {
        let token =
            JwtValidator::extract_token("Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9").unwrap();
        assert_eq!(token, "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9");
    }

    #[test]
    fn test_extract_token_lowercase_bearer() {
        let token =
            JwtValidator::extract_token("bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9").unwrap();
        assert_eq!(token, "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9");
    }

    #[test]
    fn test_extract_token_missing_bearer() {
        let result = JwtValidator::extract_token("eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9");
        assert!(matches!(result, Err(JwtError::InvalidHeaderFormat)));
    }

    #[test]
    fn test_extract_token_wrong_scheme() {
        let result = JwtValidator::extract_token("Basic dXNlcjpwYXNz");
        assert!(matches!(result, Err(JwtError::InvalidHeaderFormat)));
    }

    #[test]
    fn test_token_from_cookie() {
        let cookies = "session=abc123; token=eyJhbGci.xxx.yyy; other=value";
        let token = TokenExtractor::from_cookie(cookies, "token");
        assert_eq!(token, Some("eyJhbGci.xxx.yyy".to_string()));
    }

    #[test]
    fn test_token_from_cookie_not_found() {
        let cookies = "session=abc123; other=value";
        let token = TokenExtractor::from_cookie(cookies, "token");
        assert!(token.is_none());
    }

    #[test]
    fn test_validator_config_default() {
        let config = JwtValidatorConfig::default();
        assert_eq!(config.leeway_seconds, 30);
    }

    include!("../../tests/fixtures/signing.rs");

    #[derive(serde::Serialize)]
    struct MintedClaims {
        sub: &'static str,
        exp: i64,
        iat: i64,
        iss: String,
        tenant_id: &'static str,
        aud: String,
    }

    async fn validator_against_test_key() -> (JwtValidator, String, wiremock::MockServer) {
        use wiremock::matchers::{method, path};
        use wiremock::{Mock, MockServer, ResponseTemplate};

        let server = MockServer::start().await;
        let issuer = format!("{}/realms/stoa", server.uri());
        let jwks = format!("{}/jwks", server.uri());
        Mock::given(method("GET"))
            .and(path("/realms/stoa/.well-known/openid-configuration"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "issuer": issuer,
                "authorization_endpoint": format!("{issuer}/auth"),
                "token_endpoint": format!("{issuer}/token"),
                "jwks_uri": jwks,
            })))
            .mount(&server)
            .await;
        Mock::given(method("GET"))
            .and(path("/jwks"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "keys": [{
                    "kty": "RSA",
                    "kid": "test-key",
                    "use": "sig",
                    "alg": "RS256",
                    "n": TEST_N,
                    "e": "AQAB"
                }]
            })))
            .mount(&server)
            .await;

        let provider = Arc::new(crate::auth::oidc::OidcProvider::new(
            crate::auth::oidc::OidcProviderConfig {
                issuer_url: issuer.clone(),
                audience: "stoa-caller".into(),
                ..crate::auth::oidc::OidcProviderConfig::default()
            },
        ));
        let validator = JwtValidator::new(provider);
        (validator, issuer, server)
    }

    fn mint(issuer: &str, exp: i64) -> String {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs() as i64;
        let mut header = jsonwebtoken::Header::new(jsonwebtoken::Algorithm::RS256);
        header.kid = Some("test-key".into());
        jsonwebtoken::encode(
            &header,
            &MintedClaims {
                sub: "svc",
                exp,
                iat: now,
                iss: issuer.to_string(),
                tenant_id: "tenant-a",
                aud: "stoa-caller".into(),
            },
            &jsonwebtoken::EncodingKey::from_rsa_pem(TEST_PEM.as_bytes()).unwrap(),
        )
        .unwrap()
    }

    #[tokio::test]
    async fn rs256_accepts_token_for_configured_audience() {
        let (validator, issuer, _server) = validator_against_test_key().await;
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs() as i64;
        let token = mint(&issuer, now + 300);
        let claims = validator.validate(&token).await.expect("valid token");
        assert_eq!(claims.sub, "svc");
        assert_eq!(claims.iss, issuer);
    }

    #[tokio::test]
    async fn rs256_rejects_expired_token() {
        let (validator, issuer, _server) = validator_against_test_key().await;
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs() as i64;
        let token = mint(&issuer, now - 120);
        let error = validator.validate(&token).await.expect_err("expired");
        assert!(matches!(error, JwtError::Expired));
    }

    #[tokio::test]
    async fn rs256_rejects_wrong_issuer() {
        let (validator, _issuer, _server) = validator_against_test_key().await;
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs() as i64;
        let token = mint("http://evil.example/realms/stoa", now + 300);
        let error = validator.validate(&token).await.expect_err("wrong iss");
        assert!(matches!(error, JwtError::InvalidIssuer { .. }));
    }
    include!("mcp_test_fixture.rs");
    fn mint_tenant_payload(issuer: &str, extra: serde_json::Value) -> String {
        let now = chrono::Utc::now().timestamp();
        let mut payload = serde_json::json!({"sub":"user", "iss":issuer, "aud":"stoa-caller", "iat":now, "exp":now+300,
            "realm_access":{"roles":["tenant-admin"]}});
        payload
            .as_object_mut()
            .unwrap()
            .extend(extra.as_object().unwrap().clone());
        let mut header = jsonwebtoken::Header::new(jsonwebtoken::Algorithm::RS256);
        header.kid = Some("test-key".into());
        jsonwebtoken::encode(
            &header,
            &payload,
            &jsonwebtoken::EncodingKey::from_rsa_pem(TEST_PEM.as_bytes()).unwrap(),
        )
        .unwrap()
    }

    #[tokio::test]
    async fn published_contract_enforces_its_resource_audience() {
        use crate::uac::binders::ProtocolBinder;
        use wiremock::{matchers::method, Mock, ResponseTemplate};

        let (validator, issuer, server) = validator_against_test_key().await;
        Mock::given(method("GET"))
            .and(wiremock::matchers::path("/upstream"))
            .respond_with(ResponseTemplate::new(200).set_body_string("accepted"))
            .mount(&server)
            .await;
        let mut state = crate::state::AppState::new(crate::config::Config::default());
        state.jwt_validator = Some(Arc::new(validator));
        let contract: crate::uac::UacContractSpec = serde_json::from_value(serde_json::json!({
            "name": "sample", "tenant_id": "sandbox", "version": "1",
            "status": "published", "inboundAuth": "jwt", "inboundAuthAudience": "items-read",
            "endpoints": [{"path": "/items/", "methods": ["GET"],
                "backend_url": format!("{}/upstream/", server.uri())}]
        }))
        .expect("contract");
        crate::uac::binders::rest::RestBinder::with_policies(
            state.route_registry.clone(),
            state.policy_registry.clone(),
        )
        .bind(&contract)
        .await
        .expect("bind");
        state.contract_registry.upsert(contract);
        for (audience, expected) in [
            (serde_json::json!("account"), 401),
            (serde_json::json!("different-resource"), 401),
            (serde_json::json!("stoa-caller"), 401),
            (serde_json::json!("items-read"), 200),
            (serde_json::json!(["account", "items-read"]), 200),
        ] {
            let token = mint_tenant_payload(
                &issuer,
                serde_json::json!({
                    "tenant_id": "sandbox", "aud": audience
                }),
            );
            let request = axum::http::Request::builder()
                .uri("/apis/sandbox/sample/items/")
                .header("Authorization", format!("Bearer {token}"))
                .body(axum::body::Body::empty())
                .expect("request");
            let response =
                crate::proxy::dynamic::dynamic_proxy(axum::extract::State(state.clone()), request)
                    .await;
            assert_eq!(response.status().as_u16(), expected);
        }
    }

    #[tokio::test]
    async fn regression_route_credential_forwarded_only_for_validated_jwt() {
        use crate::uac::binders::ProtocolBinder;
        use wiremock::{matchers::method, Mock, ResponseTemplate};

        let (validator, issuer, server) = validator_against_test_key().await;
        Mock::given(method("GET"))
            .and(wiremock::matchers::path("/upstream/ping"))
            .respond_with(ResponseTemplate::new(200).set_body_string("accepted"))
            .mount(&server)
            .await;
        let mut state = crate::state::AppState::new(crate::config::Config::default());
        state.jwt_validator = Some(Arc::new(validator));
        let binder = crate::uac::binders::rest::RestBinder::with_policies(
            state.route_registry.clone(),
            state.policy_registry.clone(),
        );
        for (name, auth) in [
            ("protected", serde_json::json!({"inboundAuth": "jwt"})),
            ("open", serde_json::json!({"public": true})),
        ] {
            let mut contract = serde_json::json!({
                "name": name, "tenant_id": "sandbox", "version": "1", "status": "published",
                "endpoints": [{"path": "/ping", "methods": ["GET"],
                    "backend_url": format!("{}/upstream/ping", server.uri())}]
            });
            contract
                .as_object_mut()
                .unwrap()
                .extend(auth.as_object().unwrap().clone());
            let contract: crate::uac::UacContractSpec =
                serde_json::from_value(contract).expect("contract");
            assert!(contract.validate().is_empty());
            binder.bind(&contract).await.expect("bind");
            state.contract_registry.upsert(contract);
            state
                .credential_store
                .upsert(crate::proxy::credentials::BackendCredential {
                    route_id: format!("uac:sandbox:{name}:0"),
                    auth_type: crate::proxy::credentials::AuthType::ApiKey,
                    header_name: "X-Backend-Key".into(),
                    header_value: format!("route-level-{name}"),
                    oauth2: None,
                    allowed_origin: None,
                    shared_with_tenants: false,
                });
        }
        let token = mint_tenant_payload(&issuer, serde_json::json!({"tenant_id": "sandbox"}));
        let call = |path: &'static str, bearer: Option<String>| {
            let state = state.clone();
            async move {
                let mut builder = axum::http::Request::builder().uri(path);
                if let Some(bearer) = bearer {
                    builder = builder.header("Authorization", format!("Bearer {bearer}"));
                }
                crate::proxy::dynamic::dynamic_proxy(
                    axum::extract::State(state),
                    builder.body(axum::body::Body::empty()).expect("request"),
                )
                .await
                .status()
                .as_u16()
            }
        };

        // Validated JWT on a route with a jwt_validation policy: credential forwarded.
        assert_eq!(
            call("/apis/sandbox/protected/ping", Some(token.clone())).await,
            200
        );
        // No bearer, or a bearer the gateway did not sign: refused, backend not called.
        assert_eq!(call("/apis/sandbox/protected/ping", None).await, 401);
        assert_eq!(
            call("/apis/sandbox/protected/ping", Some("not-a-jwt".into())).await,
            401
        );
        // Public route with a route credential: no bearer validation happens on
        // this path, so there is never an identity and the call is refused,
        // even with a valid JWT.
        assert_eq!(call("/apis/sandbox/open/ping", None).await, 401);
        assert_eq!(
            call("/apis/sandbox/open/ping", Some(token.clone())).await,
            401
        );

        let received = server.received_requests().await.unwrap_or_default();
        let forwarded: Vec<_> = received
            .iter()
            .filter(|request| request.url.path() == "/upstream/ping")
            .collect();
        assert_eq!(
            forwarded.len(),
            1,
            "only the validated call reaches the backend"
        );
        assert_eq!(
            forwarded[0]
                .headers
                .get("x-backend-key")
                .and_then(|value| value.to_str().ok()),
            Some("route-level-protected")
        );
    }

    /// A `tenant-a` contract route (`inboundAuth: jwt`) with a route credential,
    /// served by a wiremock backend on the same server as the OIDC discovery.
    async fn tenant_bound_route_state() -> (crate::state::AppState, String, wiremock::MockServer) {
        use crate::uac::binders::ProtocolBinder;
        use wiremock::{matchers::method, Mock, ResponseTemplate};

        let (validator, issuer, server) = validator_against_test_key().await;
        Mock::given(method("GET"))
            .and(wiremock::matchers::path("/upstream/ping"))
            .respond_with(ResponseTemplate::new(200).set_body_string("accepted"))
            .mount(&server)
            .await;
        let mut state = crate::state::AppState::new(crate::config::Config::default());
        state.jwt_validator = Some(Arc::new(validator));
        let contract: crate::uac::UacContractSpec = serde_json::from_value(serde_json::json!({
            "name": "orders", "tenant_id": "tenant-a", "version": "1", "status": "published",
            "inboundAuth": "jwt",
            "endpoints": [{"path": "/ping", "methods": ["GET"],
                "backend_url": format!("{}/upstream/ping", server.uri())}]
        }))
        .expect("contract");
        assert!(contract.validate().is_empty());
        crate::uac::binders::rest::RestBinder::with_policies(
            state.route_registry.clone(),
            state.policy_registry.clone(),
        )
        .bind(&contract)
        .await
        .expect("bind");
        state.contract_registry.upsert(contract);
        state
            .credential_store
            .upsert(crate::proxy::credentials::BackendCredential {
                route_id: "uac:tenant-a:orders:0".into(),
                auth_type: crate::proxy::credentials::AuthType::ApiKey,
                header_name: "X-Backend-Key".into(),
                header_value: "route-level-tenant-a".into(),
                oauth2: None,
                allowed_origin: None,
                shared_with_tenants: false,
            });
        (state, issuer, server)
    }

    async fn call_tenant_route(
        state: &crate::state::AppState,
        token: &str,
    ) -> axum::response::Response {
        let request = axum::http::Request::builder()
            .uri("/apis/tenant-a/orders/ping")
            .header("Authorization", format!("Bearer {token}"))
            .body(axum::body::Body::empty())
            .expect("request");
        crate::proxy::dynamic::dynamic_proxy(axum::extract::State(state.clone()), request).await
    }

    /// Backend requests received on `/upstream/ping`, with their credential header.
    async fn forwarded_credentials(server: &wiremock::MockServer) -> Vec<Option<String>> {
        server
            .received_requests()
            .await
            .unwrap_or_default()
            .iter()
            .filter(|request| request.url.path() == "/upstream/ping")
            .map(|request| {
                request
                    .headers
                    .get("x-backend-key")
                    .and_then(|value| value.to_str().ok())
                    .map(str::to_string)
            })
            .collect()
    }

    #[tokio::test]
    async fn regression_route_tenant_token_of_same_tenant_forwards_credential() {
        let (state, issuer, server) = tenant_bound_route_state().await;
        let token = mint_tenant_payload(&issuer, serde_json::json!({"tenant_id": "tenant-a"}));
        let response = call_tenant_route(&state, &token).await;
        assert_eq!(response.status(), axum::http::StatusCode::OK);
        assert_eq!(
            forwarded_credentials(&server).await,
            vec![Some("route-level-tenant-a".to_string())]
        );
    }

    #[tokio::test]
    async fn regression_route_tenant_token_of_other_tenant_is_403_without_backend_call() {
        let (state, issuer, server) = tenant_bound_route_state().await;
        // Same issuer, same signing key, same shared audience: only the tenant differs.
        let token = mint_tenant_payload(&issuer, serde_json::json!({"tenant_id": "tenant-b"}));
        let response = call_tenant_route(&state, &token).await;
        assert_eq!(response.status(), axum::http::StatusCode::FORBIDDEN);
        assert!(
            forwarded_credentials(&server).await.is_empty(),
            "the backend must not be called and the credential must not be sent"
        );
    }

    #[tokio::test]
    async fn regression_route_tenant_token_without_tenant_is_403() {
        let (state, issuer, server) = tenant_bound_route_state().await;
        let token = mint_tenant_payload(&issuer, serde_json::json!({}));
        let response = call_tenant_route(&state, &token).await;
        assert_eq!(response.status(), axum::http::StatusCode::FORBIDDEN);
        assert!(forwarded_credentials(&server).await.is_empty());
    }

    #[tokio::test]
    async fn regression_route_tenant_platform_admin_needs_route_tenant() {
        let (state, issuer, server) = tenant_bound_route_state().await;
        // A cpi-admin token without a tenant passes JWT validation, but carries
        // no tenant: there is no implicit admin exemption on tenant routes.
        let admin = mint_tenant_payload(
            &issuer,
            serde_json::json!({"realm_access": {"roles": ["cpi-admin"]}}),
        );
        let response = call_tenant_route(&state, &admin).await;
        assert_eq!(response.status(), axum::http::StatusCode::FORBIDDEN);
        // An admin token scoped to another tenant is refused as well.
        let admin_b = mint_tenant_payload(
            &issuer,
            serde_json::json!({"tenant_id": "tenant-b", "realm_access": {"roles": ["cpi-admin"]}}),
        );
        let response = call_tenant_route(&state, &admin_b).await;
        assert_eq!(response.status(), axum::http::StatusCode::FORBIDDEN);
        assert!(forwarded_credentials(&server).await.is_empty());
        // An admin token scoped to the route tenant is accepted.
        let admin_a = mint_tenant_payload(
            &issuer,
            serde_json::json!({"tenant_id": "tenant-a", "realm_access": {"roles": ["cpi-admin"]}}),
        );
        let response = call_tenant_route(&state, &admin_a).await;
        assert_eq!(response.status(), axum::http::StatusCode::OK);
        assert_eq!(
            forwarded_credentials(&server).await,
            vec![Some("route-level-tenant-a".to_string())]
        );
    }

    #[tokio::test]
    async fn regression_route_tenant_enforced_end_to_end_with_rs256_jwks() {
        let (state, issuer, server) = tenant_bound_route_state().await;
        let cases = [
            (serde_json::json!({"tenant_id": "tenant-a"}), 200),
            (serde_json::json!({"tenant_id": "tenant-b"}), 403),
            (serde_json::json!({"tenant_id": "TENANT-A"}), 403),
            (serde_json::json!({}), 403),
            (
                serde_json::json!({"realm_access": {"roles": ["cpi-admin"]}}),
                403,
            ),
        ];
        for (extra, expected) in cases {
            let token = mint_tenant_payload(&issuer, extra.clone());
            let response = call_tenant_route(&state, &token).await;
            assert_eq!(response.status().as_u16(), expected, "claims: {extra}");
        }
        // A token signed by the right key for the wrong issuer stays a 401.
        let foreign = mint_tenant_payload(
            "http://other-issuer.invalid/realms/stoa",
            serde_json::json!({"tenant_id": "tenant-a"}),
        );
        assert_eq!(
            call_tenant_route(&state, &foreign).await.status().as_u16(),
            401
        );
        assert_eq!(
            forwarded_credentials(&server).await,
            vec![Some("route-level-tenant-a".to_string())],
            "only the same-tenant call reaches the backend"
        );
    }

    #[tokio::test]
    async fn regression_route_tenant_single_element_array_claim_is_accepted() {
        let (state, issuer, server) = tenant_bound_route_state().await;
        let token = mint_tenant_payload(&issuer, serde_json::json!({"tenant_id": ["tenant-a"]}));
        let response = call_tenant_route(&state, &token).await;
        assert_eq!(response.status(), axum::http::StatusCode::OK);
        let other = mint_tenant_payload(&issuer, serde_json::json!({"tenant_id": ["tenant-b"]}));
        let response = call_tenant_route(&state, &other).await;
        assert_eq!(response.status(), axum::http::StatusCode::FORBIDDEN);
        assert_eq!(
            forwarded_credentials(&server).await,
            vec![Some("route-level-tenant-a".to_string())]
        );
    }

    #[tokio::test]
    async fn regression_admin_api_route_with_jwt_policy_enforces_route_tenant() {
        use wiremock::{matchers::method, Mock, ResponseTemplate};

        let (validator, issuer, server) = validator_against_test_key().await;
        Mock::given(method("GET"))
            .and(wiremock::matchers::path("/upstream/ping"))
            .respond_with(ResponseTemplate::new(200).set_body_string("accepted"))
            .mount(&server)
            .await;
        let mut state = crate::state::AppState::new(crate::config::Config::default());
        state.jwt_validator = Some(Arc::new(validator));
        // Route registered through /admin/apis: no contract_key, owned by tenant-a,
        // with a jwt_validation policy attached to its id.
        state.route_registry.upsert(crate::routes::ApiRoute {
            id: "admin-orders".into(),
            name: "admin-orders".into(),
            tenant_id: "tenant-a".into(),
            path_prefix: "/apis/tenant-a/admin-orders".into(),
            backend_url: format!("{}/upstream", server.uri()),
            methods: vec!["GET".into()],
            spec_hash: "1".into(),
            activated: true,
            classification: None,
            contract_key: None,
            upstream_http_version: Default::default(),
            upstreams: vec![],
            load_balancer: Default::default(),
            trusted_backend: true,
            public: false,
        });
        state.policy_registry.upsert(crate::routes::PolicyEntry {
            id: "jwt:admin-orders".into(),
            name: "jwt_validation".into(),
            policy_type: "jwt_validation".into(),
            config: serde_json::json!({}),
            priority: 0,
            api_id: "admin-orders".into(),
        });
        state
            .credential_store
            .upsert(crate::proxy::credentials::BackendCredential {
                route_id: "admin-orders".into(),
                auth_type: crate::proxy::credentials::AuthType::ApiKey,
                header_name: "X-Backend-Key".into(),
                header_value: "route-level-admin-orders".into(),
                oauth2: None,
                allowed_origin: None,
                shared_with_tenants: false,
            });
        let call = |tenant: &'static str| {
            let state = state.clone();
            let token = mint_tenant_payload(&issuer, serde_json::json!({"tenant_id": tenant}));
            async move {
                let request = axum::http::Request::builder()
                    .uri("/apis/tenant-a/admin-orders/ping")
                    .header("Authorization", format!("Bearer {token}"))
                    .body(axum::body::Body::empty())
                    .expect("request");
                crate::proxy::dynamic::dynamic_proxy(axum::extract::State(state), request)
                    .await
                    .status()
            }
        };

        assert_eq!(call("tenant-b").await, axum::http::StatusCode::FORBIDDEN);
        assert!(
            forwarded_credentials(&server).await.is_empty(),
            "a token of another tenant must not reach the backend"
        );
        assert_eq!(call("tenant-a").await, axum::http::StatusCode::OK);
        assert_eq!(
            forwarded_credentials(&server).await,
            vec![Some("route-level-admin-orders".to_string())]
        );
    }

    #[tokio::test]
    async fn regression_route_tenant_refusal_leaves_lb_state_untouched() {
        let (state, issuer, _server) = tenant_bound_route_state().await;
        let upstream_url = "http://tenant-lb-regression-upstream.invalid:9";
        let mut route = (*state
            .route_registry
            .get("uac:tenant-a:orders:0")
            .expect("bound route"))
        .clone();
        route.upstreams = vec![crate::lb::Upstream {
            url: upstream_url.into(),
            weight: 1,
            health_check_path: None,
        }];
        state.route_registry.upsert(route);

        let gauge = crate::metrics::LB_UPSTREAM_ACTIVE.with_label_values(&[upstream_url]);
        let before = gauge.get();
        let token = mint_tenant_payload(&issuer, serde_json::json!({"tenant_id": "tenant-b"}));
        for _ in 0..3 {
            let response = call_tenant_route(&state, &token).await;
            assert_eq!(response.status(), axum::http::StatusCode::FORBIDDEN);
        }
        assert_eq!(
            gauge.get(),
            before,
            "a refused call must not select an upstream"
        );
    }

    #[tokio::test]
    async fn regression_signed_tenant_claim_contract() {
        let (validator, issuer, _server) = validator_against_test_key().await;
        for extra in [
            serde_json::json!({}),
            serde_json::json!({"tenant":"tenant-b"}),
            serde_json::json!({"realm_access":{"roles":["tenant-other"]}}),
        ] {
            let error = validator
                .validate(&mint_tenant_payload(&issuer, extra))
                .await
                .unwrap_err();
            assert!(matches!(error, JwtError::TenantRequired));
        }
        let claims = validator
            .validate(&mint_tenant_payload(
                &issuer,
                serde_json::json!({"tenant_id":"tenant-a"}),
            ))
            .await
            .unwrap();
        assert_eq!(claims.tenant_id(), Some("tenant-a"));
        let mut migration = validator;
        migration.config.allow_legacy_tenant_claim = true;
        let claims = migration
            .validate(&mint_tenant_payload(
                &issuer,
                serde_json::json!({"tenant":"tenant-b"}),
            ))
            .await
            .unwrap();
        assert_eq!(claims.tenant_id(), Some("tenant-b"));
        assert!(migration
            .validate(&mint_tenant_payload(
                &issuer,
                serde_json::json!({"tenant_id":"tenant-a", "tenant":"tenant-b"})
            ))
            .await
            .is_err());
    }

    #[tokio::test]
    async fn regression_tenantless_tokens_rejected_on_all_http_mcp_paths() {
        use axum::{
            body::Body,
            http::{Request, StatusCode},
        };
        use tower::ServiceExt;
        let (validator, issuer, _server) = validator_against_test_key().await;
        let mut state = crate::state::AppState::new(crate::config::Config::default());
        state.config.mcp_audience = Some("stoa-caller".to_string());
        state.jwt_validator = Some(Arc::new(validator));
        let app = crate::build_router(state.clone());
        let token = mint_tenant_payload(&issuer, serde_json::json!({}));
        for (method, path, body) in [
            ("GET", "/mcp/v1/tools", ""),
            ("POST", "/mcp/tools/list", "{}"),
            (
                "POST",
                "/mcp/tools/call",
                r#"{"name":"tool","arguments":{}}"#,
            ),
            (
                "POST",
                "/mcp/v1/tools/invoke",
                r#"{"tool":"tool","arguments":{}}"#,
            ),
            ("GET", "/mcp/sse", ""),
            ("DELETE", "/mcp/sse?sessionId=other", ""),
            (
                "POST",
                "/mcp",
                r#"{"jsonrpc":"2.0","id":1,"method":"tools/list"}"#,
            ),
            (
                "POST",
                "/mcp/sse",
                r#"{"jsonrpc":"2.0","id":1,"method":"initialize"}"#,
            ),
            (
                "POST",
                "/mcp",
                r#"[{"jsonrpc":"2.0","id":1,"method":"tools/list"}]"#,
            ),
            ("GET", "/mcp/events?tenant_id=other", ""),
        ] {
            let response = app
                .clone()
                .oneshot(
                    Request::builder()
                        .method(method)
                        .uri(path)
                        .header("Authorization", format!("Bearer {token}"))
                        .header("X-Tenant-ID", "tenant-a")
                        .header("Content-Type", "application/json")
                        .body(Body::from(body))
                        .unwrap(),
                )
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::FORBIDDEN, "{method} {path}");
        }
        assert_eq!(state.session_manager.count(), 0);
    }

    #[tokio::test]
    async fn regression_event_query_cannot_change_verified_tenant() {
        use axum::{
            body::Body,
            http::{Request, StatusCode},
        };
        use tower::ServiceExt;
        let (validator, issuer, _server) = validator_against_test_key().await;
        let mut state = crate::state::AppState::new(crate::config::Config::default());
        state.config.mcp_audience = Some("stoa-caller".to_string());
        state.jwt_validator = Some(Arc::new(validator));
        let app = crate::build_router(state);
        let token = mint_tenant_payload(&issuer, serde_json::json!({"tenant_id":"tenant-a"}));
        for (path, expected) in [
            ("/mcp/events", StatusCode::OK),
            ("/mcp/events?tenant_id=other", StatusCode::FORBIDDEN),
        ] {
            let response = app
                .clone()
                .oneshot(
                    Request::builder()
                        .uri(path)
                        .header("Authorization", format!("Bearer {token}"))
                        .header("X-Tenant-ID", "tenant-a")
                        .body(Body::empty())
                        .unwrap(),
                )
                .await
                .unwrap();
            assert_eq!(response.status(), expected);
        }
    }

    #[tokio::test]
    async fn regression_websocket_identity_never_uses_header_or_unknown() {
        use axum::{
            http::{HeaderMap, HeaderValue, StatusCode},
            response::IntoResponse,
        };
        let (validator, issuer, _server) = validator_against_test_key().await;
        let mut state = crate::state::AppState::new(crate::config::Config::default());
        state.config.mcp_audience = Some("stoa-caller".to_string());
        state.jwt_validator = Some(Arc::new(validator));
        for browser in [false, true] {
            let mut headers = HeaderMap::new();
            headers.insert("X-Tenant-ID", HeaderValue::from_static("tenant-a"));
            let missing = mint_tenant_payload(&issuer, serde_json::json!({}));
            let scoped = mint_tenant_payload(&issuer, serde_json::json!({"tenant_id":"tenant-a"}));
            let name = if browser {
                "Sec-WebSocket-Protocol"
            } else {
                "Authorization"
            };
            let value = if browser {
                format!("mcp-auth.{missing}")
            } else {
                format!("Bearer {missing}")
            };
            headers.insert(name, HeaderValue::from_str(&value).unwrap());
            let error = crate::mcp::ws::websocket_identity(&state, &headers)
                .await
                .unwrap_err();
            assert_eq!(error.into_response().status(), StatusCode::FORBIDDEN);
            let value = if browser {
                format!("mcp-auth.{scoped}")
            } else {
                format!("Bearer {scoped}")
            };
            headers.insert(name, HeaderValue::from_str(&value).unwrap());
            let (_, tenant) = crate::mcp::ws::websocket_identity(&state, &headers)
                .await
                .unwrap();
            assert_eq!(tenant, "tenant-a");
        }
        assert_eq!(state.session_manager.count(), 0);
    }

    struct CompositionTool {
        name: &'static str,
        owner: Option<&'static str>,
        calls: Arc<std::sync::atomic::AtomicUsize>,
    }

    #[async_trait::async_trait]
    impl crate::mcp::tools::Tool for CompositionTool {
        fn name(&self) -> &str {
            self.name
        }
        fn description(&self) -> &str {
            "Synthetic composition probe"
        }
        fn input_schema(&self) -> crate::mcp::tools::ToolSchema {
            crate::mcp::tools::ToolSchema {
                schema_type: "object".into(),
                properties: Default::default(),
                required: vec![],
            }
        }
        fn tenant_id(&self) -> Option<&str> {
            self.owner
        }
        async fn execute(
            &self,
            _args: serde_json::Value,
            _ctx: &crate::mcp::tools::ToolContext,
        ) -> Result<crate::mcp::tools::ToolResult, crate::mcp::tools::ToolError> {
            self.calls.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
            Ok(crate::mcp::tools::ToolResult::text(
                "synthetic-probe-result",
            ))
        }
    }

    #[tokio::test]
    async fn regression_signed_gateway_audience_is_required() {
        let (validator, issuer, _server) = validator_against_test_key().await;
        for audience in [serde_json::json!(null), serde_json::json!("other-resource")] {
            let token = mint_tenant_payload(
                &issuer,
                serde_json::json!({"tenant_id":"tenant-a", "aud":audience}),
            );
            assert!(validator.validate(&token).await.is_err());
        }
        let token = mint_tenant_payload(
            &issuer,
            serde_json::json!({"tenant_id":"tenant-a", "aud":"stoa-caller"}),
        );
        assert!(validator.validate(&token).await.is_ok());
    }

    #[tokio::test]
    async fn regression_bound_tokens_rejected_by_all_mcp_identity_paths() {
        use axum::{
            http::{HeaderMap, HeaderValue, StatusCode},
            response::IntoResponse,
        };
        let (validator, issuer, _server) = validator_against_test_key().await;
        let mut state = crate::state::AppState::new(crate::config::Config::default());
        state.config.mcp_audience = Some("stoa-caller".to_string());
        state.jwt_validator = Some(Arc::new(validator));
        for cnf in [
            serde_json::json!({"jkt":"synthetic-thumbprint"}),
            serde_json::json!({"x5t#S256":"synthetic-thumbprint"}),
        ] {
            let token = mint_tenant_payload(
                &issuer,
                serde_json::json!({"tenant_id":"tenant-a", "cnf":cnf}),
            );
            let mut headers = HeaderMap::new();
            headers.insert(
                "Authorization",
                HeaderValue::from_str(&format!("Bearer {token}")).unwrap(),
            );
            let error = crate::auth::tenant::request_identity(&state, &headers)
                .await
                .unwrap_err();
            assert_eq!(error.into_response().status(), StatusCode::UNAUTHORIZED);
            let mut browser = HeaderMap::new();
            browser.insert(
                "Sec-WebSocket-Protocol",
                HeaderValue::from_str(&format!("mcp-auth.{token}")).unwrap(),
            );
            assert!(crate::mcp::ws::websocket_identity(&state, &browser)
                .await
                .is_err());
        }
        assert_eq!(state.session_manager.count(), 0);
    }

    #[tokio::test]
    async fn regression_resource_metadata_and_invocation_are_tenant_scoped() {
        use axum::{
            body::{to_bytes, Body},
            http::{Request, StatusCode},
        };
        use tower::ServiceExt;
        let (validator, issuer, _server) = validator_against_test_key().await;
        let mut state = crate::state::AppState::new(crate::config::Config {
            policy_enabled: false,
            ..crate::config::Config::default()
        });
        state.config.mcp_audience = Some("stoa-caller".to_string());
        state.jwt_validator = Some(Arc::new(validator));
        state.tool_registry.mark_loaded("tenant-a");
        let calls = Arc::new(std::sync::atomic::AtomicUsize::new(0));
        for (name, owner) in [
            ("private_b", Some("tenant-b")),
            ("private_a", Some("tenant-a")),
            ("global_probe", None),
        ] {
            state.tool_registry.register(Arc::new(CompositionTool {
                name,
                owner,
                calls: calls.clone(),
            }));
        }
        let token = mint_tenant_payload(&issuer, serde_json::json!({"tenant_id":"tenant-a"}));
        let app = crate::build_router(state);
        for path in ["/mcp", "/mcp/sse"] {
            for method in ["resources/list", "resources/read", "tools/call"] {
                let request = serde_json::json!({"jsonrpc":"2.0", "id":1, "method":method,
                    "params":{"uri":"stoa://tools/private_b", "name":"private_b", "arguments":{}}});
                for batch in [false, true] {
                    let body = if batch {
                        serde_json::json!([request.clone()])
                    } else {
                        request.clone()
                    };
                    let response = app
                        .clone()
                        .oneshot(
                            Request::builder()
                                .method("POST")
                                .uri(path)
                                .header("Authorization", format!("Bearer {token}"))
                                .header("X-Tenant-ID", "tenant-a")
                                .header("Content-Type", "application/json")
                                .body(Body::from(body.to_string()))
                                .unwrap(),
                        )
                        .await
                        .unwrap();
                    assert_eq!(response.status(), StatusCode::OK);
                    let body: serde_json::Value = serde_json::from_slice(
                        &to_bytes(response.into_body(), 1_048_576).await.unwrap(),
                    )
                    .unwrap();
                    let response = if batch { &body[0] } else { &body };
                    if method == "resources/list" {
                        let resources = response["result"]["resources"].as_array().unwrap();
                        assert!(resources.iter().any(|r| r["name"] == "private_a"));
                        assert!(resources.iter().any(|r| r["name"] == "global_probe"));
                        assert!(!resources.iter().any(|r| r["name"] == "private_b"));
                    } else {
                        assert!(response["error"].is_object());
                    }
                }
            }
        }
        assert_eq!(calls.load(std::sync::atomic::Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn regression_transport_policy_consistency() {
        use axum::{
            body::{to_bytes, Body},
            http::{HeaderMap, HeaderValue, Request, StatusCode},
        };
        use tower::ServiceExt;
        let (validator, issuer, _server) = validator_against_test_key().await;
        let mut state = crate::state::AppState::new(crate::config::Config {
            policy_enabled: false,
            ..crate::config::Config::default()
        });
        state.config.mcp_audience = Some("stoa-caller".to_string());
        state.jwt_validator = Some(Arc::new(validator));
        let calls = Arc::new(std::sync::atomic::AtomicUsize::new(0));
        state.tool_registry.register(Arc::new(CompositionTool {
            name: "probe",
            owner: None,
            calls: calls.clone(),
        }));
        state.guardrail_policy_store.upsert(
            "tenant-a".into(),
            crate::guardrails::policy::TenantGuardrailPolicy {
                allowed_tools: Some(vec![]),
                ..Default::default()
            },
        );
        state
            .session_manager
            .create(crate::mcp::session::Session::new(
                "ws-session".into(),
                "tenant-a".into(),
            ))
            .await;
        let token = mint_tenant_payload(&issuer, serde_json::json!({"tenant_id":"tenant-a"}));
        let rpc = serde_json::json!({"jsonrpc":"2.0", "id":1, "method":"tools/call", "params":{"name":"probe", "arguments":{}}});
        let app = crate::build_router(state.clone());
        for (path, body) in [
            (
                "/mcp/tools/call",
                serde_json::json!({"name":"probe", "arguments":{}}),
            ),
            ("/mcp", rpc.clone()),
            ("/mcp/sse", rpc.clone()),
            ("/mcp", serde_json::json!([rpc.clone()])),
        ] {
            let response = app
                .clone()
                .oneshot(
                    Request::builder()
                        .method("POST")
                        .uri(path)
                        .header("Authorization", format!("Bearer {token}"))
                        .header("Content-Type", "application/json")
                        .body(Body::from(body.to_string()))
                        .unwrap(),
                )
                .await
                .unwrap();
            if path == "/mcp/tools/call" {
                assert_eq!(response.status(), StatusCode::FORBIDDEN);
            } else {
                let value: serde_json::Value = serde_json::from_slice(
                    &to_bytes(response.into_body(), 1_048_576).await.unwrap(),
                )
                .unwrap();
                assert!(value["error"].is_object() || value[0]["error"].is_object());
            }
        }
        let mut headers = HeaderMap::new();
        headers.insert(
            "Authorization",
            HeaderValue::from_str(&format!("Bearer {token}")).unwrap(),
        );
        let response = crate::mcp::sse::process_single_request(
            &state,
            &headers,
            &crate::mcp::sse::SseQueryParams {
                session_id: Some("ws-session".into()),
            },
            serde_json::from_value(rpc).unwrap(),
        )
        .await;
        assert!(response.error.is_some());
        assert_eq!(calls.load(std::sync::atomic::Ordering::SeqCst), 0);
    }
    fn mint_value(mut claims: serde_json::Value) -> String {
        claims["iat"] = serde_json::json!(std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs());
        let mut header = jsonwebtoken::Header::new(Algorithm::RS256);
        header.kid = Some("test-key".into());
        jsonwebtoken::encode(
            &header,
            &claims,
            &jsonwebtoken::EncodingKey::from_rsa_pem(TEST_PEM.as_bytes()).unwrap(),
        )
        .unwrap()
    }

    #[tokio::test]
    async fn regression_rejects_missing_or_wrong_audience() {
        let (validator, issuer, _server) = validator_against_test_key().await;
        for audience in [None, Some("another-resource")] {
            let mut claims = serde_json::json!({
                "sub": "svc", "iss": issuer, "exp": 4_000_000_000_u64
            });
            if let Some(audience) = audience {
                claims["aud"] = audience.into();
            }
            assert!(validator.validate(&mint_value(claims)).await.is_err());
        }
    }

    #[tokio::test]
    async fn regression_rejects_unsigned_token() {
        use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
        let (validator, issuer, _server) = validator_against_test_key().await;
        let header = URL_SAFE_NO_PAD.encode(br#"{"alg":"none","typ":"JWT"}"#);
        let claims = URL_SAFE_NO_PAD.encode(
            serde_json::to_vec(&serde_json::json!({
                "sub": "svc", "iss": issuer, "aud": "stoa-caller", "exp": 4_000_000_000_u64
            }))
            .unwrap(),
        );
        assert!(validator
            .validate(&format!("{header}.{claims}."))
            .await
            .is_err());
    }

    #[tokio::test]
    async fn regression_rejects_invalid_signature() {
        let (validator, issuer, _server) = validator_against_test_key().await;
        let token = mint(&issuer, 4_000_000_000);
        let (signed, signature) = token.rsplit_once('.').unwrap();
        let replacement = if signature.starts_with('A') { "B" } else { "A" };
        let candidate = format!("{signed}.{replacement}{}", &signature[1..]);
        assert!(matches!(
            validator.validate(&candidate).await,
            Err(JwtError::InvalidSignature)
        ));
    }

    #[tokio::test]
    async fn regression_rejects_missing_expiration() {
        let (validator, issuer, _server) = validator_against_test_key().await;
        let token = mint_value(serde_json::json!({
            "sub": "svc", "iss": issuer, "aud": "stoa-caller"
        }));
        assert!(validator.validate(&token).await.is_err());
    }
}
