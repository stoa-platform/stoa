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
    http::{HeaderMap, HeaderValue, StatusCode},
    response::{IntoResponse, Response},
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

// === REST v1 Request/Response Types ===

#[derive(Debug, Deserialize)]
pub struct RestToolInvokeRequest {
    pub tool: String,
    #[serde(default)]
    pub arguments: Value,
}

// === Handlers ===

/// GET /mcp/v1/tools — REST-style tool listing (no body required)
///
/// Returns a flat JSON array of tool definitions.
/// Used by demo scripts and simple HTTP clients (non-SSE).
#[instrument(name = "mcp.v1.tools.list", skip(state, headers), fields(otel.kind = "server"))]
pub async fn mcp_rest_tools_list(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> impl IntoResponse {
    let auth = extract_auth_context(&state, &headers).await;
    debug!(tenant_id = %auth.tenant_id, "REST v1: listing MCP tools");

    let tools = state.tool_registry.list(Some(&auth.tenant_id));
    Json(tools)
}

/// POST /mcp/v1/tools/invoke — REST-style tool invocation
///
/// Accepts `{"tool": "name", "arguments": {...}}` and delegates to the
/// same execution pipeline as POST /mcp/tools/call (auth, OPA, metering).
#[instrument(name = "mcp.v1.tools.invoke", skip(state, headers, request), fields(otel.kind = "server"))]
pub async fn mcp_rest_tools_invoke(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(request): Json<RestToolInvokeRequest>,
) -> impl IntoResponse {
    // Delegate to the existing mcp_tools_call pipeline via internal conversion
    let call_request = ToolsCallRequest {
        name: request.tool,
        arguments: request.arguments,
    };
    mcp_tools_call(State(state), headers, Json(call_request)).await
}

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

/// Helper to add rate limit headers to a response
fn with_rate_limit_headers(
    status: StatusCode,
    body: Json<ToolsCallResponse>,
    rate_result: &crate::rate_limit::RateLimitResult,
) -> Response {
    let mut response = (status, body).into_response();

    // Add rate limit headers
    for (key, value) in rate_result.headers() {
        if let Ok(header_value) = HeaderValue::from_str(&value) {
            response.headers_mut().insert(key, header_value);
        }
    }

    response
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
            )
                .into_response();
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
        )
            .into_response();
    }

    // CAB-707: Guardrails check (PII + prompt injection)
    let guardrails_cfg = crate::guardrails::GuardrailsConfig {
        pii_enabled: state.config.guardrails_pii_enabled,
        pii_redact: state.config.guardrails_pii_redact,
        injection_enabled: state.config.guardrails_injection_enabled,
    };
    let arguments = match crate::guardrails::check_request(
        &guardrails_cfg,
        &request.name,
        &request.arguments,
    ) {
        crate::guardrails::GuardrailsOutcome::Pass => request.arguments.clone(),
        crate::guardrails::GuardrailsOutcome::Redacted(redacted) => {
            metrics::record_guardrails_pii("redacted");
            warn!(tool = %request.name, "PII detected and redacted in arguments");
            redacted
        }
        crate::guardrails::GuardrailsOutcome::Blocked(reason) => {
            if reason.contains("injection") {
                metrics::record_guardrails_injection(&request.name);
            } else {
                metrics::record_guardrails_pii("blocked");
            }
            warn!(tool = %request.name, reason = %reason, "Guardrails blocked request");
            return (
                StatusCode::BAD_REQUEST,
                Json(ToolsCallResponse {
                    content: vec![ToolContent::Text {
                        text: format!("Request blocked: {reason}"),
                    }],
                    is_error: Some(true),
                }),
            )
                .into_response();
        }
    };

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
        )
            .into_response();
    }
    let t_policy = t_policy_start.elapsed();

    // Phase 6: Check semantic cache for read-only tools
    let annotations = tool.definition().annotations;
    let is_read_only = annotations
        .as_ref()
        .and_then(|a| a.read_only_hint)
        .unwrap_or(false);

    if is_read_only {
        if let Some(cached) = state
            .semantic_cache
            .get(&request.name, &auth.tenant_id, &request.arguments)
            .await
        {
            let t_gateway_ms = (t_auth + t_policy).as_millis() as u64;
            metrics::record_tool_call(
                &request.name,
                &auth.tenant_id,
                "cache_hit",
                start.elapsed().as_secs_f64(),
            );
            emit_metering_event(
                &state,
                &auth,
                &request.name,
                &format!("{:?}", required_action),
                EventStatus::Success,
                start,
                t_gateway_ms,
                request_size,
                cached.result.to_string().len() as u64,
            );
            let text = serde_json::to_string_pretty(&cached.result)
                .unwrap_or_else(|_| cached.result.to_string());
            return (
                StatusCode::OK,
                Json(ToolsCallResponse {
                    content: vec![ToolContent::Text { text }],
                    is_error: None,
                }),
            )
                .into_response();
        }
    }

    // Execute tool (measure backend time separately)
    let t_backend_start = Instant::now();
    let primary_result = tool.execute(arguments.clone(), &ctx).await;

    // CAB-708: Fallback chain — try alternate providers if primary failed
    let result = crate::resilience::execute_or_direct(
        &state.fallback_chain,
        &state.circuit_breakers,
        &state.tool_registry,
        &request.name,
        arguments,
        &ctx,
        primary_result,
    )
    .await;

    match result {
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

            // Phase 6: Cache result for read-only tools
            if is_read_only {
                if let Some(ToolContent::Text { ref text }) = content.first() {
                    if let Ok(json_val) = serde_json::from_str::<Value>(text) {
                        state
                            .semantic_cache
                            .put(&request.name, &auth.tenant_id, &request.arguments, json_val)
                            .await;
                    }
                }
            }

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
                .into_response()
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

            with_rate_limit_headers(
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ToolsCallResponse {
                    content: vec![ToolContent::Text {
                        text: e.to_string(),
                    }],
                    is_error: Some(true),
                }),
                &rate_result,
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
            uptime_secs: state.start_time.elapsed().as_secs(),
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

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::HeaderValue;

    // === expand_role_scopes ===

    #[test]
    fn test_expand_cpi_admin_all_scopes() {
        let roles = vec!["cpi-admin".to_string()];
        let mut scopes = vec![];
        expand_role_scopes(&roles, &mut scopes);
        assert_eq!(scopes.len(), 6);
        assert!(scopes.contains(&"stoa:admin".to_string()));
        assert!(scopes.contains(&"stoa:read".to_string()));
        assert!(scopes.contains(&"stoa:write".to_string()));
        assert!(scopes.contains(&"stoa:execute".to_string()));
        assert!(scopes.contains(&"stoa:deploy".to_string()));
        assert!(scopes.contains(&"stoa:audit".to_string()));
    }

    #[test]
    fn test_expand_cpi_admin_underscore_variant() {
        let roles = vec!["cpi_admin".to_string()];
        let mut scopes = vec![];
        expand_role_scopes(&roles, &mut scopes);
        assert_eq!(scopes.len(), 6);
    }

    #[test]
    fn test_expand_admin_role() {
        let roles = vec!["admin".to_string()];
        let mut scopes = vec![];
        expand_role_scopes(&roles, &mut scopes);
        assert_eq!(scopes.len(), 6);
    }

    #[test]
    fn test_expand_tenant_admin() {
        let roles = vec!["tenant-admin".to_string()];
        let mut scopes = vec![];
        expand_role_scopes(&roles, &mut scopes);
        assert_eq!(scopes.len(), 3);
        assert!(scopes.contains(&"stoa:read".to_string()));
        assert!(scopes.contains(&"stoa:write".to_string()));
        assert!(scopes.contains(&"stoa:execute".to_string()));
    }

    #[test]
    fn test_expand_tenant_admin_underscore() {
        let roles = vec!["tenant_admin".to_string()];
        let mut scopes = vec![];
        expand_role_scopes(&roles, &mut scopes);
        assert_eq!(scopes.len(), 3);
    }

    #[test]
    fn test_expand_devops() {
        let roles = vec!["devops".to_string()];
        let mut scopes = vec![];
        expand_role_scopes(&roles, &mut scopes);
        assert_eq!(scopes.len(), 3);
        assert!(scopes.contains(&"stoa:read".to_string()));
        assert!(scopes.contains(&"stoa:write".to_string()));
        assert!(scopes.contains(&"stoa:deploy".to_string()));
    }

    #[test]
    fn test_expand_dev_ops_hyphen() {
        let roles = vec!["dev-ops".to_string()];
        let mut scopes = vec![];
        expand_role_scopes(&roles, &mut scopes);
        assert_eq!(scopes.len(), 3);
        assert!(scopes.contains(&"stoa:deploy".to_string()));
    }

    #[test]
    fn test_expand_viewer() {
        let roles = vec!["viewer".to_string()];
        let mut scopes = vec![];
        expand_role_scopes(&roles, &mut scopes);
        assert_eq!(scopes.len(), 1);
        assert!(scopes.contains(&"stoa:read".to_string()));
    }

    #[test]
    fn test_expand_readonly_variants() {
        for role in &["read-only", "readonly"] {
            let roles = vec![role.to_string()];
            let mut scopes = vec![];
            expand_role_scopes(&roles, &mut scopes);
            assert_eq!(scopes.len(), 1, "Failed for role: {}", role);
            assert!(scopes.contains(&"stoa:read".to_string()));
        }
    }

    #[test]
    fn test_expand_unknown_role_adds_nothing() {
        let roles = vec!["unknown-role".to_string()];
        let mut scopes = vec![];
        expand_role_scopes(&roles, &mut scopes);
        assert!(scopes.is_empty());
    }

    #[test]
    fn test_expand_no_duplicates() {
        let roles = vec!["cpi-admin".to_string()];
        let mut scopes = vec!["stoa:read".to_string(), "stoa:admin".to_string()];
        expand_role_scopes(&roles, &mut scopes);
        // Should still have 6 unique scopes, not 8
        assert_eq!(scopes.len(), 6);
    }

    #[test]
    fn test_expand_multiple_roles_combined() {
        let roles = vec!["viewer".to_string(), "devops".to_string()];
        let mut scopes = vec![];
        expand_role_scopes(&roles, &mut scopes);
        // viewer: read, devops: read+write+deploy → 3 unique
        assert_eq!(scopes.len(), 3);
        assert!(scopes.contains(&"stoa:read".to_string()));
        assert!(scopes.contains(&"stoa:write".to_string()));
        assert!(scopes.contains(&"stoa:deploy".to_string()));
    }

    #[test]
    fn test_expand_empty_roles() {
        let roles: Vec<String> = vec![];
        let mut scopes = vec![];
        expand_role_scopes(&roles, &mut scopes);
        assert!(scopes.is_empty());
    }

    // === extract_tenant ===

    #[test]
    fn test_extract_tenant_present() {
        let mut headers = HeaderMap::new();
        headers.insert("X-Tenant-ID", HeaderValue::from_static("acme-corp"));
        assert_eq!(extract_tenant(&headers), Some("acme-corp".to_string()));
    }

    #[test]
    fn test_extract_tenant_missing() {
        let headers = HeaderMap::new();
        assert_eq!(extract_tenant(&headers), None);
    }

    // === extract_user ===

    #[test]
    fn test_extract_user_present() {
        let mut headers = HeaderMap::new();
        headers.insert("X-User-ID", HeaderValue::from_static("user-42"));
        assert_eq!(extract_user(&headers), Some("user-42".to_string()));
    }

    #[test]
    fn test_extract_user_missing() {
        let headers = HeaderMap::new();
        assert_eq!(extract_user(&headers), None);
    }

    // === extract_optimization_level ===

    #[test]
    fn test_optimization_level_none_when_missing() {
        let headers = HeaderMap::new();
        assert_eq!(
            extract_optimization_level(&headers),
            OptimizationLevel::None
        );
    }

    #[test]
    fn test_optimization_level_moderate() {
        let mut headers = HeaderMap::new();
        headers.insert("X-Token-Optimization", HeaderValue::from_static("moderate"));
        assert_eq!(
            extract_optimization_level(&headers),
            OptimizationLevel::Moderate
        );
    }

    #[test]
    fn test_optimization_level_aggressive() {
        let mut headers = HeaderMap::new();
        headers.insert(
            "X-Token-Optimization",
            HeaderValue::from_static("aggressive"),
        );
        assert_eq!(
            extract_optimization_level(&headers),
            OptimizationLevel::Aggressive
        );
    }

    #[test]
    fn test_optimization_level_unknown_defaults_to_none() {
        let mut headers = HeaderMap::new();
        headers.insert("X-Token-Optimization", HeaderValue::from_static("turbo"));
        assert_eq!(
            extract_optimization_level(&headers),
            OptimizationLevel::None
        );
    }
}
