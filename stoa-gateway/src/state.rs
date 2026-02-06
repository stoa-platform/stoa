//! Application State
//!
//! Shared state across all handlers.

use std::sync::Arc;

use crate::auth::api_key::ApiKeyValidator;
use crate::auth::jwt::{JwtValidator, JwtValidatorConfig};
use crate::auth::oidc::{OidcProvider, OidcProviderConfig};
use crate::cache::{SemanticCache, SemanticCacheConfig};
use crate::config::Config;
use crate::control_plane::{OidcConfig, ToolProxyClient};
use crate::mcp::session::SessionManager;
use crate::mcp::tools::ToolRegistry;
use crate::policy::{PolicyDecision, PolicyEngine, PolicyEngineConfig, PolicyInput};
use crate::rate_limit::RateLimiter;
use crate::resilience::{CircuitBreaker, CircuitBreakerConfig};
use crate::routes::{PolicyRegistry, RouteRegistry};
use crate::uac::Action;

/// Application state shared across all handlers
#[derive(Clone)]
pub struct AppState {
    pub config: Config,
    pub tool_registry: Arc<ToolRegistry>,
    pub session_manager: Arc<SessionManager>,
    pub rate_limiter: Arc<RateLimiter>,
    #[allow(dead_code)]
    pub api_key_validator: Arc<ApiKeyValidator>,
    pub uac_enforcer: Arc<UacEnforcer>,
    pub control_plane: Arc<ToolProxyClient>,
    pub route_registry: Arc<RouteRegistry>,
    pub policy_registry: Arc<PolicyRegistry>,
    /// JWT validator for user token authentication (None if Keycloak not configured)
    pub jwt_validator: Option<Arc<JwtValidator>>,
    /// Semantic cache for read-only tool responses (Phase 6)
    pub semantic_cache: Arc<SemanticCache>,
    /// Circuit breaker for Control Plane API calls (Phase 6)
    pub cp_circuit_breaker: Arc<CircuitBreaker>,
}

impl AppState {
    pub fn new(config: Config) -> Self {
        let tool_registry = Arc::new(ToolRegistry::new());
        let session_manager = Arc::new(SessionManager::new(config.mcp_session_ttl_minutes));
        let rate_limiter = Arc::new(RateLimiter::new(&config));
        let api_key_validator = Arc::new(ApiKeyValidator::new(&config));

        // Initialize Policy Engine (OPA)
        let policy_config = PolicyEngineConfig {
            policy_path: config.policy_path.clone(),
            enabled: config.policy_enabled,
            ..PolicyEngineConfig::default()
        };
        let policy_engine = match PolicyEngine::new(policy_config) {
            Ok(engine) => Arc::new(engine),
            Err(e) => {
                tracing::error!(error = %e, "Failed to initialize policy engine — using permissive fallback");
                // Create disabled engine as fallback
                Arc::new(
                    PolicyEngine::new(PolicyEngineConfig {
                        enabled: false,
                        ..PolicyEngineConfig::default()
                    })
                    .expect("Fallback policy engine"),
                )
            }
        };
        let uac_enforcer = Arc::new(UacEnforcer::new(policy_engine));

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
            let issuer_url = format!("{}/realms/{}", url.trim_end_matches('/'), realm);
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

        // Initialize semantic cache for tool responses (Phase 6)
        let semantic_cache = Arc::new(SemanticCache::new(SemanticCacheConfig::default()));
        tracing::info!("Semantic cache initialized");

        // Initialize circuit breaker for CP API (Phase 6)
        let cp_circuit_breaker = CircuitBreaker::new("cp-api", CircuitBreakerConfig::default());
        tracing::info!("Circuit breaker initialized for CP API");

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
            semantic_cache,
            cp_circuit_breaker,
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

/// UAC Enforcer using OPA Policy Engine
///
/// Evaluates scope-based access control policies for tool invocations.
/// Implements ADR-012 12-Scope Model.
pub struct UacEnforcer {
    policy_engine: Arc<PolicyEngine>,
}

impl UacEnforcer {
    /// Create a new UAC enforcer with the given policy engine
    pub fn new(policy_engine: Arc<PolicyEngine>) -> Self {
        Self { policy_engine }
    }

    /// Check if a tool invocation is allowed (legacy signature for compatibility)
    #[allow(dead_code)]
    pub async fn check(&self, tenant_id: &str, action: Action) -> Result<(), String> {
        // Legacy check with empty context — allows all by default for backwards compat
        // New code should use check_with_context() for proper policy evaluation
        self.check_with_context(
            None,
            None,
            tenant_id,
            "unknown",
            action,
            vec!["stoa:read".to_string()], // Default read scope
            vec![],
        )
    }

    /// Check if a tool invocation is allowed with full context
    ///
    /// This is the primary method for policy evaluation. It builds a PolicyInput
    /// from the provided context and evaluates it against the OPA policy.
    #[allow(clippy::too_many_arguments)]
    pub fn check_with_context(
        &self,
        user_id: Option<String>,
        user_email: Option<String>,
        tenant_id: &str,
        tool_name: &str,
        action: Action,
        scopes: Vec<String>,
        roles: Vec<String>,
    ) -> Result<(), String> {
        let input = PolicyInput::new(
            user_id,
            user_email,
            tenant_id.to_string(),
            tool_name.to_string(),
            action,
            scopes,
            roles,
        );

        match self.policy_engine.evaluate(&input) {
            PolicyDecision::Allow => Ok(()),
            PolicyDecision::Deny { reason } => Err(reason),
        }
    }
}
