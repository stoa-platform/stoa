use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Tenant context extracted from JWT claims
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TenantContext {
    /// Tenant identifier
    pub tenant_id: String,
    /// User identifier within the tenant
    pub user_id: Option<String>,
    /// User's roles within the tenant
    pub roles: Vec<String>,
    /// OAuth scopes granted to the user
    pub scopes: Vec<String>,
    /// Additional claims from the JWT
    #[serde(default)]
    pub claims: HashMap<String, serde_json::Value>,
}

impl TenantContext {
    /// Create a new tenant context
    pub fn new(tenant_id: impl Into<String>) -> Self {
        Self {
            tenant_id: tenant_id.into(),
            user_id: None,
            roles: Vec::new(),
            scopes: Vec::new(),
            claims: HashMap::new(),
        }
    }

    /// Set the user ID
    pub fn with_user(mut self, user_id: impl Into<String>) -> Self {
        self.user_id = Some(user_id.into());
        self
    }

    /// Add roles to the context
    pub fn with_roles(mut self, roles: Vec<String>) -> Self {
        self.roles = roles;
        self
    }

    /// Add scopes to the context
    pub fn with_scopes(mut self, scopes: Vec<String>) -> Self {
        self.scopes = scopes;
        self
    }

    /// Add a custom claim
    pub fn with_claim(mut self, key: impl Into<String>, value: serde_json::Value) -> Self {
        self.claims.insert(key.into(), value);
        self
    }

    /// Check if the user has a specific role
    pub fn has_role(&self, role: &str) -> bool {
        self.roles.iter().any(|r| r == role)
    }

    /// Check if the user has a specific scope
    pub fn has_scope(&self, scope: &str) -> bool {
        self.scopes.iter().any(|s| s == scope)
    }

    /// Check if the user has any of the specified roles
    pub fn has_any_role(&self, roles: &[&str]) -> bool {
        roles.iter().any(|r| self.has_role(r))
    }

    /// Check if the user has all of the specified scopes
    pub fn has_all_scopes(&self, scopes: &[&str]) -> bool {
        scopes.iter().all(|s| self.has_scope(s))
    }

    /// Get a claim value by key
    pub fn get_claim(&self, key: &str) -> Option<&serde_json::Value> {
        self.claims.get(key)
    }
}

impl Default for TenantContext {
    fn default() -> Self {
        Self::new("default")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_new_tenant_context() {
        let ctx = TenantContext::new("acme-corp");
        assert_eq!(ctx.tenant_id, "acme-corp");
        assert!(ctx.user_id.is_none());
        assert!(ctx.roles.is_empty());
        assert!(ctx.scopes.is_empty());
    }

    #[test]
    fn test_builder_pattern() {
        let ctx = TenantContext::new("acme-corp")
            .with_user("user123")
            .with_roles(vec!["admin".to_string(), "developer".to_string()])
            .with_scopes(vec!["stoa:read".to_string(), "stoa:write".to_string()])
            .with_claim("department", json!("engineering"));

        assert_eq!(ctx.tenant_id, "acme-corp");
        assert_eq!(ctx.user_id, Some("user123".to_string()));
        assert_eq!(ctx.roles.len(), 2);
        assert_eq!(ctx.scopes.len(), 2);
        assert!(ctx.claims.contains_key("department"));
    }

    #[test]
    fn test_has_role() {
        let ctx =
            TenantContext::new("test").with_roles(vec!["admin".to_string(), "viewer".to_string()]);

        assert!(ctx.has_role("admin"));
        assert!(ctx.has_role("viewer"));
        assert!(!ctx.has_role("superuser"));
    }

    #[test]
    fn test_has_scope() {
        let ctx = TenantContext::new("test")
            .with_scopes(vec!["stoa:read".to_string(), "stoa:write".to_string()]);

        assert!(ctx.has_scope("stoa:read"));
        assert!(ctx.has_scope("stoa:write"));
        assert!(!ctx.has_scope("stoa:admin"));
    }

    #[test]
    fn test_has_any_role() {
        let ctx = TenantContext::new("test").with_roles(vec!["developer".to_string()]);

        assert!(ctx.has_any_role(&["admin", "developer"]));
        assert!(!ctx.has_any_role(&["admin", "superuser"]));
    }

    #[test]
    fn test_has_all_scopes() {
        let ctx = TenantContext::new("test").with_scopes(vec![
            "stoa:read".to_string(),
            "stoa:write".to_string(),
            "stoa:admin".to_string(),
        ]);

        assert!(ctx.has_all_scopes(&["stoa:read", "stoa:write"]));
        assert!(!ctx.has_all_scopes(&["stoa:read", "stoa:delete"]));
    }

    #[test]
    fn test_get_claim() {
        let ctx = TenantContext::new("test")
            .with_claim("team", json!("platform"))
            .with_claim("level", json!(5));

        assert_eq!(ctx.get_claim("team"), Some(&json!("platform")));
        assert_eq!(ctx.get_claim("level"), Some(&json!(5)));
        assert_eq!(ctx.get_claim("missing"), None);
    }

    #[test]
    fn test_serialization() {
        let ctx = TenantContext::new("acme")
            .with_user("user1")
            .with_roles(vec!["admin".to_string()]);

        let json = serde_json::to_string(&ctx).unwrap();
        let ctx2: TenantContext = serde_json::from_str(&json).unwrap();

        assert_eq!(ctx.tenant_id, ctx2.tenant_id);
        assert_eq!(ctx.user_id, ctx2.user_id);
        assert_eq!(ctx.roles, ctx2.roles);
    }
}
