//! Integration tests for UAC contract admin endpoints + REST/MCP binders.

use axum::http::StatusCode;
use tower::ServiceExt;

use crate::handlers::admin::test_helpers::{
    auth_json_req, auth_req, build_full_admin_router, create_test_state,
};

fn sample_contract_json() -> serde_json::Value {
    serde_json::json!({
        "name": "payment-api",
        "version": "1.0.0",
        "tenant_id": "acme",
        "classification": "H",
        "endpoints": [{
            "path": "/payments/{id}",
            "methods": ["GET", "POST"],
            "backend_url": "https://backend.acme.com/v1/payments"
        }],
        "status": "draft"
    })
}

#[tokio::test]
async fn test_contract_upsert_create() {
    let state = create_test_state(Some("secret"));
    let app = build_full_admin_router(state);

    let response = app
        .oneshot(auth_json_req("POST", "/contracts", sample_contract_json()))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::CREATED);
    let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
        .await
        .unwrap();
    let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(data["key"], "acme:payment-api");
    assert_eq!(data["status"], "ok");
}

#[tokio::test]
async fn test_contract_upsert_update() {
    let state = create_test_state(Some("secret"));
    let app = build_full_admin_router(state);

    // Create
    let _ = app
        .clone()
        .oneshot(auth_json_req("POST", "/contracts", sample_contract_json()))
        .await
        .unwrap();

    // Update (same name+tenant = update)
    let response = app
        .oneshot(auth_json_req("POST", "/contracts", sample_contract_json()))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
}

#[tokio::test]
async fn test_contract_list_empty() {
    let state = create_test_state(Some("secret"));
    let app = build_full_admin_router(state);

    let response = app.oneshot(auth_req("GET", "/contracts")).await.unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
        .await
        .unwrap();
    let data: Vec<serde_json::Value> = serde_json::from_slice(&body).unwrap();
    assert!(data.is_empty());
}

#[tokio::test]
async fn test_contract_get_by_key() {
    let state = create_test_state(Some("secret"));
    let app = build_full_admin_router(state);

    // Create
    let _ = app
        .clone()
        .oneshot(auth_json_req("POST", "/contracts", sample_contract_json()))
        .await
        .unwrap();

    // Get by key
    let response = app
        .oneshot(auth_req("GET", "/contracts/acme:payment-api"))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
        .await
        .unwrap();
    let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(data["name"], "payment-api");
    assert_eq!(data["tenant_id"], "acme");
    assert_eq!(data["classification"], "H");
}

#[tokio::test]
async fn test_contract_get_not_found() {
    let state = create_test_state(Some("secret"));
    let app = build_full_admin_router(state);

    let response = app
        .oneshot(auth_req("GET", "/contracts/nope:nada"))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn test_contract_delete() {
    let state = create_test_state(Some("secret"));
    let app = build_full_admin_router(state);

    // Create
    let _ = app
        .clone()
        .oneshot(auth_json_req("POST", "/contracts", sample_contract_json()))
        .await
        .unwrap();

    // Delete
    let response = app
        .clone()
        .oneshot(auth_req("DELETE", "/contracts/acme:payment-api"))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
        .await
        .unwrap();
    let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(data["status"], "deleted");

    // Verify gone
    let response = app
        .oneshot(auth_req("GET", "/contracts/acme:payment-api"))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn test_contract_delete_not_found() {
    let state = create_test_state(Some("secret"));
    let app = build_full_admin_router(state);

    let response = app
        .oneshot(auth_req("DELETE", "/contracts/unknown:key"))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn test_contract_validation_error() {
    let state = create_test_state(Some("secret"));
    let app = build_full_admin_router(state);

    // Contract with empty name
    let invalid = serde_json::json!({
        "name": "",
        "version": "1.0.0",
        "tenant_id": "acme",
        "classification": "H",
        "endpoints": [],
        "status": "draft"
    });

    let response = app
        .oneshot(auth_json_req("POST", "/contracts", invalid))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
        .await
        .unwrap();
    let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(data["status"], "error");
    assert!(data["errors"].is_array());
}

#[tokio::test]
async fn test_contract_policies_auto_refreshed() {
    let state = create_test_state(Some("secret"));
    let app = build_full_admin_router(state);

    let vvh_contract = serde_json::json!({
        "name": "critical-api",
        "version": "1.0.0",
        "tenant_id": "acme",
        "classification": "VVH",
        "endpoints": [{
            "path": "/critical",
            "methods": ["POST"],
            "backend_url": "https://backend.acme.com/critical"
        }],
        "status": "draft"
    });

    let _ = app
        .clone()
        .oneshot(auth_json_req("POST", "/contracts", vvh_contract))
        .await
        .unwrap();

    let response = app
        .oneshot(auth_req("GET", "/contracts/acme:critical-api"))
        .await
        .unwrap();

    let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
        .await
        .unwrap();
    let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
    let policies = data["required_policies"].as_array().unwrap();
    assert!(policies.contains(&serde_json::json!("mtls")));
    assert!(policies.contains(&serde_json::json!("audit-logging")));
}

// =============================================================================
// REST Binder integration tests (CAB-1299 PR3)
// =============================================================================

#[tokio::test]
async fn test_contract_upsert_generates_routes() {
    let state = create_test_state(Some("secret"));
    let app = build_full_admin_router(state.clone());

    let response = app
        .oneshot(auth_json_req("POST", "/contracts", sample_contract_json()))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::CREATED);
    let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
        .await
        .unwrap();
    let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(data["routes_generated"], 1); // 1 endpoint in sample_contract_json
    assert_eq!(data["tools_generated"], 1);

    // Verify route is in the route registry
    assert_eq!(state.route_registry.count(), 1);
    let route = state.route_registry.get("uac:acme:payment-api:0");
    assert!(route.is_some());
    let route = route.unwrap();
    assert_eq!(route.path_prefix, "/apis/acme/payment-api/payments/{id}");
    assert_eq!(route.contract_key.as_deref(), Some("acme:payment-api"));

    // Verify MCP tool is in the tool registry (no operation_id → fallback name)
    assert_eq!(state.tool_registry.count(), 1);
    assert!(state
        .tool_registry
        .exists("uac:acme:payment-api:payment-api-0"));
}

#[tokio::test]
async fn test_contract_delete_cascades_routes() {
    let state = create_test_state(Some("secret"));
    let app = build_full_admin_router(state.clone());

    // Create contract → generates route
    let _ = app
        .clone()
        .oneshot(auth_json_req("POST", "/contracts", sample_contract_json()))
        .await
        .unwrap();
    assert_eq!(state.route_registry.count(), 1);

    // Delete contract → cascades route removal
    let response = app
        .oneshot(auth_req("DELETE", "/contracts/acme:payment-api"))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
        .await
        .unwrap();
    let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(data["routes_removed"], 1);
    assert_eq!(data["tools_removed"], 1);
    assert_eq!(state.route_registry.count(), 0);
    assert_eq!(state.tool_registry.count(), 0);
}

#[tokio::test]
async fn test_contract_re_upsert_replaces_routes() {
    let state = create_test_state(Some("secret"));
    let app = build_full_admin_router(state.clone());

    // Create with 1 endpoint
    let _ = app
        .clone()
        .oneshot(auth_json_req("POST", "/contracts", sample_contract_json()))
        .await
        .unwrap();
    assert_eq!(state.route_registry.count(), 1);

    // Re-upsert with 2 endpoints
    let two_endpoints = serde_json::json!({
        "name": "payment-api",
        "version": "2.0.0",
        "tenant_id": "acme",
        "classification": "H",
        "endpoints": [
            {
                "path": "/payments",
                "methods": ["GET", "POST"],
                "backend_url": "https://backend.acme.com/v2/payments"
            },
            {
                "path": "/payments/{id}",
                "methods": ["GET", "DELETE"],
                "backend_url": "https://backend.acme.com/v2/payments"
            }
        ],
        "status": "published"
    });

    let response = app
        .oneshot(auth_json_req("POST", "/contracts", two_endpoints))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
        .await
        .unwrap();
    let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(data["routes_generated"], 2);

    // Old route should be gone, 2 new routes present
    assert_eq!(state.route_registry.count(), 2);
}

#[tokio::test]
async fn test_contract_routes_have_classification() {
    let state = create_test_state(Some("secret"));
    let app = build_full_admin_router(state.clone());

    let vh_contract = serde_json::json!({
        "name": "sensitive-api",
        "version": "1.0.0",
        "tenant_id": "acme",
        "classification": "VH",
        "endpoints": [{
            "path": "/data",
            "methods": ["GET"],
            "backend_url": "https://backend.acme.com/data"
        }],
        "status": "draft"
    });

    let _ = app
        .oneshot(auth_json_req("POST", "/contracts", vh_contract))
        .await
        .unwrap();

    let route = state
        .route_registry
        .get("uac:acme:sensitive-api:0")
        .unwrap();
    assert_eq!(route.classification, Some(crate::uac::Classification::VH));
}

#[tokio::test]
async fn test_contract_upsert_generates_mcp_tools() {
    let state = create_test_state(Some("secret"));
    let app = build_full_admin_router(state.clone());

    let contract = serde_json::json!({
        "name": "orders",
        "version": "1.0.0",
        "tenant_id": "acme",
        "classification": "H",
        "endpoints": [
            {
                "path": "/orders",
                "methods": ["GET"],
                "backend_url": "https://backend.acme.com/orders",
                "operation_id": "list_orders"
            },
            {
                "path": "/orders",
                "methods": ["POST"],
                "backend_url": "https://backend.acme.com/orders",
                "operation_id": "create_order"
            }
        ],
        "status": "published"
    });

    let response = app
        .oneshot(auth_json_req("POST", "/contracts", contract))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::CREATED);
    let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
        .await
        .unwrap();
    let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(data["tools_generated"], 2);

    // Both tools registered
    assert_eq!(state.tool_registry.count(), 2);
    assert!(state.tool_registry.exists("uac:acme:orders:list_orders"));
    assert!(state.tool_registry.exists("uac:acme:orders:create_order"));
}

#[tokio::test]
async fn test_contract_delete_cascades_tools() {
    let state = create_test_state(Some("secret"));
    let app = build_full_admin_router(state.clone());

    // Create contract → generates tools
    let _ = app
        .clone()
        .oneshot(auth_json_req("POST", "/contracts", sample_contract_json()))
        .await
        .unwrap();
    assert_eq!(state.tool_registry.count(), 1);

    // Delete contract → cascades tool removal
    let response = app
        .oneshot(auth_req("DELETE", "/contracts/acme:payment-api"))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(state.tool_registry.count(), 0);
}

#[tokio::test]
async fn test_mcp_tools_visible_via_list() {
    let state = create_test_state(Some("secret"));
    let app = build_full_admin_router(state.clone());

    let _ = app
        .oneshot(auth_json_req("POST", "/contracts", sample_contract_json()))
        .await
        .unwrap();

    // Tool should be visible in tool registry
    let tools = state.tool_registry.list(Some("acme"));
    assert_eq!(tools.len(), 1);
    assert_eq!(tools[0].name, "uac:acme:payment-api:payment-api-0");
    assert_eq!(tools[0].tenant_id.as_deref(), Some("acme"));
}

// =============================================================================
// GW-1 P1-1 / P1-2 / P2-2: transactional invariants
// =============================================================================
//
// These tests exercise `perform_upsert` / `perform_delete` with mock
// binders so we can inject failures — the concrete `RestBinder` /
// `McpBinder` cannot currently fail, but the trait signature allows it
// and the transactional path must be correct *by construction*.

mod transactional {
    use std::sync::Arc;

    use async_trait::async_trait;
    use axum::http::StatusCode;
    use axum::response::IntoResponse;

    use crate::handlers::admin::contracts::{perform_delete, perform_upsert, ContractBinders};
    use crate::uac::registry::ContractRegistry;
    use crate::uac::schema::{ContractStatus, UacContractSpec, UacEndpoint};

    /// Mock binder with per-method outcomes; remembers calls for assertions.
    struct MockBinders {
        rest_bind: Result<usize, String>,
        mcp_bind: Result<usize, String>,
        rest_unbind: Result<usize, String>,
        mcp_unbind: Result<usize, String>,
        calls: Arc<Mutex<Vec<&'static str>>>,
    }

    use std::sync::Mutex;

    impl MockBinders {
        fn happy(rest_n: usize, mcp_n: usize) -> Self {
            Self {
                rest_bind: Ok(rest_n),
                mcp_bind: Ok(mcp_n),
                rest_unbind: Ok(rest_n),
                mcp_unbind: Ok(mcp_n),
                calls: Arc::new(Mutex::new(vec![])),
            }
        }
        fn record(&self, what: &'static str) {
            self.calls.lock().unwrap().push(what);
        }
        fn call_log(&self) -> Vec<&'static str> {
            self.calls.lock().unwrap().clone()
        }
    }

    #[async_trait]
    impl ContractBinders for MockBinders {
        async fn bind_rest(&self, _: &UacContractSpec) -> Result<usize, String> {
            self.record("bind_rest");
            self.rest_bind.clone()
        }
        async fn bind_mcp(&self, _: &UacContractSpec) -> Result<usize, String> {
            self.record("bind_mcp");
            self.mcp_bind.clone()
        }
        async fn unbind_rest(&self, _: &str) -> Result<usize, String> {
            self.record("unbind_rest");
            self.rest_unbind.clone()
        }
        async fn unbind_mcp(&self, _: &str) -> Result<usize, String> {
            self.record("unbind_mcp");
            self.mcp_unbind.clone()
        }
    }

    fn valid_contract(name: &str, tenant: &str) -> UacContractSpec {
        let mut spec = UacContractSpec::new(name, tenant);
        spec.status = ContractStatus::Published;
        spec.endpoints = vec![UacEndpoint {
            path: "/tx".to_string(),
            methods: vec!["GET".to_string()],
            backend_url: "https://backend.test".to_string(),
            method: None,
            description: None,
            operation_id: Some("tx".to_string()),
            input_schema: None,
            output_schema: None,
        }];
        spec
    }

    async fn read_body_json(resp: axum::response::Response) -> serde_json::Value {
        let body = axum::body::to_bytes(resp.into_body(), 64 * 1024)
            .await
            .unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    // ── P1-1: upsert_contract_rest_bind_failure_does_not_persist_contract ─
    #[tokio::test]
    async fn test_upsert_rest_bind_failure_does_not_persist() {
        let registry = Arc::new(ContractRegistry::new());
        let binders = MockBinders {
            rest_bind: Err("forced rest failure".into()),
            mcp_bind: Ok(99), // unreachable — bind-first aborts earlier
            rest_unbind: Ok(0),
            mcp_unbind: Ok(0),
            calls: Arc::new(Mutex::new(vec![])),
        };

        let resp = perform_upsert(
            registry.clone(),
            &binders,
            /* llm_enabled */ false,
            valid_contract("orders", "acme"),
        )
        .await
        .into_response();

        assert_eq!(resp.status(), StatusCode::INTERNAL_SERVER_ERROR);
        let json = read_body_json(resp).await;
        assert_eq!(json["status"], "error");
        assert!(json["message"].as_str().unwrap().contains("REST"));

        // Invariant: contract NOT persisted.
        assert_eq!(registry.count(), 0);
        assert!(registry.get("acme:orders").is_none());

        // mcp_bind must not have been called: bind-first aborts on REST failure.
        let calls = binders.call_log();
        assert!(!calls.contains(&"bind_mcp"), "calls = {:?}", calls);
    }

    // ── P1-1: upsert_contract_mcp_bind_failure_does_not_persist_contract ──
    #[tokio::test]
    async fn test_upsert_mcp_bind_failure_does_not_persist_and_rolls_back_rest() {
        let registry = Arc::new(ContractRegistry::new());
        let binders = MockBinders {
            rest_bind: Ok(1),
            mcp_bind: Err("forced mcp failure".into()),
            rest_unbind: Ok(1),
            mcp_unbind: Ok(0),
            calls: Arc::new(Mutex::new(vec![])),
        };

        let resp = perform_upsert(
            registry.clone(),
            &binders,
            false,
            valid_contract("orders", "acme"),
        )
        .await
        .into_response();

        assert_eq!(resp.status(), StatusCode::INTERNAL_SERVER_ERROR);
        let json = read_body_json(resp).await;
        assert!(json["message"].as_str().unwrap().contains("MCP"));

        // Invariant: contract NOT persisted.
        assert_eq!(registry.count(), 0);

        // REST rollback must have been attempted.
        let calls = binders.call_log();
        assert_eq!(calls, vec!["bind_rest", "bind_mcp", "unbind_rest"]);
    }

    // ── P2-2: response counts come from BindingOutput lengths ───────────
    #[tokio::test]
    async fn test_upsert_uses_binding_output_lengths_not_endpoint_count() {
        let registry = Arc::new(ContractRegistry::new());
        // Contract has 1 endpoint, but mocks claim 7 REST routes and 3 tools —
        // the response must echo the binder counts, not the endpoint count.
        let binders = MockBinders::happy(7, 3);

        let resp = perform_upsert(
            registry.clone(),
            &binders,
            false,
            valid_contract("orders", "acme"),
        )
        .await
        .into_response();

        assert_eq!(resp.status(), StatusCode::CREATED);
        let json = read_body_json(resp).await;
        assert_eq!(json["routes_generated"], 7);
        assert_eq!(json["tools_generated"], 3);

        // Happy path: contract IS persisted, and only after both binds.
        assert_eq!(registry.count(), 1);
        assert_eq!(binders.call_log(), vec!["bind_rest", "bind_mcp"]);
    }

    // ── P1-2: delete_contract_rest_unbind_failure_does_not_delete ───────
    #[tokio::test]
    async fn test_delete_rest_unbind_failure_does_not_remove_contract() {
        let registry = Arc::new(ContractRegistry::new());
        registry.upsert(valid_contract("orders", "acme"));

        let binders = MockBinders {
            rest_bind: Ok(0),
            mcp_bind: Ok(0),
            rest_unbind: Err("forced rest unbind failure".into()),
            mcp_unbind: Ok(0),
            calls: Arc::new(Mutex::new(vec![])),
        };

        let resp = perform_delete(registry.clone(), &binders, "acme:orders".into())
            .await
            .into_response();

        assert_eq!(resp.status(), StatusCode::INTERNAL_SERVER_ERROR);
        let json = read_body_json(resp).await;
        assert!(json["message"].as_str().unwrap().contains("REST"));

        // Invariant: contract NOT removed.
        assert_eq!(registry.count(), 1);
        assert!(registry.get("acme:orders").is_some());

        // mcp_unbind must not have been called: unbind-first aborts on REST.
        let calls = binders.call_log();
        assert!(!calls.contains(&"unbind_mcp"));
    }

    // ── P1-2: delete_contract_mcp_unbind_failure_does_not_delete ────────
    //
    // Asserts the core invariant (registry still holds the contract) and
    // that the handler doesn't silently declare success. The specific
    // rollback sequence is covered in more detail by
    // `test_delete_contract_mcp_unbind_failure_restores_rest_bindings_or_reports_partial_state`.
    #[tokio::test]
    async fn test_delete_mcp_unbind_failure_does_not_remove_contract() {
        let registry = Arc::new(ContractRegistry::new());
        registry.upsert(valid_contract("orders", "acme"));

        let binders = MockBinders {
            rest_bind: Ok(0),
            mcp_bind: Ok(0),
            rest_unbind: Ok(1),
            mcp_unbind: Err("forced mcp unbind failure".into()),
            calls: Arc::new(Mutex::new(vec![])),
        };

        let resp = perform_delete(registry.clone(), &binders, "acme:orders".into())
            .await
            .into_response();

        assert_eq!(resp.status(), StatusCode::INTERNAL_SERVER_ERROR);
        let json = read_body_json(resp).await;
        assert!(json["message"].as_str().unwrap().contains("MCP"));

        // Invariant: contract NOT removed (even though REST routes already gone).
        assert_eq!(registry.count(), 1);
        assert!(registry.get("acme:orders").is_some());

        // Both unbinds attempted in the right order; rollback path is
        // asserted in detail by the dedicated restore-rollback test.
        let calls = binders.call_log();
        assert_eq!(&calls[..2], &["unbind_rest", "unbind_mcp"]);
    }

    // ── Happy delete through the transactional path ─────────────────────
    #[tokio::test]
    async fn test_delete_happy_path_reports_binding_counts() {
        let registry = Arc::new(ContractRegistry::new());
        registry.upsert(valid_contract("orders", "acme"));

        let binders = MockBinders::happy(5, 2);
        let resp = perform_delete(registry.clone(), &binders, "acme:orders".into())
            .await
            .into_response();

        assert_eq!(resp.status(), StatusCode::OK);
        let json = read_body_json(resp).await;
        assert_eq!(json["status"], "deleted");
        assert_eq!(json["routes_removed"], 5);
        assert_eq!(json["tools_removed"], 2);
        assert_eq!(registry.count(), 0);

        // Order must be unbind-first: both unbinds happened before remove.
        assert_eq!(binders.call_log(), vec!["unbind_rest", "unbind_mcp"]);
    }

    // ── Unknown contract deletes still short-circuit to 404 ─────────────
    #[tokio::test]
    async fn test_delete_unknown_contract_returns_404_without_calling_binders() {
        let registry = Arc::new(ContractRegistry::new());
        let binders = MockBinders::happy(0, 0);

        let resp = perform_delete(registry.clone(), &binders, "ghost:none".into())
            .await
            .into_response();

        assert_eq!(resp.status(), StatusCode::NOT_FOUND);
        assert!(binders.call_log().is_empty());
    }

    // =========================================================================
    // GW-1 P1-1 / P1-2 update-case rollback (post-review patch on #2502)
    //
    // The CREATE-case tests above establish that new contracts aren't persisted
    // if the binders fail. These UPDATE-case tests establish the stronger
    // invariant that a binder failure on an *existing* contract restores the
    // previous bindings, so registry + REST + MCP stay consistent.
    // =========================================================================

    // ── upsert_existing_contract_rest_failure_restores_previous_bindings ──
    //
    // Setup: pre-seeded registry with an "old" contract.
    // Flow: bind_rest(new) fails → handler calls bind_rest(old) + bind_mcp(old)
    //       as rollback. The mock returns Err for bind_rest on *every* call,
    //       so the rollback's bind_rest call also logs a warn — but the
    //       test's job is to verify the *attempt*, not the binder's health.
    #[tokio::test]
    async fn test_upsert_existing_contract_rest_bind_failure_restores_previous_bindings() {
        let registry = Arc::new(ContractRegistry::new());
        // Seed with the "old" version of the contract.
        let mut old = valid_contract("orders", "acme");
        old.version = "1.0.0".into();
        registry.upsert(old);

        let binders = MockBinders {
            rest_bind: Err("forced rest failure".into()),
            mcp_bind: Ok(5),
            rest_unbind: Ok(0),
            mcp_unbind: Ok(0),
            calls: Arc::new(Mutex::new(vec![])),
        };

        // Attempt to upsert a "new" version.
        let mut new = valid_contract("orders", "acme");
        new.version = "2.0.0".into();
        let resp = perform_upsert(registry.clone(), &binders, false, new)
            .await
            .into_response();

        assert_eq!(resp.status(), StatusCode::INTERNAL_SERVER_ERROR);

        // Invariant: the OLD contract is still the one in the registry —
        // the new upsert did not commit, and the rollback was attempted.
        assert_eq!(registry.count(), 1);
        let persisted = registry.get("acme:orders").expect("old contract kept");
        assert_eq!(persisted.version, "1.0.0");

        // Call log: bind_rest (new, fails) → bind_rest (old, rollback) →
        //           bind_mcp (old, rollback). No bind_mcp on new.
        assert_eq!(
            binders.call_log(),
            vec!["bind_rest", "bind_rest", "bind_mcp"]
        );
    }

    // ── upsert_existing_contract_mcp_failure_restores_previous_bindings ──
    //
    // Flow: bind_rest(new) OK → bind_mcp(new) fails → handler tries
    //       bind_rest(old) + bind_mcp(old) as rollback rather than just
    //       unbind_rest (which would leave the contract_registry's "old"
    //       row with no REST/MCP artefacts).
    #[tokio::test]
    async fn test_upsert_existing_contract_mcp_bind_failure_restores_previous_bindings() {
        let registry = Arc::new(ContractRegistry::new());
        let mut old = valid_contract("orders", "acme");
        old.version = "1.0.0".into();
        registry.upsert(old);

        let binders = MockBinders {
            rest_bind: Ok(7),
            mcp_bind: Err("forced mcp failure".into()),
            rest_unbind: Ok(0),
            mcp_unbind: Ok(0),
            calls: Arc::new(Mutex::new(vec![])),
        };

        let mut new = valid_contract("orders", "acme");
        new.version = "2.0.0".into();
        let resp = perform_upsert(registry.clone(), &binders, false, new)
            .await
            .into_response();

        assert_eq!(resp.status(), StatusCode::INTERNAL_SERVER_ERROR);

        // Old contract still in registry, unchanged.
        let persisted = registry.get("acme:orders").expect("old contract kept");
        assert_eq!(persisted.version, "1.0.0");

        // Call log: new path attempted (bind_rest OK, bind_mcp fails),
        // then rollback restores (bind_rest old, bind_mcp old).
        // Crucially: NO unbind_rest — on an update we restore rather than
        // wipe, because wiping would leave the old contract with no artefacts.
        let calls = binders.call_log();
        assert_eq!(
            calls,
            vec!["bind_rest", "bind_mcp", "bind_rest", "bind_mcp"],
            "expected restore sequence, got {:?}",
            calls
        );
        assert!(!calls.contains(&"unbind_rest"));
    }

    // ── delete_contract_mcp_unbind_failure_restores_rest_bindings_or_reports_partial_state ──
    //
    // Flow: unbind_rest(key) OK (REST routes gone) → unbind_mcp(key) fails.
    // Handler attempts bind_rest(old_contract) to restore REST routes, then
    // returns 500 and leaves the contract in the registry. MCP state is
    // indeterminate by construction, so we document it explicitly rather
    // than reporting false success.
    #[tokio::test]
    async fn test_delete_contract_mcp_unbind_failure_restores_rest_bindings_or_reports_partial_state(
    ) {
        let registry = Arc::new(ContractRegistry::new());
        registry.upsert(valid_contract("orders", "acme"));

        let binders = MockBinders {
            rest_bind: Ok(1),
            mcp_bind: Ok(0),
            rest_unbind: Ok(1),
            mcp_unbind: Err("forced mcp unbind failure".into()),
            calls: Arc::new(Mutex::new(vec![])),
        };

        let resp = perform_delete(registry.clone(), &binders, "acme:orders".into())
            .await
            .into_response();

        assert_eq!(resp.status(), StatusCode::INTERNAL_SERVER_ERROR);
        let json = read_body_json(resp).await;
        assert!(json["message"].as_str().unwrap().contains("MCP"));

        // Invariant: contract stays in registry (we could not fully delete).
        assert_eq!(registry.count(), 1);
        assert!(registry.get("acme:orders").is_some());

        // Call log: unbind_rest (OK) → unbind_mcp (fails) → bind_rest(old)
        // as best-effort REST restore.
        let calls = binders.call_log();
        assert_eq!(
            calls,
            vec!["unbind_rest", "unbind_mcp", "bind_rest"],
            "expected REST restore after MCP unbind failure, got {:?}",
            calls
        );
    }
}
