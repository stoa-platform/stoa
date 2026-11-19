//! BYOK (Bring Your Own Key) credential store for backend API authentication.
//!
//! Stores backend authentication credentials per route. The Control Plane
//! pushes credentials via the admin API; the dynamic proxy injects them
//! into outgoing requests.
//!
//! Supports static credentials (API key, Bearer, Basic) and OAuth2
//! client_credentials flow with automatic token caching (CAB-1317).

use parking_lot::RwLock;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::time::{Duration, Instant};
use tracing::debug;

/// Authentication type for backend APIs.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum AuthType {
    /// API key in a custom header (e.g., `X-API-Key: <value>`)
    ApiKey,
    /// Bearer token (e.g., `Authorization: Bearer <value>`)
    Bearer,
    /// Basic auth (e.g., `Authorization: Basic <base64>`)
    Basic,
    /// OAuth2 client_credentials grant — token fetched and cached automatically
    #[serde(rename = "oauth2_client_credentials")]
    OAuth2ClientCredentials,
}

/// OAuth2 client_credentials configuration for a backend.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OAuth2Config {
    /// Token endpoint URL (must be HTTPS in production)
    pub token_url: String,
    /// OAuth2 client ID
    pub client_id: String,
    /// OAuth2 client secret
    pub client_secret: String,
}

/// A backend credential for a specific route.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BackendCredential {
    /// Route ID this credential applies to
    pub route_id: String,
    /// Authentication type
    pub auth_type: AuthType,
    /// Header name (e.g., "Authorization", "X-API-Key")
    pub header_name: String,
    /// Header value (e.g., "Bearer token123", "Basic dXNlcjpwYXNz")
    pub header_value: String,
    /// OAuth2 configuration (required when auth_type is OAuth2ClientCredentials)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub oauth2: Option<OAuth2Config>,
    /// Upstream origin this credential is bound to: scheme, host and port,
    /// e.g. `https://api.example.com:443`. Mandatory for dynamic tool
    /// credentials (keys starting with [`MCP_TOOL_KEY_PREFIX`]), which are
    /// only used for requests to that origin. Ignored for other keys.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub allowed_origin: Option<String>,
}

/// Key prefix of the credentials used by dynamic MCP tools
/// (`mcp-tool:{tenant}:{tool_name}`).
pub const MCP_TOOL_KEY_PREFIX: &str = "mcp-tool:";

impl BackendCredential {
    /// Whether `url` targets this credential's `allowed_origin`. False when
    /// the credential has no valid `allowed_origin` or `url` has no origin.
    pub fn is_bound_to_origin_of(&self, url: &str) -> bool {
        let allowed = self.allowed_origin.as_deref().and_then(normalize_origin);
        allowed.is_some() && allowed == url_origin(url)
    }
}

/// Normalize an origin given as `scheme://host[:port]` (an optional trailing
/// `/` is accepted). Scheme and host are lowercased and the port is always
/// explicit (80 for http, 443 for https when omitted), so two spellings of
/// the same origin compare equal. `None` when `value` is not an http(s)
/// origin: other scheme, no host, or user info, path, query or fragment.
pub fn normalize_origin(value: &str) -> Option<String> {
    let parsed = url::Url::parse(value).ok()?;
    let is_bare_origin = parsed.username().is_empty()
        && parsed.password().is_none()
        && parsed.path() == "/"
        && parsed.query().is_none()
        && parsed.fragment().is_none();
    if is_bare_origin {
        origin_of(&parsed)
    } else {
        None
    }
}

/// Origin of an http(s) URL, in the form produced by [`normalize_origin`].
pub fn url_origin(url: &str) -> Option<String> {
    origin_of(&url::Url::parse(url).ok()?)
}

fn origin_of(parsed: &url::Url) -> Option<String> {
    if !matches!(parsed.scheme(), "http" | "https") {
        return None;
    }
    let host = parsed.host_str().filter(|host| !host.is_empty())?;
    let port = parsed.port_or_known_default()?;
    Some(format!("{}://{host}:{port}", parsed.scheme()))
}

/// Cached OAuth2 access token with expiry tracking.
struct CachedOAuth2Token {
    access_token: String,
    expires_at: Instant,
}

/// OAuth2 token endpoint response (subset of RFC 6749 §5.1).
#[derive(Deserialize)]
struct TokenResponse {
    access_token: String,
    #[serde(default = "default_expires_in")]
    expires_in: u64,
}

fn default_expires_in() -> u64 {
    3600
}

/// Safety margin before token expiry — fetch a new token 30s early.
const TOKEN_EXPIRY_MARGIN: Duration = Duration::from_secs(30);

/// Thread-safe in-memory credential store, keyed by route_id.
/// Embeds the OAuth2 token cache (Council adjustment #2).
pub struct CredentialStore {
    credentials: RwLock<HashMap<String, BackendCredential>>,
    oauth2_tokens: RwLock<HashMap<String, CachedOAuth2Token>>,
}

impl Default for CredentialStore {
    fn default() -> Self {
        Self::new()
    }
}

impl CredentialStore {
    pub fn new() -> Self {
        Self {
            credentials: RwLock::new(HashMap::new()),
            oauth2_tokens: RwLock::new(HashMap::new()),
        }
    }

    /// Insert or update a credential. Returns the previous value if it existed.
    /// Invalidates the OAuth2 token cache for this route on update.
    pub fn upsert(&self, cred: BackendCredential) -> Option<BackendCredential> {
        let route_id = cred.route_id.clone();
        let prev = self.credentials.write().insert(route_id.clone(), cred);
        // Invalidate cached token — config may have changed
        self.oauth2_tokens.write().remove(&route_id);
        prev
    }

    /// Remove a credential by route_id. Also clears the OAuth2 token cache.
    pub fn remove(&self, route_id: &str) -> Option<BackendCredential> {
        self.oauth2_tokens.write().remove(route_id);
        self.credentials.write().remove(route_id)
    }

    /// Get a credential by route_id.
    /// Short-circuits to None without acquiring the lock when the store is empty (CAB-1893).
    pub fn get(&self, route_id: &str) -> Option<BackendCredential> {
        let guard = self.credentials.read();
        if guard.is_empty() {
            return None;
        }
        guard.get(route_id).cloned()
    }

    /// List all credentials (header_value redacted for safety).
    pub fn list(&self) -> Vec<BackendCredential> {
        self.credentials.read().values().cloned().collect()
    }

    /// Number of stored credentials.
    pub fn count(&self) -> usize {
        self.credentials.read().len()
    }

    /// Number of cached OAuth2 tokens (for diagnostics).
    pub fn oauth2_cache_count(&self) -> usize {
        self.oauth2_tokens.read().len()
    }

    /// Get a valid OAuth2 access token for a route, fetching a new one if needed.
    ///
    /// Pattern generalized from `tool_proxy.rs` — 30s safety margin before expiry.
    pub async fn get_oauth2_token(
        &self,
        route_id: &str,
        client: &reqwest::Client,
    ) -> Result<String, String> {
        // Fast path: return cached token if still valid
        {
            let cache = self.oauth2_tokens.read();
            if let Some(cached) = cache.get(route_id) {
                if cached.expires_at > Instant::now() + TOKEN_EXPIRY_MARGIN {
                    return Ok(cached.access_token.clone());
                }
            }
        }

        // Slow path: fetch new token
        let cred = self
            .credentials
            .read()
            .get(route_id)
            .cloned()
            .ok_or_else(|| format!("No credential found for route {route_id}"))?;

        let oauth2 = cred
            .oauth2
            .as_ref()
            .ok_or_else(|| format!("Route {route_id} has no OAuth2 config"))?;

        debug!(route_id = %route_id, token_url = %oauth2.token_url, "Fetching OAuth2 token");

        let resp = client
            .post(&oauth2.token_url)
            .form(&[
                ("grant_type", "client_credentials"),
                ("client_id", &oauth2.client_id),
                ("client_secret", &oauth2.client_secret),
            ])
            .send()
            .await
            .map_err(|e| format!("OAuth2 token request failed: {e}"))?;

        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp
                .text()
                .await
                .unwrap_or_else(|_| "<no body>".to_string());
            return Err(format!("OAuth2 token endpoint returned {status}: {body}"));
        }

        let token_resp: TokenResponse = resp
            .json()
            .await
            .map_err(|e| format!("Failed to parse OAuth2 token response: {e}"))?;

        let expires_at = Instant::now() + Duration::from_secs(token_resp.expires_in);
        let access_token = token_resp.access_token.clone();

        self.oauth2_tokens.write().insert(
            route_id.to_string(),
            CachedOAuth2Token {
                access_token: token_resp.access_token,
                expires_at,
            },
        );

        Ok(access_token)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_cred(route_id: &str) -> BackendCredential {
        BackendCredential {
            route_id: route_id.to_string(),
            auth_type: AuthType::Bearer,
            header_name: "Authorization".to_string(),
            header_value: "Bearer test-token".to_string(),
            oauth2: None,
            allowed_origin: None,
        }
    }

    fn make_oauth2_cred(route_id: &str) -> BackendCredential {
        BackendCredential {
            route_id: route_id.to_string(),
            auth_type: AuthType::OAuth2ClientCredentials,
            header_name: String::new(),
            header_value: String::new(),
            oauth2: Some(OAuth2Config {
                token_url: "https://auth.example.com/token".to_string(),
                client_id: "test-client".to_string(),
                client_secret: "test-secret".to_string(),
            }),
            allowed_origin: None,
        }
    }

    #[test]
    fn test_upsert_new() {
        let store = CredentialStore::new();
        let prev = store.upsert(make_cred("r1"));
        assert!(prev.is_none());
        assert_eq!(store.count(), 1);
    }

    #[test]
    fn test_upsert_existing() {
        let store = CredentialStore::new();
        store.upsert(make_cred("r1"));
        let prev = store.upsert(BackendCredential {
            route_id: "r1".to_string(),
            auth_type: AuthType::ApiKey,
            header_name: "X-API-Key".to_string(),
            header_value: "new-key".to_string(),
            oauth2: None,
            allowed_origin: None,
        });
        assert!(prev.is_some());
        assert_eq!(prev.unwrap().auth_type, AuthType::Bearer);
        assert_eq!(store.count(), 1);
    }

    #[test]
    fn test_get() {
        let store = CredentialStore::new();
        store.upsert(make_cred("r1"));
        let cred = store.get("r1");
        assert!(cred.is_some());
        assert_eq!(cred.unwrap().header_value, "Bearer test-token");
    }

    #[test]
    fn test_get_nonexistent() {
        let store = CredentialStore::new();
        assert!(store.get("ghost").is_none());
    }

    #[test]
    fn test_remove() {
        let store = CredentialStore::new();
        store.upsert(make_cred("r1"));
        let removed = store.remove("r1");
        assert!(removed.is_some());
        assert_eq!(store.count(), 0);
    }

    #[test]
    fn test_remove_nonexistent() {
        let store = CredentialStore::new();
        assert!(store.remove("ghost").is_none());
    }

    #[test]
    fn test_list() {
        let store = CredentialStore::new();
        store.upsert(make_cred("r1"));
        store.upsert(make_cred("r2"));
        assert_eq!(store.list().len(), 2);
    }

    #[test]
    fn test_auth_type_serialization() {
        let cred = make_cred("r1");
        let json = serde_json::to_value(&cred).unwrap();
        assert_eq!(json["auth_type"], "bearer");

        let api_key_cred = BackendCredential {
            auth_type: AuthType::ApiKey,
            ..make_cred("r2")
        };
        let json = serde_json::to_value(&api_key_cred).unwrap();
        assert_eq!(json["auth_type"], "api_key");
    }

    #[test]
    fn test_oauth2_auth_type_serialization() {
        let cred = make_oauth2_cred("r1");
        let json = serde_json::to_value(&cred).unwrap();
        assert_eq!(json["auth_type"], "oauth2_client_credentials");
        assert!(json["oauth2"].is_object());
        assert_eq!(
            json["oauth2"]["token_url"],
            "https://auth.example.com/token"
        );
    }

    #[test]
    fn test_oauth2_deserialization() {
        let json = serde_json::json!({
            "route_id": "r1",
            "auth_type": "oauth2_client_credentials",
            "header_name": "",
            "header_value": "",
            "oauth2": {
                "token_url": "https://auth.example.com/token",
                "client_id": "my-client",
                "client_secret": "my-secret"
            }
        });
        let cred: BackendCredential = serde_json::from_value(json).unwrap();
        assert_eq!(cred.auth_type, AuthType::OAuth2ClientCredentials);
        assert!(cred.oauth2.is_some());
        let oauth2 = cred.oauth2.unwrap();
        assert_eq!(oauth2.client_id, "my-client");
    }

    #[test]
    fn test_oauth2_cache_invalidation_on_upsert() {
        let store = CredentialStore::new();
        store.upsert(make_oauth2_cred("r1"));
        // Manually inject a cached token
        store.oauth2_tokens.write().insert(
            "r1".to_string(),
            CachedOAuth2Token {
                access_token: "old-token".to_string(),
                expires_at: Instant::now() + Duration::from_secs(3600),
            },
        );
        assert_eq!(store.oauth2_cache_count(), 1);
        // Upsert should clear the cache
        store.upsert(make_oauth2_cred("r1"));
        assert_eq!(store.oauth2_cache_count(), 0);
    }

    #[test]
    fn test_oauth2_cache_invalidation_on_remove() {
        let store = CredentialStore::new();
        store.upsert(make_oauth2_cred("r1"));
        store.oauth2_tokens.write().insert(
            "r1".to_string(),
            CachedOAuth2Token {
                access_token: "old-token".to_string(),
                expires_at: Instant::now() + Duration::from_secs(3600),
            },
        );
        assert_eq!(store.oauth2_cache_count(), 1);
        store.remove("r1");
        assert_eq!(store.oauth2_cache_count(), 0);
    }

    #[tokio::test]
    async fn test_oauth2_token_missing_credential() {
        let store = CredentialStore::new();
        let client = reqwest::Client::new();
        let result = store.get_oauth2_token("nonexistent", &client).await;
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("No credential found"));
    }

    #[tokio::test]
    async fn test_oauth2_token_missing_config() {
        let store = CredentialStore::new();
        // Insert a static bearer credential (no OAuth2 config)
        store.upsert(make_cred("r1"));
        let client = reqwest::Client::new();
        let result = store.get_oauth2_token("r1", &client).await;
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("no OAuth2 config"));
    }

    #[tokio::test]
    async fn test_oauth2_cache_hit() {
        let store = CredentialStore::new();
        store.upsert(make_oauth2_cred("r1"));
        // Inject a valid cached token
        store.oauth2_tokens.write().insert(
            "r1".to_string(),
            CachedOAuth2Token {
                access_token: "cached-token-123".to_string(),
                expires_at: Instant::now() + Duration::from_secs(3600),
            },
        );
        let client = reqwest::Client::new();
        let result = store.get_oauth2_token("r1", &client).await;
        assert!(result.is_ok());
        assert_eq!(result.unwrap(), "cached-token-123");
    }

    #[test]
    fn test_static_cred_oauth2_field_omitted_in_json() {
        let cred = make_cred("r1");
        let json = serde_json::to_value(&cred).unwrap();
        // oauth2 field should be absent (skip_serializing_if = "Option::is_none")
        assert!(json.get("oauth2").is_none());
    }

    #[test]
    fn allowed_origin_is_optional_in_serialized_form() {
        // Payloads written before the field existed still deserialize, and a
        // credential without an origin serializes as it did before.
        let json = serde_json::to_value(make_cred("r1")).unwrap();
        assert!(json.get("allowed_origin").is_none());
        let cred: BackendCredential = serde_json::from_value(json).unwrap();
        assert_eq!(cred.allowed_origin, None);

        let bound = BackendCredential {
            allowed_origin: Some("https://api.example.com:443".to_string()),
            ..make_cred("mcp-tool:acme:payments")
        };
        let json = serde_json::to_value(&bound).unwrap();
        assert_eq!(json["allowed_origin"], "https://api.example.com:443");
        let cred: BackendCredential = serde_json::from_value(json).unwrap();
        assert_eq!(cred.allowed_origin, bound.allowed_origin);
    }

    #[test]
    fn normalize_origin_lowercases_and_makes_the_port_explicit() {
        for (input, expected) in [
            ("https://api.example.com", "https://api.example.com:443"),
            ("https://api.example.com:443", "https://api.example.com:443"),
            ("HTTPS://API.Example.COM/", "https://api.example.com:443"),
            ("http://api.example.com", "http://api.example.com:80"),
            ("http://api.example.com:80/", "http://api.example.com:80"),
            ("http://backend:8080", "http://backend:8080"),
            (
                "https://api.example.com:8443",
                "https://api.example.com:8443",
            ),
            ("http://127.0.0.1:9000", "http://127.0.0.1:9000"),
            ("http://[::1]:9000", "http://[::1]:9000"),
        ] {
            assert_eq!(
                normalize_origin(input).as_deref(),
                Some(expected),
                "{input}"
            );
        }
    }

    #[test]
    fn normalize_origin_rejects_values_that_are_not_an_origin() {
        for input in [
            "",
            "api.example.com",
            "api.example.com:443",
            "ftp://api.example.com",
            "https://",
            "https://api.example.com/v1",
            "https://api.example.com/?tenant=acme",
            "https://api.example.com/#top",
            "https://user@api.example.com",
            "https://user:pass@api.example.com",
            "https://api.example.com:notaport",
        ] {
            assert_eq!(normalize_origin(input), None, "{input}");
        }
    }

    #[test]
    fn url_origin_ignores_path_query_and_user_info() {
        for (url, expected) in [
            (
                "https://api.example.com/v1/orders?limit=5",
                "https://api.example.com:443",
            ),
            ("HTTP://Backend:8080/orders", "http://backend:8080"),
            (
                "http://api.example.com:8080@other.example.com/orders",
                "http://other.example.com:80",
            ),
        ] {
            assert_eq!(url_origin(url).as_deref(), Some(expected), "{url}");
        }
        for url in ["", "/orders", "ftp://api.example.com/orders"] {
            assert_eq!(url_origin(url), None, "{url}");
        }
    }

    #[test]
    fn credential_is_bound_to_its_allowed_origin_only() {
        let bound = |origin: Option<&str>| BackendCredential {
            allowed_origin: origin.map(str::to_string),
            ..make_cred("mcp-tool:acme:payments")
        };
        let url = "https://api.example.com/v1/orders";

        // Any spelling of the same origin matches.
        for origin in ["https://api.example.com:443", "HTTPS://API.example.com"] {
            assert!(bound(Some(origin)).is_bound_to_origin_of(url), "{origin}");
        }
        // Another scheme, host or port does not, nor does a missing or
        // malformed origin.
        for origin in [
            Some("http://api.example.com"),
            Some("https://api.example.com:8443"),
            Some("https://other.example.com"),
            Some("https://example.com"),
            Some("https://api.example.com/v1"),
            Some("not an origin"),
            None,
        ] {
            assert!(!bound(origin).is_bound_to_origin_of(url), "{origin:?}");
        }
        // A target without an origin never matches.
        let cred = bound(Some("https://api.example.com"));
        assert!(!cred.is_bound_to_origin_of("/v1/orders"));
    }
}
