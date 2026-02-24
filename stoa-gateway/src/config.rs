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

    // === LLM Contracts (CAB-709) ===
    /// Enable LLM contract endpoint expansion (default: false)
    /// Env: STOA_LLM_ENABLED
    #[serde(default)]
    pub llm_enabled: bool,

    /// Default timeout in milliseconds for LLM backend calls
    /// Env: STOA_LLM_DEFAULT_TIMEOUT_MS
    #[serde(default = "default_llm_timeout_ms")]
    pub llm_default_timeout_ms: u64,
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

fn default_llm_timeout_ms() -> u64 {
    30_000
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
            quota_enforcement_enabled: false,
            quota_sync_interval_secs: default_quota_sync_interval(),
            quota_default_rate_per_minute: default_quota_rate_per_minute(),
            quota_default_daily_limit: default_quota_daily_limit(),
            access_log_enabled: default_access_log_enabled(),
            guardrails_pii_enabled: false,
            guardrails_pii_redact: default_guardrails_pii_redact(),
            guardrails_injection_enabled: false,
            guardrails_content_filter_enabled: false,
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
            prompt_cache_max_entries: default_prompt_cache_max_entries(),
            prompt_cache_ttl_secs: default_prompt_cache_ttl_secs(),
            prompt_cache_watch_dir: None,
            budget_enforcement_enabled: false,
            budget_cache_ttl_secs: default_budget_cache_ttl(),
            billing_api_url: None,
            llm_enabled: false,
            llm_default_timeout_ms: default_llm_timeout_ms(),
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
    fn test_default_otel_sample_rate() {
        let config = Config::default();
        assert!((config.otel_sample_rate - 1.0).abs() < f64::EPSILON);
    }
}
