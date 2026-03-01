//! LLM proxy integration tests.
//!
//! Tests the full LLM cost-aware routing flow:
//! - Admin LLM status / providers / costs endpoints
//! - Cost calculator + budget gate wiring
//! - Router strategy selection

use axum::http::StatusCode;

use stoa_gateway::config::{Config, LlmRouterConfig};
use stoa_gateway::llm::providers::{LlmProvider, ProviderConfig};
use stoa_gateway::llm::RoutingStrategy;

use crate::common::{config_with_admin_token, TestApp};

/// Create a config with admin token + LLM router enabled (2 test providers).
fn config_with_llm_router() -> Config {
    Config {
        admin_api_token: Some("test-admin-token".to_string()),
        auto_register: false,
        llm_router: LlmRouterConfig {
            enabled: true,
            default_strategy: RoutingStrategy::LowestCost,
            budget_limit_usd: 100.0,
            providers: vec![
                ProviderConfig {
                    provider: LlmProvider::Anthropic,
                    backend_id: None,
                    base_url: "https://api.anthropic.com/v1".to_string(),
                    api_key_env: None,
                    default_model: Some("claude-sonnet-4-20250514".to_string()),
                    max_concurrent: 50,
                    enabled: true,
                    cost_per_1m_input: 3.0,
                    cost_per_1m_output: 15.0,
                    cost_per_1m_cache_read: 0.3,
                    cost_per_1m_cache_write: 3.75,
                    priority: 1,
                    deployment: None,
                    api_version: None,
                },
                ProviderConfig {
                    provider: LlmProvider::OpenAi,
                    backend_id: None,
                    base_url: "https://api.openai.com/v1".to_string(),
                    api_key_env: None,
                    default_model: Some("gpt-4o".to_string()),
                    max_concurrent: 50,
                    enabled: true,
                    cost_per_1m_input: 2.5,
                    cost_per_1m_output: 10.0,
                    cost_per_1m_cache_read: 0.0,
                    cost_per_1m_cache_write: 0.0,
                    priority: 2,
                    deployment: None,
                    api_version: None,
                },
            ],
            ..Default::default()
        },
        ..Config::default()
    }
}

// ========================================================================
// Admin LLM Status — GET /admin/llm/status
// ========================================================================

#[tokio::test]
async fn test_llm_status_disabled_by_default() {
    let config = config_with_admin_token("test-admin-token");
    let app = TestApp::with_config(config);
    let (status, body) = app
        .get_with_bearer("/admin/llm/status", "test-admin-token")
        .await;
    assert_eq!(status, StatusCode::OK);
    assert!(body.contains("\"enabled\":false"));
    assert!(body.contains("\"provider_count\":0"));
}

#[tokio::test]
async fn test_llm_status_enabled_with_providers() {
    let config = config_with_llm_router();
    let app = TestApp::with_config(config);
    let (status, body) = app
        .get_with_bearer("/admin/llm/status", "test-admin-token")
        .await;
    assert_eq!(status, StatusCode::OK);
    assert!(body.contains("\"enabled\":true"));
    assert!(body.contains("\"provider_count\":2"));
    assert!(body.contains("\"routing_strategy\":\"LowestCost\""));
}

#[tokio::test]
async fn test_llm_status_requires_auth() {
    let config = config_with_llm_router();
    let app = TestApp::with_config(config);
    let (status, _body) = app.get("/admin/llm/status").await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
}

// ========================================================================
// Admin LLM Providers — GET /admin/llm/providers
// ========================================================================

#[tokio::test]
async fn test_llm_providers_returns_list() {
    let config = config_with_llm_router();
    let app = TestApp::with_config(config);
    let (status, body) = app
        .get_with_bearer("/admin/llm/providers", "test-admin-token")
        .await;
    assert_eq!(status, StatusCode::OK);
    // Should contain both providers with pricing metadata
    assert!(body.contains("\"provider\":\"anthropic\""));
    assert!(body.contains("\"provider\":\"openai\""));
    assert!(body.contains("\"cost_per_1m_input\":3.0"));
    assert!(body.contains("\"cost_per_1m_input\":2.5"));
}

#[tokio::test]
async fn test_llm_providers_empty_when_disabled() {
    let config = config_with_admin_token("test-admin-token");
    let app = TestApp::with_config(config);
    let (status, body) = app
        .get_with_bearer("/admin/llm/providers", "test-admin-token")
        .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body, "[]");
}

// ========================================================================
// Admin LLM Costs — GET /admin/llm/costs
// ========================================================================

#[tokio::test]
async fn test_llm_costs_tracking_disabled_without_router() {
    let config = config_with_admin_token("test-admin-token");
    let app = TestApp::with_config(config);
    let (status, body) = app
        .get_with_bearer("/admin/llm/costs", "test-admin-token")
        .await;
    assert_eq!(status, StatusCode::OK);
    assert!(body.contains("\"cost_tracking_enabled\":false"));
}

#[tokio::test]
async fn test_llm_costs_tracking_enabled_with_router() {
    let config = config_with_llm_router();
    let app = TestApp::with_config(config);
    let (status, body) = app
        .get_with_bearer("/admin/llm/costs", "test-admin-token")
        .await;
    assert_eq!(status, StatusCode::OK);
    assert!(body.contains("\"cost_tracking_enabled\":true"));
    // No requests yet, so metrics array should be empty
    assert!(body.contains("\"metrics\":[]"));
}

// ========================================================================
// Auth enforcement on LLM admin endpoints
// ========================================================================

#[tokio::test]
async fn test_llm_providers_requires_auth() {
    let config = config_with_llm_router();
    let app = TestApp::with_config(config);
    let (status, _body) = app.get("/admin/llm/providers").await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn test_llm_costs_requires_auth() {
    let config = config_with_llm_router();
    let app = TestApp::with_config(config);
    let (status, _body) = app.get("/admin/llm/costs").await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn test_llm_status_wrong_token_returns_401() {
    let config = config_with_llm_router();
    let app = TestApp::with_config(config);
    let (status, _body) = app
        .get_with_bearer("/admin/llm/status", "wrong-token")
        .await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
}
