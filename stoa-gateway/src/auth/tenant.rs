//! Shared identity extraction for every tenant-bound MCP transport.
use axum::http::{header::AUTHORIZATION, HeaderMap};

use super::{
    claims::Claims,
    jwt::{JwtError, JwtValidator},
    middleware::AuthError,
};
use crate::state::AppState;

/// Push transports must stop at token expiry even without another request.
/// Saturation handles extreme signed timestamps without arithmetic overflow.
pub fn authorization_deadline(exp: i64) -> tokio::time::Instant {
    let now = tokio::time::Instant::now();
    let remaining = exp
        .saturating_mul(1000)
        .saturating_sub(chrono::Utc::now().timestamp_millis());
    let duration = std::time::Duration::from_millis(remaining.max(0) as u64);
    now.checked_add(duration).unwrap_or(now)
}

pub fn require_tenant(claims: &Claims) -> Result<&str, AuthError> {
    claims
        .tenant_id()
        .filter(|tenant| crate::telemetry::validated_tenant(Some(tenant)).is_some())
        .ok_or_else(tenant_required)
}

pub fn tenant_required() -> AuthError {
    tracing::warn!(
        audit = true,
        action = "authorization",
        outcome = "failure",
        reason = "tenant_required",
        status = 403,
        "Request denied",
    );
    AuthError::forbidden("A tenant claim is required")
}

pub fn token_error(error: JwtError) -> AuthError {
    match error {
        JwtError::TenantRequired => tenant_required(),
        JwtError::MissingClaim(claim) if claim == "sub" => {
            AuthError::unauthorized("A subject claim is required")
        }
        _ => AuthError::unauthorized("Invalid token"),
    }
}

/// No sender proof verifier is wired into the MCP transport handlers. A bound
/// token must never silently become an ordinary bearer token on these paths.
fn require_unbound_token(claims: &Claims) -> Result<(), AuthError> {
    if claims
        .cnf
        .as_ref()
        .is_some_and(|cnf| cnf.jkt.is_some() || cnf.x5t_s256.is_some())
    {
        return Err(AuthError::unauthorized(
            "Sender-constrained tokens unsupported on this transport",
        ));
    }
    Ok(())
}

/// Federation claims are refused when federation is disabled or malformed.
/// Shared by [`request_identity`] and the A2A task owner.
pub fn check_federation_claims(state: &AppState, claims: &Claims) -> Result<(), AuthError> {
    let federation_claims = claims.sub_account_id.is_some() || claims.master_account_id.is_some();
    if federation_claims
        && (!state.config.federation_enabled
            || claims
                .sub_account_id
                .as_deref()
                .is_none_or(|id| id.is_empty() || id != id.trim())
            || claims
                .master_account_id
                .as_deref()
                .is_none_or(|id| id.is_empty() || id != id.trim()))
    {
        return Err(AuthError::forbidden(
            "Invalid or disabled federation identity",
        ));
    }
    Ok(())
}

/// Restricted subject and tenant used only in explicit local dev mode without
/// Keycloak and without a Control Plane.
pub const LOCAL_DEV_SUBJECT: &str = "local-dev";
pub const LOCAL_DEV_TENANT: &str = "local";

fn local_dev_claims() -> Claims {
    let now = chrono::Utc::now().timestamp();
    Claims {
        acr: None,
        amr: None,
        sub: LOCAL_DEV_SUBJECT.to_string(),
        exp: now + 3600,
        iat: now,
        iss: "local-dev".to_string(),
        aud: super::claims::Audience::None,
        azp: Some(LOCAL_DEV_SUBJECT.to_string()),
        preferred_username: Some(LOCAL_DEV_SUBJECT.to_string()),
        email: None,
        email_verified: None,
        name: None,
        given_name: None,
        family_name: None,
        tenant: Some(LOCAL_DEV_TENANT.to_string()),
        legacy_tenant: None,
        realm_access: None,
        resource_access: None,
        sid: None,
        typ: None,
        scope: Some("stoa:read".to_string()),
        scp: None,
        cnf: None,
        sub_account_id: None,
        master_account_id: None,
        worker_name: None,
        worker_roles: None,
        supervision_tier: None,
    }
}

/// Headers select only the Bearer token, never its tenant or user identity.
///
/// Always fails closed when no JWT validator is configured.
pub async fn request_identity(
    state: &AppState,
    headers: &HeaderMap,
) -> Result<(Claims, String), AuthError> {
    let Some(validator) = state.jwt_validator.as_ref() else {
        return Err(AuthError::unauthorized("JWT validation unavailable"));
    };
    let header = headers
        .get(AUTHORIZATION)
        .and_then(|h| h.to_str().ok())
        .ok_or_else(|| AuthError::unauthorized("Authentication required"))?;
    let token = JwtValidator::extract_token(header).map_err(token_error)?;
    let claims = validator
        .validate_mcp(
            token,
            state.config.mcp_audience.as_deref().unwrap_or_default(),
        )
        .await
        .map_err(token_error)?;
    if claims.sub.trim().is_empty() {
        return Err(AuthError::unauthorized("A subject claim is required"));
    }
    require_tenant(&claims)?;
    require_unbound_token(&claims)?;
    check_federation_claims(state, &claims)?;
    Ok((claims, token.to_string()))
}

/// MCP-only identity extraction.
///
/// Synthesizes the restricted local-dev identity (`local-dev`, tenant `local`,
/// scope `stoa:read`, no roles, empty token) only when no JWT validator is
/// configured, `allows_explicit_local_dev_access()` is true, and no
/// `Authorization` header was presented. A Bearer token without a validator
/// still fails closed via [`request_identity`].
pub async fn request_mcp_identity(
    state: &AppState,
    headers: &HeaderMap,
) -> Result<(Claims, String), AuthError> {
    if state.jwt_validator.is_none()
        && state.config.allows_explicit_local_dev_access()
        && !headers.contains_key(AUTHORIZATION)
    {
        return Ok((local_dev_claims(), String::new()));
    }
    request_identity(state, headers).await
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::Config;
    use axum::{
        http::{HeaderValue, StatusCode},
        response::IntoResponse,
    };

    #[tokio::test]
    async fn regression_no_validator_cannot_accept_a_bearer_or_tenant_header() {
        let state = AppState::new(Config::default());
        let mut headers = HeaderMap::new();
        headers.insert(AUTHORIZATION, HeaderValue::from_static("Bearer invalid"));
        headers.insert("X-Tenant-ID", HeaderValue::from_static("other"));
        let error = request_identity(&state, &headers).await.unwrap_err();
        assert_eq!(error.into_response().status(), StatusCode::UNAUTHORIZED);
        assert_eq!(state.session_manager.count(), 0);
    }

    #[test]
    fn regression_error_status_preserves_tenant_denial() {
        assert_eq!(
            token_error(JwtError::TenantRequired)
                .into_response()
                .status(),
            StatusCode::FORBIDDEN
        );
        assert_eq!(
            token_error(JwtError::InvalidSignature)
                .into_response()
                .status(),
            StatusCode::UNAUTHORIZED
        );
        assert!(!Config::default().allow_legacy_tenant_claim);
        assert!(!super::super::jwt::JwtValidatorConfig::default().allow_legacy_tenant_claim);
    }
    #[tokio::test]
    async fn regression_push_deadline_is_bounded_by_token_expiration() {
        let now = tokio::time::Instant::now();
        let expired = authorization_deadline(chrono::Utc::now().timestamp() - 1);
        assert!(expired <= tokio::time::Instant::now());
        let future = authorization_deadline(chrono::Utc::now().timestamp() + 60);
        assert!(future > now);
        assert!(future.duration_since(now) <= std::time::Duration::from_secs(60));
    }

    #[tokio::test]
    async fn request_identity_stays_fail_closed_in_explicit_local_dev() {
        let state = AppState::new(Config {
            environment: crate::config::Environment::Dev,
            environment_explicit: true,
            ..Config::default()
        });
        assert!(state.config.allows_explicit_local_dev_access());
        assert!(state.jwt_validator.is_none());

        let anonymous = request_identity(&state, &HeaderMap::new())
            .await
            .unwrap_err();
        assert_eq!(anonymous.into_response().status(), StatusCode::UNAUTHORIZED);

        let mut bearer_headers = HeaderMap::new();
        bearer_headers.insert(AUTHORIZATION, HeaderValue::from_static("Bearer fake-token"));
        let bearer = request_identity(&state, &bearer_headers).await.unwrap_err();
        assert_eq!(bearer.into_response().status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn request_mcp_identity_explicit_local_dev_returns_restricted_identity() {
        let state = AppState::new(Config {
            environment: crate::config::Environment::Dev,
            environment_explicit: true,
            ..Config::default()
        });
        let mut headers = HeaderMap::new();
        // Client tenant headers must still be ignored.
        headers.insert("X-Tenant-ID", HeaderValue::from_static("other"));

        let (claims, token) = request_mcp_identity(&state, &headers)
            .await
            .expect("explicit local dev without Authorization should succeed");
        assert_eq!(claims.sub, LOCAL_DEV_SUBJECT);
        assert_eq!(require_tenant(&claims).unwrap(), LOCAL_DEV_TENANT);
        assert!(crate::telemetry::validated_tenant(claims.tenant_id()).is_some());
        assert!(claims.realm_roles().is_empty());
        assert_eq!(claims.scopes(), vec!["stoa:read"]);
        assert!(token.is_empty());
    }

    #[tokio::test]
    async fn request_mcp_identity_explicit_local_dev_rejects_bearer_without_validator() {
        let state = AppState::new(Config {
            environment: crate::config::Environment::Dev,
            environment_explicit: true,
            ..Config::default()
        });
        let mut headers = HeaderMap::new();
        headers.insert(AUTHORIZATION, HeaderValue::from_static("Bearer fake-token"));

        let error = request_mcp_identity(&state, &headers).await.unwrap_err();
        assert_eq!(error.into_response().status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn request_mcp_identity_rejects_implicit_dev_and_configured_dependencies() {
        // Implicit default Dev (environment_explicit = false) stays locked.
        let implicit_dev = AppState::new(Config::default());
        let error = request_mcp_identity(&implicit_dev, &HeaderMap::new())
            .await
            .unwrap_err();
        assert_eq!(error.into_response().status(), StatusCode::UNAUTHORIZED);

        // Explicit dev with Control Plane URL stays locked.
        let dev_with_cp = AppState::new(Config {
            environment: crate::config::Environment::Dev,
            environment_explicit: true,
            control_plane_url: Some("http://127.0.0.1:1".to_string()),
            ..Config::default()
        });
        let error = request_mcp_identity(&dev_with_cp, &HeaderMap::new())
            .await
            .unwrap_err();
        assert_eq!(error.into_response().status(), StatusCode::UNAUTHORIZED);

        // Explicit dev with Keycloak URL stays locked (validator present, no token).
        let dev_with_keycloak = AppState::new(Config {
            environment: crate::config::Environment::Dev,
            environment_explicit: true,
            keycloak_url: Some("http://127.0.0.1:1".to_string()),
            ..Config::default()
        });
        let error = request_mcp_identity(&dev_with_keycloak, &HeaderMap::new())
            .await
            .unwrap_err();
        assert_eq!(error.into_response().status(), StatusCode::UNAUTHORIZED);
    }
}
