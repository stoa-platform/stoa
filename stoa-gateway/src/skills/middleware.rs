//! Skills middleware — resolves skills and injects SkillContext (CAB-1365)
//!
//! Runs after auth middleware so that tenant_id is available from AuthenticatedUser.
//! Resolves skills using the CSS cascade model, then inserts SkillContext into
//! request extensions for downstream handlers.

use axum::{body::Body, extract::State, http::Request, middleware::Next, response::Response};
use tracing::debug;

use crate::auth::middleware::AuthenticatedUser;
use crate::state::AppState;

use super::context::SkillContext;

/// Skills middleware.
///
/// 1. Early return if skill context is disabled
/// 2. Extract AuthenticatedUser from request extensions
/// 3. Resolve skills using CSS cascade (tenant, tool_ref, user_ref)
/// 4. Insert SkillContext into request extensions
pub async fn skills_middleware(
    State(state): State<AppState>,
    mut request: Request<Body>,
    next: Next,
) -> Response {
    // Skip if skill context injection is disabled
    if !state.config.skill_context_enabled {
        return next.run(request).await;
    }

    // Extract auth context (must run after auth middleware)
    let (tenant_id, user_ref) = match request.extensions().get::<AuthenticatedUser>() {
        Some(user) => {
            let tenant = user
                .tenant_id
                .clone()
                .unwrap_or_else(|| "unknown".to_string());
            let user_ref = user.email.clone().or_else(|| {
                user.username
                    .as_ref()
                    .filter(|u| *u != &user.user_id)
                    .cloned()
            });
            (tenant, user_ref)
        }
        None => return next.run(request).await,
    };

    // Resolve skills using CSS cascade
    // tool_ref is not available at middleware level (it's known only at tool call time)
    // so we resolve without tool_ref here — tool-specific resolution happens in the handler
    let resolved = state
        .skill_resolver
        .resolve(&tenant_id, None, user_ref.as_deref());

    if resolved.is_empty() {
        return next.run(request).await;
    }

    let ctx = SkillContext::from_resolved(&resolved);

    debug!(
        tenant_id = %tenant_id,
        skill_count = ctx.count,
        "Skills resolved via CSS cascade"
    );

    request.extensions_mut().insert(ctx);

    next.run(request).await
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::auth::claims::{Audience, Claims, RealmAccess};
    use crate::auth::middleware::AuthenticatedUser;
    use crate::config::Config;
    use crate::skills::resolver::{SkillResolver, SkillScope, StoredSkill};
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
            skill_context_enabled: enabled,
            ..Config::default()
        };
        AppState::new(config)
    }

    fn build_router(state: AppState) -> Router {
        Router::new()
            .route("/test", get(echo_handler))
            .layer(middleware::from_fn_with_state(
                state.clone(),
                skills_middleware,
            ))
            .with_state(state)
    }

    fn base_claims() -> Claims {
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

    fn make_auth_user(tenant: &str, email: Option<&str>) -> AuthenticatedUser {
        let mut claims = base_claims();
        claims.tenant = Some(tenant.to_string());
        claims.email = email.map(|e| e.to_string());
        AuthenticatedUser {
            user_id: "user-1".to_string(),
            username: Some("testuser".to_string()),
            email: email.map(|e| e.to_string()),
            tenant_id: Some(tenant.to_string()),
            claims,
            raw_token: "token".to_string(),
        }
    }

    fn add_skill(resolver: &SkillResolver, key: &str, tenant: &str, scope: SkillScope) {
        resolver.upsert(StoredSkill {
            key: key.to_string(),
            name: key.split('/').next_back().unwrap_or(key).to_string(),
            description: None,
            tenant_id: tenant.to_string(),
            scope,
            priority: 50,
            instructions: Some(format!("Instructions for {}", key)),
            tool_ref: None,
            user_ref: None,
            enabled: true,
        });
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
    async fn test_no_skills_passes_through() {
        let state = test_state(true);
        let app = build_router(state);

        let mut request = Request::builder().uri("/test").body(Body::empty()).unwrap();
        request
            .extensions_mut()
            .insert(make_auth_user("acme", None));

        let response = app.oneshot(request).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_skills_context_injected() {
        let state = test_state(true);
        add_skill(
            &state.skill_resolver,
            "ns/style",
            "acme",
            SkillScope::Tenant,
        );

        // Use handler that checks for SkillContext
        async fn check_handler(request: axum::extract::Request) -> axum::response::Response {
            use axum::response::IntoResponse;
            if let Some(ctx) = request.extensions().get::<SkillContext>() {
                if ctx.count == 1 {
                    return StatusCode::OK.into_response();
                }
            }
            StatusCode::NOT_FOUND.into_response()
        }

        let app = Router::new()
            .route("/test", get(check_handler))
            .layer(middleware::from_fn_with_state(
                state.clone(),
                skills_middleware,
            ))
            .with_state(state);

        let mut request = Request::builder().uri("/test").body(Body::empty()).unwrap();
        request
            .extensions_mut()
            .insert(make_auth_user("acme", None));

        let response = app.oneshot(request).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_skills_tenant_isolation() {
        let state = test_state(true);
        add_skill(
            &state.skill_resolver,
            "ns/other-tenant",
            "other",
            SkillScope::Tenant,
        );

        // Handler checks that no skills are injected for "acme" tenant
        async fn check_no_ctx(request: axum::extract::Request) -> axum::response::Response {
            use axum::response::IntoResponse;
            if request.extensions().get::<SkillContext>().is_none() {
                StatusCode::OK.into_response()
            } else {
                StatusCode::CONFLICT.into_response()
            }
        }

        let app = Router::new()
            .route("/test", get(check_no_ctx))
            .layer(middleware::from_fn_with_state(
                state.clone(),
                skills_middleware,
            ))
            .with_state(state);

        let mut request = Request::builder().uri("/test").body(Body::empty()).unwrap();
        request
            .extensions_mut()
            .insert(make_auth_user("acme", None));

        let response = app.oneshot(request).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_user_scope_resolution() {
        let state = test_state(true);

        // Add a user-scoped skill for alice@acme.com
        let skill = StoredSkill {
            key: "ns/alice-pref".to_string(),
            name: "alice-pref".to_string(),
            description: None,
            tenant_id: "acme".to_string(),
            scope: SkillScope::User,
            priority: 80,
            instructions: Some("Alice prefers verbose output.".to_string()),
            tool_ref: None,
            user_ref: Some("alice@acme.com".to_string()),
            enabled: true,
        };
        state.skill_resolver.upsert(skill.clone());

        // Also add a tenant-scoped skill
        add_skill(
            &state.skill_resolver,
            "ns/tenant-base",
            "acme",
            SkillScope::Tenant,
        );

        // Handler checks skill count
        async fn check_count(request: axum::extract::Request) -> axum::response::Response {
            use axum::response::IntoResponse;
            if let Some(ctx) = request.extensions().get::<SkillContext>() {
                // Should have 2 skills: user + tenant
                if ctx.count == 2 {
                    return StatusCode::OK.into_response();
                }
                return (
                    StatusCode::CONFLICT,
                    format!("Expected 2 skills, got {}", ctx.count),
                )
                    .into_response();
            }
            StatusCode::NOT_FOUND.into_response()
        }

        let app = Router::new()
            .route("/test", get(check_count))
            .layer(middleware::from_fn_with_state(
                state.clone(),
                skills_middleware,
            ))
            .with_state(state);

        let mut request = Request::builder().uri("/test").body(Body::empty()).unwrap();
        request
            .extensions_mut()
            .insert(make_auth_user("acme", Some("alice@acme.com")));

        let response = app.oneshot(request).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }
}
