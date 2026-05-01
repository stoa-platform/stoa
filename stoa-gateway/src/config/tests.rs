//! Config-level default wiring tests.
//!
//! Each sub-module (`mtls`, `api_proxy`, `loader`, `expansion`) also carries its
//! own focused tests. What lives here is the cross-struct wiring: asserting
//! that `Config::default()` plumbs each nested struct's default through correctly
//! and that root-level defaults (port, kafka topics, circuit breaker thresholds…)
//! match their declared `default_*()` helpers.

use super::Config;
use crate::mode::GatewayMode;

#[test]
fn test_default_config() {
    let config = Config::default();
    assert_eq!(config.port, 8080);
    assert_eq!(config.host, "0.0.0.0");
    assert_eq!(config.mcp_session_ttl_minutes, 30);
}

#[test]
fn test_default_gateway_mode() {
    let config = Config::default();
    assert_eq!(config.gateway_mode, GatewayMode::default());
}

#[test]
fn test_default_topology_registration_fields_absent() {
    let config = Config::default();
    assert!(config.target_gateway_url.is_none());
    assert!(config.gateway_public_url.is_none());
    assert!(config.gateway_ui_url.is_none());
    assert!(config.deployment_mode.is_none());
    assert!(config.target_gateway_type.is_none());
    assert!(config.topology.is_none());
    assert!(config.topology_proof.is_none());
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
fn test_default_api_proxy_disabled() {
    let config = Config::default();
    assert!(!config.api_proxy.enabled);
    assert!(config.api_proxy.require_auth);
    assert!(config.api_proxy.backends.is_empty());
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

#[test]
fn test_default_github_config() {
    let config = Config::default();
    // All GitHub fields default to None
    assert!(config.github_token.is_none());
    assert!(config.github_org.is_none());
    assert!(config.github_catalog_repo.is_none());
    assert!(config.github_gitops_repo.is_none());
    assert!(config.github_webhook_secret.is_none());
    // git_provider defaults to GitProvider::Gitlab for backward compatibility
    assert_eq!(config.git_provider, super::GitProvider::Gitlab);
    // GitLab fields are unaffected
    assert!(config.gitlab_url.is_none());
    assert!(config.gitlab_token.is_none());
}

#[test]
fn test_git_provider_github_config_complete() {
    // Verify that a fully-configured GitHub setup has all expected fields
    let config = Config {
        git_provider: super::GitProvider::Github,
        github_token: Some("ghp_test123".into()),
        github_org: Some("stoa-platform".into()),
        github_catalog_repo: Some("stoa".into()),
        github_gitops_repo: Some("stoa-infra".into()),
        github_webhook_secret: Some("whsec_test".into()),
        ..Config::default()
    };
    assert_eq!(config.git_provider, super::GitProvider::Github);
    assert_eq!(config.github_token.as_deref(), Some("ghp_test123"));
    assert_eq!(config.github_org.as_deref(), Some("stoa-platform"));
    assert_eq!(config.github_catalog_repo.as_deref(), Some("stoa"));
    assert_eq!(config.github_gitops_repo.as_deref(), Some("stoa-infra"));
    assert_eq!(config.github_webhook_secret.as_deref(), Some("whsec_test"));
}

#[test]
fn test_git_provider_gitlab_and_github_coexist() {
    // During migration, both provider configs can coexist
    let config = Config {
        git_provider: super::GitProvider::Github,
        github_token: Some("ghp_tok".into()),
        github_org: Some("acme".into()),
        gitlab_url: Some("https://gitlab.example.com".into()),
        gitlab_token: Some("glpat-legacy".into()),
        gitlab_project_id: Some("42".into()),
        ..Config::default()
    };
    // git_provider selects github even though gitlab fields are present
    assert_eq!(config.git_provider, super::GitProvider::Github);
    // GitLab fields remain accessible (for shadow mode fallback)
    assert!(config.gitlab_token.is_some());
}

// CAB-2165 Bundle 1 / P2-9 GW-2: the legacy
// `test_git_provider_unknown_value_treated_as_gitlab` test locked in the
// silent-fallthrough anti-pattern. It was replaced by strict-parse coverage
// in `config::enums::tests::git_provider_rejects_unknown_value` — unknown
// YAML/env values now surface as a clear deserialize error at Config::load()
// time instead of decaying to the Gitlab default.

/// Serialized snapshot of `Config::default()`. Drift of any default or field
/// order will show up as a diff in the .snap file during `cargo insta review`.
///
/// Debug snapshots are explicitly NOT used here: the std::fmt::Debug derived
/// format is documented as unstable across Rust versions.
#[test]
fn snapshot_default_config() {
    insta::assert_json_snapshot!(Config::default());
}
