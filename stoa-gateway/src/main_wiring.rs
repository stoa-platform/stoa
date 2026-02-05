//! Main.rs Service Wiring Patch
//!
//! Replace the empty ToolRegistry construction with proper service wiring.
//! This patch shows the BEFORE/AFTER for main.rs

// ============================================
// BEFORE (broken - services not constructed)
// ============================================
/*
// Line ~120-125 in main.rs
let tool_registry = Arc::new(ToolRegistry::new());  // EMPTY!

let app_state = AppState {
    config: config.clone(),
    tool_registry,
    // ... other fields
};
*/

// ============================================
// AFTER (fixed - all services wired)
// ============================================

use std::sync::Arc;
use tracing::info;

use crate::config::Config;
use crate::rate_limit::RateLimiter;
use crate::mcp::tools::{ToolRegistry, StoaCreateApiTool};
// Add these imports if not present:
// use crate::control_plane::ControlPlaneClient;
// use crate::git::{GitClient, GitSyncService};
// use crate::uac::UacEnforcer;

/// Initialize all services and wire them together
pub fn init_services(config: &Config) -> AppState {
    info!("Initializing STOA Gateway services...");

    // 1. Core clients
    let control_plane = Arc::new(ControlPlaneClient::new(config));
    info!("✓ Control Plane client initialized");

    let git_client = Arc::new(GitClient::new(config));
    let git_sync = Arc::new(GitSyncService::new(git_client.clone()));
    info!("✓ Git sync service initialized");

    // 2. Security & Rate Limiting
    let uac_enforcer = Arc::new(UacEnforcer::new(config));
    info!("✓ UAC enforcer initialized");

    let rate_limiter = Arc::new(RateLimiter::new(config));
    // Start cleanup task
    rate_limiter.clone().start_cleanup_task();
    info!("✓ Rate limiter initialized with cleanup task");

    // 3. MCP Tool Registry - WIRE ALL TOOLS HERE
    let tool_registry = Arc::new(ToolRegistry::new());
    
    // Register STOA Create API tool
    tool_registry.register(Arc::new(StoaCreateApiTool::new(
        control_plane.clone(),
        git_sync.clone(),
        uac_enforcer.clone(),
    )));
    
    // TODO: Register additional tools as they're implemented
    // tool_registry.register(Arc::new(StoaCatalogSearchTool::new(...)));
    // tool_registry.register(Arc::new(StoaSubscriptionTool::new(...)));
    
    info!(
        tool_count = tool_registry.count(),
        "✓ Tool registry initialized"
    );

    // 4. Build AppState
    AppState {
        config: config.clone(),
        control_plane,
        git_sync,
        uac_enforcer,
        rate_limiter,
        tool_registry,
    }
}

/// Application state shared across handlers
#[derive(Clone)]
pub struct AppState {
    pub config: Config,
    pub control_plane: Arc<ControlPlaneClient>,
    pub git_sync: Arc<GitSyncService>,
    pub uac_enforcer: Arc<UacEnforcer>,
    pub rate_limiter: Arc<RateLimiter>,
    pub tool_registry: Arc<ToolRegistry>,
}

// ============================================
// Usage in main()
// ============================================
/*
#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Init tracing
    tracing_subscriber::fmt::init();
    
    // Load config
    let config = Config::load()?;
    
    // Initialize all services (NEW!)
    let app_state = init_services(&config);
    
    // Build router
    let app = Router::new()
        .route("/health", get(health))
        .route("/ready", get(ready))
        .route("/metrics", get(metrics))
        // MCP routes
        .route("/mcp", get(mcp_discovery))
        .route("/mcp/capabilities", get(mcp_capabilities))
        .route("/mcp/tools/list", post(mcp_tools_list))
        .route("/mcp/tools/call", post(mcp_tools_call))
        // SSE (Phase 2)
        .route("/mcp/sse", get(mcp_sse_get).post(mcp_sse_post).delete(mcp_sse_delete))
        .with_state(app_state);
    
    // Start server
    let addr = SocketAddr::from(([0, 0, 0, 0], config.port));
    info!("STOA Gateway listening on {}", addr);
    
    let listener = TcpListener::bind(addr).await?;
    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await?;
    
    Ok(())
}

async fn shutdown_signal() {
    let ctrl_c = async {
        tokio::signal::ctrl_c().await.expect("Failed to install Ctrl+C handler");
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
        _ = ctrl_c => info!("Received Ctrl+C, shutting down..."),
        _ = terminate => info!("Received SIGTERM, shutting down..."),
    }
}
*/
