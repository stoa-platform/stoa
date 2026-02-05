//! STOA Gateway - Main Entry Point
//!
//! MCP-native API Gateway bridging legacy systems to AI agents.

use axum::{
    routing::{delete, get, post},
    Router,
};
use std::net::SocketAddr;
use tokio::net::TcpListener;
use tracing::{info, warn};
use tracing_subscriber::{fmt, prelude::*, EnvFilter};

mod auth;
mod config;
mod control_plane;
mod governance;
mod handlers;
mod mcp;
mod metrics;
mod mode;
mod oauth;
mod policy;
mod proxy;
mod rate_limit;
mod routes;
mod shadow;
mod state;
mod uac;

use config::Config;
use control_plane::GatewayRegistrar;
use handlers::admin;
use mcp::{
    discovery::{mcp_capabilities, mcp_discovery, mcp_health},
    handlers::{mcp_tools_call, mcp_tools_list},
    sse::{handle_sse_delete, handle_sse_get, handle_sse_post},
};
use proxy::dynamic_proxy;
use state::AppState;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Load configuration first (needed for OTel endpoint)
    let config = Config::load()?;
    config.validate()?;

    // Initialize tracing (with optional OTel export if configured)
    init_tracing(&config);

    info!(
        version = env!("CARGO_PKG_VERSION"),
        mode = ?config.gateway_mode,
        "Starting STOA Gateway"
    );

    // Initialize application state
    let state = AppState::new(config.clone());

    // Initialize mode-specific components
    init_mode_components(&config).await;

    // Auto-register with Control Plane (ADR-028)
    if config.auto_register {
        if let Some(cp_url) = &config.control_plane_url {
            if let Some(api_key) = &config.control_plane_api_key {
                info!("Auto-registering with Control Plane: {}", cp_url);
                let registrar = std::sync::Arc::new(GatewayRegistrar::new(
                    cp_url.clone(),
                    api_key.clone(),
                ));

                match registrar.register(&config).await {
                    Ok(id) => {
                        info!(gateway_id = %id, "Registered with Control Plane");
                        // Start heartbeat background task
                        registrar.start_heartbeat(
                            std::sync::Arc::new(state.clone()),
                            config.heartbeat_interval_secs,
                        );
                    }
                    Err(e) => {
                        warn!(error = %e, "Failed to register with Control Plane — running in standalone mode");
                    }
                }
            } else {
                info!("Auto-registration skipped: STOA_CONTROL_PLANE_API_KEY not set");
            }
        } else {
            info!("Auto-registration skipped: STOA_CONTROL_PLANE_URL not set");
        }
    }

    // Start background tasks
    state.start_background_tasks();

    // Register tools: try CP discovery, fallback to static
    register_tools(&state).await;

    info!(
        tools = state.tool_registry.count(),
        "Tool registry initialized"
    );

    // Build router
    let app = build_router(state);

    // Start server
    let addr = SocketAddr::from(([0, 0, 0, 0], config.port));
    info!(addr = %addr, "STOA Gateway listening");

    let listener = TcpListener::bind(addr).await?;
    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await?;

    // TODO: Flush OTel spans once OpenTelemetry API is stabilized
    // opentelemetry::global::shutdown_tracer_provider();

    info!("STOA Gateway shutdown complete");
    Ok(())
}

/// Initialize tracing subscriber with optional OpenTelemetry export.
///
/// When `config.otel_endpoint` is set, spans are exported via OTLP gRPC
/// to Grafana Alloy, enabling distributed tracing with Tempo and
/// automatic Service Map generation in Grafana.
fn init_tracing(config: &Config) {
    let filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new("info,stoa_gateway=debug"));

    let fmt_layer = fmt::layer().json();

    if config.otel_endpoint.is_some() {
        // TODO: Re-enable OTel tracing once opentelemetry 0.27 API is stabilized.
        // The current opentelemetry_sdk 0.27 changed SdkTracerProvider/Resource APIs.
        // For now, use plain tracing subscriber and log a warning.
        warn!(
            "STOA_OTEL_ENDPOINT set but OTel export not yet available — using local tracing only"
        );
    }

    tracing_subscriber::registry()
        .with(filter)
        .with(fmt_layer)
        .init();
}

/// Build the Axum router with all routes
fn build_router(state: AppState) -> Router {
    // Admin API (protected by bearer token)
    let admin_router = Router::new()
        .route("/health", get(admin::admin_health))
        .route("/apis", get(admin::list_apis).post(admin::upsert_api))
        .route("/apis/:id", get(admin::get_api).delete(admin::delete_api))
        .route(
            "/policies",
            get(admin::list_policies).post(admin::upsert_policy),
        )
        .route("/policies/:id", delete(admin::delete_policy))
        .layer(axum::middleware::from_fn_with_state(
            state.clone(),
            admin::admin_auth,
        ));

    Router::new()
        // Health & Metrics
        .route("/health", get(health))
        .route("/ready", get(ready))
        .route("/metrics", get(prometheus_metrics))
        // OAuth Discovery + Proxy (RFC 9728, RFC 8414, OIDC, DCR)
        .route(
            "/.well-known/oauth-protected-resource",
            get(oauth::discovery::protected_resource_metadata),
        )
        .route(
            "/.well-known/oauth-authorization-server",
            get(oauth::discovery::authorization_server_metadata),
        )
        .route(
            "/.well-known/openid-configuration",
            get(oauth::discovery::openid_configuration),
        )
        .route("/oauth/token", post(oauth::proxy::token_proxy))
        .route("/oauth/register", post(oauth::proxy::register_proxy))
        // MCP Discovery
        .route("/mcp", get(mcp_discovery))
        .route("/mcp/capabilities", get(mcp_capabilities))
        .route("/mcp/health", get(mcp_health))
        // MCP Tools (REST-style for backward compat)
        .route("/mcp/tools/list", post(mcp_tools_list))
        .route("/mcp/tools/call", post(mcp_tools_call))
        // MCP SSE Transport (Streamable HTTP)
        .route(
            "/mcp/sse",
            get(handle_sse_get)
                .post(handle_sse_post)
                .delete(handle_sse_delete),
        )
        // Admin API (Control Plane → Gateway)
        .nest("/admin", admin_router)
        // Dynamic proxy fallback — must be LAST
        .fallback(dynamic_proxy)
        // Add state
        .with_state(state)
}

/// Register MCP tools.
///
/// 1. Try dynamic discovery from Control Plane (no rebuild needed)
/// 2. Fallback to static definitions if CP is unreachable
/// 3. Start background refresh task to pick up CP changes
async fn register_tools(state: &AppState) {
    use mcp::tools::stoa_tools;

    match stoa_tools::discover_and_register(&state.tool_registry, &state.control_plane).await {
        Ok(count) => {
            info!(count, "Tools discovered from Control Plane");
        }
        Err(e) => {
            info!(error = %e, "CP unreachable — using static tool definitions");
            stoa_tools::register_static_tools(&state.tool_registry, state.control_plane.clone());
        }
    }

    // Background refresh: sync tools from CP every 60s
    stoa_tools::start_tool_refresh_task(state.tool_registry.clone(), state.control_plane.clone());
}

// === Health Endpoints ===

async fn health() -> &'static str {
    "OK"
}

async fn ready() -> &'static str {
    // TODO: Check dependencies (DB, Control Plane, etc.)
    "READY"
}

async fn prometheus_metrics() -> String {
    use prometheus::Encoder;
    let encoder = prometheus::TextEncoder::new();
    let metric_families = prometheus::gather();
    let mut buffer = Vec::new();
    encoder.encode(&metric_families, &mut buffer).unwrap();
    String::from_utf8(buffer).unwrap()
}

// === Graceful Shutdown ===

async fn shutdown_signal() {
    let ctrl_c = async {
        tokio::signal::ctrl_c()
            .await
            .expect("Failed to install Ctrl+C handler");
    };

    #[cfg(unix)]
    let terminate = async {
        tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
            .expect("Failed to install SIGTERM handler")
            .recv()
            .await;
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        _ = ctrl_c => info!("Received Ctrl+C, initiating shutdown..."),
        _ = terminate => info!("Received SIGTERM, initiating shutdown..."),
    }
}

// === Mode-Specific Initialization ===

/// Initialize components specific to the gateway mode
async fn init_mode_components(config: &Config) {
    use mode::GatewayMode;

    match config.gateway_mode {
        GatewayMode::EdgeMcp => {
            info!("Mode: EdgeMcp - MCP protocol with SSE transport");
            // EdgeMcp is the default mode, core router handles it
        }
        GatewayMode::Sidecar => {
            info!("Mode: Sidecar - Policy enforcement behind existing gateway");
            // TODO: Start ext_authz gRPC server for Envoy integration
        }
        GatewayMode::Proxy => {
            info!("Mode: Proxy - Inline request/response transformation");
            // TODO: Initialize route registry from config
        }
        GatewayMode::Shadow => {
            info!("Mode: Shadow - Passive traffic capture and analysis");
            // TODO: Start traffic capture based on shadow_capture_source
            // TODO: Initialize pattern analyzer
            // TODO: Start UAC generator
        }
    }

    // Initialize governance (anti-zombie detection) if enabled
    if config.zombie_detection_enabled {
        info!(
            ttl_secs = config.agent_session_ttl_secs,
            attestation_interval = config.attestation_interval,
            "Agent governance enabled (ADR-012)"
        );
    }
}
