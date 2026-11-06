//! Tenant Tool Permission Service
//!
//! Fetches and caches tenant tool permissions from the Control Plane API.
//! Eliminates the circular proxy pattern where gateway → CP-API → gateway
//! was adding ~200-300ms of unnecessary latency per tool call.
//!
//! Only an explicit allow in a complete fresh policy permits a tool call.
//! After boot nothing is allowed, and readiness stays down, until a fresh policy loads (ADR-070).

use super::policy_trust::PolicyTrustStore;
use super::ToolProxyClient;
use moka::sync::Cache;
use reqwest::Client;
use serde::Deserialize;
use std::collections::{HashMap, HashSet};
use std::sync::{Arc, RwLock};
use std::time::{Duration, Instant};
use tracing::{debug, warn};

/// Hard cap on the permission cache TTL and the readiness window (ADR-070 §4, A4).
pub const MAX_POLICY_AGE: Duration = Duration::from_secs(3600);
/// Retry interval while no policy has been loaded since boot.
const BOOT_RETRY_INTERVAL: Duration = Duration::from_secs(5);

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
}

impl PermissionRules {
    fn allows(&self, tool: &str) -> bool {
        self.overrides.get(tool).copied().unwrap_or(false)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PermissionDenyReason {
    PermissionAbsent,
    PermissionCacheExpired,
    CpUnreachable,
    CpUnauthorized,
    /// The pinned signer trust set is missing or was refused.
    TrustSetNotLoaded,
}

impl PermissionDenyReason {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::PermissionAbsent => "permission_absent",
            Self::PermissionCacheExpired => "permission_cache_expired",
            Self::CpUnreachable => "cp_unreachable",
            Self::CpUnauthorized => "cp_unauthorized",
            Self::TrustSetNotLoaded => "trust_set_not_loaded",
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
    /// Decide a call requested as `requested` that resolved to `canonical`.
    /// Both names need an explicit allow; a deny on either wins.
    fn deny_reason(&self, requested: &str, canonical: &str) -> Option<PermissionDenyReason> {
        match self {
            Self::Fresh { rules, .. } if rules.allows(requested) && rules.allows(canonical) => None,
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
    trust: Option<Arc<PolicyTrustStore>>,
    cache_ttl: Duration,
    cache: Arc<Cache<String, CachedPermissions>>,
    last_failure: Arc<RwLock<Option<PermissionDenyReason>>>,
    /// Last successful complete policy load for any tenant since boot.
    policy_loaded_at: Arc<RwLock<Option<Instant>>>,
    max_policy_age: Duration,
}

impl ToolPermissionService {
    /// Create a new service.
    ///
    /// - `client`: shared HTTP client with connection pooling
    /// - `base_url`: Control Plane API base URL (e.g., `http://control-plane-api:8000`)
    /// - `cache_ttl`: per-tenant cache lifetime (default: 60s), capped at [`MAX_POLICY_AGE`]
    pub fn new(client: Client, base_url: &str, cache_ttl: Duration) -> Self {
        if cache_ttl > MAX_POLICY_AGE {
            warn!(ttl_secs = cache_ttl.as_secs(), "Policy cache TTL capped");
        }
        Self {
            client,
            base_url: base_url.trim_end_matches('/').to_string(),
            auth: None,
            trust: None,
            cache_ttl: cache_ttl.min(MAX_POLICY_AGE),
            cache: Arc::new(Cache::builder().max_capacity(10_000).build()),
            last_failure: Arc::new(RwLock::new(None)),
            policy_loaded_at: Arc::new(RwLock::new(None)),
            max_policy_age: MAX_POLICY_AGE,
        }
    }

    /// Authenticate with the gateway service account.
    pub fn with_auth(mut self, auth: Arc<ToolProxyClient>) -> Self {
        self.auth = Some(auth);
        self
    }

    /// While the pinned signer trust set is not loaded, every call is denied
    /// without contacting the Control Plane.
    pub fn with_trust_store(mut self, trust: Option<Arc<PolicyTrustStore>>) -> Self {
        self.trust = trust;
        self
    }

    /// A configured signer trust set is missing or was refused: deny everything.
    pub fn trust_set_not_loaded(&self) -> bool {
        self.trust.as_ref().is_some_and(|t| t.current().is_none())
    }

    /// Check if a tool is allowed for a tenant.
    ///
    /// Requires an explicit allow in a complete fresh policy.
    /// Missing permissions and stale or unavailable policy deny.
    pub async fn is_tool_allowed(&self, tenant_id: &str, tool_name: &str) -> bool {
        self.is_tool_call_allowed(tenant_id, tool_name, tool_name)
            .await
    }

    /// Check a call requested as `requested_name` that the tool registry
    /// resolved to `canonical_name` (they differ only for deprecated aliases).
    ///
    /// The canonical tool is the one that executes, so it needs its own
    /// explicit allow; the requested name keeps its allow requirement so an
    /// alias can never widen access. A deny on either name wins.
    pub async fn is_tool_call_allowed(
        &self,
        tenant_id: &str,
        requested_name: &str,
        canonical_name: &str,
    ) -> bool {
        let state = if self.trust.as_ref().is_some_and(|t| t.current().is_none()) {
            PermissionState::Unavailable {
                reason: PermissionDenyReason::TrustSetNotLoaded,
            }
        } else {
            let state = self.get_permission_state(tenant_id).await;
            self.record_state(&state);
            state
        };

        match state.deny_reason(requested_name, canonical_name) {
            None => true,
            Some(reason) => {
                warn!(
                    audit_event = "tool_call_denied",
                    tenant_id = %tenant_id,
                    tool_name = %canonical_name,
                    requested_name = %requested_name,
                    reason = %reason.as_str(),
                    "Tool permission fail-closed deny"
                );
                false
            }
        }
    }

    pub fn readiness_failure_reason(&self) -> Option<&'static str> {
        if self.trust.as_ref().is_some_and(|t| t.current().is_none()) {
            return Some(PermissionDenyReason::TrustSetNotLoaded.as_str());
        }
        self.last_failure
            .read()
            .ok()
            .and_then(|reason| reason.map(PermissionDenyReason::as_str))
    }

    /// Why `/ready` must fail: no policy loaded since boot, or the last load is
    /// older than the hard cap (ADR-070 §4). Per-tenant denials never trip it.
    /// A configured signer trust set that is not loaded fails it as well.
    pub fn policy_readiness_failure(&self) -> Option<&'static str> {
        if self.trust.as_ref().is_some_and(|t| t.current().is_none()) {
            return Some(PermissionDenyReason::TrustSetNotLoaded.as_str());
        }
        match self.policy_loaded_at.read().ok().and_then(|at| *at) {
            None => Some("policy_not_loaded"),
            Some(at) if at.elapsed() > self.max_policy_age => Some("policy_stale"),
            Some(_) => None,
        }
    }

    /// Load a tenant's policy now; only a complete fresh policy counts as loaded.
    pub async fn load_policy(&self, tenant_id: &str) -> Result<(), PermissionDenyReason> {
        let state = self.get_permission_state(tenant_id).await;
        self.record_state(&state);
        match state {
            PermissionState::Fresh { .. } => Ok(()),
            PermissionState::Stale { .. } => Err(PermissionDenyReason::PermissionCacheExpired),
            PermissionState::Unavailable { reason } => Err(reason),
        }
    }

    /// Load the given tenants' policies at startup (always a fresh fetch, ADR-070
    /// A7) and keep them refreshed, recovering once the Control Plane is back.
    pub fn spawn_policy_refresher(self: &Arc<Self>, tenants: Vec<String>) {
        let service = Arc::clone(self);
        tokio::spawn(async move {
            loop {
                for tenant_id in &tenants {
                    if let Err(reason) = service.load_policy(tenant_id).await {
                        debug!(tenant_id = %tenant_id, reason = %reason.as_str(), "Startup policy load failed");
                    }
                }
                let interval = match service.policy_readiness_failure() {
                    Some(_) => BOOT_RETRY_INTERVAL,
                    None => service.cache_ttl,
                };
                tokio::time::sleep(interval).await;
            }
        });
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
                if let Ok(mut loaded_at) = self.policy_loaded_at.write() {
                    *loaded_at = Some(fetched_at);
                }
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
                return Ok(PermissionRules { overrides });
            }
            page += 1;
            if page > 1000 {
                return Err(PermissionDenyReason::CpUnreachable);
            }
        }
    }
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;
    use wiremock::matchers::{method, path, path_regex};
    use wiremock::{Mock, MockServer, ResponseTemplate};

    pub(crate) async fn authenticated_service(
        server: &MockServer,
        ttl: Duration,
    ) -> ToolPermissionService {
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
    async fn regression_permissions_pagination_requires_explicit_allow() {
        use wiremock::matchers::{header, query_param};
        let server = MockServer::start().await;
        let service = authenticated_service(&server, Duration::from_secs(60)).await;
        for (page, server_id, allowed) in [(1, "first", true), (2, "second", false)] {
            let mut items = vec![serde_json::json!({
                "mcp_server_id": server_id, "tool_name": "blocked", "allowed": allowed
            })];
            if page == 1 {
                items.push(serde_json::json!({
                    "mcp_server_id": server_id, "tool_name": "allowed", "allowed": true
                }));
            }
            Mock::given(method("GET"))
                .and(path("/v1/tenants/tenant-a/tool-permissions"))
                .and(query_param("page", page.to_string()))
                .and(header("Authorization", "Bearer fixture-service-access"))
                .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                    "items": items,
                    "total": 3, "page": page, "default_allowed": true
                })))
                .expect(1)
                .mount(&server)
                .await;
        }
        assert!(!service.is_tool_allowed("tenant-a", "blocked").await);
        assert!(service.is_tool_allowed("tenant-a", "allowed").await);
        assert!(!service.is_tool_allowed("tenant-a", "ordinary_read").await);
    }

    #[tokio::test]
    async fn regression_empty_permissions_deny_despite_cp_default_allow() {
        let server = MockServer::start().await;
        let service = authenticated_service(&server, Duration::from_secs(60)).await;
        Mock::given(method("GET"))
            .and(path("/v1/tenants/tenant-a/tool-permissions"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "items": [], "total": 0, "page": 1, "default_allowed": true
            })))
            .expect(1)
            .mount(&server)
            .await;

        assert!(!service.is_tool_allowed("tenant-a", "unlisted").await);
    }

    #[tokio::test]
    async fn regression_incomplete_permissions_deny_partial_allow() {
        use wiremock::matchers::query_param;
        let server = MockServer::start().await;
        let service = authenticated_service(&server, Duration::from_secs(60)).await;
        Mock::given(method("GET"))
            .and(path("/v1/tenants/tenant-a/tool-permissions"))
            .and(query_param("page", "1"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "items": [{"mcp_server_id": "first", "tool_name": "allowed", "allowed": true}],
                "total": 2, "page": 1, "default_allowed": true
            })))
            .expect(1)
            .mount(&server)
            .await;
        Mock::given(method("GET"))
            .and(path("/v1/tenants/tenant-a/tool-permissions"))
            .and(query_param("page", "2"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "items": [], "total": 2, "page": 2, "default_allowed": true
            })))
            .expect(1)
            .mount(&server)
            .await;

        assert!(!service.is_tool_allowed("tenant-a", "allowed").await);
        assert_eq!(service.readiness_failure_reason(), Some("cp_unreachable"));
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

    /// One-key trust set built from the published RFC 8032 §7.1 public key.
    pub(crate) const VALID_JWKS: &str = r#"{"keys":[{"kty":"OKP","crv":"Ed25519","alg":"EdDSA","kid":"k0","x":"11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo"}]}"#;

    #[tokio::test]
    async fn trust_set_not_loaded_denies_before_contacting_cp() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .respond_with(permissions_response(serde_json::json!([
                {"mcp_server_id": "srv1", "tool_name": "ok_tool", "allowed": true}
            ])))
            .mount(&server)
            .await;
        let dir = tempfile::tempdir().unwrap();
        let trust = PolicyTrustStore::open(dir.path().join("trust.json"));
        let svc = authenticated_service(&server, Duration::from_secs(60))
            .await
            .with_trust_store(Some(trust.clone()));
        assert_eq!(svc.readiness_failure_reason(), Some("trust_set_not_loaded"));
        assert!(!svc.is_tool_allowed("tenant1", "ok_tool").await);
        assert!(server.received_requests().await.unwrap().is_empty());

        std::fs::write(dir.path().join("trust.json"), VALID_JWKS).unwrap();
        assert_eq!(trust.reload(), Ok(1));
        assert_eq!(svc.readiness_failure_reason(), None);
        assert!(svc.is_tool_allowed("tenant1", "ok_tool").await);
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

    #[tokio::test]
    async fn regression_alias_allow_does_not_widen_canonical_deny() {
        // The requested name is an allowed alias; the canonical tool it
        // resolves to is denied or unlisted. The call must be denied.
        for canonical in [
            Some(
                serde_json::json!({"mcp_server_id": "s1", "tool_name": "new_tool", "allowed": false}),
            ),
            None,
        ] {
            let server = MockServer::start().await;
            let mut items = vec![serde_json::json!(
                {"mcp_server_id": "s1", "tool_name": "old_tool", "allowed": true}
            )];
            items.extend(canonical);
            Mock::given(method("GET"))
                .and(path_regex(r"/v1/tenants/.+/tool-permissions"))
                .respond_with(permissions_response(serde_json::Value::Array(items)))
                .mount(&server)
                .await;
            let svc = authenticated_service(&server, Duration::from_secs(60)).await;
            assert!(
                !svc.is_tool_call_allowed("tenant1", "old_tool", "new_tool")
                    .await
            );
            assert!(svc.is_tool_allowed("tenant1", "old_tool").await);
        }
    }

    #[tokio::test]
    async fn regression_alias_explicit_deny_wins_over_canonical_allow() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path_regex(r"/v1/tenants/.+/tool-permissions"))
            .respond_with(permissions_response(serde_json::json!([
                {"mcp_server_id": "s1", "tool_name": "old_tool", "allowed": false},
                {"mcp_server_id": "s1", "tool_name": "new_tool", "allowed": true}
            ])))
            .mount(&server)
            .await;
        let svc = authenticated_service(&server, Duration::from_secs(60)).await;
        assert!(
            !svc.is_tool_call_allowed("tenant1", "old_tool", "new_tool")
                .await
        );
        // The canonical name keeps working under its own allow.
        assert!(
            svc.is_tool_call_allowed("tenant1", "new_tool", "new_tool")
                .await
        );
        assert!(svc.is_tool_allowed("tenant1", "new_tool").await);
    }

    /// Serve `reply` to exactly one `GET /v1/tenants/*/tool-permissions` request.
    pub(crate) async fn serve_policy_once(server: &MockServer, reply: ResponseTemplate) {
        Mock::given(method("GET"))
            .and(path_regex("/v1/tenants/.*/tool-permissions"))
            .respond_with(reply)
            .up_to_n_times(1)
            .mount(server)
            .await;
    }

    /// Complete policy whose only explicit allow is `ok_tool`.
    pub(crate) fn ok_tool_policy() -> ResponseTemplate {
        permissions_response(serde_json::json!([
            {"mcp_server_id": "srv1", "tool_name": "ok_tool", "allowed": true}
        ]))
    }

    #[tokio::test]
    async fn regression_startup_without_control_plane_denies_and_blocks_readiness() {
        let server = MockServer::start().await;
        let mut svc = authenticated_service(&server, Duration::from_secs(60)).await;
        svc.base_url = "http://127.0.0.1:1".to_string();
        assert_eq!(svc.policy_readiness_failure(), Some("policy_not_loaded"));
        assert_eq!(
            svc.load_policy("tenant1").await,
            Err(PermissionDenyReason::CpUnreachable)
        );
        assert!(!svc.is_tool_allowed("tenant1", "any_tool").await);
        assert_eq!(svc.policy_readiness_failure(), Some("policy_not_loaded"));
    }

    #[tokio::test]
    async fn regression_first_policy_load_failure_then_success_opens_readiness() {
        let server = MockServer::start().await;
        serve_policy_once(&server, ResponseTemplate::new(503)).await;
        serve_policy_once(&server, ok_tool_policy()).await;
        let svc = authenticated_service(&server, Duration::from_secs(60)).await;

        assert_eq!(
            svc.load_policy("tenant1").await,
            Err(PermissionDenyReason::CpUnreachable)
        );
        assert_eq!(svc.policy_readiness_failure(), Some("policy_not_loaded"));

        assert_eq!(svc.load_policy("tenant1").await, Ok(()));
        assert_eq!(svc.policy_readiness_failure(), None);
        assert!(svc.is_tool_allowed("tenant1", "ok_tool").await);
        assert!(!svc.is_tool_allowed("tenant1", "other_tool").await);
    }

    #[tokio::test]
    async fn regression_stale_policy_denies_and_blocks_readiness() {
        let server = MockServer::start().await;
        serve_policy_once(&server, ok_tool_policy()).await;
        let mut svc = authenticated_service(&server, Duration::from_millis(1)).await;

        assert_eq!(svc.load_policy("tenant1").await, Ok(()));
        assert_eq!(svc.policy_readiness_failure(), None);
        // Tighten after the freshness assertion to avoid a 1 ms race after loading.
        svc.max_policy_age = Duration::from_millis(1);
        tokio::time::sleep(Duration::from_millis(20)).await;

        // Past the cap and no longer served: readiness fails and the call is denied as stale.
        assert_eq!(svc.policy_readiness_failure(), Some("policy_stale"));
        assert!(!svc.is_tool_allowed("tenant1", "ok_tool").await);
        assert_eq!(
            svc.readiness_failure_reason(),
            Some("permission_cache_expired")
        );
    }

    #[tokio::test]
    async fn regression_startup_refresher_loads_policy_before_first_call() {
        let server = MockServer::start().await;
        serve_policy_once(&server, ok_tool_policy()).await;
        let svc = Arc::new(authenticated_service(&server, Duration::from_secs(60)).await);
        svc.spawn_policy_refresher(vec!["tenant1".into()]);
        tokio::time::timeout(Duration::from_secs(5), async {
            while svc.policy_readiness_failure().is_some() {
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
        })
        .await
        .expect("startup loader must load the policy");
        // The first call is served from the warmed cache: still one fetch.
        assert!(svc.is_tool_allowed("tenant1", "ok_tool").await);
    }

    #[test]
    fn regression_cache_ttl_is_capped_at_hard_limit() {
        let svc = ToolPermissionService::new(Client::new(), "http://cp", MAX_POLICY_AGE * 2);
        assert_eq!(svc.cache_ttl, MAX_POLICY_AGE);
    }
}
