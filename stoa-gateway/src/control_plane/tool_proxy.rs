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

/// Keycloak token response
#[derive(Debug, Deserialize)]
struct TokenResponse {
    access_token: String,
    expires_in: u64,
    #[allow(dead_code)]
    #[serde(default)]
    token_type: String,
}

/// Cached access token
struct CachedToken {
    access_token: String,
    expires_at: Instant,
}

/// OIDC configuration for client credentials flow
#[derive(Clone, Debug)]
pub struct OidcConfig {
    pub token_url: String,
    pub client_id: String,
    pub client_secret: String,
}

/// HTTP client that proxies MCP tool operations to the Control Plane.
/// Authenticates via OIDC client credentials flow (Keycloak).
#[derive(Clone)]
pub struct ToolProxyClient {
    client: Client,
    base_url: String,
    oidc: Option<OidcConfig>,
    token_cache: Arc<RwLock<Option<CachedToken>>>,
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
            token_cache: Arc::new(RwLock::new(None)),
        }
    }

    /// Get the base URL for native tools
    pub fn base_url(&self) -> &str {
        &self.base_url
    }

    /// Get a valid access token, refreshing if expired.
    async fn get_token(&self) -> Result<String, String> {
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
        debug!(token_url = %oidc.token_url, client_id = %oidc.client_id, "Fetching OIDC token");

        let resp = self
            .client
            .post(&oidc.token_url)
            .form(&[
                ("grant_type", "client_credentials"),
                ("client_id", &oidc.client_id),
                ("client_secret", &oidc.client_secret),
            ])
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

        let expires_at = Instant::now() + Duration::from_secs(token_resp.expires_in);
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
        if self.oidc.is_some() {
            match self.discover_authenticated().await {
                Ok(tools) => return Ok(tools),
                Err(e) => {
                    warn!(error = %e, "Authenticated discovery failed, trying unauthenticated");
                }
            }
        }
        self.discover_unauthenticated().await
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
        if ctx.raw_token.is_some() || self.oidc.is_some() {
            match self.call_authenticated(tool, &args, ctx).await {
                Ok(result) => return Ok(result),
                Err(e) => {
                    warn!(tool, error = %e, "Authenticated call failed, trying unauthenticated");
                }
            }
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

        let payload = serde_json::json!({ "name": tool, "arguments": args });

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
