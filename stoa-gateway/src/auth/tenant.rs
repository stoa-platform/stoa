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

/// Headers select only the Bearer token, never its tenant or user identity.
pub async fn request_identity(
    state: &AppState,
    headers: &HeaderMap,
) -> Result<(Claims, String), AuthError> {
    let validator = state
        .jwt_validator
        .as_ref()
        .ok_or_else(|| AuthError::unauthorized("JWT validation unavailable"))?;
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
    let tenant = require_tenant(&claims)?;
    for header in headers.get_all("X-Tenant-ID").iter() {
        if header.to_str().ok() != Some(tenant) {
            return Err(AuthError::forbidden(
                "Tenant header does not match authenticated tenant",
            ));
        }
    }
    require_unbound_token(&claims)?;
    check_federation_claims(state, &claims)?;
    Ok((claims, token.to_string()))
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
}
