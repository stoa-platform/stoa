//! Lazy MCP Discovery (CAB-1552)
//!
//! Probes upstream MCP servers on first request (not at startup).
//! Discovered capabilities are cached with configurable TTL using moka.
//! Subsequent requests use cache (cache-first pattern).
//!
//! Composes with circuit breaker + retry from resilience module for
//! resilient upstream probing.

use moka::sync::Cache;
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use std::time::Duration;
use tracing::{debug, info, warn};

use crate::config::Config;
use crate::resilience::{CircuitBreakerRegistry, RetryConfig};

/// Discovered capabilities of an upstream MCP server
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UpstreamCapabilities {
    /// Server name reported by the upstream
    pub server_name: Option<String>,
    /// Protocol version supported
    pub protocol_version: Option<String>,
    /// Whether the upstream supports tool listing
    pub supports_tools: bool,
    /// Whether the upstream supports resource listing
    pub supports_resources: bool,
    /// Whether the upstream supports prompt listing
    pub supports_prompts: bool,
    /// Raw capabilities JSON for forward-compatibility
    #[serde(default)]
    pub raw: serde_json::Value,
}

/// Error types for lazy discovery
#[derive(Debug, thiserror::Error)]
pub enum DiscoveryError {
    #[error("upstream unreachable: {0}")]
    Unreachable(String),
    #[error("invalid response from upstream: {0}")]
    InvalidResponse(String),
    #[error("circuit breaker open for upstream: {0}")]
    CircuitOpen(String),
}

/// Lazy MCP discovery with moka cache and circuit breaker integration.
///
/// Cache-first pattern: on `discover()`, check moka cache by upstream URL.
/// On miss, probe the upstream's capabilities endpoint with retry + CB.
/// On hit, return cached capabilities immediately.
pub struct LazyMcpDiscovery {
    /// Moka cache keyed by upstream server URL
    cache: Cache<String, UpstreamCapabilities>,
    /// Shared HTTP client (from AppState)
    http_client: reqwest::Client,
    /// Circuit breaker registry for per-upstream isolation
    circuit_breakers: Arc<CircuitBreakerRegistry>,
    /// Retry config for transient failures
    retry_config: RetryConfig,
}

impl LazyMcpDiscovery {
    /// Create a new LazyMcpDiscovery from gateway config.
    ///
    /// Uses `mcp_discovery_cache_ttl_secs` and `mcp_discovery_cache_max_entries`
    /// from Config (defaults: 300s TTL, 256 entries).
    pub fn new(
        config: &Config,
        http_client: reqwest::Client,
        circuit_breakers: Arc<CircuitBreakerRegistry>,
    ) -> Self {
        let cache = Cache::builder()
            .time_to_live(Duration::from_secs(config.mcp_discovery_cache_ttl_secs))
            .max_capacity(config.mcp_discovery_cache_max_entries)
            .build();

        let retry_config = RetryConfig {
            max_attempts: 3,
            initial_delay: Duration::from_millis(200),
            max_delay: Duration::from_secs(2),
            multiplier: 2.0,
            jitter: 0.1,
        };

        info!(
            ttl_secs = config.mcp_discovery_cache_ttl_secs,
            max_entries = config.mcp_discovery_cache_max_entries,
            "Lazy MCP discovery initialized"
        );

        Self {
            cache,
            http_client,
            circuit_breakers,
            retry_config,
        }
    }

    /// Discover capabilities of an upstream MCP server.
    ///
    /// Cache-first: returns cached result if available.
    /// On cache miss: probes the upstream, caches result, returns it.
    pub async fn discover(
        &self,
        upstream_url: &str,
    ) -> Result<UpstreamCapabilities, DiscoveryError> {
        // Cache hit — fast path
        if let Some(caps) = self.cache.get(upstream_url) {
            debug!(upstream = %upstream_url, "MCP discovery cache hit");
            return Ok(caps);
        }

        // Cache miss — probe upstream with circuit breaker
        debug!(upstream = %upstream_url, "MCP discovery cache miss, probing upstream");
        let caps = self.probe_upstream(upstream_url).await?;
        self.cache.insert(upstream_url.to_string(), caps.clone());
        info!(
            upstream = %upstream_url,
            server_name = ?caps.server_name,
            "Cached upstream MCP capabilities"
        );
        Ok(caps)
    }

    /// Probe an upstream MCP server's capabilities endpoint.
    ///
    /// Uses circuit breaker per upstream URL and retry with backoff.
    async fn probe_upstream(
        &self,
        upstream_url: &str,
    ) -> Result<UpstreamCapabilities, DiscoveryError> {
        let cb_key = format!("mcp-discovery:{upstream_url}");
        let cb = self.circuit_breakers.get_or_create(&cb_key);

        // Check circuit state before attempting
        if !cb.allow_request() {
            return Err(DiscoveryError::CircuitOpen(upstream_url.to_string()));
        }

        let capabilities_url = format!("{}/capabilities", upstream_url.trim_end_matches('/'));

        let mut last_error = None;
        for attempt in 0..self.retry_config.max_attempts {
            if attempt > 0 {
                let delay = self.retry_config.delay_for_attempt(attempt);
                tokio::time::sleep(delay).await;
            }

            match self.fetch_capabilities(&capabilities_url).await {
                Ok(caps) => {
                    cb.record_success();
                    return Ok(caps);
                }
                Err(e) => {
                    warn!(
                        upstream = %upstream_url,
                        attempt = attempt + 1,
                        max_attempts = self.retry_config.max_attempts,
                        error = %e,
                        "MCP discovery probe failed"
                    );
                    cb.record_failure();
                    last_error = Some(e);
                }
            }
        }

        Err(last_error.unwrap_or_else(|| DiscoveryError::Unreachable(upstream_url.to_string())))
    }

    /// Fetch and parse capabilities from a single URL.
    async fn fetch_capabilities(&self, url: &str) -> Result<UpstreamCapabilities, DiscoveryError> {
        let resp = self
            .http_client
            .get(url)
            .timeout(Duration::from_secs(5))
            .send()
            .await
            .map_err(|e| DiscoveryError::Unreachable(e.to_string()))?;

        if !resp.status().is_success() {
            return Err(DiscoveryError::InvalidResponse(format!(
                "HTTP {}",
                resp.status()
            )));
        }

        let body: serde_json::Value = resp
            .json()
            .await
            .map_err(|e| DiscoveryError::InvalidResponse(e.to_string()))?;

        Ok(parse_capabilities(&body))
    }

    /// Invalidate a cached upstream entry (e.g., after config change).
    pub fn invalidate(&self, upstream_url: &str) {
        self.cache.invalidate(upstream_url);
        debug!(upstream = %upstream_url, "Invalidated MCP discovery cache entry");
    }

    /// Number of cached upstream entries (for metrics/diagnostics).
    pub fn cached_count(&self) -> u64 {
        self.cache.entry_count()
    }
}

/// Parse capabilities JSON into structured format.
///
/// Handles both MCP standard format and STOA's custom capabilities response.
fn parse_capabilities(body: &serde_json::Value) -> UpstreamCapabilities {
    // Try MCP standard: { "capabilities": { "tools": {}, "resources": {}, "prompts": {} } }
    let caps = body
        .get("capabilities")
        .or_else(|| body.get("result").and_then(|r| r.get("capabilities")));

    let (supports_tools, supports_resources, supports_prompts) = match caps {
        Some(c) => (
            c.get("tools").is_some(),
            c.get("resources").is_some(),
            c.get("prompts").is_some(),
        ),
        None => (false, false, false),
    };

    // Try to extract server info
    let server_info = body
        .get("serverInfo")
        .or_else(|| body.get("result").and_then(|r| r.get("serverInfo")))
        .or_else(|| body.get("server"));

    let server_name = server_info
        .and_then(|s| s.get("name"))
        .and_then(|n| n.as_str())
        .map(String::from);

    let protocol_version = server_info
        .and_then(|s| s.get("protocolVersion"))
        .or_else(|| body.get("protocolVersion"))
        .and_then(|v| v.as_str())
        .map(String::from);

    UpstreamCapabilities {
        server_name,
        protocol_version,
        supports_tools,
        supports_resources,
        supports_prompts,
        raw: body.clone(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::resilience::CircuitBreakerConfig;
    use serde_json::json;

    #[test]
    fn test_parse_capabilities_mcp_standard() {
        let body = json!({
            "serverInfo": { "name": "test-server", "protocolVersion": "2025-03-26" },
            "capabilities": {
                "tools": { "listChanged": true },
                "resources": {},
                "prompts": {}
            }
        });
        let caps = parse_capabilities(&body);
        assert_eq!(caps.server_name.as_deref(), Some("test-server"));
        assert_eq!(caps.protocol_version.as_deref(), Some("2025-03-26"));
        assert!(caps.supports_tools);
        assert!(caps.supports_resources);
        assert!(caps.supports_prompts);
    }

    #[test]
    fn test_parse_capabilities_nested_result() {
        let body = json!({
            "result": {
                "serverInfo": { "name": "nested-server" },
                "capabilities": { "tools": {} }
            }
        });
        let caps = parse_capabilities(&body);
        assert_eq!(caps.server_name.as_deref(), Some("nested-server"));
        assert!(caps.supports_tools);
        assert!(!caps.supports_resources);
        assert!(!caps.supports_prompts);
    }

    #[test]
    fn test_parse_capabilities_stoa_format() {
        let body = json!({
            "server": { "name": "STOA Gateway", "protocolVersion": "2025-11-25" },
            "capabilities": { "tools": { "listChanged": true } }
        });
        let caps = parse_capabilities(&body);
        assert_eq!(caps.server_name.as_deref(), Some("STOA Gateway"));
        assert!(caps.supports_tools);
    }

    #[test]
    fn test_parse_capabilities_empty() {
        let body = json!({});
        let caps = parse_capabilities(&body);
        assert!(caps.server_name.is_none());
        assert!(!caps.supports_tools);
        assert!(!caps.supports_resources);
        assert!(!caps.supports_prompts);
    }

    #[test]
    fn test_parse_capabilities_tools_only() {
        let body = json!({ "capabilities": { "tools": {} } });
        let caps = parse_capabilities(&body);
        assert!(caps.supports_tools);
        assert!(!caps.supports_resources);
    }

    #[test]
    fn test_upstream_capabilities_serde_roundtrip() {
        let caps = UpstreamCapabilities {
            server_name: Some("test".to_string()),
            protocol_version: Some("2025-03-26".to_string()),
            supports_tools: true,
            supports_resources: false,
            supports_prompts: true,
            raw: json!({"capabilities": {"tools": {}}}),
        };
        let json_str = serde_json::to_string(&caps).expect("serialize");
        let deserialized: UpstreamCapabilities =
            serde_json::from_str(&json_str).expect("deserialize");
        assert_eq!(deserialized.server_name, caps.server_name);
        assert!(deserialized.supports_tools);
        assert!(!deserialized.supports_resources);
    }

    // --- Integration-style tests using mockito ---

    #[tokio::test]
    async fn test_discover_cache_hit() {
        let config = Config {
            mcp_discovery_cache_ttl_secs: 300,
            mcp_discovery_cache_max_entries: 64,
            ..Config::default()
        };
        let http_client = reqwest::Client::new();
        let cb_registry = Arc::new(CircuitBreakerRegistry::new(CircuitBreakerConfig::default()));
        let discovery = LazyMcpDiscovery::new(&config, http_client, cb_registry);

        // Manually insert into cache
        let caps = UpstreamCapabilities {
            server_name: Some("cached-server".to_string()),
            protocol_version: Some("2025-03-26".to_string()),
            supports_tools: true,
            supports_resources: false,
            supports_prompts: false,
            raw: json!({}),
        };
        discovery
            .cache
            .insert("http://example.com/mcp".to_string(), caps.clone());

        // Should return cached value without HTTP call
        let result = discovery.discover("http://example.com/mcp").await;
        assert!(result.is_ok());
        let discovered = result.expect("should be cached");
        assert_eq!(discovered.server_name.as_deref(), Some("cached-server"));
    }

    #[tokio::test]
    async fn test_discover_cache_miss_unreachable() {
        let config = Config {
            mcp_discovery_cache_ttl_secs: 300,
            mcp_discovery_cache_max_entries: 64,
            ..Config::default()
        };
        let http_client = reqwest::Client::builder()
            .timeout(Duration::from_millis(100))
            .build()
            .expect("client");
        let cb_registry = Arc::new(CircuitBreakerRegistry::new(CircuitBreakerConfig::default()));
        let discovery = LazyMcpDiscovery::new(&config, http_client, cb_registry);

        // Non-existent host — should fail with Unreachable
        let result = discovery.discover("http://192.0.2.1:19999/mcp").await;
        assert!(result.is_err());
        match result.unwrap_err() {
            DiscoveryError::Unreachable(_) => {} // expected
            other => panic!("expected Unreachable, got: {other}"),
        }
    }

    #[test]
    fn test_invalidate() {
        let config = Config {
            mcp_discovery_cache_ttl_secs: 300,
            mcp_discovery_cache_max_entries: 64,
            ..Config::default()
        };
        let http_client = reqwest::Client::new();
        let cb_registry = Arc::new(CircuitBreakerRegistry::new(CircuitBreakerConfig::default()));
        let discovery = LazyMcpDiscovery::new(&config, http_client, cb_registry);

        let caps = UpstreamCapabilities {
            server_name: Some("test".to_string()),
            protocol_version: None,
            supports_tools: true,
            supports_resources: false,
            supports_prompts: false,
            raw: json!({}),
        };
        discovery
            .cache
            .insert("http://example.com/mcp".to_string(), caps);
        discovery.cache.run_pending_tasks();
        assert_eq!(discovery.cached_count(), 1);

        discovery.invalidate("http://example.com/mcp");
        discovery.cache.run_pending_tasks();
        assert!(discovery.cache.get("http://example.com/mcp").is_none());
    }

    #[test]
    fn test_cached_count() {
        let config = Config {
            mcp_discovery_cache_ttl_secs: 300,
            mcp_discovery_cache_max_entries: 64,
            ..Config::default()
        };
        let http_client = reqwest::Client::new();
        let cb_registry = Arc::new(CircuitBreakerRegistry::new(CircuitBreakerConfig::default()));
        let discovery = LazyMcpDiscovery::new(&config, http_client, cb_registry);

        assert_eq!(discovery.cached_count(), 0);

        let caps = UpstreamCapabilities {
            server_name: None,
            protocol_version: None,
            supports_tools: false,
            supports_resources: false,
            supports_prompts: false,
            raw: json!({}),
        };
        discovery.cache.insert("a".to_string(), caps.clone());
        discovery.cache.insert("b".to_string(), caps);
        discovery.cache.run_pending_tasks();
        assert_eq!(discovery.cached_count(), 2);
    }
}
