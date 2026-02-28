//! Sender-Constraint Middleware (CAB-1607)
//!
//! Unified pipeline for mTLS (RFC 8705) and DPoP (RFC 9449) sender-constrained tokens.
//!
//! Checks the JWT `cnf` claim against:
//! - `cnf.x5t#S256`: mTLS client certificate thumbprint
//! - `cnf.jkt`: DPoP proof JWK thumbprint
//!
//! Per-tenant configuration controls which binding methods are enforced.
//! Bypass paths (OAuth, discovery, health, MCP transport) skip this middleware.

use axum::{
    body::Body,
    http::{Request, StatusCode},
    middleware::Next,
    response::{IntoResponse, Response},
    Json,
};
use base64::Engine;
use serde::Serialize;
use subtle::ConstantTimeEq;
use tracing::{debug, warn};

use crate::auth::claims::CnfClaim;
use crate::auth::middleware::AuthenticatedUser;
use crate::auth::mtls::ClientCertInfo;
use crate::config::SenderConstraintConfig;
use crate::metrics;

// =============================================================================
// Bypass Paths
// =============================================================================

/// Paths that bypass sender-constraint checks.
/// Consistent with mTLS bypass paths (see auth::mtls::is_mtls_bypass_path).
fn is_bypass_path(path: &str) -> bool {
    const BYPASS_PREFIXES: &[&str] = &[
        "/.well-known/",
        "/oauth/",
        "/mcp/sse",
        "/mcp/ws",
        "/mcp/tools/",
        "/mcp/v1/",
        "/health",
        "/ready",
        "/metrics",
        "/admin/",
    ];
    const BYPASS_EXACT: &[&str] = &["/mcp", "/mcp/capabilities", "/mcp/health"];

    BYPASS_PREFIXES.iter().any(|p| path.starts_with(p)) || BYPASS_EXACT.contains(&path)
}

// =============================================================================
// Error Response
// =============================================================================

#[derive(Debug, Serialize)]
pub struct SenderConstraintError {
    pub error: String,
    pub detail: String,
}

impl SenderConstraintError {
    fn dpop_required() -> Self {
        Self {
            error: "SENDER_CONSTRAINT_DPOP_REQUIRED".to_string(),
            detail: "DPoP proof required for this token".to_string(),
        }
    }

    fn dpop_missing_proof() -> Self {
        Self {
            error: "SENDER_CONSTRAINT_DPOP_MISSING".to_string(),
            detail: "token has cnf.jkt but no DPoP proof was provided".to_string(),
        }
    }

    fn mtls_required() -> Self {
        Self {
            error: "SENDER_CONSTRAINT_MTLS_REQUIRED".to_string(),
            detail: "mTLS client certificate required for this token".to_string(),
        }
    }

    fn mtls_missing_cert() -> Self {
        Self {
            error: "SENDER_CONSTRAINT_MTLS_MISSING".to_string(),
            detail: "token has cnf.x5t#S256 but no client certificate was presented".to_string(),
        }
    }

    fn mtls_binding_mismatch() -> Self {
        Self {
            error: "SENDER_CONSTRAINT_MTLS_MISMATCH".to_string(),
            detail: "client certificate thumbprint does not match token binding".to_string(),
        }
    }
}

impl IntoResponse for SenderConstraintError {
    fn into_response(self) -> Response {
        let status = match self.error.as_str() {
            "SENDER_CONSTRAINT_DPOP_REQUIRED"
            | "SENDER_CONSTRAINT_MTLS_REQUIRED"
            | "SENDER_CONSTRAINT_DPOP_MISSING"
            | "SENDER_CONSTRAINT_MTLS_MISSING" => StatusCode::UNAUTHORIZED,
            _ => StatusCode::FORBIDDEN,
        };
        (status, Json(self)).into_response()
    }
}

// =============================================================================
// Middleware
// =============================================================================

/// Unified sender-constraint middleware.
///
/// Runs after JWT auth — requires `AuthenticatedUser` in request extensions.
/// Checks DPoP and mTLS bindings based on the token's `cnf` claim and config.
pub async fn sender_constraint_middleware(
    config: SenderConstraintConfig,
    request: Request<Body>,
    next: Next,
) -> Result<Response, SenderConstraintError> {
    if !config.enabled {
        return Ok(next.run(request).await);
    }

    let path = request.uri().path().to_string();
    if is_bypass_path(&path) {
        return Ok(next.run(request).await);
    }

    // Extract authenticated user (set by JWT middleware)
    let user = request.extensions().get::<AuthenticatedUser>().cloned();
    let Some(user) = user else {
        // No authenticated user → anonymous request, skip constraint check
        debug!("sender_constraint: no authenticated user, skipping");
        return Ok(next.run(request).await);
    };

    let tenant = user.tenant_id.as_deref().unwrap_or("unknown");
    let cnf = user.claims.cnf.as_ref();

    // Check DPoP binding
    if let Some(err) = check_dpop_binding(cnf, &config, &request, tenant) {
        return Err(err);
    }

    // Check mTLS binding
    if let Some(err) = check_mtls_binding(cnf, &config, &request, tenant) {
        return Err(err);
    }

    // All checks passed
    if cnf.is_some() {
        debug!(tenant = tenant, "sender_constraint: all bindings verified");
        metrics::record_sender_constraint_check("pass", "combined", tenant);
    }

    Ok(next.run(request).await)
}

/// Check DPoP binding: cnf.jkt present → DPoP header must be present.
///
/// Note: Full DPoP proof validation (signature, htm, htu, jti) is handled by
/// the dedicated DPoP middleware. This check only verifies the binding exists.
fn check_dpop_binding(
    cnf: Option<&CnfClaim>,
    config: &SenderConstraintConfig,
    request: &Request<Body>,
    tenant: &str,
) -> Option<SenderConstraintError> {
    let has_jkt = cnf.and_then(|c| c.jkt.as_ref()).is_some();

    if config.dpop_required && !has_jkt {
        warn!(
            tenant = tenant,
            "sender_constraint: DPoP required but token has no cnf.jkt"
        );
        metrics::record_sender_constraint_check("dpop_required_no_jkt", "dpop", tenant);
        return Some(SenderConstraintError::dpop_required());
    }

    if has_jkt {
        // Token claims DPoP binding — verify DPoP header is present
        let dpop_header = request.headers().get("DPoP");
        if dpop_header.is_none() {
            warn!(
                tenant = tenant,
                "sender_constraint: token has cnf.jkt but no DPoP header"
            );
            metrics::record_sender_constraint_check("dpop_missing_proof", "dpop", tenant);
            return Some(SenderConstraintError::dpop_missing_proof());
        }

        debug!(
            tenant = tenant,
            "sender_constraint: DPoP header present for cnf.jkt token"
        );
        metrics::record_sender_constraint_check("pass", "dpop", tenant);
    }

    None
}

/// Check mTLS binding: cnf.x5t#S256 present → client cert must match.
fn check_mtls_binding(
    cnf: Option<&CnfClaim>,
    config: &SenderConstraintConfig,
    request: &Request<Body>,
    tenant: &str,
) -> Option<SenderConstraintError> {
    let expected_thumbprint = cnf.and_then(|c| c.x5t_s256.as_ref());

    if config.mtls_required && expected_thumbprint.is_none() {
        warn!(
            tenant = tenant,
            "sender_constraint: mTLS required but token has no cnf.x5t#S256"
        );
        metrics::record_sender_constraint_check("mtls_required_no_cnf", "mtls", tenant);
        return Some(SenderConstraintError::mtls_required());
    }

    if let Some(expected) = expected_thumbprint {
        // Token claims mTLS binding — verify certificate is present and matches
        let cert_info = request.extensions().get::<ClientCertInfo>();
        let Some(cert) = cert_info else {
            warn!(
                tenant = tenant,
                "sender_constraint: token has cnf.x5t#S256 but no client certificate"
            );
            metrics::record_sender_constraint_check("mtls_missing_cert", "mtls", tenant);
            return Some(SenderConstraintError::mtls_missing_cert());
        };

        // Convert hex fingerprint to base64url for comparison with cnf.x5t#S256
        let cert_thumbprint_b64 = hex_to_base64url(&cert.fingerprint);
        let matches = constant_time_eq(expected.as_bytes(), cert_thumbprint_b64.as_bytes());
        if !matches {
            warn!(
                tenant = tenant,
                "sender_constraint: mTLS certificate thumbprint does not match cnf.x5t#S256"
            );
            metrics::record_sender_constraint_check("mtls_mismatch", "mtls", tenant);
            return Some(SenderConstraintError::mtls_binding_mismatch());
        }

        debug!(tenant = tenant, "sender_constraint: mTLS binding verified");
        metrics::record_sender_constraint_check("pass", "mtls", tenant);
    }

    None
}

/// Convert a hex-encoded SHA-256 fingerprint to base64url (no padding).
/// cnf.x5t#S256 uses base64url encoding per RFC 8705.
fn hex_to_base64url(hex: &str) -> String {
    let bytes: Vec<u8> = (0..hex.len())
        .step_by(2)
        .filter_map(|i| u8::from_str_radix(&hex[i..i + 2], 16).ok())
        .collect();
    base64::engine::general_purpose::URL_SAFE_NO_PAD.encode(&bytes)
}

/// Timing-safe comparison using subtle::ConstantTimeEq.
fn constant_time_eq(a: &[u8], b: &[u8]) -> bool {
    if a.len() != b.len() {
        return false;
    }
    a.ct_eq(b).into()
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use crate::auth::claims::{Audience, Claims, CnfClaim, RealmAccess};
    use crate::auth::jwt::ValidatedToken;
    use crate::auth::middleware::AuthenticatedUser;
    use crate::auth::mtls::ClientCertInfo;
    use axum::body::Body;
    use axum::http::Request;
    use chrono::Utc;

    fn sample_claims(cnf: Option<CnfClaim>) -> Claims {
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
            cnf,
            sub_account_id: None,
            master_account_id: None,
        }
    }

    fn make_user(cnf: Option<CnfClaim>) -> AuthenticatedUser {
        let claims = sample_claims(cnf);
        let token = ValidatedToken::new("token123".to_string(), claims);
        AuthenticatedUser::from_token(token)
    }

    fn enabled_config(dpop_required: bool, mtls_required: bool) -> SenderConstraintConfig {
        SenderConstraintConfig {
            enabled: true,
            dpop_required,
            mtls_required,
        }
    }

    fn make_cert_info(fingerprint: &str) -> ClientCertInfo {
        ClientCertInfo {
            fingerprint: fingerprint.to_string(),
            subject_dn: "CN=test".to_string(),
            issuer_dn: "CN=ca".to_string(),
            serial: "01".to_string(),
            not_before: None,
            not_after: None,
        }
    }

    #[test]
    fn test_bypass_paths() {
        assert!(is_bypass_path("/.well-known/oauth-protected-resource"));
        assert!(is_bypass_path("/oauth/token"));
        assert!(is_bypass_path("/health"));
        assert!(is_bypass_path("/ready"));
        assert!(is_bypass_path("/metrics"));
        assert!(is_bypass_path("/mcp/sse"));
        assert!(is_bypass_path("/mcp/tools/list"));
        assert!(is_bypass_path("/admin/apis"));
        assert!(is_bypass_path("/mcp"));
        assert!(is_bypass_path("/mcp/capabilities"));

        assert!(!is_bypass_path("/api/v1/payments"));
        assert!(!is_bypass_path("/proxy/backend"));
        assert!(!is_bypass_path("/"));
    }

    #[test]
    fn test_hex_to_base64url() {
        // SHA-256 of "test" = 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08
        let hex = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08";
        let b64 = hex_to_base64url(hex);
        assert_eq!(b64, "n4bQgYhMfWWaL-qgxVrQFaO_TxsrC4Is0V1sFbDwCgg");
    }

    #[test]
    fn test_constant_time_eq_same() {
        assert!(constant_time_eq(b"hello", b"hello"));
    }

    #[test]
    fn test_constant_time_eq_different() {
        assert!(!constant_time_eq(b"hello", b"world"));
    }

    #[test]
    fn test_constant_time_eq_different_length() {
        assert!(!constant_time_eq(b"hi", b"hello"));
    }

    #[test]
    fn test_check_dpop_no_cnf_not_required() {
        let config = enabled_config(false, false);
        let request = Request::builder()
            .uri("/api/v1/data")
            .body(Body::empty())
            .unwrap();
        let result = check_dpop_binding(None, &config, &request, "acme");
        assert!(result.is_none());
    }

    #[test]
    fn test_check_dpop_required_no_jkt() {
        let config = enabled_config(true, false);
        let request = Request::builder()
            .uri("/api/v1/data")
            .body(Body::empty())
            .unwrap();
        let result = check_dpop_binding(None, &config, &request, "acme");
        assert!(result.is_some());
        assert_eq!(result.unwrap().error, "SENDER_CONSTRAINT_DPOP_REQUIRED");
    }

    #[test]
    fn test_check_dpop_jkt_present_no_header() {
        let config = enabled_config(false, false);
        let cnf = CnfClaim {
            x5t_s256: None,
            jkt: Some("thumbprint123".to_string()),
        };
        let request = Request::builder()
            .uri("/api/v1/data")
            .body(Body::empty())
            .unwrap();
        let result = check_dpop_binding(Some(&cnf), &config, &request, "acme");
        assert!(result.is_some());
        assert_eq!(result.unwrap().error, "SENDER_CONSTRAINT_DPOP_MISSING");
    }

    #[test]
    fn test_check_dpop_jkt_present_with_header() {
        let config = enabled_config(false, false);
        let cnf = CnfClaim {
            x5t_s256: None,
            jkt: Some("thumbprint123".to_string()),
        };
        let request = Request::builder()
            .uri("/api/v1/data")
            .header("DPoP", "eyJ...")
            .body(Body::empty())
            .unwrap();
        let result = check_dpop_binding(Some(&cnf), &config, &request, "acme");
        assert!(result.is_none());
    }

    #[test]
    fn test_check_mtls_no_cnf_not_required() {
        let config = enabled_config(false, false);
        let request = Request::builder()
            .uri("/api/v1/data")
            .body(Body::empty())
            .unwrap();
        let result = check_mtls_binding(None, &config, &request, "acme");
        assert!(result.is_none());
    }

    #[test]
    fn test_check_mtls_required_no_x5t() {
        let config = enabled_config(false, true);
        let request = Request::builder()
            .uri("/api/v1/data")
            .body(Body::empty())
            .unwrap();
        let result = check_mtls_binding(None, &config, &request, "acme");
        assert!(result.is_some());
        assert_eq!(result.unwrap().error, "SENDER_CONSTRAINT_MTLS_REQUIRED");
    }

    #[test]
    fn test_check_mtls_x5t_present_no_cert() {
        let config = enabled_config(false, false);
        let cnf = CnfClaim {
            x5t_s256: Some("n4bQgYhMfWWaL-qgxVrQFaO_TxsrC4Is0V1sFbDwCgg".to_string()),
            jkt: None,
        };
        let request = Request::builder()
            .uri("/api/v1/data")
            .body(Body::empty())
            .unwrap();
        let result = check_mtls_binding(Some(&cnf), &config, &request, "acme");
        assert!(result.is_some());
        assert_eq!(result.unwrap().error, "SENDER_CONSTRAINT_MTLS_MISSING");
    }

    #[test]
    fn test_check_mtls_x5t_matching_cert() {
        let config = enabled_config(false, false);
        // Hex fingerprint that maps to the base64url value
        let hex_fp = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08";
        let b64_fp = hex_to_base64url(hex_fp);

        let cnf = CnfClaim {
            x5t_s256: Some(b64_fp),
            jkt: None,
        };

        let cert = make_cert_info(hex_fp);
        let mut request = Request::builder()
            .uri("/api/v1/data")
            .body(Body::empty())
            .unwrap();
        request.extensions_mut().insert(cert);

        let result = check_mtls_binding(Some(&cnf), &config, &request, "acme");
        assert!(result.is_none());
    }

    #[test]
    fn test_check_mtls_x5t_mismatching_cert() {
        let config = enabled_config(false, false);
        let cnf = CnfClaim {
            x5t_s256: Some("n4bQgYhMfWWaL-qgxVrQFaO_TxsrC4Is0V1sFbDwCgg".to_string()),
            jkt: None,
        };

        let cert =
            make_cert_info("0000000000000000000000000000000000000000000000000000000000000000");
        let mut request = Request::builder()
            .uri("/api/v1/data")
            .body(Body::empty())
            .unwrap();
        request.extensions_mut().insert(cert);

        let result = check_mtls_binding(Some(&cnf), &config, &request, "acme");
        assert!(result.is_some());
        assert_eq!(result.unwrap().error, "SENDER_CONSTRAINT_MTLS_MISMATCH");
    }

    // -------------------------------------------------------------------------
    // Middleware integration tests using Router + tower::ServiceExt
    // -------------------------------------------------------------------------

    use axum::routing::get;
    use axum::Router;
    use tower::ServiceExt;

    fn build_app(config: SenderConstraintConfig) -> Router {
        Router::new()
            .route("/api/v1/data", get(|| async { "ok" }))
            .route("/health", get(|| async { "ok" }))
            .layer(axum::middleware::from_fn(move |req, next| {
                let c = config.clone();
                sender_constraint_middleware(c, req, next)
            }))
    }

    #[tokio::test]
    async fn test_middleware_disabled_passes_through() {
        let app = build_app(SenderConstraintConfig::default());
        let request = Request::builder()
            .uri("/api/v1/data")
            .body(Body::empty())
            .unwrap();
        let response = app.oneshot(request).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_middleware_bypass_path() {
        let app = build_app(enabled_config(true, true));
        let request = Request::builder()
            .uri("/health")
            .body(Body::empty())
            .unwrap();
        let response = app.oneshot(request).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_middleware_no_user_passes() {
        let app = build_app(enabled_config(true, true));
        let request = Request::builder()
            .uri("/api/v1/data")
            .body(Body::empty())
            .unwrap();
        // No AuthenticatedUser in extensions → middleware passes through
        let response = app.oneshot(request).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_middleware_dpop_required_rejects() {
        let config = enabled_config(true, false);
        let user = make_user(None); // no cnf

        let app = Router::new()
            .route("/api/v1/data", get(|| async { "ok" }))
            .layer(axum::middleware::from_fn(
                move |mut req: Request<Body>, next: axum::middleware::Next| {
                    req.extensions_mut().insert(user.clone());
                    let c = config.clone();
                    sender_constraint_middleware(c, req, next)
                },
            ));

        let request = Request::builder()
            .uri("/api/v1/data")
            .body(Body::empty())
            .unwrap();
        let response = app.oneshot(request).await.unwrap();
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn test_middleware_clean_token_passes() {
        let config = enabled_config(false, false);
        let user = make_user(None); // no cnf, not required

        let app = Router::new()
            .route("/api/v1/data", get(|| async { "ok" }))
            .layer(axum::middleware::from_fn(
                move |mut req: Request<Body>, next: axum::middleware::Next| {
                    req.extensions_mut().insert(user.clone());
                    let c = config.clone();
                    sender_constraint_middleware(c, req, next)
                },
            ));

        let request = Request::builder()
            .uri("/api/v1/data")
            .body(Body::empty())
            .unwrap();
        let response = app.oneshot(request).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }
}
