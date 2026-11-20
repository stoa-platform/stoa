//! Config loader and accessor methods.
//!
//! Figment-based layered loading (defaults → YAML file → `STOA_*` env → legacy
//! envy keys) plus read-only accessors that encode cross-cluster policy (e.g.,
//! Keycloak backend URL prefers the internal cluster DNS to bypass hairpin NAT
//! on OVH MKS).
//!
//! Env vars for **nested structs** use a double-underscore separator, e.g.
//! `STOA_MTLS__ENABLED=true` sets `mtls.enabled`. Single-underscore forms like
//! `STOA_MTLS_ENABLED` remain no-op for nested fields (historical behaviour,
//! preserved for backward compatibility with k8s manifests in flight).

use figment::{
    providers::{Env, Format, Serialized, Yaml},
    Figment,
};
use thiserror::Error;
use tracing::info;

use super::Config;

/// Errors returned by [`Config::load`] / [`Config::validate`].
///
/// Variants are exhaustive: the gateway refuses to start on any of these
/// instead of silently proceeding with an inconsistent configuration.
#[derive(Debug, Error)]
pub enum ConfigError {
    /// Figment failed to load/parse the config (YAML syntax, type mismatch, etc.).
    #[error("configuration loading failed: {0}")]
    Load(#[from] figment::Error),

    /// Port must be a non-zero value to bind a TCP listener.
    #[error("invalid port: {0} (expected 1..=65535)")]
    InvalidPort(u16),

    /// mTLS cannot be safely enabled with an empty trusted-proxy allow list,
    /// because `trusted_proxies: []` documents "accept all sources" (auth bypass
    /// risk). Operators must explicitly list trusted F5/ingress IPs.
    #[error(
        "mtls.enabled=true requires a non-empty mtls.trusted_proxies list \
         (empty = accept all sources = auth bypass). Set \
         `STOA_MTLS__TRUSTED_PROXIES` or the YAML field."
    )]
    MtlsEnabledWithoutTrustedProxies,

    /// Enabling `federation_enabled` with no upstreams is almost certainly a
    /// misconfiguration — the feature silently does nothing.
    #[error(
        "federation_enabled=true requires at least one federation_upstream \
         (set `STOA_FEDERATION_UPSTREAMS` as a JSON array or the YAML list)"
    )]
    FederationEnabledWithoutUpstreams,

    /// `sender_constraint.enabled=true` only makes sense if at least one of
    /// mTLS or DPoP is available to carry the cnf claim.
    #[error(
        "sender_constraint.enabled=true requires mtls.enabled || dpop.enabled \
         (otherwise no binding channel is available)"
    )]
    SenderConstraintWithoutBacking,

    /// Local agent admission needs a positive capacity and window.
    #[error("poc_agents_enabled=true requires positive poc_max_admission_entries and poc_caller_budget_window_secs")]
    InvalidPocAdmissionBounds,

    /// An API proxy backend declares an inconsistent access setting.
    #[error("api_proxy backend `{backend}`: {reason}")]
    ApiProxyBackendAccess {
        backend: String,
        reason: &'static str,
    },

    /// `tcp_rate_limit_per_ip` must be a finite positive float when set.
    /// NaN / -inf / +inf would silently disable or fully-open the limiter.
    #[error("tcp_rate_limit_per_ip must be a finite positive f64 when set (got {0})")]
    TcpRateLimitNotFinite(f64),

    /// MCP entrypoints need an explicit token audience. There is no default,
    /// and a production gateway does not start without it.
    #[error(
        "environment=prod requires mcp_audience (set `STOA_MCP_AUDIENCE` to the \
         resource audience carried by MCP access tokens)"
    )]
    McpAudienceRequired,

    #[error("ext_authz in prod requires STOA_EXT_AUTHZ_AUDIENCE and non-empty STOA_EXT_AUTHZ_REQUIRED_SCOPES")]
    ExtAuthzProfileRequired,

    /// The `private_key_jwt` key file must exist when its path is configured.
    #[error("keycloak_client_key_path does not point to a readable file: {0}")]
    ClientKeyUnreadable(String),
}

fn non_empty_trimmed(value: &Option<String>) -> Option<&str> {
    value.as_deref().map(str::trim).filter(|s| !s.is_empty())
}

impl Config {
    /// Return the Keycloak backend URL for service-to-service calls.
    ///
    /// Prefers `keycloak_internal_url` (K8s service DNS) over `keycloak_url` (external)
    /// to bypass hairpin NAT issues on OVH MKS and similar cloud providers.
    /// Returns `None` if neither is configured (empty/whitespace counts as unset).
    pub fn keycloak_backend_url(&self) -> Option<&str> {
        non_empty_trimmed(&self.keycloak_internal_url)
            .or_else(|| non_empty_trimmed(&self.keycloak_url))
    }

    /// True only when running in explicit local dev mode without Keycloak
    /// and without a Control Plane.
    ///
    /// Empty or whitespace-only URL values are treated as unset. Implicit
    /// `Dev` defaults (`Config::default()` or unset `STOA_ENVIRONMENT`),
    /// staging, production, and any run with a Keycloak or Control Plane URL
    /// return `false`.
    pub fn allows_explicit_local_dev_access(&self) -> bool {
        self.environment == super::Environment::Dev
            && self.environment_explicit
            && non_empty_trimmed(&self.keycloak_url).is_none()
            && non_empty_trimmed(&self.keycloak_internal_url).is_none()
            && non_empty_trimmed(&self.control_plane_url).is_none()
    }

    /// Load configuration from file and environment.
    ///
    /// Layer order (later overrides earlier):
    /// 1. `Config::default()` as serialized baseline.
    /// 2. `config.yaml` / `config.yml` / `/etc/stoa/config.yaml` (first one found).
    /// 3. `STOA_*` env vars (`__` splits nested structs — see module-level doc).
    /// 4. Legacy flat env vars (`PORT`, `JWT_SECRET`, …) kept for envy compat.
    #[allow(clippy::result_large_err)]
    pub fn load() -> Result<Self, ConfigError> {
        let mut figment = Figment::new()
            // Start with defaults
            .merge(Serialized::defaults(Config::default()));
        // Track explicit overrides (file -> STOA_* env) without defaults so
        // `environment_explicit` reflects the winning provider value only.
        let mut explicit_figment = Figment::new();

        // Try config.yaml if exists. Read the file once and reuse the captured
        // contents for both extraction and environment provenance.
        let config_paths = ["config.yaml", "config.yml", "/etc/stoa/config.yaml"];
        for path in config_paths {
            match std::fs::read_to_string(path) {
                Ok(contents) => {
                    info!(path = path, "Loading config from file");
                    explicit_figment = explicit_figment.merge(Yaml::string(&contents));
                    figment = figment.merge(Yaml::string(&contents));
                    break;
                }
                Err(err) if err.kind() == std::io::ErrorKind::NotFound => continue,
                Err(err) => {
                    return Err(figment::Error::from(format!(
                        "failed to read config file {path}: {err}"
                    ))
                    .into());
                }
            }
        }

        // Environment variables override (STOA_ prefix).
        // `.split("__")` lets nested struct fields be driven via env: e.g.
        // `STOA_MTLS__ENABLED=true` → `mtls.enabled`. Single-underscore forms
        // bind to root-level flat fields only (unchanged behaviour).
        // Materialize the prefixed env provider once and reuse that snapshot
        // for both environment provenance and extraction.
        let env_figment = Figment::from(Env::prefixed("STOA_").split("__"));
        explicit_figment = explicit_figment.merge(env_figment.clone());
        figment = figment.merge(env_figment);

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
            "GITHUB_TOKEN",
            "GITHUB_ORG",
            "GITHUB_CATALOG_REPO",
            "GITHUB_GITOPS_REPO",
            "GITHUB_WEBHOOK_SECRET",
            "GIT_PROVIDER",
        ]));

        let mut config: Config = figment.extract()?;
        config.environment_explicit = explicit_figment
            .find_value("environment")
            .ok()
            .and_then(|value| value.as_str().and_then(super::Environment::parse_literal))
            .is_some();

        info!(
            port = config.port,
            host = %config.host,
            control_plane = non_empty_trimmed(&config.control_plane_url).unwrap_or("not set"),
            "Configuration loaded"
        );

        Ok(config)
    }

    /// Validate configuration invariants.
    ///
    /// Returns `Err(ConfigError)` for any invariant violation that would lead
    /// to a silent misconfiguration in production (auth bypass, feature that
    /// appears enabled but is a no-op, rate limiter with non-finite values).
    /// Emits `tracing::warn!` for non-critical gaps (e.g., missing control
    /// plane URL) so the gateway can still boot in dev environments.
    #[allow(clippy::result_large_err)]
    pub fn validate(&self) -> Result<(), ConfigError> {
        // --- Hard invariants (refuse boot) ---

        if self.port == 0 {
            return Err(ConfigError::InvalidPort(self.port));
        }

        if self.mtls.enabled && self.mtls.trusted_proxies.is_empty() {
            return Err(ConfigError::MtlsEnabledWithoutTrustedProxies);
        }

        if self.federation_enabled && self.federation_upstreams.is_empty() {
            return Err(ConfigError::FederationEnabledWithoutUpstreams);
        }

        if self.sender_constraint.enabled && !(self.mtls.enabled || self.dpop.enabled) {
            return Err(ConfigError::SenderConstraintWithoutBacking);
        }

        if self.poc_agents_enabled
            && (self.poc_max_admission_entries == 0 || self.poc_caller_budget_window_secs == 0)
        {
            return Err(ConfigError::InvalidPocAdmissionBounds);
        }

        for (backend, b) in &self.api_proxy.backends {
            if let Some(reason) = b.access_conflict() {
                return Err(ConfigError::ApiProxyBackendAccess {
                    backend: backend.clone(),
                    reason,
                });
            }
        }

        if let Some(rate) = self.tcp_rate_limit_per_ip {
            if !rate.is_finite() || rate <= 0.0 {
                return Err(ConfigError::TcpRateLimitNotFinite(rate));
            }
        }

        let mcp_audience_missing = self
            .mcp_audience
            .as_deref()
            .is_none_or(|audience| audience.trim().is_empty());
        if mcp_audience_missing && self.environment == super::Environment::Prod {
            return Err(ConfigError::McpAudienceRequired);
        }

        if self.ext_authz_grpc_addr.is_some() {
            let missing = self
                .ext_authz_audience
                .as_deref()
                .is_none_or(|a| a.trim().is_empty());
            let empty_scopes = self.ext_authz_required_scopes.is_empty()
                || self
                    .ext_authz_required_scopes
                    .iter()
                    .any(|s| s.trim().is_empty());
            if self.environment == super::Environment::Prod && (missing || empty_scopes) {
                return Err(ConfigError::ExtAuthzProfileRequired);
            }
            if missing {
                tracing::warn!("ext_authz audience missing: listener will deny all requests and remain not ready");
            }
            if empty_scopes {
                tracing::warn!("ext_authz required scopes are empty or invalid");
            }
        }

        if let Some(ref key_path) = self.keycloak_client_key_path {
            let readable = std::fs::File::open(key_path)
                .and_then(|file| file.metadata())
                .is_ok_and(|metadata| metadata.is_file());
            if !readable {
                return Err(ConfigError::ClientKeyUnreadable(key_path.clone()));
            }
        }

        // --- Soft warnings (proceed) ---

        if mcp_audience_missing {
            tracing::warn!(
                "STOA_MCP_AUDIENCE not set - MCP entrypoints will reject authenticated requests"
            );
        }

        let has_control_plane = non_empty_trimmed(&self.control_plane_url).is_some();
        let has_keycloak = self.keycloak_backend_url().is_some();

        if self.keycloak_client_key_path.is_none() && has_control_plane {
            tracing::warn!(
                "STOA_KEYCLOAK_CLIENT_KEY_PATH not set - tenant tool permissions cannot be read, \
                 tool calls will be denied"
            );
        }

        if !has_control_plane {
            tracing::warn!("CONTROL_PLANE_URL not set - some features will be disabled");
        }

        if self.jwt_secret.is_none() && !has_keycloak {
            tracing::warn!("No JWT_SECRET or KEYCLOAK_URL - auth will be limited");
        }

        // CAB-2165 Bundle 2 / P2-11 GW-2 defense-in-depth: warn when a
        // filesystem path field resolves outside canonical STOA prefixes
        // (/etc/stoa, /var/stoa, /opt/stoa). Never rejects — operator keeps
        // control; the warning surfaces typos and misconfigured mounts.
        if let Some(ref p) = self.policy_path {
            super::path_safety::warn_if_unsafe("policy_path", p);
        }
        if let Some(ref p) = self.policy_trust_jwks_file {
            // Field only: the trust key set location never reaches the logs.
            if super::path_safety::is_path_outside_safe_prefixes(p) {
                tracing::warn!(field = "policy_trust_jwks_file", "outside safe prefixes");
            }
        }
        if let Some(ref p) = self.ip_blocklist_file {
            super::path_safety::warn_if_unsafe("ip_blocklist_file", p);
        }
        if let Some(ref p) = self.prompt_cache_watch_dir {
            super::path_safety::warn_if_unsafe("prompt_cache_watch_dir", p);
        }

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::{Config, ConfigError};
    use serde_json::json;

    /// Regression test for PR #1814: OAuth proxy endpoints must use
    /// keycloak_internal_url when available, to bypass hairpin NAT on OVH MKS.
    /// Root cause: proxy.rs used config.keycloak_url (external) for backend
    /// calls, causing 502 on DCR registration from inside the cluster.
    #[test]
    fn regression_keycloak_backend_url_prefers_internal() {
        let mut config = Config::default();

        // No URLs configured → None
        assert!(config.keycloak_backend_url().is_none());

        // Only external URL → returns external
        config.keycloak_url = Some("https://auth.gostoa.dev".to_string());
        assert_eq!(
            config.keycloak_backend_url(),
            Some("https://auth.gostoa.dev")
        );

        // Both configured → internal wins (bypasses hairpin NAT)
        config.keycloak_internal_url =
            Some("http://keycloak.stoa-system.svc.cluster.local:8080".to_string());
        assert_eq!(
            config.keycloak_backend_url(),
            Some("http://keycloak.stoa-system.svc.cluster.local:8080")
        );

        // Only internal URL → returns internal
        config.keycloak_url = None;
        assert_eq!(
            config.keycloak_backend_url(),
            Some("http://keycloak.stoa-system.svc.cluster.local:8080")
        );
    }

    #[test]
    #[allow(clippy::result_large_err)] // figment::Jail closure returns Result<(), figment::Error>
    fn test_load_with_defaults() {
        // Wrap in figment::Jail so this test takes the same global LOCK as
        // the enum env-var tests below (CAB-2165 Bundle 1). Without it, a
        // parallel Jail test that sets `STOA_GIT_PROVIDER=bitbucket` can
        // leak into this test's `Config::load()` call and trip the strict
        // enum parser.
        figment::Jail::expect_with(|jail| {
            jail.clear_env();
            let config = Config::load().expect("Should load defaults");
            assert_eq!(config.port, 8080);
            Ok(())
        });
    }

    #[test]
    fn test_validate_rejects_inconsistent_public_proxy_backend() {
        for (extra, ok) in [
            (json!({ "public": true, "auth_type": "none" }), true),
            (json!({ "public": true }), false),
            (json!({ "public": true, "auth_type": "api_key" }), false),
            (
                json!({ "public": true, "auth_type": "none", "required_scopes": ["s"] }),
                false,
            ),
            (
                json!({ "public": true, "auth_type": "none", "required_roles": ["r"] }),
                false,
            ),
            (json!({ "required_scopes": ["s"] }), true),
        ] {
            let mut b = json!({ "base_url": "http://upstream.invalid" });
            b.as_object_mut()
                .unwrap()
                .extend(extra.as_object().unwrap().clone());
            let config = Config {
                api_proxy: serde_json::from_value(json!({ "backends": { "t": b } })).unwrap(),
                ..Config::default()
            };
            let r = config.validate();
            assert_eq!(r.is_ok(), ok, "{extra}");
            if !ok {
                assert!(
                    matches!(r, Err(ConfigError::ApiProxyBackendAccess { .. })),
                    "{extra}"
                );
            }
        }
    }

    #[test]
    fn test_validate_accepts_default_config() {
        let config = Config::default();
        // Default config has no CP URL and no JWT — validate logs warnings
        // but does not fail.
        config.validate().expect("default config must validate");
    }

    /// The trust key set location stays out of validation logs and of the
    /// `Config` `Debug` output, even when it sits outside the safe prefixes.
    #[test]
    fn trust_key_set_path_is_withheld_from_diagnostics() {
        use crate::control_plane::tool_proxy::tests::LogBuffer;
        let path = "/srv/synthetic-mount/trust-keys.json";
        let config = Config {
            policy_trust_jwks_file: Some(path.to_string()),
            ..Config::default()
        };
        let logs = LogBuffer::default();
        let subscriber = tracing_subscriber::fmt()
            .with_writer(logs.clone())
            .with_ansi(false)
            .finish();
        tracing::subscriber::with_default(subscriber, || config.validate().unwrap());
        let captured = String::from_utf8(logs.0.lock().clone()).unwrap();
        assert!(captured.contains("policy_trust_jwks_file"), "{captured}");
        assert!(!captured.contains(path), "{captured}");
        assert!(!format!("{config:?}").contains(path));
    }

    #[test]
    fn test_validate_rejects_prod_without_mcp_audience() {
        for audience in [None, Some(String::new()), Some("  ".to_string())] {
            let config = Config {
                environment: super::super::Environment::Prod,
                mcp_audience: audience,
                ..Config::default()
            };
            match config.validate() {
                Err(ConfigError::McpAudienceRequired) => {}
                other => panic!("expected McpAudienceRequired, got {:?}", other),
            }
        }
    }

    #[test]
    fn test_validate_accepts_prod_with_mcp_audience() {
        let config = Config {
            environment: super::super::Environment::Prod,
            mcp_audience: Some("stoa-mcp".to_string()),
            ..Config::default()
        };
        config
            .validate()
            .expect("prod with an explicit MCP audience must validate");
    }

    #[test]
    #[allow(clippy::result_large_err)] // figment::Jail closure returns Result<(), figment::Error>
    fn test_prod_startup_fails_without_mcp_audience_env() {
        figment::Jail::expect_with(|jail| {
            jail.clear_env();
            jail.set_env("STOA_ENVIRONMENT", "prod");
            let config = Config::load().expect("load");
            assert!(config.mcp_audience.is_none(), "no default audience");
            assert!(matches!(
                config.validate(),
                Err(ConfigError::McpAudienceRequired)
            ));

            jail.set_env("STOA_MCP_AUDIENCE", "stoa-mcp");
            let config = Config::load().expect("load");
            assert_eq!(config.mcp_audience.as_deref(), Some("stoa-mcp"));
            config.validate().expect("audience set");
            Ok(())
        });
    }

    #[test]
    fn test_validate_rejects_missing_client_key_file() {
        let dir = tempfile::tempdir().unwrap();
        let config = Config {
            keycloak_client_key_path: Some(dir.path().join("absent.pem").display().to_string()),
            ..Config::default()
        };
        assert!(matches!(
            config.validate(),
            Err(ConfigError::ClientKeyUnreadable(_))
        ));

        let key = dir.path().join("key.pem");
        std::fs::write(&key, "placeholder").unwrap();
        let config = Config {
            keycloak_client_key_path: Some(key.display().to_string()),
            ..Config::default()
        };
        config.validate().expect("existing key file");
    }

    #[test]
    fn test_validate_rejects_port_zero() {
        let config = Config {
            port: 0,
            ..Config::default()
        };
        match config.validate() {
            Err(ConfigError::InvalidPort(0)) => {}
            other => panic!("expected InvalidPort(0), got {:?}", other),
        }
    }

    #[test]
    fn test_validate_poc_admission_bounds() {
        for (max_entries, window_secs) in [(0, 900), (10, 0)] {
            let mut config = Config {
                poc_agents_enabled: true,
                poc_max_admission_entries: max_entries,
                poc_caller_budget_window_secs: window_secs,
                ..Config::default()
            };
            assert!(matches!(
                config.validate(),
                Err(ConfigError::InvalidPocAdmissionBounds)
            ));
            config.poc_agents_enabled = false;
            config.validate().expect("PoC disabled");
        }
    }

    #[test]
    fn test_validate_rejects_mtls_without_trusted_proxies() {
        let mut config = Config::default();
        config.mtls.enabled = true;
        config.mtls.trusted_proxies.clear();
        match config.validate() {
            Err(ConfigError::MtlsEnabledWithoutTrustedProxies) => {}
            other => panic!("expected MtlsEnabledWithoutTrustedProxies, got {:?}", other),
        }
    }

    #[test]
    fn test_validate_accepts_mtls_with_trusted_proxies() {
        let mut config = Config::default();
        config.mtls.enabled = true;
        config.mtls.trusted_proxies = vec!["10.0.0.0/8".to_string()];
        config.validate().expect("must accept mtls + trusted proxy");
    }

    #[test]
    fn test_validate_rejects_federation_without_upstreams() {
        let config = Config {
            federation_enabled: true,
            federation_upstreams: Vec::new(),
            ..Config::default()
        };
        match config.validate() {
            Err(ConfigError::FederationEnabledWithoutUpstreams) => {}
            other => panic!(
                "expected FederationEnabledWithoutUpstreams, got {:?}",
                other
            ),
        }
    }

    #[test]
    fn test_validate_rejects_sender_constraint_without_backing() {
        // both mtls + dpop off, sender_constraint enabled
        let mut config = Config::default();
        config.sender_constraint.enabled = true;
        config.mtls.enabled = false;
        config.dpop.enabled = false;
        match config.validate() {
            Err(ConfigError::SenderConstraintWithoutBacking) => {}
            other => panic!("expected SenderConstraintWithoutBacking, got {:?}", other),
        }
    }

    #[test]
    fn test_validate_accepts_sender_constraint_with_dpop_only() {
        let mut config = Config::default();
        config.sender_constraint.enabled = true;
        config.dpop.enabled = true;
        config
            .validate()
            .expect("dpop alone is enough backing for sender_constraint");
    }

    #[test]
    fn test_validate_rejects_tcp_rate_limit_infinity() {
        let config = Config {
            tcp_rate_limit_per_ip: Some(f64::INFINITY),
            ..Config::default()
        };
        match config.validate() {
            Err(ConfigError::TcpRateLimitNotFinite(r)) if r.is_infinite() => {}
            other => panic!("expected TcpRateLimitNotFinite, got {:?}", other),
        }
    }

    #[test]
    fn test_validate_rejects_tcp_rate_limit_nan() {
        let config = Config {
            tcp_rate_limit_per_ip: Some(f64::NAN),
            ..Config::default()
        };
        match config.validate() {
            Err(ConfigError::TcpRateLimitNotFinite(r)) if r.is_nan() => {}
            other => panic!("expected TcpRateLimitNotFinite(NaN), got {:?}", other),
        }
    }

    #[test]
    fn test_validate_accepts_none_tcp_rate_limit() {
        let config = Config {
            tcp_rate_limit_per_ip: None,
            ..Config::default()
        };
        config.validate().expect("None is the documented disable");
    }

    #[test]
    fn test_validate_accepts_positive_finite_tcp_rate_limit() {
        let config = Config {
            tcp_rate_limit_per_ip: Some(10.0),
            ..Config::default()
        };
        config.validate().expect("positive finite must validate");
    }

    // CAB-2165 Bundle 1: verify that env vars pick up the enum deserialization
    // path too, not just YAML. `figment::Jail` provides a hermetic env scope so
    // these tests don't race with others that `set_var`/`remove_var` globally.

    #[test]
    #[allow(clippy::result_large_err)] // figment::Jail closure returns Result<(), figment::Error>
    fn env_var_sets_git_provider_to_github() {
        use figment::providers::{Env, Serialized};
        use figment::{Figment, Jail};

        Jail::expect_with(|jail| {
            jail.set_env("STOA_GIT_PROVIDER", "github");
            let figment = Figment::new()
                .merge(Serialized::defaults(Config::default()))
                .merge(Env::prefixed("STOA_").split("__"));
            let cfg: Config = figment.extract()?;
            assert_eq!(cfg.git_provider, super::super::GitProvider::Github);
            Ok(())
        });
    }

    #[test]
    #[allow(clippy::result_large_err)] // figment::Jail closure returns Result<(), figment::Error>
    fn env_var_sets_environment_to_prod() {
        use figment::providers::{Env, Serialized};
        use figment::{Figment, Jail};

        Jail::expect_with(|jail| {
            jail.set_env("STOA_ENVIRONMENT", "prod");
            let figment = Figment::new()
                .merge(Serialized::defaults(Config::default()))
                .merge(Env::prefixed("STOA_").split("__"));
            let cfg: Config = figment.extract()?;
            assert_eq!(cfg.environment, super::super::Environment::Prod);
            Ok(())
        });
    }

    #[test]
    #[allow(clippy::result_large_err)] // figment::Jail closure returns Result<(), figment::Error>
    fn env_var_rejects_unknown_git_provider() {
        use figment::providers::{Env, Serialized};
        use figment::{Figment, Jail};

        Jail::expect_with(|jail| {
            jail.set_env("STOA_GIT_PROVIDER", "bitbucket");
            let figment = Figment::new()
                .merge(Serialized::defaults(Config::default()))
                .merge(Env::prefixed("STOA_").split("__"));
            let err = figment
                .extract::<Config>()
                .expect_err("unknown variant must not deserialize");
            let msg = format!("{err:?}");
            assert!(
                msg.contains("unknown variant") || msg.contains("bitbucket"),
                "error should surface the rejected value: {msg}"
            );
            Ok(())
        });
    }

    #[test]
    fn explicit_local_dev_access_requires_explicit_dev_and_no_idp_or_cp() {
        let default_cfg = Config::default();
        assert!(!default_cfg.environment_explicit);
        assert!(!default_cfg.allows_explicit_local_dev_access());

        let mut cfg = Config {
            environment: super::super::Environment::Dev,
            environment_explicit: true,
            ..Config::default()
        };
        assert!(cfg.allows_explicit_local_dev_access());

        // Blank / whitespace URLs count as unset.
        cfg.keycloak_url = Some("   ".to_string());
        cfg.keycloak_internal_url = Some("".to_string());
        cfg.control_plane_url = Some("\t ".to_string());
        assert!(cfg.allows_explicit_local_dev_access());

        // Setting any Keycloak or Control Plane URL re-locks access.
        cfg.keycloak_url = Some("https://auth.example.com".to_string());
        assert!(!cfg.allows_explicit_local_dev_access());
        cfg.keycloak_url = None;

        cfg.keycloak_internal_url = Some("http://keycloak.internal:8080".to_string());
        assert!(!cfg.allows_explicit_local_dev_access());
        cfg.keycloak_internal_url = None;

        cfg.control_plane_url = Some("http://127.0.0.1:8000".to_string());
        assert!(!cfg.allows_explicit_local_dev_access());
        cfg.control_plane_url = None;

        // Staging and Prod never allow explicit local dev access.
        for env in [
            super::super::Environment::Staging,
            super::super::Environment::Prod,
        ] {
            cfg.environment = env;
            assert!(!cfg.allows_explicit_local_dev_access(), "{env:?}");
        }
    }

    #[test]
    #[allow(clippy::result_large_err)]
    fn environment_load_tracks_explicit_env_and_file_and_rejects_unknown() {
        use figment::Jail;

        // Absent STOA_ENVIRONMENT stays implicit Dev (locked).
        Jail::expect_with(|jail| {
            jail.clear_env();
            let cfg = Config::load().expect("default load");
            assert_eq!(cfg.environment, super::super::Environment::Dev);
            assert!(!cfg.environment_explicit);
            assert!(!cfg.allows_explicit_local_dev_access());

            // A casual env var for the skipped field cannot flip it.
            jail.set_env("STOA_ENVIRONMENT_EXPLICIT", "true");
            let cfg = Config::load().expect("load with ignored explicit flag");
            assert!(!cfg.environment_explicit);
            assert!(!cfg.allows_explicit_local_dev_access());
            Ok(())
        });

        // Explicit STOA_ENVIRONMENT=dev unlocks local dev when no IdP/CP URL is set.
        Jail::expect_with(|jail| {
            jail.clear_env();
            jail.set_env("STOA_ENVIRONMENT", "dev");
            let cfg = Config::load().expect("explicit dev load");
            assert_eq!(cfg.environment, super::super::Environment::Dev);
            assert!(cfg.environment_explicit);
            assert!(cfg.allows_explicit_local_dev_access());

            // Whitespace URLs remain unset.
            jail.set_env("STOA_KEYCLOAK_URL", "   ");
            jail.set_env("STOA_CONTROL_PLANE_URL", "");
            let cfg = Config::load().expect("explicit dev with blank urls");
            assert!(cfg.allows_explicit_local_dev_access());

            // Real Keycloak URL re-locks access.
            jail.set_env("STOA_KEYCLOAK_URL", "https://auth.example.com");
            let cfg = Config::load().expect("explicit dev with keycloak");
            assert!(!cfg.allows_explicit_local_dev_access());

            // Real Control Plane URL alone also re-locks access.
            jail.set_env("STOA_KEYCLOAK_URL", "");
            jail.set_env("STOA_CONTROL_PLANE_URL", "http://127.0.0.1:8000");
            let cfg = Config::load().expect("explicit dev with cp");
            assert!(!cfg.allows_explicit_local_dev_access());
            Ok(())
        });

        // Config file setting environment: dev unlocks; omitting environment stays locked.
        Jail::expect_with(|jail| {
            jail.clear_env();
            jail.create_file("config.yaml", "port: 9091\nenvironment_explicit: true\n")?;
            let cfg = Config::load().expect("yaml without environment");
            assert!(!cfg.environment_explicit);
            assert!(!cfg.allows_explicit_local_dev_access());

            jail.create_file("config.yaml", "environment: dev\n")?;
            let cfg = Config::load().expect("yaml with explicit dev");
            assert_eq!(cfg.environment, super::super::Environment::Dev);
            assert!(cfg.environment_explicit);
            assert!(cfg.allows_explicit_local_dev_access());

            // STOA_ENVIRONMENT overrides YAML environment using the single snapshot.
            jail.set_env("STOA_ENVIRONMENT", "prod");
            let cfg = Config::load().expect("env prod overrides yaml dev");
            assert_eq!(cfg.environment, super::super::Environment::Prod);
            assert!(cfg.environment_explicit);
            assert!(!cfg.allows_explicit_local_dev_access());
            Ok(())
        });

        // Blank YAML environment refuses startup.
        Jail::expect_with(|jail| {
            jail.clear_env();
            jail.create_file("config.yaml", "environment: \"   \"\n")?;
            assert!(
                Config::load().is_err(),
                "blank YAML environment must fail Config::load()"
            );
            Ok(())
        });

        // Blank or unknown STOA_ENVIRONMENT refuses startup.
        for bad in ["", "   ", "mordor"] {
            Jail::expect_with(|jail| {
                jail.clear_env();
                jail.set_env("STOA_ENVIRONMENT", bad);
                assert!(
                    Config::load().is_err(),
                    "STOA_ENVIRONMENT={bad:?} must fail Config::load()"
                );
                Ok(())
            });
        }
    }

    #[test]
    #[allow(clippy::result_large_err)]
    fn environment_load_preserves_case_variant_and_quoted_env_overrides() {
        use figment::Jail;

        // Case-variant env override takes precedence over explicit YAML dev.
        Jail::expect_with(|jail| {
            jail.clear_env();
            jail.create_file("config.yaml", "environment: dev\n")?;
            jail.set_env("STOA_environment", "staging");
            let cfg = Config::load().expect("case-variant staging override");
            assert_eq!(cfg.environment, super::super::Environment::Staging);
            assert!(cfg.environment_explicit);
            assert!(!cfg.allows_explicit_local_dev_access());
            Ok(())
        });

        // Case-variant unknown environment value fails Config::load().
        Jail::expect_with(|jail| {
            jail.clear_env();
            jail.set_env("STOA_environment", "mordor");
            assert!(
                Config::load().is_err(),
                "case-variant unknown environment must fail Config::load()"
            );
            Ok(())
        });

        // Figment-parsed quoted env values continue to work as overrides.
        Jail::expect_with(|jail| {
            jail.clear_env();
            jail.create_file("config.yaml", "environment: dev\n")?;
            jail.set_env("STOA_ENVIRONMENT", "\"staging\"");
            let cfg = Config::load().expect("quoted staging override");
            assert_eq!(cfg.environment, super::super::Environment::Staging);
            assert!(cfg.environment_explicit);
            assert!(!cfg.allows_explicit_local_dev_access());
            Ok(())
        });
    }

    #[test]
    #[allow(clippy::result_large_err)]
    fn environment_load_rejects_numeric_indexes_in_env_and_yaml() {
        use figment::Jail;

        // Numeric env values fail alone (no enum index deserialization).
        for bad in ["0", "1", "2", "\"0\""] {
            Jail::expect_with(|jail| {
                jail.clear_env();
                jail.set_env("STOA_ENVIRONMENT", bad);
                assert!(
                    Config::load().is_err(),
                    "STOA_ENVIRONMENT={bad} must fail Config::load()"
                );
                Ok(())
            });
        }

        // Numeric env override over explicit YAML staging/prod fails closed.
        for yaml_env in ["staging", "prod"] {
            Jail::expect_with(|jail| {
                jail.clear_env();
                jail.create_file("config.yaml", &format!("environment: {yaml_env}\n"))?;
                jail.set_env("STOA_ENVIRONMENT", "0");
                assert!(
                    Config::load().is_err(),
                    "STOA_ENVIRONMENT=0 over YAML {yaml_env} must fail Config::load()"
                );
                Ok(())
            });
        }

        // Numeric YAML environment fails Config::load().
        for yaml_val in ["0", "1", "2"] {
            Jail::expect_with(|jail| {
                jail.clear_env();
                jail.create_file("config.yaml", &format!("environment: {yaml_val}\n"))?;
                assert!(
                    Config::load().is_err(),
                    "YAML environment: {yaml_val} must fail Config::load()"
                );
                Ok(())
            });
        }

        // Literal dev / staging / prod continue to load cleanly.
        for (label, expected, allows_local) in [
            ("dev", super::super::Environment::Dev, true),
            ("staging", super::super::Environment::Staging, false),
            ("prod", super::super::Environment::Prod, false),
        ] {
            Jail::expect_with(|jail| {
                jail.clear_env();
                jail.set_env("STOA_ENVIRONMENT", label);
                let cfg = Config::load().expect("literal environment load");
                assert_eq!(cfg.environment, expected);
                assert!(cfg.environment_explicit);
                assert_eq!(cfg.allows_explicit_local_dev_access(), allows_local);
                Ok(())
            });
        }
    }
}
