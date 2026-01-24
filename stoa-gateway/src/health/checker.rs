use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::broadcast;

/// Health checker for webMethods gateway.
///
/// Periodically checks the health of the webMethods gateway and tracks
/// failover events. Supports graceful shutdown via broadcast channel.
pub struct HealthChecker {
    webmethods_url: String,
    check_interval: Duration,
    check_timeout: Duration,
    current_state: Arc<AtomicBool>,
    failover_count: Arc<AtomicU64>,
    client: reqwest::Client,
}

impl HealthChecker {
    /// Create a new health checker.
    ///
    /// # Arguments
    /// * `webmethods_url` - Base URL of the webMethods gateway
    /// * `check_interval` - How often to check health (default: 5s)
    /// * `check_timeout` - Timeout for health check requests (default: 2s)
    pub fn new(webmethods_url: String, check_interval: Duration, check_timeout: Duration) -> Self {
        let client = reqwest::Client::builder()
            .timeout(check_timeout)
            .build()
            .expect("Failed to create HTTP client");

        Self {
            webmethods_url,
            check_interval,
            check_timeout,
            current_state: Arc::new(AtomicBool::new(true)), // Assume healthy initially
            failover_count: Arc::new(AtomicU64::new(0)),
            client,
        }
    }

    /// Run the health check loop.
    ///
    /// This method will run until a shutdown signal is received.
    /// It checks the webMethods health endpoint at regular intervals
    /// and logs failover/recovery events.
    pub async fn run(&self, mut shutdown: broadcast::Receiver<()>) {
        let mut interval = tokio::time::interval(self.check_interval);
        // Don't burst on startup
        interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);

        tracing::info!(
            url = %self.webmethods_url,
            interval_secs = self.check_interval.as_secs(),
            timeout_secs = self.check_timeout.as_secs(),
            "starting health checker"
        );

        loop {
            tokio::select! {
                _ = interval.tick() => {
                    let is_healthy = self.check_webmethods().await;
                    let was_healthy = self.current_state.swap(is_healthy, Ordering::SeqCst);

                    if was_healthy && !is_healthy {
                        let count = self.failover_count.fetch_add(1, Ordering::Relaxed) + 1;
                        tracing::warn!(
                            event = "failover",
                            from = "webmethods",
                            to = "rust",
                            total_failovers = count,
                            "webMethods became unhealthy, failover activated"
                        );
                    } else if !was_healthy && is_healthy {
                        tracing::info!(
                            event = "recovery",
                            from = "rust",
                            to = "webmethods",
                            "webMethods recovered, routing restored"
                        );
                    }
                }
                _ = shutdown.recv() => {
                    tracing::info!("health checker received shutdown signal");
                    break;
                }
            }
        }

        tracing::info!("health checker stopped");
    }

    /// Check if webMethods is currently healthy.
    async fn check_webmethods(&self) -> bool {
        let health_url = format!("{}/health", self.webmethods_url);

        match self.client.get(&health_url).send().await {
            Ok(resp) => {
                let status = resp.status();
                if status.is_success() {
                    tracing::trace!(status = %status, "webmethods health check passed");
                    true
                } else {
                    tracing::warn!(
                        status = %status,
                        url = %health_url,
                        "webmethods health check returned non-success status"
                    );
                    false
                }
            }
            Err(e) => {
                tracing::warn!(
                    error = %e,
                    url = %health_url,
                    "webmethods health check failed"
                );
                false
            }
        }
    }

    /// Check if webMethods is currently considered healthy.
    /// Used by non-shadow mode deployments (P0 failover router).
    #[allow(dead_code)]
    pub fn is_healthy(&self) -> bool {
        self.current_state.load(Ordering::SeqCst)
    }

    /// Get the total number of failover events.
    /// Useful for debugging and testing.
    #[allow(dead_code)]
    pub fn failover_count(&self) -> u64 {
        self.failover_count.load(Ordering::Relaxed)
    }

    /// Get an Arc clone of the health state for sharing with handlers.
    pub fn state(&self) -> Arc<AtomicBool> {
        Arc::clone(&self.current_state)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_health_checker_initial_state() {
        let checker = HealthChecker::new(
            "http://localhost:9999".to_string(),
            Duration::from_secs(5),
            Duration::from_secs(2),
        );

        // Initially assumes healthy
        assert!(checker.is_healthy());
        assert_eq!(checker.failover_count(), 0);
    }
}
