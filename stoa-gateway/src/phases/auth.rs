//! Auth Phase — request_filter implementation (CAB-1834)
//!
//! Demonstrates the ProxyPhase trait by wrapping authentication logic into a
//! lifecycle phase. Validates that a tenant ID is present (extracted from JWT
//! or API key by upstream middleware) and populates context fields.

use async_trait::async_trait;
use axum::http::StatusCode;

use super::{PhaseContext, PhaseResult, ProxyPhase};

/// Authentication phase that verifies tenant identity is present.
///
/// In the full pipeline, JWT/API-key validation happens in axum middleware
/// before the phase chain runs. This phase acts as a guard, rejecting requests
/// that made it through without identity (e.g., misconfigured bypass routes).
pub struct AuthPhase {
    /// If true, requests without a tenant ID are rejected.
    require_tenant: bool,
}

impl AuthPhase {
    pub fn new(require_tenant: bool) -> Self {
        Self { require_tenant }
    }
}

impl Default for AuthPhase {
    fn default() -> Self {
        Self::new(true)
    }
}

#[async_trait]
impl ProxyPhase for AuthPhase {
    fn name(&self) -> &str {
        "auth"
    }

    async fn request_filter(&self, ctx: &mut PhaseContext) -> PhaseResult {
        // Tenant identity must be populated from verified JWT/API-key middleware.
        // Caller-controlled headers are never an identity source.

        if self.require_tenant
            && ctx
                .tenant_id
                .as_deref()
                .is_none_or(|t| t.is_empty() || t != t.trim())
        {
            return PhaseResult::Reject {
                status: StatusCode::UNAUTHORIZED,
                body: "Missing tenant identity".to_string(),
            };
        }

        PhaseResult::Continue
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::{HeaderMap, HeaderValue, Method};

    fn make_ctx_with_headers(headers: HeaderMap) -> PhaseContext {
        PhaseContext::new(Method::GET, "/api/v1/tools".to_string(), headers)
    }

    #[tokio::test]
    async fn test_rejects_tenant_header_as_identity() {
        let phase = AuthPhase::default();
        let mut headers = HeaderMap::new();
        headers.insert("x-stoa-tenant-id", HeaderValue::from_static("acme"));
        headers.insert("x-stoa-user-id", HeaderValue::from_static("user-42"));

        let mut ctx = make_ctx_with_headers(headers);
        let result = phase.request_filter(&mut ctx).await;

        assert!(matches!(result, PhaseResult::Reject { .. }));
        assert!(ctx.tenant_id.is_none());
        assert!(ctx.user_id.is_none());
    }

    #[tokio::test]
    async fn test_rejects_missing_tenant_when_required() {
        let phase = AuthPhase::new(true);
        let mut ctx = make_ctx_with_headers(HeaderMap::new());

        let result = phase.request_filter(&mut ctx).await;
        match result {
            PhaseResult::Reject { status, .. } => {
                assert_eq!(status, StatusCode::UNAUTHORIZED);
            }
            _ => panic!("expected Reject"),
        }
    }

    #[tokio::test]
    async fn test_allows_missing_tenant_when_not_required() {
        let phase = AuthPhase::new(false);
        let mut ctx = make_ctx_with_headers(HeaderMap::new());

        let result = phase.request_filter(&mut ctx).await;
        assert!(matches!(result, PhaseResult::Continue));
        assert!(ctx.tenant_id.is_none());
    }

    #[tokio::test]
    async fn test_preserves_existing_tenant() {
        let phase = AuthPhase::default();
        let mut headers = HeaderMap::new();
        headers.insert("x-stoa-tenant-id", HeaderValue::from_static("from-header"));

        let mut ctx = make_ctx_with_headers(headers);
        ctx.tenant_id = Some("already-set".to_string());

        let result = phase.request_filter(&mut ctx).await;
        assert!(matches!(result, PhaseResult::Continue));
        assert_eq!(ctx.tenant_id.as_deref(), Some("already-set"));
    }

    #[tokio::test]
    async fn regression_verified_tenant_does_not_make_user_header_trusted() {
        let mut headers = HeaderMap::new();
        headers.insert("x-stoa-user-id", HeaderValue::from_static("victim"));
        let mut ctx = make_ctx_with_headers(headers);
        ctx.tenant_id = Some("tenant-a".into());
        assert!(matches!(
            AuthPhase::default().request_filter(&mut ctx).await,
            PhaseResult::Continue
        ));
        assert!(ctx.user_id.is_none());
        ctx.user_id = Some("verified-user".into());
        AuthPhase::default().request_filter(&mut ctx).await;
        assert_eq!(ctx.user_id.as_deref(), Some("verified-user"));
    }
}
