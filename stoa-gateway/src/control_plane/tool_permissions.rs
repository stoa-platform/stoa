//! Tenant Tool Permission Service
//!
//! Fetches and caches tenant tool permissions from the Control Plane API.
//! Eliminates the circular proxy pattern where gateway → CP-API → gateway
//! was adding ~200-300ms of unnecessary latency per tool call.
//!
//! Deny-by-default: if no fresh explicit allow exists for a tool, it is denied.

use moka::sync::Cache;
use reqwest::Client;
use serde::Deserialize;
use std::collections::{HashMap, HashSet};
use std::sync::{Arc, RwLock};
use std::time::{Duration, Instant};
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

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PermissionDenyReason {
    PermissionAbsent,
    PermissionCacheExpired,
    CpUnreachable,
}

impl PermissionDenyReason {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::PermissionAbsent => "permission_absent",
            Self::PermissionCacheExpired => "permission_cache_expired",
            Self::CpUnreachable => "cp_unreachable",
        }
    }
}

pub enum PermissionState {
    Fresh {
        allow_set: HashSet<String>,
        fetched_at: Instant,
    },
    Stale {
        allow_set: HashSet<String>,
        expired_at: Instant,
    },
    Unavailable {
        reason: PermissionDenyReason,
    },
}

impl PermissionState {
    fn deny_reason(&self, tool_name: &str) -> Option<PermissionDenyReason> {
        match self {
            Self::Fresh { allow_set, .. } if allow_set.contains(tool_name) => None,
            Self::Fresh { .. } => Some(PermissionDenyReason::PermissionAbsent),
            Self::Stale { .. } => Some(PermissionDenyReason::PermissionCacheExpired),
            Self::Unavailable { reason } => Some(*reason),
        }
    }
}

#[derive(Debug, Clone)]
struct CachedPermissions {
    allow_set: HashSet<String>,
    fetched_at: Instant,
    expires_at: Instant,
}

/// Service that checks tenant tool permissions by fetching from CP-API
/// and caching locally with a configurable TTL.
#[derive(Clone)]
pub struct ToolPermissionService {
    client: Client,
    base_url: String,
    cache_ttl: Duration,
    cache: Arc<Cache<String, CachedPermissions>>,
    last_failure: Arc<RwLock<Option<PermissionDenyReason>>>,
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
            cache_ttl,
            cache: Arc::new(Cache::builder().max_capacity(10_000).build()),
            last_failure: Arc::new(RwLock::new(None)),
        }
    }

    /// Check if a tool is allowed for a tenant.
    ///
    /// Deny-by-default: returns `true` only when the tool is present in a fresh
    /// explicit allow set. Missing, stale, or unavailable permissions deny.
    pub async fn is_tool_allowed(&self, tenant_id: &str, tool_name: &str) -> bool {
        let state = self.get_permission_state(tenant_id).await;
        self.record_state(&state);

        match state.deny_reason(tool_name) {
            None => true,
            Some(reason) => {
                warn!(
                    audit_event = "tool_call_denied",
                    tenant_id = %tenant_id,
                    tool_name = %tool_name,
                    reason = %reason.as_str(),
                    "Tool permission fail-closed deny"
                );
                false
            }
        }
    }

    pub fn readiness_failure_reason(&self) -> Option<&'static str> {
        self.last_failure
            .read()
            .ok()
            .and_then(|reason| reason.map(PermissionDenyReason::as_str))
    }

    /// Get (or fetch) the explicit permission state for a tenant.
    ///
    /// An expired cache entry does **not** deny on its own: while the
    /// Control Plane is reachable the entry is refetched so legitimate
    /// calls keep flowing across the TTL boundary. Only a *failed* refetch
    /// over expired data yields `Stale` (deny); a failed refetch with no
    /// prior data yields `Unavailable` (deny).
    async fn get_permission_state(&self, tenant_id: &str) -> PermissionState {
        let cache_key = tenant_id.to_string();

        // Prior allow set carried from an expired entry, so a failed
        // refetch can still surface `Stale` instead of losing the data.
        let mut expired_entry: Option<(HashSet<String>, Instant)> = None;

        if let Some(cached) = self.cache.get(&cache_key) {
            if Instant::now() <= cached.expires_at {
                return PermissionState::Fresh {
                    allow_set: cached.allow_set,
                    fetched_at: cached.fetched_at,
                };
            }
            // Expired: drop the entry and attempt a refetch before deciding.
            self.cache.invalidate(&cache_key);
            expired_entry = Some((cached.allow_set, cached.expires_at));
        }

        match self.fetch_permissions(tenant_id).await {
            Ok(allow_set) => {
                let fetched_at = Instant::now();
                let cached = CachedPermissions {
                    allow_set: allow_set.clone(),
                    fetched_at,
                    expires_at: fetched_at + self.cache_ttl,
                };
                self.cache.insert(cache_key, cached);
                PermissionState::Fresh {
                    allow_set,
                    fetched_at,
                }
            }
            Err(reason) => {
                warn!(
                    tenant_id = %tenant_id,
                    reason = %reason.as_str(),
                    "Failed to fetch tool permissions"
                );
                // A failed refetch over an expired entry still denies, but
                // as `Stale` (prior data exists) — distinct from a cold
                // `Unavailable`. Both deny and both surface in readiness.
                match expired_entry {
                    Some((allow_set, expired_at)) => PermissionState::Stale {
                        allow_set,
                        expired_at,
                    },
                    None => PermissionState::Unavailable { reason },
                }
            }
        }
    }

    fn record_state(&self, state: &PermissionState) {
        let failure = match state {
            PermissionState::Fresh { .. } => None,
            PermissionState::Stale { .. } => Some(PermissionDenyReason::PermissionCacheExpired),
            PermissionState::Unavailable { reason } => Some(*reason),
        };
        if let Ok(mut last_failure) = self.last_failure.write() {
            *last_failure = failure;
        }
    }

    /// Fetch all permissions for a tenant from CP-API.
    async fn fetch_permissions(
        &self,
        tenant_id: &str,
    ) -> Result<HashSet<String>, PermissionDenyReason> {
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
            .map_err(|_| PermissionDenyReason::CpUnreachable)?;

        if !resp.status().is_success() {
            let status = resp.status().as_u16();
            if status == 404 {
                return Err(PermissionDenyReason::PermissionAbsent);
            }
            return Err(PermissionDenyReason::CpUnreachable);
        }

        let list: PermissionListResponse = resp
            .json()
            .await
            .map_err(|_| PermissionDenyReason::CpUnreachable)?;

        // Build permission map: tool_name → allowed
        // If ANY server denies the tool, it's denied (matches CP-API logic)
        let mut map = HashMap::new();
        for item in &list.items {
            let entry = map.entry(item.tool_name.clone()).or_insert(true);
            if !item.allowed {
                *entry = false;
            }
        }
        let allow_set = map
            .into_iter()
            .filter_map(|(tool_name, allowed)| allowed.then_some(tool_name))
            .collect::<HashSet<_>>();

        debug!(
            tenant_id = %tenant_id,
            total = list.total,
            allowed_count = allow_set.len(),
            "Loaded tool permissions"
        );

        Ok(allow_set)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use wiremock::matchers::{method, path_regex};
    use wiremock::{Mock, MockServer, ResponseTemplate};

    fn permissions_response(items: serde_json::Value) -> ResponseTemplate {
        let total = items.as_array().map_or(0, |items| items.len());
        ResponseTemplate::new(200).set_body_json(serde_json::json!({
            "items": items,
            "total": total,
            "page": 1,
            "page_size": 100
        }))
    }

    // regression for CAB-2227
    #[tokio::test]
    async fn test_no_permissions_denies() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path_regex("/v1/tenants/.*/tool-permissions"))
            .respond_with(permissions_response(serde_json::json!([])))
            .mount(&server)
            .await;

        let svc = ToolPermissionService::new(Client::new(), &server.uri(), Duration::from_secs(60));

        assert!(!svc.is_tool_allowed("tenant1", "any_tool").await);
    }

    // regression for CAB-2227
    #[tokio::test]
    async fn test_tool_permissions_missing_tool_denies() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path_regex("/v1/tenants/.*/tool-permissions"))
            .respond_with(permissions_response(serde_json::json!([
                {"mcp_server_id": "srv1", "tool_name": "ok_tool", "allowed": true}
            ])))
            .mount(&server)
            .await;

        let svc = ToolPermissionService::new(Client::new(), &server.uri(), Duration::from_secs(60));

        assert!(!svc.is_tool_allowed("tenant1", "unknown_tool").await);
    }

    // regression for CAB-2227
    #[tokio::test]
    async fn test_tool_permissions_cp_unreachable_denies() {
        let svc = ToolPermissionService::new(
            Client::new(),
            "http://127.0.0.1:1",
            Duration::from_secs(60),
        );

        assert!(!svc.is_tool_allowed("tenant1", "any_tool").await);
    }

    // regression for CAB-2227
    #[tokio::test]
    async fn test_tool_permissions_expired_cache_denies() {
        let server = MockServer::start().await;
        // Serve the cold fetch once; the post-expiry refetch finds no
        // matching mock (404) — i.e. CP no longer returns the permissions.
        Mock::given(method("GET"))
            .and(path_regex("/v1/tenants/.*/tool-permissions"))
            .respond_with(permissions_response(serde_json::json!([
                {"mcp_server_id": "srv1", "tool_name": "ok_tool", "allowed": true}
            ])))
            .up_to_n_times(1)
            .expect(1)
            .mount(&server)
            .await;

        let svc =
            ToolPermissionService::new(Client::new(), &server.uri(), Duration::from_millis(1));

        // Cold fetch from a healthy CP populates the cache.
        assert!(svc.is_tool_allowed("tenant1", "ok_tool").await);
        tokio::time::sleep(Duration::from_millis(20)).await;

        // Cache expired AND the refetch fails: the gateway must stay
        // fail-closed and deny (Stale).
        assert!(!svc.is_tool_allowed("tenant1", "ok_tool").await);
    }

    // regression for CAB-2227
    #[tokio::test]
    async fn regression_tool_permissions_expired_cache_refetches_when_cp_reachable() {
        let server = MockServer::start().await;
        // CP stays healthy and keeps serving the same allow set across the
        // TTL boundary. Two fetches are expected: the cold one and the
        // post-expiry refetch.
        Mock::given(method("GET"))
            .and(path_regex("/v1/tenants/.*/tool-permissions"))
            .respond_with(permissions_response(serde_json::json!([
                {"mcp_server_id": "srv1", "tool_name": "ok_tool", "allowed": true}
            ])))
            .expect(2)
            .mount(&server)
            .await;

        let svc =
            ToolPermissionService::new(Client::new(), &server.uri(), Duration::from_millis(1));

        // Cold fetch — allowed.
        assert!(svc.is_tool_allowed("tenant1", "ok_tool").await);
        tokio::time::sleep(Duration::from_millis(20)).await;

        // Cache expired but CP is reachable: an expired entry must trigger a
        // refetch, not a spurious deny. The legitimate call still succeeds.
        assert!(svc.is_tool_allowed("tenant1", "ok_tool").await);
    }

    #[tokio::test]
    async fn test_denied_tool() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path_regex("/v1/tenants/.*/tool-permissions"))
            .respond_with(permissions_response(serde_json::json!([
                {"mcp_server_id": "srv1", "tool_name": "blocked_tool", "allowed": false},
                {"mcp_server_id": "srv1", "tool_name": "ok_tool", "allowed": true}
            ])))
            .mount(&server)
            .await;

        let svc = ToolPermissionService::new(Client::new(), &server.uri(), Duration::from_secs(60));

        assert!(!svc.is_tool_allowed("tenant1", "blocked_tool").await);
        assert!(svc.is_tool_allowed("tenant1", "ok_tool").await);
        assert!(!svc.is_tool_allowed("tenant1", "unknown_tool").await);
    }

    #[tokio::test]
    async fn test_cache_hit() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path_regex("/v1/tenants/.*/tool-permissions"))
            .respond_with(permissions_response(serde_json::json!([
                {"mcp_server_id": "s1", "tool_name": "cached_tool", "allowed": false}
            ])))
            .expect(1) // Only one fetch, second call hits cache
            .mount(&server)
            .await;

        let svc = ToolPermissionService::new(Client::new(), &server.uri(), Duration::from_secs(60));

        assert!(!svc.is_tool_allowed("tenant1", "cached_tool").await);
        assert!(!svc.is_tool_allowed("tenant1", "cached_tool").await);
    }
}
