//! Security Profile Enforcement Middleware (CAB-1744)
//!
//! Enforces per-subscription security requirements based on the `security_profile`
//! field from `SubscriptionInfo`. Runs AFTER subscription validation middleware
//! (which injects `SubscriptionInfo` into request extensions).
//!
//! Profile requirements:
//! - `api_key`: API key validated upstream (pass-through here)
//! - `oauth2_public`: JWT only (default, no extra requirements)
//! - `oauth2_confidential`: JWT only (server-side client, no extra requirements)
//! - `fapi_baseline`: JWT + DPoP proof header required
//! - `fapi_advanced`: JWT + DPoP proof header + mTLS client certificate required

use axum::{
    body::Body,
    http::{Request, StatusCode},
    middleware::Next,
    response::{IntoResponse, Response},
    Json,
};
use serde::Serialize;
use tracing::{debug, instrument, warn};

use crate::auth::middleware::AuthenticatedUser;
use crate::auth::mtls::ClientCertInfo;
use crate::auth::subscription::SubscriptionInfo;
use crate::metrics;

// =============================================================================
// Error Response
// =============================================================================

#[derive(Debug, Serialize)]
pub struct ProfileEnforcementError {
    pub error: String,
    pub detail: String,
    pub security_profile: String,
}

impl ProfileEnforcementError {
    fn dpop_required(profile: &str) -> Self {
        Self {
            error: "PROFILE_DPOP_REQUIRED".to_string(),
            detail: format!(
                "Security profile '{}' requires DPoP proof (RFC 9449). Include a DPoP header.",
                profile
            ),
            security_profile: profile.to_string(),
        }
    }

    fn mtls_required(profile: &str) -> Self {
        Self {
            error: "PROFILE_MTLS_REQUIRED".to_string(),
            detail: format!(
                "Security profile '{}' requires mTLS client certificate (RFC 8705).",
                profile
            ),
            security_profile: profile.to_string(),
        }
    }
}

impl IntoResponse for ProfileEnforcementError {
    fn into_response(self) -> Response {
        (StatusCode::FORBIDDEN, Json(self)).into_response()
    }
}

// =============================================================================
// Middleware
// =============================================================================

/// Security profile enforcement middleware.
///
/// Reads `SubscriptionInfo` from request extensions (set by subscription middleware)
/// and enforces per-profile auth requirements:
/// - `fapi_baseline`: DPoP header must be present
/// - `fapi_advanced`: DPoP header + mTLS client certificate must be present
///
/// `api_key`, `oauth2_public`, and `oauth2_confidential` have no extra requirements
/// beyond what the JWT auth middleware already validates.
#[instrument(name = "auth.profile", skip_all, fields(otel.kind = "internal"))]
pub async fn profile_enforcement_middleware(
    request: Request<Body>,
    next: Next,
) -> Result<Response, ProfileEnforcementError> {
    // Only enforce if subscription info is present (set by subscription middleware)
    let sub_info = match request.extensions().get::<SubscriptionInfo>() {
        Some(info) => info.clone(),
        None => {
            // No subscription info → not a proxied route, skip
            return Ok(next.run(request).await);
        }
    };

    let profile = sub_info.security_profile.as_str();

    match profile {
        "api_key" | "oauth2_public" | "oauth2_confidential" | "" => {
            // No extra requirements beyond JWT
            debug!(
                security_profile = profile,
                api_id = %sub_info.api_id,
                "profile_enforcement: no extra requirements"
            );
            metrics::record_profile_enforcement("pass", profile);
            Ok(next.run(request).await)
        }
        "fapi_baseline" => {
            // Require DPoP proof header
            enforce_dpop(&request, profile)?;

            debug!(
                security_profile = profile,
                api_id = %sub_info.api_id,
                "profile_enforcement: fapi_baseline requirements met"
            );
            metrics::record_profile_enforcement("pass", profile);
            Ok(next.run(request).await)
        }
        "fapi_advanced" => {
            // Require DPoP proof header + mTLS client certificate
            enforce_dpop(&request, profile)?;
            enforce_mtls(&request, profile)?;

            debug!(
                security_profile = profile,
                api_id = %sub_info.api_id,
                "profile_enforcement: fapi_advanced requirements met"
            );
            metrics::record_profile_enforcement("pass", profile);
            Ok(next.run(request).await)
        }
        unknown => {
            // Unknown profile — log but allow (fail-open for forward compatibility)
            warn!(
                security_profile = unknown,
                api_id = %sub_info.api_id,
                "profile_enforcement: unknown security profile, allowing request"
            );
            metrics::record_profile_enforcement("unknown_profile", unknown);
            Ok(next.run(request).await)
        }
    }
}

/// Check that DPoP header is present.
fn enforce_dpop(request: &Request<Body>, profile: &str) -> Result<(), ProfileEnforcementError> {
    if request.headers().get("DPoP").is_none() {
        let user_id = request
            .extensions()
            .get::<AuthenticatedUser>()
            .map(|u| u.user_id.as_str())
            .unwrap_or("unknown");
        warn!(
            security_profile = profile,
            user_id = user_id,
            "profile_enforcement: DPoP proof required but missing"
        );
        metrics::record_profile_enforcement("dpop_missing", profile);
        return Err(ProfileEnforcementError::dpop_required(profile));
    }
    Ok(())
}

/// Check that mTLS client certificate info is present in extensions.
fn enforce_mtls(request: &Request<Body>, profile: &str) -> Result<(), ProfileEnforcementError> {
    if request.extensions().get::<ClientCertInfo>().is_none() {
        let user_id = request
            .extensions()
            .get::<AuthenticatedUser>()
            .map(|u| u.user_id.as_str())
            .unwrap_or("unknown");
        warn!(
            security_profile = profile,
            user_id = user_id,
            "profile_enforcement: mTLS client certificate required but missing"
        );
        metrics::record_profile_enforcement("mtls_missing", profile);
        return Err(ProfileEnforcementError::mtls_required(profile));
    }
    Ok(())
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use crate::auth::claims::{Audience, Claims, RealmAccess};
    use crate::auth::jwt::ValidatedToken;
    use crate::auth::middleware::AuthenticatedUser;
    use crate::auth::mtls::ClientCertInfo;
    use crate::auth::subscription::SubscriptionInfo;
    use axum::body::Body;
    use axum::http::Request;
    use axum::routing::get;
    use axum::Router;
    use chrono::Utc;
    use tower::ServiceExt;

    fn sample_claims() -> Claims {
        Claims {
            sub: "user-123".to_string(),
            exp: Utc::now().timestamp() + 3600,
            iat: Utc::now().timestamp(),
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
            scope: Some("openid stoa:write".to_string()),
            cnf: None,
            sub_account_id: None,
            master_account_id: None,
            worker_name: None,
            worker_roles: None,
            supervision_tier: None,
        }
    }

    fn make_user() -> AuthenticatedUser {
        let claims = sample_claims();
        let token = ValidatedToken::new("token123".to_string(), claims);
        AuthenticatedUser::from_token(token)
    }

    fn make_sub_info(profile: &str) -> SubscriptionInfo {
        SubscriptionInfo {
            valid: true,
            subscription_id: "sub-1".into(),
            tenant_id: "acme".into(),
            api_id: "api-banking".into(),
            oauth_client_id: "kc-client-123".into(),
            rate_limit: None,
            security_profile: profile.into(),
        }
    }

    fn make_cert_info() -> ClientCertInfo {
        ClientCertInfo {
            fingerprint: "abcdef0123456789".to_string(),
            subject_dn: "CN=test".to_string(),
            issuer_dn: "CN=ca".to_string(),
            serial: "01".to_string(),
            not_before: None,
            not_after: None,
        }
    }

    fn build_app() -> Router {
        Router::new()
            .route("/api/v1/data", get(|| async { "ok" }))
            .layer(axum::middleware::from_fn(profile_enforcement_middleware))
    }

    // ─── No subscription info → pass through ─────────────────────────────

    #[tokio::test]
    async fn test_no_subscription_info_passes() {
        let app = build_app();
        let request = Request::builder()
            .uri("/api/v1/data")
            .body(Body::empty())
            .unwrap();
        let response = app.oneshot(request).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

    // ─── oauth2_public → no extra requirements ───────────────────────────

    #[tokio::test]
    async fn test_oauth2_public_passes() {
        let app = build_app();
        let mut request = Request::builder()
            .uri("/api/v1/data")
            .body(Body::empty())
            .unwrap();
        request
            .extensions_mut()
            .insert(make_sub_info("oauth2_public"));
        request.extensions_mut().insert(make_user());

        let response = app.oneshot(request).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

    // ─── oauth2_confidential → no extra requirements ─────────────────────

    #[tokio::test]
    async fn test_oauth2_confidential_passes() {
        let app = build_app();
        let mut request = Request::builder()
            .uri("/api/v1/data")
            .body(Body::empty())
            .unwrap();
        request
            .extensions_mut()
            .insert(make_sub_info("oauth2_confidential"));
        request.extensions_mut().insert(make_user());

        let response = app.oneshot(request).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

    // ─── api_key → no extra requirements ─────────────────────────────────

    #[tokio::test]
    async fn test_api_key_passes() {
        let app = build_app();
        let mut request = Request::builder()
            .uri("/api/v1/data")
            .body(Body::empty())
            .unwrap();
        request.extensions_mut().insert(make_sub_info("api_key"));
        request.extensions_mut().insert(make_user());

        let response = app.oneshot(request).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

    // ─── fapi_baseline: DPoP required ────────────────────────────────────

    #[tokio::test]
    async fn test_fapi_baseline_rejects_without_dpop() {
        let app = build_app();
        let mut request = Request::builder()
            .uri("/api/v1/data")
            .body(Body::empty())
            .unwrap();
        request
            .extensions_mut()
            .insert(make_sub_info("fapi_baseline"));
        request.extensions_mut().insert(make_user());

        let response = app.oneshot(request).await.unwrap();
        assert_eq!(response.status(), StatusCode::FORBIDDEN);
    }

    #[tokio::test]
    async fn test_fapi_baseline_passes_with_dpop() {
        let app = build_app();
        let mut request = Request::builder()
            .uri("/api/v1/data")
            .header("DPoP", "eyJ...")
            .body(Body::empty())
            .unwrap();
        request
            .extensions_mut()
            .insert(make_sub_info("fapi_baseline"));
        request.extensions_mut().insert(make_user());

        let response = app.oneshot(request).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

    // ─── fapi_advanced: DPoP + mTLS required ─────────────────────────────

    #[tokio::test]
    async fn test_fapi_advanced_rejects_without_dpop() {
        let app = build_app();
        let mut request = Request::builder()
            .uri("/api/v1/data")
            .body(Body::empty())
            .unwrap();
        request
            .extensions_mut()
            .insert(make_sub_info("fapi_advanced"));
        request.extensions_mut().insert(make_user());

        let response = app.oneshot(request).await.unwrap();
        assert_eq!(response.status(), StatusCode::FORBIDDEN);
    }

    #[tokio::test]
    async fn test_fapi_advanced_rejects_dpop_only_no_mtls() {
        let app = build_app();
        let mut request = Request::builder()
            .uri("/api/v1/data")
            .header("DPoP", "eyJ...")
            .body(Body::empty())
            .unwrap();
        request
            .extensions_mut()
            .insert(make_sub_info("fapi_advanced"));
        request.extensions_mut().insert(make_user());
        // DPoP present but no ClientCertInfo

        let response = app.oneshot(request).await.unwrap();
        assert_eq!(response.status(), StatusCode::FORBIDDEN);
    }

    #[tokio::test]
    async fn test_fapi_advanced_passes_with_dpop_and_mtls() {
        let app = build_app();
        let mut request = Request::builder()
            .uri("/api/v1/data")
            .header("DPoP", "eyJ...")
            .body(Body::empty())
            .unwrap();
        request
            .extensions_mut()
            .insert(make_sub_info("fapi_advanced"));
        request.extensions_mut().insert(make_user());
        request.extensions_mut().insert(make_cert_info());

        let response = app.oneshot(request).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

    // ─── Unknown profile → fail-open ─────────────────────────────────────

    #[tokio::test]
    async fn test_unknown_profile_passes() {
        let app = build_app();
        let mut request = Request::builder()
            .uri("/api/v1/data")
            .body(Body::empty())
            .unwrap();
        request
            .extensions_mut()
            .insert(make_sub_info("future_profile_v3"));
        request.extensions_mut().insert(make_user());

        let response = app.oneshot(request).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

    // ─── Empty profile → treated as oauth2_public ────────────────────────

    #[tokio::test]
    async fn test_empty_profile_passes() {
        let app = build_app();
        let mut request = Request::builder()
            .uri("/api/v1/data")
            .body(Body::empty())
            .unwrap();
        request.extensions_mut().insert(make_sub_info(""));
        request.extensions_mut().insert(make_user());

        let response = app.oneshot(request).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

    // ─── Error response format ───────────────────────────────────────────

    #[test]
    fn test_dpop_required_error_fields() {
        let err = ProfileEnforcementError::dpop_required("fapi_baseline");
        assert_eq!(err.error, "PROFILE_DPOP_REQUIRED");
        assert_eq!(err.security_profile, "fapi_baseline");
        assert!(err.detail.contains("DPoP"));
    }

    #[test]
    fn test_mtls_required_error_fields() {
        let err = ProfileEnforcementError::mtls_required("fapi_advanced");
        assert_eq!(err.error, "PROFILE_MTLS_REQUIRED");
        assert_eq!(err.security_profile, "fapi_advanced");
        assert!(err.detail.contains("mTLS"));
    }
}
