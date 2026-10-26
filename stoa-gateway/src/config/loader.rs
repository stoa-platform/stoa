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
use std::path::Path;
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

impl Config {
    /// Return the Keycloak backend URL for service-to-service calls.
    ///
    /// Prefers `keycloak_internal_url` (K8s service DNS) over `keycloak_url` (external)
    /// to bypass hairpin NAT issues on OVH MKS and similar cloud providers.
    /// Returns `None` if neither is configured.
    pub fn keycloak_backend_url(&self) -> Option<&str> {
        self.keycloak_internal_url
            .as_deref()
            .or(self.keycloak_url.as_deref())
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

        // Try config.yaml if exists
        let config_paths = ["config.yaml", "config.yml", "/etc/stoa/config.yaml"];
        for path in config_paths {
            if Path::new(path).exists() {
                info!(path = path, "Loading config from file");
                figment = figment.merge(Yaml::file(path));
                break;
            }
        }

        // Environment variables override (STOA_ prefix).
        // `.split("__")` lets nested struct fields be driven via env: e.g.
        // `STOA_MTLS__ENABLED=true` → `mtls.enabled`. Single-underscore forms
        // bind to root-level flat fields only (unchanged behaviour).
        figment = figment.merge(Env::prefixed("STOA_").split("__"));

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

        let config: Config = figment.extract()?;

        info!(
            port = config.port,
            host = %config.host,
            control_plane = config.control_plane_url.as_deref().unwrap_or("not set"),
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

        if self.keycloak_client_key_path.is_none() && self.control_plane_url.is_some() {
            tracing::warn!(
                "STOA_KEYCLOAK_CLIENT_KEY_PATH not set - tenant tool permissions cannot be read, \
                 tool calls will be denied"
            );
        }

        if self.control_plane_url.is_none() {
            tracing::warn!("CONTROL_PLANE_URL not set - some features will be disabled");
        }

        if self.jwt_secret.is_none() && self.keycloak_url.is_none() {
            tracing::warn!("No JWT_SECRET or KEYCLOAK_URL - auth will be limited");
        }

        // CAB-2165 Bundle 2 / P2-11 GW-2 defense-in-depth: warn when a
        // filesystem path field resolves outside canonical STOA prefixes
        // (/etc/stoa, /var/stoa, /opt/stoa). Never rejects — operator keeps
        // control; the warning surfaces typos and misconfigured mounts.
        if let Some(ref p) = self.policy_path {
            super::path_safety::warn_if_unsafe("policy_path", p);
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
    fn test_validate_accepts_default_config() {
        let config = Config::default();
        // Default config has no CP URL and no JWT — validate logs warnings
        // but does not fail.
        config.validate().expect("default config must validate");
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
}
