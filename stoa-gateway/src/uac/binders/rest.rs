//! REST Protocol Binder
//!
//! Transforms a UAC contract into REST routes registered in the RouteRegistry.
//! Each endpoint in the contract becomes a proxied route with the path prefix
//! `/apis/{tenant_id}/{contract_name}{static_path}`, where `static_path` is
//! the endpoint path up to its first `{param}` segment.

use std::sync::Arc;

use crate::routes::{ApiRoute, PolicyEntry, PolicyRegistry, RouteRegistry};
use crate::uac::schema::{is_jwt_validation_policy, UacContractSpec};

use super::{split_path_template, BindingOutput, ProtocolBinder, CONTRACT_REJECTED};

/// REST protocol binder — generates proxy routes from UAC contracts.
pub struct RestBinder {
    route_registry: Arc<RouteRegistry>,
    policy_registry: Arc<PolicyRegistry>,
    /// When set, a contract with no inbound JWT is not published.
    /// Standalone turns this on (`STOA_CONTROL_PLANE_URL` unset). A control
    /// plane still allows an open route.
    require_inbound_auth: bool,
    /// `STOA_JWT_AUDIENCE`. A JWT route may omit `inboundAuthAudience` only
    /// when this list is non-empty. Both empty is refused in standalone.
    global_jwt_audience: Vec<String>,
}

impl RestBinder {
    /// Create a new REST binder backed by the given route registry.
    ///
    /// JWT policies are recorded on a private registry. Production uses
    /// [`Self::with_policies`] so the dynamic proxy can see them.
    pub fn new(route_registry: Arc<RouteRegistry>) -> Self {
        Self::with_policies(route_registry, Arc::new(PolicyRegistry::new()))
    }

    /// Bind routes and, when the contract asks for it, a `jwt_validation` policy.
    pub fn with_policies(
        route_registry: Arc<RouteRegistry>,
        policy_registry: Arc<PolicyRegistry>,
    ) -> Self {
        Self {
            route_registry,
            policy_registry,
            require_inbound_auth: false,
            global_jwt_audience: Vec::new(),
        }
    }

    /// Refuse to publish a route that has no inbound JWT policy.
    ///
    /// Used when the process is standalone. An update that drops inbound
    /// auth also removes any route already stored for that contract.
    pub fn enforcing_inbound_auth(mut self) -> Self {
        self.require_inbound_auth = true;
        self
    }

    /// Global audience from `STOA_JWT_AUDIENCE`. Copied from `Config` when the
    /// admin handler builds the standalone binder.
    pub fn with_global_audience(
        mut self,
        audiences: impl IntoIterator<Item = impl AsRef<str>>,
    ) -> Self {
        self.global_jwt_audience = audiences
            .into_iter()
            .map(|audience| audience.as_ref().trim().to_string())
            .filter(|audience| !audience.is_empty())
            .collect();
        self
    }

    /// Generate REST routes from a contract (pure function, no side effects).
    ///
    /// The route prefix is the static part of the endpoint path: up to the
    /// first `{param}` segment, trailing `/` included (`/customers/{id}` →
    /// `/apis/{tenant}/{contract}/customers/`). `backend_url` is the upstream
    /// URL of that static part; the proxy appends the rest of the request path.
    /// Endpoints with the same prefix and backend share one route, methods
    /// merged. Same prefix with another backend is an error.
    pub fn generate_routes(contract: &UacContractSpec) -> Result<Vec<ApiRoute>, String> {
        let contract_key = format!("{}:{}", contract.tenant_id, contract.name);
        let mut routes: Vec<ApiRoute> = Vec::new();
        // Index of the endpoint that created each route, for error messages.
        let mut first_endpoint: Vec<usize> = Vec::new();

        for (i, endpoint) in contract.endpoints.iter().enumerate() {
            let (static_path, _) = split_path_template(&endpoint.path);
            let path_prefix = format!(
                "/apis/{}/{}{}",
                contract.tenant_id, contract.name, static_path
            );

            if let Some(pos) = routes.iter().position(|r| r.path_prefix == path_prefix) {
                let route = &mut routes[pos];
                if !same_backend(&route.backend_url, &endpoint.backend_url) {
                    return Err(format!(
                        "{CONTRACT_REJECTED}endpoints[{}] ({}) and endpoints[{}] share the REST prefix {} with different backend_url ({} and {})",
                        first_endpoint[pos],
                        contract.endpoints[first_endpoint[pos]].path,
                        i,
                        path_prefix,
                        route.backend_url,
                        endpoint.backend_url
                    ));
                }
                for method in &endpoint.methods {
                    if !route.methods.contains(method) {
                        route.methods.push(method.clone());
                    }
                }
                continue;
            }

            // Route name: from operation_id or "{contract}-{index}"
            let name = endpoint
                .operation_id
                .clone()
                .unwrap_or_else(|| format!("{}-{}", contract.name, i));

            first_endpoint.push(i);
            routes.push(ApiRoute {
                // Deterministic: contract + index of the first endpoint.
                id: format!("uac:{}:{}", contract_key, i),
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
                upstream_http_version: Default::default(),
                upstreams: vec![],
                load_balancer: Default::default(),
                trusted_backend: true,
            });
        }

        Ok(routes)
    }

    fn upsert_jwt_policies(&self, contract: &UacContractSpec, routes: &[ApiRoute]) {
        let mut config = serde_json::json!({
            "source": "contract",
            "inbound_auth": contract.inbound_auth,
        });
        if let Some(audience) = contract_audience(contract) {
            config["audience"] = serde_json::Value::String(audience);
        }
        for route in routes {
            self.policy_registry.upsert(PolicyEntry {
                id: format!("jwt:{}", route.id),
                name: "jwt_validation".to_string(),
                policy_type: "jwt_validation".to_string(),
                config: config.clone(),
                priority: 0,
                api_id: route.id.clone(),
            });
        }
    }

    fn sync_jwt_policy(&self, contract: &UacContractSpec, routes: &[ApiRoute]) {
        let contract_key = format!("{}:{}", contract.tenant_id, contract.name);
        self.remove_contract_jwt_policies(&contract_key);
        if contract.requires_jwt_validation() {
            self.upsert_jwt_policies(contract, routes);
        }
    }
}

/// The proxy trims trailing `/` from the backend before joining, so
/// `http://b/customers/` and `http://b/customers` reach the same URLs.
fn same_backend(a: &str, b: &str) -> bool {
    a.trim_end_matches('/') == b.trim_end_matches('/')
}

fn contract_audience(contract: &UacContractSpec) -> Option<String> {
    if let Some(audience) = contract
        .inbound_auth_audience
        .as_ref()
        .map(|value| value.trim())
        .filter(|value| !value.is_empty())
    {
        return Some(audience.to_string());
    }
    contract.policies.iter().find_map(|policy| {
        if !is_jwt_validation_policy(&policy.policy_type) {
            return None;
        }
        policy
            .config
            .get("audience")
            .and_then(|value| value.as_str())
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(str::to_string)
    })
}

fn jwt_policy_prefix(contract_key: &str) -> String {
    format!("jwt:uac:{contract_key}:")
}

/// `jwt:uac:{contract_key}:{index}` with `{index}` made only of digits.
///
/// `starts_with` is not enough: contract `demo:a` would also match
/// `jwt:uac:demo:a:b:0`. The remainder after the key must be the endpoint index.
fn jwt_policy_belongs_to_contract(policy_id: &str, contract_key: &str) -> bool {
    let Some(rest) = policy_id.strip_prefix(&jwt_policy_prefix(contract_key)) else {
        return false;
    };
    !rest.is_empty() && rest.bytes().all(|byte| byte.is_ascii_digit())
}

impl RestBinder {
    fn remove_contract_jwt_policies(&self, contract_key: &str) {
        let stale: Vec<String> = self
            .policy_registry
            .list()
            .into_iter()
            .filter(|policy| jwt_policy_belongs_to_contract(&policy.id, contract_key))
            .map(|policy| policy.id)
            .collect();
        for id in stale {
            self.policy_registry.remove(&id);
        }
    }

    fn prune_stale_jwt_policies(&self, contract_key: &str, routes: &[ApiRoute]) {
        let live: std::collections::HashSet<&str> =
            routes.iter().map(|route| route.id.as_str()).collect();
        let stale: Vec<String> = self
            .policy_registry
            .list()
            .into_iter()
            .filter(|policy| {
                jwt_policy_belongs_to_contract(&policy.id, contract_key)
                    && !live.contains(policy.api_id.as_str())
            })
            .map(|policy| policy.id)
            .collect();
        for id in stale {
            self.policy_registry.remove(&id);
        }
    }
}

impl ProtocolBinder for RestBinder {
    async fn bind(&self, contract: &UacContractSpec) -> Result<BindingOutput, String> {
        let contract_key = format!("{}:{}", contract.tenant_id, contract.name);
        // Before any registry change: a rejected contract leaves the
        // previous routes and policies in place.
        let routes = Self::generate_routes(contract)?;
        let count = routes.len();

        if self.require_inbound_auth && !contract.requires_jwt_validation() {
            // Keep the route unpublished. Drop anything already stored so a
            // republish without inbound auth cannot leave the previous route open.
            self.route_registry.remove_by_contract(&contract_key);
            self.remove_contract_jwt_policies(&contract_key);
            return Err(
                "standalone mode refuses a route with no inbound auth; set inboundAuth to jwt"
                    .to_string(),
            );
        }

        if self.require_inbound_auth && contract.requires_jwt_validation() {
            let route_audience = contract
                .inbound_auth_audience
                .as_deref()
                .map(str::trim)
                .filter(|audience| !audience.is_empty());
            if route_audience.is_none() && self.global_jwt_audience.is_empty() {
                self.route_registry.remove_by_contract(&contract_key);
                self.remove_contract_jwt_policies(&contract_key);
                return Err(
                    "standalone mode refuses a JWT route with no audience; set STOA_JWT_AUDIENCE or inboundAuthAudience"
                        .to_string(),
                );
            }
        }

        if contract.requires_jwt_validation() {
            // Policy first. A concurrent request can see the new route only
            // after this returns, and the policy is already in the registry.
            // There is no second POST /admin/policies and no anonymous window.
            self.upsert_jwt_policies(contract, &routes);
            self.route_registry.remove_by_contract(&contract_key);
            for route in &routes {
                self.route_registry.upsert(route.clone());
            }
            self.prune_stale_jwt_policies(&contract_key, &routes);
        } else {
            // Drop the route before the policy so it cannot be served open.
            self.route_registry.remove_by_contract(&contract_key);
            self.sync_jwt_policy(contract, &routes);
            for route in &routes {
                self.route_registry.upsert(route.clone());
            }
        }

        tracing::info!(
            contract = %contract_key,
            routes = count,
            "REST binder: routes generated"
        );

        Ok(BindingOutput::Routes(routes))
    }

    async fn unbind(&self, contract_key: &str) -> Result<usize, String> {
        // Routes first, so unbind cannot leave a route with its policy already gone.
        let removed = self.route_registry.remove_by_contract(contract_key);
        self.remove_contract_jwt_policies(contract_key);

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
                method: None,
                description: None,
                operation_id: Some("list_payments".to_string()),
                input_schema: None,
                output_schema: None,
                llm: None,
            },
            UacEndpoint {
                path: "/payments/{id}".to_string(),
                methods: vec!["GET".to_string()],
                backend_url: "https://backend.acme.com/v1/payments".to_string(),
                method: None,
                description: None,
                operation_id: Some("get_payment".to_string()),
                input_schema: None,
                output_schema: None,
                llm: None,
            },
        ];
        spec
    }

    #[test]
    fn test_generate_routes_count() {
        let contract = sample_contract();
        let routes = RestBinder::generate_routes(&contract).expect("routes");
        assert_eq!(routes.len(), 2);
    }

    #[test]
    fn test_generate_routes_path_prefix() {
        let contract = sample_contract();
        let routes = RestBinder::generate_routes(&contract).expect("routes");
        assert_eq!(routes[0].path_prefix, "/apis/acme/payments/payments");
        assert_eq!(routes[1].path_prefix, "/apis/acme/payments/payments/");
    }

    fn customer_endpoint(path: &str, method: &str, backend_url: &str) -> UacEndpoint {
        UacEndpoint {
            path: path.to_string(),
            methods: vec![method.to_string()],
            backend_url: backend_url.to_string(),
            method: None,
            description: None,
            operation_id: None,
            input_schema: None,
            output_schema: None,
            llm: None,
        }
    }

    fn customer_contract(endpoints: Vec<UacEndpoint>) -> UacContractSpec {
        let mut spec = UacContractSpec::new("api", "demo");
        spec.status = ContractStatus::Published;
        spec.endpoints = endpoints;
        spec
    }

    #[test]
    fn route_prefix_stops_before_the_first_parameter_segment() {
        let cases = [
            ("/customers/{id}", "/apis/demo/api/customers/"),
            ("/customers/{id}/segment", "/apis/demo/api/customers/"),
            ("/{id}", "/apis/demo/api/"),
            ("/customers", "/apis/demo/api/customers"),
            ("/customers/", "/apis/demo/api/customers/"),
        ];
        for (path, expected) in cases {
            let contract =
                customer_contract(vec![customer_endpoint(path, "GET", "http://b/customers/")]);
            let routes = RestBinder::generate_routes(&contract).expect("routes");
            assert_eq!(routes.len(), 1, "{path}");
            assert_eq!(routes[0].path_prefix, expected, "{path}");
        }
    }

    #[test]
    fn endpoints_with_the_same_prefix_and_backend_share_one_route() {
        let contract = customer_contract(vec![
            customer_endpoint("/customers/{id}", "GET", "http://b/customers/"),
            customer_endpoint("/customers/{id}/segment", "GET", "http://b/customers/"),
            customer_endpoint("/customers/{id}", "DELETE", "http://b/customers"),
            customer_endpoint("/customers", "POST", "http://b/customers"),
        ]);
        let routes = RestBinder::generate_routes(&contract).expect("routes");
        assert_eq!(routes.len(), 2);
        assert_eq!(routes[0].id, "uac:demo:api:0");
        assert_eq!(routes[0].path_prefix, "/apis/demo/api/customers/");
        assert_eq!(routes[0].backend_url, "http://b/customers/");
        assert_eq!(routes[0].methods, vec!["GET", "DELETE"]);
        assert_eq!(routes[1].id, "uac:demo:api:3");
        assert_eq!(routes[1].path_prefix, "/apis/demo/api/customers");
        assert_eq!(routes[1].methods, vec!["POST"]);
    }

    #[test]
    fn same_prefix_with_another_backend_is_rejected() {
        let contract = customer_contract(vec![
            customer_endpoint("/customers/{id}", "GET", "http://b/customers/"),
            customer_endpoint("/customers/{id}/segment", "GET", "http://other/segments/"),
        ]);
        let error = RestBinder::generate_routes(&contract).expect_err("conflict");
        assert!(error.starts_with(CONTRACT_REJECTED), "{error}");
        assert!(error.contains("endpoints[0]"), "{error}");
        assert!(error.contains("endpoints[1]"), "{error}");
        assert!(error.contains("/apis/demo/api/customers/"), "{error}");
    }

    #[tokio::test]
    async fn rejected_republish_keeps_the_routes_already_published() {
        let registry = Arc::new(RouteRegistry::new());
        let binder = RestBinder::new(registry.clone());
        binder
            .bind(&customer_contract(vec![customer_endpoint(
                "/customers/{id}",
                "GET",
                "http://b/customers/",
            )]))
            .await
            .expect("first bind");

        let conflicting = customer_contract(vec![
            customer_endpoint("/customers/{id}", "GET", "http://b2/customers/"),
            customer_endpoint("/customers/{id}/x", "GET", "http://other/x/"),
        ]);
        binder.bind(&conflicting).await.expect_err("conflict");

        assert_eq!(registry.count(), 1);
        let route = registry.get("uac:demo:api:0").expect("route kept");
        assert_eq!(route.backend_url, "http://b/customers/");
    }

    #[tokio::test]
    async fn parameterised_path_reaches_the_backend_through_the_proxy() {
        use axum::body::Body;
        use axum::http::{Request, StatusCode};
        use tower::ServiceExt;
        use wiremock::matchers::{method, path};
        use wiremock::{Mock, MockServer, ResponseTemplate};

        use crate::config::Config;
        use crate::proxy::dynamic_proxy;
        use crate::state::AppState;

        let backend = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/customers/C-1001/segment"))
            .respond_with(ResponseTemplate::new(200).set_body_string("segment"))
            .mount(&backend)
            .await;

        let state = AppState::new(Config::default());
        let binder =
            RestBinder::with_policies(state.route_registry.clone(), state.policy_registry.clone());
        let base = format!("{}/customers/", backend.uri());
        binder
            .bind(&customer_contract(vec![
                customer_endpoint("/customers/{id}", "GET", &base),
                customer_endpoint("/customers/{id}/segment", "GET", &base),
            ]))
            .await
            .expect("bind");

        let response = axum::Router::new()
            .fallback(dynamic_proxy)
            .with_state(state)
            .oneshot(
                Request::builder()
                    .uri("/apis/demo/api/customers/C-1001/segment")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[test]
    fn test_generate_routes_id_format() {
        let contract = sample_contract();
        let routes = RestBinder::generate_routes(&contract).expect("routes");
        assert_eq!(routes[0].id, "uac:acme:payments:0");
        assert_eq!(routes[1].id, "uac:acme:payments:1");
    }

    #[test]
    fn test_generate_routes_name_from_operation_id() {
        let contract = sample_contract();
        let routes = RestBinder::generate_routes(&contract).expect("routes");
        assert_eq!(routes[0].name, "list_payments");
        assert_eq!(routes[1].name, "get_payment");
    }

    #[test]
    fn test_generate_routes_name_fallback() {
        let mut contract = sample_contract();
        contract.endpoints[0].operation_id = None;
        let routes = RestBinder::generate_routes(&contract).expect("routes");
        assert_eq!(routes[0].name, "payments-0");
    }

    #[test]
    fn test_generate_routes_classification_propagated() {
        let mut contract = sample_contract();
        contract.classification = Classification::Vvh;
        let routes = RestBinder::generate_routes(&contract).expect("routes");
        assert_eq!(routes[0].classification, Some(Classification::Vvh));
        assert_eq!(routes[1].classification, Some(Classification::Vvh));
    }

    #[test]
    fn test_generate_routes_contract_key() {
        let contract = sample_contract();
        let routes = RestBinder::generate_routes(&contract).expect("routes");
        assert_eq!(routes[0].contract_key.as_deref(), Some("acme:payments"));
    }

    #[test]
    fn test_generate_routes_methods_preserved() {
        let contract = sample_contract();
        let routes = RestBinder::generate_routes(&contract).expect("routes");
        assert_eq!(routes[0].methods, vec!["GET", "POST"]);
        assert_eq!(routes[1].methods, vec!["GET"]);
    }

    #[test]
    fn test_generate_routes_backend_url() {
        let contract = sample_contract();
        let routes = RestBinder::generate_routes(&contract).expect("routes");
        assert_eq!(
            routes[0].backend_url,
            "https://backend.acme.com/v1/payments"
        );
    }

    #[test]
    fn test_generate_routes_activated() {
        let contract = sample_contract();
        let routes = RestBinder::generate_routes(&contract).expect("routes");
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
            upstream_http_version: Default::default(),
            upstreams: vec![],
            load_balancer: Default::default(),
            trusted_backend: false,
        });

        let contract = sample_contract();
        binder.bind(&contract).await.expect("bind");
        assert_eq!(registry.count(), 3); // 1 manual + 2 contract

        binder.unbind("acme:payments").await.expect("unbind");
        assert_eq!(registry.count(), 1); // manual route survives
        assert!(registry.get("manual-1").is_some());
    }

    #[tokio::test]
    async fn inbound_auth_stores_jwt_validation_policy() {
        let routes = Arc::new(RouteRegistry::new());
        let policies = Arc::new(PolicyRegistry::new());
        let binder = RestBinder::with_policies(routes.clone(), policies.clone());

        let mut contract = sample_contract();
        contract.inbound_auth = Some("jwt".into());
        binder.bind(&contract).await.expect("bind");

        let stored = policies.list_for_api("uac:acme:payments:0");
        assert_eq!(stored.len(), 1);
        assert_eq!(stored[0].policy_type, "jwt_validation");
        assert!(routes.get("uac:acme:payments:0").is_some());

        binder.unbind("acme:payments").await.expect("unbind");
        assert!(policies.list_for_api("uac:acme:payments:0").is_empty());
    }

    #[tokio::test]
    async fn inbound_auth_audience_is_on_the_policy_in_the_same_bind() {
        let routes = Arc::new(RouteRegistry::new());
        let policies = Arc::new(PolicyRegistry::new());
        let binder = RestBinder::with_policies(routes.clone(), policies.clone());

        let mut contract = sample_contract();
        contract.inbound_auth = Some("jwt".into());
        contract.inbound_auth_audience = Some("demo-customer-referential".into());
        binder.bind(&contract).await.expect("bind");

        let stored = policies.list_for_api("uac:acme:payments:0");
        assert_eq!(
            stored[0].config["audience"].as_str(),
            Some("demo-customer-referential")
        );
        assert!(routes.get("uac:acme:payments:0").is_some());
        assert!(routes.get("uac:acme:payments:1").is_some());
        assert_eq!(policies.list_for_api("uac:acme:payments:1").len(), 1);
    }

    #[tokio::test]
    async fn contract_without_jwt_policy_stores_none() {
        let routes = Arc::new(RouteRegistry::new());
        let policies = Arc::new(PolicyRegistry::new());
        let binder = RestBinder::with_policies(routes.clone(), policies.clone());
        binder.bind(&sample_contract()).await.expect("bind");
        assert_eq!(policies.count(), 0);
        assert!(routes.get("uac:acme:payments:0").is_some());
    }

    #[tokio::test]
    async fn standalone_refuses_a_route_without_inbound_auth() {
        let routes = Arc::new(RouteRegistry::new());
        let policies = Arc::new(PolicyRegistry::new());
        let open = RestBinder::with_policies(routes.clone(), policies.clone());
        open.bind(&sample_contract()).await.expect("open bind");
        assert!(routes.get("uac:acme:payments:0").is_some());

        let standalone =
            RestBinder::with_policies(routes.clone(), policies.clone()).enforcing_inbound_auth();
        let error = standalone
            .bind(&sample_contract())
            .await
            .expect_err("open route");
        assert!(error.contains("no inbound auth"), "{error}");
        assert!(routes.get("uac:acme:payments:0").is_none());
        assert_eq!(policies.count(), 0);
    }

    #[tokio::test]
    async fn standalone_publishes_a_route_that_requires_jwt() {
        let routes = Arc::new(RouteRegistry::new());
        let policies = Arc::new(PolicyRegistry::new());
        let standalone =
            RestBinder::with_policies(routes.clone(), policies.clone()).enforcing_inbound_auth();
        let mut contract = sample_contract();
        contract.inbound_auth = Some("jwt".into());
        contract.inbound_auth_audience = Some("demo-customer-referential".into());
        standalone.bind(&contract).await.expect("jwt bind");
        assert!(routes.get("uac:acme:payments:0").is_some());
        assert_eq!(
            policies.list_for_api("uac:acme:payments:0")[0].config["audience"].as_str(),
            Some("demo-customer-referential")
        );
    }

    #[tokio::test]
    async fn standalone_refuses_jwt_route_when_global_and_route_audience_are_empty() {
        let routes = Arc::new(RouteRegistry::new());
        let policies = Arc::new(PolicyRegistry::new());
        let standalone =
            RestBinder::with_policies(routes.clone(), policies.clone()).enforcing_inbound_auth();
        let mut contract = sample_contract();
        contract.inbound_auth = Some("jwt".into());
        let error = standalone.bind(&contract).await.expect_err("no audience");
        assert!(error.contains("no audience"), "{error}");
        assert!(routes.get("uac:acme:payments:0").is_none());
    }

    #[tokio::test]
    async fn standalone_publishes_jwt_route_that_uses_the_global_audience() {
        let routes = Arc::new(RouteRegistry::new());
        let policies = Arc::new(PolicyRegistry::new());
        let standalone = RestBinder::with_policies(routes.clone(), policies.clone())
            .enforcing_inbound_auth()
            .with_global_audience(["stoa-gateway"]);
        let mut contract = sample_contract();
        contract.inbound_auth = Some("jwt".into());
        standalone.bind(&contract).await.expect("global audience");
        assert!(routes.get("uac:acme:payments:0").is_some());
        assert!(policies.list_for_api("uac:acme:payments:0")[0]
            .config
            .get("audience")
            .is_none());
    }

    fn ping_contract(tenant: &str, name: &str) -> UacContractSpec {
        let mut spec = UacContractSpec::new(name, tenant);
        spec.status = ContractStatus::Published;
        spec.inbound_auth = Some("jwt".into());
        spec.inbound_auth_audience = Some("stoa-gateway".into());
        spec.endpoints = vec![UacEndpoint {
            path: "/ping".to_string(),
            methods: vec!["GET".to_string()],
            backend_url: "http://127.0.0.1:9".to_string(),
            method: None,
            description: None,
            operation_id: Some(format!("{name}-ping")),
            input_schema: None,
            output_schema: None,
            llm: None,
        }];
        spec
    }

    #[test]
    fn jwt_policy_match_is_the_contract_key_not_a_prefix() {
        assert!(jwt_policy_belongs_to_contract("jwt:uac:demo:a:0", "demo:a"));
        assert!(!jwt_policy_belongs_to_contract(
            "jwt:uac:demo:a:b:0",
            "demo:a"
        ));
        assert!(jwt_policy_belongs_to_contract(
            "jwt:uac:demo:a:b:0",
            "demo:a:b"
        ));
    }

    #[tokio::test]
    async fn contract_name_prefix_does_not_purge_the_other_jwt_policy() {
        let routes = Arc::new(RouteRegistry::new());
        let policies = Arc::new(PolicyRegistry::new());
        let binder = RestBinder::with_policies(routes.clone(), policies.clone());
        binder
            .bind(&ping_contract("demo", "a:b"))
            .await
            .expect("long");
        binder
            .bind(&ping_contract("demo", "a"))
            .await
            .expect("short");
        binder
            .bind(&ping_contract("demo", "a"))
            .await
            .expect("republish short");

        assert_eq!(policies.list_for_api("uac:demo:a:b:0").len(), 1);
        assert_eq!(policies.list_for_api("uac:demo:a:0").len(), 1);
        assert!(routes.get("uac:demo:a:b:0").is_some());

        binder.unbind("demo:a").await.expect("unbind short");
        assert!(routes.get("uac:demo:a:0").is_none());
        assert!(policies.list_for_api("uac:demo:a:0").is_empty());
        assert!(routes.get("uac:demo:a:b:0").is_some());
        assert_eq!(policies.list_for_api("uac:demo:a:b:0").len(), 1);
    }

    #[tokio::test]
    async fn overlapped_contract_stays_401_without_a_token() {
        use axum::body::Body;
        use axum::http::{Request, StatusCode};
        use tower::ServiceExt;

        use crate::config::Config;
        use crate::proxy::dynamic_proxy;
        use crate::state::AppState;

        let state = AppState::new(Config::default());
        let binder =
            RestBinder::with_policies(state.route_registry.clone(), state.policy_registry.clone());
        binder
            .bind(&ping_contract("demo", "a:b"))
            .await
            .expect("long");
        binder
            .bind(&ping_contract("demo", "a"))
            .await
            .expect("short");
        binder
            .bind(&ping_contract("demo", "a"))
            .await
            .expect("republish short");

        let app = axum::Router::new()
            .fallback(dynamic_proxy)
            .with_state(state);
        let long = app
            .clone()
            .oneshot(
                Request::builder()
                    .uri("/apis/demo/a:b/ping")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(long.status(), StatusCode::UNAUTHORIZED);
        let short = app
            .oneshot(
                Request::builder()
                    .uri("/apis/demo/a/ping")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(short.status(), StatusCode::UNAUTHORIZED);
    }
}
