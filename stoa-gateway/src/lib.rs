//! STOA Gateway Library
//!
//! Public modules and router builder for integration testing and the binary entry point.

pub mod a2a;
pub mod access_log;
pub mod auth;
pub mod cache;
pub mod config;
pub mod control_plane;
pub mod diagnostics;
pub mod ebpf;
pub mod events;
pub mod federation;
pub mod git;
pub mod governance;
pub mod graphql;
pub mod grpc;
pub mod guardrails;
pub mod handlers;
pub mod hegemon;
pub mod k8s;
pub mod kafka;
pub mod lb;
pub mod llm;
pub mod mcp;
pub mod memory;
pub mod metering;
pub mod metrics;
pub mod mode;
pub mod oauth;
pub mod observability;
pub mod optimization;
#[cfg(feature = "phases")]
pub mod phases;
pub mod plugin;
pub mod policy;
pub mod proxy;
pub mod quota;
pub mod rag;
pub mod rate_limit;
pub mod resilience;
pub mod routes;
pub mod security_headers;
pub mod shadow;
pub mod skills;
pub mod soap;
pub mod state;
pub mod supervision;
pub mod tcp_filter;
pub mod telemetry;
pub mod trace_context;
pub mod uac;
pub mod ws;

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
    resources::{
        mcp_completion_complete, mcp_prompts_get, mcp_prompts_list, mcp_resources_list,
        mcp_resources_read, mcp_resources_templates_list,
    },
    sse::{handle_sse_delete, handle_sse_get, handle_sse_post},
    ws::handle_ws_upgrade,
};
use proxy::{api_proxy_handler, dynamic_proxy, list_api_proxy_backends, llm_proxy_handler};
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
    let memory_monitor = state.memory_monitor.clone();

    // Build TCP filter early (before state is moved into with_state)
    let tcp_filter = std::sync::Arc::new(tcp_filter::TcpFilter::from_config(&state.config));

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
        .route("/skills/sync", post(admin::skills_sync))
        .route(
            "/skills",
            get(admin::skills_list)
                .post(admin::skills_upsert)
                .delete(admin::skills_delete),
        )
        // CAB-1551: Skills health (literal path before parametric :id)
        .route("/skills/health", get(admin::skills_health_all))
        .route(
            "/skills/:id",
            get(admin::skills_get_by_id)
                .put(admin::skills_update)
                .delete(admin::skills_delete_by_id),
        )
        .route("/skills/:id/health", get(admin::skills_health))
        .route("/skills/:id/health/reset", post(admin::skills_health_reset))
        // CAB-1487: LLM cost-aware routing admin
        .route("/llm/status", get(admin::llm_status))
        .route("/llm/providers", get(admin::llm_providers))
        .route("/llm/costs", get(admin::llm_costs))
        // CAB-1752: Distributed tracing admin
        .route("/tracing/status", get(admin::tracing_status))
        // CAB-1752: Federation upstreams listing
        .route("/federation/upstreams", get(admin::federation_upstreams))
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
        // CAB-1710/1711: HEGEMON agent registry admin
        .route("/hegemon/agents", get(hegemon::registry::list_agents))
        .route("/hegemon/agents/:name", get(hegemon::registry::get_agent))
        .route(
            "/hegemon/agents/:name/tier",
            post(hegemon::registry::update_agent_tier),
        )
        // CAB-1713/1714: HEGEMON dispatch admin
        .route(
            "/hegemon/dispatches",
            get(hegemon::dispatch::list_dispatches),
        )
        .route(
            "/hegemon/dispatches/:id",
            get(hegemon::dispatch::get_dispatch),
        )
        // CAB-1716: HEGEMON budget admin
        .route("/hegemon/budget", get(hegemon::budget::list_budgets))
        // CAB-1718: HEGEMON claims admin
        .route("/hegemon/claims", get(hegemon::claims::list_claims))
        .route("/hegemon/claims/:mega_id", get(hegemon::claims::get_claims))
        // CAB-1720/1721: HEGEMON metering + dashboard admin
        .route(
            "/hegemon/dashboard",
            get(hegemon::dashboard::fleet_dashboard),
        )
        .route("/hegemon/events", get(hegemon::metering::list_events))
        // CAB-1709 P6: HEGEMON messaging admin
        .route("/hegemon/messages", get(hegemon::messaging::list_inboxes))
        // CAB-1754: A2A agent registry admin
        .route(
            "/a2a/agents",
            get(a2a::admin::list_agents).post(a2a::admin::register_agent),
        )
        .route(
            "/a2a/agents/:name",
            get(a2a::admin::get_agent).delete(a2a::admin::unregister_agent),
        )
        // CAB-1828: Route hot-reload
        .route("/routes/reload", post(admin::routes_reload))
        // CAB-1645: Error snapshot capture
        .route(
            "/snapshots",
            get(handlers::snapshot::list_snapshots).delete(handlers::snapshot::clear_snapshots),
        )
        .route(
            "/snapshots/:request_id",
            get(handlers::snapshot::get_snapshot),
        )
        // CAB-1848: eBPF kernel policy sync
        .route("/ebpf/sync", post(ebpf::ebpf_sync))
        .route("/ebpf/status", get(ebpf::ebpf_status))
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
        // HTTP metrics middleware: records method, path, status, duration for ALL requests.
        // Also triggers auto-RCA on 5xx responses (CAB-1542 Phase 3).
        .layer(axum::middleware::from_fn_with_state(
            state.clone(),
            http_metrics_middleware,
        ));

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
                // RFC 9126 — Pushed Authorization Requests (CAB-1733, FAPI 2.0)
                .route("/oauth/par", post(oauth::proxy::par_proxy))
                .route("/oauth/register", post(oauth::proxy::register_proxy))
                // RFC 7592 — Dynamic Client Registration Management (CAB-1606)
                .route(
                    "/oauth/register/:client_id",
                    get(oauth::proxy::register_get_proxy)
                        .put(oauth::proxy::register_update_proxy)
                        .delete(oauth::proxy::register_delete_proxy),
                )
                // MCP Discovery
                .route("/mcp", get(mcp_discovery))
                .route("/mcp/capabilities", get(mcp_capabilities))
                .route("/mcp/health", get(mcp_health))
                // MCP Tools (JSON-RPC style)
                .route("/mcp/tools/list", post(mcp_tools_list))
                .route("/mcp/tools/call", post(mcp_tools_call))
                // MCP Resources, Prompts, Completion (REST — CAB-1472)
                .route("/mcp/resources/list", post(mcp_resources_list))
                .route("/mcp/resources/read", post(mcp_resources_read))
                .route(
                    "/mcp/resources/templates/list",
                    post(mcp_resources_templates_list),
                )
                .route("/mcp/prompts/list", post(mcp_prompts_list))
                .route("/mcp/prompts/get", post(mcp_prompts_get))
                .route("/mcp/completion/complete", post(mcp_completion_complete))
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
                // LLM API Proxy (CAB-1568: STOA Dogfood) — before fallback
                .route("/v1/messages", post(llm_proxy_handler))
                .route("/v1/messages/count_tokens", post(llm_proxy_handler))
                // OpenAI-compatible LLM proxy (Mistral, OpenAI, vLLM, etc.)
                .route("/v1/chat/completions", post(llm_proxy_handler))
                // API Proxy — internal dogfooding (CAB-1722)
                // Routes /proxy/<backend>/... to upstream with credential injection.
                // Separate from /mcp/* and /apis/* (dynamic proxy routes).
                // Uses catch-all since axum doesn't allow {param}/{*rest}.
                .route("/proxy/*path", axum::routing::any(api_proxy_handler))
                .route("/admin/api-proxy/backends", get(list_api_proxy_backends))
                // CAB-1713/1714: HEGEMON dispatch endpoints
                .route("/hegemon/dispatch", post(hegemon::dispatch::dispatch_job))
                .route(
                    "/hegemon/dispatch/:id",
                    get(hegemon::dispatch::get_dispatch_status),
                )
                .route(
                    "/hegemon/dispatch/:id/result",
                    post(hegemon::dispatch::dispatch_result),
                )
                // CAB-1716: HEGEMON budget endpoints
                .route("/hegemon/budget/check", post(hegemon::budget::budget_check))
                .route(
                    "/hegemon/budget/record",
                    post(hegemon::budget::budget_record),
                )
                // CAB-1718: HEGEMON claim coordination endpoints
                .route(
                    "/hegemon/claims/:mega_id/reserve",
                    post(hegemon::claims::reserve_claim),
                )
                .route(
                    "/hegemon/claims/:mega_id/release",
                    post(hegemon::claims::release_claim),
                )
                .route(
                    "/hegemon/claims/:mega_id/heartbeat",
                    post(hegemon::claims::heartbeat_claim),
                )
                // CAB-1709 P6: HEGEMON messaging endpoints
                .route("/hegemon/messages", post(hegemon::messaging::send_message))
                .route(
                    "/hegemon/messages/:agent_name",
                    get(hegemon::messaging::get_inbox),
                )
                .route(
                    "/hegemon/messages/:agent_name/read",
                    post(hegemon::messaging::mark_message_read),
                )
                .route(
                    "/hegemon/messages/:agent_name/read-all",
                    post(hegemon::messaging::mark_all_messages_read),
                )
                // A2A (Agent-to-Agent) Protocol — Google A2A spec (CAB-1754)
                .route("/.well-known/agent.json", get(a2a::discovery::agent_card))
                .route("/a2a", post(a2a::handlers::a2a_handler))
                .route("/a2a/agents", get(a2a::discovery::list_agents))
                // WebSocket Proxy (CAB-1758): bidirectional relay with governance
                .route("/ws/:route_id", get(ws::proxy::ws_proxy_upgrade))
                // SOAP Proxy (CAB-1762): passthrough with auth + fault detection
                .route("/soap/:route_id", post(soap::proxy::soap_proxy))
                // Dynamic proxy fallback — must be LAST
                .fallback(dynamic_proxy)
                // Security profile enforcement: per-subscription DPoP/mTLS (CAB-1744)
                .layer(axum::middleware::from_fn(
                    auth::profile_enforcement::profile_enforcement_middleware,
                ))
                // Quota enforcement: runs after auth, before handlers (CAB-1121 P4)
                .layer(axum::middleware::from_fn_with_state(
                    state.clone(),
                    quota::quota_middleware,
                ))
                // HEGEMON Supervision: runs after quota, before mTLS (CAB-1636)
                .layer(axum::middleware::from_fn_with_state(
                    state.clone(),
                    supervision::supervision_middleware,
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

            // Sender-constraint layer: unified mTLS + DPoP pipeline (CAB-1607)
            let edge_final = if state.config.sender_constraint.enabled {
                let sc_config = state.config.sender_constraint.clone();
                edge_with_mtls.layer(axum::middleware::from_fn(move |request, next| {
                    let config = sc_config.clone();
                    auth::sender_constraint::sender_constraint_middleware(config, request, next)
                }))
            } else {
                edge_with_mtls
            };

            edge_final.with_state(state)
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

            // Dispatch git client by git_provider config (CAB-1891)
            let shadow_service = match state.config.git_provider.as_str() {
                "github" => {
                    // GitHub: log that PR submission will use GitHub (future: integrate GitHubClient)
                    tracing::info!("Shadow mode: git_provider=github, PR submission via GitHub");
                    std::sync::Arc::new(mode::shadow::ShadowService::new(shadow_settings))
                }
                _ => {
                    // GitLab (default): existing behavior (CAB-1109 Phase 5)
                    if let (Some(api_url), Some(token), Some(project_id)) = (
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
                                std::sync::Arc::new(mode::shadow::ShadowService::new(
                                    shadow_settings,
                                ))
                            }
                        }
                    } else {
                        tracing::info!(
                            "Shadow mode: GitLab not configured, MR submission disabled"
                        );
                        std::sync::Arc::new(mode::shadow::ShadowService::new(shadow_settings))
                    }
                }
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

    // Memory backpressure: reject early with 503 when RSS exceeds threshold (CAB-1829).
    // Runs BEFORE trace context / access log to short-circuit without overhead.
    let with_backpressure = mode_router.layer(axum::middleware::from_fn(move |request, next| {
        let m = memory_monitor.clone();
        memory_backpressure_middleware(m, request, next)
    }));

    // W3C Trace Context: extract incoming traceparent header into request extensions.
    // Runs BEFORE access_log so trace_id is available for structured logging.
    let with_trace_ctx = with_backpressure.layer(axum::middleware::from_fn(
        trace_context::trace_context_middleware,
    ));

    // Access log: structured JSON for every request (shipped to OpenSearch via Fluent Bit).
    // Runs after auth so tenant_id/consumer_id are available from extensions.
    let with_access_log = if access_log_enabled {
        with_trace_ctx.layer(axum::middleware::from_fn(access_log::access_log_middleware))
    } else {
        with_trace_ctx
    };

    // Security headers: applied AFTER all routes are registered.
    // Adds X-Content-Type-Options, X-Frame-Options, etc. to every response.
    let with_security = with_access_log.layer(axum::middleware::from_fn(
        security_headers::security_headers_middleware,
    ));

    // TCP early filter (CAB-1830): outermost layer — rejects blocked/rate-limited IPs
    // before any HTTP processing. Requires into_make_service_with_connect_info in main.
    if tcp_filter.is_enabled() {
        let filter = tcp_filter.clone();
        with_security.layer(axum::middleware::from_fn(move |request, next| {
            let filter = filter.clone();
            tcp_filter::pre_tls_filter(filter, request, next)
        }))
    } else {
        with_security
    }
}

// === HTTP Metrics Middleware ===

/// Middleware that records Prometheus metrics for every HTTP request.
/// On 5xx responses, triggers the diagnostic engine for automatic root-cause analysis (CAB-1542)
/// and optionally captures an error snapshot with PII-masked body data (CAB-1645).
///
/// Health, readiness, and metrics endpoints are excluded to avoid unnecessary
/// overhead on high-frequency probes (K8s liveness/readiness, arena benchmarks).
async fn http_metrics_middleware(
    axum::extract::State(state): axum::extract::State<AppState>,
    request: axum::extract::Request,
    next: axum::middleware::Next,
) -> axum::response::Response {
    // Skip metrics recording for infrastructure endpoints
    let raw_path = request.uri().path();
    if raw_path.starts_with("/health") || raw_path.starts_with("/ready") || raw_path == "/metrics" {
        return next.run(request).await;
    }

    // Fast path: skip metrics + tracing overhead when both are disabled (pure proxy mode).
    // Env: STOA_PROXY_METRICS_ENABLED=false + STOA_PROXY_TRACING_ENABLED=false
    let metrics_enabled = state.config.proxy_metrics_enabled;
    let tracing_enabled = state.config.proxy_tracing_enabled;
    if !metrics_enabled && !tracing_enabled {
        return next.run(request).await;
    }

    let method = request.method().to_string();
    // Path normalization replaces UUIDs/numeric IDs with :id to prevent Prometheus label
    // cardinality explosion. Skip when metrics are disabled to save ~0.5ms per request.
    let path = if metrics_enabled {
        metrics::normalize_path(raw_path)
    } else {
        raw_path.to_string()
    };
    let request_id = request
        .headers()
        .get("x-request-id")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("unknown")
        .to_string();
    let start = std::time::Instant::now();

    // CAB-1645: Buffer request body + headers for snapshot capture (only when enabled).
    // When disabled, this block is a no-op boolean check — zero overhead.
    let snapshot_enabled = state.snapshot_store.is_enabled();
    let (request_headers_clone, request_body_bytes, request) = if snapshot_enabled {
        let (parts, body) = request.into_parts();
        let req_headers = parts.headers.clone();
        // Cap body buffering at configured max
        let max_bytes = state.config.snapshot_body_max_bytes;
        let body_bytes: axum::body::Bytes = match axum::body::to_bytes(body, max_bytes + 1).await {
            Ok(b) => b,
            Err(_) => axum::body::Bytes::new(),
        };
        // Rebuild the request with the buffered body
        let rebuilt =
            axum::http::Request::from_parts(parts, axum::body::Body::from(body_bytes.clone()));
        (Some(req_headers), Some(body_bytes), rebuilt)
    } else {
        (None, None, request)
    };

    // CAB-1842: inject deployment mode as span attribute for Tempo service graph.
    // Uses Instrument (not Span::enter) because next.run().await is async —
    // Span::enter guard is dropped at the first yield point.
    // Skip span creation when proxy tracing is disabled to save ~0.4ms per request.
    // Env: STOA_PROXY_TRACING_ENABLED (default: true)
    use tracing::Instrument;
    // Extract remote IP (TCP peer) and client IP (X-Forwarded-For / X-Real-IP)
    let remote_ip = request
        .extensions()
        .get::<axum::extract::ConnectInfo<std::net::SocketAddr>>()
        .map(|ci| ci.0.ip().to_string())
        .unwrap_or_else(|| "-".to_string());
    let client_ip = request
        .headers()
        .get("x-forwarded-for")
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.split(',').next())
        .map(|s| s.trim().to_string())
        .or_else(|| {
            request
                .headers()
                .get("x-real-ip")
                .and_then(|v| v.to_str().ok())
                .map(|s| s.to_string())
        })
        .unwrap_or_else(|| remote_ip.clone());
    let (response, captured_trace_id) = if tracing_enabled {
        let deployment_mode = state.config.gateway_mode.to_string();
        let request_span = tracing::span!(
            tracing::Level::INFO,
            "http.request",
            otel.kind = "server",
            "stoa.deployment_mode" = %deployment_mode,
            http.method = %method,
            http.route = %path,
            "net.peer.ip" = %remote_ip,
            "http.client_ip" = %client_ip,
            http.status_code = tracing::field::Empty,
            otel.status_code = tracing::field::Empty,
            otel.status_message = tracing::field::Empty,
        );
        // CAB-1866: capture trace_id inside the span so access_log_middleware can read it.
        // access_log is an outer layer — by the time it sees the response, this span has
        // already closed and tracing::Span::current() returns Span::none().
        // Status code + OTel status are recorded inside the span before it closes.
        let (resp, trace_id) = async {
            let r = next.run(request).await;
            let status = r.status().as_u16();
            let current = tracing::Span::current();
            current.record("http.status_code", status);
            if status >= 500 {
                current.record("otel.status_code", "ERROR");
                current.record("otel.status_message", &format!("HTTP {status}") as &str);
            } else {
                current.record("otel.status_code", "OK");
            }
            let tid = crate::telemetry::extract_trace_id();
            (r, tid)
        }
        .instrument(request_span)
        .await;
        (resp, trace_id)
    } else {
        let resp = next.run(request).await;
        (resp, "-".to_string())
    };
    let mut response = response;
    response
        .extensions_mut()
        .insert(crate::access_log::CapturedTraceId(captured_trace_id));

    let duration = start.elapsed().as_secs_f64();
    let status = response.status().as_u16();
    if metrics_enabled {
        metrics::record_http_request(&method, &path, status, duration);
    }

    // Auto-RCA + snapshot capture on server errors
    if status >= 500 {
        // Auto-RCA: trigger diagnostic engine (CAB-1542)
        let input = diagnostics::engine::DiagnosticInput {
            request_id: request_id.clone(),
            method: method.clone(),
            path: path.clone(),
            status_code: status,
            error_message: None,
            hop_headers: diagnostics::hops::HopHeaders::default(),
            timing: diagnostics::latency::TimingBreakdown {
                total_ms: duration * 1000.0,
                ..diagnostics::latency::TimingBreakdown::default()
            },
            timestamp: chrono::Utc::now().to_rfc3339(),
        };
        let _report = state.diagnostic_engine.diagnose(input);
        tracing::warn!(
            status = status,
            path = %path,
            method = %method,
            duration_ms = duration * 1000.0,
            "auto-RCA triggered for 5xx response"
        );

        // CAB-1645: Capture error snapshot with PII-masked body data.
        // Skip for streaming responses (SSE, WebSocket upgrades).
        if snapshot_enabled {
            let is_streaming = status == 101
                || response
                    .headers()
                    .get("content-type")
                    .and_then(|v| v.to_str().ok())
                    .map(|ct| ct.contains("text/event-stream"))
                    .unwrap_or(false);

            if !is_streaming {
                // Buffer response body for snapshot
                let resp_headers = response.headers().clone();
                let (resp_parts, resp_body) = response.into_parts();
                let max_bytes = state.config.snapshot_body_max_bytes;
                let resp_body_bytes = match axum::body::to_bytes(resp_body, max_bytes + 1).await {
                    Ok(bytes) => bytes,
                    Err(_) => axum::body::Bytes::new(),
                };

                // Compile extra PII patterns
                let extra_patterns: Vec<regex::Regex> = state
                    .config
                    .snapshot_extra_pii_patterns
                    .iter()
                    .filter_map(|p| regex::Regex::new(p).ok())
                    .collect();

                let error_category =
                    diagnostics::taxonomy::ErrorCategory::classify(Some(status), None);

                let empty_headers = axum::http::HeaderMap::new();
                let req_hdrs = request_headers_clone.as_ref().unwrap_or(&empty_headers);
                let empty_bytes = axum::body::Bytes::new();
                let req_body = request_body_bytes.as_ref().unwrap_or(&empty_bytes);

                let snapshot =
                    observability::capture::build_snapshot(observability::capture::SnapshotInput {
                        request_id,
                        method,
                        path,
                        status_code: status,
                        error_category: format!("{:?}", error_category).to_lowercase(),
                        duration_ms: duration * 1000.0,
                        request_headers: req_hdrs,
                        request_body: req_body,
                        response_headers: &resp_headers,
                        response_body: &resp_body_bytes,
                        max_body_bytes: max_bytes,
                        extra_patterns: &extra_patterns,
                    });

                state.snapshot_store.push(snapshot);

                // Rebuild the response with the buffered body
                return axum::http::Response::from_parts(
                    resp_parts,
                    axum::body::Body::from(resp_body_bytes),
                );
            }
        }
    }

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
        match state.http_client.get(&health_url).send().await {
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

// === Memory Backpressure Middleware (CAB-1829) ===

/// Rejects requests with 503 + Retry-After when memory is under pressure.
/// Health and metrics endpoints are exempt to keep probes and scraping alive.
async fn memory_backpressure_middleware(
    monitor: memory::MemoryMonitor,
    request: axum::extract::Request,
    next: axum::middleware::Next,
) -> axum::response::Response {
    // Always allow health/metrics so K8s probes and Prometheus scraping work
    let path = request.uri().path();
    if path.starts_with("/health") || path.starts_with("/ready") || path == "/metrics" {
        return next.run(request).await;
    }

    if monitor.under_pressure() {
        return memory::backpressure_response();
    }

    next.run(request).await
}

async fn prometheus_metrics() -> String {
    use prometheus::Encoder;
    // Sync OTel spans counter before scrape (CAB-1831)
    metrics::sync_otel_spans_gauge();
    let encoder = prometheus::TextEncoder::new();
    let metric_families = prometheus::gather();
    let mut buffer = Vec::new();
    encoder.encode(&metric_families, &mut buffer).unwrap();
    String::from_utf8(buffer).unwrap()
}
