//! Tenant Tool Permission Service
//!
//! Fetches and caches signed tenant tool policies from the Control Plane API.
//! Eliminates the circular proxy pattern where gateway → CP-API → gateway
//! was adding ~200-300ms of unnecessary latency per tool call.
//!
//! Only an explicit allow in a complete fresh policy permits a tool call.
//! After boot nothing is allowed, and readiness stays down, until a fresh policy loads (ADR-070).

use super::policy_artifact::{PolicyArtifactVerifier, VerifiedPolicyArtifact};
use super::policy_trust::PolicyTrustStore;
use super::ToolProxyClient;
use chrono::{DateTime, Utc};
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
/// Renew early enough for a bounded clock offset and the HTTP retry.
const POLICY_REFRESH_MARGIN: Duration = Duration::from_secs(30);
/// Same compact-JWS limit as the Control Plane signer.
const MAX_POLICY_BYTES: usize = 1024 * 1024;
const MAX_TRACKED_TENANTS: usize = 10_000;

/// A single tool permission entry from CP-API.
#[derive(Debug, Clone, Deserialize)]
struct PermissionItem {
    mcp_server: String,
    tool: String,
    allowed: bool,
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
    /// The signed policy is malformed, unverifiable or expired.
    PolicyArtifactInvalid,
}

impl PermissionDenyReason {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::PermissionAbsent => "permission_absent",
            Self::PermissionCacheExpired => "permission_cache_expired",
            Self::CpUnreachable => "cp_unreachable",
            Self::CpUnauthorized => "cp_unauthorized",
            Self::TrustSetNotLoaded => "trust_set_not_loaded",
            Self::PolicyArtifactInvalid => "policy_artifact_invalid",
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
    artifact: String,
    rules: PermissionRules,
    fetched_at: Instant,
    expires_at: Instant,
}

struct LoadedPolicy {
    tenant_id: String,
    artifact: String,
    fetched_at: Instant,
}

#[derive(Clone, Copy)]
struct PolicyIdentity {
    tenant_uuid: uuid::Uuid,
    version: u64,
}

impl PolicyIdentity {
    fn permits(self, next: Self) -> bool {
        self.tenant_uuid == next.tenant_uuid && next.version >= self.version
    }
}

/// Service that checks tenant tool permissions by fetching from CP-API
/// and caching locally with a configurable TTL.
#[derive(Clone)]
pub struct ToolPermissionService {
    client: Client,
    base_url: String,
    auth: Option<Arc<ToolProxyClient>>,
    trust: Option<Arc<PolicyTrustStore>>,
    verifier: PolicyArtifactVerifier,
    cache_ttl: Duration,
    cache: Arc<Cache<String, CachedPermissions>>,
    last_failure: Arc<RwLock<Option<PermissionDenyReason>>>,
    /// Last successful complete policy load for any tenant since boot.
    loaded_policy: Arc<RwLock<Option<LoadedPolicy>>>,
    /// Process-lifetime floors survive cache expiry, but not a gateway restart.
    accepted_policies: Arc<RwLock<HashMap<String, PolicyIdentity>>>,
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
            verifier: PolicyArtifactVerifier::new("stoa-control-plane", "stoa-gateway"),
            cache_ttl: cache_ttl.min(MAX_POLICY_AGE),
            cache: Arc::new(Cache::builder().max_capacity(10_000).build()),
            last_failure: Arc::new(RwLock::new(None)),
            loaded_policy: Arc::new(RwLock::new(None)),
            accepted_policies: Arc::new(RwLock::new(HashMap::new())),
            max_policy_age: MAX_POLICY_AGE,
        }
    }

    /// Authenticate with the gateway service account.
    pub fn with_auth(mut self, auth: Arc<ToolProxyClient>) -> Self {
        self.auth = Some(auth);
        self
    }

    /// Require the configured issuer and audience on every signed policy.
    pub fn with_policy_identity(mut self, issuer: &str, audience: &str) -> Self {
        self.verifier = PolicyArtifactVerifier::new(issuer, audience);
        self
    }

    /// While the pinned signer trust set is not loaded, every call is denied
    /// without contacting the Control Plane.
    pub fn with_trust_store(mut self, trust: Option<Arc<PolicyTrustStore>>) -> Self {
        self.trust = trust;
        self
    }

    /// An absent, unreadable or refused signer trust set denies every call.
    pub fn trust_set_not_loaded(&self) -> bool {
        self.trust.as_ref().and_then(|t| t.current()).is_none()
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
        // A blank tenant is not an identity. Deny before any cache or Control Plane read.
        if tenant_id.trim().is_empty() {
            warn!(
                audit_event = "tool_call_denied",
                tenant_id = %tenant_id,
                tool_name = %canonical_name,
                requested_name = %requested_name,
                reason = %PermissionDenyReason::PermissionAbsent.as_str(),
                "Tool permission fail-closed deny"
            );
            return false;
        }
        let state = if self.trust_set_not_loaded() {
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
        if self.trust_set_not_loaded() {
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
        if self.trust_set_not_loaded() {
            return Some(PermissionDenyReason::TrustSetNotLoaded.as_str());
        }
        let loaded = self.loaded_policy.read().ok();
        match loaded.as_deref().and_then(|policy| policy.as_ref()) {
            None => Some("policy_not_loaded"),
            Some(policy)
                if policy.fetched_at.elapsed() > self.max_policy_age
                    || self
                        .verify_artifact(&policy.tenant_id, &policy.artifact)
                        .is_err() =>
            {
                Some("policy_stale")
            }
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
                let mut next_refresh = Instant::now() + service.cache_ttl;
                for tenant_id in &tenants {
                    if let Err(reason) = service.load_policy(tenant_id).await {
                        debug!(tenant_id = %tenant_id, reason = %reason.as_str(), "Startup policy load failed");
                        next_refresh = next_refresh.min(Instant::now() + BOOT_RETRY_INTERVAL);
                    }
                    if let Some(cached) = service.cache.get(tenant_id) {
                        next_refresh = next_refresh.min(cached.expires_at);
                    }
                }
                if service.policy_readiness_failure().is_some() {
                    next_refresh = next_refresh.min(Instant::now() + BOOT_RETRY_INTERVAL);
                }
                tokio::time::sleep_until(next_refresh.into()).await;
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
        if self.trust_set_not_loaded() {
            return PermissionState::Unavailable {
                reason: PermissionDenyReason::TrustSetNotLoaded,
            };
        }
        let cache_key = tenant_id.to_string();

        // Prior allow set carried from an expired entry, so a failed
        // refetch can still surface `Stale` instead of losing the data.
        let mut expired_entry: Option<(PermissionRules, Instant)> = None;

        if let Some(cached) = self.cache.get(&cache_key) {
            // Reverify against the current trust set and wall clock: neither a
            // removed signer nor signed expiry may be bypassed by a cache hit.
            if Instant::now() < cached.expires_at
                && self.verify_artifact(tenant_id, &cached.artifact).is_ok()
            {
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
            Ok(cached) => {
                let rules = cached.rules.clone();
                let fetched_at = cached.fetched_at;
                if let Ok(mut loaded) = self.loaded_policy.write() {
                    *loaded = Some(LoadedPolicy {
                        tenant_id: tenant_id.to_owned(),
                        artifact: cached.artifact.clone(),
                        fetched_at,
                    });
                }
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

    fn verify_artifact(
        &self,
        tenant_id: &str,
        artifact: &str,
    ) -> Result<VerifiedPolicyArtifact, PermissionDenyReason> {
        let trust = self
            .trust
            .as_ref()
            .and_then(|t| t.current())
            .ok_or(PermissionDenyReason::TrustSetNotLoaded)?;
        let verified = self
            .verifier
            .verify(&trust, tenant_id, artifact)
            .map_err(|reason| {
                warn!(reason = %reason, "Signed tool policy refused");
                PermissionDenyReason::PolicyArtifactInvalid
            })?;
        let identity = Self::policy_identity(&verified)?;
        let accepted = self
            .accepted_policies
            .read()
            .map_err(|_| PermissionDenyReason::PolicyArtifactInvalid)?;
        if accepted
            .get(tenant_id)
            .is_some_and(|previous| !previous.permits(identity))
        {
            return Err(PermissionDenyReason::PolicyArtifactInvalid);
        }
        Ok(verified)
    }

    fn policy_identity(
        verified: &VerifiedPolicyArtifact,
    ) -> Result<PolicyIdentity, PermissionDenyReason> {
        let invalid = PermissionDenyReason::PolicyArtifactInvalid;
        let version = verified
            .claims
            .get("version")
            .and_then(serde_json::Value::as_u64)
            .filter(|version| *version > 0)
            .ok_or(invalid)?;
        let issued_at = verified
            .claims
            .get("issued_at")
            .and_then(serde_json::Value::as_str)
            .and_then(|raw| DateTime::parse_from_rfc3339(raw).ok())
            .map(|at| at.with_timezone(&Utc))
            .ok_or(invalid)?;
        let validity = (verified.expires_at - issued_at)
            .to_std()
            .map_err(|_| invalid)?;
        if validity.is_zero()
            || validity > MAX_POLICY_AGE
            || issued_at
                > Utc::now() + chrono::Duration::seconds(POLICY_REFRESH_MARGIN.as_secs() as i64)
        {
            return Err(invalid);
        }
        Ok(PolicyIdentity {
            tenant_uuid: verified.tenant_uuid,
            version,
        })
    }

    fn accept_policy(&self, verified: &VerifiedPolicyArtifact) -> Result<(), PermissionDenyReason> {
        let identity = Self::policy_identity(verified)?;
        let mut accepted = self
            .accepted_policies
            .write()
            .map_err(|_| PermissionDenyReason::PolicyArtifactInvalid)?;
        if let Some(previous) = accepted.get(&verified.tenant_id) {
            if !previous.permits(identity) {
                return Err(PermissionDenyReason::PolicyArtifactInvalid);
            }
        } else if accepted.len() >= MAX_TRACKED_TENANTS {
            return Err(PermissionDenyReason::PolicyArtifactInvalid);
        }
        accepted.insert(verified.tenant_id.clone(), identity);
        Ok(())
    }

    async fn read_policy_body(
        mut response: reqwest::Response,
    ) -> Result<String, PermissionDenyReason> {
        if response
            .content_length()
            .is_some_and(|length| length > MAX_POLICY_BYTES as u64)
        {
            return Err(PermissionDenyReason::PolicyArtifactInvalid);
        }
        let mut body = Vec::new();
        while let Some(chunk) = response
            .chunk()
            .await
            .map_err(|_| PermissionDenyReason::CpUnreachable)?
        {
            if chunk.len() > MAX_POLICY_BYTES - body.len() {
                return Err(PermissionDenyReason::PolicyArtifactInvalid);
            }
            body.extend_from_slice(&chunk);
        }
        String::from_utf8(body).map_err(|_| PermissionDenyReason::PolicyArtifactInvalid)
    }

    /// Fetch only the complete signed artifact. Never consult the unsigned list.
    async fn fetch_permissions(
        &self,
        tenant_id: &str,
    ) -> Result<CachedPermissions, PermissionDenyReason> {
        // Only a signing-key (private_key_jwt) service identity reads permissions.
        let auth = self
            .auth
            .as_ref()
            .filter(|auth| auth.uses_private_key_jwt())
            .ok_or(PermissionDenyReason::CpUnauthorized)?;
        let url = format!(
            "{}/v1/tenants/{}/tool-permissions/artifact",
            self.base_url, tenant_id
        );
        let mut token = auth
            .get_token()
            .await
            .map_err(|_| PermissionDenyReason::CpUnauthorized)?;
        let mut refreshed = false;
        let mut reissue = false;
        loop {
            let response = self
                .client
                .get(&url)
                .query(&[("reissue", reissue)])
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
            let artifact = Self::read_policy_body(response).await?;
            let verified = self.verify_artifact(tenant_id, &artifact)?;
            let remaining = (verified.expires_at - Utc::now())
                .to_std()
                .map_err(|_| PermissionDenyReason::PolicyArtifactInvalid)?;
            if remaining <= POLICY_REFRESH_MARGIN && !reissue {
                reissue = true;
                continue;
            }
            let items: Vec<PermissionItem> = serde_json::from_value(
                verified
                    .claims
                    .get("permissions")
                    .cloned()
                    .unwrap_or_default(),
            )
            .map_err(|_| PermissionDenyReason::PolicyArtifactInvalid)?;
            if items.len() > 5000 {
                return Err(PermissionDenyReason::PolicyArtifactInvalid);
            }
            let mut seen = HashSet::new();
            let mut overrides = HashMap::new();
            for item in items {
                if item.mcp_server.trim().is_empty()
                    || item.tool.trim().is_empty()
                    || !seen.insert((item.mcp_server, item.tool.clone()))
                {
                    return Err(PermissionDenyReason::PolicyArtifactInvalid);
                }
                let entry = overrides.entry(item.tool).or_insert(true);
                *entry &= item.allowed;
            }
            let remaining = (verified.expires_at - Utc::now())
                .to_std()
                .map_err(|_| PermissionDenyReason::PolicyArtifactInvalid)?;
            if remaining.is_zero() {
                return Err(PermissionDenyReason::PolicyArtifactInvalid);
            }
            // Publish the floor only after the entire permission set is valid.
            self.accept_policy(&verified)?;
            let refresh_after = if remaining > POLICY_REFRESH_MARGIN {
                remaining - POLICY_REFRESH_MARGIN
            } else {
                remaining.min(BOOT_RETRY_INTERVAL)
            };
            let fetched_at = Instant::now();
            return Ok(CachedPermissions {
                artifact,
                rules: PermissionRules { overrides },
                fetched_at,
                expires_at: fetched_at + self.cache_ttl.min(refresh_after),
            });
        }
    }
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;
    use crate::auth::jwt::tests::policy;
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
            .with_trust_store(Some(test_trust_store()))
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
            .and(path_regex(r"/v1/tenants/.+/tool-permissions/artifact"))
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
            .with_auth(Arc::new(secret_client))
            .with_trust_store(Some(test_trust_store()));
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
            .and(path_regex(r"/v1/tenants/.+/tool-permissions/artifact"))
            .respond_with(permissions_response(serde_json::json!([
                {"mcp_server_id": "s1", "tool_name": "allowed_tool", "allowed": true}
            ])))
            .mount(&server)
            .await;
        let svc = authenticated_service(&server, Duration::from_secs(60)).await;
        assert!(svc.is_tool_allowed("tenant1", "allowed_tool").await);
        assert!(!svc.is_tool_allowed("tenant1", "unlisted_tool").await);
    }

    pub(crate) fn test_trust_store() -> Arc<PolicyTrustStore> {
        static PATH: std::sync::OnceLock<std::path::PathBuf> = std::sync::OnceLock::new();
        let path = PATH.get_or_init(|| {
            let path = tempfile::tempdir().unwrap().keep().join("trust.json");
            std::fs::write(&path, VALID_JWKS).unwrap();
            path
        });
        PolicyTrustStore::open(path)
    }

    pub(crate) fn permissions_response(items: serde_json::Value) -> impl wiremock::Respond {
        move |request: &wiremock::Request| {
            let tenant = request.url.path().split('/').nth(3).unwrap();
            let entries: Vec<_> = items
                .as_array()
                .unwrap()
                .iter()
                .map(|item| {
                    serde_json::json!({"mcp_server": item["mcp_server_id"],
                    "tool": item["tool_name"], "allowed": item["allowed"]})
                })
                .collect();
            ResponseTemplate::new(200).set_body_raw(
                policy::artifact(tenant, serde_json::json!(entries)),
                "application/jose",
            )
        }
    }

    // regression for CAB-2227
    #[tokio::test]
    async fn test_no_permissions_denies() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path_regex("/v1/tenants/.*/tool-permissions/artifact"))
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
            .and(path_regex("/v1/tenants/.*/tool-permissions/artifact"))
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
            .and(path_regex("/v1/tenants/.*/tool-permissions/artifact"))
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
            .and(path_regex("/v1/tenants/.*/tool-permissions/artifact"))
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
            .and(path_regex("/v1/tenants/.*/tool-permissions/artifact"))
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
            .and(path_regex("/v1/tenants/.*/tool-permissions/artifact"))
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
    async fn regression_complete_signed_policy_keeps_cross_server_deny_precedence() {
        let server = MockServer::start().await;
        let service = authenticated_service(&server, Duration::from_secs(60)).await;
        let mut items = Vec::new();
        for index in 0..120 {
            items.push(serde_json::json!({"mcp_server_id": "first",
                "tool_name": format!("allowed_{index}"), "allowed": true}));
        }
        items.extend([
            serde_json::json!({"mcp_server_id": "first", "tool_name": "blocked", "allowed": true}),
            serde_json::json!({"mcp_server_id": "second", "tool_name": "blocked", "allowed": false}),
        ]);
        Mock::given(method("GET"))
            .and(path("/v1/tenants/tenant-a/tool-permissions/artifact"))
            .respond_with(permissions_response(serde_json::json!(items)))
            .expect(1)
            .mount(&server)
            .await;
        assert!(!service.is_tool_allowed("tenant-a", "blocked").await);
        assert!(service.is_tool_allowed("tenant-a", "allowed_119").await);
        assert!(!service.is_tool_allowed("tenant-a", "unlisted").await);
    }

    #[tokio::test]
    async fn regression_invalid_or_absent_artifact_never_uses_unsigned_permissions() {
        let cases = [
            "missing",
            "unsigned",
            "expired",
            "no_expiry",
            "bad_signature",
            "wrong_tenant",
            "wrong_issuer",
            "wrong_audience",
            "missing_entries",
            "duplicate",
        ];
        for case in cases {
            let server = MockServer::start().await;
            let service = authenticated_service(&server, Duration::from_secs(60)).await;
            let entries =
                serde_json::json!([{"mcp_server":"s1", "tool":"allowed", "allowed":true}]);
            let mut claims = policy::claims("tenant-a", entries.clone());
            match case {
                "expired" => {
                    claims["expires_at"] =
                        serde_json::json!((Utc::now() - chrono::Duration::seconds(1)).to_rfc3339())
                }
                "no_expiry" => {
                    claims.as_object_mut().unwrap().remove("expires_at");
                }
                "wrong_tenant" => claims["tenant_id"] = serde_json::json!("tenant-b"),
                "wrong_issuer" => claims["iss"] = serde_json::json!("other-issuer"),
                "wrong_audience" => claims["aud"] = serde_json::json!("other-audience"),
                "missing_entries" => {
                    claims.as_object_mut().unwrap().remove("permissions");
                }
                "duplicate" => claims["permissions"] = serde_json::json!([entries[0], entries[0]]),
                _ => {}
            }
            let mut artifact = policy::sign(&claims);
            if case == "bad_signature" {
                let start = artifact.rfind('.').unwrap() + 1;
                artifact.replace_range(
                    start..start + 1,
                    if &artifact[start..start + 1] == "A" {
                        "B"
                    } else {
                        "A"
                    },
                );
            }
            let response = match case {
                "missing" => ResponseTemplate::new(404),
                "unsigned" => ResponseTemplate::new(200).set_body_json(serde_json::json!({"items":[{"tool_name":"allowed", "mcp_server_id":"s1", "allowed":true}], "total":1})),
                _ => ResponseTemplate::new(200).set_body_raw(artifact, "application/jose"),
            };
            Mock::given(method("GET"))
                .and(path("/v1/tenants/tenant-a/tool-permissions"))
                .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({"items":[{"tool_name":"allowed", "mcp_server_id":"s1", "allowed":true}], "total":1})))
                .expect(0).mount(&server).await;
            Mock::given(method("GET"))
                .and(path("/v1/tenants/tenant-a/tool-permissions/artifact"))
                .respond_with(response)
                .mount(&server)
                .await;
            assert!(
                !service.is_tool_allowed("tenant-a", "allowed").await,
                "{case}"
            );
            assert_eq!(
                service.policy_readiness_failure(),
                Some("policy_not_loaded"),
                "{case}"
            );
        }
    }

    #[tokio::test]
    async fn regression_signed_expiry_still_denies_when_control_plane_cannot_renew() {
        let server = MockServer::start().await;
        let service = authenticated_service(&server, Duration::from_secs(60)).await;
        let mut claims = policy::claims(
            "tenant-a",
            serde_json::json!([{"mcp_server":"s1", "tool":"allowed", "allowed":true}]),
        );
        claims["expires_at"] =
            serde_json::json!((Utc::now() + chrono::Duration::seconds(2)).to_rfc3339());
        Mock::given(method("GET"))
            .and(path("/v1/tenants/tenant-a/tool-permissions/artifact"))
            .respond_with(
                ResponseTemplate::new(200).set_body_raw(policy::sign(&claims), "application/jose"),
            )
            .mount(&server)
            .await;
        assert!(service.is_tool_allowed("tenant-a", "allowed").await);
        assert_eq!(service.policy_readiness_failure(), None);
        tokio::time::sleep(Duration::from_millis(2050)).await;
        assert_eq!(service.policy_readiness_failure(), Some("policy_stale"));
        assert!(!service.is_tool_allowed("tenant-a", "allowed").await);
    }

    #[tokio::test]
    async fn regression_refresher_renews_before_signed_expiry() {
        use wiremock::matchers::query_param;
        let server = MockServer::start().await;
        let service = Arc::new(authenticated_service(&server, Duration::from_secs(60)).await);
        let entries = serde_json::json!([{"mcp_server":"s1", "tool":"allowed", "allowed":true}]);
        let mut claims = policy::claims("tenant-a", entries.clone());
        claims["expires_at"] =
            serde_json::json!((Utc::now() + chrono::Duration::seconds(31)).to_rfc3339());
        let original_expiry =
            chrono::DateTime::parse_from_rfc3339(claims["expires_at"].as_str().unwrap())
                .unwrap()
                .with_timezone(&Utc);
        Mock::given(method("GET"))
            .and(path("/v1/tenants/tenant-a/tool-permissions/artifact"))
            .respond_with(
                ResponseTemplate::new(200).set_body_raw(policy::sign(&claims), "application/jose"),
            )
            .mount(&server)
            .await;
        Mock::given(method("GET"))
            .and(path("/v1/tenants/tenant-a/tool-permissions/artifact"))
            .and(query_param("reissue", "true"))
            .respond_with(move |_: &wiremock::Request| {
                ResponseTemplate::new(200).set_body_raw(
                    policy::artifact("tenant-a", entries.clone()),
                    "application/jose",
                )
            })
            .with_priority(1)
            .expect(1)
            .mount(&server)
            .await;
        service.load_policy("tenant-a").await.unwrap();
        service.spawn_policy_refresher(vec!["tenant-a".into()]);
        tokio::time::timeout(Duration::from_secs(3), async {
            loop {
                assert_eq!(service.policy_readiness_failure(), None);
                let verified = {
                    let loaded = service.loaded_policy.read().unwrap();
                    service
                        .verify_artifact("tenant-a", &loaded.as_ref().unwrap().artifact)
                        .unwrap()
                };
                if verified.expires_at > original_expiry {
                    break;
                }
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
        })
        .await
        .expect("renew while the original policy is still valid");
        assert!(service.is_tool_allowed("tenant-a", "allowed").await);
        assert_eq!(service.policy_readiness_failure(), None);
    }

    #[tokio::test]
    async fn regression_near_expiry_on_cold_load_requests_reissue() {
        use wiremock::matchers::query_param;
        let server = MockServer::start().await;
        let service = authenticated_service(&server, Duration::from_secs(60)).await;
        let mut claims = policy::claims(
            "tenant-a",
            serde_json::json!([{"mcp_server":"s1", "tool":"allowed", "allowed":true}]),
        );
        claims["expires_at"] =
            serde_json::json!((Utc::now() + chrono::Duration::seconds(2)).to_rfc3339());
        Mock::given(method("GET"))
            .and(path("/v1/tenants/tenant-a/tool-permissions/artifact"))
            .respond_with(
                ResponseTemplate::new(200).set_body_raw(policy::sign(&claims), "application/jose"),
            )
            .mount(&server)
            .await;
        Mock::given(method("GET"))
            .and(path("/v1/tenants/tenant-a/tool-permissions/artifact"))
            .and(query_param("reissue", "true"))
            .respond_with(permissions_response(serde_json::json!([
                {"mcp_server_id":"s1", "tool_name":"allowed", "allowed":true}])))
            .with_priority(1)
            .expect(1)
            .mount(&server)
            .await;
        service.load_policy("tenant-a").await.unwrap();
        tokio::time::sleep(Duration::from_millis(2050)).await;
        assert_eq!(service.policy_readiness_failure(), None);
        assert!(service.is_tool_allowed("tenant-a", "allowed").await);
    }

    async fn assert_policies_from_two_replicas(newer_version: bool) {
        use wiremock::matchers::query_param;

        let replica_a = MockServer::start().await;
        let replica_b = MockServer::start().await;
        let mut service = authenticated_service(&replica_b, Duration::from_secs(60)).await;
        let now = Utc::now();
        for (replica, age, version) in [
            (&replica_a, 60, if newer_version { 3 } else { 2 }),
            (&replica_b, 30, 2),
        ] {
            let mut claims = policy::claims(
                "tenant-a",
                serde_json::json!([{"mcp_server":"s1", "tool":"allowed", "allowed":true}]),
            );
            let issued_at = now - chrono::Duration::seconds(age);
            claims["version"] = serde_json::json!(version);
            claims["issued_at"] = serde_json::json!(issued_at.to_rfc3339());
            claims["expires_at"] =
                serde_json::json!((issued_at + chrono::Duration::seconds(900)).to_rfc3339());
            Mock::given(method("GET"))
                .and(path("/v1/tenants/tenant-a/tool-permissions/artifact"))
                .and(query_param("reissue", "false"))
                .respond_with(
                    ResponseTemplate::new(200)
                        .set_body_raw(policy::sign(&claims), "application/jose"),
                )
                .expect(if newer_version { 1 } else { 2 })
                .mount(replica)
                .await;
        }
        let replicas = if newer_version {
            vec![&replica_b, &replica_a]
        } else {
            vec![&replica_b, &replica_a, &replica_b, &replica_a]
        };
        for replica in replicas {
            // Route cache misses to each replica while retaining the gateway's
            // accepted identity and version, as with a load-balanced CP URL.
            service.base_url = replica.uri();
            service.cache.invalidate(&"tenant-a".to_owned());
            service
                .load_policy("tenant-a")
                .await
                .expect("valid policies from either replica must load");
            assert!(service.is_tool_allowed("tenant-a", "allowed").await);
            assert!(!service.is_tool_allowed("tenant-a", "unlisted").await);
            assert_eq!(service.policy_readiness_failure(), None);
        }
        replica_a.verify().await;
        replica_b.verify().await;
    }

    #[tokio::test]
    async fn regression_two_replicas_accept_same_version_with_earlier_issuance() {
        assert_policies_from_two_replicas(false).await;
    }

    #[tokio::test]
    async fn regression_two_replicas_accept_newer_version_with_earlier_issuance() {
        assert_policies_from_two_replicas(true).await;
    }

    #[tokio::test]
    async fn regression_policy_rollback_and_tenant_replacement_are_refused() {
        for case in ["version", "tenant_uuid"] {
            let server = MockServer::start().await;
            let service = authenticated_service(&server, Duration::from_secs(60)).await;
            let mut claims = policy::claims(
                "tenant-a",
                serde_json::json!([{"mcp_server":"s1", "tool":"allowed", "allowed":false}]),
            );
            claims["version"] = serde_json::json!(2);
            Mock::given(method("GET"))
                .and(path("/v1/tenants/tenant-a/tool-permissions/artifact"))
                .respond_with(
                    ResponseTemplate::new(200)
                        .set_body_raw(policy::sign(&claims), "application/jose"),
                )
                .up_to_n_times(1)
                .with_priority(1)
                .expect(1)
                .mount(&server)
                .await;
            assert!(!service.is_tool_allowed("tenant-a", "allowed").await);
            assert_eq!(service.policy_readiness_failure(), None);
            service.cache.invalidate(&"tenant-a".to_owned());
            claims["permissions"][0]["allowed"] = serde_json::json!(true);
            match case {
                "version" => claims["version"] = serde_json::json!(1),
                _ => {
                    claims["tenant_uuid"] =
                        serde_json::json!("11111111-1111-4111-8111-111111111111")
                }
            }
            Mock::given(method("GET"))
                .and(path("/v1/tenants/tenant-a/tool-permissions/artifact"))
                .respond_with(
                    ResponseTemplate::new(200)
                        .set_body_raw(policy::sign(&claims), "application/jose"),
                )
                .mount(&server)
                .await;
            assert!(
                !service.is_tool_allowed("tenant-a", "allowed").await,
                "{case}"
            );
        }
    }

    #[tokio::test]
    async fn regression_policy_metadata_and_size_are_bounded() {
        for case in [
            "version",
            "issued_at",
            "future_issued_at",
            "validity",
            "size",
        ] {
            let server = MockServer::start().await;
            let service = authenticated_service(&server, Duration::from_secs(60)).await;
            let mut claims = policy::claims(
                "tenant-a",
                serde_json::json!([{"mcp_server":"s1", "tool":"allowed", "allowed":true}]),
            );
            match case {
                "version" => claims["version"] = serde_json::json!(0),
                "issued_at" => {
                    claims.as_object_mut().unwrap().remove("issued_at");
                }
                "future_issued_at" => {
                    claims["issued_at"] =
                        serde_json::json!((Utc::now() + chrono::Duration::minutes(5)).to_rfc3339())
                }
                "validity" => {
                    claims["expires_at"] =
                        serde_json::json!((Utc::now() + chrono::Duration::hours(2)).to_rfc3339())
                }
                // A valid signature and entry, but an oversized signed payload.
                _ => claims["padding"] = serde_json::json!("x".repeat(1024 * 1024)),
            }
            Mock::given(method("GET"))
                .and(path("/v1/tenants/tenant-a/tool-permissions/artifact"))
                .respond_with(
                    ResponseTemplate::new(200)
                        .set_body_raw(policy::sign(&claims), "application/jose"),
                )
                .mount(&server)
                .await;
            assert!(
                !service.is_tool_allowed("tenant-a", "allowed").await,
                "{case}"
            );
        }
    }

    #[tokio::test]
    async fn regression_chunked_policy_body_stops_at_size_limit() {
        use futures::StreamExt;
        let server = MockServer::start().await;
        let mut service = authenticated_service(&server, Duration::from_secs(60)).await;
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        service.base_url = format!("http://{}", listener.local_addr().unwrap());
        let app = axum::Router::new().route(
            "/v1/tenants/tenant-a/tool-permissions/artifact",
            axum::routing::get(|| async {
                let body = futures::stream::iter([Ok::<_, std::io::Error>(
                    axum::body::Bytes::from(vec![b'x'; 1024 * 1024 + 1]),
                )])
                .chain(futures::stream::pending());
                axum::response::Response::new(axum::body::Body::from_stream(body))
            }),
        );
        let task = tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });
        let result = tokio::time::timeout(
            Duration::from_secs(2),
            service.is_tool_allowed("tenant-a", "allowed"),
        )
        .await;
        task.abort();
        assert!(!result.expect("stop reading oversized chunked bodies without waiting for EOF"));
        assert_eq!(
            service.readiness_failure_reason(),
            Some("policy_artifact_invalid")
        );
    }

    #[tokio::test]
    async fn regression_unconfigured_trust_denies_load_and_calls_without_network() {
        let server = MockServer::start().await;
        let service = authenticated_service(&server, Duration::from_secs(60))
            .await
            .with_trust_store(None);
        assert_eq!(
            service.load_policy("tenant-a").await,
            Err(PermissionDenyReason::TrustSetNotLoaded)
        );
        assert!(!service.is_tool_allowed("tenant-a", "allowed").await);
        assert_eq!(
            service.policy_readiness_failure(),
            Some("trust_set_not_loaded")
        );
        assert!(server.received_requests().await.unwrap().is_empty());
    }

    #[tokio::test]
    async fn regression_cached_policy_is_reverified_after_explicit_trust_reload() {
        let server = MockServer::start().await;
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("trust.json");
        std::fs::write(&path, VALID_JWKS).unwrap();
        let trust = PolicyTrustStore::open(&path);
        let service = authenticated_service(&server, Duration::from_secs(60))
            .await
            .with_trust_store(Some(trust.clone()));
        Mock::given(method("GET"))
            .and(path_regex("/tool-permissions/artifact$"))
            .respond_with(permissions_response(
                serde_json::json!([{"mcp_server_id":"s1", "tool_name":"allowed", "allowed":true}]),
            ))
            .mount(&server)
            .await;
        assert!(service.is_tool_allowed("tenant-a", "allowed").await);
        std::fs::write(
            &path,
            VALID_JWKS.replace("cp-policy-202611-1", "cp-policy-202611-2"),
        )
        .unwrap();
        trust.reload().unwrap();
        assert_eq!(service.policy_readiness_failure(), Some("policy_stale"));
        assert!(!service.is_tool_allowed("tenant-a", "allowed").await);
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
            .and(path("/v1/tenants/tenant-a/tool-permissions/artifact"))
            .and(header("Authorization", "Bearer rejected-service-token"))
            .respond_with(ResponseTemplate::new(401))
            .expect(1)
            .mount(&server)
            .await;
        Mock::given(method("GET"))
            .and(path("/v1/tenants/tenant-a/tool-permissions/artifact"))
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
            .filter(|r| r.url.path().ends_with("/tool-permissions/artifact"))
            .all(|r| r.headers.contains_key("Authorization")));
    }

    /// One-key trust set built from the published RFC 8032 §7.1 public key.
    pub(crate) const VALID_JWKS: &str = policy::JWKS;

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
            .and(path("/v1/tenants/tenant-a/tool-permissions/artifact"))
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
                .and(path_regex(r"/v1/tenants/.+/tool-permissions/artifact"))
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
            .and(path_regex(r"/v1/tenants/.+/tool-permissions/artifact"))
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

    /// Serve `reply` to exactly one `GET /v1/tenants/*/tool-permissions/artifact` request.
    pub(crate) async fn serve_policy_once(
        server: &MockServer,
        reply: impl wiremock::Respond + 'static,
    ) {
        Mock::given(method("GET"))
            .and(path_regex("/v1/tenants/.*/tool-permissions/artifact"))
            .respond_with(reply)
            .up_to_n_times(1)
            .mount(server)
            .await;
    }

    /// Complete policy whose only explicit allow is `ok_tool`.
    pub(crate) fn ok_tool_policy() -> impl wiremock::Respond {
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

    #[tokio::test]
    async fn regression_blank_tenant_denies_without_reading_an_allow() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path_regex(r"/v1/tenants/.*/tool-permissions/artifact"))
            .respond_with(permissions_response(serde_json::json!([
                {"mcp_server_id": "srv1", "tool_name": "ok_tool", "allowed": true}
            ])))
            .mount(&server)
            .await;
        let svc = authenticated_service(&server, Duration::from_secs(60)).await;
        assert!(!svc.is_tool_allowed("", "ok_tool").await);
        assert!(!svc.is_tool_allowed("   ", "ok_tool").await);
        assert!(
            server.received_requests().await.unwrap().is_empty(),
            "a blank tenant must not be authorized from a Control Plane allow"
        );
    }

    #[tokio::test]
    async fn regression_tenant_cache_does_not_authorize_another_tenant() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/v1/tenants/tenant-a/tool-permissions/artifact"))
            .respond_with(permissions_response(serde_json::json!([
                {"mcp_server_id": "srv1", "tool_name": "ok_tool", "allowed": true}
            ])))
            .expect(1)
            .mount(&server)
            .await;
        Mock::given(method("GET"))
            .and(path("/v1/tenants/tenant-b/tool-permissions/artifact"))
            .respond_with(permissions_response(serde_json::json!([])))
            .expect(1)
            .mount(&server)
            .await;
        let svc = authenticated_service(&server, Duration::from_secs(60)).await;
        assert!(svc.is_tool_allowed("tenant-a", "ok_tool").await);
        assert!(svc.is_tool_allowed("tenant-a", "ok_tool").await);
        assert!(!svc.is_tool_allowed("tenant-b", "ok_tool").await);
        assert!(!svc.is_tool_allowed("tenant-b", "ok_tool").await);
    }
}
