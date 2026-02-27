//! Proxy Hardening — Circuit Breaker + Retry for OAuth & CP Calls (CAB-1542 Phase 2)
//!
//! Wraps Keycloak OAuth and Control Plane calls with:
//! - Per-upstream circuit breaker (reuses existing CircuitBreakerRegistry)
//! - Retry with exponential backoff on transient errors (5xx, timeouts)
//! - Via header injection for hop detection
//!
//! Design: thin wrappers that compose existing resilience primitives.
//! No new state machines — leverages circuit_breaker.rs + retry.rs.

use std::sync::Arc;

use axum::http::StatusCode;
use tracing::{debug, warn};

use crate::resilience::{
    retry_with_backoff_if, CircuitBreaker, CircuitBreakerRegistry, RetryConfig,
};

/// Default circuit breaker key for Keycloak OAuth calls.
const CB_KEY_KEYCLOAK: &str = "keycloak-oauth";

/// Default circuit breaker key for Control Plane API calls.
const CB_KEY_CONTROL_PLANE: &str = "control-plane-api";

/// Retry configuration tuned for OAuth/identity provider calls.
/// More conservative than generic retries: fewer attempts, longer backoff.
pub fn oauth_retry_config() -> RetryConfig {
    RetryConfig {
        max_attempts: 2,
        initial_delay: std::time::Duration::from_millis(200),
        max_delay: std::time::Duration::from_secs(2),
        multiplier: 2.0,
        jitter: 0.15,
    }
}

/// Retry configuration for Control Plane API calls.
/// Tool discovery/calls are less latency-sensitive, allow more retries.
pub fn cp_retry_config() -> RetryConfig {
    RetryConfig {
        max_attempts: 3,
        initial_delay: std::time::Duration::from_millis(100),
        max_delay: std::time::Duration::from_secs(3),
        multiplier: 2.0,
        jitter: 0.1,
    }
}

/// Check if an HTTP error is transient and worth retrying.
/// Retries on: connection errors, timeouts, 502, 503, 504.
/// Does NOT retry on: 400, 401, 403, 404, 409, 422 (client errors).
pub fn is_transient_error(error: &str) -> bool {
    let lower = error.to_lowercase();
    // Connection/timeout errors from reqwest
    if lower.contains("connection")
        || lower.contains("timeout")
        || lower.contains("timed out")
        || lower.contains("connect")
        || lower.contains("dns")
        || lower.contains("reset by peer")
    {
        return true;
    }
    // HTTP 5xx server errors (from our formatted error strings: "... returned 502: ...")
    if lower.contains("returned 502")
        || lower.contains("returned 503")
        || lower.contains("returned 504")
        || lower.contains("error 502")
        || lower.contains("error 503")
        || lower.contains("error 504")
    {
        return true;
    }
    false
}

/// Execute an OAuth proxy call through circuit breaker + retry.
///
/// Returns:
/// - `Ok(response)` on success
/// - `Err(status, message)` on failure (includes CB-open fast-fail)
pub async fn with_keycloak_resilience<F, Fut>(
    cb_registry: &Arc<CircuitBreakerRegistry>,
    operation_name: &str,
    operation: F,
) -> Result<reqwest::Response, (StatusCode, String)>
where
    F: Fn() -> Fut + Clone,
    Fut: std::future::Future<Output = Result<reqwest::Response, String>>,
{
    let cb = cb_registry.get_or_create(CB_KEY_KEYCLOAK);
    let retry_config = oauth_retry_config();

    with_resilience(&cb, &retry_config, operation_name, operation).await
}

/// Execute a Control Plane API call through circuit breaker + retry.
pub async fn with_cp_resilience<F, Fut>(
    cb_registry: &Arc<CircuitBreakerRegistry>,
    operation_name: &str,
    operation: F,
) -> Result<reqwest::Response, (StatusCode, String)>
where
    F: Fn() -> Fut + Clone,
    Fut: std::future::Future<Output = Result<reqwest::Response, String>>,
{
    let cb = cb_registry.get_or_create(CB_KEY_CONTROL_PLANE);
    let retry_config = cp_retry_config();

    with_resilience(&cb, &retry_config, operation_name, operation).await
}

/// Inner resilience wrapper: circuit breaker → retry → operation.
async fn with_resilience<F, Fut>(
    cb: &Arc<CircuitBreaker>,
    retry_config: &RetryConfig,
    operation_name: &str,
    operation: F,
) -> Result<reqwest::Response, (StatusCode, String)>
where
    F: Fn() -> Fut + Clone,
    Fut: std::future::Future<Output = Result<reqwest::Response, String>>,
{
    // Check circuit breaker before attempting
    if !cb.allow_request() {
        warn!(
            operation = %operation_name,
            "Circuit breaker OPEN — fast-failing"
        );
        return Err((
            StatusCode::SERVICE_UNAVAILABLE,
            format!(
                "Service temporarily unavailable (circuit open for {})",
                operation_name
            ),
        ));
    }

    // Retry with backoff on transient errors
    let op_name = operation_name.to_string();
    let op = operation.clone();
    let result = retry_with_backoff_if(
        retry_config,
        &op_name,
        || {
            let f = op.clone();
            async move { f().await }
        },
        |e: &String| is_transient_error(e),
    )
    .await;

    match result {
        Ok(response) => {
            let status = response.status();
            if status.is_server_error() {
                cb.record_failure();
                debug!(
                    operation = %operation_name,
                    status = status.as_u16(),
                    "Recorded failure in circuit breaker (server error)"
                );
            } else {
                cb.record_success();
            }
            Ok(response)
        }
        Err(e) => {
            cb.record_failure();
            warn!(
                operation = %operation_name,
                error = %e,
                "All retries exhausted — recorded failure in circuit breaker"
            );
            Err((StatusCode::BAD_GATEWAY, e))
        }
    }
}

/// Execute a Control Plane operation through circuit breaker + retry (generic version).
///
/// Unlike `with_cp_resilience` which works with `reqwest::Response`, this accepts
/// any operation returning `Result<T, String>`. Used by ToolProxyClient for
/// tool discovery and invocation.
pub async fn with_cp_resilience_generic<T, F, Fut>(
    cb_registry: &Arc<CircuitBreakerRegistry>,
    operation_name: &str,
    operation: F,
) -> Result<T, String>
where
    F: Fn() -> Fut + Clone,
    Fut: std::future::Future<Output = Result<T, String>>,
{
    let cb = cb_registry.get_or_create(CB_KEY_CONTROL_PLANE);
    let retry_config = cp_retry_config();

    // Check circuit breaker before attempting
    if !cb.allow_request() {
        warn!(
            operation = %operation_name,
            "Circuit breaker OPEN for CP — fast-failing"
        );
        return Err(format!(
            "Service temporarily unavailable (circuit open for {})",
            operation_name
        ));
    }

    // Retry with backoff on transient errors
    let op_name = operation_name.to_string();
    let op = operation.clone();
    let result = retry_with_backoff_if(
        &retry_config,
        &op_name,
        || {
            let f = op.clone();
            async move { f().await }
        },
        |e: &String| is_transient_error(e),
    )
    .await;

    match &result {
        Ok(_) => {
            cb.record_success();
        }
        Err(e) => {
            cb.record_failure();
            warn!(
                operation = %operation_name,
                error = %e,
                "CP operation failed — recorded failure in circuit breaker"
            );
        }
    }

    result
}

/// Get the circuit breaker key for a custom upstream (e.g., a specific MCP server URL).
pub fn upstream_cb_key(url: &str) -> String {
    // Extract host from URL for the CB key
    if let Ok(parsed) = reqwest::Url::parse(url) {
        if let Some(host) = parsed.host_str() {
            return format!("upstream:{}", host);
        }
    }
    format!("upstream:{}", url)
}

/// Build the Via header value for outgoing requests from this gateway.
/// Re-export from hop_detection for convenience.
pub use super::hop_detection::build_via_value;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_is_transient_connection_error() {
        assert!(is_transient_error("connection refused"));
        assert!(is_transient_error("Connection reset by peer"));
        assert!(is_transient_error("request timeout"));
        assert!(is_transient_error("DNS resolution failed"));
        assert!(is_transient_error("timed out waiting for response"));
    }

    #[test]
    fn test_is_transient_server_error() {
        assert!(is_transient_error("CP returned 502: bad gateway"));
        assert!(is_transient_error("Error 503: service unavailable"));
        assert!(is_transient_error("returned 504: gateway timeout"));
    }

    #[test]
    fn test_is_not_transient_client_error() {
        assert!(!is_transient_error("returned 401: unauthorized"));
        assert!(!is_transient_error("returned 403: forbidden"));
        assert!(!is_transient_error("returned 404: not found"));
        assert!(!is_transient_error("returned 422: unprocessable"));
        assert!(!is_transient_error("invalid json payload"));
    }

    #[test]
    fn test_upstream_cb_key_parses_url() {
        assert_eq!(
            upstream_cb_key("https://api.gostoa.dev/v1/tools"),
            "upstream:api.gostoa.dev"
        );
        assert_eq!(
            upstream_cb_key("http://localhost:8080/health"),
            "upstream:localhost"
        );
    }

    #[test]
    fn test_upstream_cb_key_fallback() {
        assert_eq!(upstream_cb_key("not-a-url"), "upstream:not-a-url");
    }

    #[test]
    fn test_oauth_retry_config() {
        let config = oauth_retry_config();
        assert_eq!(config.max_attempts, 2);
        assert!(config.initial_delay.as_millis() > 0);
    }

    #[test]
    fn test_cp_retry_config() {
        let config = cp_retry_config();
        assert_eq!(config.max_attempts, 3);
        assert!(config.initial_delay.as_millis() > 0);
    }

    #[tokio::test]
    async fn test_circuit_breaker_open_fast_fail() {
        use crate::resilience::{CircuitBreakerConfig, CircuitBreakerRegistry};
        use std::time::Duration;

        // Create a CB with very low threshold
        let config = CircuitBreakerConfig {
            failure_threshold: 1,
            reset_timeout: Duration::from_secs(60),
            ..Default::default()
        };
        let registry = Arc::new(CircuitBreakerRegistry::new(config));
        let cb = registry.get_or_create(CB_KEY_KEYCLOAK);

        // Trip the circuit breaker
        cb.record_failure();

        // Next call should fast-fail
        let result = with_keycloak_resilience(&registry, "test-op", || async {
            Ok(reqwest::Response::from(
                axum::http::Response::builder()
                    .status(200)
                    .body(reqwest::Body::from(""))
                    .unwrap(),
            ))
        })
        .await;

        assert!(result.is_err());
        let (status, msg) = result.unwrap_err();
        assert_eq!(status, StatusCode::SERVICE_UNAVAILABLE);
        assert!(msg.contains("circuit open"));
    }

    #[tokio::test]
    async fn test_successful_call_records_success() {
        use crate::resilience::{CircuitBreakerConfig, CircuitBreakerRegistry};

        let registry = Arc::new(CircuitBreakerRegistry::new(CircuitBreakerConfig::default()));

        let result = with_keycloak_resilience(&registry, "test-success", || async {
            Ok(reqwest::Response::from(
                axum::http::Response::builder()
                    .status(200)
                    .body(reqwest::Body::from("ok"))
                    .unwrap(),
            ))
        })
        .await;

        assert!(result.is_ok());
        let cb = registry.get_or_create(CB_KEY_KEYCLOAK);
        let stats = cb.stats();
        assert_eq!(stats.success_count, 1);
    }
}
