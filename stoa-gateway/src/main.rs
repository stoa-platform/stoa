// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
use anyhow::Result;
use axum::{
    routing::{any, get},
    Router,
};
use std::net::SocketAddr;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;
use tokio::net::TcpListener;
use tokio::signal;
use tokio::sync::broadcast;
use tower_http::trace::TraceLayer;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

mod auth;
mod config;
mod control_plane;
mod git;
mod handlers;
mod health;
mod mcp;
mod metrics;
mod proxy;
mod rate_limit;
mod router;
mod uac;

use auth::{AuthBuilder, AuthComponents, RbacPolicy};
use config::Config;
use handlers::{health_live, health_ready, health_startup, metrics_handler, AppState};
use health::HealthChecker;
use mcp::handlers::{mcp_router, mcp_router_with_auth, McpState};
use mcp::tools::ToolRegistry;
use metrics::Metrics;
use router::{shadow_route_request, ShadowRouter};

#[tokio::main]
async fn main() -> Result<()> {
    // Load configuration
    let config = Config::from_env()?;

    // Initialize tracing
    init_tracing(&config);

    tracing::info!(
        host = %config.host,
        port = config.port,
        webmethods_url = %config.webmethods_url,
        shadow_mode = config.shadow_mode_enabled,
        "starting stoa-gateway"
    );

    // Create shutdown broadcast channel
    let (shutdown_tx, _) = broadcast::channel::<()>(1);
    let shutting_down = Arc::new(AtomicBool::new(false));

    // Create metrics registry
    let metrics = Metrics::new();

    // Create health checker
    let health_checker = Arc::new(HealthChecker::new(
        config.webmethods_url.clone(),
        Duration::from_secs(config.webmethods_health_check_interval_secs),
        Duration::from_secs(config.webmethods_health_check_timeout_secs),
    ));

    // Get shared health state
    let health_state = health_checker.state();

    // Spawn health checker task
    let health_shutdown_rx = shutdown_tx.subscribe();
    let health_checker_clone = Arc::clone(&health_checker);
    tokio::spawn(async move {
        health_checker_clone.run(health_shutdown_rx).await;
    });

    // Spawn metrics sync task (tracks health changes for prometheus)
    let metrics_shutdown_rx = shutdown_tx.subscribe();
    let health_metrics = metrics.clone();
    let health_state_for_metrics = Arc::clone(&health_state);
    tokio::spawn(async move {
        let mut was_healthy = true;
        let mut interval = tokio::time::interval(Duration::from_secs(1));
        let mut shutdown_rx = metrics_shutdown_rx;

        loop {
            tokio::select! {
                _ = interval.tick() => {
                    let is_healthy = health_state_for_metrics.load(Ordering::SeqCst);
                    health_metrics.set_health("webmethods", is_healthy);

                    if was_healthy && !is_healthy {
                        health_metrics.record_failover("webmethods", "rust");
                    }
                    was_healthy = is_healthy;
                }
                _ = shutdown_rx.recv() => {
                    tracing::debug!("metrics sync task shutting down");
                    break;
                }
            }
        }
    });

    // Create app state for health endpoints
    let app_state = AppState {
        webmethods_healthy: Arc::clone(&health_state),
        shutting_down: Arc::clone(&shutting_down),
    };

    // Create shadow router (uses shadow mode when enabled)
    let shadow_router = ShadowRouter::new(
        health_state,
        config.webmethods_url.clone(),
        metrics.clone(),
        Duration::from_secs(config.shadow_timeout_secs),
        config.shadow_mode_enabled,
    );

    // CAB-912: Create MCP tool registry
    let tool_registry = ToolRegistry::new();
    // Tools will be registered here when services are configured
    // registry.register(StoaCreateApiTool::new(...));

    // CAB-912 P2: Initialize auth if OIDC is configured
    let oidc_enabled = std::env::var("OIDC_ISSUER_URL").is_ok();
    let mcp_routes = if oidc_enabled {
        let auth_components = AuthBuilder::from_env()
            .with_rbac_policy(RbacPolicy::default())
            .build();

        tracing::info!(
            issuer = %auth_components.config.issuer_url,
            audience = %auth_components.config.audience,
            "OIDC authentication enabled"
        );

        let mcp_state = McpState::with_rbac(
            tool_registry,
            auth_components.auth_state.clone(),
            auth_components.rbac_enforcer,
        );

        mcp_router_with_auth(mcp_state)
    } else {
        tracing::warn!("OIDC not configured - MCP endpoints will be unauthenticated");
        let mcp_state = McpState::new(tool_registry);
        mcp_router(mcp_state)
    };

    tracing::info!("MCP gateway initialized");

    // Build application router
    let app = Router::new()
        // Health endpoints (no state needed for live/startup)
        .route("/health/live", get(health_live))
        .route("/health/startup", get(health_startup))
        .route(
            "/health/ready",
            get(health_ready).with_state(app_state.clone()),
        )
        // Metrics endpoint
        .route("/metrics", get(metrics_handler).with_state(metrics.clone()))
        // CAB-912: MCP endpoints (with or without auth)
        .merge(mcp_routes)
        // Catch-all route for API proxying with shadow mode
        .fallback(any(shadow_route_request).with_state(shadow_router))
        // Add tracing layer
        .layer(TraceLayer::new_for_http());

    // Create TCP listener
    let addr: SocketAddr = format!("{}:{}", config.host, config.port).parse()?;
    let listener = TcpListener::bind(addr).await?;
    tracing::info!(address = %addr, "listening for connections");

    // Spawn graceful shutdown handler
    let shutdown_tx_clone = shutdown_tx.clone();
    let shutting_down_clone = Arc::clone(&shutting_down);
    tokio::spawn(async move {
        shutdown_signal().await;
        tracing::info!("shutdown signal received, initiating graceful shutdown");

        // Mark as shutting down (health check will return not ready)
        shutting_down_clone.store(true, Ordering::SeqCst);

        // Signal all tasks to stop
        let _ = shutdown_tx_clone.send(());

        // Give some time for in-flight requests to complete
        tokio::time::sleep(Duration::from_secs(5)).await;
    });

    // Run server with graceful shutdown
    axum::serve(listener, app)
        .with_graceful_shutdown(async move {
            let mut rx = shutdown_tx.subscribe();
            let _ = rx.recv().await;
        })
        .await?;

    tracing::info!("stoa-gateway stopped");
    Ok(())
}

/// Initialize tracing based on configuration.
fn init_tracing(config: &Config) {
    let filter = tracing_subscriber::EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new(&config.log_level));

    if config.log_format == "json" {
        tracing_subscriber::registry()
            .with(filter)
            .with(tracing_subscriber::fmt::layer().json())
            .init();
    } else {
        tracing_subscriber::registry()
            .with(filter)
            .with(tracing_subscriber::fmt::layer().pretty())
            .init();
    }
}

/// Wait for shutdown signal (SIGTERM or SIGINT).
async fn shutdown_signal() {
    let ctrl_c = async {
        signal::ctrl_c()
            .await
            .expect("failed to install Ctrl+C handler");
    };

    #[cfg(unix)]
    let terminate = async {
        signal::unix::signal(signal::unix::SignalKind::terminate())
            .expect("failed to install SIGTERM handler")
            .recv()
            .await;
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        _ = ctrl_c => {},
        _ = terminate => {},
    }
}
