//! Root-level default helpers and `impl Default for Config`.
//!
//! Co-locates every `fn default_*()` consumed by `#[serde(default = "...")]`
//! attributes on the flat `Config` struct, along with the `Default` impl that
//! wires them together. Keeping fns + impl in the same file means adding a
//! new root-level field only ever touches this module plus `config.rs`.

use super::{ApiProxyConfig, Config, ExpansionMode, LlmRouterConfig, MtlsConfig, SenderConstraintConfig};
use crate::mode::GatewayMode;

pub(super) fn default_true() -> bool {
    true
}

pub(super) fn default_port() -> u16 {
    8080
}

pub(super) fn default_host() -> String {
    "0.0.0.0".to_string()
}

pub(super) fn default_session_ttl() -> i64 {
    30
}

pub(super) fn default_ws_proxy_rate_limit() -> f64 {
    100.0
}

pub(super) fn default_ws_proxy_burst() -> usize {
    50
}

pub(super) fn default_gateway_external_url() -> Option<String> {
    Some("http://localhost:8080".to_string())
}

pub(super) fn default_policy_enabled() -> bool {
    true
}

pub(super) fn default_zombie_detection() -> bool {
    true
}

pub(super) fn default_agent_session_ttl() -> u64 {
    600 // 10 minutes per ADR-012
}

pub(super) fn default_attestation_interval() -> u64 {
    100 // Require attestation every 100 requests
}

pub(super) fn default_shadow_min_samples() -> usize {
    10 // Minimum samples before pattern is considered stable
}

pub(super) fn default_environment() -> String {
    "dev".to_string()
}

pub(super) fn default_auto_register() -> bool {
    true // Auto-register when control_plane_url is set
}

pub(super) fn default_heartbeat_interval() -> u64 {
    30 // 30 seconds per ADR-028
}

pub(super) fn default_native_tools_enabled() -> bool {
    true // Phase 1: native tools call CP API directly
}

pub(super) fn default_kafka_brokers() -> String {
    "redpanda:9092".to_string()
}

pub(super) fn default_kafka_metering_topic() -> String {
    "stoa.metering".to_string()
}

pub(super) fn default_kafka_errors_topic() -> String {
    "stoa.errors".to_string()
}

pub(super) fn default_kafka_deploy_progress_topic() -> String {
    "stoa.deployment.progress".to_string()
}

pub(super) fn default_otel_enabled() -> bool {
    true // CAB-1831: OTel always on, no-op exporter when STOA_OTEL_ENDPOINT absent
}

pub(super) fn default_otel_sample_rate() -> f64 {
    1.0 // Sample all traces by default
}

pub(super) fn default_quota_sync_interval() -> u64 {
    60
}

pub(super) fn default_quota_rate_per_minute() -> u32 {
    60
}

pub(super) fn default_quota_daily_limit() -> u32 {
    10_000
}

pub(super) fn default_route_reload_interval() -> u64 {
    30
}

pub(super) fn default_access_log_enabled() -> bool {
    true // Enabled by default — structured access logs for observability
}

pub(super) fn default_guardrails_pii_redact() -> bool {
    true // Redact by default (safer than rejecting)
}

pub(super) fn default_rag_max_context_length() -> usize {
    4096
}

pub(super) fn default_rag_source_timeout_ms() -> u64 {
    3000
}

pub(super) fn default_rag_max_chunks() -> usize {
    5
}

pub(super) fn default_token_budget_limit() -> u64 {
    500_000 // 500K tokens per window (~2M chars)
}

pub(super) fn default_token_budget_window_hours() -> u64 {
    1 // 1-hour sliding window
}

pub(super) fn default_fallback_timeout_ms() -> u64 {
    5000
}

pub(super) fn default_tool_refresh_ttl_secs() -> u64 {
    300
}

pub(super) fn default_tool_max_staleness_secs() -> u64 {
    1800
}

pub(super) fn default_cb_failure_threshold() -> u32 {
    5
}

pub(super) fn default_cb_reset_timeout_secs() -> u64 {
    30
}

pub(super) fn default_cb_success_threshold() -> u32 {
    2
}

pub(super) fn default_kafka_cns_topics() -> String {
    "stoa.api.lifecycle,stoa.deployment.events,stoa.security.alerts,stoa.policy.changes".to_string()
}

pub(super) fn default_kafka_cns_consumer_group() -> String {
    "stoa-gateway-cns".to_string()
}

pub(super) fn default_skill_cache_ttl() -> u64 {
    300 // 5 minutes
}

pub(super) fn default_skill_context_max_bytes() -> usize {
    8192
}

pub(super) fn default_skill_context_header() -> String {
    "X-Skill-Context".to_string()
}

pub(super) fn default_federation_cache_ttl() -> u64 {
    300
}

pub(super) fn default_federation_cache_max_entries() -> u64 {
    10_000
}

pub(super) fn default_prompt_cache_max_entries() -> u64 {
    1000
}

pub(super) fn default_prompt_cache_ttl_secs() -> u64 {
    3600
}

pub(super) fn default_budget_cache_ttl() -> u64 {
    60 // Refresh budget status every 60 seconds
}

pub(super) fn default_mcp_discovery_cache_ttl_secs() -> u64 {
    300 // 5 minutes
}

pub(super) fn default_mcp_discovery_cache_max_entries() -> u64 {
    256
}

pub(super) fn default_supervision_tier() -> String {
    "autopilot".to_string()
}

pub(super) fn default_llm_timeout_ms() -> u64 {
    30_000
}

pub(super) fn default_llm_proxy_upstream_url() -> String {
    "https://api.anthropic.com".to_string()
}

pub(super) fn default_llm_proxy_timeout_secs() -> u64 {
    300
}

pub(super) fn default_llm_proxy_mistral_upstream_url() -> String {
    "https://api.mistral.ai".to_string()
}

pub(super) fn default_hegemon_budget_daily_usd() -> f64 {
    50.0
}

pub(super) fn default_hegemon_budget_warn_pct() -> f64 {
    0.8
}

pub(super) fn default_a2a_max_agents() -> usize {
    1000
}

pub(super) fn default_a2a_max_tasks() -> usize {
    10000
}

pub(super) fn default_memory_limit_mb() -> u64 {
    512
}

pub(super) fn default_snapshot_max_count() -> usize {
    100
}

pub(super) fn default_snapshot_max_age_secs() -> u64 {
    3600
}

pub(super) fn default_snapshot_body_max_bytes() -> usize {
    4096
}

pub(super) fn default_git_provider() -> String {
    "gitlab".to_string() // backward compatible default
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
            github_token: None,
            github_org: None,
            github_catalog_repo: None,
            github_gitops_repo: None,
            github_webhook_secret: None,
            git_provider: default_git_provider(),
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
            detailed_tracing: false,
            proxy_metrics_enabled: true,
            proxy_tracing_enabled: true,
            gateway_mode: GatewayMode::default(),
            zombie_detection_enabled: default_zombie_detection(),
            agent_session_ttl_secs: default_agent_session_ttl(),
            attestation_interval: default_attestation_interval(),
            shadow_capture_source: None,
            shadow_min_samples: default_shadow_min_samples(),
            shadow_gitlab_project: None,
            environment: default_environment(),
            auto_register: default_auto_register(),
            advertise_url: None,
            heartbeat_interval_secs: default_heartbeat_interval(),
            target_gateway_url: None,
            gateway_public_url: None,
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
            route_reload_enabled: false,
            route_reload_interval_secs: default_route_reload_interval(),
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
            tool_expansion_mode: ExpansionMode::default(),
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
            ip_blocklist: String::new(),
            ip_blocklist_file: None,
            tcp_rate_limit_per_ip: None,
            memory_limit_mb: default_memory_limit_mb(),
            snapshot_enabled: false,
            snapshot_max_count: default_snapshot_max_count(),
            snapshot_max_age_secs: default_snapshot_max_age_secs(),
            snapshot_body_max_bytes: default_snapshot_body_max_bytes(),
            snapshot_extra_pii_patterns: vec![],
        }
    }
}
