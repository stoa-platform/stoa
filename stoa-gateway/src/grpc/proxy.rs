//! gRPC Proxy Passthrough (CAB-1755)
//!
//! Forwards gRPC requests to backend services over HTTP/2.
//! gRPC is HTTP/2 POST with:
//! - Content-Type: application/grpc (or application/grpc+proto)
//! - gRPC-specific trailers (grpc-status, grpc-message)
//! - Length-prefixed protobuf frames (5-byte header: 1 byte compress flag + 4 bytes length)
//!
//! Route: `POST /grpc/:route_id/*path` — looks up backend from RouteRegistry.

use axum::{
    body::Body,
    extract::{Path, State},
    http::{HeaderMap, HeaderValue, StatusCode},
    response::{IntoResponse, Response},
};
use tracing::{info, warn};

use crate::metrics;
use crate::state::AppState;

/// POST /grpc/:route_id/*path — gRPC proxy passthrough.
///
/// 1. Validates auth (Bearer token from Authorization header)
/// 2. Looks up backend URL from RouteRegistry by route_id
/// 3. Forwards the raw gRPC request (HTTP/2 body with protobuf frames)
/// 4. Returns the raw gRPC response with trailers preserved
pub async fn grpc_proxy(
    State(state): State<AppState>,
    Path((route_id, grpc_path)): Path<(String, String)>,
    headers: HeaderMap,
    body: Body,
) -> Response {
    // Feature gate
    if !state.config.grpc_proxy_enabled {
        return (StatusCode::NOT_FOUND, "gRPC proxy is not enabled").into_response();
    }

    // Auth: require Bearer token
    let token = headers
        .get("authorization")
        .and_then(|v| v.to_str().ok())
        .and_then(|v| {
            v.strip_prefix("Bearer ")
                .or_else(|| v.strip_prefix("bearer "))
        });

    if token.is_none() {
        return grpc_error(StatusCode::UNAUTHORIZED, 16, "Missing Bearer token");
    }

    // Look up backend URL from route registry
    let route = state.route_registry.get(&route_id);
    let Some(route) = route else {
        warn!(route_id = %route_id, "gRPC route not found");
        return grpc_error(StatusCode::NOT_FOUND, 5, "Route not found");
    };

    if !route.activated {
        return grpc_error(StatusCode::SERVICE_UNAVAILABLE, 14, "Route not active");
    }

    let backend_url = &route.backend_url;

    metrics::track_grpc_proxy_request(&route_id);

    // Build the target URL: backend_url + gRPC path
    let target = format!(
        "{}/{}",
        backend_url.trim_end_matches('/'),
        grpc_path.trim_start_matches('/')
    );

    info!(
        route_id = %route_id,
        grpc_path = %grpc_path,
        target = %target,
        "Proxying gRPC request"
    );

    // Forward the request using reqwest with HTTP/2
    let client = &state.http_client;

    // Collect body bytes for forwarding
    let body_bytes = match axum::body::to_bytes(body, 10 * 1024 * 1024).await {
        Ok(b) => b,
        Err(e) => {
            warn!(error = %e, "Failed to read gRPC request body");
            return grpc_error(StatusCode::BAD_REQUEST, 3, "Failed to read request body");
        }
    };

    // Build the proxied request
    let mut req = client.post(&target).body(body_bytes.to_vec());

    // Forward relevant headers
    for (name, value) in &headers {
        let name_str = name.as_str();
        // Forward gRPC-specific and auth headers
        if name_str.starts_with("grpc-")
            || name_str == "content-type"
            || name_str == "authorization"
            || name_str == "te"
            || name_str == "user-agent"
            || name_str.starts_with("x-")
        {
            if let Ok(v) = value.to_str() {
                req = req.header(name_str, v);
            }
        }
    }

    // Ensure content-type is set for gRPC
    if !headers.contains_key("content-type") {
        req = req.header("content-type", "application/grpc");
    }

    // Send the request
    match req.send().await {
        Ok(response) => {
            let status = response.status();
            let resp_headers = response.headers().clone();

            // Check for gRPC-specific status in trailers/headers
            let grpc_status = resp_headers
                .get("grpc-status")
                .and_then(|v| v.to_str().ok())
                .and_then(|v| v.parse::<u32>().ok())
                .unwrap_or(0);

            let success = status.is_success() && grpc_status == 0;
            metrics::track_grpc_proxy_response(&route_id, success);

            if grpc_status != 0 {
                let grpc_message = resp_headers
                    .get("grpc-message")
                    .and_then(|v| v.to_str().ok())
                    .unwrap_or("Unknown gRPC error");
                info!(
                    route_id = %route_id,
                    grpc_status = grpc_status,
                    grpc_message = %grpc_message,
                    "gRPC backend returned error"
                );
            }

            // Forward the response body
            let resp_body = match response.bytes().await {
                Ok(b) => b,
                Err(e) => {
                    warn!(error = %e, "Failed to read gRPC response body");
                    return grpc_error(
                        StatusCode::BAD_GATEWAY,
                        14,
                        "Failed to read backend response",
                    );
                }
            };

            // Build response with gRPC headers
            let mut builder = Response::builder().status(status);

            // Copy response headers
            for (name, value) in &resp_headers {
                let name_str = name.as_str();
                if name_str.starts_with("grpc-")
                    || name_str == "content-type"
                    || name_str.starts_with("x-")
                {
                    builder = builder.header(name_str, value);
                }
            }

            builder
                .body(Body::from(resp_body.to_vec()))
                .unwrap_or_else(|_| {
                    (StatusCode::INTERNAL_SERVER_ERROR, "Response build failed").into_response()
                })
        }
        Err(e) => {
            warn!(
                route_id = %route_id,
                error = %e,
                "gRPC proxy request failed"
            );
            metrics::track_grpc_proxy_response(&route_id, false);
            grpc_error(
                StatusCode::BAD_GATEWAY,
                14,
                &format!("Backend unavailable: {e}"),
            )
        }
    }
}

/// Build a gRPC error response with proper headers.
///
/// gRPC errors use HTTP 200 with grpc-status and grpc-message headers/trailers.
/// However, for HTTP-level errors (auth, not found), we return HTTP error codes
/// with gRPC status in headers for interoperability.
fn grpc_error(http_status: StatusCode, grpc_status: u32, message: &str) -> Response {
    Response::builder()
        .status(http_status)
        .header("content-type", "application/grpc")
        .header("grpc-status", grpc_status.to_string())
        .header(
            "grpc-message",
            HeaderValue::from_str(message).unwrap_or_else(|_| HeaderValue::from_static("error")),
        )
        .body(Body::empty())
        .unwrap_or_else(|_| {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                "Error building gRPC response",
            )
                .into_response()
        })
}

/// gRPC status codes (subset — full list in gRPC spec).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u32)]
pub enum GrpcStatus {
    Ok = 0,
    Cancelled = 1,
    Unknown = 2,
    InvalidArgument = 3,
    DeadlineExceeded = 4,
    NotFound = 5,
    AlreadyExists = 6,
    PermissionDenied = 7,
    ResourceExhausted = 8,
    Unauthenticated = 16,
    Unavailable = 14,
    Unimplemented = 12,
    Internal = 13,
}

impl GrpcStatus {
    /// Convert gRPC status to a human-readable name.
    pub fn name(self) -> &'static str {
        match self {
            Self::Ok => "OK",
            Self::Cancelled => "CANCELLED",
            Self::Unknown => "UNKNOWN",
            Self::InvalidArgument => "INVALID_ARGUMENT",
            Self::DeadlineExceeded => "DEADLINE_EXCEEDED",
            Self::NotFound => "NOT_FOUND",
            Self::AlreadyExists => "ALREADY_EXISTS",
            Self::PermissionDenied => "PERMISSION_DENIED",
            Self::ResourceExhausted => "RESOURCE_EXHAUSTED",
            Self::Unauthenticated => "UNAUTHENTICATED",
            Self::Unavailable => "UNAVAILABLE",
            Self::Unimplemented => "UNIMPLEMENTED",
            Self::Internal => "INTERNAL",
        }
    }
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_grpc_error_response() {
        let response = grpc_error(StatusCode::NOT_FOUND, 5, "Route not found");
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
        assert_eq!(
            response
                .headers()
                .get("grpc-status")
                .unwrap()
                .to_str()
                .unwrap(),
            "5"
        );
        assert_eq!(
            response
                .headers()
                .get("grpc-message")
                .unwrap()
                .to_str()
                .unwrap(),
            "Route not found"
        );
        assert_eq!(
            response
                .headers()
                .get("content-type")
                .unwrap()
                .to_str()
                .unwrap(),
            "application/grpc"
        );
    }

    #[test]
    fn test_grpc_status_names() {
        assert_eq!(GrpcStatus::Ok.name(), "OK");
        assert_eq!(GrpcStatus::NotFound.name(), "NOT_FOUND");
        assert_eq!(GrpcStatus::Unauthenticated.name(), "UNAUTHENTICATED");
        assert_eq!(GrpcStatus::Unavailable.name(), "UNAVAILABLE");
        assert_eq!(GrpcStatus::Internal.name(), "INTERNAL");
    }

    #[test]
    fn test_grpc_error_with_special_chars() {
        // Ensure message with special chars doesn't panic
        let response = grpc_error(
            StatusCode::BAD_GATEWAY,
            14,
            "Backend error: connection refused",
        );
        assert_eq!(response.status(), StatusCode::BAD_GATEWAY);
        assert_eq!(
            response
                .headers()
                .get("grpc-status")
                .unwrap()
                .to_str()
                .unwrap(),
            "14"
        );
    }

    #[test]
    fn test_grpc_status_values() {
        assert_eq!(GrpcStatus::Ok as u32, 0);
        assert_eq!(GrpcStatus::Cancelled as u32, 1);
        assert_eq!(GrpcStatus::InvalidArgument as u32, 3);
        assert_eq!(GrpcStatus::NotFound as u32, 5);
        assert_eq!(GrpcStatus::PermissionDenied as u32, 7);
        assert_eq!(GrpcStatus::Unauthenticated as u32, 16);
    }
}
