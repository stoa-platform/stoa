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
