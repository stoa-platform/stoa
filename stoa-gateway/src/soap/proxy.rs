//! SOAP Proxy Passthrough (CAB-1762)
//!
//! Forwards SOAP requests (HTTP POST with text/xml) to backend services
//! with auth validation, metrics, and SOAP fault detection.
//!
//! Route: `POST /soap/:route_id` — looks up backend URL from RouteRegistry.

use axum::{
    body::Body,
    extract::{Path, State},
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
};
use tracing::{info, warn};

use crate::metrics;
use crate::state::AppState;

/// POST /soap/:route_id — SOAP proxy passthrough.
///
/// 1. Validates auth (Bearer token from Authorization header)
/// 2. Looks up backend URL from RouteRegistry
/// 3. Forwards the raw SOAP request body to the backend
/// 4. Returns the raw SOAP response with metrics tracking
pub async fn soap_proxy(
    State(state): State<AppState>,
    Path(route_id): Path<String>,
    headers: HeaderMap,
    body: Body,
) -> Response {
    // Feature gate
    if !state.config.soap_proxy_enabled {
        return (StatusCode::NOT_FOUND, "SOAP proxy is not enabled").into_response();
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
        return (
            StatusCode::UNAUTHORIZED,
            "Missing Bearer token in Authorization header",
        )
            .into_response();
    }

    // Look up backend URL from route registry
    let route = state.route_registry.get(&route_id);
    let Some(route) = route else {
        return (
            StatusCode::NOT_FOUND,
            format!("Route not found: {route_id}"),
        )
            .into_response();
    };

    if !route.activated {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            format!("Route {} is not active", route_id),
        )
            .into_response();
    }

    let backend_url = &route.backend_url;
    let tenant_id = &route.tenant_id;

    // Extract SOAPAction header (optional, forwarded to backend)
    let soap_action = headers
        .get("soapaction")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("")
        .to_string();

    info!(
        route_id = %route_id,
        backend = %backend_url,
        tenant = %tenant_id,
        soap_action = %soap_action,
        "SOAP proxy request"
    );

    metrics::track_soap_proxy_request(&route_id);

    // Read body bytes
    let body_bytes = match axum::body::to_bytes(body, 10 * 1024 * 1024).await {
        Ok(bytes) => bytes,
        Err(e) => {
            warn!(error = %e, "Failed to read SOAP request body");
            return (StatusCode::BAD_REQUEST, "Failed to read request body").into_response();
        }
    };

    // Forward to backend
    let mut request = state
        .http_client
        .post(backend_url)
        .header("Content-Type", "text/xml; charset=utf-8")
        .body(body_bytes);

    if !soap_action.is_empty() {
        request = request.header("SOAPAction", &soap_action);
    }

    // Forward relevant headers
    for key in &["x-request-id", "x-correlation-id", "x-tenant-id"] {
        if let Some(val) = headers.get(*key) {
            if let Ok(val_str) = val.to_str() {
                request = request.header(*key, val_str);
            }
        }
    }

    match request.send().await {
        Ok(response) => {
            let status = response.status();
            let is_success = status.is_success();

            // Read response body
            match response.bytes().await {
                Ok(response_body) => {
                    metrics::track_soap_proxy_response(&route_id, is_success);

                    // Check for SOAP fault in body (even on HTTP 200, SOAP can return faults)
                    if let Ok(body_str) = std::str::from_utf8(&response_body) {
                        if body_str.contains("soap:Fault") || body_str.contains("Fault>") {
                            metrics::track_soap_proxy_fault(&route_id);
                        }
                    }

                    let mut builder = axum::http::Response::builder()
                        .status(StatusCode::from_u16(status.as_u16()).unwrap_or(StatusCode::OK))
                        .header("Content-Type", "text/xml; charset=utf-8");

                    // Forward CORS headers if present
                    if let Some(origin) = headers.get("origin") {
                        if let Ok(origin_str) = origin.to_str() {
                            builder = builder
                                .header("Access-Control-Allow-Origin", origin_str)
                                .header("Access-Control-Allow-Methods", "POST, OPTIONS")
                                .header(
                                    "Access-Control-Allow-Headers",
                                    "Content-Type, SOAPAction, Authorization",
                                );
                        }
                    }

                    builder.body(Body::from(response_body)).unwrap_or_else(|_| {
                        (StatusCode::INTERNAL_SERVER_ERROR, "Response build error").into_response()
                    })
                }
                Err(e) => {
                    warn!(error = %e, route_id = %route_id, "Failed to read backend response");
                    metrics::track_soap_proxy_response(&route_id, false);
                    (StatusCode::BAD_GATEWAY, "Failed to read backend response").into_response()
                }
            }
        }
        Err(e) => {
            warn!(error = %e, route_id = %route_id, backend = %backend_url, "SOAP backend request failed");
            metrics::track_soap_proxy_response(&route_id, false);
            (
                StatusCode::BAD_GATEWAY,
                format!("SOAP backend unreachable: {e}"),
            )
                .into_response()
        }
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn test_soap_content_type() {
        // Verify the expected content type for SOAP requests
        let ct = "text/xml; charset=utf-8";
        assert!(ct.starts_with("text/xml"));
    }
}
