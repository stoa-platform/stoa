//! Proxy Mode Implementation
//!
//! Full inline proxy mode with request/response transformation,
//! rate limiting, and API versioning support.
//!
//! # Architecture
//!
//! ```text
//!    Client Request
//!         │
//!         ▼
//!    ┌─────────────┐
//!    │   STOA      │
//!    │   Proxy     │
//!    │             │
//!    │ ┌─────────┐ │
//!    │ │Transform│ │  ← Header injection, body rewrite
//!    │ └────┬────┘ │
//!    │      ▼      │
//!    │ ┌─────────┐ │
//!    │ │  OPA    │ │  ← Policy evaluation
//!    │ └────┬────┘ │
//!    │      ▼      │
//!    │ ┌─────────┐ │
//!    │ │  Rate   │ │  ← Rate limit check
//!    │ │  Limit  │ │
//!    │ └────┬────┘ │
//!    │      ▼      │
//!    │ ┌─────────┐ │
//!    │ │ Backend │ │  ← Route to upstream
//!    │ │ Routing │ │
//!    │ └─────────┘ │
//!    └─────────────┘
//!         │
//!         ▼
//!    Backend Service
//! ```

use super::ProxySettings;
use axum::{
    body::Body,
    extract::State,
    http::{HeaderMap, HeaderName, HeaderValue, Method, Request, Response, StatusCode, Uri},
    response::IntoResponse,
};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;
use thiserror::Error;
use tracing::{debug, error, info, instrument};

/// Proxy errors
#[derive(Error, Debug)]
pub enum ProxyError {
    #[error("Upstream connection error: {0}")]
    Connection(String),

    #[error("Upstream timeout")]
    Timeout,

    #[error("Invalid request: {0}")]
    InvalidRequest(String),

    #[error("No route found for: {0}")]
    NoRoute(String),

    #[error("Transformation error: {0}")]
    Transformation(String),

    #[error("Rate limited")]
    RateLimited,

    #[error("Policy denied: {0}")]
    PolicyDenied(String),
}

/// Proxy service state
pub struct ProxyService {
    /// Configuration
    settings: ProxySettings,

    /// HTTP client for upstream requests
    client: Client,

    /// Route configuration
    routes: Arc<RouteRegistry>,

    /// Request transformers
    transformers: Vec<Arc<dyn RequestTransformer>>,

    /// Response transformers
    response_transformers: Vec<Arc<dyn ResponseTransformer>>,
}

/// Route registry for upstream routing
pub struct RouteRegistry {
    /// Routes by path prefix
    routes: HashMap<String, RouteConfig>,
}

/// Route configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RouteConfig {
    /// Path prefix to match
    pub path_prefix: String,

    /// Upstream URL
    pub upstream_url: String,

    /// Strip path prefix before forwarding
    #[serde(default)]
    pub strip_prefix: bool,

    /// Rewrite path (regex replacement)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub rewrite_path: Option<String>,

    /// Timeout for this route
    #[serde(default = "default_timeout")]
    pub timeout_secs: u64,

    /// Headers to add
    #[serde(default)]
    pub headers_to_add: HashMap<String, String>,

    /// Headers to remove
    #[serde(default)]
    pub headers_to_remove: Vec<String>,

    /// Enable load balancing
    #[serde(default)]
    pub load_balance: bool,

    /// Additional upstream endpoints for load balancing
    #[serde(default)]
    pub upstream_endpoints: Vec<String>,
}

fn default_timeout() -> u64 {
    30
}

impl RouteRegistry {
    /// Create a new route registry
    pub fn new() -> Self {
        Self {
            routes: HashMap::new(),
        }
    }

    /// Add a route
    pub fn add_route(&mut self, route: RouteConfig) {
        self.routes.insert(route.path_prefix.clone(), route);
    }

    /// Find route for a path
    pub fn find_route(&self, path: &str) -> Option<&RouteConfig> {
        // Find longest matching prefix
        let mut best_match: Option<&RouteConfig> = None;
        let mut best_len = 0;

        for (prefix, route) in &self.routes {
            if path.starts_with(prefix) && prefix.len() > best_len {
                best_match = Some(route);
                best_len = prefix.len();
            }
        }

        best_match
    }
}

impl Default for RouteRegistry {
    fn default() -> Self {
        Self::new()
    }
}

/// Request transformation trait
pub trait RequestTransformer: Send + Sync {
    /// Transform the request before forwarding
    fn transform(&self, request: &mut ProxyRequest) -> Result<(), ProxyError>;

    /// Transformer name for logging
    fn name(&self) -> &str;
}

/// Response transformation trait
pub trait ResponseTransformer: Send + Sync {
    /// Transform the response before returning to client
    fn transform(&self, response: &mut ProxyResponse) -> Result<(), ProxyError>;

    /// Transformer name for logging
    fn name(&self) -> &str;
}

/// Proxy request wrapper
#[derive(Debug)]
pub struct ProxyRequest {
    /// HTTP method
    pub method: Method,

    /// Request URI
    pub uri: Uri,

    /// Request headers
    pub headers: HeaderMap,

    /// Request body
    pub body: Vec<u8>,

    /// Upstream URL (resolved)
    pub upstream_url: Option<String>,

    /// Route configuration
    pub route: Option<RouteConfig>,

    /// Request metadata
    pub metadata: RequestMetadata,
}

/// Proxy response wrapper
#[derive(Debug)]
pub struct ProxyResponse {
    /// Response status
    pub status: StatusCode,

    /// Response headers
    pub headers: HeaderMap,

    /// Response body
    pub body: Vec<u8>,

    /// Upstream response time
    pub upstream_time_ms: u64,
}

/// Request metadata
#[derive(Debug, Default)]
pub struct RequestMetadata {
    /// Request ID
    pub request_id: String,

    /// Tenant ID
    pub tenant_id: Option<String>,

    /// User ID
    pub user_id: Option<String>,

    /// Start time
    pub start_time: Option<std::time::Instant>,
}

impl ProxyService {
    /// Create a new proxy service
    pub fn new(settings: ProxySettings, routes: RouteRegistry) -> Self {
        let client = Client::builder()
            .pool_max_idle_per_host(settings.connection_pool_size)
            .timeout(Duration::from_secs(60))
            .build()
            .expect("Failed to create HTTP client");

        Self {
            settings,
            client,
            routes: Arc::new(routes),
            transformers: Vec::new(),
            response_transformers: Vec::new(),
        }
    }

    /// Add a request transformer
    pub fn add_transformer(&mut self, transformer: Arc<dyn RequestTransformer>) {
        self.transformers.push(transformer);
    }

    /// Add a response transformer
    pub fn add_response_transformer(&mut self, transformer: Arc<dyn ResponseTransformer>) {
        self.response_transformers.push(transformer);
    }

    /// Handle proxy request
    #[instrument(skip(self, request))]
    pub async fn handle(&self, request: Request<Body>) -> Result<Response<Body>, ProxyError> {
        let start = std::time::Instant::now();
        let request_id = uuid::Uuid::new_v4().to_string();

        // Convert to proxy request
        let mut proxy_request = self.convert_request(request, &request_id).await?;

        // Find route
        let path = proxy_request.uri.path();
        let route = self
            .routes
            .find_route(path)
            .ok_or_else(|| ProxyError::NoRoute(path.to_string()))?
            .clone();

        proxy_request.route = Some(route.clone());
        proxy_request.upstream_url = Some(self.build_upstream_url(&route, &proxy_request.uri)?);

        // Apply request transformers
        for transformer in &self.transformers {
            debug!(
                transformer = transformer.name(),
                "Applying request transformer"
            );
            transformer.transform(&mut proxy_request)?;
        }

        // Forward to upstream
        let mut proxy_response = self.forward_request(&proxy_request, &route).await?;

        // Apply response transformers
        for transformer in &self.response_transformers {
            debug!(
                transformer = transformer.name(),
                "Applying response transformer"
            );
            transformer.transform(&mut proxy_response)?;
        }

        let total_time = start.elapsed().as_millis() as u64;
        info!(
            request_id = %request_id,
            upstream_time_ms = proxy_response.upstream_time_ms,
            total_time_ms = total_time,
            status = %proxy_response.status,
            "Proxy request completed"
        );

        // Convert to response
        self.convert_response(proxy_response)
    }

    /// Convert axum request to proxy request
    async fn convert_request(
        &self,
        request: Request<Body>,
        request_id: &str,
    ) -> Result<ProxyRequest, ProxyError> {
        let (parts, body) = request.into_parts();

        let body_bytes = axum::body::to_bytes(body, 10 * 1024 * 1024) // 10MB limit
            .await
            .map_err(|e| ProxyError::InvalidRequest(e.to_string()))?;

        Ok(ProxyRequest {
            method: parts.method,
            uri: parts.uri,
            headers: parts.headers,
            body: body_bytes.to_vec(),
            upstream_url: None,
            route: None,
            metadata: RequestMetadata {
                request_id: request_id.to_string(),
                start_time: Some(std::time::Instant::now()),
                ..Default::default()
            },
        })
    }

    /// Build upstream URL from route config
    fn build_upstream_url(&self, route: &RouteConfig, uri: &Uri) -> Result<String, ProxyError> {
        let path = uri.path();
        let query = uri.query().map(|q| format!("?{}", q)).unwrap_or_default();

        let upstream_path = if route.strip_prefix {
            path.strip_prefix(&route.path_prefix).unwrap_or(path)
        } else {
            path
        };

        Ok(format!("{}{}{}", route.upstream_url, upstream_path, query))
    }

    /// Forward request to upstream
    async fn forward_request(
        &self,
        request: &ProxyRequest,
        route: &RouteConfig,
    ) -> Result<ProxyResponse, ProxyError> {
        let upstream_url = request
            .upstream_url
            .as_ref()
            .ok_or_else(|| ProxyError::InvalidRequest("No upstream URL".to_string()))?;

        let start = std::time::Instant::now();

        // Convert axum Method (http 1.x) to reqwest Method (http 0.2)
        let method = reqwest::Method::from_bytes(request.method.as_str().as_bytes())
            .map_err(|e| ProxyError::InvalidRequest(format!("Invalid method: {}", e)))?;

        // Build request
        let mut req_builder = self.client.request(method, upstream_url);

        // Copy headers (convert axum HeaderName/Value to reqwest-compatible)
        for (name, value) in &request.headers {
            // Skip hop-by-hop headers
            if is_hop_by_hop_header(name) {
                continue;
            }
            // Convert to string and back to ensure compatibility
            let name_str = name.as_str();
            if let Ok(value_str) = value.to_str() {
                req_builder = req_builder.header(name_str, value_str);
            }
        }

        // Add route-specific headers
        for (name, value) in &route.headers_to_add {
            req_builder = req_builder.header(name.as_str(), value.as_str());
        }

        // Add body if present
        if !request.body.is_empty() {
            req_builder = req_builder.body(request.body.clone());
        }

        // Set timeout
        req_builder = req_builder.timeout(Duration::from_secs(route.timeout_secs));

        // Send request
        let response = req_builder.send().await.map_err(|e| {
            if e.is_timeout() {
                ProxyError::Timeout
            } else {
                ProxyError::Connection(e.to_string())
            }
        })?;

        let upstream_time = start.elapsed().as_millis() as u64;

        // Convert response
        let status = response.status();
        let headers = response.headers().clone();
        let body = response
            .bytes()
            .await
            .map_err(|e| ProxyError::Connection(e.to_string()))?
            .to_vec();

        // Convert reqwest headers to axum HeaderMap
        let mut response_headers = HeaderMap::new();
        for (name, value) in headers.iter() {
            if !is_hop_by_hop_header_str(name.as_str()) {
                if let Ok(name) = HeaderName::from_bytes(name.as_str().as_bytes()) {
                    if let Ok(value) = HeaderValue::from_bytes(value.as_bytes()) {
                        response_headers.insert(name, value);
                    }
                }
            }
        }

        // Remove headers specified in route config
        for header_name in &route.headers_to_remove {
            if let Ok(name) = HeaderName::from_bytes(header_name.as_bytes()) {
                response_headers.remove(&name);
            }
        }

        Ok(ProxyResponse {
            status: StatusCode::from_u16(status.as_u16()).unwrap_or(StatusCode::BAD_GATEWAY),
            headers: response_headers,
            body,
            upstream_time_ms: upstream_time,
        })
    }

    /// Convert proxy response to axum response
    fn convert_response(&self, response: ProxyResponse) -> Result<Response<Body>, ProxyError> {
        let mut builder = Response::builder().status(response.status);

        for (name, value) in &response.headers {
            builder = builder.header(name, value);
        }

        builder
            .body(Body::from(response.body))
            .map_err(|e| ProxyError::Transformation(e.to_string()))
    }
}

/// Check if a header is a hop-by-hop header that shouldn't be forwarded
fn is_hop_by_hop_header(name: &HeaderName) -> bool {
    is_hop_by_hop_header_str(name.as_str())
}

/// Check if a header name (as string) is a hop-by-hop header
fn is_hop_by_hop_header_str(name: &str) -> bool {
    matches!(
        name.to_lowercase().as_str(),
        "connection"
            | "keep-alive"
            | "proxy-authenticate"
            | "proxy-authorization"
            | "te"
            | "trailers"
            | "transfer-encoding"
            | "upgrade"
    )
}

/// Header injection transformer
pub struct HeaderInjector {
    /// Headers to inject
    headers: HashMap<String, String>,
}

impl HeaderInjector {
    pub fn new(headers: HashMap<String, String>) -> Self {
        Self { headers }
    }
}

impl RequestTransformer for HeaderInjector {
    fn transform(&self, request: &mut ProxyRequest) -> Result<(), ProxyError> {
        for (name, value) in &self.headers {
            if let (Ok(name), Ok(value)) = (
                HeaderName::from_bytes(name.as_bytes()),
                HeaderValue::from_str(value),
            ) {
                request.headers.insert(name, value);
            }
        }
        Ok(())
    }

    fn name(&self) -> &str {
        "header_injector"
    }
}

/// Axum handler for proxy mode
pub async fn handle_proxy(
    State(service): State<Arc<ProxyService>>,
    request: Request<Body>,
) -> impl IntoResponse {
    match service.handle(request).await {
        Ok(response) => response,
        Err(e) => {
            error!("Proxy error: {}", e);
            match e {
                ProxyError::NoRoute(_) => StatusCode::NOT_FOUND.into_response(),
                ProxyError::Timeout => StatusCode::GATEWAY_TIMEOUT.into_response(),
                ProxyError::RateLimited => StatusCode::TOO_MANY_REQUESTS.into_response(),
                ProxyError::PolicyDenied(_) => StatusCode::FORBIDDEN.into_response(),
                _ => StatusCode::BAD_GATEWAY.into_response(),
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_route_registry_find() {
        let mut registry = RouteRegistry::new();
        registry.add_route(RouteConfig {
            path_prefix: "/api/v1".to_string(),
            upstream_url: "http://backend:8080".to_string(),
            strip_prefix: true,
            rewrite_path: None,
            timeout_secs: 30,
            headers_to_add: HashMap::new(),
            headers_to_remove: Vec::new(),
            load_balance: false,
            upstream_endpoints: Vec::new(),
        });
        registry.add_route(RouteConfig {
            path_prefix: "/api/v1/users".to_string(),
            upstream_url: "http://users:8080".to_string(),
            strip_prefix: true,
            rewrite_path: None,
            timeout_secs: 30,
            headers_to_add: HashMap::new(),
            headers_to_remove: Vec::new(),
            load_balance: false,
            upstream_endpoints: Vec::new(),
        });

        // Should match longest prefix
        let route = registry.find_route("/api/v1/users/123").unwrap();
        assert_eq!(route.upstream_url, "http://users:8080");

        // Should match shorter prefix
        let route = registry.find_route("/api/v1/products").unwrap();
        assert_eq!(route.upstream_url, "http://backend:8080");

        // No match
        assert!(registry.find_route("/other").is_none());
    }

    #[test]
    fn test_hop_by_hop_headers() {
        assert!(is_hop_by_hop_header(&HeaderName::from_static("connection")));
        assert!(is_hop_by_hop_header(&HeaderName::from_static(
            "transfer-encoding"
        )));
        assert!(!is_hop_by_hop_header(&HeaderName::from_static(
            "content-type"
        )));
        assert!(!is_hop_by_hop_header(&HeaderName::from_static(
            "authorization"
        )));
    }

    #[test]
    fn test_header_injector() {
        let mut headers = HashMap::new();
        headers.insert("X-Custom".to_string(), "value".to_string());

        let injector = HeaderInjector::new(headers);

        let mut request = ProxyRequest {
            method: Method::GET,
            uri: "/test".parse().unwrap(),
            headers: HeaderMap::new(),
            body: Vec::new(),
            upstream_url: None,
            route: None,
            metadata: RequestMetadata::default(),
        };

        injector.transform(&mut request).unwrap();

        assert!(request.headers.contains_key("x-custom"));
    }
}
