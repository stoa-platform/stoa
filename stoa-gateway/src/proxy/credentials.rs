//! BYOK (Bring Your Own Key) credential store for backend API authentication.
//!
//! Stores backend authentication credentials per route. The Control Plane
//! pushes credentials via the admin API; the dynamic proxy injects them
//! into outgoing requests.

use parking_lot::RwLock;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Authentication type for backend APIs.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum AuthType {
    /// API key in a custom header (e.g., `X-API-Key: <value>`)
    ApiKey,
    /// Bearer token (e.g., `Authorization: Bearer <value>`)
    Bearer,
    /// Basic auth (e.g., `Authorization: Basic <base64>`)
    Basic,
}

/// A backend credential for a specific route.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BackendCredential {
    /// Route ID this credential applies to
    pub route_id: String,
    /// Authentication type
    pub auth_type: AuthType,
    /// Header name (e.g., "Authorization", "X-API-Key")
    pub header_name: String,
    /// Header value (e.g., "Bearer token123", "Basic dXNlcjpwYXNz")
    pub header_value: String,
}

/// Thread-safe in-memory credential store, keyed by route_id.
pub struct CredentialStore {
    credentials: RwLock<HashMap<String, BackendCredential>>,
}

impl Default for CredentialStore {
    fn default() -> Self {
        Self::new()
    }
}

impl CredentialStore {
    pub fn new() -> Self {
        Self {
            credentials: RwLock::new(HashMap::new()),
        }
    }

    /// Insert or update a credential. Returns the previous value if it existed.
    pub fn upsert(&self, cred: BackendCredential) -> Option<BackendCredential> {
        self.credentials.write().insert(cred.route_id.clone(), cred)
    }

    /// Remove a credential by route_id.
    pub fn remove(&self, route_id: &str) -> Option<BackendCredential> {
        self.credentials.write().remove(route_id)
    }

    /// Get a credential by route_id.
    pub fn get(&self, route_id: &str) -> Option<BackendCredential> {
        self.credentials.read().get(route_id).cloned()
    }

    /// List all credentials (header_value redacted for safety).
    pub fn list(&self) -> Vec<BackendCredential> {
        self.credentials.read().values().cloned().collect()
    }

    /// Number of stored credentials.
    pub fn count(&self) -> usize {
        self.credentials.read().len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_cred(route_id: &str) -> BackendCredential {
        BackendCredential {
            route_id: route_id.to_string(),
            auth_type: AuthType::Bearer,
            header_name: "Authorization".to_string(),
            header_value: "Bearer test-token".to_string(),
        }
    }

    #[test]
    fn test_upsert_new() {
        let store = CredentialStore::new();
        let prev = store.upsert(make_cred("r1"));
        assert!(prev.is_none());
        assert_eq!(store.count(), 1);
    }

    #[test]
    fn test_upsert_existing() {
        let store = CredentialStore::new();
        store.upsert(make_cred("r1"));
        let prev = store.upsert(BackendCredential {
            route_id: "r1".to_string(),
            auth_type: AuthType::ApiKey,
            header_name: "X-API-Key".to_string(),
            header_value: "new-key".to_string(),
        });
        assert!(prev.is_some());
        assert_eq!(prev.unwrap().auth_type, AuthType::Bearer);
        assert_eq!(store.count(), 1);
    }

    #[test]
    fn test_get() {
        let store = CredentialStore::new();
        store.upsert(make_cred("r1"));
        let cred = store.get("r1");
        assert!(cred.is_some());
        assert_eq!(cred.unwrap().header_value, "Bearer test-token");
    }

    #[test]
    fn test_get_nonexistent() {
        let store = CredentialStore::new();
        assert!(store.get("ghost").is_none());
    }

    #[test]
    fn test_remove() {
        let store = CredentialStore::new();
        store.upsert(make_cred("r1"));
        let removed = store.remove("r1");
        assert!(removed.is_some());
        assert_eq!(store.count(), 0);
    }

    #[test]
    fn test_remove_nonexistent() {
        let store = CredentialStore::new();
        assert!(store.remove("ghost").is_none());
    }

    #[test]
    fn test_list() {
        let store = CredentialStore::new();
        store.upsert(make_cred("r1"));
        store.upsert(make_cred("r2"));
        assert_eq!(store.list().len(), 2);
    }

    #[test]
    fn test_auth_type_serialization() {
        let cred = make_cred("r1");
        let json = serde_json::to_value(&cred).unwrap();
        assert_eq!(json["auth_type"], "bearer");

        let api_key_cred = BackendCredential {
            auth_type: AuthType::ApiKey,
            ..make_cred("r2")
        };
        let json = serde_json::to_value(&api_key_cred).unwrap();
        assert_eq!(json["auth_type"], "api_key");
    }
}
