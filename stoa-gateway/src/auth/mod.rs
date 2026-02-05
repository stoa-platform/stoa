//! Authentication module
//!
//! Supports:
//! - JWT validation (Bearer tokens) via OIDC/JWKS
//! - API Key validation (X-API-Key header)
//! - RBAC enforcement (role + scope + tenant isolation)
//! - Combined auth middleware

pub mod api_key;
pub mod claims;
pub mod jwt;
pub mod middleware;
pub mod oidc;
pub mod rbac;

pub use api_key::{ApiKeyError, ApiKeyInfo, ApiKeyValidator};
pub use claims::Claims;
pub use jwt::{JwtValidator, JwtValidatorConfig, ValidatedToken};
pub use middleware::AuthenticatedUser;
pub use oidc::{OidcProvider, OidcProviderConfig};
