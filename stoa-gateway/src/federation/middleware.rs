//! Federation middleware (CAB-1362)
//!
//! Axum middleware that extracts SubAccountContext from JWT claims.
//! Runs after auth, before quota. Non-federation requests pass through untouched.

use axum::{body::Body, extract::State, http::Request, middleware::Next, response::Response};
use tracing::{debug, warn};

use crate::auth::middleware::AuthenticatedUser;
use crate::state::AppState;

use super::context::SubAccountContext;

/// Federation middleware.
///
/// 1. Early return if federation is disabled
/// 2. Extract AuthenticatedUser from request extensions
/// 3. Check sub_account_id + master_account_id claims
/// 4. Fetch allowed tools from FederationCache
/// 5. Insert SubAccountContext into request extensions
pub async fn federation_middleware(
    State(state): State<AppState>,
    mut request: Request<Body>,
    next: Next,
) -> Response {
    // Skip if federation is disabled
    if !state.config.federation_enabled {
        return next.run(request).await;
    }

    // Extract auth context (must run after auth middleware)
    let (sub_account_id, master_account_id, tenant_id) = {
        let user = match request.extensions().get::<AuthenticatedUser>() {
            Some(u) => u,
            None => return next.run(request).await,
        };

        let sub_id = match &user.claims.sub_account_id {
            Some(id) => id.clone(),
            None => return next.run(request).await,
        };

        let master_id = match &user.claims.master_account_id {
            Some(id) => id.clone(),
            None => {
                warn!(
                    sub_account_id = %sub_id,
                    "sub_account_id present but master_account_id missing"
                );
                return next.run(request).await;
            }
        };

        let tenant = user
            .tenant_id
            .clone()
            .unwrap_or_else(|| "unknown".to_string());

        (sub_id, master_id, tenant)
    };

    debug!(
        sub_account_id = %sub_account_id,
        master_account_id = %master_account_id,
        tenant_id = %tenant_id,
        "Federation context detected"
    );

    // Fetch allowed tools from cache
    let allowed_tools = state
        .federation_cache
        .get_allowed_tools(&sub_account_id, &tenant_id, &master_account_id)
        .await;

    // Build and inject SubAccountContext
    let ctx = SubAccountContext {
        sub_account_id,
        master_account_id,
        tenant_id,
        allowed_tools,
    };

    request.extensions_mut().insert(ctx);

    next.run(request).await
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::auth::claims::{Audience, Claims};
    use crate::auth::middleware::AuthenticatedUser;
    use crate::config::Config;
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

    fn test_state(enabled: bool) -> AppState {
        let config = Config {
            federation_enabled: enabled,
            ..Config::default()
        };
        AppState::new(config)
    }

    fn build_router(state: AppState) -> Router {
        Router::new()
            .route("/test", get(echo_handler))
            .layer(middleware::from_fn_with_state(
                state.clone(),
                federation_middleware,
            ))
            .with_state(state)
    }

    fn base_claims() -> Claims {
        use crate::auth::claims::RealmAccess;
        Claims {
            sub: "user-1".to_string(),
            exp: chrono::Utc::now().timestamp() + 3600,
            iat: chrono::Utc::now().timestamp(),
            iss: "https://auth.gostoa.dev/realms/stoa".to_string(),
            aud: Audience::Single("stoa-mcp".to_string()),
            azp: None,
            preferred_username: None,
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
            scope: None,
            cnf: None,
            sub_account_id: None,
            master_account_id: None,
        }
    }

    fn test_claims_with_federation() -> Claims {
        let mut claims = base_claims();
        claims.sub_account_id = Some("sub-acct-1".to_string());
        claims.master_account_id = Some("master-1".to_string());
        claims
    }

    fn test_claims_without_federation() -> Claims {
        base_claims()
    }

    #[tokio::test]
    async fn test_disabled_passes_through() {
        let state = test_state(false);
        let app = build_router(state);

        let response = app
            .oneshot(Request::builder().uri("/test").body(Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_no_auth_user_passes_through() {
        let state = test_state(true);
        let app = build_router(state);

        let response = app
            .oneshot(Request::builder().uri("/test").body(Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_no_federation_claims_passes_through() {
        let state = test_state(true);
        let app = build_router(state);

        let mut request = Request::builder().uri("/test").body(Body::empty()).unwrap();
        request.extensions_mut().insert(AuthenticatedUser {
            user_id: "user-1".to_string(),
            username: Some("test".to_string()),
            email: None,
            tenant_id: Some("acme".to_string()),
            claims: test_claims_without_federation(),
            raw_token: "token".to_string(),
        });

        let response = app.oneshot(request).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_federation_context_injected() {
        let state = test_state(true);

        // Use a handler that checks for SubAccountContext
        async fn check_handler(request: axum::extract::Request) -> axum::response::Response {
            use axum::response::IntoResponse;
            if request.extensions().get::<SubAccountContext>().is_some() {
                StatusCode::OK.into_response()
            } else {
                StatusCode::NOT_FOUND.into_response()
            }
        }

        let app = Router::new()
            .route("/test", get(check_handler))
            .layer(middleware::from_fn_with_state(
                state.clone(),
                federation_middleware,
            ))
            .with_state(state);

        let mut request = Request::builder().uri("/test").body(Body::empty()).unwrap();
        request.extensions_mut().insert(AuthenticatedUser {
            user_id: "user-1".to_string(),
            username: Some("test".to_string()),
            email: None,
            tenant_id: Some("acme".to_string()),
            claims: test_claims_with_federation(),
            raw_token: "token".to_string(),
        });

        let response = app.oneshot(request).await.unwrap();
        // SubAccountContext should be present (allowed_tools will be None since CP is unreachable)
        assert_eq!(response.status(), StatusCode::OK);
    }
}
