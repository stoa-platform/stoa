//! MCP Tool Proxy Client
//!
//! Lightweight HTTP client for:
//! - Discovering tools from the Control Plane (GitOps source of truth)
//! - Proxying tool calls to the Control Plane
//! - OIDC client credentials flow for Keycloak authentication
//!
//! Strategy:
//! - If OIDC configured and working → authenticated /mcp/v1/tools endpoints
//! - Fallback → unauthenticated /tools endpoints
//!
//! No gateway rebuild needed when tools are added/changed in Git.

use parking_lot::RwLock;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tracing::{debug, error, info, warn};

use crate::mcp::tools::ToolContext;
use crate::proxy::hardening::with_cp_resilience_generic;
use crate::resilience::CircuitBreakerRegistry;

/// A tool definition fetched from the Control Plane
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RemoteToolDef {
    pub name: String,
    pub description: String,
    #[serde(rename = "inputSchema")]
    pub input_schema: RemoteToolSchema,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RemoteToolSchema {
    #[serde(rename = "type", default = "default_object")]
    pub schema_type: String,
    #[serde(default)]
    pub properties: HashMap<String, Value>,
    #[serde(default)]
    pub required: Vec<String>,
}

fn default_object() -> String {
    "object".into()
}

/// Response from CP tools list endpoint
#[derive(Debug, Deserialize)]
pub struct ToolsListResponse {
    pub tools: Vec<RemoteToolDef>,
}

/// A UAC-generated tool definition fetched from the Control Plane (CAB-605/606).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GeneratedToolDef {
    pub tool_name: String,
    pub description: Option<String>,
    pub input_schema: Option<Value>,
    pub output_schema: Option<Value>,
    pub backend_url: Option<String>,
    pub http_method: Option<String>,
    pub path_pattern: Option<String>,
    pub version: String,
    pub enabled: bool,
}

/// Response from CP generated-tools endpoint (CAB-605)
#[derive(Debug, Deserialize)]
pub struct GeneratedToolsResponse {
    pub tenant_id: String,
    pub tools: Vec<GeneratedToolDef>,
    pub total: usize,
}

/// Keycloak token response
#[derive(Debug, Deserialize)]
struct TokenResponse {
    access_token: String,
    expires_in: u64,
}

/// Cached access token
struct CachedToken {
    access_token: String,
    expires_at: Instant,
}

/// Assertion type for `private_key_jwt` client authentication (RFC 7523).
const CLIENT_ASSERTION_TYPE: &str = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer";

/// Lifetime of a signed client assertion.
const CLIENT_ASSERTION_TTL_SECS: i64 = 60;

/// Default upper bound for the lifetime of a cached service access token.
pub const DEFAULT_SERVICE_TOKEN_MAX_TTL_SECS: u64 = 300;

/// How the gateway authenticates to the token endpoint.
#[derive(Clone)]
pub enum ClientCredential {
    /// Shared client secret. Kept for tool discovery on deployments that have
    /// not moved to a signing key yet; not accepted for tool permissions.
    Secret(String),
    /// `private_key_jwt`: a short-lived RS256 assertion signed with a private
    /// key read from a mounted file (for example a Kubernetes Secret volume).
    /// The file is read when a token is requested, so key rotation only needs
    /// the mounted file to be updated. Its content is never logged.
    PrivateKeyJwt {
        key_path: std::path::PathBuf,
        key_id: Option<String>,
    },
}

impl ClientCredential {
    /// True when the credential is a signing key (`private_key_jwt`).
    pub fn is_private_key_jwt(&self) -> bool {
        matches!(self, Self::PrivateKeyJwt { .. })
    }
}

impl std::fmt::Debug for ClientCredential {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Secret(_) => f.write_str("Secret([REDACTED])"),
            Self::PrivateKeyJwt { key_path, key_id } => f
                .debug_struct("PrivateKeyJwt")
                .field("key_path", key_path)
                .field("key_id", key_id)
                .finish(),
        }
    }
}

/// OIDC configuration for the client credentials grant.
#[derive(Clone, Debug)]
pub struct OidcConfig {
    pub token_url: String,
    pub client_id: String,
    pub credential: ClientCredential,
    /// Upper bound applied to `expires_in` when caching service tokens.
    pub max_token_ttl: Duration,
}

impl OidcConfig {
    pub fn new(token_url: String, client_id: String, credential: ClientCredential) -> Self {
        Self {
            token_url,
            client_id,
            credential,
            max_token_ttl: Duration::from_secs(DEFAULT_SERVICE_TOKEN_MAX_TTL_SECS),
        }
    }

    /// Form parameters that authenticate the client at the token endpoint.
    async fn client_auth_params(&self) -> Result<Vec<(&'static str, String)>, String> {
        match &self.credential {
            ClientCredential::Secret(secret) => Ok(vec![("client_secret", secret.clone())]),
            ClientCredential::PrivateKeyJwt { key_path, key_id } => {
                let assertion =
                    sign_client_assertion(&self.client_id, &self.token_url, key_path, key_id)
                        .await?;
                Ok(vec![
                    ("client_assertion_type", CLIENT_ASSERTION_TYPE.to_string()),
                    ("client_assertion", assertion),
                ])
            }
        }
    }
}

#[derive(Serialize)]
struct ClientAssertionClaims<'a> {
    iss: &'a str,
    sub: &'a str,
    aud: &'a str,
    jti: String,
    iat: i64,
    nbf: i64,
    exp: i64,
}

/// Build and sign a `private_key_jwt` client assertion.
///
/// Errors never include key material: only the file path and a generic reason.
async fn sign_client_assertion(
    client_id: &str,
    token_url: &str,
    key_path: &std::path::Path,
    key_id: &Option<String>,
) -> Result<String, String> {
    let pem = tokio::fs::read(key_path)
        .await
        .map_err(|e| format!("client key {} unreadable: {}", key_path.display(), e.kind()))?;
    let key = jsonwebtoken::EncodingKey::from_rsa_pem(&pem).map_err(|_| {
        format!(
            "client key {} is not a valid RSA PEM key",
            key_path.display()
        )
    })?;
    drop(pem);
    let now = chrono::Utc::now().timestamp();
    let claims = ClientAssertionClaims {
        iss: client_id,
        sub: client_id,
        aud: token_url,
        jti: uuid::Uuid::new_v4().to_string(),
        iat: now,
        nbf: now,
        exp: now + CLIENT_ASSERTION_TTL_SECS,
    };
    let mut header = jsonwebtoken::Header::new(jsonwebtoken::Algorithm::RS256);
    header.kid = key_id.clone();
    jsonwebtoken::encode(&header, &claims, &key)
        .map_err(|_| "client assertion signing failed".to_string())
}

/// HTTP client that proxies MCP tool operations to the Control Plane.
/// Authenticates via OIDC client credentials flow (Keycloak) or X-Gateway-Key
/// for internal endpoints (CAB-1817).
#[derive(Clone)]
pub struct ToolProxyClient {
    client: Client,
    base_url: String,
    oidc: Option<OidcConfig>,
    /// Gateway API key for internal endpoints (X-Gateway-Key auth).
    /// When set, tool discovery uses /v1/internal/gateways/ endpoints
    /// instead of /v1/mcp/ endpoints that require user JWT.
    api_key: Option<String>,
    token_cache: Arc<RwLock<Option<CachedToken>>>,
    /// Per-upstream circuit breaker registry for CP resilience (CAB-1542 Phase 2).
    cb_registry: Option<Arc<CircuitBreakerRegistry>>,
}

impl ToolProxyClient {
    pub fn new(base_url: &str, oidc: Option<OidcConfig>) -> Self {
        if oidc.is_some() {
            info!(base_url = %base_url, "ToolProxyClient initialized with OIDC auth");
        } else {
            warn!(base_url = %base_url, "ToolProxyClient initialized WITHOUT OIDC — using unauthenticated endpoints");
        }
        Self {
            client: Client::builder()
                .timeout(Duration::from_secs(30))
                .build()
                .expect("HTTP client"),
            base_url: base_url.trim_end_matches('/').to_string(),
            oidc,
            api_key: None,
            token_cache: Arc::new(RwLock::new(None)),
            cb_registry: None,
        }
    }

    /// Set the gateway API key for internal endpoint auth (CAB-1817).
    /// When set, discover_generated_tools uses /v1/internal/gateways/tools/generated
    /// with X-Gateway-Key header instead of OIDC Bearer token.
    pub fn with_api_key(mut self, api_key: String) -> Self {
        self.api_key = Some(api_key);
        self
    }

    /// Enable circuit breaker + retry for CP operations (CAB-1542 Phase 2).
    pub fn with_circuit_breakers(mut self, registry: Arc<CircuitBreakerRegistry>) -> Self {
        self.cb_registry = Some(registry);
        self
    }

    /// Get the base URL for native tools
    pub fn base_url(&self) -> &str {
        &self.base_url
    }

    /// Get a reference to the inner HTTP client (for federation cache etc.)
    pub fn http_client(&self) -> &Client {
        &self.client
    }

    /// True when the service client authenticates with `private_key_jwt`.
    pub fn uses_private_key_jwt(&self) -> bool {
        self.oidc
            .as_ref()
            .is_some_and(|oidc| oidc.credential.is_private_key_jwt())
    }

    /// Invalidate only the rejected token, preserving a concurrent refresh.
    pub(super) fn invalidate_token(&self, rejected: &str) {
        let mut cache = self.token_cache.write();
        if cache
            .as_ref()
            .is_some_and(|cached| cached.access_token == rejected)
        {
            *cache = None;
        }
    }

    /// Get a valid access token, refreshing if expired.
    pub(super) async fn get_token(&self) -> Result<String, String> {
        let oidc = match &self.oidc {
            Some(o) => o,
            None => return Err("OIDC not configured".into()),
        };

        // Check cache (with 30s safety margin before expiry)
        {
            let cache = self.token_cache.read();
            if let Some(cached) = cache.as_ref() {
                if cached.expires_at > Instant::now() + Duration::from_secs(30) {
                    return Ok(cached.access_token.clone());
                }
            }
        }

        // Fetch new token via client_credentials grant
        debug!(
            token_url = %oidc.token_url,
            client_id = %oidc.client_id,
            private_key_jwt = oidc.credential.is_private_key_jwt(),
            "Fetching OIDC token"
        );

        let mut form = vec![
            ("grant_type", "client_credentials".to_string()),
            ("client_id", oidc.client_id.clone()),
        ];
        form.extend(oidc.client_auth_params().await?);

        let resp = self
            .client
            .post(&oidc.token_url)
            .form(&form)
            .send()
            .await
            .map_err(|e| format!("Token request failed: {}", e))?;

        if !resp.status().is_success() {
            let status = resp.status().as_u16();
            let body = resp.text().await.unwrap_or_default();
            return Err(format!("Token endpoint returned {}: {}", status, body));
        }

        let token_resp: TokenResponse = resp
            .json()
            .await
            .map_err(|e| format!("Failed to parse token response: {}", e))?;

        let lifetime = Duration::from_secs(token_resp.expires_in).min(oidc.max_token_ttl);
        let expires_at = Instant::now() + lifetime;
        let access_token = token_resp.access_token.clone();

        // Cache the token
        {
            let mut cache = self.token_cache.write();
            *cache = Some(CachedToken {
                access_token: token_resp.access_token,
                expires_at,
            });
        }

        info!(
            expires_in = token_resp.expires_in,
            "OIDC access token acquired"
        );
        Ok(access_token)
    }

    /// Discover available tools from the Control Plane.
    ///
    /// Strategy:
    /// 1. If OIDC configured → try GET /v1/mcp/tools (authenticated)
    /// 2. Fallback → GET /v1/mcp/tools (unauthenticated)
    pub async fn discover_tools(&self) -> Result<Vec<RemoteToolDef>, String> {
        if let Some(ref cb_registry) = self.cb_registry {
            let this = self.clone();
            with_cp_resilience_generic(cb_registry, "cp-discover-tools", || {
                let t = this.clone();
                async move { t.discover_tools_inner().await }
            })
            .await
        } else {
            self.discover_tools_inner().await
        }
    }

    async fn discover_tools_inner(&self) -> Result<Vec<RemoteToolDef>, String> {
        // Prefer internal endpoint with API key (CAB-1817: sidecars don't have OIDC)
        if let Some(ref key) = self.api_key {
            return self.discover_with_api_key(key).await;
        }
        if self.oidc.is_some() {
            // When OIDC is configured, use authenticated discovery only.
            // Unauthenticated fallback would always 401 since the endpoint requires auth.
            self.discover_authenticated().await
        } else {
            self.discover_unauthenticated().await
        }
    }

    async fn discover_with_api_key(&self, api_key: &str) -> Result<Vec<RemoteToolDef>, String> {
        let url = format!("{}/v1/internal/gateways/tools", self.base_url);
        debug!(url = %url, "Discovering tools (internal, API key)");

        let resp = self
            .client
            .get(&url)
            .header("X-Gateway-Key", api_key)
            .send()
            .await
            .map_err(|e| e.to_string())?;

        if !resp.status().is_success() {
            let status = resp.status().as_u16();
            let body = resp.text().await.unwrap_or_default();
            return Err(format!("Internal discovery error {}: {}", status, body));
        }

        let list: ToolsListResponse = resp.json().await.map_err(|e| e.to_string())?;
        info!(
            count = list.tools.len(),
            "Discovered tools (internal, API key)"
        );
        Ok(list.tools)
    }

    async fn discover_authenticated(&self) -> Result<Vec<RemoteToolDef>, String> {
        let url = format!("{}/v1/mcp/tools", self.base_url);
        debug!(url = %url, "Discovering tools (authenticated)");

        let token = self.get_token().await?;
        let resp = self
            .client
            .get(&url)
            .header("Authorization", format!("Bearer {}", token))
            .send()
            .await
            .map_err(|e| e.to_string())?;

        if !resp.status().is_success() {
            let status = resp.status().as_u16();
            let body = resp.text().await.unwrap_or_default();
            return Err(format!("Auth discovery error {}: {}", status, body));
        }

        let list: ToolsListResponse = resp.json().await.map_err(|e| e.to_string())?;
        info!(count = list.tools.len(), "Discovered tools (authenticated)");
        Ok(list.tools)
    }

    async fn discover_unauthenticated(&self) -> Result<Vec<RemoteToolDef>, String> {
        let url = format!("{}/v1/mcp/tools", self.base_url);
        debug!(url = %url, "Discovering tools (unauthenticated)");

        let resp = self.client.get(&url).send().await.map_err(|e| {
            warn!(error = %e, "Failed to reach Control Plane");
            e.to_string()
        })?;

        if !resp.status().is_success() {
            let status = resp.status().as_u16();
            let body = resp.text().await.unwrap_or_default();
            return Err(format!("Discovery error {}: {}", status, body));
        }

        let list: ToolsListResponse = resp.json().await.map_err(|e| e.to_string())?;
        info!(
            count = list.tools.len(),
            "Discovered tools (unauthenticated)"
        );
        Ok(list.tools)
    }

    /// Discover UAC-generated tools for a tenant from the Control Plane (CAB-605/606).
    ///
    /// Strategy (CAB-1817):
    /// 1. If API key configured → use internal endpoint with X-Gateway-Key auth
    /// 2. Else if OIDC configured → use user-facing endpoint with Bearer token
    /// 3. Fallback → unauthenticated request (will 401 on protected endpoints)
    pub async fn discover_generated_tools(
        &self,
        tenant_id: &str,
    ) -> Result<Vec<GeneratedToolDef>, String> {
        // Prefer internal endpoint with API key (CAB-1817: sidecars don't have OIDC)
        if let Some(ref key) = self.api_key {
            let url = format!(
                "{}/v1/internal/gateways/tools/generated?tenant_id={}",
                self.base_url, tenant_id
            );
            debug!(url = %url, tenant_id, "Discovering UAC-generated tools (internal, API key)");

            let resp = self
                .client
                .get(&url)
                .header("X-Gateway-Key", key.as_str())
                .send()
                .await
                .map_err(|e| {
                    warn!(tenant_id, error = %e, "Failed to discover generated tools (internal)");
                    e.to_string()
                })?;

            if !resp.status().is_success() {
                let status = resp.status().as_u16();
                let body = resp.text().await.unwrap_or_default();
                return Err(format!(
                    "Generated tools discovery error {}: {}",
                    status, body
                ));
            }

            let list: GeneratedToolsResponse = resp.json().await.map_err(|e| e.to_string())?;
            info!(
                count = list.tools.len(),
                tenant_id, "Discovered UAC-generated tools (internal)"
            );
            return Ok(list.tools.into_iter().filter(|t| t.enabled).collect());
        }

        // Fallback: user-facing endpoint with OIDC token
        let url = format!(
            "{}/v1/mcp/generated-tools?tenant_id={}",
            self.base_url, tenant_id
        );
        debug!(url = %url, tenant_id, "Discovering UAC-generated tools");

        let mut req = self.client.get(&url);

        // Use OIDC token if available
        if self.oidc.is_some() {
            if let Ok(token) = self.get_token().await {
                req = req.header("Authorization", format!("Bearer {}", token));
            }
        }

        let resp = req.send().await.map_err(|e| {
            warn!(tenant_id, error = %e, "Failed to discover generated tools");
            e.to_string()
        })?;

        if !resp.status().is_success() {
            let status = resp.status().as_u16();
            let body = resp.text().await.unwrap_or_default();
            return Err(format!(
                "Generated tools discovery error {}: {}",
                status, body
            ));
        }

        let list: GeneratedToolsResponse = resp.json().await.map_err(|e| e.to_string())?;
        info!(
            count = list.tools.len(),
            tenant_id, "Discovered UAC-generated tools"
        );
        Ok(list.tools.into_iter().filter(|t| t.enabled).collect())
    }

    /// Proxy a tool call to the Control Plane API.
    ///
    /// Strategy:
    /// 1. If user token present → use it directly (user identity flows through)
    /// 2. Else if OIDC configured → use service account token
    /// 3. Fallback → unauthenticated endpoint
    ///
    /// Identity headers (X-User-Id, X-User-Email, X-User-Roles, X-Tenant-ID)
    /// are forwarded so the CP can enforce per-user policies.
    pub async fn call_tool(
        &self,
        tool: &str,
        args: Value,
        ctx: &ToolContext,
    ) -> Result<Value, String> {
        if let Some(ref cb_registry) = self.cb_registry {
            let this = self.clone();
            let tool_name = tool.to_string();
            let args_owned = args.clone();
            let ctx_owned = ctx.clone();
            with_cp_resilience_generic(cb_registry, &format!("cp-call-tool:{}", tool), || {
                let t = this.clone();
                let tn = tool_name.clone();
                let a = args_owned.clone();
                let c = ctx_owned.clone();
                async move { t.call_tool_inner(&tn, a, &c).await }
            })
            .await
        } else {
            self.call_tool_inner(tool, args, ctx).await
        }
    }

    async fn call_tool_inner(
        &self,
        tool: &str,
        args: Value,
        ctx: &ToolContext,
    ) -> Result<Value, String> {
        if ctx.raw_token.is_some() || self.oidc.is_some() {
            return self.call_authenticated(tool, &args, ctx).await;
        }
        self.call_unauthenticated(tool, &args, &ctx.tenant_id).await
    }

    async fn call_authenticated(
        &self,
        tool: &str,
        args: &Value,
        ctx: &ToolContext,
    ) -> Result<Value, String> {
        let url = format!("{}/v1/mcp/tools/{}/invoke", self.base_url, tool);

        // Use user token if present, otherwise fall back to service account
        let token = if let Some(ref user_token) = ctx.raw_token {
            debug!(tool, url = %url, "Proxying tool call with user token");
            user_token.clone()
        } else {
            debug!(tool, url = %url, "Proxying tool call with service account token");
            self.get_token().await?
        };

        // Inject _skill_context into arguments if present (CAB-1365)
        let enriched_args = if let Some(ref instructions) = ctx.skill_instructions {
            let mut args_obj = args.clone();
            if let Some(obj) = args_obj.as_object_mut() {
                obj.insert(
                    "_skill_context".to_string(),
                    serde_json::Value::String(instructions.clone()),
                );
            }
            args_obj
        } else {
            args.clone()
        };

        let payload = serde_json::json!({ "name": tool, "arguments": enriched_args });

        let mut req = self
            .client
            .post(&url)
            .header("Authorization", format!("Bearer {}", token))
            .header("Content-Type", "application/json")
            .header("X-Tenant-ID", &ctx.tenant_id);

        // Forward user identity headers
        if let Some(ref uid) = ctx.user_id {
            req = req.header("X-User-Id", uid);
        }
        if let Some(ref email) = ctx.user_email {
            req = req.header("X-User-Email", email);
        }
        if !ctx.roles.is_empty() {
            req = req.header("X-User-Roles", ctx.roles.join(","));
        }

        let resp = req.json(&payload).send().await.map_err(|e| e.to_string())?;

        if !resp.status().is_success() {
            let status = resp.status().as_u16();
            let body = resp.text().await.unwrap_or_default();
            return Err(format!("CP error {}: {}", status, body));
        }

        resp.json().await.map_err(|e| e.to_string())
    }

    async fn call_unauthenticated(
        &self,
        tool: &str,
        args: &Value,
        tenant_id: &str,
    ) -> Result<Value, String> {
        let url = format!("{}/v1/mcp/tools/{}/invoke", self.base_url, tool);
        debug!(tool, url = %url, "Proxying tool call (unauthenticated)");

        let payload = serde_json::json!({ "name": tool, "arguments": args });

        let resp = self
            .client
            .post(&url)
            .header("Content-Type", "application/json")
            .header("X-Tenant-ID", tenant_id)
            .json(&payload)
            .send()
            .await
            .map_err(|e| {
                error!(tool, error = %e, "Control Plane request failed");
                e.to_string()
            })?;

        if !resp.status().is_success() {
            let status = resp.status().as_u16();
            let body = resp.text().await.unwrap_or_default();
            error!(tool, status, body = %body, "Control Plane returned error");
            return Err(format!("CP error {}: {}", status, body));
        }

        resp.json().await.map_err(|e| {
            error!(tool, error = %e, "Failed to parse Control Plane response");
            e.to_string()
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use wiremock::matchers::{body_string_contains, header, method, path};
    use wiremock::{Mock, MockServer, ResponseTemplate};

    fn make_tool_context() -> ToolContext {
        ToolContext {
            tenant_id: "acme".to_string(),
            user_id: Some("uid-1".to_string()),
            user_email: Some("user@test.com".to_string()),
            request_id: "req-1".to_string(),
            roles: vec!["admin".to_string()],
            scopes: vec!["stoa:read".to_string()],
            raw_token: None,
            skill_instructions: None,
            progress_token: None,
            consumer_id: "test-consumer".to_string(),
            from_control_plane: false,
        }
    }

    #[test]
    fn test_tool_proxy_client_new_no_oidc() {
        let client = ToolProxyClient::new("http://localhost:8000", None);
        assert_eq!(client.base_url(), "http://localhost:8000");
        assert!(client.oidc.is_none());
    }

    #[test]
    fn test_tool_proxy_client_new_with_oidc() {
        let oidc = OidcConfig {
            token_url: "http://kc/token".to_string(),
            client_id: "gw".to_string(),
            credential: ClientCredential::Secret("secret".to_string()),
            max_token_ttl: Duration::from_secs(DEFAULT_SERVICE_TOKEN_MAX_TTL_SECS),
        };
        let client = ToolProxyClient::new("http://localhost:8000/", Some(oidc));
        // Trailing slash stripped
        assert_eq!(client.base_url(), "http://localhost:8000");
        assert!(client.oidc.is_some());
    }

    #[test]
    fn test_remote_tool_def_deserialize() {
        let json = r#"{
            "name": "list_users",
            "description": "List all users",
            "inputSchema": {
                "type": "object",
                "properties": {"page": {"type": "integer"}},
                "required": ["page"]
            }
        }"#;

        let tool: RemoteToolDef = serde_json::from_str(json).unwrap();
        assert_eq!(tool.name, "list_users");
        assert_eq!(tool.description, "List all users");
        assert_eq!(tool.input_schema.schema_type, "object");
        assert!(tool.input_schema.properties.contains_key("page"));
        assert_eq!(tool.input_schema.required, vec!["page"]);
    }

    #[test]
    fn test_remote_tool_def_deserialize_minimal() {
        let json = r#"{
            "name": "health",
            "description": "Check health",
            "inputSchema": {}
        }"#;

        let tool: RemoteToolDef = serde_json::from_str(json).unwrap();
        assert_eq!(tool.name, "health");
        // default_object() should provide "object"
        assert_eq!(tool.input_schema.schema_type, "object");
        assert!(tool.input_schema.properties.is_empty());
        assert!(tool.input_schema.required.is_empty());
    }

    #[test]
    fn test_tools_list_response_deserialize() {
        let json = r#"{"tools": [
            {"name": "t1", "description": "d1", "inputSchema": {}},
            {"name": "t2", "description": "d2", "inputSchema": {"type": "object"}}
        ]}"#;

        let resp: ToolsListResponse = serde_json::from_str(json).unwrap();
        assert_eq!(resp.tools.len(), 2);
        assert_eq!(resp.tools[0].name, "t1");
        assert_eq!(resp.tools[1].name, "t2");
    }

    #[tokio::test]
    async fn test_discover_tools_unauthenticated() {
        let mock_server = MockServer::start().await;

        Mock::given(method("GET"))
            .and(path("/v1/mcp/tools"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "tools": [
                    {"name": "tool_a", "description": "A", "inputSchema": {}},
                    {"name": "tool_b", "description": "B", "inputSchema": {}}
                ]
            })))
            .mount(&mock_server)
            .await;

        let client = ToolProxyClient::new(&mock_server.uri(), None);
        let tools = client.discover_tools().await.unwrap();
        assert_eq!(tools.len(), 2);
        assert_eq!(tools[0].name, "tool_a");
    }

    #[tokio::test]
    async fn test_discover_tools_server_error() {
        let mock_server = MockServer::start().await;

        Mock::given(method("GET"))
            .and(path("/v1/mcp/tools"))
            .respond_with(ResponseTemplate::new(500).set_body_string("Internal error"))
            .mount(&mock_server)
            .await;

        let client = ToolProxyClient::new(&mock_server.uri(), None);
        let result = client.discover_tools().await;
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("500"));
    }

    #[tokio::test]
    async fn test_discover_tools_authenticated_failure_no_fallback() {
        let mock_server = MockServer::start().await;

        // Token endpoint
        Mock::given(method("POST"))
            .and(path("/token"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "access_token": "test-token",
                "expires_in": 300,
                "token_type": "Bearer"
            })))
            .mount(&mock_server)
            .await;

        // Authenticated endpoint returns 401 — no unauthenticated fallback
        Mock::given(method("GET"))
            .and(path("/v1/mcp/tools"))
            .and(header("Authorization", "Bearer test-token"))
            .respond_with(ResponseTemplate::new(401))
            .mount(&mock_server)
            .await;

        let oidc = OidcConfig {
            token_url: format!("{}/token", mock_server.uri()),
            client_id: "gw".to_string(),
            credential: ClientCredential::Secret("secret".to_string()),
            max_token_ttl: Duration::from_secs(DEFAULT_SERVICE_TOKEN_MAX_TTL_SECS),
        };

        let client = ToolProxyClient::new(&mock_server.uri(), Some(oidc));
        let result = client.discover_tools().await;
        assert!(
            result.is_err(),
            "Should fail without unauthenticated fallback"
        );
        assert!(result.unwrap_err().contains("401"));
    }

    #[tokio::test]
    async fn test_call_tool_unauthenticated() {
        let mock_server = MockServer::start().await;

        Mock::given(method("POST"))
            .and(path("/v1/mcp/tools/list_users/invoke"))
            .and(header("X-Tenant-ID", "acme"))
            .respond_with(
                ResponseTemplate::new(200)
                    .set_body_json(serde_json::json!({"result": "ok", "users": []})),
            )
            .mount(&mock_server)
            .await;

        let client = ToolProxyClient::new(&mock_server.uri(), None);
        let ctx = make_tool_context();
        let args = serde_json::json!({"page": 1});

        let result = client.call_tool("list_users", args, &ctx).await.unwrap();
        assert_eq!(result["result"], "ok");
    }

    #[tokio::test]
    async fn test_call_tool_with_user_token() {
        let mock_server = MockServer::start().await;

        Mock::given(method("POST"))
            .and(path("/v1/mcp/tools/my_tool/invoke"))
            .and(header("Authorization", "Bearer user-jwt-token"))
            .and(header("X-User-Id", "uid-1"))
            .and(header("X-User-Email", "user@test.com"))
            .and(header("X-User-Roles", "admin"))
            .and(header("X-Tenant-ID", "acme"))
            .respond_with(
                ResponseTemplate::new(200).set_body_json(serde_json::json!({"status": "done"})),
            )
            .mount(&mock_server)
            .await;

        let client = ToolProxyClient::new(&mock_server.uri(), None);
        let mut ctx = make_tool_context();
        ctx.raw_token = Some("user-jwt-token".to_string());

        let result = client
            .call_tool("my_tool", serde_json::json!({}), &ctx)
            .await
            .unwrap();
        assert_eq!(result["status"], "done");
    }

    #[tokio::test]
    async fn test_call_tool_server_error_fallback() {
        let mock_server = MockServer::start().await;

        // All calls fail
        Mock::given(method("POST"))
            .and(path("/v1/mcp/tools/bad_tool/invoke"))
            .respond_with(ResponseTemplate::new(500).set_body_string("boom"))
            .mount(&mock_server)
            .await;

        let client = ToolProxyClient::new(&mock_server.uri(), None);
        let ctx = make_tool_context();
        let result = client
            .call_tool("bad_tool", serde_json::json!({}), &ctx)
            .await;
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("500"));
    }

    #[tokio::test]
    async fn test_call_tool_forwards_skill_context() {
        let mock_server = MockServer::start().await;

        Mock::given(method("POST"))
            .and(path("/v1/mcp/tools/my_tool/invoke"))
            .and(body_string_contains("_skill_context"))
            .and(body_string_contains("Always respond in French"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({"ok": true})))
            .mount(&mock_server)
            .await;

        let client = ToolProxyClient::new(&mock_server.uri(), None);
        let mut ctx = make_tool_context();
        ctx.raw_token = Some("jwt-token".to_string());
        ctx.skill_instructions = Some("Always respond in French".to_string());

        let result = client
            .call_tool("my_tool", serde_json::json!({"query": "hello"}), &ctx)
            .await
            .unwrap();
        assert_eq!(result["ok"], true);
    }

    #[tokio::test]
    async fn test_call_tool_no_skill_context_when_none() {
        let mock_server = MockServer::start().await;

        Mock::given(method("POST"))
            .and(path("/v1/mcp/tools/clean_tool/invoke"))
            .respond_with(
                ResponseTemplate::new(200).set_body_json(serde_json::json!({"clean": true})),
            )
            .mount(&mock_server)
            .await;

        let client = ToolProxyClient::new(&mock_server.uri(), None);
        let mut ctx = make_tool_context();
        ctx.raw_token = Some("jwt-token".to_string());

        let result = client
            .call_tool("clean_tool", serde_json::json!({}), &ctx)
            .await
            .unwrap();
        assert_eq!(result["clean"], true);
    }

    // === CAB-606: Generated tool discovery tests ===

    #[test]
    fn test_generated_tool_def_deserialize() {
        let json = r#"{
            "tool_name": "acme:billing:create_invoice",
            "description": "Create a new invoice",
            "input_schema": {"type": "object", "properties": {"amount": {"type": "number"}}},
            "output_schema": null,
            "backend_url": "https://billing.acme.com/v1/invoices",
            "http_method": "POST",
            "path_pattern": "/v1/invoices",
            "version": "1.0.0",
            "enabled": true
        }"#;

        let tool: GeneratedToolDef = serde_json::from_str(json).unwrap();
        assert_eq!(tool.tool_name, "acme:billing:create_invoice");
        assert_eq!(tool.description.as_deref(), Some("Create a new invoice"));
        assert_eq!(tool.http_method.as_deref(), Some("POST"));
        assert!(tool.enabled);
    }

    #[test]
    fn test_generated_tools_response_deserialize() {
        let json = r#"{
            "tenant_id": "acme",
            "tools": [
                {"tool_name": "t1", "version": "1.0", "enabled": true},
                {"tool_name": "t2", "version": "1.0", "enabled": false}
            ],
            "total": 2
        }"#;

        let resp: GeneratedToolsResponse = serde_json::from_str(json).unwrap();
        assert_eq!(resp.tenant_id, "acme");
        assert_eq!(resp.tools.len(), 2);
        assert_eq!(resp.total, 2);
    }

    #[tokio::test]
    async fn test_discover_generated_tools_success() {
        let mock_server = MockServer::start().await;

        Mock::given(method("GET"))
            .and(path("/v1/mcp/generated-tools"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "tenant_id": "acme",
                "tools": [
                    {"tool_name": "acme:billing:create_invoice", "version": "1.0", "enabled": true},
                    {"tool_name": "acme:billing:list_invoices", "version": "1.0", "enabled": true},
                    {"tool_name": "acme:billing:deprecated_tool", "version": "0.9", "enabled": false}
                ],
                "total": 3
            })))
            .mount(&mock_server)
            .await;

        let client = ToolProxyClient::new(&mock_server.uri(), None);
        let tools = client.discover_generated_tools("acme").await.unwrap();
        // Only enabled tools returned
        assert_eq!(tools.len(), 2);
        assert_eq!(tools[0].tool_name, "acme:billing:create_invoice");
        assert_eq!(tools[1].tool_name, "acme:billing:list_invoices");
    }

    #[tokio::test]
    async fn test_discover_generated_tools_server_error() {
        let mock_server = MockServer::start().await;

        Mock::given(method("GET"))
            .and(path("/v1/mcp/generated-tools"))
            .respond_with(ResponseTemplate::new(500).set_body_string("Internal error"))
            .mount(&mock_server)
            .await;

        let client = ToolProxyClient::new(&mock_server.uri(), None);
        let result = client.discover_generated_tools("acme").await;
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("500"));
    }

    #[tokio::test]
    async fn test_discover_generated_tools_empty_tenant() {
        let mock_server = MockServer::start().await;

        Mock::given(method("GET"))
            .and(path("/v1/mcp/generated-tools"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "tenant_id": "empty-corp",
                "tools": [],
                "total": 0
            })))
            .mount(&mock_server)
            .await;

        let client = ToolProxyClient::new(&mock_server.uri(), None);
        let tools = client.discover_generated_tools("empty-corp").await.unwrap();
        assert!(tools.is_empty());
    }

    #[tokio::test]
    async fn test_get_token_no_oidc() {
        let client = ToolProxyClient::new("http://localhost:8000", None);
        let result = client.get_token().await;
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("OIDC not configured"));
    }

    #[tokio::test]
    async fn test_get_token_success_and_cache() {
        let mock_server = MockServer::start().await;

        Mock::given(method("POST"))
            .and(path("/token"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "access_token": "fresh-token",
                "expires_in": 3600,
                "token_type": "Bearer"
            })))
            .expect(1) // Should only be called once due to caching
            .mount(&mock_server)
            .await;

        let oidc = OidcConfig {
            token_url: format!("{}/token", mock_server.uri()),
            client_id: "gw".to_string(),
            credential: ClientCredential::Secret("s3cret".to_string()),
            max_token_ttl: Duration::from_secs(DEFAULT_SERVICE_TOKEN_MAX_TTL_SECS),
        };

        let client = ToolProxyClient::new(&mock_server.uri(), Some(oidc));

        // First call - fetches token
        let token1 = client.get_token().await.unwrap();
        assert_eq!(token1, "fresh-token");

        // Second call - should use cache (mock expects exactly 1 call)
        let token2 = client.get_token().await.unwrap();
        assert_eq!(token2, "fresh-token");
    }

    #[tokio::test]
    async fn test_get_token_error_response() {
        let mock_server = MockServer::start().await;

        Mock::given(method("POST"))
            .and(path("/token"))
            .respond_with(ResponseTemplate::new(401).set_body_string("bad credentials"))
            .mount(&mock_server)
            .await;

        let oidc = OidcConfig {
            token_url: format!("{}/token", mock_server.uri()),
            client_id: "gw".to_string(),
            credential: ClientCredential::Secret("wrong".to_string()),
            max_token_ttl: Duration::from_secs(DEFAULT_SERVICE_TOKEN_MAX_TTL_SECS),
        };

        let client = ToolProxyClient::new(&mock_server.uri(), Some(oidc));
        let result = client.get_token().await;
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("401"));
    }

    // === CAB-1817: API key auth for internal tool discovery ===

    #[test]
    fn test_with_api_key_sets_field() {
        let client = ToolProxyClient::new("http://localhost:8000", None)
            .with_api_key("gw-secret-key".to_string());
        assert_eq!(client.api_key.as_deref(), Some("gw-secret-key"));
    }

    #[test]
    fn test_without_api_key_field_is_none() {
        let client = ToolProxyClient::new("http://localhost:8000", None);
        assert!(client.api_key.is_none());
    }

    #[tokio::test]
    async fn test_discover_tools_with_api_key() {
        let mock_server = MockServer::start().await;

        Mock::given(method("GET"))
            .and(path("/v1/internal/gateways/tools"))
            .and(header("X-Gateway-Key", "gw-key-123"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "tools": [
                    {"name": "tool_a", "description": "A", "inputSchema": {}},
                    {"name": "tool_b", "description": "B", "inputSchema": {}}
                ]
            })))
            .mount(&mock_server)
            .await;

        let client =
            ToolProxyClient::new(&mock_server.uri(), None).with_api_key("gw-key-123".to_string());
        let tools = client.discover_tools().await.unwrap();
        assert_eq!(tools.len(), 2);
        assert_eq!(tools[0].name, "tool_a");
    }

    #[tokio::test]
    async fn test_discover_tools_api_key_preferred_over_oidc() {
        let mock_server = MockServer::start().await;

        // Internal endpoint (should be called)
        Mock::given(method("GET"))
            .and(path("/v1/internal/gateways/tools"))
            .and(header("X-Gateway-Key", "gw-key"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "tools": [{"name": "internal_tool", "description": "I", "inputSchema": {}}]
            })))
            .expect(1)
            .mount(&mock_server)
            .await;

        // OIDC endpoint (should NOT be called)
        Mock::given(method("GET"))
            .and(path("/v1/mcp/tools"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "tools": [{"name": "oidc_tool", "description": "O", "inputSchema": {}}]
            })))
            .expect(0)
            .mount(&mock_server)
            .await;

        let oidc = OidcConfig {
            token_url: format!("{}/token", mock_server.uri()),
            client_id: "gw".to_string(),
            credential: ClientCredential::Secret("secret".to_string()),
            max_token_ttl: Duration::from_secs(DEFAULT_SERVICE_TOKEN_MAX_TTL_SECS),
        };

        let client =
            ToolProxyClient::new(&mock_server.uri(), Some(oidc)).with_api_key("gw-key".to_string());
        let tools = client.discover_tools().await.unwrap();
        assert_eq!(tools.len(), 1);
        assert_eq!(tools[0].name, "internal_tool");
    }

    #[tokio::test]
    async fn test_discover_generated_tools_with_api_key() {
        let mock_server = MockServer::start().await;

        Mock::given(method("GET"))
            .and(path("/v1/internal/gateways/tools/generated"))
            .and(header("X-Gateway-Key", "gw-key-123"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "tenant_id": "acme",
                "tools": [
                    {"tool_name": "acme:billing:create", "version": "1.0", "enabled": true},
                    {"tool_name": "acme:billing:disabled", "version": "1.0", "enabled": false}
                ],
                "total": 2
            })))
            .mount(&mock_server)
            .await;

        let client =
            ToolProxyClient::new(&mock_server.uri(), None).with_api_key("gw-key-123".to_string());
        let tools = client.discover_generated_tools("acme").await.unwrap();
        // Only enabled tools returned
        assert_eq!(tools.len(), 1);
        assert_eq!(tools[0].tool_name, "acme:billing:create");
    }

    #[tokio::test]
    async fn test_discover_tools_api_key_401_propagated() {
        let mock_server = MockServer::start().await;

        Mock::given(method("GET"))
            .and(path("/v1/internal/gateways/tools"))
            .respond_with(ResponseTemplate::new(401).set_body_string("Invalid gateway key"))
            .mount(&mock_server)
            .await;

        let client =
            ToolProxyClient::new(&mock_server.uri(), None).with_api_key("bad-key".to_string());
        let result = client.discover_tools().await;
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("401"));
    }

    #[tokio::test]
    async fn tool_refusal_is_returned_as_is() {
        let server = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/v1/mcp/tools/denied/invoke"))
            .respond_with(ResponseTemplate::new(403))
            .mount(&server)
            .await;
        let client = ToolProxyClient::new(&server.uri(), None);
        let mut context = make_tool_context();
        context.raw_token = Some("fixture-user-token".to_string());
        assert!(client
            .call_tool("denied", serde_json::json!({}), &context)
            .await
            .is_err());
        let requests = server.received_requests().await.unwrap();
        assert_eq!(requests.len(), 1);
        assert!(requests[0].headers.contains_key("Authorization"));
    }

    // === private_key_jwt service authentication ===

    fn write_test_key(dir: &tempfile::TempDir) -> std::path::PathBuf {
        let key_path = dir.path().join("client-key.pem");
        std::fs::write(&key_path, crate::auth::jwt::tests::test_signing_pem()).unwrap();
        key_path
    }

    fn key_jwt_oidc(server: &MockServer, key_path: std::path::PathBuf) -> OidcConfig {
        OidcConfig::new(
            format!("{}/token", server.uri()),
            "stoa-mcp-gateway".to_string(),
            ClientCredential::PrivateKeyJwt {
                key_path,
                key_id: Some("gw-key-1".to_string()),
            },
        )
    }

    fn form_value(body: &[u8], key: &str) -> Option<String> {
        url::form_urlencoded::parse(body)
            .find(|(name, _)| name == key)
            .map(|(_, value)| value.into_owned())
    }

    #[tokio::test]
    async fn private_key_jwt_sends_signed_short_lived_assertion() {
        let server = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/token"))
            .and(body_string_contains("client_assertion_type="))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "access_token": "service-access", "expires_in": 300
            })))
            .expect(1)
            .mount(&server)
            .await;
        let dir = tempfile::tempdir().unwrap();
        let client = ToolProxyClient::new(
            &server.uri(),
            Some(key_jwt_oidc(&server, write_test_key(&dir))),
        );

        assert_eq!(client.get_token().await.unwrap(), "service-access");

        let requests = server.received_requests().await.unwrap();
        let body = &requests[0].body;
        assert_eq!(
            form_value(body, "grant_type").as_deref(),
            Some("client_credentials")
        );
        assert_eq!(
            form_value(body, "client_assertion_type").as_deref(),
            Some(CLIENT_ASSERTION_TYPE)
        );
        assert!(form_value(body, "client_secret").is_none());
        let assertion = form_value(body, "client_assertion").expect("client assertion");

        let header = jsonwebtoken::decode_header(&assertion).unwrap();
        assert_eq!(header.alg, jsonwebtoken::Algorithm::RS256);
        assert_eq!(header.kid.as_deref(), Some("gw-key-1"));
        let key = jsonwebtoken::DecodingKey::from_rsa_components(
            crate::auth::jwt::tests::test_modulus(),
            "AQAB",
        )
        .unwrap();
        let mut validation = jsonwebtoken::Validation::new(jsonwebtoken::Algorithm::RS256);
        let token_url = format!("{}/token", server.uri());
        validation.set_audience(&[token_url.as_str()]);
        validation.set_issuer(&["stoa-mcp-gateway"]);
        let claims = jsonwebtoken::decode::<serde_json::Value>(&assertion, &key, &validation)
            .expect("assertion signed with the configured key")
            .claims;
        assert_eq!(claims["sub"], "stoa-mcp-gateway");
        assert!(claims["jti"].as_str().is_some_and(|jti| !jti.is_empty()));
        let lifetime = claims["exp"].as_i64().unwrap() - claims["iat"].as_i64().unwrap();
        assert!(lifetime > 0 && lifetime <= CLIENT_ASSERTION_TTL_SECS);
    }

    #[tokio::test]
    async fn service_token_lifetime_is_capped() {
        let server = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/token"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "access_token": "long-lived", "expires_in": 86_400
            })))
            .expect(2)
            .mount(&server)
            .await;
        let dir = tempfile::tempdir().unwrap();
        let mut oidc = key_jwt_oidc(&server, write_test_key(&dir));
        // Below the 30 s refresh margin: every call must request a new token.
        oidc.max_token_ttl = Duration::from_secs(10);
        let client = ToolProxyClient::new(&server.uri(), Some(oidc));
        client.get_token().await.unwrap();
        client.get_token().await.unwrap();
    }

    #[tokio::test]
    async fn private_key_jwt_missing_key_file_fails_without_secret_fallback() {
        let server = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/token"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "access_token": "unexpected", "expires_in": 300
            })))
            .expect(0)
            .mount(&server)
            .await;
        let dir = tempfile::tempdir().unwrap();
        let client = ToolProxyClient::new(
            &server.uri(),
            Some(key_jwt_oidc(&server, dir.path().join("absent.pem"))),
        );
        let error = client.get_token().await.unwrap_err();
        assert!(error.contains("unreadable"), "{error}");
    }

    /// In-memory writer used to capture log output.
    #[derive(Clone, Default)]
    struct LogBuffer(Arc<parking_lot::Mutex<Vec<u8>>>);

    impl std::io::Write for LogBuffer {
        fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
            self.0.lock().extend_from_slice(buf);
            Ok(buf.len())
        }
        fn flush(&mut self) -> std::io::Result<()> {
            Ok(())
        }
    }

    impl<'a> tracing_subscriber::fmt::MakeWriter<'a> for LogBuffer {
        type Writer = LogBuffer;
        fn make_writer(&'a self) -> Self::Writer {
            self.clone()
        }
    }

    #[tokio::test]
    async fn private_key_is_never_logged() {
        let pem = crate::auth::jwt::tests::test_signing_pem();
        // A line from the middle of the key body, and an invalid key with a marker.
        let key_line = pem.lines().nth(3).unwrap().to_string();
        let marker = "MARKER-KEY-CONTENT-7f3a";

        let server = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/token"))
            .respond_with(ResponseTemplate::new(401).set_body_string("invalid_client"))
            .mount(&server)
            .await;
        let dir = tempfile::tempdir().unwrap();
        let valid = write_test_key(&dir);
        let invalid = dir.path().join("invalid.pem");
        // PEM armour assembled at runtime so the test source holds no key block.
        let armour = |edge: &str| format!("-----{edge} {}-----", ["PRIVATE", "KEY"].join(" "));
        std::fs::write(
            &invalid,
            format!("{}\n{marker}\n{}\n", armour("BEGIN"), armour("END")),
        )
        .unwrap();

        let logs = LogBuffer::default();
        let subscriber = tracing_subscriber::fmt()
            .with_max_level(tracing::Level::TRACE)
            .with_writer(logs.clone())
            .with_ansi(false)
            .finish();
        let _guard = tracing::subscriber::set_default(subscriber);

        let mut errors = Vec::new();
        for key_path in [valid, invalid] {
            let oidc = key_jwt_oidc(&server, key_path);
            errors.push(format!("{oidc:?}"));
            let client = ToolProxyClient::new(&server.uri(), Some(oidc));
            let error = client.get_token().await.unwrap_err();
            tracing::warn!(error = %error, "service token request failed");
            errors.push(error);
        }

        let captured = String::from_utf8(logs.0.lock().clone()).unwrap();
        assert!(!captured.is_empty(), "log capture must be active");
        for output in errors.iter().map(String::as_str).chain([captured.as_str()]) {
            assert!(!output.contains(&key_line), "key material in output");
            assert!(!output.contains(marker), "key file content in output");
            assert!(!output.contains("BEGIN PRIVATE KEY"), "PEM in output");
        }
    }

    #[test]
    fn client_secret_is_redacted_in_debug() {
        let oidc = OidcConfig::new(
            "http://kc/token".into(),
            "gw".into(),
            ClientCredential::Secret("do-not-print".into()),
        );
        assert!(!format!("{oidc:?}").contains("do-not-print"));
    }
}
