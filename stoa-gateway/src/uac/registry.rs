//! In-memory contract registry for UAC contracts.
//!
//! Contracts are registered via the admin API and used by protocol
//! binders to generate REST routes and MCP tools.

use parking_lot::RwLock;
use std::collections::HashMap;

use super::schema::UacContractSpec;

/// Thread-safe in-memory registry of UAC contracts.
pub struct ContractRegistry {
    contracts: RwLock<HashMap<String, UacContractSpec>>,
}

impl Default for ContractRegistry {
    fn default() -> Self {
        Self::new()
    }
}

impl ContractRegistry {
    /// Create an empty contract registry.
    pub fn new() -> Self {
        Self {
            contracts: RwLock::new(HashMap::new()),
        }
    }

    /// Insert or update a contract by name. Returns the previous value if it existed.
    pub fn upsert(&self, contract: UacContractSpec) -> Option<UacContractSpec> {
        let key = format!("{}:{}", contract.tenant_id, contract.name);
        self.contracts.write().insert(key, contract)
    }

    /// Remove a contract by composite key (tenant_id:name). Returns the removed contract.
    pub fn remove(&self, key: &str) -> Option<UacContractSpec> {
        self.contracts.write().remove(key)
    }

    /// Get a contract by composite key (tenant_id:name).
    pub fn get(&self, key: &str) -> Option<UacContractSpec> {
        self.contracts.read().get(key).cloned()
    }

    /// List all registered contracts.
    pub fn list(&self) -> Vec<UacContractSpec> {
        self.contracts.read().values().cloned().collect()
    }

    /// List contracts for a specific tenant.
    pub fn list_by_tenant(&self, tenant_id: &str) -> Vec<UacContractSpec> {
        self.contracts
            .read()
            .values()
            .filter(|c| c.tenant_id == tenant_id)
            .cloned()
            .collect()
    }

    /// Number of registered contracts.
    pub fn count(&self) -> usize {
        self.contracts.read().len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::uac::schema::UacEndpoint;
    use crate::uac::Classification;

    fn make_contract(name: &str, tenant: &str) -> UacContractSpec {
        let mut spec = UacContractSpec::new(name, tenant);
        spec.endpoints = vec![UacEndpoint {
            path: "/test".to_string(),
            methods: vec!["GET".to_string()],
            backend_url: "https://backend.test".to_string(),
            operation_id: None,
            input_schema: None,
            output_schema: None,
        }];
        spec
    }

    #[test]
    fn test_upsert_new() {
        let reg = ContractRegistry::new();
        let prev = reg.upsert(make_contract("payments", "acme"));
        assert!(prev.is_none());
        assert_eq!(reg.count(), 1);
    }

    #[test]
    fn test_upsert_existing() {
        let reg = ContractRegistry::new();
        reg.upsert(make_contract("payments", "acme"));
        let mut updated = make_contract("payments", "acme");
        updated.version = "2.0.0".to_string();
        let prev = reg.upsert(updated);
        assert!(prev.is_some());
        assert_eq!(prev.expect("prev").version, "1.0.0");
        assert_eq!(reg.count(), 1);
    }

    #[test]
    fn test_remove() {
        let reg = ContractRegistry::new();
        reg.upsert(make_contract("payments", "acme"));
        let removed = reg.remove("acme:payments");
        assert!(removed.is_some());
        assert_eq!(reg.count(), 0);
    }

    #[test]
    fn test_remove_nonexistent() {
        let reg = ContractRegistry::new();
        let removed = reg.remove("unknown:key");
        assert!(removed.is_none());
    }

    #[test]
    fn test_get() {
        let reg = ContractRegistry::new();
        reg.upsert(make_contract("payments", "acme"));
        let found = reg.get("acme:payments");
        assert!(found.is_some());
        assert_eq!(found.expect("found").name, "payments");
    }

    #[test]
    fn test_get_nonexistent() {
        let reg = ContractRegistry::new();
        let found = reg.get("nope:nada");
        assert!(found.is_none());
    }

    #[test]
    fn test_list() {
        let reg = ContractRegistry::new();
        reg.upsert(make_contract("api-a", "acme"));
        reg.upsert(make_contract("api-b", "acme"));
        reg.upsert(make_contract("api-c", "globex"));
        assert_eq!(reg.list().len(), 3);
    }

    #[test]
    fn test_list_by_tenant() {
        let reg = ContractRegistry::new();
        reg.upsert(make_contract("api-a", "acme"));
        reg.upsert(make_contract("api-b", "acme"));
        reg.upsert(make_contract("api-c", "globex"));

        let acme = reg.list_by_tenant("acme");
        assert_eq!(acme.len(), 2);

        let globex = reg.list_by_tenant("globex");
        assert_eq!(globex.len(), 1);

        let empty = reg.list_by_tenant("unknown");
        assert!(empty.is_empty());
    }

    #[test]
    fn test_classification_preserved() {
        let reg = ContractRegistry::new();
        let mut contract = make_contract("critical", "acme");
        contract.classification = Classification::Vvh;
        contract.refresh_policies();
        reg.upsert(contract);

        let found = reg.get("acme:critical").expect("found");
        assert_eq!(found.classification, Classification::Vvh);
        assert!(found.required_policies.contains(&"mtls".to_string()));
    }
}
