//! REST Protocol Binder
//!
//! Transforms a UAC contract into REST routes registered in the RouteRegistry.
//! Each endpoint in the contract becomes a proxied route with the path pattern:
//! `/apis/{tenant_id}/{contract_name}{endpoint_path}`

use std::sync::Arc;

use crate::routes::{ApiRoute, RouteRegistry};
use crate::uac::schema::UacContractSpec;

use super::{BindingOutput, ProtocolBinder};

/// REST protocol binder — generates proxy routes from UAC contracts.
pub struct RestBinder {
    route_registry: Arc<RouteRegistry>,
}

impl RestBinder {
    /// Create a new REST binder backed by the given route registry.
    pub fn new(route_registry: Arc<RouteRegistry>) -> Self {
        Self { route_registry }
    }

    /// Generate REST routes from a contract (pure function, no side effects).
    pub fn generate_routes(contract: &UacContractSpec) -> Vec<ApiRoute> {
        let contract_key = format!("{}:{}", contract.tenant_id, contract.name);

        contract
            .endpoints
            .iter()
            .enumerate()
            .map(|(i, endpoint)| {
                // Route ID: deterministic, derived from contract + endpoint index
                let route_id = format!("uac:{}:{}", contract_key, i);

                // Path: /apis/{tenant}/{contract}{endpoint_path}
                let path_prefix = format!(
                    "/apis/{}/{}{}",
                    contract.tenant_id, contract.name, endpoint.path
                );

                // Route name: from operation_id or "{contract}-{index}"
                let name = endpoint
                    .operation_id
                    .clone()
                    .unwrap_or_else(|| format!("{}-{}", contract.name, i));

                ApiRoute {
                    id: route_id,
                    name,
                    tenant_id: contract.tenant_id.clone(),
                    path_prefix,
                    backend_url: endpoint.backend_url.clone(),
                    methods: endpoint.methods.clone(),
                    spec_hash: contract
                        .spec_hash
                        .clone()
                        .unwrap_or_else(|| contract.version.clone()),
                    activated: true,
                    classification: Some(contract.classification),
                    contract_key: Some(contract_key.clone()),
                }
            })
            .collect()
    }
}

impl ProtocolBinder for RestBinder {
    async fn bind(&self, contract: &UacContractSpec) -> Result<BindingOutput, String> {
        let contract_key = format!("{}:{}", contract.tenant_id, contract.name);

        // Remove existing routes for this contract (idempotent re-bind)
        self.route_registry.remove_by_contract(&contract_key);

        // Generate and register new routes
        let routes = Self::generate_routes(contract);
        let count = routes.len();

        for route in &routes {
            self.route_registry.upsert(route.clone());
        }

        tracing::info!(
            contract = %contract_key,
            routes = count,
            "REST binder: routes generated"
        );

        Ok(BindingOutput::Routes(routes))
    }

    async fn unbind(&self, contract_key: &str) -> Result<usize, String> {
        let removed = self.route_registry.remove_by_contract(contract_key);

        tracing::info!(
            contract = %contract_key,
            removed,
            "REST binder: routes removed"
        );

        Ok(removed)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::uac::classifications::Classification;
    use crate::uac::schema::{ContractStatus, UacContractSpec, UacEndpoint};

    fn sample_contract() -> UacContractSpec {
        let mut spec = UacContractSpec::new("payments", "acme");
        spec.status = ContractStatus::Published;
        spec.endpoints = vec![
            UacEndpoint {
                path: "/payments".to_string(),
                methods: vec!["GET".to_string(), "POST".to_string()],
                backend_url: "https://backend.acme.com/v1/payments".to_string(),
                operation_id: Some("list_payments".to_string()),
                input_schema: None,
                output_schema: None,
            },
            UacEndpoint {
                path: "/payments/{id}".to_string(),
                methods: vec!["GET".to_string()],
                backend_url: "https://backend.acme.com/v1/payments".to_string(),
                operation_id: Some("get_payment".to_string()),
                input_schema: None,
                output_schema: None,
            },
        ];
        spec
    }

    #[test]
    fn test_generate_routes_count() {
        let contract = sample_contract();
        let routes = RestBinder::generate_routes(&contract);
        assert_eq!(routes.len(), 2);
    }

    #[test]
    fn test_generate_routes_path_prefix() {
        let contract = sample_contract();
        let routes = RestBinder::generate_routes(&contract);
        assert_eq!(routes[0].path_prefix, "/apis/acme/payments/payments");
        assert_eq!(routes[1].path_prefix, "/apis/acme/payments/payments/{id}");
    }

    #[test]
    fn test_generate_routes_id_format() {
        let contract = sample_contract();
        let routes = RestBinder::generate_routes(&contract);
        assert_eq!(routes[0].id, "uac:acme:payments:0");
        assert_eq!(routes[1].id, "uac:acme:payments:1");
    }

    #[test]
    fn test_generate_routes_name_from_operation_id() {
        let contract = sample_contract();
        let routes = RestBinder::generate_routes(&contract);
        assert_eq!(routes[0].name, "list_payments");
        assert_eq!(routes[1].name, "get_payment");
    }

    #[test]
    fn test_generate_routes_name_fallback() {
        let mut contract = sample_contract();
        contract.endpoints[0].operation_id = None;
        let routes = RestBinder::generate_routes(&contract);
        assert_eq!(routes[0].name, "payments-0");
    }

    #[test]
    fn test_generate_routes_classification_propagated() {
        let mut contract = sample_contract();
        contract.classification = Classification::Vvh;
        let routes = RestBinder::generate_routes(&contract);
        assert_eq!(routes[0].classification, Some(Classification::Vvh));
        assert_eq!(routes[1].classification, Some(Classification::Vvh));
    }

    #[test]
    fn test_generate_routes_contract_key() {
        let contract = sample_contract();
        let routes = RestBinder::generate_routes(&contract);
        assert_eq!(routes[0].contract_key.as_deref(), Some("acme:payments"));
    }

    #[test]
    fn test_generate_routes_methods_preserved() {
        let contract = sample_contract();
        let routes = RestBinder::generate_routes(&contract);
        assert_eq!(routes[0].methods, vec!["GET", "POST"]);
        assert_eq!(routes[1].methods, vec!["GET"]);
    }

    #[test]
    fn test_generate_routes_backend_url() {
        let contract = sample_contract();
        let routes = RestBinder::generate_routes(&contract);
        assert_eq!(
            routes[0].backend_url,
            "https://backend.acme.com/v1/payments"
        );
    }

    #[test]
    fn test_generate_routes_activated() {
        let contract = sample_contract();
        let routes = RestBinder::generate_routes(&contract);
        assert!(routes[0].activated);
    }

    #[tokio::test]
    async fn test_bind_registers_routes() {
        let registry = Arc::new(RouteRegistry::new());
        let binder = RestBinder::new(registry.clone());

        let contract = sample_contract();
        let result = binder.bind(&contract).await;
        assert!(result.is_ok());

        // Routes should be in the registry
        assert_eq!(registry.count(), 2);
        assert!(registry.get("uac:acme:payments:0").is_some());
        assert!(registry.get("uac:acme:payments:1").is_some());
    }

    #[tokio::test]
    async fn test_bind_replaces_existing_routes() {
        let registry = Arc::new(RouteRegistry::new());
        let binder = RestBinder::new(registry.clone());

        let contract = sample_contract();
        binder.bind(&contract).await.expect("first bind");
        assert_eq!(registry.count(), 2);

        // Re-bind with updated contract (fewer endpoints)
        let mut updated = sample_contract();
        updated.endpoints.pop();
        binder.bind(&updated).await.expect("second bind");
        assert_eq!(registry.count(), 1);
    }

    #[tokio::test]
    async fn test_unbind_removes_routes() {
        let registry = Arc::new(RouteRegistry::new());
        let binder = RestBinder::new(registry.clone());

        let contract = sample_contract();
        binder.bind(&contract).await.expect("bind");
        assert_eq!(registry.count(), 2);

        let removed = binder.unbind("acme:payments").await.expect("unbind");
        assert_eq!(removed, 2);
        assert_eq!(registry.count(), 0);
    }

    #[tokio::test]
    async fn test_unbind_nonexistent_returns_zero() {
        let registry = Arc::new(RouteRegistry::new());
        let binder = RestBinder::new(registry.clone());

        let removed = binder.unbind("unknown:contract").await.expect("unbind");
        assert_eq!(removed, 0);
    }

    #[tokio::test]
    async fn test_bind_does_not_affect_non_contract_routes() {
        let registry = Arc::new(RouteRegistry::new());
        let binder = RestBinder::new(registry.clone());

        // Add a manually registered route (no contract_key)
        registry.upsert(ApiRoute {
            id: "manual-1".to_string(),
            name: "manual".to_string(),
            tenant_id: "acme".to_string(),
            path_prefix: "/manual".to_string(),
            backend_url: "https://manual.test".to_string(),
            methods: vec!["GET".to_string()],
            spec_hash: "hash".to_string(),
            activated: true,
            classification: None,
            contract_key: None,
        });

        let contract = sample_contract();
        binder.bind(&contract).await.expect("bind");
        assert_eq!(registry.count(), 3); // 1 manual + 2 contract

        binder.unbind("acme:payments").await.expect("unbind");
        assert_eq!(registry.count(), 1); // manual route survives
        assert!(registry.get("manual-1").is_some());
    }
}
