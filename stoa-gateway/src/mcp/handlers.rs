//! MCP REST Handlers
//!
//! REST-style endpoints for MCP tools (backward compat with non-SSE clients)

use axum::{
    extract::State,
    http::{HeaderMap, StatusCode},
    response::IntoResponse,
    Json,
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::time::Instant;
use tracing::{debug, error, instrument, warn};

use crate::metrics;
use crate::mcp::tools::{ToolContext, ToolDefinition};
use crate::state::AppState;

// === Request/Response Types ===

#[derive(Debug, Deserialize)]
pub struct ToolsListRequest {
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

// === Handlers ===

/// POST /mcp/tools/list - List available tools
#[instrument(name = "mcp.tools.list", skip(state, headers, request), fields(otel.kind = "server"))]
pub async fn mcp_tools_list(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(request): Json<ToolsListRequest>,
) -> impl IntoResponse {
    let tenant_id = extract_tenant(&headers).unwrap_or_else(|| "default".to_string());
    
    debug!(tenant_id = %tenant_id, "Listing MCP tools");

    let tools = state.tool_registry.list(Some(&tenant_id));

    Json(ToolsListResponse {
        tools,
        next_cursor: None, // Pagination not implemented yet
    })
}

/// POST /mcp/tools/call - Execute a tool
#[instrument(name = "mcp.tools.call", skip(state, headers, request), fields(otel.kind = "server"))]
pub async fn mcp_tools_call(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(request): Json<ToolsCallRequest>,
) -> impl IntoResponse {
    let tenant_id = extract_tenant(&headers).unwrap_or_else(|| "default".to_string());
    let request_id = uuid::Uuid::new_v4().to_string();
    
    debug!(
        tenant_id = %tenant_id,
        tool = %request.name,
        request_id = %request_id,
        "Executing MCP tool"
    );

    let start = Instant::now();

    // Get tool from registry
    let tool = match state.tool_registry.get(&request.name) {
        Some(t) => t,
        None => {
            warn!(tool = %request.name, "Tool not found");
            metrics::record_tool_call(&request.name, &tenant_id, "not_found", 0.0);
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
    let rate_result = state.rate_limiter.check(&tenant_id);
    if !rate_result.allowed {
        warn!(tenant_id = %tenant_id, "Rate limit exceeded");
        metrics::record_rate_limit_hit(&tenant_id);
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

    // Build context
    let ctx = ToolContext {
        tenant_id: tenant_id.clone(),
        user_id: extract_user(&headers),
        user_email: None,
        request_id,
        roles: vec![],
        raw_token: None,
    };

    // Execute tool
    match tool.execute(request.arguments, &ctx).await {
        Ok(result) => {
            let duration = start.elapsed().as_secs_f64();
            metrics::record_tool_call(&request.name, &tenant_id, "success", duration);
            
            (
                StatusCode::OK,
                Json(ToolsCallResponse {
                    content: result.content.into_iter().map(|c| match c {
                        crate::mcp::tools::ToolContent::Text { text } => ToolContent::Text { text },
                        _ => ToolContent::Text { text: "[unsupported content type]".to_string() },
                    }).collect(),
                    is_error: result.is_error,
                }),
            )
        }
        Err(e) => {
            let duration = start.elapsed().as_secs_f64();
            error!(tool = %request.name, error = %e, "Tool execution failed");
            metrics::record_tool_call(&request.name, &tenant_id, "error", duration);
            
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
