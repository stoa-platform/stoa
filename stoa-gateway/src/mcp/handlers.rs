//! MCP HTTP Handlers
//!
//! CAB-912: HTTP endpoints for MCP protocol (tools/list, tools/call).
//! CAB-912 P2: JWT authentication integration.

use axum::{
    extract::State,
    http::StatusCode,
    middleware,
    response::IntoResponse,
    routing::{get, post},
    Json, Router,
};
use serde_json::json;
use std::sync::Arc;
use tracing::{error, info, warn};

use super::protocol::{
    McpError, ToolCallRequest, ToolCallResponse, ToolsListRequest, ToolsListResponse,
};
use super::tools::ToolRegistry;
use crate::auth::{
    auth_middleware, optional_auth, Action, AuthError, AuthState, AuthUser, AuthenticatedUser,
    OptionalAuthUser, RbacEnforcer,
};
use crate::uac::EnforcementContext;

// =============================================================================
// App State
// =============================================================================

/// Shared application state for MCP handlers.
#[derive(Clone)]
pub struct McpState {
    /// Tool registry
    pub registry: Arc<ToolRegistry>,

    /// Auth state (optional, for testing without auth)
    pub auth_state: Option<AuthState>,

    /// RBAC enforcer
    pub rbac_enforcer: Option<Arc<RbacEnforcer>>,
}

impl McpState {
    /// Create a new MCP state without authentication (for testing).
    pub fn new(registry: ToolRegistry) -> Self {
        Self {
            registry: Arc::new(registry),
            auth_state: None,
            rbac_enforcer: None,
        }
    }

    /// Create with authentication enabled.
    pub fn with_auth(registry: ToolRegistry, auth_state: AuthState) -> Self {
        Self {
            registry: Arc::new(registry),
            auth_state: Some(auth_state),
            rbac_enforcer: Some(Arc::new(RbacEnforcer::default())),
        }
    }

    /// Create with full configuration.
    pub fn with_rbac(
        registry: ToolRegistry,
        auth_state: AuthState,
        rbac_enforcer: RbacEnforcer,
    ) -> Self {
        Self {
            registry: Arc::new(registry),
            auth_state: Some(auth_state),
            rbac_enforcer: Some(Arc::new(rbac_enforcer)),
        }
    }

    /// Check if authentication is enabled.
    pub fn is_auth_enabled(&self) -> bool {
        self.auth_state.is_some()
    }
}

// =============================================================================
// Handlers
// =============================================================================

/// POST /mcp/tools/list
///
/// List all available MCP tools.
async fn handle_tools_list(
    State(state): State<McpState>,
    user: OptionalAuthUser,
    Json(request): Json<ToolsListRequest>,
) -> impl IntoResponse {
    let user_info = user
        .0
        .as_ref()
        .map(|u| format!("user={}", u.user_id))
        .unwrap_or_else(|| "anonymous".to_string());

    info!(
        cursor = ?request.cursor,
        user = %user_info,
        "Handling tools/list request"
    );

    let tools = state.registry.list();

    let response = ToolsListResponse {
        tools,
        next_cursor: None, // Pagination not implemented yet
    };

    Json(response)
}

/// POST /mcp/tools/call
///
/// Execute a tool by name with the given arguments.
/// Requires authentication when auth is enabled.
async fn handle_tools_call(
    State(state): State<McpState>,
    user: OptionalAuthUser,
    Json(request): Json<ToolCallRequest>,
) -> impl IntoResponse {
    info!(tool = %request.name, "Handling tools/call request");

    // Get the tool
    let tool = match state.registry.get(&request.name) {
        Some(t) => t,
        None => {
            let error = McpError::tool_not_found(&request.name);
            error!(tool = %request.name, "Tool not found");
            return (
                StatusCode::NOT_FOUND,
                Json(ToolCallResponse::error(error.message)),
            );
        }
    };

    // Create enforcement context from authenticated user or default
    let ctx = match user.0 {
        Some(auth_user) => {
            info!(
                user_id = %auth_user.user_id,
                tenant = ?auth_user.tenant_id,
                "Authenticated user executing tool"
            );

            // Check RBAC if enforcer is available
            if let Some(rbac) = &state.rbac_enforcer {
                if let Err(e) = rbac.authorize(
                    &auth_user,
                    Action::CreateApi,
                    auth_user.tenant_id.as_deref(),
                ) {
                    warn!(
                        user_id = %auth_user.user_id,
                        error = %e,
                        "RBAC authorization failed"
                    );
                    return (
                        StatusCode::FORBIDDEN,
                        Json(ToolCallResponse::error(format!("Access denied: {}", e))),
                    );
                }
            }

            EnforcementContext::new(
                auth_user.tenant_id.as_deref().unwrap_or("unknown"),
                &auth_user.user_id,
            )
            .with_request_id(uuid::Uuid::new_v4().to_string())
        }
        None => {
            // No authenticated user - check if auth is required
            if state.is_auth_enabled() {
                warn!("Unauthenticated request to tools/call");
                return (
                    StatusCode::UNAUTHORIZED,
                    Json(ToolCallResponse::error("Authentication required")),
                );
            }

            // Allow anonymous access in dev mode
            info!("Anonymous user executing tool (auth disabled)");
            EnforcementContext::new("default-tenant", "anonymous")
                .with_request_id(uuid::Uuid::new_v4().to_string())
        }
    };

    // Execute the tool
    let response = tool.execute(request.arguments, ctx).await;

    if response.is_error {
        (StatusCode::BAD_REQUEST, Json(response))
    } else {
        (StatusCode::OK, Json(response))
    }
}

/// Health check for MCP endpoints.
async fn handle_mcp_health() -> impl IntoResponse {
    Json(json!({
        "status": "ok",
        "service": "mcp-gateway",
        "protocol_version": "1.0"
    }))
}

// =============================================================================
// Router
// =============================================================================

/// Create the MCP router with all endpoints (no auth).
pub fn mcp_router(state: McpState) -> Router {
    Router::new()
        .route("/mcp/tools/list", post(handle_tools_list))
        .route("/mcp/tools/call", post(handle_tools_call))
        .route(
            "/mcp/health",
            post(handle_mcp_health).get(handle_mcp_health),
        )
        .with_state(state)
}

/// Create the MCP router with JWT authentication.
pub fn mcp_router_with_auth(state: McpState) -> Router {
    let auth_state = state
        .auth_state
        .clone()
        .expect("Auth state required for authenticated router");

    // Protected routes (require auth)
    let protected = Router::new()
        .route("/mcp/tools/call", post(handle_tools_call))
        .layer(middleware::from_fn_with_state(
            auth_state.clone(),
            auth_middleware,
        ));

    // Semi-protected routes (optional auth)
    let optional_auth_routes = Router::new()
        .route("/mcp/tools/list", post(handle_tools_list))
        .layer(middleware::from_fn_with_state(
            AuthState::optional(auth_state.validator.clone()),
            optional_auth,
        ));

    // Public routes (no auth)
    let public = Router::new().route(
        "/mcp/health",
        post(handle_mcp_health).get(handle_mcp_health),
    );

    Router::new()
        .merge(protected)
        .merge(optional_auth_routes)
        .merge(public)
        .with_state(state)
}

/// User info endpoint for debugging.
async fn handle_user_info(user: AuthUser) -> impl IntoResponse {
    Json(json!({
        "user_id": user.0.user_id,
        "username": user.0.username,
        "email": user.0.email,
        "tenant_id": user.0.tenant_id,
        "roles": user.0.claims.realm_roles(),
        "scopes": user.0.claims.scopes(),
    }))
}

/// Create a debug router with user info endpoint.
pub fn mcp_debug_router(state: McpState) -> Router {
    let auth_state = state
        .auth_state
        .clone()
        .expect("Auth state required for debug router");

    Router::new()
        .route("/mcp/userinfo", get(handle_user_info))
        .layer(middleware::from_fn_with_state(auth_state, auth_middleware))
        .with_state(state)
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{
        body::Body,
        http::{Method, Request},
    };
    use tower::ServiceExt;

    fn create_test_router() -> Router {
        let registry = ToolRegistry::new();
        let state = McpState::new(registry);
        mcp_router(state)
    }

    #[tokio::test]
    async fn test_tools_list_empty() {
        let app = create_test_router();

        let request = Request::builder()
            .method(Method::POST)
            .uri("/mcp/tools/list")
            .header("content-type", "application/json")
            .body(Body::from("{}"))
            .unwrap();

        let response = app.oneshot(request).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_tools_call_not_found() {
        let app = create_test_router();

        let request = Request::builder()
            .method(Method::POST)
            .uri("/mcp/tools/call")
            .header("content-type", "application/json")
            .body(Body::from(r#"{"name":"nonexistent","arguments":{}}"#))
            .unwrap();

        let response = app.oneshot(request).await.unwrap();
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn test_mcp_health() {
        let app = create_test_router();

        let request = Request::builder()
            .method(Method::GET)
            .uri("/mcp/health")
            .body(Body::empty())
            .unwrap();

        let response = app.oneshot(request).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }
}
