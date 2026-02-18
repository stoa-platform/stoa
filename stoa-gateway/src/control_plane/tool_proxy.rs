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

    /// Get a reference to the inner HTTP client (for federation cache etc.)
    pub fn http_client(&self) -> &Client {
        &self.client
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

#[cfg(test)]
mod tests {
    use super::*;
    use wiremock::matchers::{header, method, path};
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
            client_secret: "secret".to_string(),
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
    async fn test_discover_tools_authenticated_with_fallback() {
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

        // Authenticated endpoint returns 401 → triggers fallback
        Mock::given(method("GET"))
            .and(path("/v1/mcp/tools"))
            .and(header("Authorization", "Bearer test-token"))
            .respond_with(ResponseTemplate::new(401))
            .mount(&mock_server)
            .await;

        // Unauthenticated fallback works
        Mock::given(method("GET"))
            .and(path("/v1/mcp/tools"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "tools": [{"name": "fallback_tool", "description": "ok", "inputSchema": {}}]
            })))
            .mount(&mock_server)
            .await;

        let oidc = OidcConfig {
            token_url: format!("{}/token", mock_server.uri()),
            client_id: "gw".to_string(),
            client_secret: "secret".to_string(),
        };

        let client = ToolProxyClient::new(&mock_server.uri(), Some(oidc));
        let tools = client.discover_tools().await.unwrap();
        assert_eq!(tools.len(), 1);
        assert_eq!(tools[0].name, "fallback_tool");
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
            client_secret: "s3cret".to_string(),
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
            client_secret: "wrong".to_string(),
        };

        let client = ToolProxyClient::new(&mock_server.uri(), Some(oidc));
        let result = client.get_token().await;
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("401"));
    }
}
