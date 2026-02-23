//! Per-consumer credential store for backend API auth (CAB-1432).
//!
//! Consumers authenticate to STOA via OAuth2 (Keycloak JWT), but backend APIs
//! may require their own credentials (API keys, Bearer tokens, Basic Auth).
//! This store maps `(route_id, consumer_id)` → backend credential so the
//! gateway can inject the correct header before forwarding.
//!
//! Falls back to the route-level [`super::CredentialStore`] (BYOK) when no
//! per-consumer mapping exists.

use parking_lot::RwLock;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Composite key: (route_id, consumer_id).
type ConsumerCredentialKey = (String, String);

/// Auth type for the backend credential.
#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ConsumerAuthType {
    #[default]
    ApiKey,
    Bearer,
    Basic,
}

/// A per-consumer backend credential.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConsumerCredential {
    pub route_id: String,
    pub consumer_id: String,
    #[serde(default)]
    pub auth_type: ConsumerAuthType,
    pub header_name: String,
    pub header_value: String,
}

/// Thread-safe store for per-consumer backend credentials.
///
/// Mirrors [`super::CredentialStore`] but keyed by `(route_id, consumer_id)`
/// instead of just `route_id`.
pub struct ConsumerCredentialStore {
    credentials: RwLock<HashMap<ConsumerCredentialKey, ConsumerCredential>>,
}

impl Default for ConsumerCredentialStore {
    fn default() -> Self {
        Self::new()
    }
}

impl ConsumerCredentialStore {
    /// Create an empty store.
    pub fn new() -> Self {
        Self {
            credentials: RwLock::new(HashMap::new()),
        }
    }

    /// Insert or update a consumer credential.
    /// Returns the previous credential if one existed for this key.
    pub fn upsert(&self, cred: ConsumerCredential) -> Option<ConsumerCredential> {
        let key = (cred.route_id.clone(), cred.consumer_id.clone());
        self.credentials.write().insert(key, cred)
    }

    /// Remove a consumer credential by route and consumer ID.
    pub fn remove(&self, route_id: &str, consumer_id: &str) -> Option<ConsumerCredential> {
        let key = (route_id.to_owned(), consumer_id.to_owned());
        self.credentials.write().remove(&key)
    }

    /// Look up a consumer credential.
    pub fn get(&self, route_id: &str, consumer_id: &str) -> Option<ConsumerCredential> {
        let key = (route_id.to_owned(), consumer_id.to_owned());
        self.credentials.read().get(&key).cloned()
    }

    /// List all consumer credentials (snapshot).
    pub fn list(&self) -> Vec<ConsumerCredential> {
        self.credentials.read().values().cloned().collect()
    }

    /// List consumer credentials for a specific route.
    pub fn list_by_route(&self, route_id: &str) -> Vec<ConsumerCredential> {
        self.credentials
            .read()
            .values()
            .filter(|c| c.route_id == route_id)
            .cloned()
            .collect()
    }

    /// Number of stored credentials.
    pub fn count(&self) -> usize {
        self.credentials.read().len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_cred(route: &str, consumer: &str, header_val: &str) -> ConsumerCredential {
        ConsumerCredential {
            route_id: route.to_owned(),
            consumer_id: consumer.to_owned(),
            auth_type: ConsumerAuthType::ApiKey,
            header_name: "X-Api-Key".to_owned(),
            header_value: header_val.to_owned(),
        }
    }

    #[test]
    fn test_upsert_new() {
        let store = ConsumerCredentialStore::new();
        let prev = store.upsert(make_cred("r1", "c1", "key-1"));
        assert!(prev.is_none());
        assert_eq!(store.count(), 1);
    }

    #[test]
    fn test_upsert_existing() {
        let store = ConsumerCredentialStore::new();
        store.upsert(make_cred("r1", "c1", "key-1"));
        let prev = store.upsert(make_cred("r1", "c1", "key-2"));
        assert!(prev.is_some());
        assert_eq!(prev.expect("prev").header_value, "key-1");
        assert_eq!(store.count(), 1);
        let current = store.get("r1", "c1").expect("exists");
        assert_eq!(current.header_value, "key-2");
    }

    #[test]
    fn test_get_existing() {
        let store = ConsumerCredentialStore::new();
        store.upsert(make_cred("r1", "c1", "key-1"));
        let cred = store.get("r1", "c1");
        assert!(cred.is_some());
        assert_eq!(cred.expect("cred").header_value, "key-1");
    }

    #[test]
    fn test_get_nonexistent() {
        let store = ConsumerCredentialStore::new();
        assert!(store.get("r1", "c1").is_none());
    }

    #[test]
    fn test_different_consumers_same_route() {
        let store = ConsumerCredentialStore::new();
        store.upsert(make_cred("r1", "c1", "key-a"));
        store.upsert(make_cred("r1", "c2", "key-b"));
        assert_eq!(store.count(), 2);
        assert_eq!(store.get("r1", "c1").expect("c1").header_value, "key-a");
        assert_eq!(store.get("r1", "c2").expect("c2").header_value, "key-b");
    }

    #[test]
    fn test_remove() {
        let store = ConsumerCredentialStore::new();
        store.upsert(make_cred("r1", "c1", "key-1"));
        let removed = store.remove("r1", "c1");
        assert!(removed.is_some());
        assert_eq!(store.count(), 0);
        assert!(store.get("r1", "c1").is_none());
    }

    #[test]
    fn test_remove_nonexistent() {
        let store = ConsumerCredentialStore::new();
        assert!(store.remove("r1", "c1").is_none());
    }

    #[test]
    fn test_list() {
        let store = ConsumerCredentialStore::new();
        store.upsert(make_cred("r1", "c1", "key-1"));
        store.upsert(make_cred("r2", "c2", "key-2"));
        let all = store.list();
        assert_eq!(all.len(), 2);
    }

    #[test]
    fn test_list_by_route() {
        let store = ConsumerCredentialStore::new();
        store.upsert(make_cred("r1", "c1", "key-1"));
        store.upsert(make_cred("r1", "c2", "key-2"));
        store.upsert(make_cred("r2", "c3", "key-3"));
        let r1_creds = store.list_by_route("r1");
        assert_eq!(r1_creds.len(), 2);
        let r2_creds = store.list_by_route("r2");
        assert_eq!(r2_creds.len(), 1);
    }

    #[test]
    fn test_serde_roundtrip() {
        let cred = make_cred("r1", "c1", "key-1");
        let json = serde_json::to_string(&cred).expect("serialize");
        let back: ConsumerCredential = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(back.route_id, "r1");
        assert_eq!(back.consumer_id, "c1");
        assert_eq!(back.header_value, "key-1");
        assert_eq!(back.auth_type, ConsumerAuthType::ApiKey);
    }

    #[test]
    fn test_auth_type_deserialize_default() {
        let json =
            r#"{"route_id":"r1","consumer_id":"c1","header_name":"X-Key","header_value":"val"}"#;
        let cred: ConsumerCredential = serde_json::from_str(json).expect("deserialize");
        assert_eq!(cred.auth_type, ConsumerAuthType::ApiKey);
    }

    #[test]
    fn test_default_impl() {
        let store = ConsumerCredentialStore::default();
        assert_eq!(store.count(), 0);
    }
}
