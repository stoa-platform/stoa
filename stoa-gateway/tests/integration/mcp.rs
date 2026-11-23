//! MCP protocol integration tests.
//!
//! Tests the MCP discovery, tools, and OAuth endpoints across the full router.
//! In EdgeMcp mode (default), these endpoints are available.

use axum::http::StatusCode;
use std::{collections::HashMap, sync::Arc};
use stoa_gateway::config::Config;
use stoa_gateway::mcp::tools::dynamic_tool::DynamicTool;
use stoa_gateway::mcp::tools::ToolSchema;

use crate::common::TestApp;

// ========================================================================
// MCP Discovery endpoints (no auth required)
// ========================================================================

#[tokio::test]
async fn test_mcp_discovery_returns_json() {
    let app = TestApp::new();
    let (status, body) = app.get("/mcp").await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    // Discovery response has server.name and server.version
    assert_eq!(json["server"]["name"], "STOA Gateway");
    assert!(json["server"]["version"].is_string());
    // serde renames protocol_version → protocolVersion
    assert!(json["server"]["protocolVersion"].is_string());
}

#[tokio::test]
async fn test_mcp_discovery_includes_endpoints() {
    let app = TestApp::new();
    let (status, body) = app.get("/mcp").await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    // Discovery lists available endpoints
    assert_eq!(json["endpoints"]["sse"], "/mcp/sse");
    assert_eq!(json["endpoints"]["tools_list"], "/mcp/tools/list");
    assert_eq!(json["endpoints"]["tools_call"], "/mcp/tools/call");
}

#[tokio::test]
async fn test_mcp_capabilities_endpoint() {
    let app = TestApp::new();
    let (status, body) = app.get("/mcp/capabilities").await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    // Capabilities should list supported features
    assert!(json.is_object());
    assert!(json.get("capabilities").is_some());
}

#[tokio::test]
async fn test_mcp_health_endpoint() {
    let app = TestApp::new();
    let (status, body) = app.get("/mcp/health").await;
    assert_eq!(status, StatusCode::OK);
    assert!(!body.is_empty());
}

// ========================================================================
// MCP Tools — direct JSON (not JSON-RPC envelope)
//
// A missing validator refuses protected requests. Successful tool listings
// use the signed local fixture; negotiation remains public.
// ========================================================================

#[tokio::test]
async fn test_mcp_tools_list_no_validator_denies_access() {
    let app = TestApp::new();
    let (status, body) = app.post_json("/mcp/tools/list", "{}").await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert_eq!(json["isError"], true);
    assert!(json.get("tools").is_none());
}

#[tokio::test]
async fn test_mcp_tools_call_no_validator_unknown_tool() {
    let app = TestApp::new();
    // ToolsCallRequest: {"name": "xxx", "arguments": {}}
    let (status, body) = app
        .post_json(
            "/mcp/tools/call",
            r#"{"name":"nonexistent-tool","arguments":{}}"#,
        )
        .await;
    // Should return a response (200 with error content or a non-200)
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    // The response should indicate an error for unknown tool
    if status == StatusCode::OK {
        // Check isError or content indicating failure
        assert!(
            json.get("isError").is_some() || json.get("content").is_some(),
            "Expected error indication for unknown tool"
        );
    } else {
        // Non-200 status is also acceptable for unknown tool
        assert!(status.is_client_error() || status.is_server_error());
    }
}

// regression for CAB-2227
#[tokio::test]
async fn test_unauthenticated_tools_call_is_rejected_before_cp_lookup() {
    let app = TestApp::with_config(Config {
        control_plane_url: Some("http://127.0.0.1:1".to_string()),
        quota_enforcement_enabled: false,
        ..Config::default()
    });
    let schema = ToolSchema {
        schema_type: "object".to_string(),
        properties: HashMap::new(),
        required: Vec::new(),
    };
    let tool = DynamicTool::new(
        "any_tool",
        "permission regression tool",
        "http://localhost:9/noop",
        "POST",
        schema,
        "default",
    )
    .into_public();
    app.state.tool_registry.register(Arc::new(tool));

    let (status, _) = app
        .post_json("/mcp/tools/call", r#"{"name":"any_tool","arguments":{}}"#)
        .await;

    // Authentication fails before a tenant permission lookup can be attempted.
    assert_eq!(status, StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn test_mcp_tools_list_no_validator_denial_shape() {
    let app = TestApp::new();
    let (status, body) = app.post_json("/mcp/tools/list", "{}").await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert_eq!(json["isError"], true);
    assert!(json.get("tools").is_none());
}

// ========================================================================
// MCP v1 REST API (validator unset → auth middleware passthrough)
// ========================================================================

#[tokio::test]
async fn test_mcp_rest_tools_list_no_validator() {
    let app = TestApp::new();
    let (status, body) = app.get("/mcp/v1/tools").await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert_eq!(json["isError"], true);
    assert!(json.get("tools").is_none());
}

#[tokio::test]
async fn test_mcp_rest_tools_invoke_no_validator_unknown() {
    let app = TestApp::new();
    // RestToolInvokeRequest: {"tool": "name", "arguments": {}}
    let invoke = r#"{"tool":"nonexistent","arguments":{}}"#;
    let (status, body) = app.post_json("/mcp/v1/tools/invoke", invoke).await;
    assert!(!body.is_empty());
    assert_eq!(status, StatusCode::UNAUTHORIZED);
}

// ========================================================================
// OAuth Discovery endpoints (RFC 9728 / 8414)
// ========================================================================

#[tokio::test]
async fn test_oauth_protected_resource_metadata() {
    let app = TestApp::new();
    let (status, body) = app.get("/.well-known/oauth-protected-resource").await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    // RFC 9728: must have resource field
    assert!(json.get("resource").is_some());
}

#[tokio::test]
async fn test_oauth_authorization_server_metadata() {
    let app = TestApp::new();
    let (status, body) = app.get("/.well-known/oauth-authorization-server").await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    // RFC 8414: must have issuer
    assert!(json.get("issuer").is_some());
}

#[tokio::test]
async fn test_openid_configuration_requires_keycloak() {
    // Without Keycloak URL configured, OIDC discovery returns 503
    let app = TestApp::new();
    let (status, _body) = app.get("/.well-known/openid-configuration").await;
    assert_eq!(status, StatusCode::SERVICE_UNAVAILABLE);
}

#[tokio::test]
async fn test_authenticated_mcp_tools_list() {
    let app = TestApp::with_mcp_auth().await;
    let (status, body) = app
        .post_json_with_bearer("/mcp/tools/list", "{}", app.mcp_token())
        .await;
    assert_eq!(status, StatusCode::OK);
    let response: serde_json::Value = serde_json::from_str(&body).unwrap();
    assert!(response["tools"].is_array());
}

// ========================================================================
// Explicit local-dev auth path & fail-closed boundaries
// ========================================================================

fn regulated_policy_file() -> tempfile::NamedTempFile {
    use std::io::Write;
    let mut file = tempfile::NamedTempFile::new().expect("temp policy file");
    write!(
        file,
        "{}",
        stoa_gateway::policy::PolicyEngineConfig::default().default_policy
    )
    .expect("write policy");
    file
}

#[tokio::test]
async fn test_explicit_local_dev_allows_rest_and_mcp_tools_list_without_idp_or_cp() {
    let app = TestApp::with_config(Config {
        environment: stoa_gateway::config::Environment::Dev,
        environment_explicit: true,
        ..Config::default()
    });
    stoa_gateway::mcp::tools::native_tool::register_native_tools(
        &app.state.tool_registry,
        stoa_gateway::mcp::tools::native_tool::create_http_client(),
        "",
        app.state.tool_registry.clone(),
        Some(app.state.session_manager.clone()),
        Some(app.state.circuit_breakers.clone()),
        Some(app.state.prompt_cache.clone()),
    );

    // Readiness and discovery remain available.
    let (ready_status, ready_body) = app.get("/ready").await;
    assert_eq!(ready_status, StatusCode::OK);
    assert_eq!(ready_body, "READY");

    let (disc_status, _) = app.get("/mcp").await;
    assert_eq!(disc_status, StatusCode::OK);

    // JSON-RPC initialize on POST /mcp stays public.
    let init = r#"{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"solo","version":"1.0"}}}"#;
    let (init_status, init_body) = app.post_json("/mcp", init).await;
    assert_eq!(init_status, StatusCode::OK);
    let init_json: serde_json::Value = serde_json::from_str(&init_body).expect("valid JSON");
    assert!(init_json["result"]["protocolVersion"].is_string());

    // REST POST /mcp/tools/list returns 200 with native tools.
    let (rest_status, rest_body) = app.post_json("/mcp/tools/list", "{}").await;
    assert_eq!(rest_status, StatusCode::OK);
    let rest_json: serde_json::Value = serde_json::from_str(&rest_body).expect("valid JSON");
    assert!(
        rest_json["tools"].as_array().is_some_and(|t| !t.is_empty()),
        "expected native tools in REST /mcp/tools/list: {rest_body}"
    );

    // REST GET /mcp/v1/tools returns 200 with native tools.
    let (v1_status, v1_body) = app.get("/mcp/v1/tools").await;
    assert_eq!(v1_status, StatusCode::OK);
    let v1_json: serde_json::Value = serde_json::from_str(&v1_body).expect("valid JSON");
    assert!(v1_json.as_array().is_some_and(|t| !t.is_empty()));

    // JSON-RPC tools/list on POST /mcp returns 200 with native tools.
    let rpc_list = r#"{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}"#;
    let (rpc_status, rpc_body) = app.post_json("/mcp", rpc_list).await;
    assert_eq!(rpc_status, StatusCode::OK);
    let rpc_json: serde_json::Value = serde_json::from_str(&rpc_body).expect("valid JSON");
    assert!(
        rpc_json["result"]["tools"]
            .as_array()
            .is_some_and(|t| !t.is_empty()),
        "expected native tools in JSON-RPC tools/list: {rpc_body}"
    );

    // Presenting a Bearer token without a validator must still fail closed.
    let (bearer_rest, _) = app
        .post_json_with_bearer("/mcp/tools/list", "{}", "fake-token")
        .await;
    assert_eq!(bearer_rest, StatusCode::UNAUTHORIZED);
    let (bearer_rpc, _) = app
        .post_json_with_bearer("/mcp", rpc_list, "fake-token")
        .await;
    assert_eq!(bearer_rpc, StatusCode::UNAUTHORIZED);

    // Protected non-MCP routes (A2A / API proxy) stay fail-closed in explicit local dev.
    let (a2a_status, _) = app
        .post_json(
            "/a2a",
            r#"{"jsonrpc":"2.0","id":1,"method":"tasks/get","params":{"id":"x"}}"#,
        )
        .await;
    assert_eq!(a2a_status, StatusCode::UNAUTHORIZED);
    let (proxy_status, _) = app.get("/proxy/example/ping").await;
    assert_eq!(proxy_status, StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn test_explicit_local_dev_treats_blank_urls_as_unset() {
    let app = TestApp::with_config(Config {
        environment: stoa_gateway::config::Environment::Dev,
        environment_explicit: true,
        keycloak_url: Some("   ".to_string()),
        control_plane_url: Some("".to_string()),
        ..Config::default()
    });
    let (rest_status, _) = app.post_json("/mcp/tools/list", "{}").await;
    assert_eq!(rest_status, StatusCode::OK);
    let (rpc_status, _) = app
        .post_json(
            "/mcp",
            r#"{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}"#,
        )
        .await;
    assert_eq!(rpc_status, StatusCode::OK);
}

#[tokio::test]
async fn test_explicit_local_dev_locked_when_keycloak_or_cp_configured() {
    let rpc_list = r#"{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}"#;

    // Explicit dev with Keycloak URL configured: JWT required (401 without token).
    let with_keycloak = TestApp::with_config(Config {
        environment: stoa_gateway::config::Environment::Dev,
        environment_explicit: true,
        keycloak_url: Some("http://127.0.0.1:1".to_string()),
        ..Config::default()
    });
    let (status, _) = with_keycloak.post_json("/mcp/tools/list", "{}").await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
    let (status, _) = with_keycloak.post_json("/mcp", rpc_list).await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);

    // Explicit dev with only Control Plane URL configured: 401 without JWT.
    let with_cp = TestApp::with_config(Config {
        environment: stoa_gateway::config::Environment::Dev,
        environment_explicit: true,
        control_plane_url: Some("http://127.0.0.1:1".to_string()),
        ..Config::default()
    });
    let (status, _) = with_cp.post_json("/mcp/tools/list", "{}").await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
    let (status, _) = with_cp.post_json("/mcp", rpc_list).await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn test_staging_and_prod_without_idp_or_cp_stay_401() {
    let policy_file = regulated_policy_file();
    let policy_path = policy_file.path().display().to_string();
    let rpc_list = r#"{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}"#;

    for env in [
        stoa_gateway::config::Environment::Staging,
        stoa_gateway::config::Environment::Prod,
    ] {
        let app = TestApp::with_config(Config {
            environment: env,
            environment_explicit: true,
            policy_enabled: true,
            policy_path: Some(policy_path.clone()),
            ..Config::default()
        });
        let (rest_status, _) = app.post_json("/mcp/tools/list", "{}").await;
        assert_eq!(
            rest_status,
            StatusCode::UNAUTHORIZED,
            "{env:?} REST tools/list"
        );
        let (rpc_status, _) = app.post_json("/mcp", rpc_list).await;
        assert_eq!(
            rpc_status,
            StatusCode::UNAUTHORIZED,
            "{env:?} RPC tools/list"
        );
        let (v1_status, _) = app.get("/mcp/v1/tools").await;
        assert_eq!(v1_status, StatusCode::UNAUTHORIZED, "{env:?} REST v1 tools");
        let (res_status, _) = app.post_json("/mcp/resources/list", "{}").await;
        assert_eq!(
            res_status,
            StatusCode::UNAUTHORIZED,
            "{env:?} REST resources/list"
        );
    }
}

#[tokio::test]
async fn test_implicit_dev_default_remains_locked_while_ready_succeeds() {
    let app = TestApp::new();
    let (ready_status, ready_body) = app.get("/ready").await;
    assert_eq!(ready_status, StatusCode::OK);
    assert_eq!(ready_body, "READY");

    let (rest_status, _) = app.post_json("/mcp/tools/list", "{}").await;
    assert_eq!(rest_status, StatusCode::UNAUTHORIZED);
    let (rpc_status, _) = app
        .post_json(
            "/mcp",
            r#"{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}"#,
        )
        .await;
    assert_eq!(rpc_status, StatusCode::UNAUTHORIZED);
    let (res_status, _) = app.post_json("/mcp/resources/list", "{}").await;
    assert_eq!(res_status, StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn test_explicit_local_dev_resources_and_tools_are_tenant_scoped() {
    let app = TestApp::with_config(Config {
        environment: stoa_gateway::config::Environment::Dev,
        environment_explicit: true,
        ..Config::default()
    });
    let schema = ToolSchema {
        schema_type: "object".to_string(),
        properties: HashMap::new(),
        required: Vec::new(),
    };
    let other_tenant_tool = DynamicTool::new(
        "other_tenant_tool",
        "Private tool owned by another tenant",
        "http://localhost:9/other",
        "GET",
        schema.clone(),
        "other-tenant",
    );
    let local_tenant_tool = DynamicTool::new(
        "local_tenant_tool",
        "Tool owned by the local dev tenant",
        "http://localhost:9/local",
        "GET",
        schema.clone(),
        "local",
    );
    let global_tool = DynamicTool::new(
        "global_public_tool",
        "Global tool visible across tenants",
        "http://localhost:9/global",
        "GET",
        schema,
        "default",
    )
    .into_public();

    app.state
        .tool_registry
        .register(Arc::new(other_tenant_tool));
    app.state
        .tool_registry
        .register(Arc::new(local_tenant_tool));
    app.state.tool_registry.register(Arc::new(global_tool));

    // POST /mcp/resources/list includes local and global tools, never another tenant's tool.
    let (res_list_status, res_list_body) = app.post_json("/mcp/resources/list", "{}").await;
    assert_eq!(res_list_status, StatusCode::OK);
    let res_list_json: serde_json::Value =
        serde_json::from_str(&res_list_body).expect("valid JSON");
    let resource_names: Vec<&str> = res_list_json["resources"]
        .as_array()
        .expect("resources array")
        .iter()
        .filter_map(|item| item["name"].as_str())
        .collect();
    assert!(
        !resource_names.contains(&"other_tenant_tool"),
        "other tenant tool leaked in resources/list: {resource_names:?}"
    );
    assert!(resource_names.contains(&"local_tenant_tool"));
    assert!(resource_names.contains(&"global_public_tool"));

    // POST /mcp/resources/read refuses another tenant's tool with 404.
    let (other_read_status, other_read_body) = app
        .post_json(
            "/mcp/resources/read",
            r#"{"uri":"stoa://tools/other_tenant_tool"}"#,
        )
        .await;
    assert_eq!(other_read_status, StatusCode::NOT_FOUND);
    assert!(!other_read_body.contains("Private tool owned by another tenant"));

    // Local and global resources remain readable.
    for uri in [
        "stoa://tools/local_tenant_tool",
        "stoa://tools/global_public_tool",
    ] {
        let payload = serde_json::json!({ "uri": uri }).to_string();
        let (read_status, read_body) = app.post_json("/mcp/resources/read", &payload).await;
        assert_eq!(read_status, StatusCode::OK, "uri: {uri}");
        let read_json: serde_json::Value = serde_json::from_str(&read_body).expect("valid JSON");
        assert_eq!(read_json["contents"][0]["uri"], uri);
    }

    // POST /mcp/tools/list also omits the other tenant's tool.
    let (tools_list_status, tools_list_body) = app.post_json("/mcp/tools/list", "{}").await;
    assert_eq!(tools_list_status, StatusCode::OK);
    let tools_list_json: serde_json::Value =
        serde_json::from_str(&tools_list_body).expect("valid JSON");
    let tool_names: Vec<&str> = tools_list_json["tools"]
        .as_array()
        .expect("tools array")
        .iter()
        .filter_map(|item| item["name"].as_str())
        .collect();
    assert!(
        !tool_names.contains(&"other_tenant_tool"),
        "other tenant tool leaked in tools/list: {tool_names:?}"
    );
    assert!(tool_names.contains(&"local_tenant_tool"));
    assert!(tool_names.contains(&"global_public_tool"));
}
