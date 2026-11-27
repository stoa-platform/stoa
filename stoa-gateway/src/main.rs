//! STOA Gateway - Main Entry Point
//!
//! MCP-native API Gateway bridging legacy systems to AI agents.

use std::net::{IpAddr, SocketAddr};
use tokio::net::TcpListener;
use tracing::{error, info, warn};
use tracing_subscriber::{fmt, prelude::*, EnvFilter};

/// TCP listen backlog size. Default Linux is 128 — too low for burst traffic
/// (100 concurrent VUs overflow SYN queue → 200ms+ retries).
/// 1024 matches nginx/envoy defaults.
const TCP_BACKLOG: i32 = 1024;

use stoa_gateway::config::{Config, ConfigError};
use stoa_gateway::control_plane::GatewayRegistrar;
use stoa_gateway::state::AppState;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Load configuration first (needed for OTel endpoint)
    let config = Config::load()?;
    config
        .validate()
        .map_err(|error| -> Box<dyn std::error::Error> {
            match error {
                ConfigError::StandaloneWithControlPlane => error.to_string().into(),
                _ => error.into(),
            }
        })?;

    // Resolve the HTTP listen address up front so an invalid STOA_HOST stops
    // startup before any background work begins (CAB-2681).
    let http_addr = bind_addr(&config.host, config.port)?;

    // Initialize tracing (with optional OTel export if configured)
    init_tracing(&config);

    info!(
        version = env!("CARGO_PKG_VERSION"),
        mode = ?config.gateway_mode,
        otel_enabled = config.otel_enabled,
        otel_endpoint = config.otel_endpoint.as_deref().unwrap_or("(none)"),
        otel_active = stoa_gateway::telemetry::is_otel_active(),
        "Starting STOA Gateway"
    );

    // Force-initialize all Prometheus metrics so they appear on /metrics
    // even before any traffic arrives (fixes: only rate_limit_buckets visible)
    stoa_gateway::metrics::init_all_metrics();

    // Initialize application state
    let state = AppState::new(config.clone());
    stoa_gateway::handlers::admin::restore_contracts(&state)
        .await
        .map_err(|error| format!("Could not restore contract snapshot: {error}"))?;

    if config.poc_agents_enabled {
        stoa_gateway::mcp::poc::load_poc_fixtures(&state)
            .await
            .map_err(|reason| format!("Failed to load autonomous PoC fixtures: {reason}"))?;
    }

    // SIGHUP handler for policy + route hot-reload (CAB-1109, CAB-1828)
    #[cfg(unix)]
    {
        let policy_engine = state.uac_enforcer.policy_engine().clone();
        let sighup_state = state.clone();
        tokio::spawn(async move {
            let mut sighup = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::hangup())
                .expect("Failed to install SIGHUP handler");
            loop {
                sighup.recv().await;
                info!("Received SIGHUP - reloading policies and routes");
                match policy_engine.reload() {
                    Ok(()) => info!("Policies reloaded successfully"),
                    Err(e) => error!(error = %e, "Policy reload failed"),
                }
                if sighup_state.config.route_reload_enabled && !sighup_state.config.standalone {
                    match stoa_gateway::handlers::admin::reload_routes_from_cp(&sighup_state).await
                    {
                        Ok(count) => {
                            stoa_gateway::metrics::record_route_reload("sighup", "success", count);
                            info!(routes = count, "Route table reloaded via SIGHUP");
                        }
                        Err(e) => {
                            stoa_gateway::metrics::record_route_reload("sighup", "error", 0);
                            error!(error = %e, "Route reload via SIGHUP failed");
                        }
                    }
                }
            }
        });
    }

    // Initialize mode-specific components
    init_mode_components(&config).await;

    let control_plane_url = config.normalized_control_plane_url();

    // Auto-register with Control Plane (ADR-028, CAB-1915)
    // Registration runs in background with retry so the gateway becomes visible
    // even if the CP API is not ready at startup (common in K8s).
    // The registrar is kept alive so api_bridge can read the assigned gateway_id (CAB-1940).
    let registrar: Option<std::sync::Arc<GatewayRegistrar>> = if config.auto_register
        && !config.standalone
    {
        match (control_plane_url, &config.control_plane_api_key) {
            (Some(cp_url), Some(api_key)) => {
                info!(
                    "Starting background registration with Control Plane: {}",
                    cp_url
                );
                let r =
                    std::sync::Arc::new(GatewayRegistrar::new(cp_url.to_string(), api_key.clone()));

                r.clone().start_registration_and_heartbeat(
                    config.clone(),
                    std::sync::Arc::new(state.clone()),
                    config.heartbeat_interval_secs,
                );
                Some(r)
            }
            (None, _) => {
                info!("Auto-registration skipped: STOA_CONTROL_PLANE_URL not set");
                None
            }
            (_, None) => {
                info!("Auto-registration skipped: STOA_CONTROL_PLANE_API_KEY not set");
                None
            }
        }
    } else {
        None
    };

    // Start background tasks
    state.start_background_tasks();

    // Initialize Kafka CNS event bridge (CAB-1178: push Kafka events to SSE clients)
    init_kafka_cns_consumer(&config, &state);

    // Initialize K8s CRD watcher (Phase 7: CAB-1105)
    init_k8s_watcher(&config, &state).await;

    // Register tools: try CP discovery, fallback to static
    // Pass registrar so API catalog discovery can scope by gateway_id (CAB-1940)
    register_tools(&state, registrar).await;

    info!(
        tools = state.tool_registry.count(),
        "Tool registry initialized"
    );

    // Pre-warm connection pool: establish TCP+TLS connections to Control Plane
    // before the first real request, so ramp_up traffic doesn't pay cold-start cost.
    if let Some(cp_url) = control_plane_url {
        prewarm_connections(cp_url).await;
    }

    // Bind before HTTP startup; a failed authorization bind aborts startup.
    let grpc = if let Some(addr) = config.ext_authz_grpc_addr {
        let jwt = state
            .jwt_validator
            .clone()
            .ok_or("ext_authz requires an OIDC JWT validator")?;
        if !addr.ip().is_loopback() {
            warn!(%addr, "ext_authz has no TLS; use a trusted private network");
        }
        if !matches!(
            tokio::time::timeout(
                std::time::Duration::from_millis(800),
                jwt.oidc_provider().get_jwks()
            )
            .await,
            Ok(Ok(_))
        ) {
            warn!("ext_authz JWKS prewarm failed; requests remain fail-closed");
        }
        let mut engine = stoa_gateway::mode::decision::DecisionEngine::new()
            .with_required_scopes(config.ext_authz_required_scopes.clone());
        if config.quota_enforcement_enabled {
            engine = engine.with_rate_limiter(state.consumer_rate_limiter.clone());
        }
        let service = stoa_gateway::authz::ext_authz_grpc::ExtAuthzService::new(
            jwt,
            config.ext_authz_audience.clone(),
            config.ext_authz_required_scopes.clone(),
            engine,
        );
        let listener = tokio::net::TcpListener::bind(addr).await?;
        let bound = listener.local_addr()?;
        info!(addr = %bound, "ext_authz gRPC listening");
        Some((listener, service))
    } else {
        None
    };
    let (mut health, health_service) = tonic_health::server::health_reporter();
    let ready = config
        .ext_authz_audience
        .as_deref()
        .is_some_and(|a| !a.trim().is_empty());
    let status = if ready {
        tonic_health::ServingStatus::Serving
    } else {
        tonic_health::ServingStatus::NotServing
    };
    health.set_service_status("", status).await;
    health
        .set_service_status("envoy.service.auth.v3.Authorization", status)
        .await;

    // Build router
    let app = stoa_gateway::build_router(state);

    // Start server with tuned TCP socket (CAB-1359 perf)
    let listener = create_tcp_listener(http_addr)?;
    let bound = listener.local_addr()?;
    info!(
        addr = %bound,
        backlog = TCP_BACKLOG,
        "STOA Gateway listening"
    );

    // HTTP server with idle/header deadlines and a connection cap. Requests carry
    // ConnectInfo<SocketAddr> (required by tcp_filter::pre_tls_filter for
    // IP-based filtering after accept).
    let limits = stoa_gateway::server::ServerLimits::from_config_values(
        config.http_idle_timeout_secs,
        config.http_header_read_timeout_secs,
        config.http_max_connections,
    );
    info!(
        idle_timeout_secs = config.http_idle_timeout_secs,
        header_read_timeout_secs = config.http_header_read_timeout_secs,
        max_connections = config.http_max_connections,
        "HTTP connection limits (0 = disabled)"
    );
    use futures::FutureExt;
    let shutdown = shutdown_signal().shared();
    let http_shutdown = shutdown.clone();
    let http = async {
        stoa_gateway::server::serve(listener, app, limits, http_shutdown).await?;
        Ok::<(), Box<dyn std::error::Error>>(())
    };
    let authorization = async {
        if let Some((listener, service)) = grpc {
            let shutdown_observer = shutdown.clone();
            use stoa_gateway::authz::proto::envoy::service::auth::v3::authorization_server::AuthorizationServer;
            tonic::transport::Server::builder()
                .add_service(health_service)
                .add_service(AuthorizationServer::new(service).max_decoding_message_size(64 * 1024))
                .serve_with_incoming_shutdown(
                    tokio_stream::wrappers::TcpListenerStream::new(listener),
                    shutdown,
                )
                .await?;
            if shutdown_observer.now_or_never().is_none() {
                return Err("ext_authz listener stopped before shutdown".into());
            }
        }
        Ok::<(), Box<dyn std::error::Error>>(())
    };
    // Both servers are supervised: any listener failure terminates the process.
    tokio::try_join!(http, authorization)?;

    // Flush pending OTel spans before exit
    stoa_gateway::telemetry::shutdown_telemetry();

    info!("STOA Gateway shutdown complete");
    Ok(())
}

/// Pre-warm the HTTP connection pool by sending throwaway requests to the Control Plane.
/// Establishes TCP connections before the first real request, avoiding cold-start latency
/// during burst traffic (Arena ramp_up scenario).
async fn prewarm_connections(cp_url: &str) {
    let health_url = format!("{}/health", cp_url);
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(3))
        .pool_max_idle_per_host(4)
        .build()
        .unwrap_or_default();

    for i in 1..=3 {
        match client.get(&health_url).send().await {
            Ok(_) => {
                info!(attempt = i, "Connection pool pre-warmed");
                break;
            }
            Err(e) => {
                warn!(attempt = i, error = %e, "Pre-warm connection failed (non-fatal)");
            }
        }
    }
}

/// Build the HTTP listen address from `STOA_HOST` and `STOA_PORT` (CAB-2681).
///
/// Only literal IPv4 or IPv6 addresses are accepted; hostnames are not resolved.
fn bind_addr(host: &str, port: u16) -> Result<SocketAddr, Box<dyn std::error::Error>> {
    let ip: IpAddr = host.parse().map_err(|_| {
        format!("STOA_HOST must be an IP address such as 0.0.0.0 or ::, got '{host}'")
    })?;
    Ok(SocketAddr::new(ip, port))
}

/// Create a TCP listener with tuned socket options for high-concurrency workloads.
///
/// - `SO_REUSEADDR`: allow immediate rebind after restart
/// - `SO_REUSEPORT`: kernel-level load balancing across threads (Linux 3.9+)
/// - Backlog 1024: prevent SYN queue overflow under burst traffic
///   (default 128 causes 200ms+ retries at 100 concurrent connections)
fn create_tcp_listener(addr: SocketAddr) -> Result<TcpListener, Box<dyn std::error::Error>> {
    use socket2::{Domain, Protocol, Socket, Type};

    let domain = if addr.is_ipv4() {
        Domain::IPV4
    } else {
        Domain::IPV6
    };

    let socket = Socket::new(domain, Type::STREAM, Some(Protocol::TCP))?;
    socket.set_reuse_address(true)?;

    // SO_REUSEPORT: available on Linux 3.9+ and macOS.
    // Enables kernel-level connection distribution across listeners.
    #[cfg(any(target_os = "linux", target_os = "macos"))]
    socket.set_reuse_port(true)?;

    socket.set_nonblocking(true)?;
    socket.bind(&addr.into())?;
    socket.listen(TCP_BACKLOG)?;

    let std_listener: std::net::TcpListener = socket.into();
    Ok(TcpListener::from_std(std_listener)?)
}

/// Initialize tracing subscriber with optional OpenTelemetry export.
///
/// CAB-1831: OTel is always compiled in. When `STOA_OTEL_ENDPOINT` is set,
/// spans are exported via OTLP. Otherwise, tracing works locally (no-op export).
fn init_tracing(config: &Config) {
    let filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new("info,stoa_gateway=debug"));

    // JSON formatter with service field for cross-component log correlation (CAB-1455)
    let fmt_layer = fmt::layer()
        .json()
        .with_target(true)
        .with_current_span(true);

    if config.otel_enabled {
        use stoa_gateway::telemetry::{init_telemetry_tracer, TelemetryConfig};

        let telem_config = TelemetryConfig {
            otlp_endpoint: config.otel_endpoint.clone(),
            sample_rate: config.otel_sample_rate,
            deployment_mode: config.gateway_mode.to_string(),
            ..TelemetryConfig::default()
        };
        if let Some(tracer) = init_telemetry_tracer(&telem_config) {
            let otel_layer = tracing_opentelemetry::layer().with_tracer(tracer);
            tracing_subscriber::registry()
                .with(filter)
                .with(fmt_layer)
                .with(otel_layer)
                .init();
            return;
        }
    }

    // OTel disabled: runtime toggle off, no endpoint, or init failed
    stoa_gateway::telemetry::init_telemetry_noop();
    tracing_subscriber::registry()
        .with(filter)
        .with(fmt_layer)
        .init();
}

/// Register MCP tools.
///
/// When a `GatewayRegistrar` is provided, the API catalog discovery uses the
/// assigned gateway_id to scope results to this gateway's assigned APIs (CAB-1940).
async fn register_tools(state: &AppState, registrar: Option<std::sync::Arc<GatewayRegistrar>>) {
    use stoa_gateway::mcp::tools::{api_bridge, stoa_tools};

    let Some(control_plane) = state.control_plane.as_ref() else {
        if state.config.allows_explicit_local_dev_access() && state.config.native_tools_enabled {
            let http_client = stoa_gateway::mcp::tools::native_tool::create_http_client();
            stoa_gateway::mcp::tools::native_tool::register_native_tools(
                &state.tool_registry,
                http_client,
                "",
                state.tool_registry.clone(),
                Some(state.session_manager.clone()),
                Some(state.circuit_breakers.clone()),
                Some(state.prompt_cache.clone()),
            );
            info!("Control Plane not configured — registered native tool catalog for explicit local dev");
        } else {
            info!(
                "Control Plane not configured — skipping Control Plane tool and catalog discovery"
            );
        }
        return;
    };

    if state.config.native_tools_enabled {
        info!("Native tools enabled (direct CP API calls)");
        match stoa_tools::discover_and_register(
            state.tool_registry.clone(),
            control_plane,
            state.cp_circuit_breaker.clone(),
            Some(state.session_manager.clone()),
            Some(state.circuit_breakers.clone()),
            Some(state.prompt_cache.clone()),
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
        stoa_tools::register_static_tools(&state.tool_registry, control_plane.clone());
    }

    // Background refresh: sync tools from CP every 60s
    stoa_tools::start_tool_refresh_task(
        state.tool_registry.clone(),
        control_plane.clone(),
        state.cp_circuit_breaker.clone(),
    );

    // Discover published APIs from CP catalog and register as MCP tools
    // Sidecar is an ext_authz enforcer, Shadow is passive capture — neither needs discovery (CAB-1949)
    if state.config.gateway_mode.supports_discovery() {
        let cp_url = control_plane.base_url().to_string();
        let http_client = stoa_gateway::mcp::tools::native_tool::create_http_client();

        let expansion_mode = state.config.tool_expansion_mode;
        let gw_id = match registrar.as_ref() {
            Some(r) => r.gateway_id().await,
            None => None,
        };

        if registrar.is_some() && gw_id.is_none() {
            info!("Skipping API catalog discovery until gateway registration completes");
        } else {
            let discovery = match expansion_mode {
                stoa_gateway::config::ExpansionMode::Coarse => {
                    api_bridge::discover_api_tools(
                        &state.tool_registry,
                        &cp_url,
                        &http_client,
                        gw_id,
                        state.config.control_plane_api_key.as_deref(),
                    )
                    .await
                }
                stoa_gateway::config::ExpansionMode::PerOp => {
                    api_bridge::discover_expanded_api_tools_with_credentials(
                        &state.tool_registry,
                        &cp_url,
                        &http_client,
                        gw_id,
                        state.config.control_plane_api_key.as_deref(),
                        Some(&state.credential_store),
                    )
                    .await
                }
            };
            match discovery {
                Ok(count) => {
                    if count > 0 {
                        info!(count, mode = ?expansion_mode, "API catalog tools registered");
                    }
                }
                Err(e) => {
                    warn!(error = %e, mode = ?expansion_mode, "API catalog discovery failed (will retry in background)");
                }
            }
        }

        // Background refresh: sync API catalog tools every 60s
        // Passes registrar so each tick reads the current gateway_id (CAB-1940)
        api_bridge::start_api_tool_refresh_task(
            state.tool_registry.clone(),
            cp_url,
            http_client,
            registrar,
            expansion_mode,
            state.config.control_plane_api_key.clone(),
            Some(state.credential_store.clone()),
        );
    } else {
        info!(mode = %state.config.gateway_mode, "Skipping API catalog discovery (sidecar/shadow mode)");
    }
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

/// Initialize Kafka CNS event bridge (CAB-1178: Kafka -> SSE push via NotificationBus)
fn init_kafka_cns_consumer(config: &Config, state: &AppState) {
    if !config.kafka_cns_enabled {
        info!("Kafka CNS event bridge disabled (STOA_KAFKA_CNS_ENABLED=false)");
        return;
    }

    if !config.kafka_enabled {
        warn!("Kafka CNS enabled but Kafka brokers not configured (STOA_KAFKA_ENABLED=false) -- skipping");
        return;
    }

    let brokers = config.kafka_brokers.clone();
    let topics = config.kafka_cns_topics.clone();
    let group_id = config.kafka_cns_consumer_group.clone();
    let session_manager = stoa_gateway::mcp::session::SessionManager::clone(&state.session_manager);

    stoa_gateway::events::consumer::start_cns_consumer(
        &brokers,
        &topics,
        &group_id,
        session_manager,
        state.event_buffer.clone(),
    );
    info!(
        brokers = %config.kafka_brokers,
        topics = %config.kafka_cns_topics,
        group = %config.kafka_cns_consumer_group,
        "Kafka CNS event bridge started"
    );
}

/// Initialize K8s CRD watcher for dynamic tool registration (Phase 7: CAB-1105)
async fn init_k8s_watcher(config: &Config, _state: &AppState) {
    if !config.k8s_enabled {
        info!("K8s CRD watcher disabled (STOA_K8S_ENABLED=false)");
        return;
    }

    #[cfg(feature = "k8s")]
    {
        info!("Initializing K8s CRD watcher for dynamic tool registration");
        match kube::Client::try_default().await {
            Ok(client) => {
                let watcher = stoa_gateway::k8s::CrdWatcher::new(
                    client,
                    _state.tool_registry.clone(),
                    _state.skill_resolver.clone(),
                    _state.session_manager.clone(),
                    _state.guardrail_policy_store.clone(),
                )
                .with_credential_store(_state.credential_store.clone());
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

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::{Ipv4Addr, Ipv6Addr};

    #[tokio::test]
    async fn regression_loopback_host_binds_loopback_ipv4() {
        let addr = bind_addr("127.0.0.1", 0).expect("loopback host is valid");
        assert_eq!(addr.ip(), IpAddr::V4(Ipv4Addr::LOCALHOST));

        let listener = create_tcp_listener(addr).expect("bind on loopback");
        let bound = listener.local_addr().expect("bound address");
        assert_eq!(bound.ip(), IpAddr::V4(Ipv4Addr::LOCALHOST));
        assert_ne!(bound.port(), 0);
        drop(listener);
    }

    #[test]
    fn regression_non_ip_host_is_rejected() {
        for host in ["not-an-ip", "localhost", "", "0.0.0.0:8080"] {
            let error = bind_addr(host, 8080).expect_err(host);
            assert!(
                error.to_string().contains(&format!("'{host}'")),
                "error should name the invalid value: {error}"
            );
        }
    }

    #[test]
    fn regression_default_host_is_unspecified_ipv4() {
        let config = Config::default();
        let addr = bind_addr(&config.host, config.port).expect("default host is valid");
        assert_eq!(addr.ip(), IpAddr::V4(Ipv4Addr::UNSPECIFIED));
        assert_eq!(addr.port(), config.port);
    }

    #[test]
    fn regression_ipv6_hosts_are_accepted() {
        let loopback = bind_addr("::1", 8080).expect("IPv6 loopback is valid");
        assert_eq!(loopback.ip(), IpAddr::V6(Ipv6Addr::LOCALHOST));

        let any = bind_addr("::", 8080).expect("IPv6 unspecified is valid");
        assert_eq!(any.ip(), IpAddr::V6(Ipv6Addr::UNSPECIFIED));
    }
}
