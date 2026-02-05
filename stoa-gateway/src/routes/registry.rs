//! In-memory route registry for dynamically managed API routes.
//!
//! Routes are registered by the Control Plane via the admin API
//! and used by the dynamic proxy to route incoming requests.

use parking_lot::RwLock;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// An API route managed by the Control Plane.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApiRoute {
    /// Control Plane assigned UUID
    pub id: String,
    /// Human-readable API name
    pub name: String,
    /// Tenant that owns this API
    pub tenant_id: String,
    /// URL path prefix (e.g. "/apis/acme/payments")
    pub path_prefix: String,
    /// Backend URL to proxy to (e.g. "https://backend.acme.com/v1")
    pub backend_url: String,
    /// Allowed HTTP methods (empty = all methods)
    pub methods: Vec<String>,
    /// Spec hash for drift detection
    pub spec_hash: String,
    /// Whether the route is active
    pub activated: bool,
}

/// Thread-safe in-memory registry of API routes.
pub struct RouteRegistry {
    routes: RwLock<HashMap<String, ApiRoute>>,
}

impl RouteRegistry {
    /// Create an empty registry.
    pub fn new() -> Self {
        Self {
            routes: RwLock::new(HashMap::new()),
        }
    }

    /// Insert or update a route. Returns the previous value if it existed.
    pub fn upsert(&self, route: ApiRoute) -> Option<ApiRoute> {
        self.routes.write().insert(route.id.clone(), route)
    }

    /// Remove a route by ID. Returns the removed route if it existed.
    pub fn remove(&self, id: &str) -> Option<ApiRoute> {
        self.routes.write().remove(id)
    }

    /// Get a route by ID.
    pub fn get(&self, id: &str) -> Option<ApiRoute> {
        self.routes.read().get(id).cloned()
    }

    /// List all registered routes.
    pub fn list(&self) -> Vec<ApiRoute> {
        self.routes.read().values().cloned().collect()
    }

    /// Number of registered routes.
    pub fn count(&self) -> usize {
        self.routes.read().len()
    }

    /// Find the best matching route for a request path.
    ///
    /// Uses longest-prefix matching: if multiple routes match,
    /// the one with the longest `path_prefix` wins.
    pub fn find_by_path(&self, path: &str) -> Option<ApiRoute> {
        let routes = self.routes.read();
        let mut best: Option<&ApiRoute> = None;
        let mut best_len = 0;

        for route in routes.values() {
            if path.starts_with(&route.path_prefix) && route.path_prefix.len() > best_len {
                best = Some(route);
                best_len = route.path_prefix.len();
            }
        }

        best.cloned()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_route(id: &str, prefix: &str) -> ApiRoute {
        ApiRoute {
            id: id.to_string(),
            name: format!("test-{}", id),
            tenant_id: "acme".to_string(),
            path_prefix: prefix.to_string(),
            backend_url: "https://backend.test".to_string(),
            methods: vec!["GET".to_string(), "POST".to_string()],
            spec_hash: "abc123".to_string(),
            activated: true,
        }
    }

    #[test]
    fn test_upsert_new_route() {
        let reg = RouteRegistry::new();
        let prev = reg.upsert(make_route("r1", "/apis/acme/payments"));
        assert!(prev.is_none());
        assert_eq!(reg.count(), 1);
    }

    #[test]
    fn test_upsert_existing_route() {
        let reg = RouteRegistry::new();
        reg.upsert(make_route("r1", "/apis/acme/payments"));
        let prev = reg.upsert(make_route("r1", "/apis/acme/payments-v2"));
        assert!(prev.is_some());
        assert_eq!(prev.unwrap().path_prefix, "/apis/acme/payments");
        assert_eq!(reg.count(), 1);
    }

    #[test]
    fn test_remove_route() {
        let reg = RouteRegistry::new();
        reg.upsert(make_route("r1", "/apis/acme/payments"));
        let removed = reg.remove("r1");
        assert!(removed.is_some());
        assert_eq!(reg.count(), 0);
    }

    #[test]
    fn test_remove_nonexistent() {
        let reg = RouteRegistry::new();
        let removed = reg.remove("unknown");
        assert!(removed.is_none());
    }

    #[test]
    fn test_find_by_path_exact() {
        let reg = RouteRegistry::new();
        reg.upsert(make_route("r1", "/apis/acme/payments"));
        let found = reg.find_by_path("/apis/acme/payments");
        assert!(found.is_some());
        assert_eq!(found.unwrap().id, "r1");
    }

    #[test]
    fn test_find_by_path_subpath() {
        let reg = RouteRegistry::new();
        reg.upsert(make_route("r1", "/apis/acme/payments"));
        let found = reg.find_by_path("/apis/acme/payments/123/refund");
        assert!(found.is_some());
        assert_eq!(found.unwrap().id, "r1");
    }

    #[test]
    fn test_find_by_path_longest_prefix() {
        let reg = RouteRegistry::new();
        reg.upsert(make_route("r1", "/apis"));
        reg.upsert(make_route("r2", "/apis/acme"));
        let found = reg.find_by_path("/apis/acme/payments");
        assert!(found.is_some());
        assert_eq!(found.unwrap().id, "r2");
    }

    #[test]
    fn test_find_by_path_no_match() {
        let reg = RouteRegistry::new();
        reg.upsert(make_route("r1", "/apis/acme/payments"));
        let found = reg.find_by_path("/other/path");
        assert!(found.is_none());
    }

    #[test]
    fn test_list_routes() {
        let reg = RouteRegistry::new();
        reg.upsert(make_route("r1", "/apis/a"));
        reg.upsert(make_route("r2", "/apis/b"));
        reg.upsert(make_route("r3", "/apis/c"));
        let all = reg.list();
        assert_eq!(all.len(), 3);
    }
}
