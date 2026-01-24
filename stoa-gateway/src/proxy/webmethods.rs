use axum::{
    body::Body,
    extract::Request,
    http::{header, HeaderMap, HeaderValue, Method, StatusCode},
    response::{IntoResponse, Response},
};
use std::time::Duration;

/// Proxy for forwarding requests to the webMethods gateway.
///
/// Handles HTTP request forwarding with proper header manipulation
/// and error handling.
#[derive(Clone)]
pub struct WebMethodsProxy {
    /// Base URL of the webMethods gateway
    base_url: String,
    /// HTTP client for making requests
    client: reqwest::Client,
}

impl WebMethodsProxy {
    /// Create a new webMethods proxy.
    ///
    /// # Arguments
    /// * `base_url` - Base URL of the webMethods gateway (e.g., "https://gateway.gostoa.dev")
    pub fn new(base_url: String) -> Self {
        let client = reqwest::Client::builder()
            .timeout(Duration::from_secs(30))
            .connect_timeout(Duration::from_secs(5))
            .build()
            .expect("Failed to create HTTP client");

        Self { base_url, client }
    }

    /// Forward a request to webMethods.
    ///
    /// This method:
    /// 1. Constructs the target URL from the incoming request path
    /// 2. Copies relevant headers (excluding hop-by-hop headers)
    /// 3. Forwards the request body
    /// 4. Returns the response from webMethods
    pub async fn forward(&self, request: Request<Body>) -> Response {
        let method = request.method().clone();
        let uri = request.uri().clone();
        let headers = request.headers().clone();

        // Build target URL
        let path_and_query = uri.path_and_query().map(|pq| pq.as_str()).unwrap_or("/");
        let target_url = format!("{}{}", self.base_url, path_and_query);

        tracing::debug!(
            method = %method,
            target_url = %target_url,
            "forwarding request to webmethods"
        );

        // Build the proxied request
        let mut req_builder = match method {
            Method::GET => self.client.get(&target_url),
            Method::POST => self.client.post(&target_url),
            Method::PUT => self.client.put(&target_url),
            Method::DELETE => self.client.delete(&target_url),
            Method::PATCH => self.client.patch(&target_url),
            Method::HEAD => self.client.head(&target_url),
            Method::OPTIONS => self.client.request(Method::OPTIONS, &target_url),
            _ => {
                tracing::warn!(method = %method, "unsupported HTTP method");
                return (StatusCode::METHOD_NOT_ALLOWED, "Method not allowed").into_response();
            }
        };

        // Copy headers, excluding hop-by-hop headers
        req_builder = Self::copy_headers(req_builder, &headers);

        // Forward body for methods that support it
        if matches!(method, Method::POST | Method::PUT | Method::PATCH) {
            let body_bytes = match axum::body::to_bytes(request.into_body(), 10 * 1024 * 1024).await
            {
                Ok(bytes) => bytes,
                Err(e) => {
                    tracing::error!(error = %e, "failed to read request body");
                    return (StatusCode::BAD_REQUEST, "Failed to read request body")
                        .into_response();
                }
            };
            req_builder = req_builder.body(body_bytes);
        }

        // Send the request
        match req_builder.send().await {
            Ok(resp) => Self::convert_response(resp).await,
            Err(e) => {
                tracing::error!(
                    error = %e,
                    target_url = %target_url,
                    "failed to forward request to webmethods"
                );

                if e.is_timeout() {
                    (StatusCode::GATEWAY_TIMEOUT, "Gateway timeout").into_response()
                } else if e.is_connect() {
                    (StatusCode::BAD_GATEWAY, "Failed to connect to upstream").into_response()
                } else {
                    (StatusCode::BAD_GATEWAY, "Bad gateway").into_response()
                }
            }
        }
    }

    /// Copy headers from the incoming request to the outgoing request.
    ///
    /// Excludes hop-by-hop headers that should not be forwarded.
    fn copy_headers(
        mut builder: reqwest::RequestBuilder,
        headers: &HeaderMap<HeaderValue>,
    ) -> reqwest::RequestBuilder {
        // Headers that should not be forwarded (hop-by-hop headers)
        const HOP_BY_HOP: &[&str] = &[
            "connection",
            "keep-alive",
            "proxy-authenticate",
            "proxy-authorization",
            "te",
            "trailer",
            "transfer-encoding",
            "upgrade",
            "host", // We'll use the target host
        ];

        for (name, value) in headers.iter() {
            let name_str = name.as_str().to_lowercase();
            if !HOP_BY_HOP.contains(&name_str.as_str()) {
                if let Ok(header_name) = reqwest::header::HeaderName::from_bytes(name.as_ref()) {
                    if let Ok(header_value) =
                        reqwest::header::HeaderValue::from_bytes(value.as_bytes())
                    {
                        builder = builder.header(header_name, header_value);
                    }
                }
            }
        }

        builder
    }

    /// Convert a reqwest response to an axum response.
    async fn convert_response(resp: reqwest::Response) -> Response {
        let status = resp.status();
        let headers = resp.headers().clone();

        // Get response body
        let body = match resp.bytes().await {
            Ok(bytes) => bytes,
            Err(e) => {
                tracing::error!(error = %e, "failed to read response body from webmethods");
                return (StatusCode::BAD_GATEWAY, "Failed to read upstream response")
                    .into_response();
            }
        };

        // Build axum response
        let mut response = Response::builder()
            .status(StatusCode::from_u16(status.as_u16()).unwrap_or(StatusCode::OK));

        // Copy response headers
        for (name, value) in headers.iter() {
            let name_str = name.as_str().to_lowercase();
            // Skip hop-by-hop headers
            if !["connection", "keep-alive", "transfer-encoding"].contains(&name_str.as_str()) {
                if let Ok(header_name) = header::HeaderName::from_bytes(name.as_ref()) {
                    if let Ok(header_value) = header::HeaderValue::from_bytes(value.as_bytes()) {
                        response = response.header(header_name, header_value);
                    }
                }
            }
        }

        response.body(Body::from(body)).unwrap_or_else(|_| {
            (StatusCode::INTERNAL_SERVER_ERROR, "Internal error").into_response()
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_proxy_creation() {
        let proxy = WebMethodsProxy::new("https://gateway.gostoa.dev".to_string());
        assert_eq!(proxy.base_url, "https://gateway.gostoa.dev");
    }
}
