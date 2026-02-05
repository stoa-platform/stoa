//! Application State
//!
//! Shared state across all handlers.

use std::sync::Arc;

use crate::auth::api_key::ApiKeyValidator;
use crate::auth::jwt::{JwtValidator, JwtValidatorConfig};
use crate::auth::oidc::{OidcProvider, OidcProviderConfig};
use crate::config::Config;
use crate::control_plane::{OidcConfig, ToolProxyClient};
use crate::mcp::session::SessionManager;
use crate::mcp::tools::ToolRegistry;
use crate::rate_limit::RateLimiter;
use crate::routes::{RouteRegistry, PolicyRegistry};

/// Application state shared across all handlers
#[derive(Clone)]
pub struct AppState {
    pub config: Config,
    pub tool_registry: Arc<ToolRegistry>,
    pub session_manager: Arc<SessionManager>,
    pub rate_limiter: Arc<RateLimiter>,
    pub api_key_validator: Arc<ApiKeyValidator>,
    pub uac_enforcer: Arc<UacEnforcer>,
    pub control_plane: Arc<ToolProxyClient>,
    pub route_registry: Arc<RouteRegistry>,
    pub policy_registry: Arc<PolicyRegistry>,
    /// JWT validator for user token authentication (None if Keycloak not configured)
    pub jwt_validator: Option<Arc<JwtValidator>>,
}

impl AppState {
    pub fn new(config: Config) -> Self {
        let tool_registry = Arc::new(ToolRegistry::new());
        let session_manager = Arc::new(SessionManager::new(config.mcp_session_ttl_minutes));
        let rate_limiter = Arc::new(RateLimiter::new(&config));
        let api_key_validator = Arc::new(ApiKeyValidator::new(&config));
        let uac_enforcer = Arc::new(UacEnforcer);

        let cp_url = config
            .control_plane_url
            .as_deref()
            .unwrap_or("http://localhost:8000");

        // Build OIDC config if Keycloak credentials are provided
        let oidc = match (
            &config.keycloak_url,
            &config.keycloak_client_id,
            &config.keycloak_client_secret,
        ) {
            (Some(url), Some(client_id), Some(client_secret)) => {
                let realm = config.keycloak_realm.as_deref().unwrap_or("stoa");
                let token_url = format!(
                    "{}/realms/{}/protocol/openid-connect/token",
                    url.trim_end_matches('/'),
                    realm
                );
                Some(OidcConfig {
                    token_url,
                    client_id: client_id.clone(),
                    client_secret: client_secret.clone(),
                })
            }
            _ => None,
        };

        let control_plane = Arc::new(ToolProxyClient::new(cp_url, oidc));
        let route_registry = Arc::new(RouteRegistry::new());
        let policy_registry = Arc::new(PolicyRegistry::new());

        // Build JWT validator if Keycloak is configured (for user token validation)
        let jwt_validator = if let Some(url) = &config.keycloak_url {
            let realm = config.keycloak_realm.as_deref().unwrap_or("stoa");
            let issuer_url = format!(
                "{}/realms/{}",
                url.trim_end_matches('/'),
                realm
            );
            let client_id = config
                .keycloak_client_id
                .as_deref()
                .unwrap_or("stoa-mcp-gateway");

            let oidc_config = OidcProviderConfig {
                issuer_url,
                audience: client_id.to_string(),
                ..OidcProviderConfig::default()
            };
            let oidc_provider = Arc::new(OidcProvider::new(oidc_config));
            // Disable audience validation: user tokens come from various clients
            // (control-plane-ui, Claude.ai DCR, etc.) and won't have the gateway
            // client_id in their aud claim unless a Keycloak audience mapper is added.
            // Issuer + RS256 signature validation is sufficient.
            let jwt_config = JwtValidatorConfig {
                validate_audience: false,
                ..JwtValidatorConfig::default()
            };
            let validator = JwtValidator::with_config(oidc_provider, jwt_config);
            tracing::info!("JWT validator initialized for user token authentication");
            Some(Arc::new(validator))
        } else {
            tracing::warn!("Keycloak not configured — JWT user auth disabled");
            None
        };

        Self {
            config,
            tool_registry,
            session_manager,
            rate_limiter,
            api_key_validator,
            uac_enforcer,
            control_plane,
            route_registry,
            policy_registry,
            jwt_validator,
        }
    }

    /// Start background tasks
    pub fn start_background_tasks(&self) {
        // Start session cleanup
        self.session_manager.clone().start_cleanup_task();
        
        // Start rate limiter cleanup
        self.rate_limiter.clone().start_cleanup_task();
    }
}

// Placeholder for UAC enforcer until full implementation
pub struct UacEnforcer;

impl UacEnforcer {
    pub async fn check(&self, _tenant_id: &str, _action: crate::uac::Action) -> Result<(), String> {
        // TODO: Implement actual UAC check
        Ok(())
    }
}
