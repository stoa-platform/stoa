//! RBAC (Role-Based Access Control)
//!
//! CAB-912 P2: Role-based access control with tenant isolation.
//!
//! Features:
//! - Permission checking based on STOA roles
//! - Tenant isolation enforcement
//! - Scope-based authorization
//! - Action-based permissions

use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use thiserror::Error;
use tracing::{debug, warn};

use super::claims::{Claims, StoaRole};
use super::middleware::AuthenticatedUser;

// =============================================================================
// Errors
// =============================================================================

#[derive(Debug, Error)]
pub enum RbacError {
    #[error("Access denied: {0}")]
    AccessDenied(String),

    #[error("Tenant mismatch: user tenant '{user_tenant}' cannot access tenant '{target_tenant}'")]
    TenantMismatch {
        user_tenant: String,
        target_tenant: String,
    },

    #[error("Missing required role: {0}")]
    MissingRole(String),

    #[error("Missing required scope: {0}")]
    MissingScope(String),

    #[error("Insufficient permissions for action: {0}")]
    InsufficientPermissions(String),
}

// =============================================================================
// Actions
// =============================================================================

/// Actions that can be performed in the STOA platform.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Action {
    /// List APIs
    ListApis,

    /// Read API details
    ReadApi,

    /// Create a new API
    CreateApi,

    /// Update an existing API
    UpdateApi,

    /// Delete an API
    DeleteApi,

    /// Promote an API (change state)
    PromoteApi,

    /// Approve a pending API (for VH/VVH)
    ApproveApi,

    /// View audit logs
    ViewAuditLogs,

    /// Manage tenant settings
    ManageTenant,

    /// Platform administration
    AdminPlatform,
}

impl Action {
    /// Get the required scope for this action.
    pub fn required_scope(&self) -> &'static str {
        match self {
            Action::ListApis | Action::ReadApi => "stoa:read",
            Action::CreateApi | Action::UpdateApi | Action::DeleteApi | Action::PromoteApi => {
                "stoa:write"
            }
            Action::ApproveApi | Action::ManageTenant => "stoa:write",
            Action::ViewAuditLogs => "stoa:read",
            Action::AdminPlatform => "stoa:admin",
        }
    }

    /// Get the minimum role required for this action.
    pub fn minimum_role(&self) -> StoaRole {
        match self {
            Action::ListApis | Action::ReadApi | Action::ViewAuditLogs => StoaRole::Viewer,
            Action::CreateApi | Action::UpdateApi | Action::PromoteApi => StoaRole::DevOps,
            Action::DeleteApi | Action::ManageTenant => StoaRole::TenantAdmin,
            Action::ApproveApi | Action::AdminPlatform => StoaRole::CpiAdmin,
        }
    }

    /// Check if an action is admin-only.
    pub fn is_admin_only(&self) -> bool {
        matches!(self, Action::ApproveApi | Action::AdminPlatform)
    }
}

// =============================================================================
// RBAC Policy
// =============================================================================

/// RBAC policy for authorization decisions.
#[derive(Debug, Clone)]
pub struct RbacPolicy {
    /// Whether to enforce tenant isolation
    pub enforce_tenant_isolation: bool,

    /// Whether to require scopes
    pub require_scopes: bool,

    /// Actions that are always allowed (bypass role check)
    pub always_allowed: HashSet<Action>,

    /// Actions that are always denied
    pub always_denied: HashSet<Action>,
}

impl Default for RbacPolicy {
    fn default() -> Self {
        Self {
            enforce_tenant_isolation: true,
            require_scopes: true,
            always_allowed: HashSet::new(),
            always_denied: HashSet::new(),
        }
    }
}

impl RbacPolicy {
    /// Create a permissive policy (for development).
    pub fn permissive() -> Self {
        Self {
            enforce_tenant_isolation: false,
            require_scopes: false,
            always_allowed: HashSet::new(),
            always_denied: HashSet::new(),
        }
    }

    /// Create a strict policy (for production).
    pub fn strict() -> Self {
        Self::default()
    }
}

// =============================================================================
// RBAC Enforcer
// =============================================================================

/// RBAC enforcer for authorization decisions.
#[derive(Debug, Clone)]
pub struct RbacEnforcer {
    policy: RbacPolicy,
}

impl RbacEnforcer {
    /// Create a new RBAC enforcer with default policy.
    pub fn new() -> Self {
        Self {
            policy: RbacPolicy::default(),
        }
    }

    /// Create with a custom policy.
    pub fn with_policy(policy: RbacPolicy) -> Self {
        Self { policy }
    }

    /// Check if a user can perform an action on a resource.
    pub fn authorize(
        &self,
        user: &AuthenticatedUser,
        action: Action,
        target_tenant: Option<&str>,
    ) -> Result<(), RbacError> {
        debug!(
            user_id = %user.user_id,
            action = ?action,
            target_tenant = ?target_tenant,
            "Checking RBAC authorization"
        );

        // Check always denied
        if self.policy.always_denied.contains(&action) {
            return Err(RbacError::AccessDenied("Action is disabled".to_string()));
        }

        // Check always allowed
        if self.policy.always_allowed.contains(&action) {
            return Ok(());
        }

        // Check tenant isolation
        if self.policy.enforce_tenant_isolation {
            if let Some(target) = target_tenant {
                self.check_tenant_access(user, target)?;
            }
        }

        // Check scopes
        if self.policy.require_scopes {
            self.check_scope(user, action)?;
        }

        // Check role
        self.check_role(user, action)?;

        Ok(())
    }

    /// Check if user can access a specific tenant.
    fn check_tenant_access(
        &self,
        user: &AuthenticatedUser,
        target_tenant: &str,
    ) -> Result<(), RbacError> {
        // CPI admins can access any tenant
        if user.claims.stoa_role() == Some(StoaRole::CpiAdmin) {
            return Ok(());
        }

        // Check if user's tenant matches target
        match &user.tenant_id {
            Some(user_tenant) if user_tenant == target_tenant => Ok(()),
            Some(user_tenant) => {
                warn!(
                    user_id = %user.user_id,
                    user_tenant = %user_tenant,
                    target_tenant = %target_tenant,
                    "Tenant access denied"
                );
                Err(RbacError::TenantMismatch {
                    user_tenant: user_tenant.clone(),
                    target_tenant: target_tenant.to_string(),
                })
            }
            None => Err(RbacError::TenantMismatch {
                user_tenant: "none".to_string(),
                target_tenant: target_tenant.to_string(),
            }),
        }
    }

    /// Check if user has required scope for action.
    fn check_scope(&self, user: &AuthenticatedUser, action: Action) -> Result<(), RbacError> {
        let required = action.required_scope();

        // CPI admins bypass scope check
        if user.claims.stoa_role() == Some(StoaRole::CpiAdmin) {
            return Ok(());
        }

        if !user.has_scope(required) {
            return Err(RbacError::MissingScope(required.to_string()));
        }

        Ok(())
    }

    /// Check if user has required role for action.
    fn check_role(&self, user: &AuthenticatedUser, action: Action) -> Result<(), RbacError> {
        let user_role = user.claims.stoa_role();
        let required_role = action.minimum_role();

        match user_role {
            Some(role) if role_satisfies(role, required_role) => Ok(()),
            Some(role) => {
                warn!(
                    user_id = %user.user_id,
                    user_role = ?role,
                    required_role = ?required_role,
                    "Insufficient role"
                );
                Err(RbacError::InsufficientPermissions(format!(
                    "Requires {} role, but user has {}",
                    required_role.as_str(),
                    role.as_str()
                )))
            }
            None => Err(RbacError::MissingRole(required_role.as_str().to_string())),
        }
    }

    /// Quick check if user can perform action (returns bool).
    pub fn can(&self, user: &AuthenticatedUser, action: Action, tenant: Option<&str>) -> bool {
        self.authorize(user, action, tenant).is_ok()
    }
}

impl Default for RbacEnforcer {
    fn default() -> Self {
        Self::new()
    }
}

/// Check if a role satisfies the required minimum role.
fn role_satisfies(actual: StoaRole, required: StoaRole) -> bool {
    use StoaRole::*;

    match required {
        Viewer => true, // Any role satisfies Viewer
        DevOps => matches!(actual, DevOps | TenantAdmin | CpiAdmin),
        TenantAdmin => matches!(actual, TenantAdmin | CpiAdmin),
        CpiAdmin => actual == CpiAdmin,
    }
}

// =============================================================================
// Authorization Context
// =============================================================================

/// Context for authorization decisions.
#[derive(Debug, Clone)]
pub struct AuthzContext {
    /// The authenticated user
    pub user: AuthenticatedUser,

    /// Target tenant (if applicable)
    pub target_tenant: Option<String>,

    /// Target resource ID (if applicable)
    pub resource_id: Option<String>,

    /// Additional metadata
    pub metadata: std::collections::HashMap<String, String>,
}

impl AuthzContext {
    /// Create a new authorization context.
    pub fn new(user: AuthenticatedUser) -> Self {
        Self {
            user,
            target_tenant: None,
            resource_id: None,
            metadata: std::collections::HashMap::new(),
        }
    }

    /// Set the target tenant.
    pub fn for_tenant(mut self, tenant: impl Into<String>) -> Self {
        self.target_tenant = Some(tenant.into());
        self
    }

    /// Set the target resource.
    pub fn for_resource(mut self, resource_id: impl Into<String>) -> Self {
        self.resource_id = Some(resource_id.into());
        self
    }

    /// Add metadata.
    pub fn with_metadata(mut self, key: impl Into<String>, value: impl Into<String>) -> Self {
        self.metadata.insert(key.into(), value.into());
        self
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use crate::auth::claims::{Audience, RealmAccess};
    use crate::auth::jwt::ValidatedToken;

    fn make_user(role: &str, tenant: Option<&str>, scopes: &str) -> AuthenticatedUser {
        let claims = Claims {
            sub: "user-123".to_string(),
            exp: chrono::Utc::now().timestamp() + 3600,
            iat: chrono::Utc::now().timestamp(),
            iss: "https://auth.gostoa.dev/realms/stoa".to_string(),
            aud: Audience::Single("stoa-mcp".to_string()),
            azp: None,
            preferred_username: Some("testuser".to_string()),
            email: None,
            email_verified: None,
            name: None,
            given_name: None,
            family_name: None,
            tenant: tenant.map(|s| s.to_string()),
            realm_access: Some(RealmAccess {
                roles: vec![role.to_string()],
            }),
            resource_access: None,
            sid: None,
            typ: None,
            scope: Some(scopes.to_string()),
        };

        let token = ValidatedToken::new("token".to_string(), claims);
        AuthenticatedUser::from_token(token)
    }

    #[test]
    fn test_role_satisfies() {
        // Viewer is satisfied by all roles
        assert!(role_satisfies(StoaRole::Viewer, StoaRole::Viewer));
        assert!(role_satisfies(StoaRole::DevOps, StoaRole::Viewer));
        assert!(role_satisfies(StoaRole::TenantAdmin, StoaRole::Viewer));
        assert!(role_satisfies(StoaRole::CpiAdmin, StoaRole::Viewer));

        // DevOps requires DevOps or higher
        assert!(!role_satisfies(StoaRole::Viewer, StoaRole::DevOps));
        assert!(role_satisfies(StoaRole::DevOps, StoaRole::DevOps));
        assert!(role_satisfies(StoaRole::TenantAdmin, StoaRole::DevOps));
        assert!(role_satisfies(StoaRole::CpiAdmin, StoaRole::DevOps));

        // TenantAdmin requires TenantAdmin or higher
        assert!(!role_satisfies(StoaRole::Viewer, StoaRole::TenantAdmin));
        assert!(!role_satisfies(StoaRole::DevOps, StoaRole::TenantAdmin));
        assert!(role_satisfies(StoaRole::TenantAdmin, StoaRole::TenantAdmin));
        assert!(role_satisfies(StoaRole::CpiAdmin, StoaRole::TenantAdmin));

        // CpiAdmin requires CpiAdmin
        assert!(!role_satisfies(StoaRole::Viewer, StoaRole::CpiAdmin));
        assert!(!role_satisfies(StoaRole::DevOps, StoaRole::CpiAdmin));
        assert!(!role_satisfies(StoaRole::TenantAdmin, StoaRole::CpiAdmin));
        assert!(role_satisfies(StoaRole::CpiAdmin, StoaRole::CpiAdmin));
    }

    #[test]
    fn test_action_scopes() {
        assert_eq!(Action::ListApis.required_scope(), "stoa:read");
        assert_eq!(Action::CreateApi.required_scope(), "stoa:write");
        assert_eq!(Action::AdminPlatform.required_scope(), "stoa:admin");
    }

    #[test]
    fn test_authorize_viewer_read() {
        let enforcer = RbacEnforcer::new();
        let user = make_user("viewer", Some("acme"), "openid stoa:read");

        assert!(enforcer
            .authorize(&user, Action::ListApis, Some("acme"))
            .is_ok());
        assert!(enforcer
            .authorize(&user, Action::ReadApi, Some("acme"))
            .is_ok());
    }

    #[test]
    fn test_authorize_viewer_cannot_write() {
        let enforcer = RbacEnforcer::new();
        let user = make_user("viewer", Some("acme"), "openid stoa:read");

        let result = enforcer.authorize(&user, Action::CreateApi, Some("acme"));
        assert!(result.is_err());
    }

    #[test]
    fn test_authorize_devops_write() {
        let enforcer = RbacEnforcer::new();
        let user = make_user("devops", Some("acme"), "openid stoa:read stoa:write");

        assert!(enforcer
            .authorize(&user, Action::CreateApi, Some("acme"))
            .is_ok());
        assert!(enforcer
            .authorize(&user, Action::UpdateApi, Some("acme"))
            .is_ok());
    }

    #[test]
    fn test_authorize_tenant_isolation() {
        let enforcer = RbacEnforcer::new();
        let user = make_user("tenant-admin", Some("acme"), "openid stoa:read stoa:write");

        // Can access own tenant
        assert!(enforcer
            .authorize(&user, Action::ReadApi, Some("acme"))
            .is_ok());

        // Cannot access other tenant
        let result = enforcer.authorize(&user, Action::ReadApi, Some("other"));
        assert!(matches!(result, Err(RbacError::TenantMismatch { .. })));
    }

    #[test]
    fn test_authorize_admin_cross_tenant() {
        let enforcer = RbacEnforcer::new();
        let user = make_user("cpi-admin", Some("admin"), "openid stoa:admin");

        // Admin can access any tenant
        assert!(enforcer
            .authorize(&user, Action::ReadApi, Some("acme"))
            .is_ok());
        assert!(enforcer
            .authorize(&user, Action::ReadApi, Some("other"))
            .is_ok());
    }

    #[test]
    fn test_authorize_missing_scope() {
        let enforcer = RbacEnforcer::new();
        let user = make_user("devops", Some("acme"), "openid");

        let result = enforcer.authorize(&user, Action::CreateApi, Some("acme"));
        assert!(matches!(result, Err(RbacError::MissingScope(_))));
    }

    #[test]
    fn test_can_method() {
        let enforcer = RbacEnforcer::new();
        let user = make_user("viewer", Some("acme"), "openid stoa:read");

        assert!(enforcer.can(&user, Action::ListApis, Some("acme")));
        assert!(!enforcer.can(&user, Action::CreateApi, Some("acme")));
    }

    #[test]
    fn test_permissive_policy() {
        let enforcer = RbacEnforcer::with_policy(RbacPolicy::permissive());
        let user = make_user("viewer", Some("acme"), "openid");

        // Permissive: no tenant isolation, no scope check
        // But still checks role
        assert!(enforcer
            .authorize(&user, Action::ReadApi, Some("other"))
            .is_ok());
    }
}
