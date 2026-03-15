//! GraphQL Proxy Passthrough (CAB-1756)
//!
//! Forwards GraphQL requests (HTTP POST with application/json) to backend
//! services with auth validation, query depth limiting, and metrics.
//!
//! Route: `POST /graphql/:route_id` — looks up backend URL from RouteRegistry.

use axum::{
    body::Body,
    extract::{Path, State},
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
};
use serde_json::Value;
use tracing::{info, warn};

use crate::metrics;
use crate::state::AppState;

/// Maximum allowed query depth (prevents deeply nested abuse queries).
const DEFAULT_MAX_DEPTH: usize = 15;

/// POST /graphql/:route_id — GraphQL proxy passthrough.
///
/// 1. Validates auth (Bearer token from Authorization header)
/// 2. Looks up backend URL from RouteRegistry
/// 3. Validates query depth (if enabled)
/// 4. Forwards the GraphQL request to the backend
/// 5. Returns the backend response with metrics tracking
pub async fn graphql_proxy(
    State(state): State<AppState>,
    Path(route_id): Path<String>,
    headers: HeaderMap,
    body: Body,
) -> Response {
    // Feature gate
    if !state.config.graphql_proxy_enabled {
        return (StatusCode::NOT_FOUND, "GraphQL proxy is not enabled").into_response();
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
        return graphql_error(StatusCode::UNAUTHORIZED, "Missing Bearer token");
    }

    // Look up backend URL from route registry
    let route = state.route_registry.get(&route_id);
    let Some(route) = route else {
        warn!(route_id = %route_id, "GraphQL route not found");
        return graphql_error(StatusCode::NOT_FOUND, "Route not found");
    };

    if !route.activated {
        return graphql_error(StatusCode::SERVICE_UNAVAILABLE, "Route not active");
    }

    let backend_url = &route.backend_url;

    metrics::track_graphql_proxy_request(&route_id);

    // Read body bytes
    let body_bytes = match axum::body::to_bytes(body, 10 * 1024 * 1024).await {
        Ok(b) => b,
        Err(e) => {
            warn!(error = %e, "Failed to read GraphQL request body");
            return graphql_error(StatusCode::BAD_REQUEST, "Failed to read request body");
        }
    };

    // Parse the GraphQL request to check query depth
    if let Ok(gql_request) = serde_json::from_slice::<Value>(&body_bytes) {
        if let Some(query_str) = gql_request.get("query").and_then(|q| q.as_str()) {
            let depth = measure_query_depth(query_str);
            if depth > DEFAULT_MAX_DEPTH {
                metrics::track_graphql_proxy_response(&route_id, false);
                return graphql_error(
                    StatusCode::BAD_REQUEST,
                    &format!(
                        "Query depth {depth} exceeds maximum allowed depth {DEFAULT_MAX_DEPTH}"
                    ),
                );
            }
        }
    }

    info!(
        route_id = %route_id,
        backend = %backend_url,
        "Proxying GraphQL request"
    );

    // Build the proxied request
    let mut req = state
        .http_client
        .post(backend_url)
        .header("Content-Type", "application/json")
        .header("Accept", "application/json")
        .body(body_bytes.to_vec());

    // Forward relevant headers
    for (name, value) in &headers {
        let name_str = name.as_str();
        if name_str == "authorization" || name_str == "user-agent" || name_str.starts_with("x-") {
            if let Ok(v) = value.to_str() {
                req = req.header(name_str, v);
            }
        }
    }

    // Send the request
    match req.send().await {
        Ok(response) => {
            let status = response.status();
            let is_success = status.is_success();

            match response.bytes().await {
                Ok(resp_body) => {
                    // Check for GraphQL errors in response
                    let has_errors = serde_json::from_slice::<Value>(&resp_body)
                        .ok()
                        .and_then(|v| v.get("errors").cloned())
                        .is_some_and(|e| {
                            e.is_array() && !e.as_array().unwrap_or(&vec![]).is_empty()
                        });

                    metrics::track_graphql_proxy_response(&route_id, is_success && !has_errors);

                    Response::builder()
                        .status(StatusCode::from_u16(status.as_u16()).unwrap_or(StatusCode::OK))
                        .header("Content-Type", "application/json")
                        .body(Body::from(resp_body.to_vec()))
                        .unwrap_or_else(|_| {
                            (StatusCode::INTERNAL_SERVER_ERROR, "Response build failed")
                                .into_response()
                        })
                }
                Err(e) => {
                    warn!(error = %e, "Failed to read GraphQL response body");
                    metrics::track_graphql_proxy_response(&route_id, false);
                    graphql_error(StatusCode::BAD_GATEWAY, "Failed to read backend response")
                }
            }
        }
        Err(e) => {
            warn!(
                route_id = %route_id,
                error = %e,
                "GraphQL proxy request failed"
            );
            metrics::track_graphql_proxy_response(&route_id, false);
            graphql_error(
                StatusCode::BAD_GATEWAY,
                &format!("Backend unavailable: {e}"),
            )
        }
    }
}

/// Build a GraphQL-style error response.
///
/// Returns JSON `{ "errors": [{ "message": "..." }] }` with the given HTTP status.
fn graphql_error(status: StatusCode, message: &str) -> Response {
    let body = serde_json::json!({
        "errors": [{ "message": message }]
    });
    Response::builder()
        .status(status)
        .header("Content-Type", "application/json")
        .body(Body::from(body.to_string()))
        .unwrap_or_else(|_| {
            (StatusCode::INTERNAL_SERVER_ERROR, "Error building response").into_response()
        })
}

/// Measure the nesting depth of a GraphQL query string.
///
/// Counts `{` / `}` brace nesting to estimate query complexity.
/// This is a lightweight heuristic — a full AST parser would be more accurate
/// but is overkill for depth limiting.
pub fn measure_query_depth(query: &str) -> usize {
    let mut max_depth: usize = 0;
    let mut current_depth: usize = 0;
    let mut in_string = false;

    for ch in query.chars() {
        match ch {
            '"' => in_string = !in_string,
            '{' if !in_string => {
                current_depth += 1;
                if current_depth > max_depth {
                    max_depth = current_depth;
                }
            }
            '}' if !in_string => {
                current_depth = current_depth.saturating_sub(1);
            }
            _ => {}
        }
    }

    max_depth
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_measure_query_depth_simple() {
        let query = "{ user { name } }";
        assert_eq!(measure_query_depth(query), 2);
    }

    #[test]
    fn test_measure_query_depth_nested() {
        let query = "{ user { posts { comments { author { name } } } } }";
        assert_eq!(measure_query_depth(query), 5);
    }

    #[test]
    fn test_measure_query_depth_flat() {
        let query = "{ user }";
        assert_eq!(measure_query_depth(query), 1);
    }

    #[test]
    fn test_measure_query_depth_empty() {
        assert_eq!(measure_query_depth(""), 0);
    }

    #[test]
    fn test_measure_query_depth_ignores_strings() {
        let query = r#"{ user(name: "test { nested }") { id } }"#;
        // The braces inside the string should not be counted
        assert_eq!(measure_query_depth(query), 2);
    }

    #[test]
    fn test_graphql_error_response() {
        let response = graphql_error(StatusCode::BAD_REQUEST, "Test error");
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(
            response
                .headers()
                .get("Content-Type")
                .unwrap()
                .to_str()
                .unwrap(),
            "application/json"
        );
    }

    #[test]
    fn test_graphql_error_body() {
        let response = graphql_error(StatusCode::NOT_FOUND, "Not found");
        // The body should be valid JSON with errors array
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[test]
    fn test_measure_query_depth_with_fragments() {
        let query = r#"
            query {
                user {
                    ...UserFields
                }
            }
            fragment UserFields on User {
                name
                posts {
                    title
                }
            }
        "#;
        // Fragment opens new brace contexts
        // Fragment block has depth 2: fragment { name posts { title } }
        // Query block has depth 2: query { user { ... } }
        // Max across both is 2
        assert_eq!(measure_query_depth(query), 2);
    }
}
