//! Tenant Tool Permission Service
//!
//! Fetches and caches tenant tool permissions from the Control Plane API.
//! Eliminates the circular proxy pattern where gateway → CP-API → gateway
//! was adding ~200-300ms of unnecessary latency per tool call.
//!
//! Default-allow: if no permission row exists for a tool, it is allowed.

use moka::sync::Cache;
use reqwest::Client;
use serde::Deserialize;
use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;
use tracing::{debug, warn};

/// A single tool permission entry from CP-API.
#[derive(Debug, Clone, Deserialize)]
#[allow(dead_code)]
struct PermissionItem {
    mcp_server_id: String,
    tool_name: String,
    allowed: bool,
}

/// Paginated response from CP-API tool-permissions endpoint.
#[derive(Debug, Deserialize)]
struct PermissionListResponse {
    items: Vec<PermissionItem>,
    total: usize,
}

/// Cached permission map: tool_name → allowed.
/// When a tool appears with `allowed: false` for ANY server, it is denied.
type PermissionMap = HashMap<String, bool>;

/// Service that checks tenant tool permissions by fetching from CP-API
/// and caching locally with a configurable TTL.
#[derive(Clone)]
pub struct ToolPermissionService {
    client: Client,
    base_url: String,
    cache: Arc<Cache<String, PermissionMap>>,
}

impl ToolPermissionService {
    /// Create a new service.
    ///
    /// - `client`: shared HTTP client with connection pooling
    /// - `base_url`: Control Plane API base URL (e.g., `http://control-plane-api:8000`)
    /// - `cache_ttl`: how long to cache permissions per tenant (default: 60s)
    pub fn new(client: Client, base_url: &str, cache_ttl: Duration) -> Self {
        Self {
            client,
            base_url: base_url.trim_end_matches('/').to_string(),
            cache: Arc::new(
                Cache::builder()
                    .time_to_live(cache_ttl)
                    .max_capacity(10_000)
                    .build(),
            ),
        }
    }

    /// Check if a tool is allowed for a tenant.
    ///
    /// Default-allow: returns `true` if no explicit deny exists.
    /// On fetch failure: permissive (returns `true` + logs warning).
    pub async fn is_tool_allowed(&self, tenant_id: &str, tool_name: &str) -> bool {
        let perms = self.get_permissions(tenant_id).await;
        // Default-allow: if tool not in map, it's allowed
        *perms.get(tool_name).unwrap_or(&true)
    }

    /// Get (or fetch) the permission map for a tenant.
    async fn get_permissions(&self, tenant_id: &str) -> PermissionMap {
        let cache_key = tenant_id.to_string();

        if let Some(cached) = self.cache.get(&cache_key) {
            return cached;
        }

        match self.fetch_permissions(tenant_id).await {
            Ok(perms) => {
                self.cache.insert(cache_key, perms.clone());
                perms
            }
            Err(e) => {
                warn!(
                    tenant_id = %tenant_id,
                    error = %e,
                    "Failed to fetch tool permissions — defaulting to allow-all"
                );
                // Return empty map (default-allow) but don't cache the failure
                HashMap::new()
            }
        }
    }

    /// Fetch all permissions for a tenant from CP-API.
    async fn fetch_permissions(&self, tenant_id: &str) -> Result<PermissionMap, String> {
        let url = format!(
            "{}/v1/tenants/{}/tool-permissions?page_size=100",
            self.base_url, tenant_id
        );

        debug!(tenant_id = %tenant_id, url = %url, "Fetching tool permissions from CP-API");

        let resp = self
            .client
            .get(&url)
            .header("X-Tenant-ID", tenant_id)
            // Internal call — use gateway key if available, no user auth needed
            .timeout(Duration::from_secs(5))
            .send()
            .await
            .map_err(|e| format!("HTTP error: {e}"))?;

        if !resp.status().is_success() {
            let status = resp.status().as_u16();
            // 404 = no permissions configured = allow-all
            if status == 404 {
                debug!(tenant_id = %tenant_id, "No tool permissions configured (404)");
                return Ok(HashMap::new());
            }
            let body = resp.text().await.unwrap_or_default();
            return Err(format!("CP-API returned {status}: {body}"));
        }

        let list: PermissionListResponse =
            resp.json().await.map_err(|e| format!("Parse error: {e}"))?;

        // Build permission map: tool_name → allowed
        // If ANY server denies the tool, it's denied (matches CP-API logic)
        let mut map = HashMap::new();
        for item in &list.items {
            let entry = map.entry(item.tool_name.clone()).or_insert(true);
            if !item.allowed {
                *entry = false;
            }
        }

        debug!(
            tenant_id = %tenant_id,
            total = list.total,
            denied_count = map.values().filter(|v| !**v).count(),
            "Loaded tool permissions"
        );

        Ok(map)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use wiremock::matchers::{method, path_regex};
    use wiremock::{Mock, MockServer, ResponseTemplate};

    #[tokio::test]
    async fn test_default_allow_when_no_permissions() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path_regex("/v1/tenants/.*/tool-permissions"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "items": [],
                "total": 0,
                "page": 1,
                "page_size": 100
            })))
            .mount(&server)
            .await;

        let svc = ToolPermissionService::new(Client::new(), &server.uri(), Duration::from_secs(60));

        assert!(svc.is_tool_allowed("tenant1", "any_tool").await);
    }

    #[tokio::test]
    async fn test_denied_tool() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path_regex("/v1/tenants/.*/tool-permissions"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "items": [
                    {"mcp_server_id": "srv1", "tool_name": "blocked_tool", "allowed": false},
                    {"mcp_server_id": "srv1", "tool_name": "ok_tool", "allowed": true}
                ],
                "total": 2,
                "page": 1,
                "page_size": 100
            })))
            .mount(&server)
            .await;

        let svc = ToolPermissionService::new(Client::new(), &server.uri(), Duration::from_secs(60));

        assert!(!svc.is_tool_allowed("tenant1", "blocked_tool").await);
        assert!(svc.is_tool_allowed("tenant1", "ok_tool").await);
        assert!(svc.is_tool_allowed("tenant1", "unknown_tool").await);
    }

    #[tokio::test]
    async fn test_permissive_on_error() {
        // No mock server → connection refused → should default to allow
        let svc = ToolPermissionService::new(
            Client::new(),
            "http://127.0.0.1:1",
            Duration::from_secs(60),
        );

        assert!(svc.is_tool_allowed("tenant1", "any_tool").await);
    }

    #[tokio::test]
    async fn test_cache_hit() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path_regex("/v1/tenants/.*/tool-permissions"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "items": [
                    {"mcp_server_id": "s1", "tool_name": "cached_tool", "allowed": false}
                ],
                "total": 1,
                "page": 1,
                "page_size": 100
            })))
            .expect(1) // Only one fetch, second call hits cache
            .mount(&server)
            .await;

        let svc = ToolPermissionService::new(Client::new(), &server.uri(), Duration::from_secs(60));

        assert!(!svc.is_tool_allowed("tenant1", "cached_tool").await);
        assert!(!svc.is_tool_allowed("tenant1", "cached_tool").await);
    }
}
