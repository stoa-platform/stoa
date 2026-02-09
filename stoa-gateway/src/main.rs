//! STOA Gateway - Main Entry Point
//!
//! MCP-native API Gateway bridging legacy systems to AI agents.

use axum::{
    routing::{delete, get, post},
    Router,
};
use std::net::SocketAddr;
use tokio::net::TcpListener;
use tracing::{error, info, warn};
use tracing_subscriber::{fmt, prelude::*, EnvFilter};

mod auth;
mod cache;
mod config;
mod control_plane;
mod federation;
mod git;
mod governance;
mod handlers;
mod k8s;
mod mcp;
mod metering;
mod metrics;
mod mode;
mod oauth;
mod optimization;
mod policy;
mod proxy;
mod quota;
mod rate_limit;
mod resilience;
mod routes;
mod shadow;
mod state;
mod telemetry;
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

    // Kafka metering is now initialized inside AppState::new() (Phase 3: CAB-1105)

    // Initialize K8s CRD watcher (Phase 7: CAB-1105)
    init_k8s_watcher(&config, &state).await;

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

/// Build the Axum router with all routes.
///
/// Phase 8: Router is built based on gateway mode (ADR-024).
/// - EdgeMcp: Full MCP protocol, SSE transport, tool execution (default)
/// - Sidecar: Policy enforcement only (ext_authz style)
/// - Proxy: Inline proxy with request/response transformation
/// - Shadow: Passive traffic capture and UAC generation
fn build_router(state: AppState) -> Router {
    use mode::GatewayMode;

    // Admin API (shared across all modes)
    let admin_router = Router::new()
        .route("/health", get(admin::admin_health))
        .route("/apis", get(admin::list_apis).post(admin::upsert_api))
        .route("/apis/:id", get(admin::get_api).delete(admin::delete_api))
        .route(
            "/policies",
            get(admin::list_policies).post(admin::upsert_policy),
        )
        .route("/policies/:id", delete(admin::delete_policy))
        // Phase 6: Circuit Breaker admin
        .route("/circuit-breaker/stats", get(admin::circuit_breaker_stats))
        .route("/circuit-breaker/reset", post(admin::circuit_breaker_reset))
        // Phase 6: Cache admin
        .route("/cache/stats", get(admin::cache_stats))
        .route("/cache/clear", post(admin::cache_clear))
        // CAB-362: Session stats + per-upstream circuit breakers
        .route("/sessions/stats", get(admin::session_stats))
        .route("/circuit-breakers", get(admin::circuit_breakers_list))
        .route(
            "/circuit-breakers/:name/reset",
            post(admin::circuit_breaker_reset_by_name),
        )
        // CAB-864: mTLS admin
        .route("/mtls/config", get(admin::mtls_config))
        .route("/mtls/stats", get(admin::mtls_stats))
        // CAB-1121 P4: Quota enforcement admin
        .route("/quotas", get(admin::list_quotas))
        .route("/quotas/:consumer_id", get(admin::get_consumer_quota))
        .route(
            "/quotas/:consumer_id/reset",
            post(admin::reset_consumer_quota),
        )
        .layer(axum::middleware::from_fn_with_state(
            state.clone(),
            admin::admin_auth,
        ));

    // Common routes for all modes: health, metrics, admin
    let base = Router::new()
        .route("/health", get(health))
        .route("/ready", get(ready))
        .route("/metrics", get(prometheus_metrics))
        .nest("/admin", admin_router);

    // Build mTLS extraction layer (CAB-864)
    // Stage 1: runs BEFORE JWT auth — extracts cert info from headers
    let mtls_config = state.config.mtls.clone();
    let mtls_stats = state.mtls_stats.clone();
    let mtls_layer = axum::middleware::from_fn(move |request, next| {
        let config = mtls_config.clone();
        let stats = mtls_stats.clone();
        auth::mtls::mtls_extraction_middleware(config, stats, request, next)
    });

    match state.config.gateway_mode {
        GatewayMode::EdgeMcp => {
            // Full MCP protocol: OAuth discovery, MCP tools, SSE transport
            base
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
                // Dynamic proxy fallback — must be LAST
                .fallback(dynamic_proxy)
                // Quota enforcement: runs after auth, before handlers (CAB-1121 P4)
                .layer(axum::middleware::from_fn_with_state(
                    state.clone(),
                    quota::quota_middleware,
                ))
                // mTLS extraction: Stage 1 runs before JWT auth (CAB-864)
                .layer(mtls_layer)
                .with_state(state)
        }
        GatewayMode::Sidecar => {
            // Sidecar: policy enforcement, ext_authz style
            let sidecar_settings = mode::SidecarSettings::from_env();
            let sidecar_service =
                std::sync::Arc::new(mode::sidecar::SidecarService::new(sidecar_settings));

            // Use closure to capture sidecar service (avoids state type mismatch)
            let svc = sidecar_service.clone();
            base.route(
                "/authz",
                post(
                    move |axum::Json(request): axum::Json<mode::sidecar::AuthzRequest>| {
                        let svc = svc.clone();
                        async move {
                            let response = svc.authorize(request).await;
                            svc.format_response(response)
                        }
                    },
                ),
            )
            .with_state(state)
        }
        GatewayMode::Proxy => {
            // Proxy: inline request/response transformation
            let proxy_settings = mode::ProxySettings::from_env();
            let proxy_routes = mode::proxy::RouteRegistry::new();
            let proxy_service =
                std::sync::Arc::new(mode::proxy::ProxyService::new(proxy_settings, proxy_routes));

            // Use closure to capture proxy service as fallback handler
            let svc = proxy_service.clone();
            base.fallback(move |request: axum::http::Request<axum::body::Body>| {
                let svc = svc.clone();
                async move {
                    use axum::response::IntoResponse;
                    match svc.handle(request).await {
                        Ok(response) => response,
                        Err(e) => {
                            warn!(error = %e, "Proxy error");
                            axum::http::StatusCode::BAD_GATEWAY.into_response()
                        }
                    }
                }
            })
            .with_state(state)
        }
        GatewayMode::Shadow => {
            // Shadow: passive traffic capture and UAC generation
            let shadow_settings = mode::ShadowSettings::from_env();

            // Build GitClient if GitLab is configured (CAB-1109 Phase 5)
            let shadow_service = if let (Some(api_url), Some(token), Some(project_id)) = (
                &state.config.gitlab_api_url,
                &state.config.gitlab_token,
                &state.config.gitlab_project_id,
            ) {
                use crate::git::{GitClient, GitClientConfig};
                match GitClient::new(GitClientConfig {
                    api_url: api_url.clone(),
                    project_id: project_id.clone(),
                    token: token.clone(),
                    ..GitClientConfig::default()
                }) {
                    Ok(client) => {
                        info!("Shadow mode: GitLab client configured for UAC MR submission");
                        std::sync::Arc::new(mode::shadow::ShadowService::with_git_client(
                            shadow_settings,
                            std::sync::Arc::new(client),
                        ))
                    }
                    Err(e) => {
                        warn!(error = %e, "Shadow mode: GitLab client init failed, MR submission disabled");
                        std::sync::Arc::new(mode::shadow::ShadowService::new(shadow_settings))
                    }
                }
            } else {
                info!("Shadow mode: GitLab not configured, MR submission disabled");
                std::sync::Arc::new(mode::shadow::ShadowService::new(shadow_settings))
            };

            let svc_status = shadow_service.clone();
            let svc_generate = shadow_service.clone();
            let svc_submit = shadow_service.clone();

            base.route(
                "/shadow/status",
                get(move || {
                    let svc = svc_status.clone();
                    async move {
                        let status = svc.status().await;
                        axum::Json(status)
                    }
                }),
            )
            .route(
                "/shadow/generate",
                post(move || {
                    let svc = svc_generate.clone();
                    async move {
                        match svc
                            .generate_uac("shadow-api", "https://api.example.com")
                            .await
                        {
                            Some(uac) => axum::Json(
                                serde_json::json!({"status": "generated", "api_id": uac.api_id}),
                            ),
                            None => axum::Json(serde_json::json!({"status": "insufficient_data"})),
                        }
                    }
                }),
            )
            .route(
                "/shadow/submit-uac",
                post(
                    move |axum::Json(req): axum::Json<mode::shadow::SubmitUacRequest>| {
                        let svc = svc_submit.clone();
                        async move {
                            use axum::http::StatusCode;
                            use axum::response::IntoResponse;

                            match svc.submit_uac_to_git(req).await {
                                Ok(result) => axum::Json(serde_json::json!(result)).into_response(),
                                Err(e) => {
                                    let error_msg = e.to_string();
                                    (
                                        StatusCode::SERVICE_UNAVAILABLE,
                                        axum::Json(serde_json::json!({
                                            "success": false,
                                            "error": error_msg
                                        })),
                                    )
                                        .into_response()
                                }
                            }
                        }
                    },
                ),
            )
            .with_state(state)
        }
    }
}

/// Register MCP tools.
///
/// Phase 1: Native tools call CP API directly (STOA_NATIVE_TOOLS_ENABLED=true, default)
/// Legacy: ProxyTool calls Python mcp-gateway (STOA_NATIVE_TOOLS_ENABLED=false)
async fn register_tools(state: &AppState) {
    use mcp::tools::stoa_tools;

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

    // Background refresh: sync tools from CP every 60s (Phase 6: with circuit breaker)
    stoa_tools::start_tool_refresh_task(
        state.tool_registry.clone(),
        state.control_plane.clone(),
        state.cp_circuit_breaker.clone(),
    );
}

// === Health Endpoints ===

async fn health() -> &'static str {
    "OK"
}

async fn ready(
    axum::extract::State(state): axum::extract::State<AppState>,
) -> axum::response::Response {
    use axum::http::StatusCode;
    use axum::response::IntoResponse;

    // Check Control Plane connectivity (non-blocking, short timeout)
    if let Some(cp_url) = &state.config.control_plane_url {
        let health_url = format!("{}/health", cp_url);
        let client = reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(3))
            .build()
            .unwrap_or_default();
        match client.get(&health_url).send().await {
            Ok(resp) if resp.status().is_success() => {}
            Ok(resp) => {
                warn!(status = %resp.status(), "Control Plane health check returned non-200");
                return (
                    StatusCode::SERVICE_UNAVAILABLE,
                    "NOT READY: Control Plane unhealthy",
                )
                    .into_response();
            }
            Err(e) => {
                warn!(error = %e, "Control Plane unreachable");
                return (
                    StatusCode::SERVICE_UNAVAILABLE,
                    "NOT READY: Control Plane unreachable",
                )
                    .into_response();
            }
        }
    }

    // Check JWKS is reachable (if auth is enabled)
    if let Some(ref jwt) = state.jwt_validator {
        match jwt.oidc_provider().get_config().await {
            Ok(_) => {}
            Err(e) => {
                warn!(error = %e, "OIDC provider unreachable");
                return (
                    StatusCode::SERVICE_UNAVAILABLE,
                    "NOT READY: OIDC provider unreachable",
                )
                    .into_response();
            }
        }
    }

    (StatusCode::OK, "READY").into_response()
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

/// Initialize K8s CRD watcher for dynamic tool registration (Phase 7: CAB-1105)
///
/// Graceful degradation: if K8s is not available, the gateway continues without
/// dynamic tool registration. Tools can still be registered via CP discovery.
#[allow(unused_variables)] // state used only when k8s feature enabled
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
                let watcher = k8s::CrdWatcher::new(client, state.tool_registry.clone());
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

// === Mode-Specific Initialization ===

/// Initialize components specific to the gateway mode.
///
/// Phase 8 (CAB-1105): Mode-specific initialization is now a log + validation step.
/// Actual service creation happens in `build_router()` where axum state is set up.
async fn init_mode_components(config: &Config) {
    use mode::GatewayMode;

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

    // Initialize governance (anti-zombie detection) if enabled
    if config.zombie_detection_enabled {
        info!(
            ttl_secs = config.agent_session_ttl_secs,
            attestation_interval = config.attestation_interval,
            "Agent governance enabled (ADR-012)"
        );
    }
}
