//! STOA Gateway Library
//!
//! Public modules and router builder for integration testing and the binary entry point.

pub mod access_log;
pub mod auth;
pub mod cache;
pub mod config;
pub mod control_plane;
pub mod diagnostics;
pub mod events;
pub mod federation;
pub mod git;
pub mod governance;
pub mod guardrails;
pub mod handlers;
pub mod k8s;
pub mod mcp;
pub mod metering;
pub mod metrics;
pub mod mode;
pub mod oauth;
pub mod optimization;
pub mod policy;
pub mod proxy;
pub mod quota;
pub mod rate_limit;
pub mod resilience;
pub mod routes;
pub mod security_headers;
pub mod shadow;
pub mod skills;
pub mod state;
pub mod telemetry;
pub mod uac;

use axum::{
    routing::{delete, get, post},
    Router,
};
use tracing::warn;

use events::polling::poll_events;
use handlers::admin;
use mcp::{
    discovery::{mcp_capabilities, mcp_discovery, mcp_health},
    handlers::{mcp_rest_tools_invoke, mcp_rest_tools_list, mcp_tools_call, mcp_tools_list},
    sse::{handle_sse_delete, handle_sse_get, handle_sse_post},
    ws::handle_ws_upgrade,
};
use proxy::dynamic_proxy;
use state::AppState;

/// Build the Axum router with all routes.
///
/// Phase 8: Router is built based on gateway mode (ADR-024).
/// - EdgeMcp: Full MCP protocol, SSE transport, tool execution (default)
/// - Sidecar: Policy enforcement only (ext_authz style)
/// - Proxy: Inline proxy with request/response transformation
/// - Shadow: Passive traffic capture and UAC generation
pub fn build_router(state: AppState) -> Router {
    use mode::GatewayMode;

    let access_log_enabled = state.config.access_log_enabled;

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
        // CAB-1250: BYOK backend credentials
        .route(
            "/backend-credentials",
            get(admin::list_backend_credentials).post(admin::upsert_backend_credential),
        )
        .route(
            "/backend-credentials/:route_id",
            delete(admin::delete_backend_credential),
        )
        // CAB-1299: UAC contracts
        .route(
            "/contracts",
            get(admin::list_contracts).post(admin::upsert_contract),
        )
        .route(
            "/contracts/:key",
            get(admin::get_contract).delete(admin::delete_contract),
        )
        // CAB-1362: Federation admin
        .route("/federation/status", get(admin::federation_status))
        .route("/federation/cache", get(admin::federation_cache_stats))
        // CAB-1371: Federation cache invalidation
        .route(
            "/federation/cache/:sub_account_id",
            delete(admin::federation_cache_invalidate),
        )
        // CAB-1123: Prompt cache admin
        .route("/prompt-cache/stats", get(admin::prompt_cache_stats))
        .route("/prompt-cache/load", post(admin::prompt_cache_load))
        .route("/prompt-cache/get/:key", get(admin::prompt_cache_get))
        .route(
            "/prompt-cache/invalidate",
            post(admin::prompt_cache_invalidate),
        )
        .route("/prompt-cache/patterns", get(admin::prompt_cache_patterns))
        // CAB-1365/1366: Skills admin
        .route("/skills/status", get(admin::skills_status))
        .route("/skills/resolve", get(admin::skills_resolve))
        .route(
            "/skills",
            get(admin::skills_list)
                .post(admin::skills_upsert)
                .delete(admin::skills_delete),
        )
        // CAB-1316: Diagnostic endpoint (CB states, uptime, route stats)
        .route("/diagnostic", get(handlers::diagnostic::diagnostic_handler))
        // CAB-1316: Per-request diagnostic report + aggregated summary
        .route(
            "/diagnostics/summary",
            get(handlers::diagnostic::diagnostic_summary_handler),
        )
        .route(
            "/diagnostics/:request_id",
            get(handlers::diagnostic::diagnostic_report_handler),
        )
        .layer(axum::middleware::from_fn_with_state(
            state.clone(),
            admin::admin_auth,
        ));

    // Common routes for all modes: health, metrics, admin
    let base = Router::new()
        .route("/health", get(health))
        .route("/health/ready", get(ready))
        .route("/health/live", get(health))
        .route("/ready", get(ready))
        .route("/metrics", get(prometheus_metrics))
        .nest("/admin", admin_router)
        // HTTP metrics middleware: records method, path, status, duration for ALL requests
        .layer(axum::middleware::from_fn(http_metrics_middleware));

    // Build mTLS layers only when mTLS is enabled (CAB-864, CAB-1359 perf).
    // When disabled, skip the middleware entirely — avoids 2 async fn calls per request.
    let mtls_enabled = state.config.mtls.enabled;
    let mtls_extraction_layer = if mtls_enabled {
        let mtls_config_s1 = state.config.mtls.clone();
        let mtls_stats_s1 = state.mtls_stats.clone();
        Some(axum::middleware::from_fn(move |request, next| {
            let config = mtls_config_s1.clone();
            let stats = mtls_stats_s1.clone();
            auth::mtls::mtls_extraction_middleware(config, stats, request, next)
        }))
    } else {
        None
    };
    let mtls_binding_layer = if mtls_enabled {
        let mtls_config_s3 = state.config.mtls.clone();
        let mtls_stats_s3 = state.mtls_stats.clone();
        Some(axum::middleware::from_fn(move |request, next| {
            let config = mtls_config_s3.clone();
            let stats = mtls_stats_s3.clone();
            auth::mtls::mtls_binding_middleware(config, stats, request, next)
        }))
    } else {
        None
    };

    let mode_router = match state.config.gateway_mode {
        GatewayMode::EdgeMcp => {
            // Full MCP protocol: OAuth discovery, MCP tools, SSE transport
            let edge_base = base
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
                // MCP Tools (JSON-RPC style)
                .route("/mcp/tools/list", post(mcp_tools_list))
                .route("/mcp/tools/call", post(mcp_tools_call))
                // MCP v1 REST API (demo + simple HTTP clients)
                .route("/mcp/v1/tools", get(mcp_rest_tools_list))
                .route("/mcp/v1/tools/invoke", post(mcp_rest_tools_invoke))
                // MCP SSE Transport (Streamable HTTP)
                .route(
                    "/mcp/sse",
                    get(handle_sse_get)
                        .post(handle_sse_post)
                        .delete(handle_sse_delete),
                )
                // MCP WebSocket Transport (CAB-1345: bidirectional)
                .route("/mcp/ws", get(handle_ws_upgrade))
                // MCP Event Polling Fallback (CAB-1179)
                .route("/mcp/events", get(poll_events))
                // Dynamic proxy fallback — must be LAST
                .fallback(dynamic_proxy)
                // Quota enforcement: runs after auth, before handlers (CAB-1121 P4)
                .layer(axum::middleware::from_fn_with_state(
                    state.clone(),
                    quota::quota_middleware,
                ));

            // mTLS layers: only added when enabled (CAB-1359 perf — skip 2 async calls/req when off)
            let edge_with_mtls = if let (Some(binding), Some(extraction)) =
                (mtls_binding_layer, mtls_extraction_layer)
            {
                edge_base
                    // mTLS Stage 3: binding verification (RFC 8705 — cert ↔ JWT cnf)
                    .layer(binding)
                    // mTLS Stage 1: extraction (cert info from X-SSL-* headers)
                    .layer(extraction)
            } else {
                edge_base
            };

            edge_with_mtls.with_state(state)
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
                        tracing::info!(
                            "Shadow mode: GitLab client configured for UAC MR submission"
                        );
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
                tracing::info!("Shadow mode: GitLab not configured, MR submission disabled");
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
    };

    // Access log: structured JSON for every request (shipped to OpenSearch via Fluent Bit).
    // Runs after auth so tenant_id/consumer_id are available from extensions.
    let with_access_log = if access_log_enabled {
        mode_router.layer(axum::middleware::from_fn(access_log::access_log_middleware))
    } else {
        mode_router
    };

    // Security headers: outermost layer, applied AFTER all routes are registered.
    // Adds X-Content-Type-Options, X-Frame-Options, etc. to every response.
    with_access_log.layer(axum::middleware::from_fn(
        security_headers::security_headers_middleware,
    ))
}

// === HTTP Metrics Middleware ===

/// Middleware that records Prometheus metrics for every HTTP request.
async fn http_metrics_middleware(
    request: axum::extract::Request,
    next: axum::middleware::Next,
) -> axum::response::Response {
    let method = request.method().to_string();
    let path = metrics::normalize_path(request.uri().path());
    let start = std::time::Instant::now();

    let response = next.run(request).await;

    let duration = start.elapsed().as_secs_f64();
    let status = response.status().as_u16();
    metrics::record_http_request(&method, &path, status, duration);

    response
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
