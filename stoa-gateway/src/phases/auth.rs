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
    /// Header name containing the tenant ID (set by auth middleware).
    tenant_header: String,
    /// Header name containing the user ID (optional, from JWT sub).
    user_header: String,
    /// If true, requests without a tenant ID are rejected.
    require_tenant: bool,
}

impl AuthPhase {
    pub fn new(require_tenant: bool) -> Self {
        Self {
            tenant_header: "x-stoa-tenant-id".to_string(),
            user_header: "x-stoa-user-id".to_string(),
            require_tenant,
        }
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
        // Extract tenant ID from headers (set by JWT/API-key middleware)
        if ctx.tenant_id.is_none() {
            let tenant = ctx
                .request_headers
                .get(&self.tenant_header)
                .and_then(|v| v.to_str().ok())
                .map(|s| s.to_string());
            ctx.tenant_id = tenant;
        }

        // Extract user ID from headers
        if ctx.user_id.is_none() {
            let user = ctx
                .request_headers
                .get(&self.user_header)
                .and_then(|v| v.to_str().ok())
                .map(|s| s.to_string());
            ctx.user_id = user;
        }

        if self.require_tenant && ctx.tenant_id.is_none() {
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
    async fn test_extracts_tenant_from_header() {
        let phase = AuthPhase::default();
        let mut headers = HeaderMap::new();
        headers.insert("x-stoa-tenant-id", HeaderValue::from_static("acme"));
        headers.insert("x-stoa-user-id", HeaderValue::from_static("user-42"));

        let mut ctx = make_ctx_with_headers(headers);
        let result = phase.request_filter(&mut ctx).await;

        assert!(matches!(result, PhaseResult::Continue));
        assert_eq!(ctx.tenant_id.as_deref(), Some("acme"));
        assert_eq!(ctx.user_id.as_deref(), Some("user-42"));
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
}
