//! STOA Gateway - Main Entry Point
//!
//! MCP-native API Gateway bridging legacy systems to AI agents.

use std::net::SocketAddr;
use tokio::net::TcpListener;
use tracing::{error, info, warn};
use tracing_subscriber::{fmt, prelude::*, EnvFilter};

use stoa_gateway::config::Config;
use stoa_gateway::control_plane::GatewayRegistrar;
use stoa_gateway::state::AppState;

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

    // Force-initialize all Prometheus metrics so they appear on /metrics
    // even before any traffic arrives (fixes: only rate_limit_buckets visible)
    stoa_gateway::metrics::init_all_metrics();

    // Initialize application state
    let state = AppState::new(config.clone());

    // SIGHUP handler for policy hot-reload (CAB-1109)
    #[cfg(unix)]
    {
        let policy_engine = state.uac_enforcer.policy_engine().clone();
        tokio::spawn(async move {
            let mut sighup = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::hangup())
                .expect("Failed to install SIGHUP handler");
            loop {
                sighup.recv().await;
                info!("Received SIGHUP - reloading policies");
                match policy_engine.reload() {
                    Ok(()) => info!("Policies reloaded successfully"),
                    Err(e) => error!(error = %e, "Policy reload failed"),
                }
            }
        });
    }

    // Initialize mode-specific components
    init_mode_components(&config).await;

    // Auto-register with Control Plane (ADR-028)
    if config.auto_register {
        if let Some(cp_url) = &config.control_plane_url {
            if let Some(api_key) = &config.control_plane_api_key {
                info!("Auto-registering with Control Plane: {}", cp_url);
                let registrar =
                    std::sync::Arc::new(GatewayRegistrar::new(cp_url.clone(), api_key.clone()));

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

    // Initialize K8s CRD watcher (Phase 7: CAB-1105)
    init_k8s_watcher(&config, &state).await;

    // Register tools: try CP discovery, fallback to static
    register_tools(&state).await;

    info!(
        tools = state.tool_registry.count(),
        "Tool registry initialized"
    );

    // Build router
    let app = stoa_gateway::build_router(state);

    // Start server
    let addr = SocketAddr::from(([0, 0, 0, 0], config.port));
    info!(addr = %addr, "STOA Gateway listening");

    let listener = TcpListener::bind(addr).await?;
    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await?;

    info!("STOA Gateway shutdown complete");
    Ok(())
}

/// Initialize tracing subscriber with optional OpenTelemetry export.
fn init_tracing(config: &Config) {
    let filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new("info,stoa_gateway=debug"));

    let fmt_layer = fmt::layer().json();

    if config.otel_endpoint.is_some() {
        warn!(
            "STOA_OTEL_ENDPOINT set but OTel export not yet available — using local tracing only"
        );
    }

    tracing_subscriber::registry()
        .with(filter)
        .with(fmt_layer)
        .init();
}

/// Register MCP tools.
async fn register_tools(state: &AppState) {
    use stoa_gateway::mcp::tools::{api_bridge, stoa_tools};

    if state.config.native_tools_enabled {
        info!("Native tools enabled (direct CP API calls)");
        match stoa_tools::discover_and_register(
            state.tool_registry.clone(),
            &state.control_plane,
            state.cp_circuit_breaker.clone(),
        )
        .await
        {
            Ok(count) => {
                info!(count, "Tools registered (native mode)");
            }
            Err(e) => {
                warn!(error = %e, "CP unreachable — native tools only");
            }
        }
    } else {
        info!("Native tools DISABLED (STOA_NATIVE_TOOLS_ENABLED=false) — using proxy mode");
        stoa_tools::register_static_tools(&state.tool_registry, state.control_plane.clone());
    }

    // Discover published APIs from CP catalog and register as MCP tools
    let cp_url = state.control_plane.base_url().to_string();
    let http_client = stoa_gateway::mcp::tools::native_tool::create_http_client();
    match api_bridge::discover_api_tools(&state.tool_registry, &cp_url, &http_client).await {
        Ok(count) => {
            if count > 0 {
                info!(count, "API catalog tools registered");
            }
        }
        Err(e) => {
            warn!(error = %e, "API catalog discovery failed (will retry in background)");
        }
    }

    // Background refresh: sync tools from CP every 60s
    stoa_tools::start_tool_refresh_task(
        state.tool_registry.clone(),
        state.control_plane.clone(),
        state.cp_circuit_breaker.clone(),
    );

    // Background refresh: sync API catalog tools every 60s
    api_bridge::start_api_tool_refresh_task(state.tool_registry.clone(), cp_url, http_client);
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

/// Initialize K8s CRD watcher for dynamic tool registration (Phase 7: CAB-1105)
#[allow(unused_variables)]
async fn init_k8s_watcher(config: &Config, state: &AppState) {
    if !config.k8s_enabled {
        info!("K8s CRD watcher disabled (STOA_K8S_ENABLED=false)");
        return;
    }

    #[cfg(feature = "k8s")]
    {
        info!("Initializing K8s CRD watcher for dynamic tool registration");
        match kube::Client::try_default().await {
            Ok(client) => {
                let watcher =
                    stoa_gateway::k8s::CrdWatcher::new(client, state.tool_registry.clone());
                tokio::spawn(async move {
                    watcher.start().await;
                });
                info!("K8s CRD watcher started");
            }
            Err(e) => {
                warn!(
                    error = %e,
                    "K8s client initialization failed — CRD watcher disabled (gateway continues)"
                );
            }
        }
    }

    #[cfg(not(feature = "k8s"))]
    {
        warn!(
            "K8s CRD watcher requested but 'k8s' feature not enabled — compile with --features k8s"
        );
    }
}

/// Initialize components specific to the gateway mode.
async fn init_mode_components(config: &Config) {
    use stoa_gateway::mode::GatewayMode;

    match config.gateway_mode {
        GatewayMode::EdgeMcp => {
            info!("Mode: EdgeMcp - MCP protocol with SSE transport");
        }
        GatewayMode::Sidecar => {
            info!("Mode: Sidecar - Policy enforcement behind existing gateway");
            info!("Sidecar routes: POST /authz (ext_authz compatible)");
        }
        GatewayMode::Proxy => {
            info!("Mode: Proxy - Inline request/response transformation");
            info!("Proxy mode: configure routes via admin API or STOA_PROXY_ROUTES");
        }
        GatewayMode::Shadow => {
            info!("Mode: Shadow - Passive traffic capture and analysis");
            info!("Shadow routes: GET /shadow/status, POST /shadow/generate");
        }
    }

    if config.zombie_detection_enabled {
        info!(
            ttl_secs = config.agent_session_ttl_secs,
            attestation_interval = config.attestation_interval,
            "Agent governance enabled (ADR-012)"
        );
    }
}
