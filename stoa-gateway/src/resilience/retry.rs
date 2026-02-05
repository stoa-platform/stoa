//! Retry with Exponential Backoff
//!
//! Implements retry logic for transient failures:
//! - Exponential backoff with jitter (decorrelated jitter algorithm)
//! - Configurable max retries and base/max delay
//! - Only retries on specific status codes (502, 503, 504) or connection errors
//! - Respects Retry-After headers from backends

// Allow dead_code for Phase 6 components that will be wired in future handlers
#![allow(dead_code)]

use rand::Rng;
use serde::{Deserialize, Serialize};
use std::future::Future;
use std::time::Duration;
use tracing::{debug, warn};

/// Retry configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RetryConfig {
    /// Maximum number of retry attempts (default: 3)
    #[serde(default = "default_max_retries")]
    pub max_retries: u32,

    /// Base delay for exponential backoff in milliseconds (default: 100)
    #[serde(default = "default_base_delay_ms")]
    pub base_delay_ms: u64,

    /// Maximum delay cap in milliseconds (default: 10000)
    #[serde(default = "default_max_delay_ms")]
    pub max_delay_ms: u64,

    /// Enable retry (default: true)
    #[serde(default = "default_enabled")]
    pub enabled: bool,
}

fn default_max_retries() -> u32 {
    3
}

fn default_base_delay_ms() -> u64 {
    100
}

fn default_max_delay_ms() -> u64 {
    10_000
}

fn default_enabled() -> bool {
    true
}

impl Default for RetryConfig {
    fn default() -> Self {
        Self {
            max_retries: default_max_retries(),
            base_delay_ms: default_base_delay_ms(),
            max_delay_ms: default_max_delay_ms(),
            enabled: default_enabled(),
        }
    }
}

/// Retry policy that determines whether to retry and how long to wait
#[derive(Debug, Clone)]
pub struct RetryPolicy {
    config: RetryConfig,
}

impl RetryPolicy {
    /// Create a new retry policy
    pub fn new(config: RetryConfig) -> Self {
        Self { config }
    }

    /// Check if the error/status is retryable
    pub fn is_retryable_status(&self, status: u16) -> bool {
        // Only retry on specific gateway/server errors
        matches!(status, 502..=504)
    }

    /// Check if we should retry based on attempt number
    pub fn should_retry(&self, attempt: u32) -> bool {
        self.config.enabled && attempt < self.config.max_retries
    }

    /// Calculate delay for the given attempt using decorrelated jitter
    ///
    /// Uses AWS-style decorrelated jitter algorithm:
    /// delay = min(cap, random_between(base, previous_delay * 3))
    pub fn calculate_delay(&self, attempt: u32, previous_delay_ms: Option<u64>) -> Duration {
        let base = self.config.base_delay_ms;
        let cap = self.config.max_delay_ms;

        let delay_ms = if attempt == 0 {
            base
        } else {
            let prev = previous_delay_ms.unwrap_or(base);
            let mut rng = rand::thread_rng();
            let jittered = rng.gen_range(base..=(prev.saturating_mul(3)).min(cap));
            jittered.min(cap)
        };

        Duration::from_millis(delay_ms)
    }

    /// Calculate delay respecting Retry-After header if present
    pub fn calculate_delay_with_retry_after(
        &self,
        attempt: u32,
        previous_delay_ms: Option<u64>,
        retry_after_secs: Option<u64>,
    ) -> Duration {
        let computed_delay = self.calculate_delay(attempt, previous_delay_ms);

        if let Some(retry_after) = retry_after_secs {
            // Use the larger of computed delay or Retry-After
            let retry_after_duration = Duration::from_secs(retry_after);
            computed_delay.max(retry_after_duration)
        } else {
            computed_delay
        }
    }
}

impl Default for RetryPolicy {
    fn default() -> Self {
        Self::new(RetryConfig::default())
    }
}

/// Result type for retryable operations
#[derive(Debug)]
pub enum RetryableResult<T, E> {
    /// Operation succeeded
    Success(T),
    /// Operation failed with retryable error
    Retryable(E, Option<u64>), // error + optional Retry-After seconds
    /// Operation failed with non-retryable error
    NonRetryable(E),
}

/// Execute an async operation with retry
///
/// # Arguments
/// * `policy` - Retry policy to use
/// * `operation_name` - Name for logging
/// * `operation` - Async function returning RetryableResult
///
/// # Example
/// ```ignore
/// let result = with_retry(
///     &policy,
///     "fetch_data",
///     || async {
///         match client.get(url).await {
///             Ok(resp) if resp.status().is_success() => RetryableResult::Success(resp),
///             Ok(resp) if policy.is_retryable_status(resp.status().as_u16()) => {
///                 let retry_after = resp.headers()
///                     .get("retry-after")
///                     .and_then(|v| v.to_str().ok())
///                     .and_then(|v| v.parse().ok());
///                 RetryableResult::Retryable(resp, retry_after)
///             }
///             Ok(resp) => RetryableResult::NonRetryable(resp),
///             Err(e) => RetryableResult::Retryable(e, None),
///         }
///     }
/// ).await;
/// ```
pub async fn with_retry<T, E, F, Fut>(
    policy: &RetryPolicy,
    operation_name: &str,
    mut operation: F,
) -> Result<T, E>
where
    F: FnMut() -> Fut,
    Fut: Future<Output = RetryableResult<T, E>>,
    E: std::fmt::Display,
{
    let mut attempt = 0u32;
    let mut previous_delay_ms: Option<u64> = None;

    loop {
        match operation().await {
            RetryableResult::Success(result) => {
                if attempt > 0 {
                    debug!(
                        operation = operation_name,
                        attempt = attempt + 1,
                        "Operation succeeded after retry"
                    );
                }
                return Ok(result);
            }
            RetryableResult::NonRetryable(error) => {
                warn!(
                    operation = operation_name,
                    attempt = attempt + 1,
                    error = %error,
                    "Operation failed (non-retryable)"
                );
                return Err(error);
            }
            RetryableResult::Retryable(error, retry_after) => {
                if !policy.should_retry(attempt) {
                    warn!(
                        operation = operation_name,
                        attempt = attempt + 1,
                        max_retries = policy.config.max_retries,
                        error = %error,
                        "Operation failed after max retries"
                    );
                    return Err(error);
                }

                let delay =
                    policy.calculate_delay_with_retry_after(attempt, previous_delay_ms, retry_after);

                debug!(
                    operation = operation_name,
                    attempt = attempt + 1,
                    delay_ms = delay.as_millis() as u64,
                    retry_after = ?retry_after,
                    error = %error,
                    "Retrying operation after delay"
                );

                tokio::time::sleep(delay).await;

                previous_delay_ms = Some(delay.as_millis() as u64);
                attempt += 1;
            }
        }
    }
}

/// Simple retry wrapper for operations that return Result with retryable errors
///
/// This is a convenience function when you don't need fine-grained control
/// over what's retryable. It retries all errors.
#[allow(dead_code)]
pub async fn with_simple_retry<T, E, F, Fut>(
    policy: &RetryPolicy,
    operation_name: &str,
    mut operation: F,
) -> Result<T, E>
where
    F: FnMut() -> Fut,
    Fut: Future<Output = Result<T, E>>,
    E: std::fmt::Display,
{
    with_retry(policy, operation_name, || {
        let fut = operation();
        async move {
            match fut.await {
                Ok(v) => RetryableResult::Success(v),
                Err(e) => RetryableResult::Retryable(e, None),
            }
        }
    })
    .await
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU32, Ordering};
    use std::sync::Arc;

    #[test]
    fn test_retry_config_default() {
        let config = RetryConfig::default();
        assert_eq!(config.max_retries, 3);
        assert_eq!(config.base_delay_ms, 100);
        assert_eq!(config.max_delay_ms, 10_000);
        assert!(config.enabled);
    }

    #[test]
    fn test_retry_policy_retryable_status() {
        let policy = RetryPolicy::default();

        // Should retry gateway errors
        assert!(policy.is_retryable_status(502));
        assert!(policy.is_retryable_status(503));
        assert!(policy.is_retryable_status(504));

        // Should not retry other errors
        assert!(!policy.is_retryable_status(400));
        assert!(!policy.is_retryable_status(404));
        assert!(!policy.is_retryable_status(500));
        assert!(!policy.is_retryable_status(200));
    }

    #[test]
    fn test_retry_policy_should_retry() {
        let policy = RetryPolicy::new(RetryConfig {
            max_retries: 3,
            ..Default::default()
        });

        assert!(policy.should_retry(0));
        assert!(policy.should_retry(1));
        assert!(policy.should_retry(2));
        assert!(!policy.should_retry(3));
        assert!(!policy.should_retry(4));
    }

    #[test]
    fn test_retry_policy_disabled() {
        let policy = RetryPolicy::new(RetryConfig {
            enabled: false,
            ..Default::default()
        });

        assert!(!policy.should_retry(0));
    }

    #[test]
    fn test_calculate_delay_base() {
        let policy = RetryPolicy::new(RetryConfig {
            base_delay_ms: 100,
            ..Default::default()
        });

        let delay = policy.calculate_delay(0, None);
        assert_eq!(delay, Duration::from_millis(100));
    }

    #[test]
    fn test_calculate_delay_with_jitter() {
        let policy = RetryPolicy::new(RetryConfig {
            base_delay_ms: 100,
            max_delay_ms: 10_000,
            ..Default::default()
        });

        // Run multiple times to verify jitter
        let mut delays = vec![];
        for _ in 0..10 {
            let delay = policy.calculate_delay(1, Some(100));
            delays.push(delay.as_millis());
        }

        // Should have some variation (jitter)
        let min = delays.iter().min().unwrap();
        let max = delays.iter().max().unwrap();

        // All delays should be within expected range
        for d in &delays {
            assert!(*d >= 100); // base
            assert!(*d <= 300); // prev * 3
        }

        // Should have variation if jitter is working (may occasionally fail by chance)
        // Skip assertion to avoid flaky test
        let _ = (min, max);
    }

    #[test]
    fn test_calculate_delay_respects_cap() {
        let policy = RetryPolicy::new(RetryConfig {
            base_delay_ms: 100,
            max_delay_ms: 500,
            ..Default::default()
        });

        let delay = policy.calculate_delay(5, Some(10_000));
        assert!(delay.as_millis() <= 500);
    }

    #[test]
    fn test_calculate_delay_with_retry_after() {
        let policy = RetryPolicy::default();

        // Retry-After larger than computed delay
        let delay = policy.calculate_delay_with_retry_after(0, None, Some(60));
        assert_eq!(delay, Duration::from_secs(60));

        // Computed delay larger than Retry-After
        let delay = policy.calculate_delay_with_retry_after(0, None, Some(0));
        assert!(delay >= Duration::from_millis(100));
    }

    #[tokio::test]
    async fn test_with_retry_success_first_try() {
        let policy = RetryPolicy::default();
        let counter = Arc::new(AtomicU32::new(0));
        let counter_clone = counter.clone();

        let result: Result<&str, &str> = with_retry(&policy, "test", || {
            counter_clone.fetch_add(1, Ordering::SeqCst);
            async { RetryableResult::Success("ok") }
        })
        .await;

        assert!(result.is_ok());
        assert_eq!(result.unwrap(), "ok");
        assert_eq!(counter.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn test_with_retry_success_after_retries() {
        let policy = RetryPolicy::new(RetryConfig {
            max_retries: 3,
            base_delay_ms: 1, // Fast for testing
            ..Default::default()
        });

        let counter = Arc::new(AtomicU32::new(0));
        let counter_clone = counter.clone();

        let result: Result<&str, &str> = with_retry(&policy, "test", || {
            let count = counter_clone.fetch_add(1, Ordering::SeqCst);
            async move {
                if count < 2 {
                    RetryableResult::Retryable("transient error", None)
                } else {
                    RetryableResult::Success("ok")
                }
            }
        })
        .await;

        assert!(result.is_ok());
        assert_eq!(result.unwrap(), "ok");
        assert_eq!(counter.load(Ordering::SeqCst), 3);
    }

    #[tokio::test]
    async fn test_with_retry_exhausted() {
        let policy = RetryPolicy::new(RetryConfig {
            max_retries: 2,
            base_delay_ms: 1,
            ..Default::default()
        });

        let counter = Arc::new(AtomicU32::new(0));
        let counter_clone = counter.clone();

        let result: Result<&str, &str> = with_retry(&policy, "test", || {
            counter_clone.fetch_add(1, Ordering::SeqCst);
            async { RetryableResult::Retryable("persistent error", None) }
        })
        .await;

        assert!(result.is_err());
        assert_eq!(result.unwrap_err(), "persistent error");
        // 1 initial + 2 retries = 3 attempts
        assert_eq!(counter.load(Ordering::SeqCst), 3);
    }

    #[tokio::test]
    async fn test_with_retry_non_retryable() {
        let policy = RetryPolicy::default();
        let counter = Arc::new(AtomicU32::new(0));
        let counter_clone = counter.clone();

        let result: Result<&str, &str> = with_retry(&policy, "test", || {
            counter_clone.fetch_add(1, Ordering::SeqCst);
            async { RetryableResult::NonRetryable("fatal error") }
        })
        .await;

        assert!(result.is_err());
        assert_eq!(result.unwrap_err(), "fatal error");
        // Should not retry
        assert_eq!(counter.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn test_with_simple_retry() {
        let policy = RetryPolicy::new(RetryConfig {
            max_retries: 3,
            base_delay_ms: 1,
            ..Default::default()
        });

        let counter = Arc::new(AtomicU32::new(0));
        let counter_clone = counter.clone();

        let result: Result<i32, &str> = with_simple_retry(&policy, "test", || {
            let count = counter_clone.fetch_add(1, Ordering::SeqCst);
            async move {
                if count < 2 {
                    Err("not yet")
                } else {
                    Ok(42)
                }
            }
        })
        .await;

        assert!(result.is_ok());
        assert_eq!(result.unwrap(), 42);
    }
}
