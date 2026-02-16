//! Retry with Exponential Backoff
//!
//! Retries transient failures with configurable backoff strategy.
//!
//! Note: Infrastructure prepared for NativeTool integration (Phase 7).

// Retry infrastructure wired to dynamic proxy for transient error recovery (CAB-362)

use std::future::Future;
use std::time::Duration;
use tracing::{debug, warn};

/// Retry configuration
#[derive(Debug, Clone)]
pub struct RetryConfig {
    /// Maximum number of attempts (including initial)
    pub max_attempts: u32,
    /// Initial backoff delay
    pub initial_delay: Duration,
    /// Maximum backoff delay
    pub max_delay: Duration,
    /// Backoff multiplier (2.0 = double each time)
    pub multiplier: f64,
    /// Add random jitter (0.0 to 1.0)
    pub jitter: f64,
}

impl Default for RetryConfig {
    fn default() -> Self {
        Self {
            max_attempts: 3,
            initial_delay: Duration::from_millis(100),
            max_delay: Duration::from_secs(5),
            multiplier: 2.0,
            jitter: 0.1,
        }
    }
}

impl RetryConfig {
    /// Calculate delay for a given attempt (0-indexed)
    pub fn delay_for_attempt(&self, attempt: u32) -> Duration {
        if attempt == 0 {
            return Duration::ZERO;
        }

        let base_delay =
            self.initial_delay.as_secs_f64() * self.multiplier.powi(attempt as i32 - 1);
        let capped_delay = base_delay.min(self.max_delay.as_secs_f64());

        // Add jitter
        let jitter_amount = if self.jitter > 0.0 {
            let random = (std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .subsec_nanos() as f64)
                / 1_000_000_000.0;
            capped_delay * self.jitter * random
        } else {
            0.0
        };

        Duration::from_secs_f64(capped_delay + jitter_amount)
    }
}

/// Retry a fallible async operation with exponential backoff
///
/// Returns the result of the first successful attempt, or the last error.
pub async fn retry_with_backoff<F, Fut, T, E>(
    config: &RetryConfig,
    operation_name: &str,
    mut operation: F,
) -> Result<T, E>
where
    F: FnMut() -> Fut,
    Fut: Future<Output = Result<T, E>>,
    E: std::fmt::Display,
{
    let mut last_error: Option<E> = None;

    for attempt in 0..config.max_attempts {
        // Wait before retry (no wait for first attempt)
        if attempt > 0 {
            let delay = config.delay_for_attempt(attempt);
            debug!(
                operation = %operation_name,
                attempt = attempt + 1,
                max_attempts = config.max_attempts,
                delay_ms = delay.as_millis(),
                "Retrying after backoff"
            );
            tokio::time::sleep(delay).await;
        }

        match operation().await {
            Ok(result) => {
                if attempt > 0 {
                    debug!(
                        operation = %operation_name,
                        attempt = attempt + 1,
                        "Retry succeeded"
                    );
                }
                return Ok(result);
            }
            Err(e) => {
                if attempt + 1 < config.max_attempts {
                    warn!(
                        operation = %operation_name,
                        attempt = attempt + 1,
                        max_attempts = config.max_attempts,
                        error = %e,
                        "Operation failed, will retry"
                    );
                } else {
                    warn!(
                        operation = %operation_name,
                        attempt = attempt + 1,
                        error = %e,
                        "Operation failed, no more retries"
                    );
                }
                last_error = Some(e);
            }
        }
    }

    // Return the last error
    Err(last_error.expect("At least one attempt should have been made"))
}

/// Predicate-based retry: only retry if the error matches the predicate
pub async fn retry_with_backoff_if<F, Fut, T, E, P>(
    config: &RetryConfig,
    operation_name: &str,
    mut operation: F,
    should_retry: P,
) -> Result<T, E>
where
    F: FnMut() -> Fut,
    Fut: Future<Output = Result<T, E>>,
    E: std::fmt::Display,
    P: Fn(&E) -> bool,
{
    let mut last_error: Option<E> = None;

    for attempt in 0..config.max_attempts {
        if attempt > 0 {
            let delay = config.delay_for_attempt(attempt);
            debug!(
                operation = %operation_name,
                attempt = attempt + 1,
                delay_ms = delay.as_millis(),
                "Retrying after backoff"
            );
            tokio::time::sleep(delay).await;
        }

        match operation().await {
            Ok(result) => return Ok(result),
            Err(e) => {
                let can_retry = should_retry(&e);
                if can_retry && attempt + 1 < config.max_attempts {
                    warn!(
                        operation = %operation_name,
                        attempt = attempt + 1,
                        error = %e,
                        "Retryable error, will retry"
                    );
                    last_error = Some(e);
                } else {
                    if !can_retry {
                        debug!(
                            operation = %operation_name,
                            error = %e,
                            "Non-retryable error, failing immediately"
                        );
                    }
                    return Err(e);
                }
            }
        }
    }

    Err(last_error.expect("At least one attempt should have been made"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU32, Ordering};
    use std::sync::Arc;

    #[test]
    fn test_delay_calculation() {
        let config = RetryConfig {
            initial_delay: Duration::from_millis(100),
            max_delay: Duration::from_secs(10),
            multiplier: 2.0,
            jitter: 0.0, // No jitter for predictable tests
            ..Default::default()
        };

        assert_eq!(config.delay_for_attempt(0), Duration::ZERO);
        assert_eq!(config.delay_for_attempt(1), Duration::from_millis(100));
        assert_eq!(config.delay_for_attempt(2), Duration::from_millis(200));
        assert_eq!(config.delay_for_attempt(3), Duration::from_millis(400));
    }

    #[test]
    fn test_delay_capped_at_max() {
        let config = RetryConfig {
            initial_delay: Duration::from_secs(1),
            max_delay: Duration::from_secs(5),
            multiplier: 10.0,
            jitter: 0.0,
            ..Default::default()
        };

        // 1 * 10^5 = 100000 seconds, but capped at 5
        assert_eq!(config.delay_for_attempt(6), Duration::from_secs(5));
    }

    #[tokio::test]
    async fn test_retry_succeeds_first_try() {
        let config = RetryConfig::default();
        let attempts = Arc::new(AtomicU32::new(0));
        let attempts_clone = attempts.clone();

        let result: Result<i32, &str> = retry_with_backoff(&config, "test", || {
            let a = attempts_clone.clone();
            async move {
                a.fetch_add(1, Ordering::SeqCst);
                Ok(42)
            }
        })
        .await;

        assert_eq!(result.unwrap(), 42);
        assert_eq!(attempts.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn test_retry_succeeds_after_failures() {
        let config = RetryConfig {
            max_attempts: 3,
            initial_delay: Duration::from_millis(1),
            ..Default::default()
        };
        let attempts = Arc::new(AtomicU32::new(0));
        let attempts_clone = attempts.clone();

        let result: Result<i32, String> = retry_with_backoff(&config, "test", || {
            let a = attempts_clone.clone();
            async move {
                let count = a.fetch_add(1, Ordering::SeqCst);
                if count < 2 {
                    Err(format!("Attempt {} failed", count))
                } else {
                    Ok(42)
                }
            }
        })
        .await;

        assert_eq!(result.unwrap(), 42);
        assert_eq!(attempts.load(Ordering::SeqCst), 3);
    }

    #[tokio::test]
    async fn test_retry_exhausted() {
        let config = RetryConfig {
            max_attempts: 2,
            initial_delay: Duration::from_millis(1),
            ..Default::default()
        };
        let attempts = Arc::new(AtomicU32::new(0));
        let attempts_clone = attempts.clone();

        let result: Result<i32, &str> = retry_with_backoff(&config, "test", || {
            let a = attempts_clone.clone();
            async move {
                a.fetch_add(1, Ordering::SeqCst);
                Err("always fails")
            }
        })
        .await;

        assert_eq!(result.unwrap_err(), "always fails");
        assert_eq!(attempts.load(Ordering::SeqCst), 2);
    }

    #[tokio::test]
    async fn test_retry_with_predicate() {
        let config = RetryConfig {
            max_attempts: 5,
            initial_delay: Duration::from_millis(1),
            ..Default::default()
        };
        let attempts = Arc::new(AtomicU32::new(0));
        let attempts_clone = attempts.clone();

        // Only retry "transient" errors
        let result: Result<i32, String> = retry_with_backoff_if(
            &config,
            "test",
            || {
                let a = attempts_clone.clone();
                async move {
                    let count = a.fetch_add(1, Ordering::SeqCst);
                    if count == 0 {
                        Err("transient".to_string())
                    } else {
                        Err("permanent".to_string())
                    }
                }
            },
            |e: &String| e == "transient",
        )
        .await;

        // Should stop at "permanent" error without exhausting retries
        assert_eq!(result.unwrap_err(), "permanent");
        assert_eq!(attempts.load(Ordering::SeqCst), 2);
    }
}
