//! In-memory route registry for dynamically managed API routes.
//!
//! Routes are registered by the Control Plane via the admin API
//! and used by the dynamic proxy to route incoming requests.
//!
//! Uses `arc_swap::ArcSwap` for lock-free reads on the hot path.
//! Writes clone-and-swap the table — acceptable since route mutations
//! are rare (admin API or periodic reload) while reads happen per-request.

use arc_swap::ArcSwap;
use parking_lot::Mutex;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;

use crate::lb::{LbStrategy, Upstream};
use crate::uac::Classification;

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
    /// UAC classification (if generated from a contract)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub classification: Option<Classification>,
    /// UAC contract key (tenant_id:name) that generated this route
    #[serde(skip_serializing_if = "Option::is_none")]
    pub contract_key: Option<String>,
    /// Multiple upstreams for load balancing (overrides backend_url when non-empty)
    #[serde(default)]
    pub upstreams: Vec<Upstream>,
    /// Load balancing strategy (default: round_robin)
    #[serde(default)]
    pub load_balancer: LbStrategy,
}

/// Snapshot of the full route table (immutable once created).
pub type RouteTable = HashMap<String, Arc<ApiRoute>>;

/// Thread-safe in-memory registry of API routes.
///
/// Uses `ArcSwap<RouteTable>` for lock-free reads on the hot path (CAB-1828).
/// Writes use a `Mutex` to serialize clone-and-swap operations.
///
/// Routes are stored as `Arc<ApiRoute>` to avoid cloning 7+ String fields
/// on every lookup. `find_by_path()` returns `Arc<ApiRoute>` — one atomic
/// increment vs deep clone. (CAB-1332 optimization)
pub struct RouteRegistry {
    /// Lock-free readable route table.
    routes: ArcSwap<RouteTable>,
    /// Serializes write operations (clone-and-swap).
    write_lock: Mutex<()>,
}

impl Default for RouteRegistry {
    fn default() -> Self {
        Self::new()
    }
}

impl RouteRegistry {
    /// Create an empty registry.
    pub fn new() -> Self {
        Self {
            routes: ArcSwap::from_pointee(HashMap::new()),
            write_lock: Mutex::new(()),
        }
    }

    /// Insert or update a route. Returns the previous value if it existed.
    pub fn upsert(&self, route: ApiRoute) -> Option<Arc<ApiRoute>> {
        let _guard = self.write_lock.lock();
        let old = self.routes.load();
        let mut new_table = (**old).clone();
        let prev = new_table.insert(route.id.clone(), Arc::new(route));
        self.routes.store(Arc::new(new_table));
        prev
    }

    /// Remove a route by ID. Returns the removed route if it existed.
    pub fn remove(&self, id: &str) -> Option<Arc<ApiRoute>> {
        let _guard = self.write_lock.lock();
        let old = self.routes.load();
        let mut new_table = (**old).clone();
        let prev = new_table.remove(id);
        self.routes.store(Arc::new(new_table));
        prev
    }

    /// Get a route by ID.
    pub fn get(&self, id: &str) -> Option<Arc<ApiRoute>> {
        self.routes.load().get(id).map(Arc::clone)
    }

    /// List all registered routes.
    pub fn list(&self) -> Vec<Arc<ApiRoute>> {
        self.routes.load().values().map(Arc::clone).collect()
    }

    /// Number of registered routes.
    pub fn count(&self) -> usize {
        self.routes.load().len()
    }

    /// Remove all routes generated from a specific contract key.
    /// Returns the number of routes removed.
    pub fn remove_by_contract(&self, contract_key: &str) -> usize {
        let _guard = self.write_lock.lock();
        let old = self.routes.load();
        let mut new_table = (**old).clone();
        let before = new_table.len();
        new_table.retain(|_, r| r.contract_key.as_deref() != Some(contract_key));
        let removed = before - new_table.len();
        self.routes.store(Arc::new(new_table));
        removed
    }

    /// Atomically swap the entire route table with a new snapshot (CAB-1828).
    ///
    /// Used by hot-reload (SIGHUP, admin endpoint, watch loop) to replace
    /// all routes in a single lock-free pointer swap. Readers on the hot path
    /// never block — they see either the old or the new table, never a partial state.
    ///
    /// Returns the number of routes in the new table.
    pub fn swap_all(&self, routes: Vec<ApiRoute>) -> usize {
        let new_table: RouteTable = routes
            .into_iter()
            .map(|r| (r.id.clone(), Arc::new(r)))
            .collect();
        let count = new_table.len();
        self.routes.store(Arc::new(new_table));
        count
    }

    /// Find the best matching route for a request path.
    ///
    /// Uses longest-prefix matching: if multiple routes match,
    /// the one with the longest `path_prefix` wins.
    ///
    /// Returns `Arc<ApiRoute>` — one atomic increment instead of cloning
    /// 7+ String fields per request. (CAB-1332)
    pub fn find_by_path(&self, path: &str) -> Option<Arc<ApiRoute>> {
        let table = self.routes.load();
        let mut best: Option<&Arc<ApiRoute>> = None;
        let mut best_len = 0;

        for route in table.values() {
            if path.starts_with(&route.path_prefix) && route.path_prefix.len() > best_len {
                best = Some(route);
                best_len = route.path_prefix.len();
            }
        }

        best.map(Arc::clone)
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
            classification: None,
            contract_key: None,
            upstreams: vec![],
            load_balancer: LbStrategy::default(),
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
    fn test_find_by_path_returns_arc() {
        let reg = RouteRegistry::new();
        reg.upsert(make_route("r1", "/apis/acme/payments"));
        let a = reg.find_by_path("/apis/acme/payments").unwrap();
        let b = reg.find_by_path("/apis/acme/payments").unwrap();
        // Both Arc refs point to the same allocation
        assert!(Arc::ptr_eq(&a, &b));
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

    #[test]
    fn test_swap_all_replaces_entire_table() {
        let reg = RouteRegistry::new();
        reg.upsert(make_route("r1", "/apis/old"));
        reg.upsert(make_route("r2", "/apis/old2"));
        assert_eq!(reg.count(), 2);

        let new_routes = vec![
            make_route("r3", "/apis/new1"),
            make_route("r4", "/apis/new2"),
            make_route("r5", "/apis/new3"),
        ];
        let count = reg.swap_all(new_routes);
        assert_eq!(count, 3);
        assert_eq!(reg.count(), 3);
        // Old routes are gone
        assert!(reg.get("r1").is_none());
        assert!(reg.get("r2").is_none());
        // New routes are present
        assert!(reg.get("r3").is_some());
        assert!(reg.get("r4").is_some());
        assert!(reg.get("r5").is_some());
    }

    #[test]
    fn test_swap_all_empty_clears_table() {
        let reg = RouteRegistry::new();
        reg.upsert(make_route("r1", "/apis/a"));
        assert_eq!(reg.count(), 1);

        let count = reg.swap_all(vec![]);
        assert_eq!(count, 0);
        assert_eq!(reg.count(), 0);
    }

    #[test]
    fn test_swap_all_deduplicates_by_id() {
        let reg = RouteRegistry::new();
        let routes = vec![
            make_route("r1", "/apis/a"),
            make_route("r1", "/apis/b"), // same ID, different prefix
        ];
        let count = reg.swap_all(routes);
        // HashMap deduplicates by key — last write wins
        assert_eq!(count, 1);
        assert_eq!(reg.get("r1").unwrap().path_prefix, "/apis/b");
    }
}
