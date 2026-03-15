//! Plugin SDK — Trait Definitions (CAB-1759)
//!
//! Core types and traits for the STOA Gateway plugin system.

use async_trait::async_trait;
use axum::http::{HeaderMap, StatusCode};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;

/// Execution phase in the request/response lifecycle.
///
/// Aligned with Kong PDK phases for familiarity:
/// - `PreAuth`: Before authentication — modify headers, reject early
/// - `PostAuth`: After auth succeeds — access user context
/// - `PreUpstream`: Before forwarding to backend — transform request
/// - `PostUpstream`: After backend response — transform response
/// - `OnError`: On any error (4xx/5xx) — custom error handling
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Phase {
    PreAuth,
    PostAuth,
    PreUpstream,
    PostUpstream,
    OnError,
}

impl std::fmt::Display for Phase {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Phase::PreAuth => write!(f, "pre_auth"),
            Phase::PostAuth => write!(f, "post_auth"),
            Phase::PreUpstream => write!(f, "pre_upstream"),
            Phase::PostUpstream => write!(f, "post_upstream"),
            Phase::OnError => write!(f, "on_error"),
        }
    }
}

/// Plugin metadata — identity and capabilities.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PluginMetadata {
    /// Unique plugin name (kebab-case, e.g., "custom-header-injection")
    pub name: String,
    /// Semantic version (e.g., "1.0.0")
    pub version: String,
    /// Human-readable description
    pub description: String,
    /// Phases this plugin participates in (determines when `execute` is called)
    pub phases: Vec<Phase>,
}

/// Result of a plugin execution — controls the request/response flow.
#[derive(Debug, Clone)]
pub enum PluginResult {
    /// Continue processing (pass to next plugin or upstream)
    Continue,
    /// Short-circuit with an error response (stop the chain)
    Terminate { status: StatusCode, body: String },
}

/// Mutable context passed to plugins during execution.
///
/// Provides read/write access to request headers, response headers,
/// and metadata. Plugins can modify headers, inject data, or read
/// tenant/user context.
pub struct PluginContext {
    /// Current execution phase
    pub phase: Phase,
    /// Tenant ID from auth context
    pub tenant_id: String,
    /// User ID (if authenticated)
    pub user_id: Option<String>,
    /// Request path
    pub path: String,
    /// Request method (GET, POST, etc.)
    pub method: String,
    /// Mutable request headers (plugins can add/modify/remove)
    pub request_headers: HeaderMap,
    /// Mutable response headers (available in PostUpstream/OnError phases)
    pub response_headers: HeaderMap,
    /// Response status code (available in PostUpstream/OnError phases)
    pub response_status: Option<StatusCode>,
    /// Plugin-specific configuration (from plugin config in gateway config)
    pub config: Value,
    /// Shared key-value store for passing data between phases of the same request
    pub store: HashMap<String, String>,
    /// Client IP address
    pub client_ip: Option<String>,
}

impl PluginContext {
    /// Create a new plugin context for a request.
    pub fn new(
        phase: Phase,
        tenant_id: String,
        path: String,
        method: String,
        request_headers: HeaderMap,
    ) -> Self {
        Self {
            phase,
            tenant_id,
            user_id: None,
            path,
            method,
            request_headers,
            response_headers: HeaderMap::new(),
            response_status: None,
            config: Value::Null,
            store: HashMap::new(),
            client_ip: None,
        }
    }

    /// Set a request header (adds or replaces).
    pub fn set_request_header(&mut self, name: &str, value: &str) {
        if let (Ok(name), Ok(value)) = (
            axum::http::header::HeaderName::from_bytes(name.as_bytes()),
            axum::http::header::HeaderValue::from_str(value),
        ) {
            self.request_headers.insert(name, value);
        }
    }

    /// Get a request header value.
    pub fn get_request_header(&self, name: &str) -> Option<&str> {
        self.request_headers.get(name).and_then(|v| v.to_str().ok())
    }

    /// Remove a request header.
    pub fn remove_request_header(&mut self, name: &str) {
        if let Ok(name) = axum::http::header::HeaderName::from_bytes(name.as_bytes()) {
            self.request_headers.remove(name);
        }
    }

    /// Set a response header (adds or replaces).
    pub fn set_response_header(&mut self, name: &str, value: &str) {
        if let (Ok(name), Ok(value)) = (
            axum::http::header::HeaderName::from_bytes(name.as_bytes()),
            axum::http::header::HeaderValue::from_str(value),
        ) {
            self.response_headers.insert(name, value);
        }
    }

    /// Store a value in the per-request key-value store.
    /// Useful for passing data between plugin phases.
    pub fn store_set(&mut self, key: &str, value: &str) {
        self.store.insert(key.to_string(), value.to_string());
    }

    /// Retrieve a value from the per-request key-value store.
    pub fn store_get(&self, key: &str) -> Option<&str> {
        self.store.get(key).map(|s| s.as_str())
    }
}

/// The Plugin trait — implement this for custom gateway plugins.
///
/// Plugins are loaded into the `PluginRegistry` and executed at their
/// declared phases during request processing.
#[async_trait]
pub trait Plugin: Send + Sync {
    /// Plugin identity and capabilities.
    fn metadata(&self) -> PluginMetadata;

    /// Called once when the plugin is loaded into the registry.
    /// Use for initialization (connections, caches, etc.).
    async fn on_load(&self, _config: &Value) -> Result<(), String> {
        Ok(())
    }

    /// Called when the plugin is unloaded from the registry.
    /// Use for cleanup (close connections, flush buffers, etc.).
    async fn on_unload(&self) -> Result<(), String> {
        Ok(())
    }

    /// Execute the plugin logic for the given phase.
    ///
    /// Return `PluginResult::Continue` to pass to the next plugin,
    /// or `PluginResult::Terminate` to short-circuit with an error.
    async fn execute(&self, phase: Phase, ctx: &mut PluginContext) -> PluginResult;
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_phase_display() {
        assert_eq!(Phase::PreAuth.to_string(), "pre_auth");
        assert_eq!(Phase::PostAuth.to_string(), "post_auth");
        assert_eq!(Phase::PreUpstream.to_string(), "pre_upstream");
        assert_eq!(Phase::PostUpstream.to_string(), "post_upstream");
        assert_eq!(Phase::OnError.to_string(), "on_error");
    }

    #[test]
    fn test_phase_serialize() {
        let json = serde_json::to_string(&Phase::PreAuth).expect("serialize");
        assert_eq!(json, r#""pre_auth""#);
    }

    #[test]
    fn test_phase_deserialize() {
        let phase: Phase = serde_json::from_str(r#""post_upstream""#).expect("deserialize");
        assert_eq!(phase, Phase::PostUpstream);
    }

    #[test]
    fn test_plugin_metadata_serialize() {
        let meta = PluginMetadata {
            name: "test-plugin".to_string(),
            version: "1.0.0".to_string(),
            description: "A test plugin".to_string(),
            phases: vec![Phase::PreAuth, Phase::PostUpstream],
        };
        let json = serde_json::to_string(&meta).expect("serialize");
        assert!(json.contains("test-plugin"));
        assert!(json.contains("pre_auth"));
        assert!(json.contains("post_upstream"));
    }

    #[test]
    fn test_context_request_headers() {
        let mut ctx = PluginContext::new(
            Phase::PreUpstream,
            "acme".to_string(),
            "/api/v1/users".to_string(),
            "GET".to_string(),
            HeaderMap::new(),
        );

        // Set and get
        ctx.set_request_header("X-Custom", "value-1");
        assert_eq!(ctx.get_request_header("x-custom"), Some("value-1"));

        // Overwrite
        ctx.set_request_header("X-Custom", "value-2");
        assert_eq!(ctx.get_request_header("x-custom"), Some("value-2"));

        // Remove
        ctx.remove_request_header("X-Custom");
        assert_eq!(ctx.get_request_header("x-custom"), None);
    }

    #[test]
    fn test_context_response_headers() {
        let mut ctx = PluginContext::new(
            Phase::PostUpstream,
            "acme".to_string(),
            "/api".to_string(),
            "POST".to_string(),
            HeaderMap::new(),
        );

        ctx.set_response_header("X-Response-Time", "42ms");
        assert_eq!(ctx.response_headers.get("x-response-time").unwrap(), "42ms");
    }

    #[test]
    fn test_context_store() {
        let mut ctx = PluginContext::new(
            Phase::PreAuth,
            "acme".to_string(),
            "/".to_string(),
            "GET".to_string(),
            HeaderMap::new(),
        );

        assert_eq!(ctx.store_get("key"), None);
        ctx.store_set("key", "value");
        assert_eq!(ctx.store_get("key"), Some("value"));
    }

    #[test]
    fn test_context_initial_state() {
        let ctx = PluginContext::new(
            Phase::PreAuth,
            "tenant-1".to_string(),
            "/path".to_string(),
            "DELETE".to_string(),
            HeaderMap::new(),
        );

        assert_eq!(ctx.phase, Phase::PreAuth);
        assert_eq!(ctx.tenant_id, "tenant-1");
        assert_eq!(ctx.path, "/path");
        assert_eq!(ctx.method, "DELETE");
        assert!(ctx.user_id.is_none());
        assert!(ctx.response_status.is_none());
        assert!(ctx.client_ip.is_none());
        assert!(ctx.store.is_empty());
    }

    #[test]
    fn test_plugin_result_variants() {
        let cont = PluginResult::Continue;
        assert!(matches!(cont, PluginResult::Continue));

        let term = PluginResult::Terminate {
            status: StatusCode::FORBIDDEN,
            body: "denied".to_string(),
        };
        match term {
            PluginResult::Terminate { status, body } => {
                assert_eq!(status, StatusCode::FORBIDDEN);
                assert_eq!(body, "denied");
            }
            _ => panic!("expected Terminate"),
        }
    }
}
