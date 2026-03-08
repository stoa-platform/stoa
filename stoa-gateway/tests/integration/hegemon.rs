//! Integration tests for HEGEMON features (dispatch, budget, security profile).
//!
//! Verifies handlers through the full Axum router via TestApp (oneshot).
//! Covers: PR #1551 (budget) and PR #1552 (dispatch status, profile enforcement).

use axum::http::StatusCode;

use stoa_gateway::config::Config;

use super::common::{config_with_hegemon, TestApp};

// =============================================================================
// Dispatch status (GET /hegemon/dispatch/:id) — PR #1552
// =============================================================================

#[tokio::test]
async fn dispatch_status_found() {
    let app = TestApp::with_config(config_with_hegemon());

    // Create a dispatch first via POST /hegemon/dispatch
    let (status, body) = app
        .post_json(
            "/hegemon/dispatch",
            r#"{"ticket_id":"CAB-9999","title":"Test dispatch","instance_label":"w1"}"#,
        )
        .await;
    assert_eq!(status, StatusCode::ACCEPTED, "dispatch create: {body}");

    let resp: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    let dispatch_id = resp["dispatch_id"].as_str().expect("dispatch_id present");

    // Now query status
    let (status, body) = app.get(&format!("/hegemon/dispatch/{dispatch_id}")).await;
    assert_eq!(status, StatusCode::OK, "dispatch status: {body}");

    let status_resp: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert_eq!(status_resp["ticket_id"], "CAB-9999");
    // Dispatch transitions to "in_progress" once stored in tracker
    assert_eq!(status_resp["status"], "in_progress");
}

#[tokio::test]
async fn dispatch_status_not_found() {
    let app = TestApp::with_config(config_with_hegemon());

    let (status, body) = app.get("/hegemon/dispatch/heg-nonexistent").await;
    assert_eq!(status, StatusCode::NOT_FOUND, "body: {body}");

    let resp: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert_eq!(resp["error"], "dispatch_not_found");
}

#[tokio::test]
async fn dispatch_status_hegemon_disabled() {
    // Default config has hegemon_enabled = false
    let app = TestApp::new();

    let (status, body) = app.get("/hegemon/dispatch/heg-any").await;
    assert_eq!(status, StatusCode::SERVICE_UNAVAILABLE, "body: {body}");

    let resp: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert_eq!(resp["error"], "hegemon_disabled");
}

// =============================================================================
// Budget check (POST /hegemon/budget/check) — PR #1551
// =============================================================================

#[tokio::test]
async fn budget_check_endpoint() {
    let app = TestApp::with_config(config_with_hegemon());

    let (status, body) = app
        .post_json(
            "/hegemon/budget/check",
            r#"{"worker_name":"w1","estimated_cost_usd":5.0}"#,
        )
        .await;
    assert_eq!(status, StatusCode::OK, "budget check: {body}");

    let resp: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert_eq!(resp["allowed"], true);
    assert!(resp["remaining_usd"].as_f64().is_some());
    assert!(resp["daily_spent_usd"].as_f64().is_some());
    assert!(resp["daily_limit_usd"].as_f64().is_some());
    assert_eq!(resp["warning"], false);
}

#[tokio::test]
async fn budget_check_warns_near_limit() {
    let config = Config {
        hegemon_enabled: true,
        hegemon_budget_daily_usd: 10.0,
        hegemon_budget_warn_pct: 0.8,
        auto_register: false,
        ..Config::default()
    };
    let app = TestApp::with_config(config);

    // Record $9 spend first to trigger warning
    let (status, _) = app
        .post_json(
            "/hegemon/budget/record",
            r#"{"worker_name":"w1","amount_usd":9.0,"dispatch_id":"heg-test-1"}"#,
        )
        .await;
    assert_eq!(status, StatusCode::OK);

    // Now check — should see warning
    let (status, body) = app
        .post_json(
            "/hegemon/budget/check",
            r#"{"worker_name":"w1","estimated_cost_usd":0.5}"#,
        )
        .await;
    assert_eq!(status, StatusCode::OK, "budget check: {body}");

    let resp: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert_eq!(resp["warning"], true);
    assert!(resp["warning_message"].as_str().is_some());
}

// =============================================================================
// Budget record (POST /hegemon/budget/record) — PR #1551
// =============================================================================

#[tokio::test]
async fn budget_record_endpoint() {
    let app = TestApp::with_config(config_with_hegemon());

    let (status, body) = app
        .post_json(
            "/hegemon/budget/record",
            r#"{"worker_name":"w1","amount_usd":2.5,"dispatch_id":"heg-test-1"}"#,
        )
        .await;
    assert_eq!(status, StatusCode::OK, "budget record: {body}");

    let resp: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert_eq!(resp["recorded"], true);
    assert!(resp["daily_spent_usd"].as_f64().unwrap() >= 2.5);
    assert!(resp["remaining_usd"].as_f64().is_some());
}

#[tokio::test]
async fn budget_record_rejects_negative_amount() {
    let app = TestApp::with_config(config_with_hegemon());

    let (status, body) = app
        .post_json(
            "/hegemon/budget/record",
            r#"{"worker_name":"w1","amount_usd":-1.0,"dispatch_id":"heg-neg"}"#,
        )
        .await;
    assert_eq!(status, StatusCode::BAD_REQUEST, "body: {body}");

    let resp: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
    assert_eq!(resp["error"], "invalid_amount");
}

#[tokio::test]
async fn budget_endpoints_hegemon_disabled() {
    let app = TestApp::new(); // hegemon_enabled = false

    let (status, _) = app
        .post_json("/hegemon/budget/check", r#"{"worker_name":"w1"}"#)
        .await;
    assert_eq!(status, StatusCode::SERVICE_UNAVAILABLE);

    let (status, _) = app
        .post_json(
            "/hegemon/budget/record",
            r#"{"worker_name":"w1","amount_usd":1.0,"dispatch_id":"x"}"#,
        )
        .await;
    assert_eq!(status, StatusCode::SERVICE_UNAVAILABLE);
}
