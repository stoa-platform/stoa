//! Tenant Tool Permission Service
//!
//! Fetches and caches tenant tool permissions from the Control Plane API.
//! Eliminates the circular proxy pattern where gateway → CP-API → gateway
//! was adding ~200-300ms of unnecessary latency per tool call.
//!
//! Missing or stale policy denies. A complete fresh policy carries the CP default explicitly.

use super::ToolProxyClient;
use moka::sync::Cache;
use reqwest::Client;
use serde::Deserialize;
use std::collections::{HashMap, HashSet};
use std::sync::{Arc, RwLock};
use std::time::{Duration, Instant};
use tracing::{debug, warn};

/// A single tool permission entry from CP-API.
#[derive(Debug, Clone, Deserialize)]
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
    #[serde(default)]
    page: Option<usize>,
    #[serde(default)]
    default_allowed: bool,
}

#[derive(Debug, Clone)]
pub struct PermissionRules {
    overrides: HashMap<String, bool>,
    default_allowed: bool,
}

impl PermissionRules {
    fn allows(&self, tool: &str) -> bool {
        self.overrides
            .get(tool)
            .copied()
            .unwrap_or(self.default_allowed)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PermissionDenyReason {
    PermissionAbsent,
    PermissionCacheExpired,
    CpUnreachable,
    CpUnauthorized,
}

impl PermissionDenyReason {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::PermissionAbsent => "permission_absent",
            Self::PermissionCacheExpired => "permission_cache_expired",
            Self::CpUnreachable => "cp_unreachable",
            Self::CpUnauthorized => "cp_unauthorized",
        }
    }
}

pub enum PermissionState {
    Fresh {
        rules: PermissionRules,
        fetched_at: Instant,
    },
    Stale {
        rules: PermissionRules,
        expired_at: Instant,
    },
    Unavailable {
        reason: PermissionDenyReason,
    },
}

impl PermissionState {
    fn deny_reason(&self, tool_name: &str) -> Option<PermissionDenyReason> {
        match self {
            Self::Fresh { rules, .. } if rules.allows(tool_name) => None,
            Self::Fresh { .. } => Some(PermissionDenyReason::PermissionAbsent),
            Self::Stale { .. } => Some(PermissionDenyReason::PermissionCacheExpired),
            Self::Unavailable { reason } => Some(*reason),
        }
    }
}

#[derive(Debug, Clone)]
struct CachedPermissions {
    rules: PermissionRules,
    fetched_at: Instant,
    expires_at: Instant,
}

/// Service that checks tenant tool permissions by fetching from CP-API
/// and caching locally with a configurable TTL.
#[derive(Clone)]
pub struct ToolPermissionService {
    client: Client,
    base_url: String,
    auth: Option<Arc<ToolProxyClient>>,
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
            auth: None,
            cache_ttl,
            cache: Arc::new(Cache::builder().max_capacity(10_000).build()),
            last_failure: Arc::new(RwLock::new(None)),
        }
    }

    /// Authenticate with the gateway service account.
    pub fn with_auth(mut self, auth: Arc<ToolProxyClient>) -> Self {
        self.auth = Some(auth);
        self
    }

    /// Check if a tool is allowed for a tenant.
    ///
    /// Uses only a complete fresh policy, including the CP default and overrides.
    /// Missing, stale, or unavailable policy denies.
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
        let mut expired_entry: Option<(PermissionRules, Instant)> = None;

        if let Some(cached) = self.cache.get(&cache_key) {
            if Instant::now() <= cached.expires_at {
                return PermissionState::Fresh {
                    rules: cached.rules,
                    fetched_at: cached.fetched_at,
                };
            }
            // Expired: drop the entry and attempt a refetch before deciding.
            self.cache.invalidate(&cache_key);
            expired_entry = Some((cached.rules, cached.expires_at));
        }

        match self.fetch_permissions(tenant_id).await {
            Ok(rules) => {
                let fetched_at = Instant::now();
                let cached = CachedPermissions {
                    rules: rules.clone(),
                    fetched_at,
                    expires_at: fetched_at + self.cache_ttl,
                };
                self.cache.insert(cache_key, cached);
                PermissionState::Fresh { rules, fetched_at }
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
                    Some((rules, expired_at)) => PermissionState::Stale { rules, expired_at },
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
    ) -> Result<PermissionRules, PermissionDenyReason> {
        // Only a signing-key (private_key_jwt) service identity reads permissions.
        let auth = self
            .auth
            .as_ref()
            .filter(|auth| auth.uses_private_key_jwt())
            .ok_or(PermissionDenyReason::CpUnauthorized)?;
        let url = format!(
            "{}/v1/tenants/{}/tool-permissions",
            self.base_url, tenant_id
        );
        let mut token = auth
            .get_token()
            .await
            .map_err(|_| PermissionDenyReason::CpUnauthorized)?;
        let mut refreshed = false;
        let mut page = 1usize;
        let mut expected_total = None;
        let mut default_allowed = None;
        let mut received = 0usize;
        let mut seen = HashSet::new();
        let mut overrides = HashMap::new();
        loop {
            let response = self
                .client
                .get(&url)
                .query(&[("page_size", 100usize), ("page", page)])
                .bearer_auth(&token)
                .timeout(Duration::from_secs(5))
                .send()
                .await
                .map_err(|_| PermissionDenyReason::CpUnreachable)?;
            if response.status() == reqwest::StatusCode::UNAUTHORIZED && !refreshed {
                auth.invalidate_token(&token);
                token = auth
                    .get_token()
                    .await
                    .map_err(|_| PermissionDenyReason::CpUnauthorized)?;
                refreshed = true;
                continue;
            }
            match response.status().as_u16() {
                401 | 403 => return Err(PermissionDenyReason::CpUnauthorized),
                404 => return Err(PermissionDenyReason::PermissionAbsent),
                _ if !response.status().is_success() => {
                    return Err(PermissionDenyReason::CpUnreachable)
                }
                _ => {}
            }
            let list: PermissionListResponse = response
                .json()
                .await
                .map_err(|_| PermissionDenyReason::CpUnreachable)?;
            if list.page.is_some_and(|actual| actual != page)
                || expected_total.is_some_and(|total| total != list.total)
                || default_allowed.is_some_and(|allowed| allowed != list.default_allowed)
                || list.total > 100_000
                || (list.page.is_none() && list.total > list.items.len())
            {
                return Err(PermissionDenyReason::CpUnreachable);
            }
            expected_total = Some(list.total);
            default_allowed = Some(list.default_allowed);
            let page_len = list.items.len();
            for item in list.items {
                if !seen.insert((item.mcp_server_id, item.tool_name.clone())) {
                    return Err(PermissionDenyReason::CpUnreachable);
                }
                let entry = overrides.entry(item.tool_name).or_insert(true);
                *entry &= item.allowed;
            }
            received += page_len;
            if received > list.total || (received < list.total && page_len == 0) {
                return Err(PermissionDenyReason::CpUnreachable);
            }
            if received == list.total {
                debug!(tenant_id = %tenant_id, total = received, "Loaded complete tool permissions");
                return Ok(PermissionRules {
                    overrides,
                    default_allowed: list.default_allowed,
                });
            }
            page += 1;
            if page > 1000 {
                return Err(PermissionDenyReason::CpUnreachable);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use wiremock::matchers::{method, path, path_regex};
    use wiremock::{Mock, MockServer, ResponseTemplate};

    async fn authenticated_service(server: &MockServer, ttl: Duration) -> ToolPermissionService {
        Mock::given(method("POST"))
            .and(path("/token"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "access_token": "fixture-service-access", "expires_in": 300
            })))
            .mount(server)
            .await;
        ToolPermissionService::new(Client::new(), &server.uri(), ttl)
            .with_auth(Arc::new(service_client(server, service_key_path())))
    }

    /// Test signing key written once to a process-wide temporary directory.
    fn service_key_path() -> std::path::PathBuf {
        static KEY: std::sync::OnceLock<std::path::PathBuf> = std::sync::OnceLock::new();
        KEY.get_or_init(|| {
            let dir = tempfile::tempdir().unwrap().keep();
            let path = dir.join("service-key.pem");
            std::fs::write(&path, crate::auth::jwt::tests::test_signing_pem()).unwrap();
            path
        })
        .clone()
    }

    fn service_client(server: &MockServer, key_path: std::path::PathBuf) -> ToolProxyClient {
        ToolProxyClient::new(
            &server.uri(),
            Some(crate::control_plane::OidcConfig::new(
                format!("{}/token", server.uri()),
                "fixture-service".into(),
                crate::control_plane::ClientCredential::PrivateKeyJwt {
                    key_path,
                    key_id: None,
                },
            )),
        )
    }

    #[tokio::test]
    async fn permissions_require_private_key_jwt_service_identity() {
        let server = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/token"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "access_token": "fixture-service-access", "expires_in": 300
            })))
            .mount(&server)
            .await;
        Mock::given(method("GET"))
            .and(path_regex(r"/v1/tenants/.+/tool-permissions"))
            .respond_with(permissions_response(serde_json::json!([
                {"mcp_server_id": "s1", "tool_name": "allowed_tool", "allowed": true}
            ])))
            .mount(&server)
            .await;
        let secret_client = ToolProxyClient::new(
            &server.uri(),
            Some(crate::control_plane::OidcConfig::new(
                format!("{}/token", server.uri()),
                "fixture-service".into(),
                crate::control_plane::ClientCredential::Secret("fixture-only".into()),
            )),
        );
        let svc = ToolPermissionService::new(Client::new(), &server.uri(), Duration::from_secs(60))
            .with_auth(Arc::new(secret_client));
        assert!(!svc.is_tool_allowed("tenant1", "allowed_tool").await);
        assert_eq!(svc.readiness_failure_reason(), Some("cp_unauthorized"));
        assert!(server.received_requests().await.unwrap().is_empty());

        let svc = authenticated_service(&server, Duration::from_secs(60)).await;
        assert!(svc.is_tool_allowed("tenant1", "allowed_tool").await);
    }

    #[tokio::test]
    async fn permissions_default_to_deny_without_explicit_allow() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path_regex(r"/v1/tenants/.+/tool-permissions"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "items": [{"mcp_server_id": "s1", "tool_name": "allowed_tool", "allowed": true}],
                "total": 1
            })))
            .mount(&server)
            .await;
        let svc = authenticated_service(&server, Duration::from_secs(60)).await;
        assert!(svc.is_tool_allowed("tenant1", "allowed_tool").await);
        assert!(!svc.is_tool_allowed("tenant1", "unlisted_tool").await);
    }

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

        let svc = authenticated_service(&server, Duration::from_secs(60)).await;

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

        let svc = authenticated_service(&server, Duration::from_secs(60)).await;

        assert!(!svc.is_tool_allowed("tenant1", "unknown_tool").await);
    }

    // regression for CAB-2227
    #[tokio::test]
    async fn test_tool_permissions_cp_unreachable_denies() {
        let server = MockServer::start().await;
        let mut svc = authenticated_service(&server, Duration::from_secs(60)).await;
        svc.base_url = "http://127.0.0.1:1".to_string();
        assert!(!svc.is_tool_allowed("tenant1", "any_tool").await);
        assert!(server
            .received_requests()
            .await
            .unwrap()
            .iter()
            .any(|request| request.url.path() == "/token"));
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

        let svc = authenticated_service(&server, Duration::from_millis(1)).await;

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

        let svc = authenticated_service(&server, Duration::from_millis(1)).await;

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

        let svc = authenticated_service(&server, Duration::from_secs(60)).await;

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

        let svc = authenticated_service(&server, Duration::from_secs(60)).await;

        assert!(!svc.is_tool_allowed("tenant1", "cached_tool").await);
        assert!(!svc.is_tool_allowed("tenant1", "cached_tool").await);
    }

    #[tokio::test]
    async fn permissions_pagination_reads_all_pages_and_default() {
        use wiremock::matchers::{header, query_param};
        let server = MockServer::start().await;
        let service = authenticated_service(&server, Duration::from_secs(60)).await;
        for (page, server_id, allowed) in [(1, "first", true), (2, "second", false)] {
            Mock::given(method("GET")).and(path("/v1/tenants/tenant-a/tool-permissions"))
                .and(query_param("page", page.to_string()))
                .and(header("Authorization", "Bearer fixture-service-access"))
                .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                    "items": [{"mcp_server_id": server_id, "tool_name": "blocked", "allowed": allowed}],
                    "total": 2, "page": page, "default_allowed": true
                }))).expect(1).mount(&server).await;
        }
        assert!(!service.is_tool_allowed("tenant-a", "blocked").await);
        assert!(service.is_tool_allowed("tenant-a", "ordinary_read").await);
    }

    #[tokio::test]
    async fn permissions_401_refreshes_service_token_once() {
        use wiremock::matchers::header;
        let server = MockServer::start().await;
        let service = authenticated_service(&server, Duration::from_secs(60)).await;
        Mock::given(method("POST"))
            .and(path("/token"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "access_token": "rejected-service-token", "expires_in": 300
            })))
            .with_priority(1)
            .up_to_n_times(1)
            .mount(&server)
            .await;
        Mock::given(method("GET"))
            .and(path("/v1/tenants/tenant-a/tool-permissions"))
            .and(header("Authorization", "Bearer rejected-service-token"))
            .respond_with(ResponseTemplate::new(401))
            .expect(1)
            .mount(&server)
            .await;
        Mock::given(method("GET"))
            .and(path("/v1/tenants/tenant-a/tool-permissions"))
            .and(header("Authorization", "Bearer fixture-service-access"))
            .respond_with(permissions_response(serde_json::json!([{
                "mcp_server_id": "fixture", "tool_name": "allowed", "allowed": true
            }])))
            .expect(1)
            .mount(&server)
            .await;
        assert!(service.is_tool_allowed("tenant-a", "allowed").await);
        let requests = server.received_requests().await.unwrap();
        assert_eq!(
            requests.iter().filter(|r| r.url.path() == "/token").count(),
            2
        );
        assert!(requests
            .iter()
            .filter(|r| r.url.path().ends_with("/tool-permissions"))
            .all(|r| r.headers.contains_key("Authorization")));
    }

    #[tokio::test]
    async fn permissions_403_is_final() {
        let server = MockServer::start().await;
        let service = authenticated_service(&server, Duration::from_secs(60)).await;
        Mock::given(method("GET"))
            .and(path("/v1/tenants/tenant-a/tool-permissions"))
            .respond_with(ResponseTemplate::new(403))
            .expect(1)
            .mount(&server)
            .await;
        assert!(!service.is_tool_allowed("tenant-a", "allowed").await);
        assert_eq!(service.readiness_failure_reason(), Some("cp_unauthorized"));
        assert_eq!(
            server
                .received_requests()
                .await
                .unwrap()
                .iter()
                .filter(|r| r.url.path() == "/token")
                .count(),
            1
        );
    }
}
