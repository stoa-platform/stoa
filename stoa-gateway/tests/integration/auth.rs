//! Auth pipeline integration tests.
//!
//! Tests authentication and authorization across the full request pipeline:
//! - Health/ready endpoints (no auth required)
//! - Admin endpoints (Bearer token auth)
//! - MCP endpoints (JWT auth context)

use axum::http::StatusCode;
use serde_json::{json, Value};
use std::path::Path;
use std::process::Stdio;
use std::time::Duration;
use tokio::process::{Child, Command};
use wiremock::{
    matchers::{method, path},
    Mock, MockServer, ResponseTemplate,
};

use crate::common::{config_with_admin_token, TestApp};
use crate::jwt;
use crate::quota::{quota_contract, CONTRACT_ADMIN_ROUTE, CONTRACT_ROUTE};
use stoa_gateway::metrics::{
    init_all_metrics, GUARDRAILS_FULL_DECISIONS, GUARDRAILS_FULL_GUARDRAILS,
};

// ========================================================================
// Health / Ready — no auth required
// ========================================================================

#[tokio::test]
async fn test_health_no_auth_required() {
    let app = TestApp::new();
    let (status, body) = app.get("/health").await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body, "OK");
}

#[tokio::test]
async fn test_ready_no_cp_configured() {
    // In dev mode without a control_plane_url, standalone readiness succeeds
    let app = TestApp::new();
    let (status, body) = app.get("/ready").await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body, "READY");
}

#[tokio::test]
async fn test_metrics_no_auth_required() {
    init_all_metrics();
    let app = TestApp::new();
    let (status, body) = app.get("/metrics").await;
    assert_eq!(status, StatusCode::OK);

    let zero_init_surfaces = [
        ("edge-mcp", "mcp"),
        ("proxy", "api_proxy"),
        ("proxy", "dynamic_proxy"),
        ("proxy", "ws_proxy"),
    ];
    for (deployment_mode, surface) in zero_init_surfaces {
        for guardrail in GUARDRAILS_FULL_GUARDRAILS {
            let series = format!(
                r#"stoa_guardrails_evaluations_total{{deployment_mode="{deployment_mode}",guardrail="{guardrail}",surface="{surface}"}}"#
            );
            assert_counter_series_present(&body, &series);
            for decision in GUARDRAILS_FULL_DECISIONS {
                let series = format!(
                    r#"stoa_guardrails_decisions_total{{decision="{decision}",deployment_mode="{deployment_mode}",guardrail="{guardrail}",surface="{surface}"}}"#
                );
                assert_counter_series_present(&body, &series);
            }
        }
    }
}

fn assert_counter_series_present(body: &str, expected_series: &str) {
    let value = body.lines().find_map(|line| {
        line.strip_prefix(expected_series)
            .and_then(|suffix| suffix.strip_prefix(' '))
            .and_then(|suffix| suffix.split_whitespace().next())
            .and_then(|value| value.parse::<f64>().ok())
    });

    assert!(
        matches!(value, Some(value) if value >= 0.0),
        "/metrics scrape missing guardrail counter series `{expected_series}`"
    );
}

// ========================================================================
// Admin API — Bearer token auth
// ========================================================================

#[tokio::test]
async fn test_admin_no_token_configured_returns_503() {
    // Config without admin_api_token → admin API disabled → 503
    let app = TestApp::new();
    let (status, _body) = app.get_with_bearer("/admin/health", "any-token").await;
    assert_eq!(status, StatusCode::SERVICE_UNAVAILABLE);
}

#[tokio::test]
async fn test_admin_wrong_token_returns_401() {
    let config = config_with_admin_token("correct-token");
    let app = TestApp::with_config(config);
    let (status, _body) = app.get_with_bearer("/admin/health", "wrong-token").await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn test_admin_missing_header_returns_401() {
    let config = config_with_admin_token("correct-token");
    let app = TestApp::with_config(config);
    // GET without Authorization header
    let (status, _body) = app.get("/admin/health").await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn test_admin_valid_token_returns_200() {
    let config = config_with_admin_token("test-admin-token");
    let app = TestApp::with_config(config);
    let (status, body) = app
        .get_with_bearer("/admin/health", "test-admin-token")
        .await;
    assert_eq!(status, StatusCode::OK);
    // Admin health returns JSON
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert_eq!(json["status"], "ok");
    assert!(json["version"].is_string());
}

#[tokio::test]
async fn test_admin_list_apis_empty() {
    let config = config_with_admin_token("test-admin-token");
    let app = TestApp::with_config(config);
    let (status, body) = app.get_with_bearer("/admin/apis", "test-admin-token").await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert!(json.as_array().expect("array").is_empty());
}

#[tokio::test]
async fn test_admin_list_policies_empty() {
    let config = config_with_admin_token("test-admin-token");
    let app = TestApp::with_config(config);
    let (status, body) = app
        .get_with_bearer("/admin/policies", "test-admin-token")
        .await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert!(json.as_array().expect("array").is_empty());
}

#[tokio::test]
async fn test_admin_cache_stats() {
    let config = config_with_admin_token("test-admin-token");
    let app = TestApp::with_config(config);
    let (status, body) = app
        .get_with_bearer("/admin/cache/stats", "test-admin-token")
        .await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert_eq!(json["hits"], 0);
    assert_eq!(json["misses"], 0);
}

fn gateway_command(
    dir: &Path,
    admin: &str,
    standalone: bool,
    cp_url: Option<&str>,
) -> (Command, String) {
    let listener = std::net::TcpListener::bind((std::net::Ipv4Addr::LOCALHOST, 0)).unwrap();
    let addr = listener.local_addr().unwrap();
    drop(listener);

    let mut command = Command::new(env!("CARGO_BIN_EXE_stoa-gateway"));
    command
        .env_clear()
        .current_dir(dir)
        .kill_on_drop(true)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .env("STOA_HOST", addr.ip().to_string())
        .env("STOA_PORT", addr.port().to_string())
        .env("STOA_GATEWAY_MODE", "edge-mcp")
        .env("STOA_ENVIRONMENT", "dev")
        .env("STOA_STANDALONE", standalone.to_string())
        .env("STOA_ADMIN_API_TOKEN", admin)
        .env("STOA_AUDIT_SPOOL_DIR", dir.join("audit"))
        .env("STOA_CONTRACT_STATE_PATH", dir.join("contracts.json"))
        .env("STOA_AUTO_REGISTER", "true")
        .env(
            "STOA_CONTROL_PLANE_API_KEY",
            uuid::Uuid::new_v4().to_string(),
        )
        .env("STOA_HEARTBEAT_INTERVAL_SECS", "1")
        .env("STOA_NATIVE_TOOLS_ENABLED", "false")
        .env("STOA_ROUTE_RELOAD_ENABLED", "true")
        .env("STOA_ROUTE_RELOAD_INTERVAL_SECS", "1")
        .env("STOA_QUOTA_ENFORCEMENT_ENABLED", "true")
        .env("STOA_LLM_PROXY_ENABLED", "true");
    if let Some(url) = cp_url {
        command.env("STOA_CONTROL_PLANE_URL", url);
    }
    (command, format!("http://{addr}"))
}

async fn start_gateway(command: &mut Command, client: &reqwest::Client, base: &str) -> Child {
    let mut child = command.spawn().unwrap();
    tokio::time::timeout(Duration::from_secs(15), async {
        loop {
            assert!(
                child.try_wait().unwrap().is_none(),
                "Gateway exited during startup"
            );
            if client
                .get(format!("{base}/health"))
                .send()
                .await
                .is_ok_and(|r| r.status().is_success())
            {
                break;
            }
            tokio::time::sleep(Duration::from_millis(25)).await;
        }
    })
    .await
    .expect("Gateway startup timed out");
    child
}

async fn assert_startup_rejected(mut command: Command, message: &str) {
    command.stderr(Stdio::piped());
    let output = tokio::time::timeout(Duration::from_secs(10), command.output())
        .await
        .expect("Gateway did not exit")
        .unwrap();
    assert!(!output.status.success());
    assert!(
        String::from_utf8_lossy(&output.stderr).contains(message),
        "Expected startup diagnostic"
    );
}

async fn assert_fresh_contract_window(client: &reqwest::Client, base: &str, bearer: &str) {
    for remaining in (0..5).rev() {
        let response = client
            .get(format!("{base}{CONTRACT_ROUTE}/items"))
            .bearer_auth(bearer)
            .send()
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(response.headers()["x-ratelimit-limit"], "5");
        assert_eq!(
            response.headers()["x-ratelimit-remaining"]
                .to_str()
                .unwrap(),
            remaining.to_string()
        );
    }
    let response = client
        .get(format!("{base}{CONTRACT_ROUTE}/groups"))
        .bearer_auth(bearer)
        .send()
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::TOO_MANY_REQUESTS);
}

#[tokio::test]
async fn standalone_flag_restores_contract_and_cap_on_restart_with_fresh_counters() {
    let dir = tempfile::tempdir().unwrap();
    let oidc = jwt::oidc_server().await;
    let oidc_config = jwt::config(&oidc);
    let upstream = MockServer::start().await;
    Mock::given(method("GET"))
        .respond_with(ResponseTemplate::new(200))
        .mount(&upstream)
        .await;
    let admin = uuid::Uuid::new_v4().to_string();
    let reader = jwt::token_with(json!({"azp": "reader"}));
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(3))
        .build()
        .unwrap();

    let start = |cp_url| {
        let (mut command, base) = gateway_command(dir.path(), &admin, true, cp_url);
        command
            .env(
                "STOA_KEYCLOAK_URL",
                oidc_config.keycloak_url.as_deref().unwrap(),
            )
            .env(
                "STOA_KEYCLOAK_INTERNAL_URL",
                oidc_config.keycloak_internal_url.as_deref().unwrap(),
            )
            .env(
                "STOA_MCP_AUDIENCE",
                oidc_config.mcp_audience.as_deref().unwrap(),
            );
        (command, base)
    };

    let (mut command, base) = start(None);
    let mut child = start_gateway(&mut command, &client, &base).await;
    assert_eq!(
        client
            .get(format!("{base}/ready"))
            .send()
            .await
            .unwrap()
            .status(),
        StatusCode::OK
    );
    let health = client
        .get(format!("{base}/admin/health"))
        .bearer_auth(&admin)
        .send()
        .await
        .unwrap()
        .error_for_status()
        .unwrap()
        .json::<Value>()
        .await
        .unwrap();
    assert_eq!(health["contracts_count"], 0);
    let list = client
        .get(format!("{base}/admin/contracts"))
        .bearer_auth(&admin)
        .send()
        .await
        .unwrap()
        .error_for_status()
        .unwrap()
        .json::<Value>()
        .await
        .unwrap();
    assert_eq!(list, json!([]));
    assert_eq!(
        client
            .get(format!("{base}{CONTRACT_ROUTE}/items"))
            .send()
            .await
            .unwrap()
            .status(),
        StatusCode::NOT_FOUND
    );
    let reload = client
        .post(format!("{base}/admin/routes/reload"))
        .bearer_auth(&admin)
        .send()
        .await
        .unwrap();
    assert_eq!(reload.status(), StatusCode::CONFLICT);
    assert_eq!(
        reload.json::<Value>().await.unwrap()["message"],
        "Remote route reload is disabled in standalone mode"
    );
    let validation = client
        .post(format!("{base}/v1/messages"))
        .header("x-api-key", uuid::Uuid::new_v4().to_string())
        .send()
        .await
        .unwrap();
    assert_eq!(validation.status(), StatusCode::UNAUTHORIZED);

    let contract = quota_contract(&upstream.uri());
    assert_eq!(
        client
            .post(format!("{base}/admin/contracts"))
            .bearer_auth(&admin)
            .json(&contract)
            .send()
            .await
            .unwrap()
            .status(),
        StatusCode::CREATED
    );
    assert_fresh_contract_window(&client, &base, &reader).await;
    child.kill().await.unwrap();

    let (mut command, base) = start(Some("   "));
    let mut child = start_gateway(&mut command, &client, &base).await;
    let restored = client
        .get(format!("{base}{CONTRACT_ADMIN_ROUTE}"))
        .bearer_auth(&admin)
        .send()
        .await
        .unwrap()
        .error_for_status()
        .unwrap()
        .json::<Value>()
        .await
        .unwrap();
    assert_eq!(restored["policies"], contract["policies"]);
    assert_fresh_contract_window(&client, &base, &reader).await;
    assert_eq!(upstream.received_requests().await.unwrap().len(), 10);
    assert_eq!(
        client
            .delete(format!("{base}{CONTRACT_ADMIN_ROUTE}"))
            .bearer_auth(&admin)
            .send()
            .await
            .unwrap()
            .status(),
        StatusCode::OK
    );
    child.kill().await.unwrap();

    let (mut command, base) = start(None);
    let _child = start_gateway(&mut command, &client, &base).await;
    assert_eq!(
        client
            .get(format!("{base}{CONTRACT_ADMIN_ROUTE}"))
            .bearer_auth(&admin)
            .send()
            .await
            .unwrap()
            .status(),
        StatusCode::NOT_FOUND
    );
    assert_eq!(
        client
            .get(format!("{base}{CONTRACT_ROUTE}/items"))
            .bearer_auth(&reader)
            .send()
            .await
            .unwrap()
            .status(),
        StatusCode::NOT_FOUND
    );
}

#[tokio::test]
async fn standalone_rejects_control_plane_url_and_connected_mode_reaches_control_plane() {
    const REGISTER: &str = "/v1/internal/gateways/register";
    const VALIDATE: &str = "/v1/subscriptions/validate-key";
    const ROUTES: &str = "/v1/internal/gateways/routes";
    let dir = tempfile::tempdir().unwrap();
    let control = MockServer::start().await;
    let id = uuid::Uuid::new_v4();
    let heartbeat = format!("/v1/internal/gateways/{id}/heartbeat");
    Mock::given(method("POST"))
        .and(path(REGISTER))
        .respond_with(
            ResponseTemplate::new(200)
                .set_body_json(json!({"id": id, "name": "gateway", "status": "active"})),
        )
        .mount(&control)
        .await;
    Mock::given(method("POST"))
        .and(path(heartbeat.as_str()))
        .respond_with(ResponseTemplate::new(200))
        .mount(&control)
        .await;
    Mock::given(method("POST"))
        .and(path(VALIDATE))
        .respond_with(ResponseTemplate::new(401))
        .mount(&control)
        .await;
    Mock::given(method("GET"))
        .and(path(ROUTES))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!([])))
        .mount(&control)
        .await;

    let admin = uuid::Uuid::new_v4().to_string();
    let url = control.uri();
    let (command, _) = gateway_command(dir.path(), &admin, true, Some(&url));
    assert_startup_rejected(
        command,
        "STOA_STANDALONE=true requires STOA_CONTROL_PLANE_URL to be unset or blank",
    )
    .await;
    let runtime_config = stoa_gateway::config::Config {
        standalone: true,
        control_plane_url: Some(url.clone()),
        ..Default::default()
    };
    let state = stoa_gateway::state::AppState::new(runtime_config);
    assert!(matches!(
        state
            .api_key_validator
            .validate(&uuid::Uuid::new_v4().to_string())
            .await,
        Err(stoa_gateway::auth::api_key::ApiKeyError::ConfigError(_))
    ));
    let reload = stoa_gateway::handlers::admin::reload_routes_from_cp(&state)
        .await
        .unwrap_err();
    assert_eq!(
        reload.to_string(),
        "Remote route reload is disabled in standalone mode"
    );
    assert!(control.received_requests().await.unwrap().is_empty());

    let (mut command, base) = gateway_command(dir.path(), &admin, false, Some(&url));
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(3))
        .build()
        .unwrap();
    let _child = start_gateway(&mut command, &client, &base).await;
    let validation = client
        .post(format!("{base}/v1/messages"))
        .header("x-api-key", uuid::Uuid::new_v4().to_string())
        .send()
        .await
        .unwrap();
    assert_eq!(validation.status(), StatusCode::UNAUTHORIZED);
    let reload = client
        .post(format!("{base}/admin/routes/reload"))
        .bearer_auth(&admin)
        .send()
        .await
        .unwrap();
    assert_eq!(reload.status(), StatusCode::OK);

    tokio::time::timeout(Duration::from_secs(5), async {
        loop {
            let requests = control.received_requests().await.unwrap();
            if [REGISTER, heartbeat.as_str(), VALIDATE, ROUTES]
                .into_iter()
                .all(|path| requests.iter().any(|request| request.url.path() == path))
            {
                break;
            }
            tokio::time::sleep(Duration::from_millis(25)).await;
        }
    })
    .await
    .expect("Expected control plane requests in connected mode");
}

#[tokio::test]
async fn standalone_rejects_unreadable_and_invalid_contract_snapshots() {
    let dir = tempfile::tempdir().unwrap();
    let snapshot = dir.path().join("contracts.json");
    let admin = uuid::Uuid::new_v4().to_string();
    std::fs::create_dir(&snapshot).unwrap();
    let (command, _) = gateway_command(dir.path(), &admin, true, None);
    assert_startup_rejected(command, "Could not restore contract snapshot").await;
    std::fs::remove_dir(&snapshot).unwrap();
    std::fs::write(&snapshot, "[").unwrap();
    let (command, _) = gateway_command(dir.path(), &admin, true, None);
    assert_startup_rejected(command, "Could not restore contract snapshot").await;

    let mut contract = quota_contract("http://example.com");
    contract["policies"][0]["config"]["consumers"][0]["rate_limit_per_minute"] = json!(0);
    std::fs::write(&snapshot, json!([contract]).to_string()).unwrap();
    let (command, _) = gateway_command(dir.path(), &admin, true, None);
    assert_startup_rejected(command, "invalid contract in snapshot").await;
}
