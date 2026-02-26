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

    fn make_route(prefix: &str, upstream: &str) -> RouteConfig {
        RouteConfig {
            path_prefix: prefix.to_string(),
            upstream_url: upstream.to_string(),
            strip_prefix: false,
            rewrite_path: None,
            timeout_secs: 30,
            headers_to_add: HashMap::new(),
            headers_to_remove: Vec::new(),
            load_balance: false,
            upstream_endpoints: Vec::new(),
        }
    }

    fn make_route_strip(prefix: &str, upstream: &str) -> RouteConfig {
        RouteConfig {
            strip_prefix: true,
            ..make_route(prefix, upstream)
        }
    }

    #[test]
    fn test_route_registry_find() {
        let mut registry = RouteRegistry::new();
        registry.add_route(make_route_strip("/api/v1", "http://backend:8080"));
        registry.add_route(make_route_strip("/api/v1/users", "http://users:8080"));

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
    fn test_route_registry_empty() {
        let registry = RouteRegistry::new();
        assert!(registry.find_route("/anything").is_none());
    }

    #[test]
    fn test_route_registry_default() {
        let registry = RouteRegistry::default();
        assert!(registry.find_route("/anything").is_none());
    }

    #[test]
    fn test_route_registry_exact_match() {
        let mut registry = RouteRegistry::new();
        registry.add_route(make_route("/api/v1/health", "http://health:8080"));

        let route = registry.find_route("/api/v1/health").unwrap();
        assert_eq!(route.upstream_url, "http://health:8080");
    }

    #[test]
    fn test_hop_by_hop_headers() {
        assert!(is_hop_by_hop_header(&HeaderName::from_static("connection")));
        assert!(is_hop_by_hop_header(&HeaderName::from_static(
            "transfer-encoding"
        )));
        assert!(is_hop_by_hop_header(&HeaderName::from_static("upgrade")));
        assert!(is_hop_by_hop_header(&HeaderName::from_static("keep-alive")));
        assert!(is_hop_by_hop_header(&HeaderName::from_static("te")));
        assert!(is_hop_by_hop_header(&HeaderName::from_static("trailers")));
        assert!(is_hop_by_hop_header(&HeaderName::from_static(
            "proxy-authenticate"
        )));
        assert!(is_hop_by_hop_header(&HeaderName::from_static(
            "proxy-authorization"
        )));
        // Non hop-by-hop
        assert!(!is_hop_by_hop_header(&HeaderName::from_static(
            "content-type"
        )));
        assert!(!is_hop_by_hop_header(&HeaderName::from_static(
            "authorization"
        )));
        assert!(!is_hop_by_hop_header(&HeaderName::from_static("x-custom")));
    }

    #[test]
    fn test_header_injector() {
        let mut headers = HashMap::new();
        headers.insert("X-Custom".to_string(), "value".to_string());

        let injector = HeaderInjector::new(headers);
        assert_eq!(injector.name(), "header_injector");

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

    #[test]
    fn test_header_injector_multiple() {
        let mut headers = HashMap::new();
        headers.insert("X-Tenant".to_string(), "acme".to_string());
        headers.insert("X-Request-ID".to_string(), "req-123".to_string());

        let injector = HeaderInjector::new(headers);

        let mut request = ProxyRequest {
            method: Method::POST,
            uri: "/api".parse().unwrap(),
            headers: HeaderMap::new(),
            body: Vec::new(),
            upstream_url: None,
            route: None,
            metadata: RequestMetadata::default(),
        };

        injector.transform(&mut request).unwrap();

        assert_eq!(
            request.headers.get("x-tenant").unwrap().to_str().unwrap(),
            "acme"
        );
        assert_eq!(
            request
                .headers
                .get("x-request-id")
                .unwrap()
                .to_str()
                .unwrap(),
            "req-123"
        );
    }

    #[test]
    fn test_build_upstream_url_no_strip() {
        let service = ProxyService::new(ProxySettings::default(), RouteRegistry::new());
        let route = make_route("/api/v1", "http://backend:8080");
        let uri: Uri = "/api/v1/users?page=1".parse().unwrap();

        let url = service.build_upstream_url(&route, &uri).unwrap();
        assert_eq!(url, "http://backend:8080/api/v1/users?page=1");
    }

    #[test]
    fn test_build_upstream_url_strip_prefix() {
        let service = ProxyService::new(ProxySettings::default(), RouteRegistry::new());
        let route = make_route_strip("/api/v1", "http://backend:8080");
        let uri: Uri = "/api/v1/users".parse().unwrap();

        let url = service.build_upstream_url(&route, &uri).unwrap();
        assert_eq!(url, "http://backend:8080/users");
    }

    #[test]
    fn test_build_upstream_url_no_query() {
        let service = ProxyService::new(ProxySettings::default(), RouteRegistry::new());
        let route = make_route("/api", "http://backend:8080");
        let uri: Uri = "/api/health".parse().unwrap();

        let url = service.build_upstream_url(&route, &uri).unwrap();
        assert_eq!(url, "http://backend:8080/api/health");
    }

    #[test]
    fn test_default_timeout() {
        assert_eq!(default_timeout(), 30);
    }

    #[test]
    fn test_route_config_serde_defaults() {
        let json = r#"{"path_prefix":"/api","upstream_url":"http://up:80"}"#;
        let config: RouteConfig = serde_json::from_str(json).unwrap();

        assert_eq!(config.path_prefix, "/api");
        assert_eq!(config.upstream_url, "http://up:80");
        assert!(!config.strip_prefix);
        assert!(config.rewrite_path.is_none());
        assert_eq!(config.timeout_secs, 30); // default_timeout()
        assert!(config.headers_to_add.is_empty());
        assert!(config.headers_to_remove.is_empty());
        assert!(!config.load_balance);
        assert!(config.upstream_endpoints.is_empty());
    }

    #[test]
    fn test_proxy_error_display() {
        let e = ProxyError::Connection("refused".to_string());
        assert!(e.to_string().contains("refused"));

        let e = ProxyError::Timeout;
        assert_eq!(e.to_string(), "Upstream timeout");

        let e = ProxyError::NoRoute("/unknown".to_string());
        assert!(e.to_string().contains("/unknown"));

        let e = ProxyError::RateLimited;
        assert_eq!(e.to_string(), "Rate limited");

        let e = ProxyError::PolicyDenied("blocked".to_string());
        assert!(e.to_string().contains("blocked"));

        let e = ProxyError::InvalidRequest("bad".to_string());
        assert!(e.to_string().contains("bad"));

        let e = ProxyError::Transformation("failed".to_string());
        assert!(e.to_string().contains("failed"));
    }

    #[test]
    fn test_proxy_service_add_transformer() {
        let mut service = ProxyService::new(ProxySettings::default(), RouteRegistry::new());

        let injector = Arc::new(HeaderInjector::new(HashMap::new()));
        service.add_transformer(injector);

        assert_eq!(service.transformers.len(), 1);
    }

    #[test]
    fn test_proxy_service_add_response_transformer() {
        struct NoopResponseTransformer;
        impl ResponseTransformer for NoopResponseTransformer {
            fn transform(&self, _response: &mut ProxyResponse) -> Result<(), ProxyError> {
                Ok(())
            }
            fn name(&self) -> &str {
                "noop"
            }
        }

        let mut service = ProxyService::new(ProxySettings::default(), RouteRegistry::new());
        service.add_response_transformer(Arc::new(NoopResponseTransformer));

        assert_eq!(service.response_transformers.len(), 1);
    }

    #[test]
    fn test_convert_response_ok() {
        let service = ProxyService::new(ProxySettings::default(), RouteRegistry::new());
        let response = ProxyResponse {
            status: StatusCode::OK,
            headers: HeaderMap::new(),
            body: b"hello".to_vec(),
            upstream_time_ms: 42,
        };

        let result = service.convert_response(response).unwrap();
        assert_eq!(result.status(), StatusCode::OK);
    }

    #[test]
    fn test_convert_response_with_headers() {
        let service = ProxyService::new(ProxySettings::default(), RouteRegistry::new());
        let mut headers = HeaderMap::new();
        headers.insert("x-custom", HeaderValue::from_static("test"));

        let response = ProxyResponse {
            status: StatusCode::CREATED,
            headers,
            body: Vec::new(),
            upstream_time_ms: 10,
        };

        let result = service.convert_response(response).unwrap();
        assert_eq!(result.status(), StatusCode::CREATED);
        assert_eq!(result.headers().get("x-custom").unwrap(), "test");
    }

    #[test]
    fn test_request_metadata_default() {
        let metadata = RequestMetadata::default();
        assert!(metadata.request_id.is_empty());
        assert!(metadata.tenant_id.is_none());
        assert!(metadata.user_id.is_none());
        assert!(metadata.start_time.is_none());
    }

    // --- New tests for CAB-1488: Proxy Mode Unit Tests ---

    #[test]
    fn test_route_registry_overwrite() {
        let mut registry = RouteRegistry::new();
        registry.add_route(make_route("/api/v1", "http://old-backend:8080"));
        registry.add_route(make_route("/api/v1", "http://new-backend:9090"));

        let route = registry.find_route("/api/v1/users").unwrap();
        assert_eq!(route.upstream_url, "http://new-backend:9090");
    }

    #[test]
    fn test_route_registry_root_path() {
        let mut registry = RouteRegistry::new();
        registry.add_route(make_route("/", "http://default:8080"));

        let route = registry.find_route("/anything").unwrap();
        assert_eq!(route.upstream_url, "http://default:8080");

        let route = registry.find_route("/").unwrap();
        assert_eq!(route.upstream_url, "http://default:8080");
    }

    #[test]
    fn test_build_upstream_url_strip_prefix_exact_match() {
        let service = ProxyService::new(ProxySettings::default(), RouteRegistry::new());
        let route = make_route_strip("/api/v1", "http://backend:8080");
        let uri: Uri = "/api/v1".parse().unwrap();

        let url = service.build_upstream_url(&route, &uri).unwrap();
        assert_eq!(url, "http://backend:8080");
    }

    #[test]
    fn test_build_upstream_url_strip_prefix_with_query() {
        let service = ProxyService::new(ProxySettings::default(), RouteRegistry::new());
        let route = make_route_strip("/api/v1", "http://backend:8080");
        let uri: Uri = "/api/v1/users?page=2&limit=10".parse().unwrap();

        let url = service.build_upstream_url(&route, &uri).unwrap();
        assert_eq!(url, "http://backend:8080/users?page=2&limit=10");
    }

    #[test]
    fn test_is_hop_by_hop_header_str_direct() {
        assert!(is_hop_by_hop_header_str("connection"));
        assert!(is_hop_by_hop_header_str("Connection"));
        assert!(is_hop_by_hop_header_str("TRANSFER-ENCODING"));
        assert!(is_hop_by_hop_header_str("keep-alive"));
        assert!(is_hop_by_hop_header_str("te"));
        assert!(is_hop_by_hop_header_str("trailers"));
        assert!(is_hop_by_hop_header_str("proxy-authenticate"));
        assert!(is_hop_by_hop_header_str("proxy-authorization"));
        assert!(is_hop_by_hop_header_str("upgrade"));

        assert!(!is_hop_by_hop_header_str("content-type"));
        assert!(!is_hop_by_hop_header_str("authorization"));
        assert!(!is_hop_by_hop_header_str("x-custom-header"));
        assert!(!is_hop_by_hop_header_str("accept"));
    }

    #[test]
    fn test_route_config_serde_all_fields() {
        let json = r#"{
            "path_prefix": "/api",
            "upstream_url": "http://backend:8080",
            "strip_prefix": true,
            "rewrite_path": "/v2",
            "timeout_secs": 60,
            "headers_to_add": {"X-Tenant": "acme"},
            "headers_to_remove": ["X-Internal"],
            "load_balance": true,
            "upstream_endpoints": ["http://backend-1:8080", "http://backend-2:8080"]
        }"#;
        let config: RouteConfig = serde_json::from_str(json).unwrap();

        assert_eq!(config.path_prefix, "/api");
        assert_eq!(config.upstream_url, "http://backend:8080");
        assert!(config.strip_prefix);
        assert_eq!(config.rewrite_path.as_deref(), Some("/v2"));
        assert_eq!(config.timeout_secs, 60);
        assert_eq!(
            config.headers_to_add.get("X-Tenant").map(|s| s.as_str()),
            Some("acme")
        );
        assert_eq!(config.headers_to_remove, vec!["X-Internal".to_string()]);
        assert!(config.load_balance);
        assert_eq!(config.upstream_endpoints.len(), 2);
    }

    #[test]
    fn test_route_config_serde_roundtrip() {
        let config = RouteConfig {
            path_prefix: "/api".to_string(),
            upstream_url: "http://up:80".to_string(),
            strip_prefix: true,
            rewrite_path: Some("/v2".to_string()),
            timeout_secs: 45,
            headers_to_add: HashMap::from([("X-Key".to_string(), "val".to_string())]),
            headers_to_remove: vec!["X-Remove".to_string()],
            load_balance: true,
            upstream_endpoints: vec!["http://a:80".to_string()],
        };

        let json = serde_json::to_string(&config).unwrap();
        let deserialized: RouteConfig = serde_json::from_str(&json).unwrap();

        assert_eq!(deserialized.path_prefix, config.path_prefix);
        assert_eq!(deserialized.upstream_url, config.upstream_url);
        assert_eq!(deserialized.strip_prefix, config.strip_prefix);
        assert_eq!(deserialized.rewrite_path, config.rewrite_path);
        assert_eq!(deserialized.timeout_secs, config.timeout_secs);
        assert_eq!(deserialized.headers_to_add, config.headers_to_add);
        assert_eq!(deserialized.headers_to_remove, config.headers_to_remove);
        assert_eq!(deserialized.load_balance, config.load_balance);
        assert_eq!(deserialized.upstream_endpoints, config.upstream_endpoints);
    }

    #[test]
    fn test_multiple_request_transformers_applied_in_order() {
        let mut service = ProxyService::new(ProxySettings::default(), RouteRegistry::new());

        let injector1 = Arc::new(HeaderInjector::new(HashMap::from([(
            "X-First".to_string(),
            "1".to_string(),
        )])));
        let injector2 = Arc::new(HeaderInjector::new(HashMap::from([(
            "X-Second".to_string(),
            "2".to_string(),
        )])));
        let injector3 = Arc::new(HeaderInjector::new(HashMap::from([(
            "X-Third".to_string(),
            "3".to_string(),
        )])));

        service.add_transformer(injector1);
        service.add_transformer(injector2);
        service.add_transformer(injector3);

        assert_eq!(service.transformers.len(), 3);

        let mut request = ProxyRequest {
            method: Method::GET,
            uri: "/test".parse().unwrap(),
            headers: HeaderMap::new(),
            body: Vec::new(),
            upstream_url: None,
            route: None,
            metadata: RequestMetadata::default(),
        };

        for transformer in &service.transformers {
            transformer.transform(&mut request).unwrap();
        }

        assert_eq!(
            request.headers.get("x-first").unwrap().to_str().unwrap(),
            "1"
        );
        assert_eq!(
            request.headers.get("x-second").unwrap().to_str().unwrap(),
            "2"
        );
        assert_eq!(
            request.headers.get("x-third").unwrap().to_str().unwrap(),
            "3"
        );
    }

    #[test]
    fn test_custom_response_transformer() {
        struct StatusOverrideTransformer;
        impl ResponseTransformer for StatusOverrideTransformer {
            fn transform(&self, response: &mut ProxyResponse) -> Result<(), ProxyError> {
                if response.status == StatusCode::OK {
                    response
                        .headers
                        .insert("x-transformed", HeaderValue::from_static("true"));
                }
                Ok(())
            }
            fn name(&self) -> &str {
                "status_override"
            }
        }

        let mut service = ProxyService::new(ProxySettings::default(), RouteRegistry::new());
        service.add_response_transformer(Arc::new(StatusOverrideTransformer));

        assert_eq!(service.response_transformers.len(), 1);
        assert_eq!(service.response_transformers[0].name(), "status_override");

        let mut response = ProxyResponse {
            status: StatusCode::OK,
            headers: HeaderMap::new(),
            body: Vec::new(),
            upstream_time_ms: 0,
        };
        service.response_transformers[0]
            .transform(&mut response)
            .unwrap();
        assert_eq!(response.headers.get("x-transformed").unwrap(), "true");
    }

    #[test]
    fn test_proxy_settings_default_values() {
        let settings = ProxySettings::default();
        assert!(!settings.transform_request);
        assert!(!settings.transform_response);
        // Default derive gives false for inject_headers (unlike from_env which gives true)
        assert!(!settings.inject_headers);
        assert!(!settings.websocket_passthrough);
        assert_eq!(settings.connection_pool_size, 0);
    }

    #[test]
    fn test_header_injector_overwrites_existing() {
        let mut headers = HashMap::new();
        headers.insert("X-Custom".to_string(), "new-value".to_string());

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

        request
            .headers
            .insert("x-custom", HeaderValue::from_static("old-value"));

        injector.transform(&mut request).unwrap();

        assert_eq!(
            request.headers.get("x-custom").unwrap().to_str().unwrap(),
            "new-value"
        );
    }

    #[test]
    fn test_convert_response_error_status() {
        let service = ProxyService::new(ProxySettings::default(), RouteRegistry::new());
        let response = ProxyResponse {
            status: StatusCode::INTERNAL_SERVER_ERROR,
            headers: HeaderMap::new(),
            body: b"error".to_vec(),
            upstream_time_ms: 100,
        };

        let result = service.convert_response(response).unwrap();
        assert_eq!(result.status(), StatusCode::INTERNAL_SERVER_ERROR);
    }

    #[test]
    fn test_convert_response_not_found() {
        let service = ProxyService::new(ProxySettings::default(), RouteRegistry::new());
        let response = ProxyResponse {
            status: StatusCode::NOT_FOUND,
            headers: HeaderMap::new(),
            body: Vec::new(),
            upstream_time_ms: 5,
        };

        let result = service.convert_response(response).unwrap();
        assert_eq!(result.status(), StatusCode::NOT_FOUND);
    }

    #[test]
    fn test_request_metadata_with_populated_fields() {
        let metadata = RequestMetadata {
            request_id: "req-abc-123".to_string(),
            tenant_id: Some("tenant-acme".to_string()),
            user_id: Some("user-42".to_string()),
            start_time: Some(std::time::Instant::now()),
        };

        assert_eq!(metadata.request_id, "req-abc-123");
        assert_eq!(metadata.tenant_id.as_deref(), Some("tenant-acme"));
        assert_eq!(metadata.user_id.as_deref(), Some("user-42"));
        assert!(metadata.start_time.is_some());
    }

    #[test]
    fn test_proxy_request_construction() {
        let route = make_route("/api", "http://backend:8080");
        let mut headers = HeaderMap::new();
        headers.insert("content-type", HeaderValue::from_static("application/json"));

        let request = ProxyRequest {
            method: Method::POST,
            uri: "/api/data".parse().unwrap(),
            headers,
            body: b"{\"key\":\"value\"}".to_vec(),
            upstream_url: Some("http://backend:8080/api/data".to_string()),
            route: Some(route.clone()),
            metadata: RequestMetadata {
                request_id: "test-req".to_string(),
                ..Default::default()
            },
        };

        assert_eq!(request.method, Method::POST);
        assert_eq!(request.uri.path(), "/api/data");
        assert!(request.headers.contains_key("content-type"));
        assert_eq!(request.body.len(), 15);
        assert!(request.upstream_url.is_some());
        assert!(request.route.is_some());
        assert_eq!(request.metadata.request_id, "test-req");
    }

    #[test]
    fn test_proxy_response_with_body() {
        let mut headers = HeaderMap::new();
        headers.insert("content-type", HeaderValue::from_static("text/plain"));
        headers.insert("x-server", HeaderValue::from_static("stoa"));

        let response = ProxyResponse {
            status: StatusCode::OK,
            headers,
            body: b"Hello, World!".to_vec(),
            upstream_time_ms: 42,
        };

        assert_eq!(response.status, StatusCode::OK);
        assert_eq!(response.headers.len(), 2);
        assert_eq!(response.body, b"Hello, World!");
        assert_eq!(response.upstream_time_ms, 42);
    }

    #[test]
    fn test_proxy_service_creation_with_routes() {
        let mut registry = RouteRegistry::new();
        registry.add_route(make_route("/api/v1", "http://api:8080"));
        registry.add_route(make_route("/static", "http://cdn:80"));

        let service = ProxyService::new(ProxySettings::default(), registry);

        assert!(service.transformers.is_empty());
        assert!(service.response_transformers.is_empty());
        assert!(service.routes.find_route("/api/v1/users").is_some());
        assert!(service.routes.find_route("/static/style.css").is_some());
        assert!(service.routes.find_route("/unknown").is_none());
    }

    #[test]
    fn test_proxy_error_variants_are_distinct() {
        let errors: Vec<ProxyError> = vec![
            ProxyError::Connection("conn".to_string()),
            ProxyError::Timeout,
            ProxyError::InvalidRequest("invalid".to_string()),
            ProxyError::NoRoute("/missing".to_string()),
            ProxyError::Transformation("fail".to_string()),
            ProxyError::RateLimited,
            ProxyError::PolicyDenied("deny".to_string()),
        ];

        let messages: Vec<String> = errors.iter().map(|e| e.to_string()).collect();
        // Verify all error messages are unique
        for (i, msg) in messages.iter().enumerate() {
            for (j, other) in messages.iter().enumerate() {
                if i != j {
                    assert_ne!(msg, other, "Error messages should be distinct");
                }
            }
        }
    }

    #[test]
    fn test_convert_response_preserves_multiple_headers() {
        let service = ProxyService::new(ProxySettings::default(), RouteRegistry::new());
        let mut headers = HeaderMap::new();
        headers.insert("x-request-id", HeaderValue::from_static("abc-123"));
        headers.insert("x-trace-id", HeaderValue::from_static("trace-456"));
        headers.insert("content-type", HeaderValue::from_static("application/json"));

        let response = ProxyResponse {
            status: StatusCode::OK,
            headers,
            body: b"{}".to_vec(),
            upstream_time_ms: 15,
        };

        let result = service.convert_response(response).unwrap();
        assert_eq!(result.status(), StatusCode::OK);
        assert_eq!(result.headers().get("x-request-id").unwrap(), "abc-123");
        assert_eq!(result.headers().get("x-trace-id").unwrap(), "trace-456");
        assert_eq!(
            result.headers().get("content-type").unwrap(),
            "application/json"
        );
    }

    #[test]
    fn test_route_registry_longest_prefix_wins() {
        let mut registry = RouteRegistry::new();
        registry.add_route(make_route("/", "http://default:80"));
        registry.add_route(make_route("/api", "http://api:80"));
        registry.add_route(make_route("/api/v1", "http://api-v1:80"));
        registry.add_route(make_route("/api/v1/users", "http://users:80"));

        assert_eq!(
            registry
                .find_route("/api/v1/users/42")
                .unwrap()
                .upstream_url,
            "http://users:80"
        );
        assert_eq!(
            registry
                .find_route("/api/v1/products")
                .unwrap()
                .upstream_url,
            "http://api-v1:80"
        );
        assert_eq!(
            registry.find_route("/api/v2/items").unwrap().upstream_url,
            "http://api:80"
        );
        assert_eq!(
            registry.find_route("/health").unwrap().upstream_url,
            "http://default:80"
        );
    }

    #[test]
    fn test_header_injector_empty_headers() {
        let injector = HeaderInjector::new(HashMap::new());
        assert_eq!(injector.name(), "header_injector");

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
        assert!(request.headers.is_empty());
    }
}
