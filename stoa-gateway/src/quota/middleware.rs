//! Quota Enforcement Middleware (Phase 4: CAB-1121)
//!
//! Axum middleware that runs AFTER auth but BEFORE handlers.
//! Checks both rate limits and daily/monthly quotas per consumer.
//!
//! Consumer identification:
//! - From `AuthenticatedUser` request extension (JWT auth) — uses `user_id`
//! - Fallback to API key consumer if no JWT
//! - Skipped entirely if quota enforcement is disabled

use axum::{
    body::Body,
    extract::State,
    http::{Request, StatusCode},
    middleware::Next,
    response::{IntoResponse, Response},
    Json,
};
use serde::Serialize;
use tracing::{debug, warn};

use crate::auth::middleware::AuthenticatedUser;
use crate::state::AppState;

use super::QuotaError;

/// Quota exceeded error response body.
#[derive(Debug, Serialize)]
struct QuotaExceededResponse {
    error: String,
    message: String,
    retry_after_secs: Option<u64>,
}

/// Quota enforcement middleware.
///
/// Runs after auth middleware. Extracts consumer_id from request extensions
/// and checks rate limits + daily/monthly quotas.
///
/// On success, adds rate limit headers to the response.
/// On failure, returns 429 Too Many Requests.
pub async fn quota_middleware(
    State(state): State<AppState>,
    request: Request<Body>,
    next: Next,
) -> Response {
    // Skip if quota enforcement is disabled
    if !state.config.quota_enforcement_enabled {
        return next.run(request).await;
    }

    // Extract consumer_id from auth context
    let consumer_id = extract_consumer_id(&request);

    let consumer_id = match consumer_id {
        Some(id) => id,
        None => {
            // No consumer identified — skip quota enforcement
            // (anonymous requests are handled by the existing tenant rate limiter)
            debug!("No consumer_id found, skipping quota enforcement");
            return next.run(request).await;
        }
    };

    // 1. Check rate limit (per-second / per-minute)
    let rate_limit_info = match state.consumer_rate_limiter.check_rate_limit(&consumer_id) {
        Ok(info) => info,
        Err(quota_error) => {
            warn!(
                consumer_id = %consumer_id,
                error = %quota_error,
                "Rate limit exceeded"
            );
            return quota_error_response(&quota_error);
        }
    };

    // 2. Check daily/monthly quota
    if let Err(quota_error) = state.quota_manager.check_quota(&consumer_id) {
        warn!(
            consumer_id = %consumer_id,
            error = %quota_error,
            "Quota exceeded"
        );
        return quota_error_response(&quota_error);
    }

    // 3. Execute the handler
    let mut response = next.run(request).await;

    // 4. Record the request (only on success path)
    state.quota_manager.record_request(&consumer_id);

    // 5. Add rate limit headers to response
    if rate_limit_info.limit > 0 {
        let headers = response.headers_mut();
        if let Ok(val) = rate_limit_info.limit.to_string().parse() {
            headers.insert("X-RateLimit-Limit", val);
        }
        if let Ok(val) = rate_limit_info.remaining.to_string().parse() {
            headers.insert("X-RateLimit-Remaining", val);
        }
        if let Ok(val) = rate_limit_info.reset_epoch.to_string().parse() {
            headers.insert("X-RateLimit-Reset", val);
        }
    }

    response
}

/// Extract consumer_id from request extensions.
///
/// Priority:
/// 1. AuthenticatedUser.user_id (from JWT)
/// 2. None (anonymous — skip quota)
fn extract_consumer_id(request: &Request<Body>) -> Option<String> {
    // Try JWT auth user
    if let Some(user) = request.extensions().get::<AuthenticatedUser>() {
        return Some(user.user_id.clone());
    }

    None
}

/// Build a 429 response from a QuotaError.
fn quota_error_response(error: &QuotaError) -> Response {
    let (retry_after, message) = match error {
        QuotaError::RateLimit {
            retry_after_secs,
            limit_type,
            limit,
        } => (
            Some(*retry_after_secs),
            format!(
                "Rate limit exceeded: {} limit of {} requests reached",
                limit_type, limit
            ),
        ),
        QuotaError::DailyQuota { used, limit } => (
            None,
            format!(
                "Daily quota exceeded: {}/{} requests used. Resets at midnight UTC.",
                used, limit
            ),
        ),
        QuotaError::MonthlyQuota { used, limit } => (
            None,
            format!(
                "Monthly quota exceeded: {}/{} requests used. Resets at month start.",
                used, limit
            ),
        ),
    };

    let body = QuotaExceededResponse {
        error: "quota_exceeded".to_string(),
        message,
        retry_after_secs: retry_after,
    };

    let mut response = (StatusCode::TOO_MANY_REQUESTS, Json(body)).into_response();

    // Add Retry-After header if applicable
    if let Some(secs) = retry_after {
        if let Ok(val) = secs.to_string().parse() {
            response.headers_mut().insert("Retry-After", val);
        }
    }

    response
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::Config;
    use crate::quota::rate_limiter::PlanQuota;
    use axum::{
        body::Body,
        http::{Request, StatusCode},
        middleware,
        routing::get,
        Router,
    };
    use tower::ServiceExt;

    async fn echo_handler() -> &'static str {
        "OK"
    }

    fn create_test_state(enabled: bool) -> AppState {
        let config = Config {
            quota_enforcement_enabled: enabled,
            quota_default_rate_per_minute: 5,
            quota_default_daily_limit: 100,
            ..Config::default()
        };
        AppState::new(config)
    }

    fn build_test_router(state: AppState) -> Router {
        Router::new()
            .route("/test", get(echo_handler))
            .layer(middleware::from_fn_with_state(
                state.clone(),
                quota_middleware,
            ))
            .with_state(state)
    }

    #[tokio::test]
    async fn test_quota_disabled_passes_through() {
        let state = create_test_state(false);
        let app = build_test_router(state);

        let response = app
            .oneshot(Request::builder().uri("/test").body(Body::empty()).unwrap())
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_no_consumer_passes_through() {
        let state = create_test_state(true);
        let app = build_test_router(state);

        // No auth headers = no consumer_id = skip quota
        let response = app
            .oneshot(Request::builder().uri("/test").body(Body::empty()).unwrap())
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_rate_limit_headers_present() {
        let state = create_test_state(true);

        // Set a quota for consumer
        state.consumer_rate_limiter.set_plan_quota(
            "user-123",
            PlanQuota {
                rate_limit_per_minute: 10,
                rate_limit_per_second: 0,
                ..Default::default()
            },
        );
        state.quota_manager.set_plan_quota(
            "user-123",
            PlanQuota {
                daily_request_limit: 1000,
                ..Default::default()
            },
        );

        let app = build_test_router(state);

        // Build request with AuthenticatedUser in extensions
        let mut request = Request::builder().uri("/test").body(Body::empty()).unwrap();
        request.extensions_mut().insert(AuthenticatedUser {
            user_id: "user-123".to_string(),
            username: Some("test".to_string()),
            email: None,
            tenant_id: Some("acme".to_string()),
            claims: test_claims(),
            raw_token: "token".to_string(),
        });

        let response = app.oneshot(request).await.unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        assert!(response.headers().contains_key("X-RateLimit-Limit"));
        assert!(response.headers().contains_key("X-RateLimit-Remaining"));
        assert!(response.headers().contains_key("X-RateLimit-Reset"));
    }

    #[tokio::test]
    async fn test_rate_limit_exceeded_returns_429() {
        let state = create_test_state(true);

        // Set a very low quota
        state.consumer_rate_limiter.set_plan_quota(
            "user-123",
            PlanQuota {
                rate_limit_per_minute: 2,
                rate_limit_per_second: 0,
                daily_request_limit: 0,
                monthly_request_limit: 0,
                ..Default::default()
            },
        );
        state.quota_manager.set_plan_quota(
            "user-123",
            PlanQuota {
                daily_request_limit: 0,
                monthly_request_limit: 0,
                ..Default::default()
            },
        );

        let app = build_test_router(state);

        // First 2 requests should succeed
        for _ in 0..2 {
            let mut request = Request::builder().uri("/test").body(Body::empty()).unwrap();
            request.extensions_mut().insert(test_auth_user());
            let response = app.clone().oneshot(request).await.unwrap();
            assert_eq!(response.status(), StatusCode::OK);
        }

        // 3rd request should be rate limited
        let mut request = Request::builder().uri("/test").body(Body::empty()).unwrap();
        request.extensions_mut().insert(test_auth_user());
        let response = app.oneshot(request).await.unwrap();
        assert_eq!(response.status(), StatusCode::TOO_MANY_REQUESTS);
        assert!(response.headers().contains_key("Retry-After"));
    }

    fn test_claims() -> crate::auth::claims::Claims {
        use crate::auth::claims::{Audience, Claims, RealmAccess};
        Claims {
            sub: "user-123".to_string(),
            exp: chrono::Utc::now().timestamp() + 3600,
            iat: chrono::Utc::now().timestamp(),
            iss: "https://auth.gostoa.dev/realms/stoa".to_string(),
            aud: Audience::Single("stoa-mcp".to_string()),
            azp: Some("stoa-mcp".to_string()),
            preferred_username: Some("test".to_string()),
            email: None,
            email_verified: None,
            name: None,
            given_name: None,
            family_name: None,
            tenant: Some("acme".to_string()),
            realm_access: Some(RealmAccess {
                roles: vec!["tenant-admin".to_string()],
            }),
            resource_access: None,
            sid: None,
            typ: None,
            scope: Some("openid stoa:read".to_string()),
            cnf: None,
        }
    }

    fn test_auth_user() -> AuthenticatedUser {
        AuthenticatedUser {
            user_id: "user-123".to_string(),
            username: Some("test".to_string()),
            email: None,
            tenant_id: Some("acme".to_string()),
            claims: test_claims(),
            raw_token: "token".to_string(),
        }
    }
}
