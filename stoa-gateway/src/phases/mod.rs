//! Request Lifecycle Phases — Pingora-inspired internal pipeline (CAB-1834)
//!
//! Provides a `ProxyPhase` trait with 6 lifecycle callbacks and a `PhaseChain`
//! executor that runs phases in order with short-circuit on rejection.
//!
//! This is the **internal** request lifecycle (compile-time, structural).
//! For the **external** plugin system (runtime, config-driven), see `plugin/`.

pub mod auth;
pub mod metrics;
pub mod rate_limit;

use async_trait::async_trait;
use axum::http::{HeaderMap, Method, StatusCode};
use std::collections::HashMap;
use std::sync::Arc;
use std::time::Instant;

/// Result of a phase callback — controls request flow through the chain.
#[derive(Debug, Clone)]
pub enum PhaseResult {
    /// Continue to the next phase.
    Continue,
    /// Short-circuit the chain with an error response.
    Reject { status: StatusCode, body: String },
    /// Phase selected an upstream (used by `upstream_select`).
    UpstreamSelected { url: String },
}

/// Mutable context threaded through all phases of a single request.
pub struct PhaseContext {
    /// Request method
    pub method: Method,
    /// Request path
    pub path: String,
    /// Client IP address
    pub client_ip: Option<String>,
    /// Tenant ID (from auth or header)
    pub tenant_id: Option<String>,
    /// User/consumer ID (from JWT sub)
    pub user_id: Option<String>,
    /// Route ID (from RouteRegistry match)
    pub route_id: Option<String>,
    /// Mutable request headers
    pub request_headers: HeaderMap,
    /// Mutable response headers (populated after upstream response)
    pub response_headers: HeaderMap,
    /// Response status (populated after upstream response)
    pub response_status: Option<StatusCode>,
    /// Selected upstream URL (set by upstream_select phase)
    pub upstream_url: Option<String>,
    /// Per-request key-value store for cross-phase data passing
    pub store: HashMap<String, String>,
    /// Request start time (for latency metrics)
    pub start_time: Instant,
    /// Error that occurred during proxying (populated for error_handler)
    pub error: Option<String>,
}

impl PhaseContext {
    /// Create a new context for an incoming request.
    pub fn new(method: Method, path: String, request_headers: HeaderMap) -> Self {
        Self {
            method,
            path,
            client_ip: None,
            tenant_id: None,
            user_id: None,
            route_id: None,
            request_headers,
            response_headers: HeaderMap::new(),
            response_status: None,
            upstream_url: None,
            store: HashMap::new(),
            start_time: Instant::now(),
            error: None,
        }
    }

    /// Store a value for cross-phase data passing.
    pub fn store_set(&mut self, key: impl Into<String>, value: impl Into<String>) {
        self.store.insert(key.into(), value.into());
    }

    /// Retrieve a stored value.
    pub fn store_get(&self, key: &str) -> Option<&str> {
        self.store.get(key).map(|s| s.as_str())
    }

    /// Elapsed time since request start.
    pub fn elapsed_ms(&self) -> f64 {
        self.start_time.elapsed().as_secs_f64() * 1000.0
    }
}

/// A phase in the request lifecycle pipeline.
///
/// Inspired by Pingora's filter phases. Each callback has a default no-op
/// implementation so phases only need to override the callbacks they care about.
///
/// Execution order:
/// 1. `request_filter` — modify/reject before proxy
/// 2. `upstream_select` — choose backend (LB integration)
/// 3. `upstream_request_filter` — modify request before forwarding
/// 4. `response_filter` — modify response from upstream
/// 5. `logging` — emit metrics/traces
/// 6. `error_handler` — custom error handling (only on error)
#[async_trait]
pub trait ProxyPhase: Send + Sync {
    /// Phase name (for logging and diagnostics).
    fn name(&self) -> &str;

    /// Called before proxying — can inspect, modify, or reject the request.
    async fn request_filter(&self, _ctx: &mut PhaseContext) -> PhaseResult {
        PhaseResult::Continue
    }

    /// Choose which upstream backend to use. Return `UpstreamSelected` to set
    /// the upstream URL, or `Continue` to let the next phase decide.
    async fn upstream_select(&self, _ctx: &mut PhaseContext) -> PhaseResult {
        PhaseResult::Continue
    }

    /// Modify the request just before it is sent to the upstream.
    async fn upstream_request_filter(&self, _ctx: &mut PhaseContext) -> PhaseResult {
        PhaseResult::Continue
    }

    /// Modify the response received from the upstream.
    async fn response_filter(&self, _ctx: &mut PhaseContext) -> PhaseResult {
        PhaseResult::Continue
    }

    /// Emit metrics, traces, or logs after the request completes.
    async fn logging(&self, _ctx: &mut PhaseContext) -> PhaseResult {
        PhaseResult::Continue
    }

    /// Handle errors — generate custom error responses.
    /// Only called when `ctx.error` is `Some`.
    async fn error_handler(&self, _ctx: &mut PhaseContext) -> PhaseResult {
        PhaseResult::Continue
    }
}

/// Executes an ordered list of `ProxyPhase` implementations through the
/// request lifecycle. Short-circuits on `PhaseResult::Reject`.
pub struct PhaseChain {
    phases: Vec<Arc<dyn ProxyPhase>>,
}

impl PhaseChain {
    /// Create a new chain with the given phases (executed in order).
    pub fn new(phases: Vec<Arc<dyn ProxyPhase>>) -> Self {
        Self { phases }
    }

    /// Run the request_filter callback on all phases.
    /// Returns `Reject` on the first rejection, `Continue` if all pass.
    pub async fn run_request_filter(&self, ctx: &mut PhaseContext) -> PhaseResult {
        for phase in &self.phases {
            let result = phase.request_filter(ctx).await;
            if matches!(result, PhaseResult::Reject { .. }) {
                tracing::debug!(phase = phase.name(), "request rejected in request_filter");
                return result;
            }
        }
        PhaseResult::Continue
    }

    /// Run upstream_select on all phases until one selects an upstream.
    /// Sets `ctx.upstream_url` if an upstream is selected.
    pub async fn run_upstream_select(&self, ctx: &mut PhaseContext) -> PhaseResult {
        for phase in &self.phases {
            let result = phase.upstream_select(ctx).await;
            match &result {
                PhaseResult::UpstreamSelected { url } => {
                    ctx.upstream_url = Some(url.clone());
                    return result;
                }
                PhaseResult::Reject { .. } => return result,
                PhaseResult::Continue => {}
            }
        }
        PhaseResult::Continue
    }

    /// Run upstream_request_filter on all phases.
    pub async fn run_upstream_request_filter(&self, ctx: &mut PhaseContext) -> PhaseResult {
        for phase in &self.phases {
            let result = phase.upstream_request_filter(ctx).await;
            if matches!(result, PhaseResult::Reject { .. }) {
                return result;
            }
        }
        PhaseResult::Continue
    }

    /// Run response_filter on all phases.
    pub async fn run_response_filter(&self, ctx: &mut PhaseContext) -> PhaseResult {
        for phase in &self.phases {
            let result = phase.response_filter(ctx).await;
            if matches!(result, PhaseResult::Reject { .. }) {
                return result;
            }
        }
        PhaseResult::Continue
    }

    /// Run logging on all phases (never short-circuits — all phases log).
    pub async fn run_logging(&self, ctx: &mut PhaseContext) {
        for phase in &self.phases {
            let _ = phase.logging(ctx).await;
        }
    }

    /// Run error_handler on all phases until one handles the error.
    pub async fn run_error_handler(&self, ctx: &mut PhaseContext) -> PhaseResult {
        for phase in &self.phases {
            let result = phase.error_handler(ctx).await;
            if matches!(result, PhaseResult::Reject { .. }) {
                return result;
            }
        }
        PhaseResult::Continue
    }

    /// Number of phases in the chain.
    pub fn len(&self) -> usize {
        self.phases.len()
    }

    /// Whether the chain is empty.
    pub fn is_empty(&self) -> bool {
        self.phases.is_empty()
    }
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    struct PassPhase(&'static str);

    #[async_trait]
    impl ProxyPhase for PassPhase {
        fn name(&self) -> &str {
            self.0
        }
    }

    struct RejectPhase {
        name: &'static str,
        status: StatusCode,
    }

    #[async_trait]
    impl ProxyPhase for RejectPhase {
        fn name(&self) -> &str {
            self.name
        }

        async fn request_filter(&self, _ctx: &mut PhaseContext) -> PhaseResult {
            PhaseResult::Reject {
                status: self.status,
                body: format!("rejected by {}", self.name),
            }
        }
    }

    struct HeaderInjector {
        header: &'static str,
        value: &'static str,
    }

    #[async_trait]
    impl ProxyPhase for HeaderInjector {
        fn name(&self) -> &str {
            "header-injector"
        }

        async fn upstream_request_filter(&self, ctx: &mut PhaseContext) -> PhaseResult {
            if let (Ok(name), Ok(val)) = (
                axum::http::header::HeaderName::from_bytes(self.header.as_bytes()),
                axum::http::header::HeaderValue::from_str(self.value),
            ) {
                ctx.request_headers.insert(name, val);
            }
            PhaseResult::Continue
        }
    }

    struct SelectUpstream(&'static str);

    #[async_trait]
    impl ProxyPhase for SelectUpstream {
        fn name(&self) -> &str {
            "upstream-selector"
        }

        async fn upstream_select(&self, _ctx: &mut PhaseContext) -> PhaseResult {
            PhaseResult::UpstreamSelected {
                url: self.0.to_string(),
            }
        }
    }

    struct LoggingCounter;

    #[async_trait]
    impl ProxyPhase for LoggingCounter {
        fn name(&self) -> &str {
            "logging-counter"
        }

        async fn logging(&self, ctx: &mut PhaseContext) -> PhaseResult {
            let count = ctx
                .store_get("log_count")
                .and_then(|v| v.parse::<u32>().ok())
                .unwrap_or(0);
            ctx.store_set("log_count", (count + 1).to_string());
            PhaseResult::Continue
        }
    }

    fn make_ctx() -> PhaseContext {
        PhaseContext::new(Method::GET, "/api/v1/test".to_string(), HeaderMap::new())
    }

    #[test]
    fn test_phase_context_new() {
        let ctx = make_ctx();
        assert_eq!(ctx.method, Method::GET);
        assert_eq!(ctx.path, "/api/v1/test");
        assert!(ctx.client_ip.is_none());
        assert!(ctx.tenant_id.is_none());
        assert!(ctx.upstream_url.is_none());
        assert!(ctx.error.is_none());
        assert!(ctx.store.is_empty());
    }

    #[test]
    fn test_phase_context_store() {
        let mut ctx = make_ctx();
        assert!(ctx.store_get("key").is_none());
        ctx.store_set("key", "value");
        assert_eq!(ctx.store_get("key"), Some("value"));
    }

    #[test]
    fn test_phase_context_elapsed() {
        let ctx = make_ctx();
        std::thread::sleep(std::time::Duration::from_millis(5));
        assert!(ctx.elapsed_ms() >= 4.0);
    }

    #[tokio::test]
    async fn test_chain_all_pass() {
        let chain = PhaseChain::new(vec![
            Arc::new(PassPhase("a")),
            Arc::new(PassPhase("b")),
            Arc::new(PassPhase("c")),
        ]);

        let mut ctx = make_ctx();
        let result = chain.run_request_filter(&mut ctx).await;
        assert!(matches!(result, PhaseResult::Continue));
    }

    #[tokio::test]
    async fn test_chain_short_circuits_on_reject() {
        let chain = PhaseChain::new(vec![
            Arc::new(PassPhase("first")),
            Arc::new(RejectPhase {
                name: "blocker",
                status: StatusCode::FORBIDDEN,
            }),
            Arc::new(PassPhase("never-reached")),
        ]);

        let mut ctx = make_ctx();
        let result = chain.run_request_filter(&mut ctx).await;
        match result {
            PhaseResult::Reject { status, body } => {
                assert_eq!(status, StatusCode::FORBIDDEN);
                assert_eq!(body, "rejected by blocker");
            }
            _ => panic!("expected Reject"),
        }
    }

    #[tokio::test]
    async fn test_chain_upstream_select() {
        let chain = PhaseChain::new(vec![
            Arc::new(PassPhase("no-select")),
            Arc::new(SelectUpstream("http://backend:8080")),
            Arc::new(SelectUpstream("http://should-not-be-selected:9090")),
        ]);

        let mut ctx = make_ctx();
        let result = chain.run_upstream_select(&mut ctx).await;
        match result {
            PhaseResult::UpstreamSelected { url } => {
                assert_eq!(url, "http://backend:8080");
            }
            _ => panic!("expected UpstreamSelected"),
        }
        assert_eq!(ctx.upstream_url.as_deref(), Some("http://backend:8080"));
    }

    #[tokio::test]
    async fn test_chain_upstream_request_filter() {
        let chain = PhaseChain::new(vec![Arc::new(HeaderInjector {
            header: "X-Injected",
            value: "true",
        })]);

        let mut ctx = make_ctx();
        let result = chain.run_upstream_request_filter(&mut ctx).await;
        assert!(matches!(result, PhaseResult::Continue));
        assert_eq!(
            ctx.request_headers
                .get("x-injected")
                .and_then(|v| v.to_str().ok()),
            Some("true")
        );
    }

    #[tokio::test]
    async fn test_chain_logging_runs_all() {
        let chain = PhaseChain::new(vec![
            Arc::new(LoggingCounter),
            Arc::new(LoggingCounter),
            Arc::new(LoggingCounter),
        ]);

        let mut ctx = make_ctx();
        chain.run_logging(&mut ctx).await;
        assert_eq!(ctx.store_get("log_count"), Some("3"));
    }

    #[tokio::test]
    async fn test_empty_chain() {
        let chain = PhaseChain::new(vec![]);
        assert!(chain.is_empty());
        assert_eq!(chain.len(), 0);

        let mut ctx = make_ctx();
        assert!(matches!(
            chain.run_request_filter(&mut ctx).await,
            PhaseResult::Continue
        ));
        assert!(matches!(
            chain.run_upstream_select(&mut ctx).await,
            PhaseResult::Continue
        ));
    }

    #[test]
    fn test_chain_len() {
        let chain = PhaseChain::new(vec![Arc::new(PassPhase("a")), Arc::new(PassPhase("b"))]);
        assert_eq!(chain.len(), 2);
        assert!(!chain.is_empty());
    }
}
