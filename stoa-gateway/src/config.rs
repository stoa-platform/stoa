//! Configuration with Figment
//!
//! Supports:
//! - config.yaml file (optional)
//! - Environment variable overrides (STOA_ prefix)
//! - Backward compatible with existing envy-based env vars

use serde::{Deserialize, Serialize};
use std::fmt;

use crate::mode::GatewayMode;

mod api_proxy;
mod defaults;
mod deserializers;
mod enums;
mod expansion;
mod federation;
mod llm_router;
mod loader;
mod mtls;
mod path_safety;
mod redact;
mod sender_constraint;

pub use api_proxy::{ApiProxyConfig, ProxyBackendConfig};
pub use enums::{
    Environment, GitProvider, LlmProxyProvider, LogFormat, LogLevel, ShadowCaptureSource,
    SupervisionDefaultTier,
};
pub use expansion::ExpansionMode;
pub use federation::FederationUpstreamConfig;
pub use llm_router::LlmRouterConfig;
pub use loader::ConfigError;
pub use mtls::MtlsConfig;
pub use redact::Redacted;
pub use sender_constraint::SenderConstraintConfig;

use self::defaults::*;

/// Gateway configuration
///
/// `Debug` is implemented manually (see bottom of this file) so that secret
/// fields like `jwt_secret`, `keycloak_client_secret`, API keys and tokens
/// are rendered as `<redacted>` in trace logs, panics, etc.
#[derive(Clone, Serialize, Deserialize)]
pub struct Config {
    // === Server ===
    #[serde(default = "default_port")]
    pub port: u16,

    #[serde(default = "default_host")]
    pub host: String,

    // === Authentication ===
    #[serde(default)]
    pub jwt_secret: Option<String>,

    #[serde(default)]
    pub jwt_issuer: Option<String>,

    #[serde(default)]
    pub keycloak_url: Option<String>,

    #[serde(default)]
    pub keycloak_realm: Option<String>,

    #[serde(default)]
    pub keycloak_client_id: Option<String>,

    #[serde(default)]
    pub keycloak_client_secret: Option<String>,

    /// Keycloak admin password for DCR public client patch (optional).
    /// Env: STOA_KEYCLOAK_ADMIN_PASSWORD
    #[serde(default)]
    pub keycloak_admin_password: Option<String>,

    /// Internal base URL for Keycloak backend calls (bypasses hairpin NAT on OVH MKS).
    /// When set, OIDC discovery and JWKS fetches use this URL instead of keycloak_url.
    /// JWT issuer validation still uses keycloak_url (external canonical URL).
    /// Env: STOA_KEYCLOAK_INTERNAL_URL
    /// Example: http://keycloak.stoa-system.svc.cluster.local
    #[serde(default)]
    pub keycloak_internal_url: Option<String>,

    // === Gateway ===
    /// Public-facing URL of this gateway (for OAuth discovery endpoints).
    /// Env: STOA_GATEWAY_EXTERNAL_URL. Default: http://localhost:8080
    #[serde(default = "default_gateway_external_url")]
    pub gateway_external_url: Option<String>,

    // === Control Plane ===
    #[serde(default)]
    pub control_plane_url: Option<String>,

    #[serde(default)]
    pub control_plane_api_key: Option<String>,

    // === Admin API ===
    /// Bearer token for the admin API (Control Plane → gateway calls).
    /// Env: STOA_ADMIN_API_TOKEN. If not set, admin API returns 403.
    #[serde(default)]
    pub admin_api_token: Option<String>,

    // === GitLab (UAC Sync) ===
    #[serde(default)]
    pub gitlab_url: Option<String>,

    #[serde(default)]
    pub gitlab_api_url: Option<String>,

    #[serde(default)]
    pub gitlab_token: Option<String>,

    #[serde(default)]
    pub gitlab_project_id: Option<String>,

    // === GitHub (UAC Sync) ===
    /// GitHub personal access token (or fine-grained PAT).
    /// Env: GITHUB_TOKEN / STOA_GITHUB_TOKEN
    #[serde(default)]
    pub github_token: Option<String>,

    /// GitHub organization name (owner of catalog/gitops repos).
    /// Env: GITHUB_ORG / STOA_GITHUB_ORG
    #[serde(default)]
    pub github_org: Option<String>,

    /// GitHub repository name for UAC catalog storage.
    /// Env: GITHUB_CATALOG_REPO / STOA_GITHUB_CATALOG_REPO
    #[serde(default)]
    pub github_catalog_repo: Option<String>,

    /// GitHub repository name for GitOps PR submission.
    /// Env: GITHUB_GITOPS_REPO / STOA_GITHUB_GITOPS_REPO
    #[serde(default)]
    pub github_gitops_repo: Option<String>,

    /// GitHub webhook secret for validating incoming webhook payloads.
    /// Env: GITHUB_WEBHOOK_SECRET / STOA_GITHUB_WEBHOOK_SECRET
    #[serde(default)]
    pub github_webhook_secret: Option<String>,

    /// Git provider selector for UAC sync: `gitlab` (default) or `github`.
    /// Strict parsing — unknown values fail `Config::load()`.
    /// Env: GIT_PROVIDER / STOA_GIT_PROVIDER
    #[serde(default = "default_git_provider")]
    pub git_provider: GitProvider,

    // === Rate Limiting ===
    #[serde(default = "default_rate_limit_default")]
    pub rate_limit_default: Option<usize>,

    #[serde(default = "default_rate_limit_window_seconds")]
    pub rate_limit_window_seconds: Option<u64>,

    // === MCP ===
    #[serde(default = "default_session_ttl")]
    pub mcp_session_ttl_minutes: i64,

    /// Enable WebSocket transport for MCP (default: false — opt-in)
    /// Env: STOA_WEBSOCKET_ENABLED
    #[serde(default)]
    pub websocket_enabled: bool,

    /// Enable generic WebSocket proxy (CAB-1758, default: false — opt-in)
    /// Env: STOA_WS_PROXY_ENABLED
    #[serde(default)]
    pub ws_proxy_enabled: bool,

    /// WebSocket proxy: max messages per second per connection (default: 100)
    /// Env: STOA_WS_PROXY_RATE_LIMIT_PER_SECOND
    #[serde(default = "default_ws_proxy_rate_limit")]
    pub ws_proxy_rate_limit_per_second: f64,

    /// WebSocket proxy: burst capacity per connection (default: 50)
    /// Env: STOA_WS_PROXY_RATE_LIMIT_BURST
    #[serde(default = "default_ws_proxy_burst")]
    pub ws_proxy_rate_limit_burst: usize,

    // === Policy Engine (Phase 2 OPA) ===
    /// Path to Rego policy file (e.g., /etc/stoa/policies/default.rego)
    /// Env: STOA_POLICY_PATH
    #[serde(default)]
    pub policy_path: Option<String>,

    /// Enable/disable policy enforcement (default: true)
    /// Env: STOA_POLICY_ENABLED
    #[serde(default = "default_policy_enabled")]
    pub policy_enabled: bool,

    // === Observability ===
    /// Informational log level (tracing itself is driven by `RUST_LOG`).
    /// Env: STOA_LOG_LEVEL (values: trace | debug | info | warn | error)
    #[serde(default = "default_log_level")]
    pub log_level: Option<LogLevel>,

    /// Informational log format hint.
    /// Env: STOA_LOG_FORMAT (values: json | pretty | compact)
    #[serde(default = "default_log_format")]
    pub log_format: Option<LogFormat>,

    #[serde(default)]
    pub otel_endpoint: Option<String>,

    /// Enable OpenTelemetry at runtime (CAB-1831: default true, no-op when endpoint absent).
    /// Env: STOA_OTEL_ENABLED (default: true)
    #[serde(default = "default_otel_enabled")]
    pub otel_enabled: bool,

    /// Head-based sampling rate for OTel traces (0.0 = none, 1.0 = all).
    /// Env: STOA_OTEL_SAMPLE_RATE
    #[serde(default = "default_otel_sample_rate")]
    pub otel_sample_rate: f64,

    /// Enable detailed policy tracing (CAB-1842: opt-in, one span per middleware).
    /// Produces child spans for auth, rate-limit, guardrails, quota.
    /// Env: STOA_DETAILED_TRACING (default: false)
    #[serde(default)]
    pub detailed_tracing: bool,

    /// Enable HTTP metrics recording on proxy requests (path normalization + Prometheus observe).
    /// Disable for pure proxy benchmarks to eliminate ~1.2ms overhead per request.
    /// Env: STOA_PROXY_METRICS_ENABLED (default: true)
    #[serde(default = "default_true")]
    pub proxy_metrics_enabled: bool,

    /// Enable tracing span creation on proxy requests.
    /// Disable for pure proxy benchmarks to eliminate ~0.4ms overhead per request.
    /// Env: STOA_PROXY_TRACING_ENABLED (default: true)
    #[serde(default = "default_true")]
    pub proxy_tracing_enabled: bool,

    // === Gateway Mode (Phase 8) ===
    /// Gateway deployment mode: edge-mcp, sidecar, proxy, shadow
    /// Env: STOA_GATEWAY_MODE (default: edge-mcp)
    #[serde(default)]
    pub gateway_mode: GatewayMode,

    // === Governance (ADR-012) ===
    /// Enable anti-zombie agent detection
    /// Env: STOA_ZOMBIE_DETECTION_ENABLED (default: true)
    #[serde(default = "default_zombie_detection")]
    pub zombie_detection_enabled: bool,

    /// Session TTL for agent sessions in seconds (default: 600 = 10 min per ADR-012)
    /// Env: STOA_AGENT_SESSION_TTL_SECS
    #[serde(default = "default_agent_session_ttl")]
    pub agent_session_ttl_secs: u64,

    /// Attestation interval (requests between attestations)
    /// Env: STOA_ATTESTATION_INTERVAL
    #[serde(default = "default_attestation_interval")]
    pub attestation_interval: u64,

    // === Shadow Mode ===
    /// Traffic capture source for shadow mode.
    /// Env: STOA_SHADOW_CAPTURE_SOURCE (values: inline | envoy-tap | port-mirror | kafka)
    #[serde(default)]
    pub shadow_capture_source: Option<ShadowCaptureSource>,

    /// Minimum samples before generating UAC
    /// Env: STOA_SHADOW_MIN_SAMPLES
    #[serde(default = "default_shadow_min_samples")]
    pub shadow_min_samples: usize,

    /// GitLab project for UAC MR submission
    /// Env: STOA_SHADOW_GITLAB_PROJECT
    #[serde(default)]
    pub shadow_gitlab_project: Option<String>,

    // === Auto-Registration (ADR-028) ===
    /// Environment identifier for registration (canonical: dev | staging | prod).
    /// Strict parsing — unknown values fail `Config::load()`.
    /// Env: STOA_ENVIRONMENT
    #[serde(default = "default_environment")]
    pub environment: Environment,

    /// Enable auto-registration with Control Plane on startup
    /// Env: STOA_AUTO_REGISTER
    #[serde(default = "default_auto_register")]
    pub auto_register: bool,

    /// Override URL advertised to the Control Plane for admin API calls.
    /// When set, registration uses this instead of auto-detected hostname:port.
    /// Env: STOA_ADVERTISE_URL
    /// Example: http://stoa-gateway.stoa-system.svc.cluster.local:80
    #[serde(default)]
    pub advertise_url: Option<String>,

    /// Heartbeat interval in seconds (default: 30)
    /// Env: STOA_HEARTBEAT_INTERVAL_SECS
    #[serde(default = "default_heartbeat_interval")]
    pub heartbeat_interval_secs: u64,

    /// URL of the third-party gateway managed by this Link/sidecar instance.
    /// Displayed in Console UI. Only relevant for sidecar/connect modes.
    /// Env: STOA_TARGET_GATEWAY_URL
    #[serde(default)]
    pub target_gateway_url: Option<String>,

    /// Public DNS URL of this gateway (e.g. https://mcp.gostoa.dev).
    /// Sent to Control Plane during auto-registration for Console display (CAB-1940).
    /// Env: STOA_GATEWAY_PUBLIC_URL
    #[serde(default)]
    pub gateway_public_url: Option<String>,

    /// Canonical deployment mode sent to the Control Plane.
    /// Separate from `gateway_mode`: a runtime can expose sidecar routes while
    /// being deployed as a remote-agent topology.
    /// Env: STOA_DEPLOYMENT_MODE (edge | connect | sidecar)
    #[serde(default)]
    pub deployment_mode: Option<String>,

    /// Gateway technology STOA fronts or controls.
    /// Env: STOA_TARGET_GATEWAY_TYPE (stoa | kong | webmethods | gravitee | agentgateway)
    #[serde(default)]
    pub target_gateway_type: Option<String>,

    /// Execution topology sent to the Control Plane.
    /// Env: STOA_TOPOLOGY (native-edge | remote-agent | same-pod)
    #[serde(default)]
    pub topology: Option<String>,

    /// JSON evidence for `deployment_mode=sidecar`.
    /// Env: STOA_TOPOLOGY_PROOF
    #[serde(default)]
    pub topology_proof: Option<String>,

    // === Native Tools (Phase 1) ===
    /// Enable native tool implementations (default: true)
    /// Set STOA_NATIVE_TOOLS_ENABLED=false to fallback to proxy mode
    /// Env: STOA_NATIVE_TOOLS_ENABLED
    #[serde(default = "default_native_tools_enabled")]
    pub native_tools_enabled: bool,

    // === Kafka Metering (Phase 3: CAB-1105) ===
    /// Enable Kafka metering (default: false — explicit opt-in)
    /// Env: STOA_KAFKA_ENABLED
    #[serde(default)]
    pub kafka_enabled: bool,

    /// Kafka broker addresses (comma-separated)
    /// Env: STOA_KAFKA_BROKERS
    #[serde(default = "default_kafka_brokers")]
    pub kafka_brokers: String,

    /// Kafka topic for metering events
    /// Env: STOA_KAFKA_METERING_TOPIC
    #[serde(default = "default_kafka_metering_topic")]
    pub kafka_metering_topic: String,

    /// Kafka topic for error snapshots
    /// Env: STOA_KAFKA_ERRORS_TOPIC
    #[serde(default = "default_kafka_errors_topic")]
    pub kafka_errors_topic: String,

    /// Kafka topic for deployment progress events (CAB-1421)
    /// Env: STOA_KAFKA_DEPLOY_PROGRESS_TOPIC
    #[serde(default = "default_kafka_deploy_progress_topic")]
    pub kafka_deploy_progress_topic: String,

    // === K8s CRD Watcher (Phase 7: CAB-1105) ===
    /// Enable K8s CRD watching for dynamic tool registration
    /// Env: STOA_K8S_ENABLED (default: false — explicit opt-in)
    #[serde(default)]
    pub k8s_enabled: bool,

    // === Kafka CNS Event Bridge (CAB-1178) ===
    /// Enable Kafka Cloud Notification Service consumer for real-time event bridge
    /// Env: STOA_KAFKA_CNS_ENABLED (default: false)
    #[serde(default)]
    pub kafka_cns_enabled: bool,

    /// Kafka topics to subscribe for CNS events (comma-separated)
    /// Env: STOA_KAFKA_CNS_TOPICS
    #[serde(default = "default_kafka_cns_topics")]
    pub kafka_cns_topics: String,

    /// Kafka consumer group for CNS event bridge
    /// Env: STOA_KAFKA_CNS_CONSUMER_GROUP
    #[serde(default = "default_kafka_cns_consumer_group")]
    pub kafka_cns_consumer_group: String,

    // === mTLS Certificate Binding (CAB-864) ===
    /// mTLS configuration (nested struct, env vars use the `STOA_MTLS__` prefix
    /// with a **double underscore** separating nested path from field name).
    /// Env: STOA_MTLS__ENABLED, STOA_MTLS__REQUIRE_BINDING, etc.
    #[serde(default)]
    pub mtls: MtlsConfig,

    // === DPoP Sender-Constrained Tokens (CAB-438, RFC 9449) ===
    /// DPoP configuration (nested struct, env vars use the `STOA_DPOP__` prefix
    /// with a **double underscore**).
    /// Env: STOA_DPOP__ENABLED, STOA_DPOP__REQUIRED, etc.
    #[serde(default)]
    pub dpop: crate::auth::dpop::DpopConfig,

    // === Sender-Constraint Middleware (CAB-1607, unified mTLS + DPoP) ===
    /// Sender-constraint configuration (nested struct, env vars use the
    /// `STOA_SENDER_CONSTRAINT__` prefix with a **double underscore**).
    /// Env: STOA_SENDER_CONSTRAINT__ENABLED, STOA_SENDER_CONSTRAINT__DPOP_REQUIRED, etc.
    #[serde(default)]
    pub sender_constraint: SenderConstraintConfig,

    // === Quota Enforcement (Phase 4: CAB-1121) ===
    /// Enable per-consumer quota enforcement
    /// Env: STOA_QUOTA_ENFORCEMENT_ENABLED
    #[serde(default)]
    pub quota_enforcement_enabled: bool,

    /// Quota sync interval in seconds (for background reset check)
    /// Env: STOA_QUOTA_SYNC_INTERVAL_SECS
    #[serde(default = "default_quota_sync_interval")]
    pub quota_sync_interval_secs: u64,

    /// Default rate limit per minute for consumers without explicit plan quota
    /// Env: STOA_QUOTA_DEFAULT_RATE_PER_MINUTE
    #[serde(default = "default_quota_rate_per_minute")]
    pub quota_default_rate_per_minute: u32,

    /// Default daily request limit for consumers without explicit plan quota
    /// Env: STOA_QUOTA_DEFAULT_DAILY_LIMIT
    #[serde(default = "default_quota_daily_limit")]
    pub quota_default_daily_limit: u32,

    // === Access Log ===
    /// Enable structured access log output (JSON via tracing, for Fluent Bit)
    /// Env: STOA_ACCESS_LOG_ENABLED
    #[serde(default = "default_access_log_enabled")]
    pub access_log_enabled: bool,

    // === Route Hot-Reload (CAB-1828) ===
    /// Enable periodic route table reload from Control Plane
    /// Env: STOA_ROUTE_RELOAD_ENABLED
    #[serde(default)]
    pub route_reload_enabled: bool,

    /// Route reload interval in seconds (default: 30)
    /// Env: STOA_ROUTE_RELOAD_INTERVAL_SECS
    #[serde(default = "default_route_reload_interval")]
    pub route_reload_interval_secs: u64,

    // === Guardrails (CAB-707) ===
    /// Enable PII detection in tool call arguments
    /// Env: STOA_GUARDRAILS_PII_ENABLED
    #[serde(default)]
    pub guardrails_pii_enabled: bool,

    /// Redact PII (true) or reject request (false) when PII is found
    /// Env: STOA_GUARDRAILS_PII_REDACT
    #[serde(default = "default_guardrails_pii_redact")]
    pub guardrails_pii_redact: bool,

    /// Enable prompt injection detection in tool call arguments
    /// Env: STOA_GUARDRAILS_INJECTION_ENABLED
    #[serde(default)]
    pub guardrails_injection_enabled: bool,

    /// Enable content filtering for tool call arguments and responses (CAB-1337)
    /// Env: STOA_GUARDRAILS_CONTENT_FILTER_ENABLED
    #[serde(default)]
    pub guardrails_content_filter_enabled: bool,

    // === Prompt Guard (CAB-1761) ===
    /// Enable LLM prompt guard (jailbreak, injection, evasion detection)
    /// Env: STOA_PROMPT_GUARD_ENABLED
    #[serde(default)]
    pub prompt_guard_enabled: bool,

    /// Action when prompt guard detects a threat: block, warn, log_only
    /// Env: STOA_PROMPT_GUARD_ACTION
    #[serde(default)]
    pub prompt_guard_action: crate::guardrails::PromptGuardAction,

    // === RAG Injector (CAB-1761) ===
    /// Enable RAG context injection for prompts
    /// Env: STOA_RAG_INJECTOR_ENABLED
    #[serde(default)]
    pub rag_injector_enabled: bool,

    /// Maximum RAG context length in characters
    /// Env: STOA_RAG_MAX_CONTEXT_LENGTH
    #[serde(default = "default_rag_max_context_length")]
    pub rag_max_context_length: usize,

    /// RAG source request timeout in milliseconds
    /// Env: STOA_RAG_SOURCE_TIMEOUT_MS
    #[serde(default = "default_rag_source_timeout_ms")]
    pub rag_source_timeout_ms: u64,

    /// Maximum number of RAG context chunks to include
    /// Env: STOA_RAG_MAX_CHUNKS
    #[serde(default = "default_rag_max_chunks")]
    pub rag_max_chunks: usize,

    // === Token Budget (CAB-1337 Phase 2) ===
    /// Enable per-tenant token budget tracking
    /// Env: STOA_TOKEN_BUDGET_ENABLED
    #[serde(default)]
    pub token_budget_enabled: bool,

    /// Default token budget per tenant per window (in tokens, ~4 chars each)
    /// Env: STOA_TOKEN_BUDGET_DEFAULT_LIMIT
    #[serde(default = "default_token_budget_limit")]
    pub token_budget_default_limit: u64,

    /// Sliding window duration in hours
    /// Env: STOA_TOKEN_BUDGET_WINDOW_HOURS
    #[serde(default = "default_token_budget_window_hours")]
    pub token_budget_window_hours: u64,

    // === Fallback Chain (CAB-708) ===
    /// Enable fallback chain for tool execution
    /// Env: STOA_FALLBACK_ENABLED
    #[serde(default)]
    pub fallback_enabled: bool,

    /// JSON-encoded fallback chains per tool
    /// Env: STOA_FALLBACK_CHAINS (e.g. '{"tool_a":["tool_a_v2","tool_a_readonly"]}')
    #[serde(default)]
    pub fallback_chains: Option<String>,

    /// Timeout in milliseconds for each fallback attempt
    /// Env: STOA_FALLBACK_TIMEOUT_MS
    #[serde(default = "default_fallback_timeout_ms")]
    pub fallback_timeout_ms: u64,

    // === Classification Enforcement (CAB-1299) ===
    /// Enable classification-based enforcement for contract routes (soft mode: log only).
    /// Env: STOA_CLASSIFICATION_ENFORCEMENT_ENABLED
    #[serde(default)]
    pub classification_enforcement_enabled: bool,

    // === Tool Discovery (CAB-1317) ===
    /// TTL in seconds before tenant tools are considered stale (default: 300s = 5 min).
    /// Env: STOA_TOOL_REFRESH_TTL_SECS
    #[serde(default = "default_tool_refresh_ttl_secs")]
    pub tool_refresh_ttl_secs: u64,

    /// Max staleness in seconds before degraded response (default: 1800s = 30 min).
    /// Council adjustment #1: hard cap prevents serving indefinitely stale data.
    /// Env: STOA_TOOL_MAX_STALENESS_SECS
    #[serde(default = "default_tool_max_staleness_secs")]
    pub tool_max_staleness_secs: u64,

    /// Catalog tool expansion mode (CAB-2113 Phase 0).
    /// `coarse` (default) → one `{action, params}` tool per API (legacy behaviour).
    /// `per-op` → one tool per OpenAPI operation via `/apis/expanded`.
    /// Env: STOA_TOOL_EXPANSION_MODE
    #[serde(default)]
    pub tool_expansion_mode: ExpansionMode,

    // === Per-Upstream Circuit Breaker (CAB-362) ===
    /// Failure threshold before opening circuit (default: 5)
    /// Env: STOA_CB_FAILURE_THRESHOLD
    #[serde(default = "default_cb_failure_threshold")]
    pub cb_failure_threshold: u32,

    /// Reset timeout in seconds before trying half-open (default: 30)
    /// Env: STOA_CB_RESET_TIMEOUT_SECS
    #[serde(default = "default_cb_reset_timeout_secs")]
    pub cb_reset_timeout_secs: u64,

    /// Successes needed in half-open to close circuit (default: 2)
    /// Env: STOA_CB_SUCCESS_THRESHOLD
    #[serde(default = "default_cb_success_threshold")]
    pub cb_success_threshold: u32,

    // === Skills (CAB-1314) ===
    /// Enable skill context injection into tool calls (default: false)
    /// Env: STOA_SKILL_CONTEXT_ENABLED
    #[serde(default)]
    pub skill_context_enabled: bool,

    /// TTL in seconds for skill resolver cache (default: 300 = 5 min)
    /// Env: STOA_SKILL_CACHE_TTL_SECS
    #[serde(default = "default_skill_cache_ttl")]
    pub skill_cache_ttl_secs: u64,

    /// Max merged skill context size in bytes (default: 8192).
    /// Instructions exceeding this limit are truncated.
    /// Env: STOA_SKILL_CONTEXT_MAX_BYTES
    #[serde(default = "default_skill_context_max_bytes")]
    pub skill_context_max_bytes: usize,

    /// Header name for injecting skill context into DynamicTool calls.
    /// Env: STOA_SKILL_CONTEXT_HEADER
    #[serde(default = "default_skill_context_header")]
    pub skill_context_header: String,

    // === Federation (CAB-1362) ===
    /// Enable federation routing for sub-accounts (default: false)
    /// Env: STOA_FEDERATION_ENABLED
    #[serde(default)]
    pub federation_enabled: bool,

    /// TTL in seconds for federation allow-list cache (default: 300 = 5 min)
    /// Env: STOA_FEDERATION_CACHE_TTL_SECS
    #[serde(default = "default_federation_cache_ttl")]
    pub federation_cache_ttl_secs: u64,

    /// Max entries in federation allow-list cache (default: 10000)
    /// Env: STOA_FEDERATION_CACHE_MAX_ENTRIES
    #[serde(default = "default_federation_cache_max_entries")]
    pub federation_cache_max_entries: u64,

    /// Configured upstream MCP servers for federation (CAB-1752)
    /// Env: STOA_FEDERATION_UPSTREAMS (JSON array)
    #[serde(default)]
    pub federation_upstreams: Vec<FederationUpstreamConfig>,

    /// Max entries in prompt cache (default: 1000)
    /// Env: STOA_PROMPT_CACHE_MAX_ENTRIES
    #[serde(default = "default_prompt_cache_max_entries")]
    pub prompt_cache_max_entries: u64,

    /// Prompt cache TTL in seconds (default: 3600 = 1 hour)
    /// Env: STOA_PROMPT_CACHE_TTL_SECS
    #[serde(default = "default_prompt_cache_ttl_secs")]
    pub prompt_cache_ttl_secs: u64,

    /// Directory to watch for prompt/rule file changes (triggers cache invalidation)
    /// Env: STOA_PROMPT_CACHE_WATCH_DIR
    #[serde(default)]
    pub prompt_cache_watch_dir: Option<String>,

    // === Budget Enforcement (CAB-1456) ===
    /// Enable department budget enforcement (429 when over budget).
    /// Env: STOA_BUDGET_ENFORCEMENT_ENABLED
    #[serde(default)]
    pub budget_enforcement_enabled: bool,

    /// Cache TTL in seconds for budget status refresh from CP API (default: 60).
    /// Env: STOA_BUDGET_CACHE_TTL_SECS
    #[serde(default = "default_budget_cache_ttl")]
    pub budget_cache_ttl_secs: u64,

    /// Billing API URL for budget checks (defaults to control_plane_url).
    /// Env: STOA_BILLING_API_URL
    #[serde(default)]
    pub billing_api_url: Option<String>,

    // === Lazy MCP Discovery (CAB-1552) ===
    /// TTL in seconds for MCP upstream discovery cache (default: 300 = 5 min)
    /// Env: STOA_MCP_DISCOVERY_CACHE_TTL_SECS
    #[serde(default = "default_mcp_discovery_cache_ttl_secs")]
    pub mcp_discovery_cache_ttl_secs: u64,

    /// Max entries in MCP upstream discovery cache (default: 256)
    /// Env: STOA_MCP_DISCOVERY_CACHE_MAX_ENTRIES
    #[serde(default = "default_mcp_discovery_cache_max_entries")]
    pub mcp_discovery_cache_max_entries: u64,

    // === LLM Contracts (CAB-709) ===
    /// Enable LLM contract endpoint expansion (default: false)
    /// Env: STOA_LLM_ENABLED
    #[serde(default)]
    pub llm_enabled: bool,

    /// Default timeout in milliseconds for LLM backend calls
    /// Env: STOA_LLM_DEFAULT_TIMEOUT_MS
    #[serde(default = "default_llm_timeout_ms")]
    pub llm_default_timeout_ms: u64,

    // === LLM Provider Router (CAB-1487) ===
    /// LLM provider router configuration (nested struct, env vars use the
    /// `STOA_LLM_ROUTER__` prefix with a **double underscore**).
    /// Env: STOA_LLM_ROUTER__DEFAULT_STRATEGY, STOA_LLM_ROUTER__BUDGET_LIMIT_USD
    #[serde(default)]
    pub llm_router: LlmRouterConfig,

    // === HEGEMON Supervision (CAB-1636) ===
    /// Enable supervision tier enforcement for HEGEMON workers.
    /// Env: STOA_SUPERVISION_ENABLED
    #[serde(default)]
    pub supervision_enabled: bool,

    /// Webhook URL for CO-PILOT tier mutation notifications (fire-and-forget).
    /// Env: STOA_SUPERVISION_WEBHOOK_URL
    #[serde(default)]
    pub supervision_webhook_url: Option<String>,

    /// Default supervision tier when X-Hegemon-Supervision header is absent.
    /// Canonical values: `autopilot` (default), `copilot`, `command`.
    /// Accepts `co-pilot` as a deprecated alias for parity with
    /// `SupervisionTier::from_header`.
    /// Env: STOA_SUPERVISION_DEFAULT_TIER
    #[serde(default = "default_supervision_tier")]
    pub supervision_default_tier: SupervisionDefaultTier,

    // === LLM Proxy (CAB-1568: STOA Dogfood) ===
    /// Enable the LLM API proxy (passthrough to upstream LLM provider).
    /// Env: STOA_LLM_PROXY_ENABLED
    #[serde(default)]
    pub llm_proxy_enabled: bool,

    /// Upstream LLM API base URL.
    /// Env: STOA_LLM_PROXY_UPSTREAM_URL
    #[serde(default = "default_llm_proxy_upstream_url")]
    pub llm_proxy_upstream_url: String,

    /// Real API key for the upstream LLM provider.
    /// Env: STOA_LLM_PROXY_API_KEY
    #[serde(default)]
    pub llm_proxy_api_key: Option<String>,

    /// Timeout in seconds for upstream LLM calls (default: 300).
    /// Env: STOA_LLM_PROXY_TIMEOUT_SECS
    #[serde(default = "default_llm_proxy_timeout_secs")]
    pub llm_proxy_timeout_secs: u64,

    /// Control Plane URL for usage recording (defaults to control_plane_url).
    /// Env: STOA_LLM_PROXY_METERING_URL
    #[serde(default)]
    pub llm_proxy_metering_url: Option<String>,

    /// Default LLM proxy provider format (canonical: `anthropic` | `mistral`
    /// | `openai`). Controls header injection and response parsing for the
    /// default upstream.
    /// Env: STOA_LLM_PROXY_PROVIDER
    #[serde(default)]
    pub llm_proxy_provider: Option<LlmProxyProvider>,

    /// API key for Mistral upstream (when provider=mistral or for /v1/chat/completions).
    /// Env: STOA_LLM_PROXY_MISTRAL_API_KEY
    #[serde(default)]
    pub llm_proxy_mistral_api_key: Option<String>,

    /// Upstream URL for Mistral API (default: https://api.mistral.ai).
    /// Env: STOA_LLM_PROXY_MISTRAL_UPSTREAM_URL
    #[serde(default = "default_llm_proxy_mistral_upstream_url")]
    pub llm_proxy_mistral_upstream_url: String,

    /// Skip API key validation against Control Plane (local dogfood mode).
    /// When true, the LLM proxy accepts any API key without CP subscription check.
    /// NEVER enable in production — use only for local `stoa-dogfood.sh` testing.
    /// Env: STOA_LLM_PROXY_SKIP_VALIDATION
    #[serde(default)]
    pub llm_proxy_skip_validation: bool,

    // === API Proxy — Internal Dogfooding (CAB-1722) ===
    /// API proxy configuration for routing internal API calls through the gateway.
    /// Each backend (Linear, GitHub, Slack, etc.) is individually toggled.
    /// Nested struct: env vars use the `STOA_API_PROXY__` prefix with a
    /// **double underscore** (e.g. `STOA_API_PROXY__ENABLED=true`).
    #[serde(default)]
    pub api_proxy: ApiProxyConfig,

    // === HEGEMON Agent Gateway (CAB-1709) ===
    /// Enable HEGEMON agent gateway module (default: false — explicit opt-in).
    /// Kill switch: set to false to disable all HEGEMON endpoints.
    /// Env: STOA_HEGEMON_ENABLED
    #[serde(default)]
    pub hegemon_enabled: bool,

    /// Daily budget limit in USD per agent (default: 50.0).
    /// Env: STOA_HEGEMON_BUDGET_DAILY_USD
    #[serde(default = "default_hegemon_budget_daily_usd")]
    pub hegemon_budget_daily_usd: f64,

    /// Warning percentage for budget alerts (default: 0.8 = 80%).
    /// Env: STOA_HEGEMON_BUDGET_WARN_PCT
    #[serde(default = "default_hegemon_budget_warn_pct")]
    pub hegemon_budget_warn_pct: f64,

    // === A2A Protocol (CAB-1754) ===
    /// Enable A2A (Agent-to-Agent) protocol support (default: false).
    /// Env: STOA_A2A_ENABLED
    #[serde(default)]
    pub a2a_enabled: bool,

    /// Max agents in the A2A registry (default: 1000).
    /// Env: STOA_A2A_MAX_AGENTS
    #[serde(default = "default_a2a_max_agents")]
    pub a2a_max_agents: usize,

    /// Max in-flight tasks in the A2A registry (default: 10000).
    /// Env: STOA_A2A_MAX_TASKS
    #[serde(default = "default_a2a_max_tasks")]
    pub a2a_max_tasks: usize,

    // === SOAP/XML Bridge (CAB-1762) ===
    /// Enable SOAP proxy passthrough (default: false).
    /// Env: STOA_SOAP_PROXY_ENABLED
    #[serde(default)]
    pub soap_proxy_enabled: bool,

    /// Enable SOAP→MCP bridge (auto-register SOAP operations as MCP tools).
    /// Env: STOA_SOAP_BRIDGE_ENABLED
    #[serde(default)]
    pub soap_bridge_enabled: bool,

    // === gRPC Protocol Support (CAB-1755) ===
    /// Enable gRPC proxy passthrough (default: false).
    /// Env: STOA_GRPC_PROXY_ENABLED
    #[serde(default)]
    pub grpc_proxy_enabled: bool,

    /// Enable gRPC→MCP bridge (auto-register gRPC methods as MCP tools).
    /// Env: STOA_GRPC_BRIDGE_ENABLED
    #[serde(default)]
    pub grpc_bridge_enabled: bool,

    // === GraphQL Protocol Support (CAB-1756) ===
    /// Enable GraphQL proxy passthrough (default: false).
    /// Env: STOA_GRAPHQL_PROXY_ENABLED
    #[serde(default)]
    pub graphql_proxy_enabled: bool,

    /// Enable GraphQL→MCP bridge (auto-register queries/mutations as MCP tools).
    /// Env: STOA_GRAPHQL_BRIDGE_ENABLED
    #[serde(default)]
    pub graphql_bridge_enabled: bool,

    // === Kafka Event Bridge (CAB-1757) ===
    /// Enable Kafka→MCP bridge tools (publish/subscribe via MCP).
    /// Env: STOA_KAFKA_BRIDGE_ENABLED
    #[serde(default)]
    pub kafka_bridge_enabled: bool,

    // === Plugin SDK (CAB-1759) ===
    /// Enable Plugin SDK for custom gateway plugins.
    /// Env: STOA_PLUGIN_SDK_ENABLED
    #[serde(default)]
    pub plugin_sdk_enabled: bool,

    // === TCP Early Filter (CAB-1830) ===
    /// Comma-separated IPs/CIDRs to block at TCP level (before HTTP processing).
    /// Env: STOA_IP_BLOCKLIST
    #[serde(default)]
    pub ip_blocklist: String,

    /// Path to file with one IP/CIDR per line (lines starting with # are ignored).
    /// Env: STOA_IP_BLOCKLIST_FILE
    #[serde(default)]
    pub ip_blocklist_file: Option<String>,

    /// Max new TCP connections per second per IP (token bucket). 0 = disabled.
    /// Env: STOA_TCP_RATE_LIMIT_PER_IP
    #[serde(default)]
    pub tcp_rate_limit_per_ip: Option<f64>,

    // === Memory Budget (CAB-1829) ===
    /// Process memory limit in MB. Backpressure (503) activates at 80% of this limit.
    /// Env: STOA_MEMORY_LIMIT_MB
    #[serde(default = "default_memory_limit_mb")]
    pub memory_limit_mb: u64,

    // === Error Snapshots (CAB-1645) ===
    /// Enable opt-in error snapshot capture for 5xx responses.
    /// When enabled, request/response body excerpts are captured with PII masking.
    /// Env: STOA_SNAPSHOT_ENABLED
    #[serde(default)]
    pub snapshot_enabled: bool,

    /// Maximum number of snapshots to keep in the ring buffer.
    /// Env: STOA_SNAPSHOT_MAX_COUNT
    #[serde(default = "default_snapshot_max_count")]
    pub snapshot_max_count: usize,

    /// Maximum age of snapshots in seconds before eviction.
    /// Env: STOA_SNAPSHOT_MAX_AGE_SECS
    #[serde(default = "default_snapshot_max_age_secs")]
    pub snapshot_max_age_secs: u64,

    /// Maximum bytes to capture from request/response bodies.
    /// Env: STOA_SNAPSHOT_BODY_MAX_BYTES
    #[serde(default = "default_snapshot_body_max_bytes")]
    pub snapshot_body_max_bytes: usize,

    /// Extra regex patterns to treat as PII during snapshot masking.
    /// Env: STOA_SNAPSHOT_EXTRA_PII_PATTERNS (comma-separated or JSON array)
    #[serde(default, deserialize_with = "self::deserializers::string_list")]
    pub snapshot_extra_pii_patterns: Vec<String>,
}

impl fmt::Debug for Config {
    /// Custom `Debug` that redacts every secret-bearing field.
    ///
    /// Any `Option<String>` field that holds a credential (JWT secret, client
    /// secret, admin password, API token, webhook secret, API key) is rendered
    /// as `Some(<redacted>)` / `None` so that `tracing::debug!(?config)` or
    /// `panic!("{:?}", config)` cannot leak the value to structured logs.
    /// Non-secret fields are rendered normally.
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        use self::redact::debug_redact_opt_string as r;

        f.debug_struct("Config")
            .field("port", &self.port)
            .field("host", &self.host)
            .field("jwt_secret", &r(&self.jwt_secret))
            .field("jwt_issuer", &self.jwt_issuer)
            .field("keycloak_url", &self.keycloak_url)
            .field("keycloak_realm", &self.keycloak_realm)
            .field("keycloak_client_id", &self.keycloak_client_id)
            .field("keycloak_client_secret", &r(&self.keycloak_client_secret))
            .field("keycloak_admin_password", &r(&self.keycloak_admin_password))
            .field("keycloak_internal_url", &self.keycloak_internal_url)
            .field("gateway_external_url", &self.gateway_external_url)
            .field("control_plane_url", &self.control_plane_url)
            .field("control_plane_api_key", &r(&self.control_plane_api_key))
            .field("admin_api_token", &r(&self.admin_api_token))
            .field("gitlab_url", &self.gitlab_url)
            .field("gitlab_api_url", &self.gitlab_api_url)
            .field("gitlab_token", &r(&self.gitlab_token))
            .field("gitlab_project_id", &self.gitlab_project_id)
            .field("github_token", &r(&self.github_token))
            .field("github_org", &self.github_org)
            .field("github_catalog_repo", &self.github_catalog_repo)
            .field("github_gitops_repo", &self.github_gitops_repo)
            .field("github_webhook_secret", &r(&self.github_webhook_secret))
            .field("git_provider", &self.git_provider)
            .field("rate_limit_default", &self.rate_limit_default)
            .field("rate_limit_window_seconds", &self.rate_limit_window_seconds)
            .field("mcp_session_ttl_minutes", &self.mcp_session_ttl_minutes)
            .field("websocket_enabled", &self.websocket_enabled)
            .field("ws_proxy_enabled", &self.ws_proxy_enabled)
            .field(
                "ws_proxy_rate_limit_per_second",
                &self.ws_proxy_rate_limit_per_second,
            )
            .field("ws_proxy_rate_limit_burst", &self.ws_proxy_rate_limit_burst)
            .field("policy_path", &self.policy_path)
            .field("policy_enabled", &self.policy_enabled)
            .field("log_level", &self.log_level)
            .field("log_format", &self.log_format)
            .field("otel_endpoint", &self.otel_endpoint)
            .field("otel_enabled", &self.otel_enabled)
            .field("otel_sample_rate", &self.otel_sample_rate)
            .field("detailed_tracing", &self.detailed_tracing)
            .field("proxy_metrics_enabled", &self.proxy_metrics_enabled)
            .field("proxy_tracing_enabled", &self.proxy_tracing_enabled)
            .field("gateway_mode", &self.gateway_mode)
            .field("zombie_detection_enabled", &self.zombie_detection_enabled)
            .field("agent_session_ttl_secs", &self.agent_session_ttl_secs)
            .field("attestation_interval", &self.attestation_interval)
            .field("shadow_capture_source", &self.shadow_capture_source)
            .field("shadow_min_samples", &self.shadow_min_samples)
            .field("shadow_gitlab_project", &self.shadow_gitlab_project)
            .field("environment", &self.environment)
            .field("auto_register", &self.auto_register)
            .field("advertise_url", &self.advertise_url)
            .field("heartbeat_interval_secs", &self.heartbeat_interval_secs)
            .field("target_gateway_url", &self.target_gateway_url)
            .field("gateway_public_url", &self.gateway_public_url)
            .field("deployment_mode", &self.deployment_mode)
            .field("target_gateway_type", &self.target_gateway_type)
            .field("topology", &self.topology)
            .field("topology_proof", &self.topology_proof)
            .field("native_tools_enabled", &self.native_tools_enabled)
            .field("kafka_enabled", &self.kafka_enabled)
            .field("kafka_brokers", &self.kafka_brokers)
            .field("kafka_metering_topic", &self.kafka_metering_topic)
            .field("kafka_errors_topic", &self.kafka_errors_topic)
            .field(
                "kafka_deploy_progress_topic",
                &self.kafka_deploy_progress_topic,
            )
            .field("k8s_enabled", &self.k8s_enabled)
            .field("kafka_cns_enabled", &self.kafka_cns_enabled)
            .field("kafka_cns_topics", &self.kafka_cns_topics)
            .field("kafka_cns_consumer_group", &self.kafka_cns_consumer_group)
            .field("mtls", &self.mtls)
            .field("dpop", &self.dpop)
            .field("sender_constraint", &self.sender_constraint)
            .field("quota_enforcement_enabled", &self.quota_enforcement_enabled)
            .field("quota_sync_interval_secs", &self.quota_sync_interval_secs)
            .field(
                "quota_default_rate_per_minute",
                &self.quota_default_rate_per_minute,
            )
            .field("quota_default_daily_limit", &self.quota_default_daily_limit)
            .field("access_log_enabled", &self.access_log_enabled)
            .field("route_reload_enabled", &self.route_reload_enabled)
            .field(
                "route_reload_interval_secs",
                &self.route_reload_interval_secs,
            )
            .field("guardrails_pii_enabled", &self.guardrails_pii_enabled)
            .field("guardrails_pii_redact", &self.guardrails_pii_redact)
            .field(
                "guardrails_injection_enabled",
                &self.guardrails_injection_enabled,
            )
            .field(
                "guardrails_content_filter_enabled",
                &self.guardrails_content_filter_enabled,
            )
            .field("prompt_guard_enabled", &self.prompt_guard_enabled)
            .field("prompt_guard_action", &self.prompt_guard_action)
            .field("rag_injector_enabled", &self.rag_injector_enabled)
            .field("rag_max_context_length", &self.rag_max_context_length)
            .field("rag_source_timeout_ms", &self.rag_source_timeout_ms)
            .field("rag_max_chunks", &self.rag_max_chunks)
            .field("token_budget_enabled", &self.token_budget_enabled)
            .field(
                "token_budget_default_limit",
                &self.token_budget_default_limit,
            )
            .field("token_budget_window_hours", &self.token_budget_window_hours)
            .field("fallback_enabled", &self.fallback_enabled)
            .field("fallback_chains", &self.fallback_chains)
            .field("fallback_timeout_ms", &self.fallback_timeout_ms)
            .field(
                "classification_enforcement_enabled",
                &self.classification_enforcement_enabled,
            )
            .field("tool_refresh_ttl_secs", &self.tool_refresh_ttl_secs)
            .field("tool_max_staleness_secs", &self.tool_max_staleness_secs)
            .field("tool_expansion_mode", &self.tool_expansion_mode)
            .field("cb_failure_threshold", &self.cb_failure_threshold)
            .field("cb_reset_timeout_secs", &self.cb_reset_timeout_secs)
            .field("cb_success_threshold", &self.cb_success_threshold)
            .field("skill_context_enabled", &self.skill_context_enabled)
            .field("skill_cache_ttl_secs", &self.skill_cache_ttl_secs)
            .field("skill_context_max_bytes", &self.skill_context_max_bytes)
            .field("skill_context_header", &self.skill_context_header)
            .field("federation_enabled", &self.federation_enabled)
            .field("federation_cache_ttl_secs", &self.federation_cache_ttl_secs)
            .field(
                "federation_cache_max_entries",
                &self.federation_cache_max_entries,
            )
            .field("federation_upstreams", &self.federation_upstreams)
            .field("prompt_cache_max_entries", &self.prompt_cache_max_entries)
            .field("prompt_cache_ttl_secs", &self.prompt_cache_ttl_secs)
            .field("prompt_cache_watch_dir", &self.prompt_cache_watch_dir)
            .field(
                "budget_enforcement_enabled",
                &self.budget_enforcement_enabled,
            )
            .field("budget_cache_ttl_secs", &self.budget_cache_ttl_secs)
            .field("billing_api_url", &self.billing_api_url)
            .field(
                "mcp_discovery_cache_ttl_secs",
                &self.mcp_discovery_cache_ttl_secs,
            )
            .field(
                "mcp_discovery_cache_max_entries",
                &self.mcp_discovery_cache_max_entries,
            )
            .field("llm_enabled", &self.llm_enabled)
            .field("llm_default_timeout_ms", &self.llm_default_timeout_ms)
            .field("llm_router", &self.llm_router)
            .field("supervision_enabled", &self.supervision_enabled)
            .field("supervision_webhook_url", &self.supervision_webhook_url)
            .field("supervision_default_tier", &self.supervision_default_tier)
            .field("llm_proxy_enabled", &self.llm_proxy_enabled)
            .field("llm_proxy_upstream_url", &self.llm_proxy_upstream_url)
            .field("llm_proxy_api_key", &r(&self.llm_proxy_api_key))
            .field("llm_proxy_timeout_secs", &self.llm_proxy_timeout_secs)
            .field("llm_proxy_metering_url", &self.llm_proxy_metering_url)
            .field("llm_proxy_provider", &self.llm_proxy_provider)
            .field(
                "llm_proxy_mistral_api_key",
                &r(&self.llm_proxy_mistral_api_key),
            )
            .field(
                "llm_proxy_mistral_upstream_url",
                &self.llm_proxy_mistral_upstream_url,
            )
            .field("llm_proxy_skip_validation", &self.llm_proxy_skip_validation)
            .field("api_proxy", &self.api_proxy)
            .field("hegemon_enabled", &self.hegemon_enabled)
            .field("hegemon_budget_daily_usd", &self.hegemon_budget_daily_usd)
            .field("hegemon_budget_warn_pct", &self.hegemon_budget_warn_pct)
            .field("a2a_enabled", &self.a2a_enabled)
            .field("a2a_max_agents", &self.a2a_max_agents)
            .field("a2a_max_tasks", &self.a2a_max_tasks)
            .field("soap_proxy_enabled", &self.soap_proxy_enabled)
            .field("soap_bridge_enabled", &self.soap_bridge_enabled)
            .field("grpc_proxy_enabled", &self.grpc_proxy_enabled)
            .field("grpc_bridge_enabled", &self.grpc_bridge_enabled)
            .field("graphql_proxy_enabled", &self.graphql_proxy_enabled)
            .field("graphql_bridge_enabled", &self.graphql_bridge_enabled)
            .field("kafka_bridge_enabled", &self.kafka_bridge_enabled)
            .field("plugin_sdk_enabled", &self.plugin_sdk_enabled)
            .field("ip_blocklist", &self.ip_blocklist)
            .field("ip_blocklist_file", &self.ip_blocklist_file)
            .field("tcp_rate_limit_per_ip", &self.tcp_rate_limit_per_ip)
            .field("memory_limit_mb", &self.memory_limit_mb)
            .field("snapshot_enabled", &self.snapshot_enabled)
            .field("snapshot_max_count", &self.snapshot_max_count)
            .field("snapshot_max_age_secs", &self.snapshot_max_age_secs)
            .field("snapshot_body_max_bytes", &self.snapshot_body_max_bytes)
            .field(
                "snapshot_extra_pii_patterns",
                &self.snapshot_extra_pii_patterns,
            )
            .finish()
    }
}

#[cfg(test)]
mod tests;
