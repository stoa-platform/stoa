//! Authentication and Authorization Module
//!
//! CAB-912 P2: OIDC/JWT authentication with RBAC for MCP Gateway.
//!
//! ## Components
//!
//! - **claims**: JWT claims structure for Keycloak tokens
//! - **oidc**: OIDC discovery with JWKS caching
//! - **jwt**: JWT validation with RS256 signature verification
//! - **middleware**: Axum middleware for request authentication
//! - **rbac**: Role-based access control with tenant isolation
//!
//! ## Usage
//!
//! ```ignore
//! use stoa_gateway::auth::{
//!     AuthState, JwtValidator, OidcProvider, OidcProviderConfig,
//!     auth_middleware, AuthUser, RbacEnforcer, Action,
//! };
//!
//! // Create OIDC provider
//! let oidc_config = OidcProviderConfig {
//!     issuer_url: "https://auth.gostoa.dev/realms/stoa".to_string(),
//!     audience: "stoa-mcp".to_string(),
//!     ..Default::default()
//! };
//! let oidc_provider = Arc::new(OidcProvider::new(oidc_config));
//!
//! // Create JWT validator
//! let jwt_validator = Arc::new(JwtValidator::new(oidc_provider));
//!
//! // Create auth state
//! let auth_state = AuthState::new(jwt_validator);
//!
//! // Use in Axum router
//! let app = Router::new()
//!     .route("/api/protected", get(protected_handler))
//!     .layer(middleware::from_fn_with_state(auth_state, auth_middleware));
//!
//! // In handler, extract authenticated user
//! async fn protected_handler(user: AuthUser) -> impl IntoResponse {
//!     format!("Hello, {}", user.0.user_id)
//! }
//! ```

pub mod claims;
pub mod jwt;
pub mod middleware;
pub mod oidc;
pub mod rbac;

// Re-exports for convenience
pub use claims::{Audience, Claims, RealmAccess, ResourceAccess, StoaRole};
pub use jwt::{JwtError, JwtValidator, JwtValidatorConfig, TokenExtractor, ValidatedToken};
pub use middleware::{
    auth_middleware, optional_auth, require_auth, AuthError, AuthState, AuthUser,
    AuthenticatedUser, OptionalAuthUser,
};
pub use oidc::{Jwk, Jwks, OidcConfig, OidcError, OidcProvider, OidcProviderConfig};
pub use rbac::{Action, AuthzContext, RbacEnforcer, RbacError, RbacPolicy};

// =============================================================================
// Configuration
// =============================================================================

/// Authentication configuration from environment.
#[derive(Debug, Clone)]
pub struct AuthConfig {
    /// OIDC issuer URL
    pub issuer_url: String,

    /// Expected audience (client ID)
    pub audience: String,

    /// JWKS cache TTL in seconds
    pub jwks_cache_ttl_seconds: u64,

    /// Whether to require authentication
    pub require_auth: bool,
}

impl Default for AuthConfig {
    fn default() -> Self {
        Self {
            issuer_url: "https://auth.gostoa.dev/realms/stoa".to_string(),
            audience: "stoa-mcp".to_string(),
            jwks_cache_ttl_seconds: 300,
            require_auth: true,
        }
    }
}

impl AuthConfig {
    /// Load from environment variables.
    pub fn from_env() -> Self {
        Self {
            issuer_url: std::env::var("OIDC_ISSUER_URL")
                .unwrap_or_else(|_| "https://auth.gostoa.dev/realms/stoa".to_string()),
            audience: std::env::var("OIDC_AUDIENCE").unwrap_or_else(|_| "stoa-mcp".to_string()),
            jwks_cache_ttl_seconds: std::env::var("JWKS_CACHE_TTL_SECONDS")
                .ok()
                .and_then(|s| s.parse().ok())
                .unwrap_or(300),
            require_auth: std::env::var("REQUIRE_AUTH")
                .map(|s| s != "false" && s != "0")
                .unwrap_or(true),
        }
    }

    /// Convert to OIDC provider config.
    pub fn to_oidc_config(&self) -> OidcProviderConfig {
        OidcProviderConfig {
            issuer_url: self.issuer_url.clone(),
            audience: self.audience.clone(),
            jwks_cache_ttl: std::time::Duration::from_secs(self.jwks_cache_ttl_seconds),
            http_timeout: std::time::Duration::from_secs(10),
        }
    }
}

// =============================================================================
// Builder Pattern
// =============================================================================

use std::sync::Arc;

/// Builder for creating auth stack.
pub struct AuthBuilder {
    config: AuthConfig,
    rbac_policy: Option<RbacPolicy>,
}

impl AuthBuilder {
    /// Create a new auth builder with default config.
    pub fn new() -> Self {
        Self {
            config: AuthConfig::default(),
            rbac_policy: None,
        }
    }

    /// Create from environment.
    pub fn from_env() -> Self {
        Self {
            config: AuthConfig::from_env(),
            rbac_policy: None,
        }
    }

    /// Set the OIDC issuer URL.
    pub fn issuer_url(mut self, url: impl Into<String>) -> Self {
        self.config.issuer_url = url.into();
        self
    }

    /// Set the expected audience.
    pub fn audience(mut self, audience: impl Into<String>) -> Self {
        self.config.audience = audience.into();
        self
    }

    /// Set whether authentication is required.
    pub fn require_auth(mut self, required: bool) -> Self {
        self.config.require_auth = required;
        self
    }

    /// Set RBAC policy.
    pub fn with_rbac_policy(mut self, policy: RbacPolicy) -> Self {
        self.rbac_policy = Some(policy);
        self
    }

    /// Build the auth components.
    pub fn build(self) -> AuthComponents {
        let oidc_provider = Arc::new(OidcProvider::new(self.config.to_oidc_config()));
        let jwt_validator = Arc::new(JwtValidator::new(oidc_provider.clone()));
        let auth_state = if self.config.require_auth {
            AuthState::new(jwt_validator.clone())
        } else {
            AuthState::optional(jwt_validator.clone())
        };
        let rbac_enforcer =
            RbacEnforcer::with_policy(self.rbac_policy.unwrap_or_else(RbacPolicy::default));

        AuthComponents {
            oidc_provider,
            jwt_validator,
            auth_state,
            rbac_enforcer,
            config: self.config,
        }
    }
}

impl Default for AuthBuilder {
    fn default() -> Self {
        Self::new()
    }
}

/// All auth components bundled together.
#[derive(Clone)]
pub struct AuthComponents {
    /// OIDC provider for key fetching
    pub oidc_provider: Arc<OidcProvider>,

    /// JWT validator
    pub jwt_validator: Arc<JwtValidator>,

    /// Axum auth state
    pub auth_state: AuthState,

    /// RBAC enforcer
    pub rbac_enforcer: RbacEnforcer,

    /// Configuration
    pub config: AuthConfig,
}

impl AuthComponents {
    /// Create with default configuration.
    pub fn new() -> Self {
        AuthBuilder::new().build()
    }

    /// Create from environment.
    pub fn from_env() -> Self {
        AuthBuilder::from_env().build()
    }
}

impl Default for AuthComponents {
    fn default() -> Self {
        Self::new()
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_auth_config_default() {
        let config = AuthConfig::default();
        assert_eq!(config.issuer_url, "https://auth.gostoa.dev/realms/stoa");
        assert_eq!(config.audience, "stoa-mcp");
        assert!(config.require_auth);
    }

    #[test]
    fn test_auth_builder() {
        let components = AuthBuilder::new()
            .issuer_url("https://test.example.com/realms/test")
            .audience("test-client")
            .require_auth(false)
            .build();

        assert_eq!(
            components.config.issuer_url,
            "https://test.example.com/realms/test"
        );
        assert_eq!(components.config.audience, "test-client");
        assert!(!components.config.require_auth);
    }

    #[test]
    fn test_auth_components_default() {
        let components = AuthComponents::new();
        assert!(components.config.require_auth);
    }
}
