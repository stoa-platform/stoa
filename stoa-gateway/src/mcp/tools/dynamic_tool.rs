//! Dynamic Tool — HTTP endpoint tool created from K8s CRD or admin API
//!
//! Phase 7 (CAB-1105): Tools registered dynamically from Tool CRDs.
//! Each DynamicTool wraps an HTTP endpoint and exposes it as an MCP tool.

#![allow(dead_code)]

use std::sync::Arc;

use async_trait::async_trait;
use reqwest::Client;
use serde_json::Value;
use tracing::{debug, warn};

use super::{Tool, ToolAnnotations, ToolContext, ToolError, ToolResult, ToolSchema};
use crate::proxy::credentials::{url_origin, AuthType, CredentialStore, MCP_TOOL_KEY_PREFIX};
use crate::uac::Action;

/// Tenant marker of shared catalog tools that are registered for no tenant
/// in particular (coarse catalog discovery).
pub(crate) const PUBLIC_TENANT_MARKER: &str = "_public";

/// Value standing for an identity that is not known (see
/// [`ToolContext::consumer_id`]). It is never taken as a caller tenant.
const UNKNOWN_CALLER: &str = "unknown";

/// Classify the actual HTTP operation; unknown methods require write permission.
pub(super) fn action_for_http_method(method: &str) -> Action {
    match method.to_ascii_uppercase().as_str() {
        "GET" | "HEAD" | "OPTIONS" => Action::Read,
        "POST" => Action::Create,
        "PUT" | "PATCH" => Action::Update,
        "DELETE" => Action::Delete,
        _ => Action::Update,
    }
}

/// A dynamically registered tool that calls an HTTP endpoint.
///
/// Created from K8s Tool CRDs or admin API.
/// Namespace = tenant_id for isolation.
pub struct DynamicTool {
    /// Tool name ({namespace}_{crd_name})
    name: String,
    /// Human-readable description
    description: String,
    /// HTTP endpoint URL (base for per-op tools, full URL for coarse tools)
    endpoint: String,
    /// HTTP method (GET, POST, PUT, DELETE)
    method: String,
    /// JSON Schema for input
    input_schema: ToolSchema,
    /// Optional output schema
    output_schema: Option<Value>,
    /// Tool annotations (MCP 2025-03-26)
    annotations: Option<ToolAnnotations>,
    /// Required UAC action
    action: Action,
    /// Tenant ID for isolation (from CRD namespace)
    tenant_id: String,
    /// Skip tenant isolation check (for catalog API tools accessible to all)
    public: bool,
    /// Optional OpenAPI path pattern with `{name}` placeholders (CAB-2113 Phase 0).
    /// When set, the final URL is `endpoint + substituted(path_pattern)`.
    /// Tokens are pulled from the tool args and removed before the remainder is
    /// sent as query string (GET/DELETE) or JSON body (POST/PUT/PATCH).
    path_pattern: Option<String>,
    /// Backend credential store used to authenticate the upstream call.
    credential_store: Option<Arc<CredentialStore>>,
    /// Optional outbound address policy applied to both tool and OAuth2 URLs.
    outbound_policy: Option<Arc<crate::proxy::outbound_policy::OutboundAddressPolicy>>,
    /// HTTP client
    client: Client,
}

impl DynamicTool {
    /// Create a new DynamicTool from CRD-style parameters
    pub fn new(
        name: impl Into<String>,
        description: impl Into<String>,
        endpoint: impl Into<String>,
        method: impl Into<String>,
        input_schema: ToolSchema,
        tenant_id: impl Into<String>,
    ) -> Self {
        let method = method.into();
        let action = action_for_http_method(&method);
        Self {
            name: name.into(),
            description: description.into(),
            endpoint: endpoint.into(),
            method,
            input_schema,
            output_schema: None,
            annotations: None,
            action,
            tenant_id: tenant_id.into(),
            public: false,
            path_pattern: None,
            credential_store: None,
            outbound_policy: None,
            // Redirects are not followed: the request, and the backend
            // credential it carries, only go to the configured endpoint.
            client: Client::builder()
                .redirect(reqwest::redirect::Policy::none())
                .timeout(std::time::Duration::from_secs(30))
                .build()
                .expect("HTTP client"),
        }
    }

    /// Attach an OpenAPI path pattern (e.g. `/customers/{id}`) for per-op tools.
    /// At execute-time, `{name}` tokens are substituted from the tool args and
    /// appended to `endpoint` to form the final request URL.
    pub fn with_path_pattern(mut self, pattern: impl Into<String>) -> Self {
        self.path_pattern = Some(pattern.into());
        self
    }

    pub fn with_output_schema(mut self, schema: Value) -> Self {
        self.output_schema = Some(schema);
        self
    }

    pub fn with_annotations(mut self, annotations: ToolAnnotations) -> Self {
        self.annotations = Some(annotations);
        self
    }

    pub fn with_action(mut self, action: Action) -> Self {
        // The HTTP method sets the minimum required action.
        if !self.action.is_write() || action.is_write() {
            self.action = action;
        }
        self
    }

    /// Mark tool as public (skip tenant isolation, for catalog API tools)
    pub fn into_public(mut self) -> Self {
        self.public = true;
        self
    }

    /// Attach the gateway's backend credential store. The upstream call is
    /// then authenticated with the credential registered under
    /// [`DynamicTool::credential_key`] for the tool's own tenant, when there
    /// is one, it serves the caller's tenant and it is bound to the origin of
    /// the tool endpoint.
    pub fn with_credential_store(mut self, store: impl Into<Option<Arc<CredentialStore>>>) -> Self {
        self.credential_store = store.into();
        self
    }

    /// Attach an outbound address policy applied to both the tool's final URL
    /// and any OAuth2 token endpoint, pinning outbound connections to validated
    /// resolved IPv4/IPv6 addresses with redirects disabled and scrubbed errors.
    pub fn with_outbound_policy(
        mut self,
        policy: impl Into<Option<Arc<crate::proxy::outbound_policy::OutboundAddressPolicy>>>,
    ) -> Self {
        self.outbound_policy = policy.into();
        self
    }

    /// Credential-store key holding the upstream credential of a dynamic tool:
    /// `mcp-tool:{tenant}:{tool_name}`, following the `api-proxy:{backend}`
    /// convention. `tenant` is the tenant the tool is registered for (CRD
    /// namespace, contract tenant, catalog tenant), never the caller's
    /// tenant, and `tool_name` is the name returned by `tools/list`. The
    /// prefix keeps tool credentials apart from proxy route credentials held
    /// in the same store.
    ///
    /// Operators register it through `POST /admin/backend-credentials`, with
    /// the key as `route_id` and the upstream origin as `allowed_origin`, e.g.
    /// `{"route_id": "mcp-tool:acme:payments", "auth_type": "api_key",
    /// "header_name": "X-API-Key", "header_value": "...",
    /// "allowed_origin": "https://api.example.com:443"}`.
    ///
    /// The credential is used for callers of the owning tenant only (`acme`
    /// above). A tool that other tenants can call (per-operation catalog
    /// tools) calls its upstream without a credential for them, unless the
    /// entry sets `"shared_with_tenants": true`, which makes it serve the
    /// callers of every tenant allowed to call the tool.
    ///
    /// The credential is used only when the tool's request targets its
    /// `allowed_origin`; otherwise the call fails before anything is sent. A
    /// tool that is registered for no tenant in particular (coarse catalog
    /// tools) never uses a credential.
    pub fn credential_key(tenant_id: &str, tool_name: &str) -> String {
        format!("{MCP_TOOL_KEY_PREFIX}{tenant_id}:{tool_name}")
    }

    /// Tenant under which this tool's credential is registered: the tenant
    /// the tool itself is registered for.
    ///
    /// `None` when the tool has no tenant of its own (empty tenant or the
    /// [`PUBLIC_TENANT_MARKER`] of shared catalog tools): such a tool always
    /// calls its upstream without a credential. Likewise for a tenant id
    /// containing `:`, the key separator, which no key can address
    /// unambiguously.
    fn credential_tenant(&self) -> Option<&str> {
        let tenant = self.tenant_id.as_str();
        let has_own_tenant =
            !tenant.trim().is_empty() && tenant != PUBLIC_TENANT_MARKER && !tenant.contains(':');
        has_own_tenant.then_some(tenant)
    }

    /// Tenant of the caller, taken from the call context, which the
    /// transports fill from the validated token.
    ///
    /// `None` when the context names no tenant: an empty value, a value that
    /// `auth::tenant::require_tenant` does not accept as a tenant identity
    /// (which includes placeholders such as `default`), or
    /// [`UNKNOWN_CALLER`].
    fn caller_tenant(ctx: &ToolContext) -> Option<&str> {
        let tenant = ctx.tenant_id.as_str();
        let is_known =
            tenant != UNKNOWN_CALLER && crate::telemetry::validated_tenant(Some(tenant)).is_some();
        is_known.then_some(tenant)
    }

    /// Resolve the upstream auth header from the backend credential store,
    /// for a request to `final_url` made on behalf of the caller of `ctx`.
    ///
    /// `Ok(None)`, in which case the upstream request carries no auth header
    /// and no OAuth2 token is requested, when:
    /// - no store is attached, the tool has no tenant of its own, or no
    ///   credential is registered for it;
    /// - the caller's tenant is not known;
    /// - the caller belongs to another tenant than the tool's and the
    ///   credential is not `shared_with_tenants`.
    ///
    /// A credential that serves the caller but whose `allowed_origin` is not
    /// the origin of `final_url` fails the call; this is checked before the
    /// OAuth2 token is requested.
    async fn backend_auth_header(
        &self,
        final_url: &str,
        ctx: &ToolContext,
    ) -> Result<Option<(String, String)>, ToolError> {
        let (Some(store), Some(tenant)) = (&self.credential_store, self.credential_tenant()) else {
            return Ok(None);
        };
        let key = Self::credential_key(tenant, &self.name);
        let Some(cred) = store.get(&key) else {
            return Ok(None);
        };
        // The credential belongs to the tool's tenant. It serves a caller of
        // that tenant, or of any known tenant when it is shared. For anyone
        // else the call proceeds as it does for a tool without a credential.
        let Some(caller) = Self::caller_tenant(ctx) else {
            debug!(
                tool = %self.name,
                tool_tenant = %tenant,
                "Backend credential not used: caller tenant is not known"
            );
            return Ok(None);
        };
        if caller != tenant && !cred.shared_with_tenants {
            debug!(
                tool = %self.name,
                tool_tenant = %tenant,
                caller_tenant = %caller,
                "Backend credential not used: not shared with the caller's tenant"
            );
            return Ok(None);
        }
        if !cred.is_bound_to_origin_of(final_url) {
            warn!(
                tool = %self.name,
                credential_key = %key,
                allowed_origin = ?cred.allowed_origin,
                request_origin = ?url_origin(final_url),
                "Backend credential is not bound to the origin of the tool endpoint"
            );
            return Err(ToolError::ExecutionFailed(
                "Backend credential does not apply to this tool endpoint".to_string(),
            ));
        }
        if cred.auth_type != AuthType::OAuth2ClientCredentials {
            return Ok(Some((cred.header_name, cred.header_value)));
        }
        let oauth_result = match self.outbound_policy.as_deref() {
            Some(policy) => store.get_oauth2_token_guarded(&key, policy).await,
            None => store.get_oauth2_token(&key, &self.client).await,
        };
        match oauth_result {
            Ok(token) => Ok(Some((
                "Authorization".to_string(),
                format!("Bearer {token}"),
            ))),
            Err(e) => {
                warn!(
                    tool = %self.name,
                    credential_key = %key,
                    error = %e,
                    "Backend OAuth2 token fetch failed"
                );
                Err(ToolError::ExecutionFailed(
                    "Failed to authenticate with upstream".to_string(),
                ))
            }
        }
    }
}

#[async_trait]
impl Tool for DynamicTool {
    fn name(&self) -> &str {
        &self.name
    }

    fn description(&self) -> &str {
        &self.description
    }

    fn input_schema(&self) -> ToolSchema {
        self.input_schema.clone()
    }

    fn output_schema(&self) -> Option<Value> {
        self.output_schema.clone()
    }

    fn required_action(&self) -> Action {
        self.action
    }

    fn tenant_id(&self) -> Option<&str> {
        // Public tools (catalog API bridge, per-op expanded tools) are visible
        // to every tenant in `tools/list`. Non-public tools stay tenant-scoped.
        // Execute-time isolation still reads `self.tenant_id` directly via `execute()`.
        if self.public {
            None
        } else {
            Some(&self.tenant_id)
        }
    }

    async fn execute(&self, args: Value, ctx: &ToolContext) -> Result<ToolResult, ToolError> {
        // Tenant isolation: CRD namespace must match caller tenant
        // Public tools (catalog API bridge) skip this check
        if !self.public && ctx.tenant_id != self.tenant_id {
            return Err(ToolError::PermissionDenied(format!(
                "Tool {} not available for tenant {}",
                self.name, ctx.tenant_id
            )));
        }

        // CAB-2113 Phase 0: when a path pattern is attached, substitute `{name}`
        // tokens from args into the path and append to endpoint. The matched
        // args are removed so they don't leak into the query/body.
        let (final_url, remaining_args) = match &self.path_pattern {
            Some(pattern) => {
                let (path, stripped) = substitute_path_pattern(pattern, args, &self.name)?;
                (format!("{}{}", self.endpoint, path), stripped)
            }
            None => (self.endpoint.clone(), args),
        };

        debug!(
            tool = %self.name,
            endpoint = %final_url,
            method = %self.method,
            "Executing dynamic tool"
        );

        // When an outbound address policy is attached, resolve and validate the target URL
        // BEFORE fetching any OAuth2 token or building the outbound HTTP request.
        let pinned_client = match self.outbound_policy.as_deref() {
            Some(policy) => Some(
                policy
                    .validate_and_build_client(&final_url, std::time::Duration::from_secs(30))
                    .await
                    .map_err(|_| {
                        ToolError::ExecutionFailed("Upstream destination blocked".to_string())
                    })?,
            ),
            None => None,
        };
        let http_client = pinned_client.as_ref().unwrap_or(&self.client);

        // Build HTTP request
        let mut req = match self.method.to_uppercase().as_str() {
            "GET" => http_client.get(&final_url),
            "HEAD" => http_client.head(&final_url),
            "OPTIONS" => http_client.request(reqwest::Method::OPTIONS, &final_url),
            "POST" => http_client.post(&final_url),
            "PUT" => http_client.put(&final_url),
            "DELETE" => http_client.delete(&final_url),
            "PATCH" => http_client.patch(&final_url),
            other => {
                return Err(ToolError::ExecutionFailed(format!(
                    "Unsupported HTTP method: {}",
                    other
                )));
            }
        };

        // Upstream auth comes from the backend credential store only; the
        // caller's own token is for this gateway and is never sent upstream.
        // The context only tells whether the credential serves the caller's
        // tenant. Nothing has been sent at this point: a credential that is
        // not bound to the origin of `final_url` ends the call here.
        if let Some((name, value)) = self.backend_auth_header(&final_url, ctx).await? {
            req = req.header(name, value);
        }

        // Inject skill context header if present (CAB-1365)
        if let Some(ref instructions) = ctx.skill_instructions {
            req = req.header("X-Skill-Context", instructions.as_str());
        }

        let has_body = matches!(
            self.method.to_uppercase().as_str(),
            "POST" | "PUT" | "PATCH"
        );
        if has_body && !remaining_args.is_null() {
            req = req.json(&remaining_args);
        } else if !has_body {
            // GET/DELETE: surface remaining scalar args as query string.
            if let Some(obj) = remaining_args.as_object() {
                let pairs: Vec<(String, String)> = obj
                    .iter()
                    .filter_map(|(k, v)| value_to_query_string(v).map(|s| (k.clone(), s)))
                    .collect();
                if !pairs.is_empty() {
                    req = req.query(&pairs);
                }
            }
        }

        // Execute request
        let response = req.send().await.map_err(|e| {
            warn!(
                tool = %self.name,
                error = %e.without_url(),
                "Dynamic tool HTTP request failed"
            );
            ToolError::ExecutionFailed("Upstream HTTP request failed".to_string())
        })?;

        let status = response.status();
        let body = response.text().await.map_err(|e| {
            warn!(
                tool = %self.name,
                error = %e.without_url(),
                "Failed to read dynamic tool response body"
            );
            ToolError::ExecutionFailed("Failed to read upstream response body".to_string())
        })?;

        if !status.is_success() {
            warn!(
                tool = %self.name,
                status = status.as_u16(),
                "Dynamic tool upstream returned non-success status"
            );
            return Err(ToolError::ExecutionFailed(format!(
                "Upstream returned HTTP {}",
                status.as_u16()
            )));
        }

        Ok(ToolResult::text(body))
    }
}

/// Substitute `{name}` tokens in an OpenAPI path pattern from a JSON args object.
///
/// Returns the substituted path + remaining args (with matched keys removed).
/// Non-object args with a non-empty pattern is an error. A missing required
/// token is an error. Matched values are URL-encoded.
fn substitute_path_pattern(
    pattern: &str,
    args: Value,
    tool_name: &str,
) -> Result<(String, Value), ToolError> {
    let tokens = extract_path_tokens(pattern);
    if tokens.is_empty() {
        return Ok((pattern.to_string(), args));
    }

    let mut obj = match args {
        Value::Object(map) => map,
        Value::Null => serde_json::Map::new(),
        other => {
            return Err(ToolError::ExecutionFailed(format!(
                "Tool {} expects object args for path pattern {}, got {}",
                tool_name, pattern, other
            )));
        }
    };

    let mut substituted = pattern.to_string();
    for token in &tokens {
        let value = obj.remove(token).ok_or_else(|| {
            ToolError::ExecutionFailed(format!(
                "Tool {} missing required path parameter: {}",
                tool_name, token
            ))
        })?;
        let rendered = value_to_query_string(&value).ok_or_else(|| {
            ToolError::ExecutionFailed(format!(
                "Tool {} path parameter {} must be scalar",
                tool_name, token
            ))
        })?;
        substituted =
            substituted.replace(&format!("{{{}}}", token), &urlencoding::encode(&rendered));
    }

    let remaining = if obj.is_empty() {
        Value::Null
    } else {
        Value::Object(obj)
    };
    Ok((substituted, remaining))
}

/// Extract `{name}` tokens from an OpenAPI path pattern, in document order.
fn extract_path_tokens(pattern: &str) -> Vec<String> {
    let mut out = Vec::new();
    let bytes = pattern.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'{' {
            if let Some(end) = pattern[i + 1..].find('}') {
                let name = &pattern[i + 1..i + 1 + end];
                if !name.is_empty() && !name.contains('{') {
                    out.push(name.to_string());
                }
                i += end + 2;
                continue;
            }
        }
        i += 1;
    }
    out
}

/// Render a scalar JSON value as a query-string-ready string.
/// Returns `None` for objects/arrays (not supported in v1).
fn value_to_query_string(value: &Value) -> Option<String> {
    match value {
        Value::String(s) => Some(s.clone()),
        Value::Number(n) => Some(n.to_string()),
        Value::Bool(b) => Some(b.to_string()),
        Value::Null => None,
        Value::Array(_) | Value::Object(_) => None,
    }
}

/// Create a ToolSchema from a serde_json::Value (CRD inputSchema field)
pub fn schema_from_value(value: &Value) -> ToolSchema {
    ToolSchema {
        schema_type: value
            .get("type")
            .and_then(|v| v.as_str())
            .unwrap_or("object")
            .to_string(),
        properties: value
            .get("properties")
            .and_then(|v| v.as_object())
            .map(|m| m.iter().map(|(k, v)| (k.clone(), v.clone())).collect())
            .unwrap_or_default(),
        required: value
            .get("required")
            .and_then(|v| v.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|v| v.as_str().map(String::from))
                    .collect()
            })
            .unwrap_or_default(),
    }
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;
    use crate::proxy::credentials::{BackendCredential, OAuth2Config};
    use serde_json::json;
    use std::collections::HashMap;

    #[test]
    fn test_dynamic_tool_creation() {
        let schema = ToolSchema {
            schema_type: "object".to_string(),
            properties: HashMap::new(),
            required: vec![],
        };

        let tool = DynamicTool::new(
            "tenant_weather",
            "Get weather",
            "https://api.example.com/weather",
            "POST",
            schema,
            "tenant-acme",
        );

        assert_eq!(tool.name(), "tenant_weather");
        assert_eq!(tool.description(), "Get weather");
        assert_eq!(tool.required_action(), Action::Create);
    }

    #[test]
    fn test_dynamic_tool_with_builders() {
        let schema = ToolSchema {
            schema_type: "object".to_string(),
            properties: HashMap::new(),
            required: vec![],
        };

        let tool = DynamicTool::new("test", "test", "http://localhost", "GET", schema, "default")
            .with_action(Action::Delete)
            .with_output_schema(json!({"type": "string"}))
            .with_annotations(ToolAnnotations::from_action(Action::Delete));

        assert_eq!(tool.required_action(), Action::Delete);
        assert!(tool.output_schema().is_some());
    }

    #[test]
    fn test_schema_from_value() {
        let value = json!({
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "units": {"type": "string", "enum": ["metric", "imperial"]}
            },
            "required": ["location"]
        });

        let schema = schema_from_value(&value);
        assert_eq!(schema.schema_type, "object");
        assert_eq!(schema.properties.len(), 2);
        assert_eq!(schema.required, vec!["location"]);
    }

    #[test]
    fn test_schema_from_empty_value() {
        let schema = schema_from_value(&json!({}));
        assert_eq!(schema.schema_type, "object");
        assert!(schema.properties.is_empty());
        assert!(schema.required.is_empty());
    }

    #[tokio::test]
    async fn test_tenant_isolation() {
        let schema = ToolSchema {
            schema_type: "object".to_string(),
            properties: HashMap::new(),
            required: vec![],
        };

        let tool = DynamicTool::new(
            "acme_tool",
            "Acme tool",
            "http://localhost:9999/noop",
            "GET",
            schema,
            "tenant-acme",
        );

        let ctx = ToolContext {
            tenant_id: "tenant-other".to_string(),
            user_id: None,
            user_email: None,
            request_id: "req-1".to_string(),
            roles: vec![],
            scopes: vec![],
            raw_token: None,
            skill_instructions: None,
            progress_token: None,
            consumer_id: "test-consumer".to_string(),
            from_control_plane: false,
        };

        let result = tool.execute(json!({}), &ctx).await;
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("not available"));
    }

    #[tokio::test]
    async fn test_skill_context_header_injected() {
        use wiremock::matchers::{header, method};
        use wiremock::{Mock, MockServer, ResponseTemplate};

        let mock = MockServer::start().await;
        let url = format!("{}/api/action", mock.uri());

        Mock::given(method("POST"))
            .and(header("X-Skill-Context", "Always use metric units"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({"result": "ok"})))
            .mount(&mock)
            .await;

        let schema = ToolSchema {
            schema_type: "object".to_string(),
            properties: HashMap::new(),
            required: vec![],
        };

        let tool = DynamicTool::new("t1_action", "Action", &url, "POST", schema, "t1");

        let ctx = ToolContext {
            tenant_id: "t1".to_string(),
            user_id: None,
            user_email: None,
            request_id: "req-1".to_string(),
            roles: vec![],
            scopes: vec![],
            raw_token: None,
            skill_instructions: Some("Always use metric units".to_string()),
            progress_token: None,
            consumer_id: "test-consumer".to_string(),
            from_control_plane: false,
        };

        let result = tool.execute(json!({"query": "temp"}), &ctx).await.unwrap();
        assert!(result.content.iter().any(|c| {
            if let super::super::ToolContent::Text { text } = c {
                text.contains("ok")
            } else {
                false
            }
        }));
    }

    #[tokio::test]
    async fn test_no_skill_context_header_when_none() {
        use wiremock::matchers::method;
        use wiremock::{Mock, MockServer, ResponseTemplate};

        let mock = MockServer::start().await;
        let url = format!("{}/api/action", mock.uri());

        Mock::given(method("POST"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({"clean": true})))
            .mount(&mock)
            .await;

        let schema = ToolSchema {
            schema_type: "object".to_string(),
            properties: HashMap::new(),
            required: vec![],
        };

        let tool = DynamicTool::new("t1_clean", "Clean", &url, "POST", schema, "t1");

        let ctx = ToolContext {
            tenant_id: "t1".to_string(),
            user_id: None,
            user_email: None,
            request_id: "req-1".to_string(),
            roles: vec![],
            scopes: vec![],
            raw_token: None,
            skill_instructions: None,
            progress_token: None,
            consumer_id: "test-consumer".to_string(),
            from_control_plane: false,
        };

        let result = tool.execute(json!({}), &ctx).await.unwrap();
        assert!(result.content.iter().any(|c| {
            if let super::super::ToolContent::Text { text } = c {
                text.contains("clean")
            } else {
                false
            }
        }));
    }

    // === CAB-2113 Phase 0: path-pattern helpers + DynamicTool substitution ===

    #[test]
    fn cab_2113_extract_path_tokens_basic() {
        assert_eq!(
            extract_path_tokens("/customers/{id}"),
            vec!["id".to_string()]
        );
        assert_eq!(
            extract_path_tokens("/a/{x}/b/{y}"),
            vec!["x".to_string(), "y".to_string()]
        );
        assert!(extract_path_tokens("/no/tokens").is_empty());
        assert!(extract_path_tokens("/broken/{unclosed").is_empty());
    }

    #[test]
    fn cab_2113_substitute_path_pattern_strips_matched_keys() {
        let (path, rest) = substitute_path_pattern(
            "/customers/{id}",
            json!({"id": "42", "email": "foo@bar.com"}),
            "demo:bank:get-customer",
        )
        .unwrap();
        assert_eq!(path, "/customers/42");
        assert_eq!(rest, json!({"email": "foo@bar.com"}));
    }

    #[test]
    fn cab_2113_substitute_path_pattern_missing_token_errors() {
        let err = substitute_path_pattern(
            "/customers/{id}",
            json!({"other": "x"}),
            "demo:bank:get-customer",
        )
        .unwrap_err();
        assert!(err.to_string().contains("missing required path parameter"));
    }

    #[test]
    fn cab_2113_substitute_path_pattern_url_encodes_values() {
        let (path, _) =
            substitute_path_pattern("/items/{id}", json!({"id": "a/b c"}), "demo:store:get-item")
                .unwrap();
        assert_eq!(path, "/items/a%2Fb%20c");
    }

    #[tokio::test]
    async fn cab_2113_dynamic_tool_substitutes_path_and_forwards_query() {
        use wiremock::matchers::{method, path as m_path, query_param};
        use wiremock::{Mock, MockServer, ResponseTemplate};

        let mock = MockServer::start().await;
        Mock::given(method("GET"))
            .and(m_path("/customers/42"))
            .and(query_param("expand", "accounts"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({"ok": true})))
            .mount(&mock)
            .await;

        let schema = ToolSchema {
            schema_type: "object".to_string(),
            properties: HashMap::new(),
            required: vec![],
        };
        let tool = DynamicTool::new(
            "demo:bank:get-customer",
            "Get customer",
            mock.uri(),
            "GET",
            schema,
            "demo",
        )
        .into_public()
        .with_path_pattern("/customers/{id}");

        let ctx = ToolContext {
            tenant_id: "demo".to_string(),
            user_id: None,
            user_email: None,
            request_id: "req-1".to_string(),
            roles: vec![],
            scopes: vec![],
            raw_token: None,
            skill_instructions: None,
            progress_token: None,
            consumer_id: "c".to_string(),
            from_control_plane: false,
        };

        let res = tool
            .execute(json!({"id": "42", "expand": "accounts"}), &ctx)
            .await
            .unwrap();
        assert!(res.content.iter().any(|c| {
            if let super::super::ToolContent::Text { text } = c {
                text.contains("\"ok\":true")
            } else {
                false
            }
        }));
    }

    #[tokio::test]
    async fn cab_2113_dynamic_tool_post_sends_remainder_as_body() {
        use wiremock::matchers::{body_partial_json, method, path as m_path};
        use wiremock::{Mock, MockServer, ResponseTemplate};

        let mock = MockServer::start().await;
        Mock::given(method("POST"))
            .and(m_path("/customers/42/transfers"))
            .and(body_partial_json(json!({"amount": 100})))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({"created": true})))
            .mount(&mock)
            .await;

        let schema = ToolSchema {
            schema_type: "object".to_string(),
            properties: HashMap::new(),
            required: vec![],
        };
        let tool = DynamicTool::new(
            "demo:bank:create-transfer",
            "Create transfer",
            mock.uri(),
            "POST",
            schema,
            "demo",
        )
        .into_public()
        .with_path_pattern("/customers/{id}/transfers");

        let ctx = ToolContext {
            tenant_id: "demo".to_string(),
            user_id: None,
            user_email: None,
            request_id: "req-1".to_string(),
            roles: vec![],
            scopes: vec![],
            raw_token: None,
            skill_instructions: None,
            progress_token: None,
            consumer_id: "c".to_string(),
            from_control_plane: false,
        };

        tool.execute(json!({"id": "42", "amount": 100}), &ctx)
            .await
            .unwrap();
    }

    // === CAB-2123: public DynamicTool must be tenant_id=None in discovery ===
    //
    // regression for CAB-2123
    // Before the fix, `Tool::tenant_id` returned `Some(&self.tenant_id)` even when
    // the tool was registered via `.into_public()` — so `ToolRegistry::list(Some(caller))`
    // filtered public per-op tools out for every caller whose tenant didn't match the CRD
    // namespace. This broke standard /mcp/v1/tools discovery for the CAB-2113 banking
    // catalog, forcing clients through the bricolé `stoa_tools action=list` path.

    fn schema_empty_object() -> ToolSchema {
        ToolSchema {
            schema_type: "object".to_string(),
            properties: HashMap::new(),
            required: vec![],
        }
    }

    #[test]
    fn regression_cab_2123_public_dynamic_tool_has_no_tenant_in_definition() {
        let tool = DynamicTool::new(
            "demo_public",
            "public tool",
            "http://localhost",
            "GET",
            schema_empty_object(),
            "demo",
        )
        .into_public();

        assert_eq!(tool.tenant_id(), None);
        assert!(tool.definition().tenant_id.is_none());
    }

    #[test]
    fn regression_cab_2123_private_dynamic_tool_keeps_tenant_in_definition() {
        let tool = DynamicTool::new(
            "demo_private",
            "private tool",
            "http://localhost",
            "GET",
            schema_empty_object(),
            "demo",
        );

        assert_eq!(tool.tenant_id(), Some("demo"));
        assert_eq!(tool.definition().tenant_id.as_deref(), Some("demo"));
    }

    #[test]
    fn regression_cab_2123_registry_list_includes_public_dynamic_tool_for_any_tenant() {
        use super::super::ToolRegistry;
        use std::sync::Arc;

        let registry = ToolRegistry::new();
        let tool = DynamicTool::new(
            "demo:bank:get-customer",
            "Get customer",
            "http://mock",
            "GET",
            schema_empty_object(),
            "demo",
        )
        .into_public();

        registry.register(Arc::new(tool));

        // Public tool must surface for any caller tenant, not just "demo".
        for caller in ["demo", "stoa-demo", "other-tenant", "acme"] {
            let tools = registry.list(Some(caller));
            assert!(
                tools.iter().any(|t| t.name == "demo:bank:get-customer"),
                "public tool invisible to tenant `{}`",
                caller
            );
        }
    }

    #[test]
    fn regression_cab_2123_registry_list_keeps_private_dynamic_tool_tenant_scoped() {
        use super::super::ToolRegistry;
        use std::sync::Arc;

        let registry = ToolRegistry::new();
        let tool = DynamicTool::new(
            "acme_internal",
            "Internal tool",
            "http://mock",
            "GET",
            schema_empty_object(),
            "acme",
        );
        registry.register(Arc::new(tool));

        // Owner sees it; other tenants don't.
        assert!(
            registry
                .list(Some("acme"))
                .iter()
                .any(|t| t.name == "acme_internal"),
            "owner must see its private tool"
        );
        assert!(
            registry
                .list(Some("other"))
                .iter()
                .all(|t| t.name != "acme_internal"),
            "non-owner must not see private tool"
        );
    }

    #[test]
    fn regression_cab_2123_public_per_op_tool_surfaces_via_standard_list() {
        // Reproduces the api_bridge::discover_expanded_api_tools registration pattern
        // (CAB-2113 Phase 0): per-op public tool with a path pattern must surface
        // via `list(Some(caller))` for a caller whose tenant doesn't match the CRD
        // namespace. This is the CAB-2120 demo path that was still broken after the
        // STOA_TOOL_EXPANSION_MODE=per-op prod flip.
        use super::super::ToolRegistry;
        use std::sync::Arc;

        let registry = ToolRegistry::new();
        let tool = DynamicTool::new(
            "demo:bank:get-customer-by-number",
            "Get customer by number",
            "http://banking-mock",
            "GET",
            schema_empty_object(),
            "demo",
        )
        .with_action(Action::Read)
        .with_annotations(ToolAnnotations {
            title: Some("Banking: get customer".to_string()),
            open_world_hint: Some(true),
            ..Default::default()
        })
        .into_public()
        .with_path_pattern("/customers/{customerNumber}");

        registry.register(Arc::new(tool));

        // stoa-demo JWT caller (the real demo scenario) must see the per-op tool.
        let tools = registry.list(Some("stoa-demo"));
        assert!(
            tools
                .iter()
                .any(|t| t.name == "demo:bank:get-customer-by-number"),
            "per-op public tool must surface via standard discovery (CAB-2123)"
        );
    }

    // === Upstream authentication comes from the backend credential store ===

    const CALLER_BEARER: &str = "fixture-caller-bearer";

    /// Credential key of [`orders_tool`]: tenant `t1`, tool `t1_orders`.
    const ORDERS_KEY: &str = "mcp-tool:t1:t1_orders";

    /// Context of a caller from `tenant`, carrying a caller bearer.
    fn ctx_for_tenant(tenant: &str) -> ToolContext {
        ToolContext {
            tenant_id: tenant.to_string(),
            user_id: None,
            user_email: None,
            request_id: "req-1".to_string(),
            roles: vec![],
            scopes: vec![],
            raw_token: Some(CALLER_BEARER.to_string()),
            skill_instructions: None,
            progress_token: None,
            consumer_id: "test-consumer".to_string(),
            from_control_plane: false,
        }
    }

    fn ctx_with_caller_bearer() -> ToolContext {
        ctx_for_tenant("t1")
    }

    fn assert_caller_bearer_absent(request: &wiremock::Request) {
        for (name, value) in request.headers.iter() {
            assert!(
                !String::from_utf8_lossy(value.as_bytes()).contains(CALLER_BEARER),
                "caller bearer found in upstream header {name}"
            );
        }
    }

    /// Static credential stored under `key` and bound to `allowed_origin`.
    fn static_credential(
        key: &str,
        auth_type: AuthType,
        header_name: &str,
        header_value: &str,
        allowed_origin: Option<&str>,
    ) -> BackendCredential {
        BackendCredential {
            route_id: key.to_string(),
            auth_type,
            header_name: header_name.to_string(),
            header_value: header_value.to_string(),
            oauth2: None,
            allowed_origin: allowed_origin.map(str::to_string),
            shared_with_tenants: false,
        }
    }

    /// `credential`, also serving callers of other tenants.
    fn shared(credential: BackendCredential) -> BackendCredential {
        BackendCredential {
            shared_with_tenants: true,
            ..credential
        }
    }

    /// OAuth2 client-credentials entry of [`orders_tool`], with its token
    /// endpoint on `upstream` and bound to `allowed_origin`.
    fn oauth2_credential(
        upstream: &wiremock::MockServer,
        allowed_origin: Option<&str>,
    ) -> BackendCredential {
        BackendCredential {
            oauth2: Some(OAuth2Config {
                token_url: format!("{}/token", upstream.uri()),
                client_id: "fixture-client".to_string(),
                client_secret: "fixture-client-credential".to_string(),
            }),
            ..static_credential(
                ORDERS_KEY,
                AuthType::OAuth2ClientCredentials,
                "Authorization",
                "unused",
                allowed_origin,
            )
        }
    }

    fn store_of(credential: BackendCredential) -> Arc<CredentialStore> {
        let store = Arc::new(CredentialStore::new());
        store.upsert(credential);
        store
    }

    /// API key that [`api_key_store`] holds under the credential key `key`.
    pub(crate) fn api_key_for(key: &str) -> String {
        format!("fixture-backend-key-of-{key}")
    }

    /// API-key entry ([`api_key_for`]) stored under `key` and bound to
    /// `allowed_origin`.
    fn api_key_credential(key: &str, allowed_origin: &str) -> BackendCredential {
        let (name, value) = ("X-Api-Key", api_key_for(key));
        static_credential(key, AuthType::ApiKey, name, &value, Some(allowed_origin))
    }

    /// Store holding an API key ([`api_key_for`]) under each of `keys`, all
    /// bound to `allowed_origin`.
    pub(crate) fn api_key_store(keys: &[&str], allowed_origin: &str) -> Arc<CredentialStore> {
        let store = Arc::new(CredentialStore::new());
        for key in keys {
            store.upsert(api_key_credential(key, allowed_origin));
        }
        store
    }

    /// Upstream answering 200 on `/orders` (any method) and 404 elsewhere.
    pub(crate) async fn orders_upstream() -> wiremock::MockServer {
        let upstream = wiremock::MockServer::start().await;
        wiremock::Mock::given(wiremock::matchers::path("/orders"))
            .respond_with(wiremock::ResponseTemplate::new(200))
            .mount(&upstream)
            .await;
        upstream
    }

    /// Tool `name` registered for `tenant`, calling `GET {upstream}/orders`.
    fn tool_for_tenant(name: &str, tenant: &str, upstream: &wiremock::MockServer) -> DynamicTool {
        DynamicTool::new(
            name,
            "Orders",
            format!("{}/orders", upstream.uri()),
            "GET",
            schema_empty_object(),
            tenant,
        )
    }

    fn orders_tool(upstream: &wiremock::MockServer) -> DynamicTool {
        tool_for_tenant("t1_orders", "t1", upstream)
    }

    /// Call `tool` as a caller of tenant `caller`, with a caller bearer in
    /// the context, then return the `X-Api-Key` values `upstream` has
    /// received on `/orders`.
    pub(crate) async fn api_keys_received(
        tool: &dyn Tool,
        caller: &str,
        upstream: &wiremock::MockServer,
    ) -> Vec<String> {
        let ctx = ctx_for_tenant(caller);
        tool.execute(json!({}), &ctx).await.unwrap();
        let requests = upstream.received_requests().await.unwrap();
        let orders = requests.iter().filter(|r| r.url.path() == "/orders");
        orders
            .inspect(|request| assert_caller_bearer_absent(request))
            .flat_map(|request| request.headers.get_all("X-Api-Key"))
            .map(|value| value.to_str().unwrap().to_string())
            .collect()
    }

    #[test]
    fn credential_key_names_the_tenant_and_the_tool() {
        assert_eq!(
            DynamicTool::credential_key("acme", "payments"),
            "mcp-tool:acme:payments"
        );
        assert_eq!(DynamicTool::credential_key("t1", "t1_orders"), ORDERS_KEY);
    }

    #[tokio::test]
    async fn upstream_request_has_no_authorization_without_backend_credential() {
        for with_other_entries in [false, true] {
            let upstream = orders_upstream().await;
            // Entries of another tool, of another tenant, and without a tenant.
            let other_entries = [
                "mcp-tool:t1:t1_invoices",
                "mcp-tool:t2:t1_orders",
                "mcp-tool:t1_orders",
            ];
            let store = with_other_entries.then(|| api_key_store(&other_entries, &upstream.uri()));
            let tool = orders_tool(&upstream).with_credential_store(store);

            tool.execute(json!({}), &ctx_with_caller_bearer())
                .await
                .unwrap();

            let requests = upstream.received_requests().await.unwrap();
            assert_eq!(requests.len(), 1);
            assert!(!requests[0].headers.contains_key("Authorization"));
            assert!(!requests[0].headers.contains_key("X-Api-Key"));
            assert_caller_bearer_absent(&requests[0]);
        }
    }

    #[tokio::test]
    async fn upstream_request_carries_configured_backend_credential() {
        for (auth_type, header_name, header_value) in [
            (AuthType::ApiKey, "X-Api-Key", "fixture-backend-key"),
            (
                AuthType::Bearer,
                "Authorization",
                "Bearer fixture-backend-key",
            ),
        ] {
            let upstream = orders_upstream().await;
            // Origins are compared in normalized form: another spelling of
            // the endpoint origin is the same origin.
            let allowed_origin = format!("{}/", upstream.uri().to_uppercase());
            let tool = orders_tool(&upstream).with_credential_store(store_of(static_credential(
                ORDERS_KEY,
                auth_type,
                header_name,
                header_value,
                Some(&allowed_origin),
            )));

            tool.execute(json!({}), &ctx_with_caller_bearer())
                .await
                .unwrap();

            let requests = upstream.received_requests().await.unwrap();
            assert_eq!(requests.len(), 1);
            let sent: Vec<_> = requests[0].headers.get_all(header_name).iter().collect();
            assert_eq!(sent, [header_value]);
            assert_eq!(
                requests[0].headers.contains_key("Authorization"),
                header_name == "Authorization"
            );
            assert_caller_bearer_absent(&requests[0]);
        }
    }

    #[tokio::test]
    async fn upstream_request_carries_oauth2_client_credentials_token() {
        use wiremock::matchers::{body_string_contains, method, path};
        use wiremock::{Mock, ResponseTemplate};

        let upstream = orders_upstream().await;
        Mock::given(method("POST"))
            .and(path("/token"))
            .and(body_string_contains("grant_type=client_credentials"))
            .respond_with(ResponseTemplate::new(200).set_body_json(
                json!({"access_token": "fixture-backend-access", "expires_in": 300}),
            ))
            .mount(&upstream)
            .await;
        let credential = oauth2_credential(&upstream, Some(&upstream.uri()));
        let tool = orders_tool(&upstream).with_credential_store(store_of(credential));

        tool.execute(json!({}), &ctx_with_caller_bearer())
            .await
            .unwrap();

        let requests = upstream.received_requests().await.unwrap();
        let orders: Vec<_> = requests
            .iter()
            .filter(|r| r.url.path() == "/orders")
            .collect();
        assert_eq!(orders.len(), 1);
        assert_eq!(
            orders[0].headers.get("Authorization").unwrap(),
            "Bearer fixture-backend-access"
        );
        for request in &requests {
            assert_caller_bearer_absent(request);
        }
    }

    #[tokio::test]
    async fn tool_call_fails_without_reaching_upstream_when_oauth2_token_is_unavailable() {
        // No token endpoint is mounted, so the token request gets a 404.
        let upstream = orders_upstream().await;
        let credential = oauth2_credential(&upstream, Some(&upstream.uri()));
        let tool = orders_tool(&upstream).with_credential_store(store_of(credential));

        let result = tool.execute(json!({}), &ctx_with_caller_bearer()).await;

        assert!(result.is_err());
        let requests = upstream.received_requests().await.unwrap();
        assert!(requests.iter().all(|r| r.url.path() != "/orders"));
    }

    #[tokio::test]
    async fn upstream_redirect_is_not_followed() {
        let redirect_target = orders_upstream().await;
        let upstream = wiremock::MockServer::start().await;
        wiremock::Mock::given(wiremock::matchers::path("/orders"))
            .respond_with(
                wiremock::ResponseTemplate::new(302)
                    .insert_header("Location", format!("{}/orders", redirect_target.uri())),
            )
            .mount(&upstream)
            .await;
        let tool = orders_tool(&upstream)
            .with_credential_store(api_key_store(&[ORDERS_KEY], &upstream.uri()));

        let result = tool.execute(json!({}), &ctx_with_caller_bearer()).await;

        assert!(result.is_err());
        assert_eq!(upstream.received_requests().await.unwrap().len(), 1);
        assert!(redirect_target
            .received_requests()
            .await
            .unwrap()
            .is_empty());
    }

    // === A credential is bound to the tool's tenant and to one origin ===

    #[tokio::test]
    async fn same_named_tools_of_different_tenants_use_their_own_credential() {
        // Three tenants register a tool under the same name, each with its
        // own backend. Two of them have a credential, bound to their backend.
        let store = Arc::new(CredentialStore::new());
        let mut tools = Vec::new();
        for tenant in ["tenant-a", "tenant-b", "tenant-c"] {
            let upstream = orders_upstream().await;
            let key = DynamicTool::credential_key(tenant, "orders");
            if tenant != "tenant-c" {
                store.upsert(static_credential(
                    &key,
                    AuthType::ApiKey,
                    "X-Api-Key",
                    &api_key_for(&key),
                    Some(&upstream.uri()),
                ));
            }
            let tool =
                tool_for_tenant("orders", tenant, &upstream).with_credential_store(store.clone());
            tools.push((tenant, key, tool, upstream));
        }

        for (tenant, key, tool, upstream) in &tools {
            let received = api_keys_received(tool, tenant, upstream).await;
            if *tenant == "tenant-c" {
                assert!(received.is_empty(), "{tenant} has no credential");
            } else {
                assert_eq!(received, [api_key_for(key)], "{tenant}");
            }
        }
    }

    #[tokio::test]
    async fn credential_bound_to_another_origin_fails_the_call_before_any_request() {
        let elsewhere = orders_upstream().await;
        for oauth2 in [false, true] {
            // Bound to another server, to another host, or to no origin.
            for allowed_origin in [
                Some(elsewhere.uri()),
                Some("https://api.example.com:443".to_string()),
                None,
            ] {
                // `upstream` serves both the tool endpoint and the token endpoint.
                let upstream = orders_upstream().await;
                let allowed_origin = allowed_origin.as_deref();
                let credential = if oauth2 {
                    oauth2_credential(&upstream, allowed_origin)
                } else {
                    let (name, value) = ("X-Api-Key", "fixture-backend-key");
                    static_credential(ORDERS_KEY, AuthType::ApiKey, name, value, allowed_origin)
                };
                let tool = orders_tool(&upstream).with_credential_store(store_of(credential));

                let error = tool
                    .execute(json!({}), &ctx_with_caller_bearer())
                    .await
                    .unwrap_err();

                let case = format!("oauth2={oauth2} allowed_origin={allowed_origin:?}");
                assert!(error.to_string().contains("does not apply"), "{case}");
                let requests = upstream.received_requests().await.unwrap();
                assert!(requests.is_empty(), "{case}");
            }
        }
        assert!(elsewhere.received_requests().await.unwrap().is_empty());
    }

    #[tokio::test]
    async fn credential_origin_is_checked_on_the_url_resolved_from_the_path_pattern() {
        // The path pattern is appended to the endpoint. Here the resolved URL
        // points at `elsewhere`, while the credential is bound to the origin
        // of the endpoint.
        let (upstream, elsewhere) = (orders_upstream().await, orders_upstream().await);
        let tool = DynamicTool::new(
            "t1_orders",
            "Orders",
            upstream.uri(),
            "GET",
            schema_empty_object(),
            "t1",
        )
        .with_path_pattern(format!("@{}/orders", elsewhere.address()))
        .with_credential_store(api_key_store(&[ORDERS_KEY], &upstream.uri()));

        let result = tool.execute(json!({}), &ctx_with_caller_bearer()).await;

        assert!(result.unwrap_err().to_string().contains("does not apply"));
        for server in [&upstream, &elsewhere] {
            assert!(server.received_requests().await.unwrap().is_empty());
        }
    }

    #[tokio::test]
    async fn tool_registered_for_no_tenant_never_receives_a_credential() {
        // Shared catalog tools carry the public marker, or no tenant at all.
        // An entry stored under the key such a tenant would give is not used,
        // nor is one stored without a tenant, even when the entry is shared
        // with the callers of every tenant. Same for a tenant id that holds
        // the key separator.
        for tenant in [PUBLIC_TENANT_MARKER, "", "a:b"] {
            let upstream = orders_upstream().await;
            let key = DynamicTool::credential_key(tenant, "orders");
            let store = Arc::new(CredentialStore::new());
            for key in [key.as_str(), "mcp-tool:orders"] {
                store.upsert(shared(api_key_credential(key, &upstream.uri())));
            }
            let tool = tool_for_tenant("orders", tenant, &upstream)
                .into_public()
                .with_credential_store(store);

            let received = api_keys_received(&tool, "t1", &upstream).await;

            assert!(received.is_empty(), "tenant {tenant:?}");
            let requests = upstream.received_requests().await.unwrap();
            assert_eq!(requests.len(), 1, "tenant {tenant:?}");
            assert!(!requests[0].headers.contains_key("Authorization"));
        }
    }

    // === A credential serves the callers of the tool's own tenant, unless shared ===

    /// What the upstream of a tool has received: requests on the tool
    /// endpoint, the credential headers they carried, and requests on the
    /// token endpoint.
    #[derive(Debug, Default, PartialEq)]
    struct Received {
        tool_requests: usize,
        credential_headers: Vec<(String, String)>,
        token_requests: usize,
    }

    impl Received {
        /// One upstream call, without a credential and without a token request.
        fn one_call_without_credential() -> Self {
            Self {
                tool_requests: 1,
                ..Self::default()
            }
        }

        /// One upstream call carrying the entry of [`orders_credential`].
        fn one_call_with_credential(oauth2: bool) -> Self {
            let header = if oauth2 {
                ("authorization", "Bearer fixture-backend-access".to_string())
            } else {
                ("x-api-key", api_key_for(ORDERS_KEY))
            };
            Self {
                tool_requests: 1,
                credential_headers: vec![(header.0.to_string(), header.1)],
                token_requests: usize::from(oauth2),
            }
        }
    }

    async fn received_by(upstream: &wiremock::MockServer) -> Received {
        let requests = upstream.received_requests().await.unwrap();
        let (token, tool): (Vec<_>, Vec<_>) =
            requests.iter().partition(|r| r.url.path() == "/token");
        let mut credential_headers = Vec::new();
        for request in &tool {
            assert_caller_bearer_absent(request);
            for name in ["authorization", "x-api-key"] {
                for value in request.headers.get_all(name) {
                    let value = value.to_str().unwrap().to_string();
                    credential_headers.push((name.to_string(), value));
                }
            }
        }
        Received {
            tool_requests: tool.len(),
            credential_headers,
            token_requests: token.len(),
        }
    }

    /// Entry of [`orders_tool`], bound to the origin of `upstream`: an API
    /// key, or OAuth2 client credentials with their token endpoint on
    /// `upstream`.
    fn orders_credential(oauth2: bool, upstream: &wiremock::MockServer) -> BackendCredential {
        if oauth2 {
            oauth2_credential(upstream, Some(&upstream.uri()))
        } else {
            api_key_credential(ORDERS_KEY, &upstream.uri())
        }
    }

    /// Call, as a caller of tenant `caller`, a tool that tenant `t1` owns and
    /// that every tenant can call (as per-operation catalog tools are),
    /// holding the entry `credential` builds. Returns the result of the call
    /// and what the upstream, which also serves the token endpoint, received.
    async fn call_public_tool(
        caller: &str,
        credential: impl FnOnce(&wiremock::MockServer) -> BackendCredential,
    ) -> (Result<ToolResult, ToolError>, Received) {
        let upstream = orders_upstream().await;
        wiremock::Mock::given(wiremock::matchers::path("/token"))
            .respond_with(wiremock::ResponseTemplate::new(200).set_body_json(
                json!({"access_token": "fixture-backend-access", "expires_in": 300}),
            ))
            .mount(&upstream)
            .await;
        let tool = orders_tool(&upstream)
            .into_public()
            .with_credential_store(store_of(credential(&upstream)));

        let result = tool.execute(json!({}), &ctx_for_tenant(caller)).await;

        (result, received_by(&upstream).await)
    }

    #[tokio::test]
    async fn caller_of_another_tenant_gets_no_credential_and_no_token_is_requested() {
        for oauth2 in [false, true] {
            let (result, received) =
                call_public_tool("t2", |upstream| orders_credential(oauth2, upstream)).await;

            // The call goes through, as it does for a tool without a credential.
            assert!(result.is_ok(), "oauth2={oauth2}");
            let expected = Received::one_call_without_credential();
            assert_eq!(received, expected, "oauth2={oauth2}");
        }
    }

    #[tokio::test]
    async fn caller_of_the_owning_tenant_gets_the_credential() {
        for oauth2 in [false, true] {
            let (result, received) =
                call_public_tool("t1", |upstream| orders_credential(oauth2, upstream)).await;

            assert!(result.is_ok(), "oauth2={oauth2}");
            let expected = Received::one_call_with_credential(oauth2);
            assert_eq!(received, expected, "oauth2={oauth2}");
        }
    }

    #[tokio::test]
    async fn caller_of_another_tenant_gets_a_credential_shared_with_tenants() {
        for oauth2 in [false, true] {
            let (result, received) =
                call_public_tool("t2", |upstream| shared(orders_credential(oauth2, upstream)))
                    .await;

            assert!(result.is_ok(), "oauth2={oauth2}");
            let expected = Received::one_call_with_credential(oauth2);
            assert_eq!(received, expected, "oauth2={oauth2}");
        }
    }

    #[tokio::test]
    async fn caller_without_a_known_tenant_gets_no_credential() {
        // No tenant, or a value that stands for none. A shared entry is for
        // the callers of other tenants, not for a caller without one.
        for caller in ["", " ", "unknown", "default", PUBLIC_TENANT_MARKER] {
            for (oauth2, share) in [(false, false), (false, true), (true, false), (true, true)] {
                let (result, received) = call_public_tool(caller, |upstream| {
                    let credential = orders_credential(oauth2, upstream);
                    if share {
                        shared(credential)
                    } else {
                        credential
                    }
                })
                .await;

                let case = format!("caller={caller:?} oauth2={oauth2} shared={share}");
                assert!(result.is_ok(), "{case}");
                assert_eq!(received, Received::one_call_without_credential(), "{case}");
            }
        }

        // Likewise when the tool itself is registered under such a value and
        // called with it.
        for tenant in ["unknown", "default"] {
            let upstream = orders_upstream().await;
            let key = DynamicTool::credential_key(tenant, "orders");
            let entry = shared(api_key_credential(&key, &upstream.uri()));
            let tool =
                tool_for_tenant("orders", tenant, &upstream).with_credential_store(store_of(entry));

            let received = api_keys_received(&tool, tenant, &upstream).await;

            assert!(received.is_empty(), "tenant {tenant:?}");
        }
    }

    #[tokio::test]
    async fn caller_tenant_is_considered_before_the_credential_origin() {
        // An entry bound to another origin fails the calls it would serve.
        // For a caller it does not serve, it is as if there was no entry: the
        // call goes through without a credential.
        let bound_elsewhere = || api_key_credential(ORDERS_KEY, "https://api.example.com");

        let (result, received) = call_public_tool("t2", |_| bound_elsewhere()).await;
        assert!(result.is_ok());
        assert_eq!(received, Received::one_call_without_credential());

        for (caller, credential) in [("t1", bound_elsewhere()), ("t2", shared(bound_elsewhere()))] {
            let (result, received) = call_public_tool(caller, |_| credential).await;
            let error = result.unwrap_err().to_string();
            assert!(error.contains("does not apply"), "caller={caller}");
            assert_eq!(received, Received::default(), "caller={caller}");
        }
    }

    #[tokio::test]
    async fn dynamic_tool_with_outbound_policy_enforces_allowlist_no_redirects_and_masked_errors() {
        use crate::proxy::outbound_policy::OutboundAddressPolicy;
        use wiremock::matchers::{method, path};
        use wiremock::{Mock, MockServer, ResponseTemplate};

        let blocked_server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/data"))
            .respond_with(ResponseTemplate::new(200).set_body_string("secret"))
            .expect(0)
            .mount(&blocked_server)
            .await;

        let allowed_server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/ok"))
            .respond_with(ResponseTemplate::new(200).set_body_string("ok-payload"))
            .mount(&allowed_server)
            .await;
        Mock::given(method("GET"))
            .and(path("/redir"))
            .respond_with(
                ResponseTemplate::new(302)
                    .insert_header("Location", format!("{}/redir-target", allowed_server.uri()))
                    .set_body_string("sensitive-redirect-body"),
            )
            .mount(&allowed_server)
            .await;
        Mock::given(method("GET"))
            .and(path("/redir-target"))
            .respond_with(ResponseTemplate::new(200).set_body_string("must-not-reach"))
            .expect(0)
            .mount(&allowed_server)
            .await;
        Mock::given(method("GET"))
            .and(path("/err"))
            .respond_with(ResponseTemplate::new(502).set_body_string("internal-stack-trace-xyz"))
            .mount(&allowed_server)
            .await;

        let policy = Arc::new(OutboundAddressPolicy::new([allowed_server.uri()]));
        let ctx = ToolContext {
            tenant_id: "acme".to_string(),
            user_id: Some("u1".to_string()),
            user_email: None,
            request_id: "req-1".to_string(),
            roles: vec![],
            scopes: vec![],
            raw_token: None,
            skill_instructions: None,
            progress_token: None,
            consumer_id: "c1".to_string(),
            from_control_plane: false,
        };

        // 1. Non-allowlisted loopback target is blocked with zero upstream requests.
        let blocked_tool = DynamicTool::new(
            "blocked_tool",
            "Blocked",
            format!("{}/data", blocked_server.uri()),
            "GET",
            ToolSchema {
                schema_type: "object".to_string(),
                properties: HashMap::new(),
                required: vec![],
            },
            "acme",
        )
        .with_outbound_policy(policy.clone());
        let err = blocked_tool.execute(json!({}), &ctx).await.unwrap_err();
        assert!(err.to_string().contains("blocked"));
        assert_eq!(blocked_server.received_requests().await.unwrap().len(), 0);

        // 2. Allowlisted target succeeds.
        let ok_tool = DynamicTool::new(
            "ok_tool",
            "OK",
            format!("{}/ok", allowed_server.uri()),
            "GET",
            ToolSchema {
                schema_type: "object".to_string(),
                properties: HashMap::new(),
                required: vec![],
            },
            "acme",
        )
        .with_outbound_policy(policy.clone());
        let res = ok_tool.execute(json!({}), &ctx).await.unwrap();
        assert_eq!(res.content.len(), 1);

        // 3. 3xx redirect is not followed and upstream error body is masked.
        let redir_tool = DynamicTool::new(
            "redir_tool",
            "Redirect",
            format!("{}/redir", allowed_server.uri()),
            "GET",
            ToolSchema {
                schema_type: "object".to_string(),
                properties: HashMap::new(),
                required: vec![],
            },
            "acme",
        )
        .with_outbound_policy(policy.clone());
        let err = redir_tool
            .execute(json!({}), &ctx)
            .await
            .unwrap_err()
            .to_string();
        assert!(err.contains("302"), "unexpected error: {err}");
        assert!(!err.contains("sensitive-redirect-body"));

        // 4. Non-2xx upstream error body is masked even without outbound_policy.
        let err_tool = DynamicTool::new(
            "err_tool",
            "Error",
            format!("{}/err", allowed_server.uri()),
            "GET",
            ToolSchema {
                schema_type: "object".to_string(),
                properties: HashMap::new(),
                required: vec![],
            },
            "acme",
        );
        let err = err_tool
            .execute(json!({}), &ctx)
            .await
            .unwrap_err()
            .to_string();
        assert!(err.contains("502"), "unexpected error: {err}");
        assert!(!err.contains("internal-stack-trace-xyz"));
        assert!(!err.contains(&allowed_server.uri()));
    }
}
