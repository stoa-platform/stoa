//! UAC (Universal API Contract) module
//!
//! Defines actions and permissions for API access control.

pub mod binders;
pub mod cache;
pub mod classifications;
pub mod enforcer;
pub mod registry;
pub mod safe_mode;
pub mod schema;

pub use classifications::Classification;
pub use enforcer::ClassificationEnforcer;
pub use registry::ContractRegistry;
pub use schema::{ContractStatus, UacContractSpec, UacEndpoint};

use serde::{Deserialize, Serialize};

/// UAC Actions
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Action {
    // Read operations
    Read,
    List,
    Search,

    // Write operations
    Create,
    Update,
    Delete,

    // API-specific
    CreateApi,
    UpdateApi,
    DeleteApi,
    PublishApi,
    DeprecateApi,

    // Subscription
    Subscribe,
    Unsubscribe,
    ManageSubscription,

    // Admin
    ManageUsers,
    ManageTenants,
    ManageContracts,
    ViewMetrics,
    ViewLogs,
    ViewAudit,
}

impl Action {
    /// Check if this action requires write permission
    #[allow(dead_code)]
    pub fn is_write(&self) -> bool {
        matches!(
            self,
            Action::Create
                | Action::Update
                | Action::Delete
                | Action::CreateApi
                | Action::UpdateApi
                | Action::DeleteApi
                | Action::PublishApi
                | Action::DeprecateApi
                | Action::Subscribe
                | Action::Unsubscribe
                | Action::ManageSubscription
                | Action::ManageUsers
                | Action::ManageTenants
                | Action::ManageContracts
        )
    }

    /// Check if this action requires admin permission
    #[allow(dead_code)]
    pub fn is_admin(&self) -> bool {
        matches!(
            self,
            Action::ManageUsers
                | Action::ManageTenants
                | Action::ManageContracts
                | Action::ViewAudit
        )
    }
}

impl std::fmt::Display for Action {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{:?}", self)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_action_write_check() {
        assert!(!Action::Read.is_write());
        assert!(Action::Create.is_write());
        assert!(Action::CreateApi.is_write());
    }

    #[test]
    fn test_action_admin_check() {
        assert!(!Action::Read.is_admin());
        assert!(!Action::CreateApi.is_admin());
        assert!(Action::ManageUsers.is_admin());
    }
}
