//! MCP REST Handlers
//!
//! REST-style endpoints for MCP tools (backward compat with non-SSE clients).
//!
//! Integrates all 4 CAB-1105 phases:
//! - Phase 1: JWT auth extraction → real user context flows to native tools
//! - Phase 2: OPA policy evaluation with real scopes/roles
//! - Phase 3: Kafka metering emission after every tool call
//! - Phase 4: Token optimization on responses (via X-Token-Optimization header)

use axum::{
    extract::State,
    http::{HeaderMap, StatusCode},
    response::IntoResponse,
    Json,
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::time::Instant;
use tracing::{debug, error, instrument, warn};

use crate::auth::jwt::JwtValidator;
use crate::mcp::tools::{ToolContext, ToolDefinition};
use crate::metering::{
    ErrorSnapshot, EventStatus, GatewaySnapshot, MeteringProducerTrait, ToolCallEvent,
};
use crate::metrics;
use crate::optimization::{OptimizationLevel, OptimizationSettings, TokenOptimizer};
use crate::state::AppState;

// === Request/Response Types ===

#[derive(Debug, Deserialize)]
pub struct ToolsListRequest {
    #[allow(dead_code)]
    #[serde(default)]
    pub cursor: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct ToolsListResponse {
    pub tools: Vec<ToolDefinition>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub next_cursor: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct ToolsCallRequest {
    pub name: String,
    #[serde(default)]
    pub arguments: Value,
}

#[derive(Debug, Serialize)]
pub struct ToolsCallResponse {
    pub content: Vec<ToolContent>,
    #[serde(rename = "isError", skip_serializing_if = "Option::is_none")]
    pub is_error: Option<bool>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum ToolContent {
    #[serde(rename = "text")]
    Text { text: String },
}

// === Authentication Context (Phase 1) ===

/// Extracted authentication context from request headers
struct AuthContext {
    user_id: Option<String>,
    user_email: Option<String>,
    tenant_id: String,
    roles: Vec<String>,
    scopes: Vec<String>,
    raw_token: Option<String>,
}

/// Extract and validate JWT from Authorization header (Phase 1: CAB-1105)
///
/// Flow:
/// 1. Extract Bearer token from Authorization header
/// 2. Validate JWT via Keycloak JWKS (RS256)
/// 3. Extract claims (user_id, email, roles, scopes)
/// 4. Expand role-based scopes (ADR-012)
/// 5. Fallback to unauthenticated context if no JWT or validation fails
async fn extract_auth_context(state: &AppState, headers: &HeaderMap) -> AuthContext {
    let tenant_from_header = extract_tenant(headers);
    let user_from_header = extract_user(headers);

    // Try to extract and validate JWT
    if let Some(auth_header) = headers.get("Authorization").and_then(|v| v.to_str().ok()) {
        if let Some(validator) = &state.jwt_validator {
            if let Ok(token_str) = JwtValidator::extract_token(auth_header) {
                match validator.validate(token_str).await {
                    Ok(claims) => {
                        let roles: Vec<String> =
                            claims.realm_roles().iter().map(|s| s.to_string()).collect();
                        let mut scopes: Vec<String> =
                            claims.scopes().iter().map(|s| s.to_string()).collect();

                        // Expand role-based scopes (ADR-012 12-Scope Model)
                        expand_role_scopes(&roles, &mut scopes);

                        return AuthContext {
                            user_id: Some(claims.sub.clone()),
                            user_email: claims.email.clone(),
                            tenant_id: claims
                                .tenant_id()
                                .map(|s| s.to_string())
                                .or(tenant_from_header)
                                .unwrap_or_else(|| "default".to_string()),
                            roles,
                            scopes,
                            raw_token: Some(token_str.to_string()),
                        };
                    }
                    Err(e) => {
                        warn!(error = %e, "JWT validation failed, using default context");
                    }
                }
            }
        }
    }

    // Fallback: unauthenticated with default read scope
    AuthContext {
        user_id: user_from_header,
        user_email: None,
        tenant_id: tenant_from_header.unwrap_or_else(|| "default".to_string()),
        roles: vec![],
        scopes: vec!["stoa:read".to_string()],
        raw_token: None,
    }
}

/// Expand STOA roles to OAuth scopes (ADR-012 12-Scope Model)
///
/// Maps Keycloak realm roles to granular STOA scopes:
/// - cpi-admin → all 6 scopes (admin, read, write, execute, deploy, audit)
/// - tenant-admin → read, write, execute
/// - devops → read, write, deploy
/// - viewer → read only
fn expand_role_scopes(roles: &[String], scopes: &mut Vec<String>) {
    for role in roles {
        let extra = match role.as_str() {
            "cpi-admin" | "cpi_admin" | "admin" => vec![
                "stoa:admin",
                "stoa:read",
                "stoa:write",
                "stoa:execute",
                "stoa:deploy",
                "stoa:audit",
            ],
            "tenant-admin" | "tenant_admin" => {
                vec!["stoa:read", "stoa:write", "stoa:execute"]
            }
            "devops" | "dev-ops" => vec!["stoa:read", "stoa:write", "stoa:deploy"],
            "viewer" | "read-only" | "readonly" => vec!["stoa:read"],
            _ => vec![],
        };
        for s in extra {
            let s = s.to_string();
            if !scopes.contains(&s) {
                scopes.push(s);
            }
        }
    }
}

/// Extract token optimization level from request header (Phase 4)
fn extract_optimization_level(headers: &HeaderMap) -> OptimizationLevel {
    headers
        .get("X-Token-Optimization")
        .and_then(|v| v.to_str().ok())
        .map(OptimizationLevel::from_str)
        .unwrap_or(OptimizationLevel::None)
}

// === Handlers ===

/// POST /mcp/tools/list - List available tools
#[instrument(name = "mcp.tools.list", skip(state, headers, _request), fields(otel.kind = "server"))]
pub async fn mcp_tools_list(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(_request): Json<ToolsListRequest>,
) -> impl IntoResponse {
    let auth = extract_auth_context(&state, &headers).await;

    debug!(tenant_id = %auth.tenant_id, "Listing MCP tools");

    let tools = state.tool_registry.list(Some(&auth.tenant_id));

    Json(ToolsListResponse {
        tools,
        next_cursor: None,
    })
}

/// POST /mcp/tools/call - Execute a tool
///
/// Full execution pipeline (CAB-1105 Phases 1-4):
/// 1. JWT auth extraction (Phase 1)
/// 2. Rate limit check
/// 3. OPA policy evaluation (Phase 2)
/// 4. Tool execution
/// 5. Metering emission (Phase 3)
/// 6. Token optimization (Phase 4)
#[instrument(name = "mcp.tools.call", skip(state, headers, request), fields(otel.kind = "server"))]
pub async fn mcp_tools_call(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(request): Json<ToolsCallRequest>,
) -> impl IntoResponse {
    let start = Instant::now();
    let request_id = uuid::Uuid::new_v4().to_string();
    let request_size = serde_json::to_string(&request.arguments)
        .map(|s| s.len() as u64)
        .unwrap_or(0);

    // Phase 1: Extract JWT auth context
    let auth = extract_auth_context(&state, &headers).await;
    let t_auth = start.elapsed();

    debug!(
        tenant_id = %auth.tenant_id,
        tool = %request.name,
        request_id = %request_id,
        user = ?auth.user_id,
        scopes = ?auth.scopes,
        "Executing MCP tool"
    );

    // Get tool from registry
    let tool = match state.tool_registry.get(&request.name) {
        Some(t) => t,
        None => {
            warn!(tool = %request.name, "Tool not found");
            metrics::record_tool_call(&request.name, &auth.tenant_id, "not_found", 0.0);
            emit_metering_event(
                &state,
                &auth,
                &request.name,
                "Read",
                EventStatus::NotFound,
                start,
                0,
                request_size,
                0,
            );
            return (
                StatusCode::NOT_FOUND,
                Json(ToolsCallResponse {
                    content: vec![ToolContent::Text {
                        text: format!("Tool '{}' not found", request.name),
                    }],
                    is_error: Some(true),
                }),
            );
        }
    };

    // Check rate limit
    let rate_result = state.rate_limiter.check(&auth.tenant_id);
    if !rate_result.allowed {
        warn!(tenant_id = %auth.tenant_id, "Rate limit exceeded");
        metrics::record_rate_limit_hit(&auth.tenant_id);
        emit_metering_event(
            &state,
            &auth,
            &request.name,
            &format!("{:?}", tool.required_action()),
            EventStatus::RateLimited,
            start,
            0,
            request_size,
            0,
        );
        return (
            StatusCode::TOO_MANY_REQUESTS,
            Json(ToolsCallResponse {
                content: vec![ToolContent::Text {
                    text: "Rate limit exceeded".to_string(),
                }],
                is_error: Some(true),
            }),
        );
    }

    // Build tool context with real JWT claims (Phase 1)
    let ctx = ToolContext {
        tenant_id: auth.tenant_id.clone(),
        user_id: auth.user_id.clone(),
        user_email: auth.user_email.clone(),
        request_id,
        roles: auth.roles.clone(),
        scopes: auth.scopes.clone(),
        raw_token: auth.raw_token.clone(),
    };

    // Phase 2: OPA policy evaluation with real scopes/roles
    let required_action = tool.required_action();
    let t_policy_start = Instant::now();
    if let Err(e) = state.uac_enforcer.check_with_context(
        ctx.user_id.clone(),
        ctx.user_email.clone(),
        &ctx.tenant_id,
        &request.name,
        required_action,
        ctx.scopes.clone(),
        ctx.roles.clone(),
    ) {
        let t_gateway = start.elapsed().as_millis() as u64;
        warn!(
            tool = %request.name,
            action = ?required_action,
            tenant = %auth.tenant_id,
            "UAC policy denied: {}",
            e
        );
        emit_metering_event(
            &state,
            &auth,
            &request.name,
            &format!("{:?}", required_action),
            EventStatus::PolicyDenied,
            start,
            t_gateway,
            request_size,
            0,
        );
        return (
            StatusCode::FORBIDDEN,
            Json(ToolsCallResponse {
                content: vec![ToolContent::Text {
                    text: format!("Permission denied: {}", e),
                }],
                is_error: Some(true),
            }),
        );
    }
    let t_policy = t_policy_start.elapsed();

    // Execute tool (measure backend time separately)
    let t_backend_start = Instant::now();
    match tool.execute(request.arguments, &ctx).await {
        Ok(result) => {
            let duration = start.elapsed();
            let duration_secs = duration.as_secs_f64();
            let t_gateway_ms = (t_auth + t_policy).as_millis() as u64;

            metrics::record_tool_call(&request.name, &auth.tenant_id, "success", duration_secs);

            // Build response content
            let content: Vec<ToolContent> = result
                .content
                .into_iter()
                .map(|c| match c {
                    crate::mcp::tools::ToolContent::Text { text } => ToolContent::Text { text },
                    _ => ToolContent::Text {
                        text: "[unsupported content type]".to_string(),
                    },
                })
                .collect();

            // Phase 4: Apply token optimization if requested
            let opt_level = extract_optimization_level(&headers);
            let content = if opt_level != OptimizationLevel::None {
                let optimizer = TokenOptimizer::new(OptimizationSettings {
                    level: opt_level,
                    ..Default::default()
                });
                content
                    .into_iter()
                    .map(|c| match c {
                        ToolContent::Text { text } => {
                            let (optimized, _stats) = optimizer.optimize_string(&text);
                            ToolContent::Text { text: optimized }
                        }
                    })
                    .collect()
            } else {
                content
            };

            let response_size = serde_json::to_string(&content)
                .map(|s| s.len() as u64)
                .unwrap_or(0);

            // Phase 3: Emit metering event
            emit_metering_event(
                &state,
                &auth,
                &request.name,
                &format!("{:?}", required_action),
                EventStatus::Success,
                start,
                t_gateway_ms,
                request_size,
                response_size,
            );

            (
                StatusCode::OK,
                Json(ToolsCallResponse {
                    content,
                    is_error: result.is_error,
                }),
            )
        }
        Err(e) => {
            let t_backend = t_backend_start.elapsed();
            let duration = start.elapsed();
            let t_gateway_ms = (t_auth + t_policy).as_millis() as u64;
            let t_backend_ms = t_backend.as_millis() as u64;

            error!(tool = %request.name, error = %e, "Tool execution failed");
            metrics::record_tool_call(
                &request.name,
                &auth.tenant_id,
                "error",
                duration.as_secs_f64(),
            );

            // Phase 3: Emit error metering event + error snapshot
            emit_metering_event(
                &state,
                &auth,
                &request.name,
                &format!("{:?}", required_action),
                EventStatus::Error,
                start,
                t_gateway_ms,
                request_size,
                0,
            );
            emit_error_snapshot(
                &state,
                &auth,
                &request.name,
                &format!("{:?}", required_action),
                &e.to_string(),
                500,
                start,
                t_gateway_ms,
                t_backend_ms,
            );

            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ToolsCallResponse {
                    content: vec![ToolContent::Text {
                        text: e.to_string(),
                    }],
                    is_error: Some(true),
                }),
            )
        }
    }
}

// === Phase 3: Metering Emission ===

/// Emit a metering event (non-blocking, fire-and-forget)
#[allow(clippy::too_many_arguments)]
fn emit_metering_event(
    state: &AppState,
    auth: &AuthContext,
    tool_name: &str,
    action: &str,
    status: EventStatus,
    start: Instant,
    t_gateway_ms: u64,
    request_size: u64,
    response_size: u64,
) {
    if let Some(ref producer) = state.metering_producer {
        let latency_ms = start.elapsed().as_millis() as u64;
        let t_backend_ms = latency_ms.saturating_sub(t_gateway_ms);

        let event = ToolCallEvent::new(
            auth.tenant_id.clone(),
            tool_name.to_string(),
            action.to_string(),
        )
        .with_user(auth.user_id.clone(), auth.user_email.clone())
        .with_timing(latency_ms, t_gateway_ms, t_backend_ms)
        .with_status(status)
        .with_sizes(request_size, response_size)
        .with_auth(auth.scopes.clone(), auth.roles.clone());

        producer.send_metering_event(event);
    }
}

/// Emit an error snapshot (non-blocking, fire-and-forget)
#[allow(clippy::too_many_arguments)]
fn emit_error_snapshot(
    state: &AppState,
    auth: &AuthContext,
    tool_name: &str,
    action: &str,
    error_message: &str,
    response_status: u16,
    start: Instant,
    t_gateway_ms: u64,
    t_backend_ms: u64,
) {
    if let Some(ref producer) = state.metering_producer {
        let latency_ms = start.elapsed().as_millis() as u64;

        let event = ToolCallEvent::new(
            auth.tenant_id.clone(),
            tool_name.to_string(),
            action.to_string(),
        )
        .with_user(auth.user_id.clone(), auth.user_email.clone())
        .with_timing(latency_ms, t_gateway_ms, t_backend_ms)
        .with_status(EventStatus::Error);

        let snapshot = ErrorSnapshot::from_event(
            event,
            "ToolExecutionError".to_string(),
            error_message.to_string(),
            response_status,
        )
        .with_request("/mcp/tools/call".to_string(), "POST".to_string())
        .with_gateway_state(GatewaySnapshot {
            active_sessions: state.session_manager.count() as u64,
            uptime_secs: 0, // TODO: track gateway uptime
            rate_limit_buckets: 0,
            memory_rss_bytes: None,
        });

        producer.send_error_snapshot(snapshot);
    }
}

// === Helpers ===

fn extract_tenant(headers: &HeaderMap) -> Option<String> {
    headers
        .get("X-Tenant-ID")
        .and_then(|v| v.to_str().ok())
        .map(|s| s.to_string())
}

fn extract_user(headers: &HeaderMap) -> Option<String> {
    headers
        .get("X-User-ID")
        .and_then(|v| v.to_str().ok())
        .map(|s| s.to_string())
}
