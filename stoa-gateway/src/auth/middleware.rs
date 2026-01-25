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
use tracing::{debug, error, info, warn};

use super::claims::Claims;
use super::jwt::{JwtError, JwtValidator, ValidatedToken};

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
#[derive(Debug, Clone)]
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
    use crate::auth::claims::{Audience, RealmAccess, StoaRole};

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
}
