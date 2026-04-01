//! Built-in Plugins (CAB-1759, CAB-1936)
//!
//! Six built-in plugins:
//! 1. **CustomHeaderInjection** — Adds configurable headers to requests/responses
//! 2. **RequestLogger** — Logs request metadata for observability
//! 3. **IpWhitelist** — Restricts access by client IP address
//! 4. **StcPlugin** — STOA Token Compression for LLM agents (ADR-060)
//! 5. **PiiFilterPlugin** — Detects and redacts/blocks PII in bodies (CAB-1936)
//! 6. **SecretsDetectionPlugin** — Blocks leaked secrets before upstream (CAB-1936)

pub mod pii_filter;
pub mod secrets_detection;
pub mod stc;

use async_trait::async_trait;
use axum::http::StatusCode;
use serde_json::Value;
use tracing::info;

use super::sdk::{Phase, Plugin, PluginContext, PluginMetadata, PluginResult};

// ============================================================================
// 1. Custom Header Injection Plugin
// ============================================================================

/// Injects configurable headers into requests and/or responses.
///
/// Config example:
/// ```json
/// {
///   "request_headers": { "X-Custom-Source": "stoa-gateway" },
///   "response_headers": { "X-Powered-By": "STOA" }
/// }
/// ```
pub struct CustomHeaderInjection {
    request_headers: Vec<(String, String)>,
    response_headers: Vec<(String, String)>,
}

impl CustomHeaderInjection {
    pub fn new() -> Self {
        Self {
            request_headers: Vec::new(),
            response_headers: Vec::new(),
        }
    }

    fn parse_headers(config: &Value, key: &str) -> Vec<(String, String)> {
        config
            .get(key)
            .and_then(|v| v.as_object())
            .map(|obj| {
                obj.iter()
                    .filter_map(|(k, v)| v.as_str().map(|s| (k.clone(), s.to_string())))
                    .collect()
            })
            .unwrap_or_default()
    }
}

impl Default for CustomHeaderInjection {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl Plugin for CustomHeaderInjection {
    fn metadata(&self) -> PluginMetadata {
        PluginMetadata {
            name: "custom-header-injection".to_string(),
            version: "1.0.0".to_string(),
            description: "Injects configurable headers into requests and responses".to_string(),
            phases: vec![Phase::PreUpstream, Phase::PostUpstream],
        }
    }

    async fn on_load(&self, _config: &Value) -> Result<(), String> {
        Ok(())
    }

    async fn execute(&self, phase: Phase, ctx: &mut PluginContext) -> PluginResult {
        match phase {
            Phase::PreUpstream => {
                // Inject request headers from config
                let headers = Self::parse_headers(&ctx.config, "request_headers");
                for (name, value) in &headers {
                    ctx.set_request_header(name, value);
                }
                // Also inject instance-level headers
                for (name, value) in &self.request_headers {
                    ctx.set_request_header(name, value);
                }
            }
            Phase::PostUpstream => {
                // Inject response headers from config
                let headers = Self::parse_headers(&ctx.config, "response_headers");
                for (name, value) in &headers {
                    ctx.set_response_header(name, value);
                }
                for (name, value) in &self.response_headers {
                    ctx.set_response_header(name, value);
                }
            }
            _ => {}
        }
        PluginResult::Continue
    }
}

// ============================================================================
// 2. Request Logger Plugin
// ============================================================================

/// Logs request metadata at each configured phase.
///
/// Config example:
/// ```json
/// { "log_headers": true, "log_body": false }
/// ```
pub struct RequestLogger;

impl RequestLogger {
    pub fn new() -> Self {
        Self
    }
}

impl Default for RequestLogger {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl Plugin for RequestLogger {
    fn metadata(&self) -> PluginMetadata {
        PluginMetadata {
            name: "request-logger".to_string(),
            version: "1.0.0".to_string(),
            description: "Logs request metadata for observability".to_string(),
            phases: vec![Phase::PreAuth, Phase::PostUpstream],
        }
    }

    async fn execute(&self, phase: Phase, ctx: &mut PluginContext) -> PluginResult {
        let log_headers = ctx
            .config
            .get("log_headers")
            .and_then(|v| v.as_bool())
            .unwrap_or(false);

        match phase {
            Phase::PreAuth => {
                info!(
                    plugin = "request-logger",
                    phase = %phase,
                    tenant = %ctx.tenant_id,
                    method = %ctx.method,
                    path = %ctx.path,
                    client_ip = ?ctx.client_ip,
                    header_count = if log_headers { ctx.request_headers.len() } else { 0 },
                    "request received"
                );
            }
            Phase::PostUpstream => {
                let status = ctx.response_status.map(|s| s.as_u16()).unwrap_or(0);
                info!(
                    plugin = "request-logger",
                    phase = %phase,
                    tenant = %ctx.tenant_id,
                    method = %ctx.method,
                    path = %ctx.path,
                    response_status = status,
                    "response logged"
                );
            }
            _ => {}
        }

        PluginResult::Continue
    }
}

// ============================================================================
// 3. IP Whitelist Plugin
// ============================================================================

/// Restricts access by client IP address.
///
/// Config example:
/// ```json
/// {
///   "allowed_ips": ["10.0.0.1", "192.168.1.0/24"],
///   "deny_message": "Access denied by IP whitelist"
/// }
/// ```
///
/// Note: CIDR notation is checked by prefix match for simplicity.
/// For production use, a proper CIDR library should be integrated.
pub struct IpWhitelist;

impl IpWhitelist {
    pub fn new() -> Self {
        Self
    }

    fn is_allowed(client_ip: &str, allowed: &[String]) -> bool {
        if allowed.is_empty() {
            return true; // No whitelist = allow all
        }
        for entry in allowed {
            if entry.contains('/') {
                // Simple CIDR prefix match (e.g., "192.168.1." matches "192.168.1.0/24")
                if let Some(prefix) = entry.split('/').next() {
                    // Extract network prefix (everything up to last octet for /24, etc.)
                    let parts: Vec<&str> = prefix.split('.').collect();
                    if parts.len() >= 3 {
                        let network_prefix = format!("{}.{}.{}.", parts[0], parts[1], parts[2]);
                        if client_ip.starts_with(&network_prefix) {
                            return true;
                        }
                    }
                }
            } else if client_ip == entry {
                return true;
            }
        }
        false
    }
}

impl Default for IpWhitelist {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl Plugin for IpWhitelist {
    fn metadata(&self) -> PluginMetadata {
        PluginMetadata {
            name: "ip-whitelist".to_string(),
            version: "1.0.0".to_string(),
            description: "Restricts access by client IP address".to_string(),
            phases: vec![Phase::PreAuth],
        }
    }

    async fn execute(&self, _phase: Phase, ctx: &mut PluginContext) -> PluginResult {
        let allowed_ips: Vec<String> = ctx
            .config
            .get("allowed_ips")
            .and_then(|v| v.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|v| v.as_str().map(|s| s.to_string()))
                    .collect()
            })
            .unwrap_or_default();

        // If no whitelist configured, allow all
        if allowed_ips.is_empty() {
            return PluginResult::Continue;
        }

        let client_ip = ctx.client_ip.as_deref().unwrap_or("unknown");

        if Self::is_allowed(client_ip, &allowed_ips) {
            PluginResult::Continue
        } else {
            let deny_message = ctx
                .config
                .get("deny_message")
                .and_then(|v| v.as_str())
                .unwrap_or("Access denied");

            PluginResult::Terminate {
                status: StatusCode::FORBIDDEN,
                body: deny_message.to_string(),
            }
        }
    }
}

// ============================================================================
// Factory: register all built-in plugins
// ============================================================================

/// Register all built-in plugins into the given registry.
pub async fn register_builtin_plugins(
    registry: &super::registry::PluginRegistry,
    config: &Value,
) -> Result<(), String> {
    use std::sync::Arc;

    let plugins: Vec<Arc<dyn Plugin>> = vec![
        Arc::new(CustomHeaderInjection::new()),
        Arc::new(RequestLogger::new()),
        Arc::new(IpWhitelist::new()),
        Arc::new(stc::StcPlugin::new()),
        Arc::new(pii_filter::PiiFilterPlugin::new()),
        Arc::new(secrets_detection::SecretsDetectionPlugin::new()),
    ];

    for plugin in plugins {
        let name = plugin.metadata().name.clone();
        let plugin_config = config.get(&name).cloned().unwrap_or(Value::Null);
        registry.register(plugin, &plugin_config).await?;
    }

    Ok(())
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::HeaderMap;

    fn make_ctx_with_config(config: Value) -> PluginContext {
        let mut ctx = PluginContext::new(
            Phase::PreUpstream,
            "test-tenant".to_string(),
            "/api/test".to_string(),
            "GET".to_string(),
            HeaderMap::new(),
        );
        ctx.config = config;
        ctx
    }

    // --- Custom Header Injection Tests ---

    #[tokio::test]
    async fn test_header_injection_request_headers() {
        let plugin = CustomHeaderInjection::new();
        let config = serde_json::json!({
            "request_headers": {
                "X-Source": "stoa",
                "X-Version": "1.0"
            }
        });

        let mut ctx = make_ctx_with_config(config);
        let result = plugin.execute(Phase::PreUpstream, &mut ctx).await;

        assert!(matches!(result, PluginResult::Continue));
        assert_eq!(ctx.get_request_header("x-source"), Some("stoa"));
        assert_eq!(ctx.get_request_header("x-version"), Some("1.0"));
    }

    #[tokio::test]
    async fn test_header_injection_response_headers() {
        let plugin = CustomHeaderInjection::new();
        let config = serde_json::json!({
            "response_headers": {
                "X-Powered-By": "STOA"
            }
        });

        let mut ctx = make_ctx_with_config(config);
        ctx.phase = Phase::PostUpstream;
        let result = plugin.execute(Phase::PostUpstream, &mut ctx).await;

        assert!(matches!(result, PluginResult::Continue));
        assert_eq!(ctx.response_headers.get("x-powered-by").unwrap(), "STOA");
    }

    #[tokio::test]
    async fn test_header_injection_no_config() {
        let plugin = CustomHeaderInjection::new();
        let mut ctx = make_ctx_with_config(Value::Null);

        let result = plugin.execute(Phase::PreUpstream, &mut ctx).await;
        assert!(matches!(result, PluginResult::Continue));
    }

    // --- Request Logger Tests ---

    #[tokio::test]
    async fn test_request_logger_continues() {
        let plugin = RequestLogger::new();
        let mut ctx = make_ctx_with_config(serde_json::json!({"log_headers": true}));

        let result = plugin.execute(Phase::PreAuth, &mut ctx).await;
        assert!(matches!(result, PluginResult::Continue));
    }

    #[tokio::test]
    async fn test_request_logger_post_upstream() {
        let plugin = RequestLogger::new();
        let mut ctx = make_ctx_with_config(Value::Null);
        ctx.phase = Phase::PostUpstream;
        ctx.response_status = Some(StatusCode::OK);

        let result = plugin.execute(Phase::PostUpstream, &mut ctx).await;
        assert!(matches!(result, PluginResult::Continue));
    }

    // --- IP Whitelist Tests ---

    #[tokio::test]
    async fn test_ip_whitelist_allowed() {
        let plugin = IpWhitelist::new();
        let config = serde_json::json!({
            "allowed_ips": ["10.0.0.1", "192.168.1.100"]
        });

        let mut ctx = make_ctx_with_config(config);
        ctx.phase = Phase::PreAuth;
        ctx.client_ip = Some("10.0.0.1".to_string());

        let result = plugin.execute(Phase::PreAuth, &mut ctx).await;
        assert!(matches!(result, PluginResult::Continue));
    }

    #[tokio::test]
    async fn test_ip_whitelist_denied() {
        let plugin = IpWhitelist::new();
        let config = serde_json::json!({
            "allowed_ips": ["10.0.0.1"],
            "deny_message": "IP not allowed"
        });

        let mut ctx = make_ctx_with_config(config);
        ctx.phase = Phase::PreAuth;
        ctx.client_ip = Some("10.0.0.99".to_string());

        let result = plugin.execute(Phase::PreAuth, &mut ctx).await;
        match result {
            PluginResult::Terminate { status, body } => {
                assert_eq!(status, StatusCode::FORBIDDEN);
                assert_eq!(body, "IP not allowed");
            }
            _ => panic!("expected Terminate"),
        }
    }

    #[tokio::test]
    async fn test_ip_whitelist_cidr_match() {
        let plugin = IpWhitelist::new();
        let config = serde_json::json!({
            "allowed_ips": ["192.168.1.0/24"]
        });

        let mut ctx = make_ctx_with_config(config);
        ctx.phase = Phase::PreAuth;
        ctx.client_ip = Some("192.168.1.42".to_string());

        let result = plugin.execute(Phase::PreAuth, &mut ctx).await;
        assert!(matches!(result, PluginResult::Continue));
    }

    #[tokio::test]
    async fn test_ip_whitelist_empty_allows_all() {
        let plugin = IpWhitelist::new();
        let mut ctx = make_ctx_with_config(serde_json::json!({"allowed_ips": []}));
        ctx.phase = Phase::PreAuth;
        ctx.client_ip = Some("1.2.3.4".to_string());

        let result = plugin.execute(Phase::PreAuth, &mut ctx).await;
        assert!(matches!(result, PluginResult::Continue));
    }

    #[tokio::test]
    async fn test_ip_whitelist_no_config_allows_all() {
        let plugin = IpWhitelist::new();
        let mut ctx = make_ctx_with_config(Value::Null);
        ctx.phase = Phase::PreAuth;
        ctx.client_ip = Some("1.2.3.4".to_string());

        let result = plugin.execute(Phase::PreAuth, &mut ctx).await;
        assert!(matches!(result, PluginResult::Continue));
    }

    #[tokio::test]
    async fn test_ip_whitelist_no_client_ip() {
        let plugin = IpWhitelist::new();
        let config = serde_json::json!({
            "allowed_ips": ["10.0.0.1"]
        });

        let mut ctx = make_ctx_with_config(config);
        ctx.phase = Phase::PreAuth;
        // client_ip is None

        let result = plugin.execute(Phase::PreAuth, &mut ctx).await;
        match result {
            PluginResult::Terminate { status, .. } => {
                assert_eq!(status, StatusCode::FORBIDDEN);
            }
            _ => panic!("expected Terminate when client IP unknown"),
        }
    }

    // --- is_allowed unit tests ---

    #[test]
    fn test_is_allowed_exact_match() {
        assert!(IpWhitelist::is_allowed(
            "10.0.0.1",
            &["10.0.0.1".to_string()]
        ));
    }

    #[test]
    fn test_is_allowed_no_match() {
        assert!(!IpWhitelist::is_allowed(
            "10.0.0.2",
            &["10.0.0.1".to_string()]
        ));
    }

    #[test]
    fn test_is_allowed_cidr() {
        assert!(IpWhitelist::is_allowed(
            "192.168.1.50",
            &["192.168.1.0/24".to_string()]
        ));
    }

    #[test]
    fn test_is_allowed_empty_list() {
        let empty: Vec<String> = vec![];
        assert!(IpWhitelist::is_allowed("1.2.3.4", &empty));
    }

    // --- Factory Tests ---

    #[tokio::test]
    async fn test_register_builtin_plugins() {
        let registry = super::super::registry::PluginRegistry::new();
        let config = serde_json::json!({
            "custom-header-injection": {
                "request_headers": { "X-Test": "value" }
            }
        });

        register_builtin_plugins(&registry, &config)
            .await
            .expect("register builtins");

        assert_eq!(registry.count().await, 6);

        let names: Vec<String> = registry
            .list()
            .await
            .iter()
            .map(|m| m.name.clone())
            .collect();
        assert!(names.contains(&"custom-header-injection".to_string()));
        assert!(names.contains(&"request-logger".to_string()));
        assert!(names.contains(&"ip-whitelist".to_string()));
        assert!(names.contains(&"stc-compression".to_string()));
        assert!(names.contains(&"pii-filter".to_string()));
        assert!(names.contains(&"secrets-detection".to_string()));
    }
}
