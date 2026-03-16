//! Pingora Connection Pool — Cloudflare-grade upstream management (CAB-1849)
//!
//! Wraps `pingora-core::connectors::http::Connector` to provide shared
//! connection pooling across all worker threads. This is the core advantage
//! Pingora brings over reqwest: connections are multiplexed and reused
//! globally, not per-client-instance.
//!
//! Feature-gated: `#[cfg(feature = "pingora")]`
//!
//! # Usage
//!
//! ```rust,ignore
//! let pool = PingoraPool::new();
//! let response = pool.send_request("http://backend:8080/api", method, headers, body).await?;
//! ```

use axum::body::Body;
use axum::http::{HeaderMap, HeaderValue, Method, StatusCode};
use axum::response::{IntoResponse, Response};
use bytes::Bytes;
use pingora_core::connectors::http::Connector as HttpConnector;
use pingora_core::upstreams::peer::HttpPeer;
use std::sync::Arc;
use std::time::Duration;
use tracing::{debug, error, info};

/// Shared Pingora connection pool.
///
/// Uses Pingora's internal connection pool which shares connections across
/// all async tasks (equivalent to Cloudflare's cross-worker pool).
pub struct PingoraPool {
    connector: Arc<HttpConnector>,
}

impl PingoraPool {
    /// Create a new Pingora connection pool with default settings.
    pub fn new() -> Self {
        let connector = HttpConnector::new(None);
        info!("Pingora connection pool initialized (shared cross-worker)");
        Self {
            connector: Arc::new(connector),
        }
    }

    /// Send an HTTP request through the Pingora connection pool.
    ///
    /// Returns an axum Response, or an error status on failure.
    pub async fn send_request(
        &self,
        url: String,
        method: Method,
        headers: HeaderMap,
        body: Option<Bytes>,
    ) -> Response {
        // Parse URL into host:port for Pingora peer
        let peer = match parse_peer(&url) {
            Some(p) => p,
            None => {
                error!(url = %url, "Failed to parse upstream URL for Pingora pool");
                return (StatusCode::BAD_GATEWAY, "Invalid upstream URL").into_response();
            }
        };

        // Get a pooled connection (may be reused)
        let (mut session, reused) = match self.connector.get_http_session(&peer).await {
            Ok(s) => s,
            Err(e) => {
                error!(
                    url = %url,
                    error = %e,
                    "Pingora pool: failed to get HTTP session"
                );
                return (StatusCode::BAD_GATEWAY, "Failed to connect to upstream").into_response();
            }
        };

        debug!(
            url = %url,
            reused = reused,
            "Pingora pool: got HTTP session"
        );

        // Build the request header
        let path = extract_path(&url);
        let mut req_header =
            pingora_http::RequestHeader::build(method.as_str(), path.as_bytes(), None)
                .unwrap_or_else(|_| pingora_http::RequestHeader::build("GET", b"/", None).unwrap());

        // Copy headers into Pingora request
        for (name, value) in headers.iter() {
            if let Ok(v) = value.to_str() {
                let n = name.as_str().to_string();
                let val = v.to_string();
                req_header.append_header(n, val).ok();
            }
        }

        // Set Host header if not present
        if req_header.headers.get("host").is_none() {
            if let Some(host) = extract_host(&url) {
                req_header.insert_header("host", &host).ok();
            }
        }

        // Tag request with Pingora identifier
        req_header.insert_header("x-stoa-pool", "pingora").ok();

        // Write request header
        if let Err(e) = session.write_request_header(Box::new(req_header)).await {
            error!(error = %e, "Pingora: failed to write request header");
            return (StatusCode::BAD_GATEWAY, "Failed to send request").into_response();
        }

        // Write body if present
        if let Some(body_bytes) = body {
            if let Err(e) = session.write_request_body(body_bytes, true).await {
                error!(error = %e, "Pingora: failed to write request body");
                return (StatusCode::BAD_GATEWAY, "Failed to send body").into_response();
            }
        } else {
            if let Err(e) = session.finish_request_body().await {
                error!(error = %e, "Pingora: failed to finish request");
                return (StatusCode::BAD_GATEWAY, "Failed to finish request").into_response();
            }
        }

        // Read response header
        match session.read_response_header().await {
            Ok(_) => {}
            Err(e) => {
                error!(error = %e, "Pingora: failed to read response header");
                return (StatusCode::BAD_GATEWAY, "Failed to read response").into_response();
            }
        };

        // Extract status and headers from the session's response
        let resp = session.response_header().expect("response header read");
        let status_code = resp.status.as_u16();
        let status = StatusCode::from_u16(status_code).unwrap_or(StatusCode::BAD_GATEWAY);

        // Copy response headers
        let mut response_headers = HeaderMap::new();
        for (name, value) in resp.headers.iter() {
            if let (Ok(n), Ok(v)) = (
                axum::http::header::HeaderName::from_bytes(name.as_str().as_bytes()),
                HeaderValue::from_bytes(value.as_bytes()),
            ) {
                response_headers.insert(n, v);
            }
        }

        // Read response body
        let mut body_parts = Vec::new();
        loop {
            match session.read_response_body().await {
                Ok(Some(chunk)) => body_parts.push(chunk),
                Ok(None) => break,
                Err(e) => {
                    error!(error = %e, "Pingora: failed to read response body");
                    break;
                }
            }
        }

        let body_bytes: Bytes = body_parts.concat().into();

        // Release connection back to pool for reuse
        self.connector
            .release_http_session(session, &peer, Some(Duration::from_secs(90)));

        // Build axum response
        let mut response = Response::new(Body::from(body_bytes));
        *response.status_mut() = status;
        *response.headers_mut() = response_headers;
        response
    }

    /// Check if the pool has a reusable connection for the given URL.
    pub async fn has_pooled_connection(&self, url: &str) -> bool {
        if let Some(peer) = parse_peer(url) {
            // Try to get a reused session
            match self.connector.get_http_session(&peer).await {
                Ok((session, reused)) => {
                    // Release it back immediately
                    self.connector.release_http_session(
                        session,
                        &peer,
                        Some(Duration::from_secs(90)),
                    );
                    reused
                }
                Err(_) => false,
            }
        } else {
            false
        }
    }
}

impl Default for PingoraPool {
    fn default() -> Self {
        Self::new()
    }
}

/// Parse a URL into a Pingora HttpPeer.
fn parse_peer(url: &str) -> Option<HttpPeer> {
    let url = url
        .strip_prefix("http://")
        .or_else(|| url.strip_prefix("https://"))?;
    let tls = url.starts_with("https://");

    let host_port = url.split('/').next()?;
    let (host, port) = if host_port.contains(':') {
        let parts: Vec<&str> = host_port.splitn(2, ':').collect();
        (parts[0], parts[1].parse::<u16>().ok()?)
    } else if tls {
        (host_port, 443)
    } else {
        (host_port, 80)
    };

    let addr = format!("{host}:{port}");
    Some(HttpPeer::new(addr, tls, String::new()))
}

/// Extract the path component from a URL.
fn extract_path(url: &str) -> String {
    let without_scheme = url
        .strip_prefix("http://")
        .or_else(|| url.strip_prefix("https://"))
        .unwrap_or(url);
    match without_scheme.find('/') {
        Some(idx) => without_scheme[idx..].to_string(),
        None => "/".to_string(),
    }
}

/// Extract host:port from a URL.
fn extract_host(url: &str) -> Option<String> {
    let without_scheme = url
        .strip_prefix("http://")
        .or_else(|| url.strip_prefix("https://"))
        .unwrap_or(url);
    Some(without_scheme.split('/').next()?.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_peer_http() {
        let peer = parse_peer("http://127.0.0.1:8080/api/v1");
        assert!(peer.is_some());
    }

    #[test]
    fn test_parse_peer_no_port() {
        let peer = parse_peer("http://127.0.0.1/api");
        assert!(peer.is_some());
    }

    #[test]
    fn test_parse_peer_invalid() {
        assert!(parse_peer("not-a-url").is_none());
    }

    #[test]
    fn test_extract_path() {
        assert_eq!(
            extract_path("http://backend:8080/api/v1/tools"),
            "/api/v1/tools"
        );
        assert_eq!(extract_path("http://backend:8080"), "/");
        assert_eq!(extract_path("https://api.example.com/v2"), "/v2");
    }

    #[test]
    fn test_extract_host() {
        assert_eq!(
            extract_host("http://backend:8080/api"),
            Some("backend:8080".to_string())
        );
        assert_eq!(
            extract_host("https://api.example.com/v2"),
            Some("api.example.com".to_string())
        );
    }
}
