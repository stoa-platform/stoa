//! Configuration with Figment
//!
//! Supports:
//! - config.yaml file (optional)
//! - Environment variable overrides (STOA_ prefix)
//! - Backward compatible with existing envy-based env vars

use figment::{
    providers::{Env, Format, Serialized, Yaml},
    Figment,
};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::Path;
use tracing::info;

use crate::mode::GatewayMode;

/// Gateway configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
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

    // === Rate Limiting ===
    #[serde(default)]
    pub rate_limit_default: Option<usize>,

    #[serde(default)]
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
    #[serde(default)]
    pub log_level: Option<String>,

    #[serde(default)]
    pub log_format: Option<String>,

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
    /// Traffic capture source for shadow mode
    /// Env: STOA_SHADOW_CAPTURE_SOURCE (inline, envoy-tap, port-mirror, kafka)
    #[serde(default)]
    pub shadow_capture_source: Option<String>,

    /// Minimum samples before generating UAC
    /// Env: STOA_SHADOW_MIN_SAMPLES
    #[serde(default = "default_shadow_min_samples")]
    pub shadow_min_samples: usize,

    /// GitLab project for UAC MR submission
    /// Env: STOA_SHADOW_GITLAB_PROJECT
    #[serde(default)]
    pub shadow_gitlab_project: Option<String>,

    // === Auto-Registration (ADR-028) ===
    /// Environment identifier for registration (dev, staging, prod)
    /// Env: STOA_ENVIRONMENT
    #[serde(default = "default_environment")]
    pub environment: String,

    /// Enable auto-registration with Control Plane on startup
    /// Env: STOA_AUTO_REGISTER
    #[serde(default = "default_auto_register")]
    pub auto_register: bool,

    /// Heartbeat interval in seconds (default: 30)
    /// Env: STOA_HEARTBEAT_INTERVAL_SECS
    #[serde(default = "default_heartbeat_interval")]
    pub heartbeat_interval_secs: u64,

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
    /// mTLS configuration (nested struct, STOA_MTLS_ prefix)
    /// Env: STOA_MTLS_ENABLED, STOA_MTLS_REQUIRE_BINDING, etc.
    #[serde(default)]
    pub mtls: MtlsConfig,

    // === DPoP Sender-Constrained Tokens (CAB-438, RFC 9449) ===
    /// DPoP configuration (nested struct, STOA_DPOP_ prefix)
    /// Env: STOA_DPOP_ENABLED, STOA_DPOP_REQUIRED, etc.
    #[serde(default)]
    pub dpop: crate::auth::dpop::DpopConfig,

    // === Sender-Constraint Middleware (CAB-1607, unified mTLS + DPoP) ===
    /// Sender-constraint configuration (nested struct, STOA_SENDER_CONSTRAINT_ prefix)
    /// Env: STOA_SENDER_CONSTRAINT_ENABLED, STOA_SENDER_CONSTRAINT_DPOP_REQUIRED, etc.
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
    /// LLM provider router configuration (nested struct, STOA_LLM_ROUTER_ prefix).
    /// Env: STOA_LLM_ROUTER_DEFAULT_STRATEGY, STOA_LLM_ROUTER_BUDGET_LIMIT_USD
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
    /// Values: "autopilot" (default), "copilot", "command".
    /// Env: STOA_SUPERVISION_DEFAULT_TIER
    #[serde(default = "default_supervision_tier")]
    pub supervision_default_tier: String,

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

    /// Default LLM proxy provider format: "anthropic" | "mistral" | "openai".
    /// Controls header injection and response parsing for the default upstream.
    /// Env: STOA_LLM_PROXY_PROVIDER
    #[serde(default)]
    pub llm_proxy_provider: Option<String>,

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
}

/// LLM provider router configuration (CAB-1487)
///
/// Configuration for a single upstream MCP server in federation (CAB-1752).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FederationUpstreamConfig {
    /// Upstream MCP server URL
    pub url: String,
    /// Transport type (default: "sse")
    pub transport: Option<String>,
    /// Optional auth token (never exposed in admin API)
    pub auth_token: Option<String>,
    /// Connection timeout in seconds (default: 30)
    pub timeout_secs: Option<u64>,
}

/// Configures multi-provider LLM routing with cost tracking and budget enforcement.
/// Providers are defined as a list; disabled providers are filtered at startup.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LlmRouterConfig {
    /// Enable the LLM provider router (default: false).
    /// Env: STOA_LLM_ROUTER_ENABLED
    #[serde(default)]
    pub enabled: bool,

    /// Default routing strategy.
    /// Env: STOA_LLM_ROUTER_DEFAULT_STRATEGY
    #[serde(default)]
    pub default_strategy: crate::llm::RoutingStrategy,

    /// Budget limit in USD per billing window. 0 = no limit.
    /// Env: STOA_LLM_ROUTER_BUDGET_LIMIT_USD
    #[serde(default)]
    pub budget_limit_usd: f64,

    /// Provider configurations.
    #[serde(default)]
    pub providers: Vec<crate::llm::ProviderConfig>,

    /// Subscription-to-backend routing map (CAB-1610).
    /// Maps subscription IDs (or plan names) to backend IDs in the provider list.
    /// Enables multi-namespace routing: same API contract, different backends per subscriber.
    #[serde(default)]
    pub subscription_mapping: crate::llm::SubscriptionMapping,
}

impl Default for LlmRouterConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            default_strategy: crate::llm::RoutingStrategy::default(),
            budget_limit_usd: 0.0,
            providers: Vec::new(),
            subscription_mapping: crate::llm::SubscriptionMapping::new(),
        }
    }
}

/// API proxy configuration for internal dogfooding (CAB-1722).
///
/// Routes internal API calls (Linear, GitHub, Slack, Infisical, etc.) through
/// the gateway with OAuth2 auth and credential injection. Each backend is
/// individually toggled via feature flags for incremental rollout.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApiProxyConfig {
    /// Master switch: enable the `/apis/{backend}/*` proxy router.
    /// Env: STOA_API_PROXY_ENABLED
    #[serde(default)]
    pub enabled: bool,

    /// Require OAuth2 authentication for all API proxy requests.
    /// When false, accepts unauthenticated requests (dev mode only).
    /// Env: STOA_API_PROXY_REQUIRE_AUTH
    #[serde(default = "default_api_proxy_require_auth")]
    pub require_auth: bool,

    /// Per-backend configurations, keyed by backend name (e.g., "linear", "github").
    #[serde(default)]
    pub backends: HashMap<String, ProxyBackendConfig>,
}

impl Default for ApiProxyConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            require_auth: default_api_proxy_require_auth(),
            backends: HashMap::new(),
        }
    }
}

/// Configuration for a single proxied backend (CAB-1722).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProxyBackendConfig {
    /// Enable this backend (feature flag for incremental rollout).
    #[serde(default)]
    pub enabled: bool,

    /// Base URL for the upstream backend (e.g., "https://api.linear.app").
    pub base_url: String,

    /// Authentication type for the upstream backend.
    /// Uses the same AuthType as the credential store.
    #[serde(default = "default_proxy_backend_auth_type")]
    pub auth_type: String,

    /// Header name for credential injection (e.g., "Authorization", "X-API-Key").
    #[serde(default = "default_proxy_backend_header")]
    pub auth_header: String,

    /// Rate limit in requests per minute (0 = no limit).
    #[serde(default)]
    pub rate_limit_rpm: u32,

    /// Request timeout in seconds.
    #[serde(default = "default_proxy_backend_timeout_secs")]
    pub timeout_secs: u64,

    /// Enable circuit breaker for this backend.
    #[serde(default = "default_true")]
    pub circuit_breaker_enabled: bool,

    /// Enable direct fallback when gateway is down (critical backends only).
    #[serde(default)]
    pub fallback_direct: bool,

    /// Allowed path prefixes (empty = allow all paths).
    /// Security: prevents proxy abuse by restricting accessible paths.
    #[serde(default)]
    pub allowed_paths: Vec<String>,
}

fn default_api_proxy_require_auth() -> bool {
    true
}

fn default_proxy_backend_auth_type() -> String {
    "bearer".to_string()
}

fn default_proxy_backend_header() -> String {
    "Authorization".to_string()
}

fn default_proxy_backend_timeout_secs() -> u64 {
    30
}

fn default_true() -> bool {
    true
}

fn default_port() -> u16 {
    8080
}

fn default_host() -> String {
    "0.0.0.0".to_string()
}

fn default_session_ttl() -> i64 {
    30
}

fn default_ws_proxy_rate_limit() -> f64 {
    100.0
}

fn default_ws_proxy_burst() -> usize {
    50
}

fn default_gateway_external_url() -> Option<String> {
    Some("http://localhost:8080".to_string())
}

fn default_policy_enabled() -> bool {
    true
}

fn default_zombie_detection() -> bool {
    true
}

fn default_agent_session_ttl() -> u64 {
    600 // 10 minutes per ADR-012
}

fn default_attestation_interval() -> u64 {
    100 // Require attestation every 100 requests
}

fn default_shadow_min_samples() -> usize {
    10 // Minimum samples before pattern is considered stable
}

fn default_environment() -> String {
    "dev".to_string()
}

fn default_auto_register() -> bool {
    true // Auto-register when control_plane_url is set
}

fn default_heartbeat_interval() -> u64 {
    30 // 30 seconds per ADR-028
}

fn default_native_tools_enabled() -> bool {
    true // Phase 1: native tools call CP API directly
}

fn default_kafka_brokers() -> String {
    "redpanda:9092".to_string()
}

fn default_kafka_metering_topic() -> String {
    "stoa.metering".to_string()
}

fn default_kafka_errors_topic() -> String {
    "stoa.errors".to_string()
}

fn default_kafka_deploy_progress_topic() -> String {
    "stoa.deployment.progress".to_string()
}

// === mTLS Config Defaults ===

fn default_mtls_header_verify() -> String {
    "X-SSL-Client-Verify".to_string()
}

fn default_mtls_header_fingerprint() -> String {
    "X-SSL-Client-Fingerprint".to_string()
}

fn default_mtls_header_subject_dn() -> String {
    "X-SSL-Client-S-DN".to_string()
}

fn default_mtls_header_issuer_dn() -> String {
    "X-SSL-Client-I-DN".to_string()
}

fn default_mtls_header_serial() -> String {
    "X-SSL-Client-Serial".to_string()
}

fn default_mtls_header_not_before() -> String {
    "X-SSL-Client-NotBefore".to_string()
}

fn default_mtls_header_not_after() -> String {
    "X-SSL-Client-NotAfter".to_string()
}

fn default_mtls_header_cert() -> String {
    "X-SSL-Client-Cert".to_string()
}

/// mTLS configuration (CAB-864)
///
/// All fields are configurable via STOA_MTLS_* environment variables.
/// Default: disabled (zero overhead when not enabled).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MtlsConfig {
    /// Enable mTLS header extraction and validation
    /// Env: STOA_MTLS_ENABLED
    #[serde(default)]
    pub enabled: bool,

    /// Require certificate-token binding (cnf claim)
    /// Env: STOA_MTLS_REQUIRE_BINDING
    #[serde(default = "default_require_binding")]
    pub require_binding: bool,

    /// Trusted proxy CIDRs (F5 IPs). If empty, all sources accepted.
    /// Env: STOA_MTLS_TRUSTED_PROXIES (comma-separated CIDRs)
    #[serde(default)]
    pub trusted_proxies: Vec<String>,

    /// Allowed certificate issuers (DN strings). If empty, all issuers accepted.
    /// Env: STOA_MTLS_ALLOWED_ISSUERS (comma-separated DNs)
    #[serde(default)]
    pub allowed_issuers: Vec<String>,

    /// Routes that require mTLS (glob patterns). If empty, mTLS is optional on all routes.
    /// Env: STOA_MTLS_REQUIRED_ROUTES (comma-separated patterns)
    #[serde(default)]
    pub required_routes: Vec<String>,

    /// Extract tenant from certificate Subject DN (OU field)
    /// Env: STOA_MTLS_TENANT_FROM_DN
    #[serde(default = "default_tenant_from_dn")]
    pub tenant_from_dn: bool,

    // Header name overrides (for different TLS terminators)
    #[serde(default = "default_mtls_header_verify")]
    pub header_verify: String,

    #[serde(default = "default_mtls_header_fingerprint")]
    pub header_fingerprint: String,

    #[serde(default = "default_mtls_header_subject_dn")]
    pub header_subject_dn: String,

    #[serde(default = "default_mtls_header_issuer_dn")]
    pub header_issuer_dn: String,

    #[serde(default = "default_mtls_header_serial")]
    pub header_serial: String,

    #[serde(default = "default_mtls_header_not_before")]
    pub header_not_before: String,

    #[serde(default = "default_mtls_header_not_after")]
    pub header_not_after: String,

    #[serde(default = "default_mtls_header_cert")]
    pub header_cert: String,
}

fn default_require_binding() -> bool {
    true
}

fn default_tenant_from_dn() -> bool {
    true
}

impl Default for MtlsConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            require_binding: true,
            trusted_proxies: Vec::new(),
            allowed_issuers: Vec::new(),
            required_routes: Vec::new(),
            tenant_from_dn: true,
            header_verify: default_mtls_header_verify(),
            header_fingerprint: default_mtls_header_fingerprint(),
            header_subject_dn: default_mtls_header_subject_dn(),
            header_issuer_dn: default_mtls_header_issuer_dn(),
            header_serial: default_mtls_header_serial(),
            header_not_before: default_mtls_header_not_before(),
            header_not_after: default_mtls_header_not_after(),
            header_cert: default_mtls_header_cert(),
        }
    }
}

// =============================================================================
// Sender-Constraint Configuration (CAB-1607)
// =============================================================================

/// Unified sender-constraint configuration for mTLS + DPoP pipeline.
///
/// When enabled, validates that tokens are bound to the sender via:
/// - mTLS: cnf.x5t#S256 matches client certificate thumbprint (RFC 8705)
/// - DPoP: cnf.jkt matches DPoP proof JWK thumbprint (RFC 9449)
///
/// Per-tenant policy: tenants can require DPoP, mTLS, or both.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct SenderConstraintConfig {
    /// Enable the unified sender-constraint middleware.
    /// Env: STOA_SENDER_CONSTRAINT_ENABLED
    #[serde(default)]
    pub enabled: bool,

    /// Require DPoP proof when cnf.jkt is present in the token.
    /// Env: STOA_SENDER_CONSTRAINT_DPOP_REQUIRED
    #[serde(default)]
    pub dpop_required: bool,

    /// Require mTLS binding when cnf.x5t#S256 is present in the token.
    /// Env: STOA_SENDER_CONSTRAINT_MTLS_REQUIRED
    #[serde(default)]
    pub mtls_required: bool,
}

fn default_otel_enabled() -> bool {
    true // CAB-1831: OTel always on, no-op exporter when STOA_OTEL_ENDPOINT absent
}

fn default_otel_sample_rate() -> f64 {
    1.0 // Sample all traces by default
}

fn default_quota_sync_interval() -> u64 {
    60
}

fn default_quota_rate_per_minute() -> u32 {
    60
}

fn default_quota_daily_limit() -> u32 {
    10_000
}

fn default_access_log_enabled() -> bool {
    true // Enabled by default — structured access logs for observability
}

fn default_guardrails_pii_redact() -> bool {
    true // Redact by default (safer than rejecting)
}

fn default_rag_max_context_length() -> usize {
    4096
}

fn default_rag_source_timeout_ms() -> u64 {
    3000
}

fn default_rag_max_chunks() -> usize {
    5
}

fn default_token_budget_limit() -> u64 {
    500_000 // 500K tokens per window (~2M chars)
}

fn default_token_budget_window_hours() -> u64 {
    1 // 1-hour sliding window
}

fn default_fallback_timeout_ms() -> u64 {
    5000
}

fn default_tool_refresh_ttl_secs() -> u64 {
    300
}

fn default_tool_max_staleness_secs() -> u64 {
    1800
}

fn default_cb_failure_threshold() -> u32 {
    5
}

fn default_cb_reset_timeout_secs() -> u64 {
    30
}

fn default_cb_success_threshold() -> u32 {
    2
}

fn default_kafka_cns_topics() -> String {
    "stoa.api.lifecycle,stoa.deployment.events,stoa.security.alerts,stoa.policy.changes".to_string()
}

fn default_kafka_cns_consumer_group() -> String {
    "stoa-gateway-cns".to_string()
}

fn default_skill_cache_ttl() -> u64 {
    300 // 5 minutes
}

fn default_skill_context_max_bytes() -> usize {
    8192
}

fn default_skill_context_header() -> String {
    "X-Skill-Context".to_string()
}

fn default_federation_cache_ttl() -> u64 {
    300
}

fn default_federation_cache_max_entries() -> u64 {
    10_000
}

fn default_prompt_cache_max_entries() -> u64 {
    1000
}

fn default_prompt_cache_ttl_secs() -> u64 {
    3600
}

fn default_budget_cache_ttl() -> u64 {
    60 // Refresh budget status every 60 seconds
}

fn default_mcp_discovery_cache_ttl_secs() -> u64 {
    300 // 5 minutes
}

fn default_mcp_discovery_cache_max_entries() -> u64 {
    256
}

fn default_supervision_tier() -> String {
    "autopilot".to_string()
}

fn default_llm_timeout_ms() -> u64 {
    30_000
}

fn default_llm_proxy_upstream_url() -> String {
    "https://api.anthropic.com".to_string()
}

fn default_llm_proxy_timeout_secs() -> u64 {
    300
}

fn default_llm_proxy_mistral_upstream_url() -> String {
    "https://api.mistral.ai".to_string()
}

fn default_hegemon_budget_daily_usd() -> f64 {
    50.0
}

fn default_hegemon_budget_warn_pct() -> f64 {
    0.8
}

fn default_a2a_max_agents() -> usize {
    1000
}

fn default_a2a_max_tasks() -> usize {
    10000
}

impl Default for Config {
    fn default() -> Self {
        Self {
            port: default_port(),
            host: default_host(),
            jwt_secret: None,
            jwt_issuer: None,
            keycloak_url: None,
            keycloak_realm: None,
            keycloak_client_id: None,
            keycloak_client_secret: None,
            keycloak_admin_password: None,
            keycloak_internal_url: None,
            gateway_external_url: default_gateway_external_url(),
            control_plane_url: None,
            control_plane_api_key: None,
            admin_api_token: None,
            gitlab_url: None,
            gitlab_api_url: None,
            gitlab_token: None,
            gitlab_project_id: None,
            rate_limit_default: Some(1000),
            rate_limit_window_seconds: Some(60),
            mcp_session_ttl_minutes: default_session_ttl(),
            websocket_enabled: false,
            policy_path: None,
            policy_enabled: default_policy_enabled(),
            log_level: Some("info".to_string()),
            log_format: Some("json".to_string()),
            otel_enabled: default_otel_enabled(),
            otel_endpoint: None,
            otel_sample_rate: default_otel_sample_rate(),
            gateway_mode: GatewayMode::default(),
            zombie_detection_enabled: default_zombie_detection(),
            agent_session_ttl_secs: default_agent_session_ttl(),
            attestation_interval: default_attestation_interval(),
            shadow_capture_source: None,
            shadow_min_samples: default_shadow_min_samples(),
            shadow_gitlab_project: None,
            environment: default_environment(),
            auto_register: default_auto_register(),
            heartbeat_interval_secs: default_heartbeat_interval(),
            native_tools_enabled: default_native_tools_enabled(),
            kafka_enabled: false,
            kafka_brokers: default_kafka_brokers(),
            kafka_metering_topic: default_kafka_metering_topic(),
            kafka_errors_topic: default_kafka_errors_topic(),
            kafka_deploy_progress_topic: default_kafka_deploy_progress_topic(),
            k8s_enabled: false,
            kafka_cns_enabled: false,
            kafka_cns_topics: default_kafka_cns_topics(),
            kafka_cns_consumer_group: default_kafka_cns_consumer_group(),
            mtls: MtlsConfig::default(),
            dpop: crate::auth::dpop::DpopConfig::default(),
            sender_constraint: SenderConstraintConfig::default(),
            quota_enforcement_enabled: false,
            quota_sync_interval_secs: default_quota_sync_interval(),
            quota_default_rate_per_minute: default_quota_rate_per_minute(),
            quota_default_daily_limit: default_quota_daily_limit(),
            access_log_enabled: default_access_log_enabled(),
            guardrails_pii_enabled: false,
            guardrails_pii_redact: default_guardrails_pii_redact(),
            guardrails_injection_enabled: false,
            guardrails_content_filter_enabled: false,
            prompt_guard_enabled: false,
            prompt_guard_action: crate::guardrails::PromptGuardAction::default(),
            rag_injector_enabled: false,
            rag_max_context_length: default_rag_max_context_length(),
            rag_source_timeout_ms: default_rag_source_timeout_ms(),
            rag_max_chunks: default_rag_max_chunks(),
            token_budget_enabled: false,
            token_budget_default_limit: default_token_budget_limit(),
            token_budget_window_hours: default_token_budget_window_hours(),
            fallback_enabled: false,
            fallback_chains: None,
            fallback_timeout_ms: default_fallback_timeout_ms(),
            classification_enforcement_enabled: false,
            tool_refresh_ttl_secs: default_tool_refresh_ttl_secs(),
            tool_max_staleness_secs: default_tool_max_staleness_secs(),
            cb_failure_threshold: default_cb_failure_threshold(),
            cb_reset_timeout_secs: default_cb_reset_timeout_secs(),
            cb_success_threshold: default_cb_success_threshold(),
            skill_context_enabled: false,
            skill_cache_ttl_secs: default_skill_cache_ttl(),
            skill_context_max_bytes: default_skill_context_max_bytes(),
            skill_context_header: default_skill_context_header(),
            federation_enabled: false,
            federation_cache_ttl_secs: default_federation_cache_ttl(),
            federation_cache_max_entries: default_federation_cache_max_entries(),
            federation_upstreams: vec![],
            prompt_cache_max_entries: default_prompt_cache_max_entries(),
            prompt_cache_ttl_secs: default_prompt_cache_ttl_secs(),
            prompt_cache_watch_dir: None,
            budget_enforcement_enabled: false,
            budget_cache_ttl_secs: default_budget_cache_ttl(),
            billing_api_url: None,
            mcp_discovery_cache_ttl_secs: default_mcp_discovery_cache_ttl_secs(),
            mcp_discovery_cache_max_entries: default_mcp_discovery_cache_max_entries(),
            llm_enabled: false,
            llm_default_timeout_ms: default_llm_timeout_ms(),
            llm_router: LlmRouterConfig::default(),
            supervision_enabled: false,
            supervision_webhook_url: None,
            supervision_default_tier: default_supervision_tier(),
            llm_proxy_enabled: false,
            llm_proxy_upstream_url: default_llm_proxy_upstream_url(),
            llm_proxy_api_key: None,
            llm_proxy_timeout_secs: default_llm_proxy_timeout_secs(),
            llm_proxy_metering_url: None,
            llm_proxy_provider: None,
            llm_proxy_mistral_api_key: None,
            llm_proxy_mistral_upstream_url: default_llm_proxy_mistral_upstream_url(),
            llm_proxy_skip_validation: false,
            api_proxy: ApiProxyConfig::default(),
            hegemon_enabled: false,
            hegemon_budget_daily_usd: default_hegemon_budget_daily_usd(),
            hegemon_budget_warn_pct: default_hegemon_budget_warn_pct(),
            a2a_enabled: false,
            a2a_max_agents: default_a2a_max_agents(),
            a2a_max_tasks: default_a2a_max_tasks(),
            ws_proxy_enabled: false,
            ws_proxy_rate_limit_per_second: default_ws_proxy_rate_limit(),
            ws_proxy_rate_limit_burst: default_ws_proxy_burst(),
            soap_proxy_enabled: false,
            soap_bridge_enabled: false,
            grpc_proxy_enabled: false,
            grpc_bridge_enabled: false,
            graphql_proxy_enabled: false,
            graphql_bridge_enabled: false,
            kafka_bridge_enabled: false,
            plugin_sdk_enabled: false,
        }
    }
}

impl Config {
    /// Load configuration from file and environment
    #[allow(clippy::result_large_err)]
    pub fn load() -> Result<Self, figment::Error> {
        let mut figment = Figment::new()
            // Start with defaults
            .merge(Serialized::defaults(Config::default()));

        // Try config.yaml if exists
        let config_paths = ["config.yaml", "config.yml", "/etc/stoa/config.yaml"];
        for path in config_paths {
            if Path::new(path).exists() {
                info!(path = path, "Loading config from file");
                figment = figment.merge(Yaml::file(path));
                break;
            }
        }

        // Environment variables override (STOA_ prefix)
        // e.g., STOA_PORT=9090, STOA_CONTROL_PLANE_URL=http://...
        // No .split("_") — field names use underscores (control_plane_url, not nested)
        figment = figment.merge(Env::prefixed("STOA_"));

        // Legacy env vars (backward compat with envy)
        figment = figment.merge(Env::raw().only(&[
            "PORT",
            "HOST",
            "JWT_SECRET",
            "KEYCLOAK_URL",
            "KEYCLOAK_REALM",
            "GITLAB_URL",
            "GITLAB_TOKEN",
            "GITLAB_PROJECT_ID",
        ]));

        let config: Config = figment.extract()?;

        info!(
            port = config.port,
            host = %config.host,
            control_plane = config.control_plane_url.as_deref().unwrap_or("not set"),
            "Configuration loaded"
        );

        Ok(config)
    }

    /// Validate configuration (logs warnings for missing recommended settings)
    pub fn validate(&self) {
        if self.control_plane_url.is_none() {
            tracing::warn!("CONTROL_PLANE_URL not set - some features will be disabled");
        }

        if self.jwt_secret.is_none() && self.keycloak_url.is_none() {
            tracing::warn!("No JWT_SECRET or KEYCLOAK_URL - auth will be limited");
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_config() {
        let config = Config::default();
        assert_eq!(config.port, 8080);
        assert_eq!(config.host, "0.0.0.0");
        assert_eq!(config.mcp_session_ttl_minutes, 30);
    }

    #[test]
    fn test_load_with_defaults() {
        // This should work even without any config file or env vars
        std::env::remove_var("STOA_PORT");
        let config = Config::load().expect("Should load defaults");
        assert_eq!(config.port, 8080);
    }

    #[test]
    fn test_default_gateway_mode() {
        let config = Config::default();
        assert_eq!(config.gateway_mode, GatewayMode::default());
    }

    #[test]
    fn test_default_rate_limits() {
        let config = Config::default();
        assert_eq!(config.rate_limit_default, Some(1000));
        assert_eq!(config.rate_limit_window_seconds, Some(60));
    }

    #[test]
    fn test_default_kafka_disabled() {
        let config = Config::default();
        assert!(!config.kafka_enabled);
        assert_eq!(config.kafka_brokers, "redpanda:9092");
        assert_eq!(config.kafka_metering_topic, "stoa.metering");
        assert_eq!(config.kafka_errors_topic, "stoa.errors");
    }

    #[test]
    fn test_default_mtls_disabled() {
        let config = Config::default();
        assert!(!config.mtls.enabled);
        assert!(config.mtls.require_binding);
        assert!(config.mtls.trusted_proxies.is_empty());
        assert!(config.mtls.allowed_issuers.is_empty());
    }

    #[test]
    fn test_default_mtls_headers() {
        let mtls = MtlsConfig::default();
        assert_eq!(mtls.header_verify, "X-SSL-Client-Verify");
        assert_eq!(mtls.header_fingerprint, "X-SSL-Client-Fingerprint");
        assert_eq!(mtls.header_subject_dn, "X-SSL-Client-S-DN");
        assert_eq!(mtls.header_issuer_dn, "X-SSL-Client-I-DN");
        assert_eq!(mtls.header_serial, "X-SSL-Client-Serial");
        assert_eq!(mtls.header_not_before, "X-SSL-Client-NotBefore");
        assert_eq!(mtls.header_not_after, "X-SSL-Client-NotAfter");
        assert_eq!(mtls.header_cert, "X-SSL-Client-Cert");
    }

    #[test]
    fn test_default_quota_settings() {
        let config = Config::default();
        assert!(!config.quota_enforcement_enabled);
        assert_eq!(config.quota_sync_interval_secs, 60);
        assert_eq!(config.quota_default_rate_per_minute, 60);
        assert_eq!(config.quota_default_daily_limit, 10_000);
    }

    #[test]
    fn test_default_classification_enforcement_disabled() {
        let config = Config::default();
        assert!(!config.classification_enforcement_enabled);
    }

    #[test]
    fn test_default_tool_discovery_settings() {
        let config = Config::default();
        assert_eq!(config.tool_refresh_ttl_secs, 300);
        assert_eq!(config.tool_max_staleness_secs, 1800);
    }

    #[test]
    fn test_default_circuit_breaker_settings() {
        let config = Config::default();
        assert_eq!(config.cb_failure_threshold, 5);
        assert_eq!(config.cb_reset_timeout_secs, 30);
        assert_eq!(config.cb_success_threshold, 2);
    }

    #[test]
    fn test_default_governance_settings() {
        let config = Config::default();
        assert!(config.zombie_detection_enabled);
        assert_eq!(config.agent_session_ttl_secs, 600);
        assert_eq!(config.attestation_interval, 100);
    }

    #[test]
    fn test_default_gateway_external_url() {
        let config = Config::default();
        assert_eq!(
            config.gateway_external_url,
            Some("http://localhost:8080".to_string())
        );
    }

    #[test]
    fn test_default_fallback_disabled() {
        let config = Config::default();
        assert!(!config.fallback_enabled);
        assert!(config.fallback_chains.is_none());
        assert_eq!(config.fallback_timeout_ms, 5000);
    }

    #[test]
    fn test_default_guardrails_disabled() {
        let config = Config::default();
        assert!(!config.guardrails_pii_enabled);
        assert!(config.guardrails_pii_redact); // redact by default when enabled
        assert!(!config.guardrails_injection_enabled);
        assert!(!config.guardrails_content_filter_enabled);
    }

    #[test]
    fn test_default_token_budget_settings() {
        let config = Config::default();
        assert!(!config.token_budget_enabled);
        assert_eq!(config.token_budget_default_limit, 500_000);
        assert_eq!(config.token_budget_window_hours, 1);
    }

    #[test]
    fn test_validate_warns_but_succeeds() {
        let config = Config::default();
        // Default config has no CP URL and no JWT — validate logs warnings but doesn't panic
        config.validate();
    }

    #[test]
    fn test_default_api_proxy_disabled() {
        let config = Config::default();
        assert!(!config.api_proxy.enabled);
        assert!(config.api_proxy.require_auth);
        assert!(config.api_proxy.backends.is_empty());
    }

    #[test]
    fn test_api_proxy_backend_deserialization() {
        let json = serde_json::json!({
            "enabled": true,
            "base_url": "https://api.linear.app",
            "auth_type": "bearer",
            "auth_header": "Authorization",
            "rate_limit_rpm": 120,
            "timeout_secs": 15,
            "circuit_breaker_enabled": true,
            "fallback_direct": false,
            "allowed_paths": ["/graphql"]
        });
        let backend: ProxyBackendConfig = serde_json::from_value(json).unwrap();
        assert!(backend.enabled);
        assert_eq!(backend.base_url, "https://api.linear.app");
        assert_eq!(backend.rate_limit_rpm, 120);
        assert_eq!(backend.timeout_secs, 15);
        assert!(backend.circuit_breaker_enabled);
        assert!(!backend.fallback_direct);
        assert_eq!(backend.allowed_paths, vec!["/graphql"]);
    }

    #[test]
    fn test_api_proxy_config_with_backends() {
        let json = serde_json::json!({
            "enabled": true,
            "require_auth": true,
            "backends": {
                "linear": {
                    "enabled": true,
                    "base_url": "https://api.linear.app",
                    "rate_limit_rpm": 120
                },
                "github": {
                    "enabled": false,
                    "base_url": "https://api.github.com",
                    "rate_limit_rpm": 60
                }
            }
        });
        let proxy: ApiProxyConfig = serde_json::from_value(json).unwrap();
        assert!(proxy.enabled);
        assert_eq!(proxy.backends.len(), 2);
        assert!(proxy.backends["linear"].enabled);
        assert!(!proxy.backends["github"].enabled);
        assert_eq!(proxy.backends["linear"].rate_limit_rpm, 120);
    }

    #[test]
    fn test_proxy_backend_defaults() {
        let json = serde_json::json!({
            "base_url": "https://api.example.com"
        });
        let backend: ProxyBackendConfig = serde_json::from_value(json).unwrap();
        assert!(!backend.enabled);
        assert_eq!(backend.auth_type, "bearer");
        assert_eq!(backend.auth_header, "Authorization");
        assert_eq!(backend.rate_limit_rpm, 0);
        assert_eq!(backend.timeout_secs, 30);
        assert!(backend.circuit_breaker_enabled);
        assert!(!backend.fallback_direct);
        assert!(backend.allowed_paths.is_empty());
    }

    #[test]
    fn test_default_otel_sample_rate() {
        let config = Config::default();
        assert!((config.otel_sample_rate - 1.0).abs() < f64::EPSILON);
    }

    #[test]
    fn test_otel_enabled_by_default() {
        let config = Config::default();
        assert!(
            config.otel_enabled,
            "CAB-1831: otel_enabled should default to true"
        );
    }
}
