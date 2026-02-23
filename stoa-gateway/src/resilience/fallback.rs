//! Fallback Chain — Ordered provider failover for tool execution
//!
//! When a tool execution fails, the fallback chain tries alternate providers
//! in order, skipping providers with open circuit breakers.
//!
//! # Configuration
//!
//! ```text
//! STOA_FALLBACK_ENABLED=true
//! STOA_FALLBACK_CHAINS='{"tool_a":["tool_a_v2","tool_a_readonly"]}'
//! STOA_FALLBACK_TIMEOUT_MS=5000
//! ```

use serde_json::Value;
use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;
use tracing::{info, warn};

use crate::mcp::tools::{ToolContext, ToolError, ToolRegistry, ToolResult};
use crate::metrics;
use crate::resilience::CircuitBreakerRegistry;

/// Parsed fallback chain configuration
#[derive(Clone)]
pub struct FallbackChain {
    chains: HashMap<String, Vec<String>>,
    timeout: Duration,
    enabled: bool,
}

impl FallbackChain {
    /// Create a new FallbackChain from JSON config and timeout.
    pub fn new(enabled: bool, chains_json: Option<&str>, timeout_ms: u64) -> Self {
        let chains: HashMap<String, Vec<String>> = if enabled {
            chains_json
                .and_then(|s| {
                    serde_json::from_str(s)
                        .map_err(|e| {
                            warn!(error = %e, "Failed to parse STOA_FALLBACK_CHAINS JSON");
                            e
                        })
                        .ok()
                })
                .unwrap_or_default()
        } else {
            HashMap::new()
        };

        if enabled && !chains.is_empty() {
            info!(
                chain_count = chains.len(),
                timeout_ms, "Fallback chains configured"
            );
        }

        Self {
            chains,
            timeout: Duration::from_millis(timeout_ms),
            enabled,
        }
    }

    /// Check if fallback is enabled and this tool has a fallback chain.
    pub fn has_fallbacks(&self, tool_name: &str) -> bool {
        self.enabled && self.chains.get(tool_name).is_some_and(|c| !c.is_empty())
    }

    /// Get the timeout for fallback attempts.
    pub fn timeout(&self) -> Duration {
        self.timeout
    }
}

/// Execute a tool with fallback chain support.
///
/// If the primary tool fails and has configured fallbacks, tries each alternate
/// provider in order, skipping those with open circuit breakers.
/// Returns the first successful result or the last error if all providers fail.
pub async fn execute_or_direct(
    fallback_chain: &FallbackChain,
    circuit_breakers: &Arc<CircuitBreakerRegistry>,
    tool_registry: &Arc<ToolRegistry>,
    tool_name: &str,
    arguments: Value,
    ctx: &ToolContext,
    primary_result: Result<ToolResult, ToolError>,
) -> Result<ToolResult, ToolError> {
    // Fast path: if primary succeeded or no fallbacks configured, return as-is
    if primary_result.is_ok() || !fallback_chain.has_fallbacks(tool_name) {
        return primary_result;
    }

    let primary_err = primary_result.unwrap_err();
    let chain = match fallback_chain.chains.get(tool_name) {
        Some(c) => c,
        None => return Err(primary_err),
    };

    warn!(
        tool = %tool_name,
        error = %primary_err,
        fallbacks = chain.len(),
        "Primary tool failed, trying fallback chain"
    );

    metrics::record_fallback_attempt(tool_name);
    let mut last_error = primary_err;

    for fallback_name in chain {
        // Skip if circuit breaker is open for this provider
        if circuit_breakers.is_open(fallback_name) {
            warn!(
                fallback = %fallback_name,
                "Skipping fallback — circuit breaker open"
            );
            continue;
        }

        // Look up fallback tool in registry
        let fallback_tool = match tool_registry.get(fallback_name) {
            Some(t) => t,
            None => {
                warn!(fallback = %fallback_name, "Fallback tool not found in registry");
                continue;
            }
        };

        // Execute with timeout
        let timeout = fallback_chain.timeout();
        match tokio::time::timeout(timeout, fallback_tool.execute(arguments.clone(), ctx)).await {
            Ok(Ok(result)) => {
                info!(
                    tool = %tool_name,
                    fallback = %fallback_name,
                    "Fallback succeeded"
                );
                return Ok(result);
            }
            Ok(Err(e)) => {
                warn!(
                    fallback = %fallback_name,
                    error = %e,
                    "Fallback tool failed"
                );
                last_error = e;
            }
            Err(_) => {
                warn!(
                    fallback = %fallback_name,
                    timeout_ms = timeout.as_millis(),
                    "Fallback tool timed out"
                );
                last_error = ToolError::ExecutionFailed(format!(
                    "Fallback '{fallback_name}' timed out after {}ms",
                    timeout.as_millis()
                ));
            }
        }
    }

    metrics::record_fallback_exhausted(tool_name);
    warn!(
        tool = %tool_name,
        "All fallback providers exhausted"
    );
    Err(last_error)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::mcp::tools::{Tool, ToolContent, ToolSchema};
    use crate::resilience::CircuitBreakerConfig;
    use crate::uac::Action;
    use async_trait::async_trait;
    use serde_json::json;

    // === Test tools ===

    struct FailingTool {
        tool_name: String,
    }

    #[async_trait]
    impl Tool for FailingTool {
        fn name(&self) -> &str {
            &self.tool_name
        }
        fn description(&self) -> &str {
            "Always fails"
        }
        fn input_schema(&self) -> ToolSchema {
            ToolSchema {
                schema_type: "object".into(),
                properties: HashMap::new(),
                required: vec![],
            }
        }
        fn required_action(&self) -> Action {
            Action::Read
        }
        async fn execute(&self, _: Value, _: &ToolContext) -> Result<ToolResult, ToolError> {
            Err(ToolError::ExecutionFailed("always fails".into()))
        }
    }

    struct SuccessTool {
        tool_name: String,
        response: String,
    }

    #[async_trait]
    impl Tool for SuccessTool {
        fn name(&self) -> &str {
            &self.tool_name
        }
        fn description(&self) -> &str {
            "Always succeeds"
        }
        fn input_schema(&self) -> ToolSchema {
            ToolSchema {
                schema_type: "object".into(),
                properties: HashMap::new(),
                required: vec![],
            }
        }
        fn required_action(&self) -> Action {
            Action::Read
        }
        async fn execute(&self, _: Value, _: &ToolContext) -> Result<ToolResult, ToolError> {
            Ok(ToolResult {
                content: vec![ToolContent::Text {
                    text: self.response.clone(),
                }],
                is_error: None,
            })
        }
    }

    fn test_ctx() -> ToolContext {
        ToolContext {
            tenant_id: "test-tenant".into(),
            user_id: None,
            user_email: None,
            request_id: "req-1".into(),
            roles: vec![],
            scopes: vec!["stoa:read".into()],
            raw_token: None,
            skill_instructions: None,
            progress_token: None,
        }
    }

    fn test_cb_registry() -> Arc<CircuitBreakerRegistry> {
        Arc::new(CircuitBreakerRegistry::new(CircuitBreakerConfig::default()))
    }

    #[test]
    fn test_new_disabled() {
        let chain = FallbackChain::new(false, Some(r#"{"a":["b"]}"#), 5000);
        assert!(!chain.has_fallbacks("a"));
    }

    #[test]
    fn test_new_enabled_with_chains() {
        let chain = FallbackChain::new(true, Some(r#"{"tool_a":["tool_b","tool_c"]}"#), 5000);
        assert!(chain.has_fallbacks("tool_a"));
        assert!(!chain.has_fallbacks("tool_x"));
    }

    #[test]
    fn test_new_with_invalid_json() {
        let chain = FallbackChain::new(true, Some("not json"), 5000);
        assert!(!chain.has_fallbacks("anything"));
    }

    #[test]
    fn test_new_with_no_chains_json() {
        let chain = FallbackChain::new(true, None, 5000);
        assert!(!chain.has_fallbacks("anything"));
    }

    #[test]
    fn test_timeout() {
        let chain = FallbackChain::new(true, None, 3000);
        assert_eq!(chain.timeout(), Duration::from_millis(3000));
    }

    #[tokio::test]
    async fn test_primary_success_returns_immediately() {
        let chain = FallbackChain::new(true, Some(r#"{"tool_a":["tool_b"]}"#), 5000);
        let cb = test_cb_registry();
        let registry = Arc::new(ToolRegistry::new());
        let ctx = test_ctx();

        let ok_result = Ok(ToolResult::text("primary ok"));
        let result =
            execute_or_direct(&chain, &cb, &registry, "tool_a", json!({}), &ctx, ok_result).await;

        assert!(result.is_ok());
        let text = match &result.unwrap().content[0] {
            ToolContent::Text { text } => text.clone(),
            _ => panic!("Expected text"),
        };
        assert_eq!(text, "primary ok");
    }

    #[tokio::test]
    async fn test_no_fallbacks_returns_primary_error() {
        let chain = FallbackChain::new(true, None, 5000);
        let cb = test_cb_registry();
        let registry = Arc::new(ToolRegistry::new());
        let ctx = test_ctx();

        let err_result = Err(ToolError::ExecutionFailed("primary failed".into()));
        let result = execute_or_direct(
            &chain,
            &cb,
            &registry,
            "tool_a",
            json!({}),
            &ctx,
            err_result,
        )
        .await;

        assert!(result.is_err());
    }

    #[tokio::test]
    async fn test_fallback_succeeds() {
        let chain = FallbackChain::new(true, Some(r#"{"tool_a":["tool_b"]}"#), 5000);
        let cb = test_cb_registry();
        let registry = Arc::new(ToolRegistry::new());
        registry.register(Arc::new(SuccessTool {
            tool_name: "tool_b".into(),
            response: "fallback ok".into(),
        }));
        let ctx = test_ctx();

        let err_result = Err(ToolError::ExecutionFailed("primary failed".into()));
        let result = execute_or_direct(
            &chain,
            &cb,
            &registry,
            "tool_a",
            json!({}),
            &ctx,
            err_result,
        )
        .await;

        assert!(result.is_ok());
        let text = match &result.unwrap().content[0] {
            ToolContent::Text { text } => text.clone(),
            _ => panic!("Expected text"),
        };
        assert_eq!(text, "fallback ok");
    }

    #[tokio::test]
    async fn test_all_fallbacks_fail() {
        let chain = FallbackChain::new(true, Some(r#"{"tool_a":["tool_b","tool_c"]}"#), 5000);
        let cb = test_cb_registry();
        let registry = Arc::new(ToolRegistry::new());
        registry.register(Arc::new(FailingTool {
            tool_name: "tool_b".into(),
        }));
        registry.register(Arc::new(FailingTool {
            tool_name: "tool_c".into(),
        }));
        let ctx = test_ctx();

        let err_result = Err(ToolError::ExecutionFailed("primary failed".into()));
        let result = execute_or_direct(
            &chain,
            &cb,
            &registry,
            "tool_a",
            json!({}),
            &ctx,
            err_result,
        )
        .await;

        assert!(result.is_err());
    }

    #[tokio::test]
    async fn test_fallback_not_in_registry_skipped() {
        let chain = FallbackChain::new(true, Some(r#"{"tool_a":["missing_tool","tool_c"]}"#), 5000);
        let cb = test_cb_registry();
        let registry = Arc::new(ToolRegistry::new());
        registry.register(Arc::new(SuccessTool {
            tool_name: "tool_c".into(),
            response: "second fallback ok".into(),
        }));
        let ctx = test_ctx();

        let err_result = Err(ToolError::ExecutionFailed("primary failed".into()));
        let result = execute_or_direct(
            &chain,
            &cb,
            &registry,
            "tool_a",
            json!({}),
            &ctx,
            err_result,
        )
        .await;

        assert!(result.is_ok());
    }

    #[tokio::test]
    async fn test_disabled_returns_primary_error() {
        let chain = FallbackChain::new(false, Some(r#"{"tool_a":["tool_b"]}"#), 5000);
        let cb = test_cb_registry();
        let registry = Arc::new(ToolRegistry::new());
        registry.register(Arc::new(SuccessTool {
            tool_name: "tool_b".into(),
            response: "should not reach".into(),
        }));
        let ctx = test_ctx();

        let err_result = Err(ToolError::ExecutionFailed("primary failed".into()));
        let result = execute_or_direct(
            &chain,
            &cb,
            &registry,
            "tool_a",
            json!({}),
            &ctx,
            err_result,
        )
        .await;

        assert!(result.is_err());
    }
}
