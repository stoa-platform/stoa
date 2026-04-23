//! Config loader and accessor methods.
//!
//! Figment-based layered loading (defaults → YAML file → STOA_* env → legacy envy keys)
//! plus read-only accessors that encode cross-cluster policy (e.g., Keycloak backend URL
//! prefers the internal cluster DNS to bypass hairpin NAT on OVH MKS).

use figment::{
    providers::{Env, Format, Serialized, Yaml},
    Figment,
};
use std::path::Path;
use tracing::info;

use super::Config;

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
    use super::Config;

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
    fn test_load_with_defaults() {
        // This should work even without any config file or env vars
        std::env::remove_var("STOA_PORT");
        let config = Config::load().expect("Should load defaults");
        assert_eq!(config.port, 8080);
    }

    #[test]
    fn test_validate_warns_but_succeeds() {
        let config = Config::default();
        // Default config has no CP URL and no JWT — validate logs warnings but doesn't panic
        config.validate();
    }
}
