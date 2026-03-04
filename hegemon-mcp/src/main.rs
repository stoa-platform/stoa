//! HEGEMON MCP Server v0 — Read-only tools for AI agent orchestration.
//!
//! Exposes 3 MCP tools via SSE transport:
//! - `hegemon_workers_status`: Active worker sessions from PocketBase
//! - `hegemon_cycle_status`: Current sprint cycle from Linear API
//! - `hegemon_metrics`: Key runtime metrics from Prometheus
//!
//! Runs behind STOA Gateway Internal (port 8090) on `/mcp/sse`.

use axum::{
    extract::State,
    response::{
        sse::{Event, KeepAlive},
        Json, Sse,
    },
    routing::{get, post},
    Router,
};
use futures::stream::Stream;
use serde::{Deserialize, Serialize};
use std::{convert::Infallible, env, net::SocketAddr, sync::Arc, time::Duration};
use tokio_stream::StreamExt;
use tracing::{info, warn};

mod tools;

// ─── Configuration ───────────────────────────────────────────────────────────

#[derive(Clone)]
pub struct AppConfig {
    pub port: u16,
    pub pocketbase_url: String,
    pub linear_api_key: Option<String>,
    pub linear_team_id: Option<String>,
    pub prometheus_url: String,
}

impl AppConfig {
    fn from_env() -> Self {
        Self {
            port: env::var("HEGEMON_MCP_PORT")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(8092),
            pocketbase_url: env::var("POCKETBASE_URL")
                .unwrap_or_else(|_| "https://state.gostoa.dev".to_string()),
            linear_api_key: env::var("LINEAR_API_KEY").ok(),
            linear_team_id: env::var("LINEAR_TEAM_ID").ok(),
            prometheus_url: env::var("PROMETHEUS_URL")
                .unwrap_or_else(|_| "http://localhost:9090".to_string()),
        }
    }
}

// ─── MCP Protocol Types ──────────────────────────────────────────────────────

#[derive(Debug, Serialize)]
struct McpCapabilities {
    server: McpServerInfo,
    capabilities: McpCapabilitySet,
}

#[derive(Debug, Serialize)]
struct McpServerInfo {
    name: String,
    version: String,
}

#[derive(Debug, Serialize)]
struct McpCapabilitySet {
    tools: McpToolCapability,
}

#[derive(Debug, Serialize)]
struct McpToolCapability {
    #[serde(rename = "listChanged")]
    list_changed: bool,
}

#[derive(Debug, Serialize)]
struct McpTool {
    name: String,
    description: String,
    #[serde(rename = "inputSchema")]
    input_schema: serde_json::Value,
}

#[derive(Debug, Deserialize)]
struct McpToolCallRequest {
    name: String,
    #[serde(default)]
    arguments: serde_json::Value,
}

#[derive(Debug, Serialize)]
struct McpToolCallResponse {
    content: Vec<McpContent>,
    #[serde(rename = "isError")]
    is_error: bool,
}

#[derive(Debug, Serialize)]
struct McpContent {
    #[serde(rename = "type")]
    content_type: String,
    text: String,
}

// ─── Handlers ────────────────────────────────────────────────────────────────

async fn health() -> &'static str {
    "ok"
}

async fn capabilities() -> Json<McpCapabilities> {
    Json(McpCapabilities {
        server: McpServerInfo {
            name: "hegemon-mcp".to_string(),
            version: "0.1.0".to_string(),
        },
        capabilities: McpCapabilitySet {
            tools: McpToolCapability {
                list_changed: false,
            },
        },
    })
}

async fn tools_list() -> Json<Vec<McpTool>> {
    Json(vec![
        McpTool {
            name: "hegemon_workers_status".to_string(),
            description: "List active HEGEMON worker sessions with their current status, role, branch, and last activity timestamp.".to_string(),
            input_schema: serde_json::json!({
                "type": "object",
                "properties": {},
                "required": []
            }),
        },
        McpTool {
            name: "hegemon_cycle_status".to_string(),
            description: "Get the current Linear sprint cycle: name, dates, ticket counts by status (todo, in_progress, done), and completion percentage.".to_string(),
            input_schema: serde_json::json!({
                "type": "object",
                "properties": {},
                "required": []
            }),
        },
        McpTool {
            name: "hegemon_metrics".to_string(),
            description: "Get key HEGEMON runtime metrics: request rates, error rates, token usage, and circuit breaker state per worker.".to_string(),
            input_schema: serde_json::json!({
                "type": "object",
                "properties": {
                    "metric": {
                        "type": "string",
                        "description": "Optional: filter to a specific metric (requests, errors, tokens, circuit_breaker). Returns all if omitted.",
                        "enum": ["requests", "errors", "tokens", "circuit_breaker"]
                    }
                },
                "required": []
            }),
        },
    ])
}

async fn tools_call(
    State(config): State<Arc<AppConfig>>,
    Json(request): Json<McpToolCallRequest>,
) -> Json<McpToolCallResponse> {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(10))
        .build()
        .unwrap_or_default();

    let result = match request.name.as_str() {
        "hegemon_workers_status" => {
            tools::workers_status::execute(&client, &config).await
        }
        "hegemon_cycle_status" => {
            tools::cycle_status::execute(&client, &config).await
        }
        "hegemon_metrics" => {
            let metric_filter = request
                .arguments
                .get("metric")
                .and_then(|v| v.as_str())
                .map(String::from);
            tools::metrics::execute(&client, &config, metric_filter).await
        }
        _ => Err(format!("Unknown tool: {}", request.name)),
    };

    match result {
        Ok(text) => Json(McpToolCallResponse {
            content: vec![McpContent {
                content_type: "text".to_string(),
                text,
            }],
            is_error: false,
        }),
        Err(err) => Json(McpToolCallResponse {
            content: vec![McpContent {
                content_type: "text".to_string(),
                text: format!("Error: {err}"),
            }],
            is_error: true,
        }),
    }
}

async fn sse_endpoint(
    State(config): State<Arc<AppConfig>>,
) -> Sse<impl Stream<Item = Result<Event, Infallible>>> {
    let session_id = uuid::Uuid::new_v4().to_string();
    info!(session_id = %session_id, "MCP SSE session started");

    let capabilities = McpCapabilities {
        server: McpServerInfo {
            name: "hegemon-mcp".to_string(),
            version: "0.1.0".to_string(),
        },
        capabilities: McpCapabilitySet {
            tools: McpToolCapability {
                list_changed: false,
            },
        },
    };

    let init_event = Event::default()
        .event("endpoint")
        .data(format!("/mcp/messages?session_id={session_id}"));

    let caps_event = Event::default()
        .event("message")
        .data(serde_json::to_string(&capabilities).unwrap_or_default());

    let stream = tokio_stream::iter(vec![
        Ok::<_, Infallible>(init_event),
        Ok(caps_event),
    ]);

    // Keep connection alive with periodic heartbeats
    let _config = config;
    Sse::new(stream).keep_alive(
        KeepAlive::new()
            .interval(Duration::from_secs(15))
            .text("ping"),
    )
}

// ─── Main ────────────────────────────────────────────────────────────────────

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "hegemon_mcp=info".into()),
        )
        .json()
        .init();

    let config = Arc::new(AppConfig::from_env());
    let addr = SocketAddr::from(([0, 0, 0, 0], config.port));

    let app = Router::new()
        .route("/health", get(health))
        .route("/mcp/capabilities", get(capabilities))
        .route("/mcp/tools/list", post(tools_list))
        .route("/mcp/tools/call", post(tools_call))
        .route("/mcp/sse", get(sse_endpoint))
        .with_state(config.clone());

    info!(port = %addr.port(), "HEGEMON MCP Server v0 starting");

    let listener = tokio::net::TcpListener::bind(addr)
        .await
        .expect("Failed to bind");

    axum::serve(listener, app)
        .await
        .expect("Server failed");
}

// ─── Tests ───────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::Body;
    use axum::http::{Request, StatusCode};
    use tower::ServiceExt;

    fn test_app() -> Router {
        let config = Arc::new(AppConfig {
            port: 8092,
            pocketbase_url: "http://localhost:8090".to_string(),
            linear_api_key: None,
            linear_team_id: None,
            prometheus_url: "http://localhost:9090".to_string(),
        });

        Router::new()
            .route("/health", get(health))
            .route("/mcp/capabilities", get(capabilities))
            .route("/mcp/tools/list", post(tools_list))
            .route("/mcp/tools/call", post(tools_call))
            .route("/mcp/sse", get(sse_endpoint))
            .with_state(config)
    }

    #[tokio::test]
    async fn test_health() {
        let app = test_app();
        let resp = app
            .oneshot(Request::get("/health").body(Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_capabilities_returns_server_info() {
        let app = test_app();
        let resp = app
            .oneshot(Request::get("/mcp/capabilities").body(Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);

        let body = axum::body::to_bytes(resp.into_body(), 4096).await.unwrap();
        let caps: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(caps["server"]["name"], "hegemon-mcp");
        assert_eq!(caps["server"]["version"], "0.1.0");
        assert!(caps["capabilities"]["tools"].is_object());
    }

    #[tokio::test]
    async fn test_tools_list_returns_3_tools() {
        let app = test_app();
        let resp = app
            .oneshot(
                Request::post("/mcp/tools/list")
                    .header("content-type", "application/json")
                    .body(Body::from("{}"))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);

        let body = axum::body::to_bytes(resp.into_body(), 8192).await.unwrap();
        let tools: Vec<serde_json::Value> = serde_json::from_slice(&body).unwrap();
        assert_eq!(tools.len(), 3);

        let names: Vec<&str> = tools.iter().filter_map(|t| t["name"].as_str()).collect();
        assert!(names.contains(&"hegemon_workers_status"));
        assert!(names.contains(&"hegemon_cycle_status"));
        assert!(names.contains(&"hegemon_metrics"));
    }

    #[tokio::test]
    async fn test_unknown_tool_returns_error() {
        let app = test_app();
        let resp = app
            .oneshot(
                Request::post("/mcp/tools/call")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        r#"{"name":"nonexistent","arguments":{}}"#,
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);

        let body = axum::body::to_bytes(resp.into_body(), 4096).await.unwrap();
        let result: McpToolCallResponse = serde_json::from_slice(&body).unwrap();
        assert!(result.is_error);
        assert!(result.content[0].text.contains("Unknown tool"));
    }
}
