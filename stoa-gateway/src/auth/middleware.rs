//! Auth Middleware
//!
//! CAB-912 P2: Axum middleware for JWT authentication.
//!
//! Features:
//! - Extract JWT from Authorization header
//! - Validate token and extract claims
//! - Inject authenticated user into request extensions
//! - Optional authentication (for public endpoints)
use axum::{
    body::Body,
    extract::{FromRequestParts, State},
    http::{header::AUTHORIZATION, Request, StatusCode},
    middleware::Next,
    response::{IntoResponse, Response},
    Json,
};
use serde::Serialize;
use std::sync::Arc;
use tracing::{debug, instrument, warn};

use super::claims::Claims;
use super::jwt::{JwtError, JwtValidator, ValidatedToken};
use super::subscription::SubscriptionValidator;
use crate::state::AppState;

// =============================================================================
// Auth State
// =============================================================================

/// Authentication state shared across handlers.
#[derive(Clone)]
pub struct AuthState {
    /// JWT validator
    pub validator: Arc<JwtValidator>,

    /// Whether authentication is required (false = optional)
    pub required: bool,
}

impl AuthState {
    /// Create a new auth state with required authentication.
    pub fn new(validator: Arc<JwtValidator>) -> Self {
        Self {
            validator,
            required: true,
        }
    }

    /// Create with optional authentication.
    pub fn optional(validator: Arc<JwtValidator>) -> Self {
        Self {
            validator,
            required: false,
        }
    }
}

// =============================================================================
// Authenticated User (Request Extension)
// =============================================================================

/// Authenticated user extracted from JWT.
///
/// This is injected into request extensions by the auth middleware.
/// Custom Debug impl redacts raw_token to prevent cleartext credential logging.
#[derive(Clone)]
pub struct AuthenticatedUser {
    /// User ID (from sub claim)
    pub user_id: String,

    /// Username (from preferred_username)
    pub username: Option<String>,

    /// Email address
    pub email: Option<String>,

    /// Tenant ID
    pub tenant_id: Option<String>,

    /// Full claims (for advanced use)
    pub claims: Claims,

    /// Raw token (for forwarding to downstream services)
    pub raw_token: String,
}

impl std::fmt::Debug for AuthenticatedUser {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("AuthenticatedUser")
            .field("user_id", &self.user_id)
            .field("username", &"[REDACTED]")
            .field("email", &"[REDACTED]")
            .field("tenant_id", &self.tenant_id)
            .field("raw_token", &"[REDACTED]")
            .finish()
    }
}

impl AuthenticatedUser {
    /// Create from a validated token.
    pub fn from_token(token: ValidatedToken) -> Self {
        Self {
            user_id: token.claims.user_id().to_string(),
            username: token.claims.username().map(|s| s.to_string()),
            email: token.claims.email.clone(),
            tenant_id: token.claims.tenant_id().map(|s| s.to_string()),
            claims: token.claims,
            raw_token: token.raw_token,
        }
    }

    /// Check if the user has a specific realm role.
    pub fn has_role(&self, role: &str) -> bool {
        self.claims.has_realm_role(role)
    }

    /// Check if the user has a specific scope.
    pub fn has_scope(&self, scope: &str) -> bool {
        self.claims.has_scope(scope)
    }

    /// Check if the user can access a specific tenant.
    pub fn can_access_tenant(&self, tenant: &str) -> bool {
        // CPI admins can access all tenants
        if self.claims.stoa_role() == Some(super::claims::StoaRole::CpiAdmin) {
            return true;
        }

        // Otherwise, must match user's tenant
        self.tenant_id.as_deref() == Some(tenant)
    }
}

// =============================================================================
// Auth Error Response
// =============================================================================

/// Authentication error response.
#[derive(Debug, Serialize)]
pub struct AuthError {
    pub error: String,
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub details: Option<String>,
}

impl AuthError {
    pub fn unauthorized(message: &str) -> Self {
        Self {
            error: "unauthorized".to_string(),
            message: message.to_string(),
            details: None,
        }
    }

    pub fn forbidden(message: &str) -> Self {
        Self {
            error: "forbidden".to_string(),
            message: message.to_string(),
            details: None,
        }
    }
}

impl IntoResponse for AuthError {
    fn into_response(self) -> Response {
        let status = if self.error == "forbidden" {
            StatusCode::FORBIDDEN
        } else {
            StatusCode::UNAUTHORIZED
        };

        (status, Json(self)).into_response()
    }
}

// =============================================================================
// Auth Middleware
// =============================================================================

/// JWT authentication middleware.
///
/// Extracts and validates JWT from Authorization header.
/// If valid, injects `AuthenticatedUser` into request extensions.
#[instrument(name = "auth.jwt", skip_all, fields(otel.kind = "internal"))]
pub async fn auth_middleware(
    State(auth_state): State<AuthState>,
    mut request: Request<Body>,
    next: Next,
) -> Result<Response, AuthError> {
    // Extract Authorization header
    let auth_header = request
        .headers()
        .get(AUTHORIZATION)
        .and_then(|v| v.to_str().ok());

    match auth_header {
        Some(header) => {
            // Extract and validate token
            let token = JwtValidator::extract_token(header)
                .map_err(|e| AuthError::unauthorized(&e.to_string()))?;

            let claims = auth_state.validator.validate(token).await.map_err(|e| {
                warn!(error = %e, "JWT validation failed");
                match e {
                    JwtError::Expired => AuthError::unauthorized("Token expired"),
                    JwtError::InvalidIssuer { .. } => AuthError::unauthorized("Invalid issuer"),
                    JwtError::InvalidAudience { .. } => AuthError::unauthorized("Invalid audience"),
                    JwtError::InvalidSignature => AuthError::unauthorized("Invalid signature"),
                    _ => AuthError::unauthorized(&e.to_string()),
                }
            })?;

            let validated = ValidatedToken::new(token.to_string(), claims);
            let user = AuthenticatedUser::from_token(validated);

            debug!(
                user_id = %user.user_id,
                tenant = ?user.tenant_id,
                "User authenticated"
            );

            // Inject user into request extensions
            request.extensions_mut().insert(user);
        }
        None => {
            if auth_state.required {
                return Err(AuthError::unauthorized("Missing Authorization header"));
            }
            // Optional auth: continue without user
            debug!("No auth header, continuing as anonymous");
        }
    }

    Ok(next.run(request).await)
}

/// Require authentication middleware (returns 401 if no token).
pub async fn require_auth(
    State(auth_state): State<AuthState>,
    request: Request<Body>,
    next: Next,
) -> Result<Response, AuthError> {
    let state = AuthState {
        validator: auth_state.validator,
        required: true,
    };
    auth_middleware(State(state), request, next).await
}

/// Require JWT authentication on MCP REST routes (CAB-2121).
///
/// Runs on `State<AppState>` so it can read `Option<Arc<JwtValidator>>` directly.
/// Returns 401 with `WWW-Authenticate: Bearer …` when the caller is anonymous or
/// presents an invalid token. When `state.jwt_validator` is `None` (dev/test
/// configurations without Keycloak), the middleware is a passthrough. Production
/// always has `keycloak_url` set so `jwt_validator` is `Some`.
#[instrument(name = "auth.mcp_jwt_required", skip_all, fields(otel.kind = "internal"))]
pub async fn mcp_jwt_required(
    State(state): State<AppState>,
    mut request: Request<Body>,
    next: Next,
) -> Response {
    let validator = match &state.jwt_validator {
        Some(v) => v.clone(),
        None => {
            warn!("JWT validator not configured — /mcp/* auth gate bypassed");
            return next.run(request).await;
        }
    };

    let auth_header = request
        .headers()
        .get(AUTHORIZATION)
        .and_then(|v| v.to_str().ok());

    let header = match auth_header {
        Some(h) => h,
        None => {
            return mcp_auth_challenge(
                r#"Bearer resource_metadata="/.well-known/oauth-protected-resource""#,
                "Missing Authorization header",
            );
        }
    };

    let token = match JwtValidator::extract_token(header) {
        Ok(t) => t,
        Err(_) => {
            return mcp_auth_challenge(
                r#"Bearer error="invalid_token", resource_metadata="/.well-known/oauth-protected-resource""#,
                "Malformed Authorization header",
            );
        }
    };

    let claims = match validator.validate(token).await {
        Ok(c) => c,
        Err(e) => {
            warn!(error = %e, "JWT validation failed on /mcp/* route");
            let msg = match e {
                JwtError::Expired => "Token expired",
                JwtError::InvalidIssuer { .. } => "Invalid issuer",
                JwtError::InvalidAudience { .. } => "Invalid audience",
                JwtError::InvalidSignature => "Invalid signature",
                _ => "Invalid token",
            };
            return mcp_auth_challenge(
                r#"Bearer error="invalid_token", resource_metadata="/.well-known/oauth-protected-resource""#,
                msg,
            );
        }
    };

    let validated = ValidatedToken::new(token.to_string(), claims);
    let user = AuthenticatedUser::from_token(validated);
    debug!(
        user_id = %user.user_id,
        tenant = ?user.tenant_id,
        "MCP request authenticated",
    );
    request.extensions_mut().insert(user);

    next.run(request).await
}

/// Build the 401 response for `mcp_jwt_required` with a uniform body shape.
fn mcp_auth_challenge(www_authenticate: &'static str, message: &str) -> Response {
    let body = AuthError::unauthorized(message);
    let mut response = (StatusCode::UNAUTHORIZED, Json(body)).into_response();
    if let Ok(value) = axum::http::HeaderValue::from_str(www_authenticate) {
        response
            .headers_mut()
            .insert(axum::http::header::WWW_AUTHENTICATE, value);
    }
    response
}

/// Optional authentication middleware (continues if no token).
pub async fn optional_auth(
    State(auth_state): State<AuthState>,
    request: Request<Body>,
    next: Next,
) -> Result<Response, AuthError> {
    let state = AuthState {
        validator: auth_state.validator,
        required: false,
    };
    auth_middleware(State(state), request, next).await
}

// =============================================================================
// Subscription Middleware
// =============================================================================

/// State for subscription validation middleware.
#[derive(Clone)]
pub struct SubscriptionState {
    /// Subscription validator (cache + CP API client)
    pub validator: Arc<SubscriptionValidator>,
}

/// Subscription validation middleware.
///
/// Runs AFTER JWT auth middleware. Extracts `azp` claim from the authenticated
/// user's JWT and validates that an active subscription exists for the target API.
///
/// The `target_api_id` is read from request extensions (set by route matching).
/// If not present, the middleware is skipped (non-proxy routes).
///
/// Returns 401 if `azp` claim is missing, 403 if no active subscription.
#[instrument(name = "auth.subscription", skip_all, fields(otel.kind = "internal"))]
pub async fn subscription_middleware(
    State(sub_state): State<SubscriptionState>,
    mut request: Request<Body>,
    next: Next,
) -> Result<Response, AuthError> {
    // Only check subscription if there's an authenticated user
    let user = match request.extensions().get::<AuthenticatedUser>() {
        Some(user) => user.clone(),
        None => {
            // No authenticated user — skip subscription check (JWT middleware handles auth)
            return Ok(next.run(request).await);
        }
    };

    // Only check subscription if route has a target_api_id
    let api_id = match request.extensions().get::<TargetApiId>() {
        Some(target) => target.0.clone(),
        None => {
            // No target API — not a proxied route, skip subscription check
            return Ok(next.run(request).await);
        }
    };

    // Extract azp (authorized party) = Keycloak client_id
    let azp = match &user.claims.azp {
        Some(azp) => azp.clone(),
        None => {
            warn!(
                user_id = %user.user_id,
                "Missing azp claim in JWT — subscription validation failed"
            );
            return Err(AuthError::unauthorized("Missing azp claim in JWT"));
        }
    };

    // Validate subscription
    match sub_state.validator.validate(&azp, &api_id).await {
        Ok(info) => {
            debug!(
                oauth_client_id = %azp,
                api_id = %api_id,
                subscription_id = %info.subscription_id,
                security_profile = %info.security_profile,
                "Subscription validated"
            );
            request.extensions_mut().insert(info);
        }
        Err(e) => {
            warn!(
                oauth_client_id = %azp,
                api_id = %api_id,
                error = %e,
                "Subscription validation failed"
            );
            return Err(AuthError::forbidden(&e.to_string()));
        }
    }

    Ok(next.run(request).await)
}

/// Marker type injected into request extensions by route matching
/// to identify the target API for subscription validation.
#[derive(Debug, Clone)]
pub struct TargetApiId(pub String);

// =============================================================================
// Extractor
// =============================================================================

/// Extractor for authenticated user.
///
/// Use this in handler parameters to get the authenticated user:
/// ```ignore
/// async fn handler(user: AuthUser) -> impl IntoResponse {
///     format!("Hello, {}", user.0.user_id)
/// }
/// ```
#[derive(Debug, Clone)]
pub struct AuthUser(pub AuthenticatedUser);

#[axum::async_trait]
impl<S> FromRequestParts<S> for AuthUser
where
    S: Send + Sync,
{
    type Rejection = AuthError;

    async fn from_request_parts(
        parts: &mut axum::http::request::Parts,
        _state: &S,
    ) -> Result<Self, Self::Rejection> {
        parts
            .extensions
            .get::<AuthenticatedUser>()
            .cloned()
            .map(AuthUser)
            .ok_or_else(|| AuthError::unauthorized("No authenticated user"))
    }
}

/// Optional extractor for authenticated user.
///
/// Returns None if not authenticated.
#[derive(Debug, Clone)]
pub struct OptionalAuthUser(pub Option<AuthenticatedUser>);

#[axum::async_trait]
impl<S> FromRequestParts<S> for OptionalAuthUser
where
    S: Send + Sync,
{
    type Rejection = std::convert::Infallible;

    async fn from_request_parts(
        parts: &mut axum::http::request::Parts,
        _state: &S,
    ) -> Result<Self, Self::Rejection> {
        Ok(OptionalAuthUser(
            parts.extensions.get::<AuthenticatedUser>().cloned(),
        ))
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use crate::auth::claims::{Audience, RealmAccess};

    fn sample_claims() -> Claims {
        Claims {
            sub: "user-123".to_string(),
            exp: chrono::Utc::now().timestamp() + 3600,
            iat: chrono::Utc::now().timestamp(),
            iss: "https://auth.gostoa.dev/realms/stoa".to_string(),
            aud: Audience::Single("stoa-mcp".to_string()),
            azp: Some("stoa-mcp".to_string()),
            preferred_username: Some("john.doe".to_string()),
            email: Some("john.doe@acme.com".to_string()),
            email_verified: Some(true),
            name: Some("John Doe".to_string()),
            given_name: Some("John".to_string()),
            family_name: Some("Doe".to_string()),
            tenant: Some("acme".to_string()),
            realm_access: Some(RealmAccess {
                roles: vec!["tenant-admin".to_string()],
            }),
            resource_access: None,
            sid: None,
            typ: None,
            scope: Some("openid profile email stoa:write".to_string()),
            cnf: None,
            sub_account_id: None,
            master_account_id: None,
            worker_name: None,
            worker_roles: None,
            supervision_tier: None,
        }
    }

    #[test]
    fn test_authenticated_user_from_token() {
        let claims = sample_claims();
        let token = ValidatedToken::new("token123".to_string(), claims);
        let user = AuthenticatedUser::from_token(token);

        assert_eq!(user.user_id, "user-123");
        assert_eq!(user.username, Some("john.doe".to_string()));
        assert_eq!(user.tenant_id, Some("acme".to_string()));
    }

    #[test]
    fn test_can_access_tenant_own() {
        let claims = sample_claims();
        let token = ValidatedToken::new("token".to_string(), claims);
        let user = AuthenticatedUser::from_token(token);

        assert!(user.can_access_tenant("acme"));
        assert!(!user.can_access_tenant("other"));
    }

    #[test]
    fn test_can_access_tenant_admin() {
        let mut claims = sample_claims();
        claims.realm_access = Some(RealmAccess {
            roles: vec!["cpi-admin".to_string()],
        });

        let token = ValidatedToken::new("token".to_string(), claims);
        let user = AuthenticatedUser::from_token(token);

        // Admin can access any tenant
        assert!(user.can_access_tenant("acme"));
        assert!(user.can_access_tenant("other"));
        assert!(user.can_access_tenant("any-tenant"));
    }

    #[test]
    fn test_auth_error_unauthorized() {
        let error = AuthError::unauthorized("Invalid token");
        assert_eq!(error.error, "unauthorized");
    }

    #[test]
    fn test_auth_error_forbidden() {
        let error = AuthError::forbidden("Access denied");
        assert_eq!(error.error, "forbidden");
    }

    #[test]
    fn test_target_api_id_clone() {
        let target = TargetApiId("api-weather".to_string());
        let cloned = target.clone();
        assert_eq!(cloned.0, "api-weather");
    }

    #[test]
    fn test_subscription_state_clone() {
        let validator = Arc::new(SubscriptionValidator::new(
            "http://localhost:8000".into(),
            reqwest::Client::new(),
        ));
        let state = SubscriptionState {
            validator: validator.clone(),
        };
        let cloned = state.clone();
        assert_eq!(cloned.validator.cache_size(), 0);
    }
}
