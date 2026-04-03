//! PII Filter Plugin — Detect and redact/block PII in request/response bodies
//!
//! Wraps the existing `guardrails::PiiScanner` as a plugin SDK builtin.
//! Configurable per-tenant: choose redact mode (replace PII with `[REDACTED]`)
//! or block mode (reject the request entirely).
//!
//! CAB-1936 Phase 3.

use async_trait::async_trait;
use axum::http::StatusCode;
use serde_json::Value;
use tracing::warn;

use super::super::sdk::{Phase, Plugin, PluginContext, PluginMetadata, PluginResult};
use crate::guardrails::PiiScanner;

/// Config key for mode: "redact" (default) or "block".
const MODE_KEY: &str = "mode";

/// Block mode value.
const MODE_BLOCK: &str = "block";

pub struct PiiFilterPlugin;

impl PiiFilterPlugin {
    pub fn new() -> Self {
        Self
    }

    fn is_block_mode(config: &Value) -> bool {
        config
            .get(MODE_KEY)
            .and_then(|v| v.as_str())
            .map(|s| s == MODE_BLOCK)
            .unwrap_or(false)
    }

    fn scan_and_act(text: &str, config: &Value, tenant_id: &str, phase: Phase) -> ScanAction {
        let (pii_found, redacted) = PiiScanner::redact_text(text);
        if !pii_found {
            return ScanAction::Clean;
        }

        warn!(
            plugin = "pii-filter",
            tenant = %tenant_id,
            phase = %phase,
            "PII detected in body"
        );

        if Self::is_block_mode(config) {
            ScanAction::Block
        } else {
            ScanAction::Redacted(redacted)
        }
    }
}

enum ScanAction {
    Clean,
    Redacted(String),
    Block,
}

impl Default for PiiFilterPlugin {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl Plugin for PiiFilterPlugin {
    fn metadata(&self) -> PluginMetadata {
        PluginMetadata {
            name: "pii-filter".to_string(),
            version: "1.0.0".to_string(),
            description: "Detects and redacts/blocks PII in request and response bodies"
                .to_string(),
            phases: vec![Phase::PreUpstream, Phase::PostUpstream],
        }
    }

    async fn execute(&self, phase: Phase, ctx: &mut PluginContext) -> PluginResult {
        match phase {
            Phase::PreUpstream => {
                let body = match ctx.get_request_body_str() {
                    Some(b) if !b.is_empty() => b,
                    _ => return PluginResult::Continue,
                };

                match Self::scan_and_act(body, &ctx.config, &ctx.tenant_id, phase) {
                    ScanAction::Clean => PluginResult::Continue,
                    ScanAction::Redacted(redacted) => {
                        ctx.set_request_body(&redacted);
                        ctx.set_request_header("x-stoa-pii-redacted", "true");
                        PluginResult::Continue
                    }
                    ScanAction::Block => PluginResult::Terminate {
                        status: StatusCode::UNPROCESSABLE_ENTITY,
                        body: "Request blocked: PII detected in request body".to_string(),
                    },
                }
            }
            Phase::PostUpstream => {
                let body = match ctx.get_response_body_str() {
                    Some(b) if !b.is_empty() => b,
                    _ => return PluginResult::Continue,
                };

                match Self::scan_and_act(body, &ctx.config, &ctx.tenant_id, phase) {
                    ScanAction::Clean => PluginResult::Continue,
                    ScanAction::Redacted(redacted) => {
                        ctx.set_response_body(&redacted);
                        ctx.set_response_header("x-stoa-pii-redacted", "true");
                        PluginResult::Continue
                    }
                    ScanAction::Block => PluginResult::Terminate {
                        status: StatusCode::UNPROCESSABLE_ENTITY,
                        body: "Response blocked: PII detected in response body".to_string(),
                    },
                }
            }
            _ => PluginResult::Continue,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::HeaderMap;
    use serde_json::json;

    fn make_ctx(phase: Phase, config: Value) -> PluginContext {
        let mut ctx = PluginContext::new(
            phase,
            "test-tenant".to_string(),
            "/api/test".to_string(),
            "POST".to_string(),
            HeaderMap::new(),
        );
        ctx.config = config;
        ctx
    }

    // --- PreUpstream tests ---

    #[tokio::test]
    async fn test_clean_request_passes() {
        let plugin = PiiFilterPlugin::new();
        let mut ctx = make_ctx(Phase::PreUpstream, json!({}));
        ctx.request_body = Some(b"hello world".to_vec());

        let result = plugin.execute(Phase::PreUpstream, &mut ctx).await;
        assert!(matches!(result, PluginResult::Continue));
        assert!(ctx.get_request_header("x-stoa-pii-redacted").is_none());
    }

    #[tokio::test]
    async fn test_pii_redacted_in_request() {
        let plugin = PiiFilterPlugin::new();
        let mut ctx = make_ctx(Phase::PreUpstream, json!({"mode": "redact"}));
        ctx.request_body = Some(b"contact john@example.com please".to_vec());

        let result = plugin.execute(Phase::PreUpstream, &mut ctx).await;
        assert!(matches!(result, PluginResult::Continue));

        let body = ctx.get_request_body_str().unwrap();
        assert!(body.contains("[REDACTED]"));
        assert!(!body.contains("john@example.com"));
        assert_eq!(ctx.get_request_header("x-stoa-pii-redacted"), Some("true"));
    }

    #[tokio::test]
    async fn test_pii_blocked_in_request() {
        let plugin = PiiFilterPlugin::new();
        let mut ctx = make_ctx(Phase::PreUpstream, json!({"mode": "block"}));
        ctx.request_body = Some(b"my email is john@example.com".to_vec());

        let result = plugin.execute(Phase::PreUpstream, &mut ctx).await;
        match result {
            PluginResult::Terminate { status, body } => {
                assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
                assert!(body.contains("PII detected"));
            }
            _ => panic!("expected Terminate"),
        }
    }

    #[tokio::test]
    async fn test_no_body_passes() {
        let plugin = PiiFilterPlugin::new();
        let mut ctx = make_ctx(Phase::PreUpstream, json!({"mode": "block"}));
        // request_body is None

        let result = plugin.execute(Phase::PreUpstream, &mut ctx).await;
        assert!(matches!(result, PluginResult::Continue));
    }

    #[tokio::test]
    async fn test_empty_body_passes() {
        let plugin = PiiFilterPlugin::new();
        let mut ctx = make_ctx(Phase::PreUpstream, json!({}));
        ctx.request_body = Some(Vec::new());

        let result = plugin.execute(Phase::PreUpstream, &mut ctx).await;
        assert!(matches!(result, PluginResult::Continue));
    }

    #[tokio::test]
    async fn test_default_mode_is_redact() {
        let plugin = PiiFilterPlugin::new();
        let mut ctx = make_ctx(Phase::PreUpstream, json!({}));
        ctx.request_body = Some(b"SSN is 123-45-6789".to_vec());

        let result = plugin.execute(Phase::PreUpstream, &mut ctx).await;
        assert!(matches!(result, PluginResult::Continue));

        let body = ctx.get_request_body_str().unwrap();
        assert!(body.contains("[REDACTED]"));
    }

    // --- PostUpstream tests ---

    #[tokio::test]
    async fn test_pii_redacted_in_response() {
        let plugin = PiiFilterPlugin::new();
        let mut ctx = make_ctx(Phase::PostUpstream, json!({"mode": "redact"}));
        ctx.response_body = Some(b"result: call +1 (555) 123-4567".to_vec());

        let result = plugin.execute(Phase::PostUpstream, &mut ctx).await;
        assert!(matches!(result, PluginResult::Continue));

        let body = ctx.get_response_body_str().unwrap();
        assert!(body.contains("[REDACTED]"));
        assert_eq!(
            ctx.response_headers.get("x-stoa-pii-redacted").unwrap(),
            "true"
        );
    }

    #[tokio::test]
    async fn test_pii_blocked_in_response() {
        let plugin = PiiFilterPlugin::new();
        let mut ctx = make_ctx(Phase::PostUpstream, json!({"mode": "block"}));
        ctx.response_body = Some(b"card 4111111111111111 charged".to_vec());

        let result = plugin.execute(Phase::PostUpstream, &mut ctx).await;
        match result {
            PluginResult::Terminate { status, body } => {
                assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
                assert!(body.contains("response body"));
            }
            _ => panic!("expected Terminate"),
        }
    }

    // --- IBAN detection ---

    #[tokio::test]
    async fn test_iban_detected_and_redacted() {
        let plugin = PiiFilterPlugin::new();
        let mut ctx = make_ctx(Phase::PreUpstream, json!({}));
        ctx.request_body = Some(b"wire to DE89370400440532013000".to_vec());

        let result = plugin.execute(Phase::PreUpstream, &mut ctx).await;
        assert!(matches!(result, PluginResult::Continue));

        let body = ctx.get_request_body_str().unwrap();
        assert!(body.contains("[REDACTED]"));
        assert!(!body.contains("DE89370400440532013000"));
    }

    // --- Unrelated phase ---

    #[tokio::test]
    async fn test_unrelated_phase_passes() {
        let plugin = PiiFilterPlugin::new();
        let mut ctx = make_ctx(Phase::PreAuth, json!({"mode": "block"}));
        ctx.request_body = Some(b"john@example.com".to_vec());

        let result = plugin.execute(Phase::PreAuth, &mut ctx).await;
        assert!(matches!(result, PluginResult::Continue));
    }

    // --- Metadata ---

    #[test]
    fn test_metadata() {
        let plugin = PiiFilterPlugin::new();
        let meta = plugin.metadata();
        assert_eq!(meta.name, "pii-filter");
        assert!(meta.phases.contains(&Phase::PreUpstream));
        assert!(meta.phases.contains(&Phase::PostUpstream));
    }
}
