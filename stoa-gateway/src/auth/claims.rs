//! JWT Claims
//!
//! CAB-912 P2: JWT claims structure for Keycloak OIDC tokens.
//!
//! Expected claims:
//! - sub: Subject (user ID)
//! - preferred_username: User's display name
//! - email: User's email
//! - tenant: Custom claim for tenant ID
//! - realm_access.roles: Keycloak realm roles
//! - resource_access: Client-specific roles

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// =============================================================================
// JWT Claims
// =============================================================================

/// Standard JWT claims from Keycloak.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Claims {
    /// Subject (user ID in Keycloak)
    pub sub: String,

    /// Token expiration time (Unix timestamp)
    pub exp: i64,

    /// Token issued at (Unix timestamp)
    pub iat: i64,

    /// Token issuer (Keycloak realm URL)
    pub iss: String,

    /// Audience (client IDs)
    #[serde(default)]
    pub aud: Audience,

    /// Authorized party (the client that requested the token)
    #[serde(default)]
    pub azp: Option<String>,

    /// Preferred username
    #[serde(default)]
    pub preferred_username: Option<String>,

    /// Email address
    #[serde(default)]
    pub email: Option<String>,

    /// Whether email is verified
    #[serde(default)]
    pub email_verified: Option<bool>,

    /// Full name
    #[serde(default)]
    pub name: Option<String>,

    /// Given name (first name)
    #[serde(default)]
    pub given_name: Option<String>,

    /// Family name (last name)
    #[serde(default)]
    pub family_name: Option<String>,

    /// Custom tenant claim
    #[serde(default)]
    pub tenant: Option<String>,

    /// Realm-level roles
    #[serde(default)]
    pub realm_access: Option<RealmAccess>,

    /// Client-specific roles
    #[serde(default)]
    pub resource_access: Option<HashMap<String, ResourceAccess>>,

    /// Session ID
    #[serde(default)]
    pub sid: Option<String>,

    /// Token type (typically "Bearer")
    #[serde(default)]
    pub typ: Option<String>,

    /// Scope
    #[serde(default)]
    pub scope: Option<String>,
}

/// Audience can be a single string or array of strings.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(untagged)]
pub enum Audience {
    #[default]
    None,
    Single(String),
    Multiple(Vec<String>),
}

impl Audience {
    /// Check if the audience contains a specific value.
    pub fn contains(&self, aud: &str) -> bool {
        match self {
            Audience::None => false,
            Audience::Single(s) => s == aud,
            Audience::Multiple(v) => v.iter().any(|a| a == aud),
        }
    }

    /// Get all audience values.
    pub fn values(&self) -> Vec<&str> {
        match self {
            Audience::None => vec![],
            Audience::Single(s) => vec![s.as_str()],
            Audience::Multiple(v) => v.iter().map(|s| s.as_str()).collect(),
        }
    }
}

/// Realm-level access roles.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct RealmAccess {
    /// List of realm roles
    #[serde(default)]
    pub roles: Vec<String>,
}

/// Client-specific resource access.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ResourceAccess {
    /// List of client roles
    #[serde(default)]
    pub roles: Vec<String>,
}

impl Claims {
    /// Get the user ID (subject).
    pub fn user_id(&self) -> &str {
        &self.sub
    }

    /// Get the username.
    pub fn username(&self) -> Option<&str> {
        self.preferred_username.as_deref()
    }

    /// Get the tenant ID from custom claim or extract from realm roles.
    pub fn tenant_id(&self) -> Option<&str> {
        // First, check explicit tenant claim
        if let Some(tenant) = &self.tenant {
            return Some(tenant.as_str());
        }

        // Fallback: look for tenant-xxx role pattern
        if let Some(realm_access) = &self.realm_access {
            for role in &realm_access.roles {
                if let Some(tenant) = role.strip_prefix("tenant-") {
                    return Some(tenant);
                }
            }
        }

        None
    }

    /// Get all realm roles.
    pub fn realm_roles(&self) -> Vec<&str> {
        self.realm_access
            .as_ref()
            .map(|r| r.roles.iter().map(|s| s.as_str()).collect())
            .unwrap_or_default()
    }

    /// Get roles for a specific client.
    pub fn client_roles(&self, client_id: &str) -> Vec<&str> {
        self.resource_access
            .as_ref()
            .and_then(|r| r.get(client_id))
            .map(|a| a.roles.iter().map(|s| s.as_str()).collect())
            .unwrap_or_default()
    }

    /// Check if the user has a specific realm role.
    pub fn has_realm_role(&self, role: &str) -> bool {
        self.realm_access
            .as_ref()
            .map(|r| r.roles.iter().any(|r| r == role))
            .unwrap_or(false)
    }

    /// Check if the user has a specific client role.
    pub fn has_client_role(&self, client_id: &str, role: &str) -> bool {
        self.resource_access
            .as_ref()
            .and_then(|r| r.get(client_id))
            .map(|a| a.roles.iter().any(|r| r == role))
            .unwrap_or(false)
    }

    /// Check if the token is expired.
    pub fn is_expired(&self) -> bool {
        let now = chrono::Utc::now().timestamp();
        self.exp < now
    }

    /// Get scopes as a vector.
    pub fn scopes(&self) -> Vec<&str> {
        self.scope
            .as_ref()
            .map(|s| s.split_whitespace().collect())
            .unwrap_or_default()
    }

    /// Check if the token has a specific scope.
    pub fn has_scope(&self, scope: &str) -> bool {
        self.scopes().contains(&scope)
    }
}

// =============================================================================
// STOA-Specific Role Mapping
// =============================================================================

/// STOA platform roles.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StoaRole {
    /// Platform administrator (full access)
    CpiAdmin,
    /// Tenant administrator
    TenantAdmin,
    /// DevOps role (deploy, promote)
    DevOps,
    /// Read-only viewer
    Viewer,
}

impl StoaRole {
    /// Parse a role string into a StoaRole.
    pub fn from_str(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "cpi-admin" | "cpi_admin" | "admin" => Some(StoaRole::CpiAdmin),
            "tenant-admin" | "tenant_admin" => Some(StoaRole::TenantAdmin),
            "devops" | "dev-ops" => Some(StoaRole::DevOps),
            "viewer" | "read-only" | "readonly" => Some(StoaRole::Viewer),
            _ => None,
        }
    }

    /// Get the role name.
    pub fn as_str(&self) -> &'static str {
        match self {
            StoaRole::CpiAdmin => "cpi-admin",
            StoaRole::TenantAdmin => "tenant-admin",
            StoaRole::DevOps => "devops",
            StoaRole::Viewer => "viewer",
        }
    }

    /// Check if this role can write (create/update APIs).
    pub fn can_write(&self) -> bool {
        matches!(
            self,
            StoaRole::CpiAdmin | StoaRole::TenantAdmin | StoaRole::DevOps
        )
    }

    /// Check if this role is admin.
    pub fn is_admin(&self) -> bool {
        matches!(self, StoaRole::CpiAdmin | StoaRole::TenantAdmin)
    }
}

impl Claims {
    /// Get the highest STOA role from the claims.
    pub fn stoa_role(&self) -> Option<StoaRole> {
        let roles = self.realm_roles();

        // Check in priority order
        if roles
            .iter()
            .any(|r| StoaRole::from_str(r) == Some(StoaRole::CpiAdmin))
        {
            return Some(StoaRole::CpiAdmin);
        }
        if roles
            .iter()
            .any(|r| StoaRole::from_str(r) == Some(StoaRole::TenantAdmin))
        {
            return Some(StoaRole::TenantAdmin);
        }
        if roles
            .iter()
            .any(|r| StoaRole::from_str(r) == Some(StoaRole::DevOps))
        {
            return Some(StoaRole::DevOps);
        }
        if roles
            .iter()
            .any(|r| StoaRole::from_str(r) == Some(StoaRole::Viewer))
        {
            return Some(StoaRole::Viewer);
        }

        None
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_claims() -> Claims {
        Claims {
            sub: "user-123".to_string(),
            exp: chrono::Utc::now().timestamp() + 3600,
            iat: chrono::Utc::now().timestamp(),
            iss: "https://auth.gostoa.dev/realms/stoa".to_string(),
            aud: Audience::Single("stoa-mcp".to_string()),
            azp: Some("stoa-mcp".to_string()),
            preferred_username: Some("john.doe".to_string()),
            email: Some("john.doe@acme.com".to_string()),
            email_verified: Some(true),
            name: Some("John Doe".to_string()),
            given_name: Some("John".to_string()),
            family_name: Some("Doe".to_string()),
            tenant: Some("acme".to_string()),
            realm_access: Some(RealmAccess {
                roles: vec!["tenant-admin".to_string(), "offline_access".to_string()],
            }),
            resource_access: Some(HashMap::from([(
                "stoa-mcp".to_string(),
                ResourceAccess {
                    roles: vec!["api-creator".to_string()],
                },
            )])),
            sid: Some("session-456".to_string()),
            typ: Some("Bearer".to_string()),
            scope: Some("openid profile email stoa:write".to_string()),
        }
    }

    #[test]
    fn test_claims_user_id() {
        let claims = sample_claims();
        assert_eq!(claims.user_id(), "user-123");
    }

    #[test]
    fn test_claims_tenant_from_claim() {
        let claims = sample_claims();
        assert_eq!(claims.tenant_id(), Some("acme"));
    }

    #[test]
    fn test_claims_tenant_from_role() {
        let mut claims = sample_claims();
        claims.tenant = None;
        claims.realm_access = Some(RealmAccess {
            roles: vec!["tenant-demo".to_string()],
        });
        assert_eq!(claims.tenant_id(), Some("demo"));
    }

    #[test]
    fn test_claims_realm_roles() {
        let claims = sample_claims();
        let roles = claims.realm_roles();
        assert!(roles.contains(&"tenant-admin"));
    }

    #[test]
    fn test_claims_client_roles() {
        let claims = sample_claims();
        let roles = claims.client_roles("stoa-mcp");
        assert!(roles.contains(&"api-creator"));
    }

    #[test]
    fn test_claims_has_realm_role() {
        let claims = sample_claims();
        assert!(claims.has_realm_role("tenant-admin"));
        assert!(!claims.has_realm_role("cpi-admin"));
    }

    #[test]
    fn test_claims_scopes() {
        let claims = sample_claims();
        assert!(claims.has_scope("openid"));
        assert!(claims.has_scope("stoa:write"));
        assert!(!claims.has_scope("stoa:admin"));
    }

    #[test]
    fn test_audience_single() {
        let aud = Audience::Single("stoa-mcp".to_string());
        assert!(aud.contains("stoa-mcp"));
        assert!(!aud.contains("other"));
    }

    #[test]
    fn test_audience_multiple() {
        let aud = Audience::Multiple(vec!["stoa-mcp".to_string(), "stoa-api".to_string()]);
        assert!(aud.contains("stoa-mcp"));
        assert!(aud.contains("stoa-api"));
        assert!(!aud.contains("other"));
    }

    #[test]
    fn test_stoa_role_parsing() {
        assert_eq!(StoaRole::from_str("cpi-admin"), Some(StoaRole::CpiAdmin));
        assert_eq!(
            StoaRole::from_str("tenant-admin"),
            Some(StoaRole::TenantAdmin)
        );
        assert_eq!(StoaRole::from_str("devops"), Some(StoaRole::DevOps));
        assert_eq!(StoaRole::from_str("viewer"), Some(StoaRole::Viewer));
        assert_eq!(StoaRole::from_str("unknown"), None);
    }

    #[test]
    fn test_stoa_role_from_claims() {
        let claims = sample_claims();
        assert_eq!(claims.stoa_role(), Some(StoaRole::TenantAdmin));
    }

    #[test]
    fn test_stoa_role_permissions() {
        assert!(StoaRole::CpiAdmin.can_write());
        assert!(StoaRole::TenantAdmin.can_write());
        assert!(StoaRole::DevOps.can_write());
        assert!(!StoaRole::Viewer.can_write());
    }
}
