//! Contract registry and optional on-disk snapshot for pushed contracts.
//!
//! Contracts are registered via the admin API and used by protocol
//! binders to generate REST routes and MCP tools.

use parking_lot::RwLock;
use std::collections::HashMap;
use std::fs::{self, File, OpenOptions};
use std::io::{self, BufReader, Write};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use tokio::sync::RwLock as AsyncRwLock;

use super::schema::UacContractSpec;

struct RegisteredContract {
    bound: UacContractSpec,
    declarative: Option<UacContractSpec>,
    quotas: Option<Arc<HashMap<String, u32>>>,
}

/// Thread-safe registry of UAC contracts.
pub struct ContractRegistry {
    contracts: RwLock<HashMap<String, RegisteredContract>>,
    state_path: Option<PathBuf>,
    /// Writers hold this through binding and persistence. REST readers capture route policy under it.
    pub(crate) bindings: AsyncRwLock<()>,
}

impl Default for ContractRegistry {
    fn default() -> Self {
        Self::new()
    }
}

impl ContractRegistry {
    /// Create an empty contract registry.
    pub fn new() -> Self {
        Self::with_state_path(None)
    }

    pub(crate) fn with_state_path(state_path: Option<PathBuf>) -> Self {
        Self {
            contracts: RwLock::new(HashMap::new()),
            state_path,
            bindings: AsyncRwLock::new(()),
        }
    }

    /// Insert or update a contract by name. Returns the previous value if it existed.
    pub fn upsert(&self, contract: UacContractSpec) -> Option<UacContractSpec> {
        self.upsert_bound(contract, None)
    }

    pub(crate) fn upsert_bound(
        &self,
        bound: UacContractSpec,
        declarative: Option<UacContractSpec>,
    ) -> Option<UacContractSpec> {
        let quotas = bound
            .consumer_quotas()
            .unwrap_or_else(|_| Some(HashMap::new()))
            .map(Arc::new);
        self.contracts
            .write()
            .insert(
                bound.canonical_key(),
                RegisteredContract {
                    bound,
                    declarative,
                    quotas,
                },
            )
            .map(|entry| entry.bound)
    }

    /// Remove a contract by composite key (tenant_id:name). Returns the removed contract.
    pub fn remove(&self, key: &str) -> Option<UacContractSpec> {
        self.contracts.write().remove(key).map(|entry| entry.bound)
    }

    /// Get a contract by composite key (tenant_id:name).
    pub fn get(&self, key: &str) -> Option<UacContractSpec> {
        self.contracts
            .read()
            .get(key)
            .map(|entry| entry.bound.clone())
    }

    pub(crate) fn rest_audience(&self, key: &str) -> Option<String> {
        self.contracts
            .read()
            .get(key)?
            .bound
            .inbound_auth_audience
            .clone()
    }

    pub(crate) fn consumer_quotas(&self, key: &str) -> Option<Arc<HashMap<String, u32>>> {
        self.contracts.read().get(key)?.quotas.clone()
    }

    /// List all registered contracts.
    pub fn list(&self) -> Vec<UacContractSpec> {
        self.contracts
            .read()
            .values()
            .map(|entry| entry.bound.clone())
            .collect()
    }

    /// List contracts for a specific tenant.
    pub fn list_by_tenant(&self, tenant_id: &str) -> Vec<UacContractSpec> {
        self.contracts
            .read()
            .values()
            .map(|entry| &entry.bound)
            .filter(|c| c.tenant_id == tenant_id)
            .cloned()
            .collect()
    }

    /// Number of registered contracts.
    pub fn count(&self) -> usize {
        self.contracts.read().len()
    }

    pub(crate) async fn read_snapshot(&self) -> io::Result<Vec<UacContractSpec>> {
        let Some(path) = self.state_path.clone() else {
            return Ok(Vec::new());
        };
        tokio::task::spawn_blocking(move || {
            match fs::symlink_metadata(&path) {
                Ok(metadata) if metadata.is_file() => (),
                Ok(_) => {
                    return Err(io::Error::new(
                        io::ErrorKind::InvalidData,
                        "contract snapshot must be a regular file",
                    ))
                }
                Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(Vec::new()),
                Err(error) => return Err(error),
            }
            serde_json::from_reader(BufReader::new(File::open(path)?)).map_err(|error| {
                if let Some(kind) = error.io_error_kind() {
                    io::Error::new(kind, "could not read contract snapshot")
                } else {
                    io::Error::new(io::ErrorKind::InvalidData, "invalid contract snapshot JSON")
                }
            })
        })
        .await
        .map_err(io::Error::other)?
    }

    pub(crate) async fn persist_change(
        &self,
        key: &str,
        replacement: Option<UacContractSpec>,
    ) -> io::Result<()> {
        let Some(path) = self.state_path.clone() else {
            return Ok(());
        };
        let mut specs = self
            .contracts
            .read()
            .iter()
            .filter(|(entry_key, _)| entry_key.as_str() != key)
            .map(|(_, entry)| entry.declarative.as_ref().unwrap_or(&entry.bound).clone())
            .collect::<Vec<_>>();
        specs.extend(replacement);
        specs.sort_by_cached_key(UacContractSpec::canonical_key);
        tokio::task::spawn_blocking(move || write_snapshot(&path, &specs))
            .await
            .map_err(io::Error::other)?
    }
}

fn write_snapshot(path: &Path, specs: &[UacContractSpec]) -> io::Result<()> {
    let parent = path
        .parent()
        .filter(|dir| !dir.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    let temporary = parent.join(format!(".contracts-{}.tmp", uuid::Uuid::new_v4()));
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options.open(&temporary)?;
    let written = (|| {
        serde_json::to_writer(&mut file, specs)?;
        file.flush()?;
        file.sync_all()
    })();
    drop(file);

    if let Err(error) = written.and_then(|()| fs::rename(&temporary, path)) {
        let _ = fs::remove_file(&temporary);
        return Err(error);
    }

    // The rename commits the snapshot. Flush the directory entry where supported.
    #[cfg(unix)]
    if let Err(error) = File::open(parent).and_then(|dir| dir.sync_all()) {
        tracing::warn!(%error, "Could not flush the contract snapshot directory");
    }
    Ok(())
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
            method: None,
            description: None,
            operation_id: None,
            input_schema: None,
            output_schema: None,
            llm: None,
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
