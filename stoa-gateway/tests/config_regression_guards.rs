//! Regression guards for the GW-2 bug-hunt batch.
//!
//! These tests lock the fixes applied in the `fix/gw-2-bug-hunt-batch`
//! commit against silent regressions:
//!
//! - P0-1: env var `STOA_*__*` double-underscore splitting for nested structs.
//! - P0-2: `Vec<String>` fields accept both CSV and JSON array strings.
//! - P1-4: `Config::default()` and `#[serde(default)]` agree on the four
//!   `Option<…>` fields that used to diverge (rate limits, log level/format).
//! - P1-5: `Debug` output does not leak any of the secret-bearing fields.
//! - P1-7: default Config round-trips through JSON/YAML without drift, and the
//!   production fixture parses + validates.
//!
//! Env vars are serialised through a global `Mutex` because Rust test threads
//! share the process env. Any test that mutates env state MUST take this lock.

use std::sync::{Mutex, MutexGuard, OnceLock};

use stoa_gateway::config::Config;

// ----- Shared env-mutation lock --------------------------------------------

fn env_lock() -> MutexGuard<'static, ()> {
    static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
    // On poisoning, recover and continue — a previous test panicked while
    // holding the lock, but the env state is not corrupted in a way that
    // affects the next test after we clear it.
    LOCK.get_or_init(|| Mutex::new(()))
        .lock()
        .unwrap_or_else(|e| e.into_inner())
}

fn clear_stoa_env() {
    for (k, _) in std::env::vars() {
        if k.starts_with("STOA_") {
            std::env::remove_var(k);
        }
    }
}

// ----- P0-1: env var split --------------------------------------------------

#[test]
fn regression_nested_mtls_double_underscore_activates_nested_field() {
    let _g = env_lock();
    clear_stoa_env();
    // Default MUST be disabled so we see the env flip take effect.
    std::env::set_var("STOA_MTLS__ENABLED", "true");
    std::env::set_var("STOA_MTLS__TRUSTED_PROXIES", "10.0.0.0/8");

    let config = Config::load().expect("load with nested mtls env vars");
    assert!(
        config.mtls.enabled,
        "STOA_MTLS__ENABLED=true must set config.mtls.enabled to true"
    );
    assert_eq!(config.mtls.trusted_proxies, vec!["10.0.0.0/8"]);

    clear_stoa_env();
}

#[test]
fn regression_nested_single_underscore_env_remains_ignored_for_backward_compat() {
    // Ensures the single-underscore form (historical k8s manifest pattern)
    // stays a no-op so migrating operators are never surprised by a sudden
    // feature flip on redeploy.
    let _g = env_lock();
    clear_stoa_env();
    std::env::set_var("STOA_MTLS_ENABLED", "true");

    let config = Config::load().expect("load with single-underscore env var");
    assert!(
        !config.mtls.enabled,
        "STOA_MTLS_ENABLED (single underscore) must NOT activate the nested mtls.enabled field"
    );

    clear_stoa_env();
}

#[test]
fn test_env_var_nested_api_proxy_double_underscore() {
    let _g = env_lock();
    clear_stoa_env();
    std::env::set_var("STOA_API_PROXY__ENABLED", "true");
    std::env::set_var("STOA_API_PROXY__REQUIRE_AUTH", "false");

    let config = Config::load().expect("load with nested api_proxy env vars");
    assert!(config.api_proxy.enabled);
    assert!(!config.api_proxy.require_auth);

    clear_stoa_env();
}

// ----- P0-2: CSV / JSON array string list deserializer ---------------------

#[test]
fn test_snapshot_extra_pii_patterns_accepts_csv_env() {
    let _g = env_lock();
    clear_stoa_env();
    std::env::set_var(
        "STOA_SNAPSHOT_EXTRA_PII_PATTERNS",
        "card_number, ssn_us ,, ",
    );

    let config = Config::load().expect("CSV env var must not crash load()");
    assert_eq!(
        config.snapshot_extra_pii_patterns,
        vec!["card_number", "ssn_us"],
        "CSV should trim whitespace and drop empty segments"
    );

    clear_stoa_env();
}

#[test]
fn test_snapshot_extra_pii_patterns_accepts_json_array_env() {
    let _g = env_lock();
    clear_stoa_env();
    std::env::set_var(
        "STOA_SNAPSHOT_EXTRA_PII_PATTERNS",
        r#"["card_number","ssn_us"]"#,
    );

    let config = Config::load().expect("JSON array env var must not crash load()");
    assert_eq!(
        config.snapshot_extra_pii_patterns,
        vec!["card_number", "ssn_us"]
    );

    clear_stoa_env();
}

#[test]
fn test_mtls_trusted_proxies_csv_via_double_underscore() {
    let _g = env_lock();
    clear_stoa_env();
    std::env::set_var("STOA_MTLS__ENABLED", "true");
    std::env::set_var("STOA_MTLS__TRUSTED_PROXIES", "10.0.0.0/8, 192.168.0.0/16");

    let config = Config::load().expect("CSV nested env var must not crash load()");
    assert_eq!(
        config.mtls.trusted_proxies,
        vec!["10.0.0.0/8", "192.168.0.0/16"]
    );

    clear_stoa_env();
}

// ----- P1-4: Config::default() ↔ #[serde(default)] alignment ----------------

#[test]
fn test_config_default_matches_empty_yaml_deserialize() {
    // Pre-fix, an empty YAML produced None for these four fields while
    // Config::default() produced Some(…). This test locks the alignment.
    let yaml_cfg: Config = serde_yaml::from_str("").expect("empty yaml must parse");
    let default_cfg = Config::default();

    assert_eq!(
        yaml_cfg.rate_limit_default, default_cfg.rate_limit_default,
        "rate_limit_default must agree"
    );
    assert_eq!(
        yaml_cfg.rate_limit_window_seconds, default_cfg.rate_limit_window_seconds,
        "rate_limit_window_seconds must agree"
    );
    assert_eq!(
        yaml_cfg.log_level, default_cfg.log_level,
        "log_level must agree"
    );
    assert_eq!(
        yaml_cfg.log_format, default_cfg.log_format,
        "log_format must agree"
    );

    // Spot-check a couple of other fields just to confirm the round trip is
    // not degenerate.
    assert_eq!(yaml_cfg.port, default_cfg.port);
    assert_eq!(yaml_cfg.mtls.enabled, default_cfg.mtls.enabled);
}

// ----- P1-5: Debug does not leak secrets ------------------------------------

const SENTINEL: &str = "SECRET_DO_NOT_LEAK_XYZ";

fn fresh_config_with_sentinel() -> Config {
    let secret = Some(SENTINEL.to_string());
    Config {
        jwt_secret: secret.clone(),
        keycloak_client_secret: secret.clone(),
        keycloak_admin_password: secret.clone(),
        control_plane_api_key: secret.clone(),
        admin_api_token: secret.clone(),
        gitlab_token: secret.clone(),
        github_token: secret.clone(),
        github_webhook_secret: secret.clone(),
        llm_proxy_api_key: secret.clone(),
        llm_proxy_mistral_api_key: secret.clone(),
        ..Config::default()
    }
}

#[test]
fn regression_debug_does_not_leak_secrets() {
    let config = fresh_config_with_sentinel();
    let rendered = format!("{:?}", config);
    assert!(
        !rendered.contains(SENTINEL),
        "Config Debug output must not contain the sentinel secret value"
    );
    // Shape sanity: redacted fields are still present with a clear marker.
    assert!(
        rendered.contains("<redacted>"),
        "redaction marker `<redacted>` must appear in Debug output"
    );
    // The field *names* are fine to leak — only values must be hidden.
    assert!(rendered.contains("jwt_secret"));
    assert!(rendered.contains("keycloak_client_secret"));
}

#[test]
fn test_federation_upstream_debug_redacts_token() {
    use stoa_gateway::config::{FederationUpstreamConfig, Redacted};

    let upstream = FederationUpstreamConfig {
        url: "https://upstream.example.com".to_string(),
        transport: Some("sse".to_string()),
        auth_token: Some(Redacted::new(SENTINEL.to_string())),
        timeout_secs: Some(30),
    };
    let rendered = format!("{:?}", upstream);
    assert!(
        !rendered.contains(SENTINEL),
        "FederationUpstreamConfig.auth_token must be redacted in Debug"
    );
    // URL (non-secret) still renders.
    assert!(rendered.contains("upstream.example.com"));
}

// ----- P1-7: roundtrip + fixtures -------------------------------------------

#[test]
fn test_config_roundtrip_default_json() {
    let default = Config::default();
    let json = serde_json::to_string(&default).expect("serialize default");
    let back: Config = serde_json::from_str(&json).expect("deserialize default");
    // Cross-check a representative slice of fields — a full structural assert
    // is not possible (Config is not PartialEq) but the JSON round-trip
    // should preserve identity modulo field ordering.
    let re_json = serde_json::to_string(&back).expect("re-serialize");
    assert_eq!(
        json, re_json,
        "JSON round-trip must be stable (default → json → Config → json)"
    );
}

#[test]
fn test_fixture_minimal_parses() {
    let path =
        std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/config_minimal.yaml");
    let raw = std::fs::read_to_string(&path).expect("read minimal fixture");
    let cfg: Config = serde_yaml::from_str(&raw).expect("parse minimal fixture");
    assert_eq!(cfg.port, 9090);
    assert_eq!(cfg.host, "127.0.0.1");
    assert_eq!(cfg.log_level, Some(stoa_gateway::config::LogLevel::Debug));
    // Unset fields keep their Config::default() value.
    assert!(cfg.rate_limit_default.is_some(), "default propagates");
}

#[test]
fn regression_fixture_production_parses_and_validates() {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures/config_production.yaml");
    let raw = std::fs::read_to_string(&path).expect("read production fixture");
    let cfg: Config = serde_yaml::from_str(&raw).expect("parse production fixture");
    cfg.validate()
        .expect("production fixture must pass Config::validate()");

    // Spot checks confirming the fixture actually exercises the critical
    // invariants we added (mtls + trusted_proxies, sender_constraint +
    // backing).
    assert!(cfg.mtls.enabled);
    assert!(!cfg.mtls.trusted_proxies.is_empty());
    assert!(cfg.sender_constraint.enabled);
    assert!(cfg.dpop.enabled || cfg.mtls.enabled);
    assert_eq!(cfg.snapshot_extra_pii_patterns.len(), 2);
}
