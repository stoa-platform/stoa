use prometheus::{
    CounterVec, Encoder, GaugeVec, Histogram, HistogramOpts, HistogramVec, Opts, Registry,
    TextEncoder,
};
use std::sync::Arc;
use std::time::Duration;

/// Prometheus metrics for gateway comparison.
///
/// Thread-safe metrics registry for tracking request latency, throughput,
/// health status, and failover events.
#[derive(Clone)]
pub struct Metrics {
    registry: Arc<Registry>,

    /// Request duration histogram: gateway_request_duration_seconds{gateway, endpoint, status}
    request_duration: HistogramVec,

    /// Request counter: gateway_request_total{gateway, endpoint, status}
    request_total: CounterVec,

    /// Health status gauge: gateway_health_status{gateway} (1=up, 0=down)
    health_status: GaugeVec,

    /// Failover counter: gateway_failover_total{from, to}
    failover_total: CounterVec,

    /// Shadow latency diff: gateway_shadow_latency_diff_ms (rust - webmethods)
    /// Used by P2 when shadow results are correlated back to primary.
    #[allow(dead_code)]
    shadow_latency_diff: Histogram,
}

impl Metrics {
    /// Create a new metrics registry with all gauges initialized.
    pub fn new() -> Self {
        let registry = Registry::new();

        // Request duration: buckets from 1ms to 10s (exponential)
        let request_duration = HistogramVec::new(
            HistogramOpts::new(
                "gateway_request_duration_seconds",
                "Request duration in seconds",
            )
            .buckets(vec![
                0.001, 0.002, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0,
            ]),
            &["gateway", "endpoint", "status"],
        )
        .expect("failed to create request_duration histogram");

        let request_total = CounterVec::new(
            Opts::new("gateway_request_total", "Total number of requests"),
            &["gateway", "endpoint", "status"],
        )
        .expect("failed to create request_total counter");

        let health_status = GaugeVec::new(
            Opts::new(
                "gateway_health_status",
                "Gateway health status (1=up, 0=down)",
            ),
            &["gateway"],
        )
        .expect("failed to create health_status gauge");

        let failover_total = CounterVec::new(
            Opts::new("gateway_failover_total", "Total failover events"),
            &["from", "to"],
        )
        .expect("failed to create failover_total counter");

        // Latency diff buckets: -100ms to +100ms
        let shadow_latency_diff = Histogram::with_opts(
            HistogramOpts::new(
                "gateway_shadow_latency_diff_ms",
                "Latency difference (rust - webmethods) in milliseconds",
            )
            .buckets(vec![
                -100.0, -50.0, -20.0, -10.0, -5.0, 0.0, 5.0, 10.0, 20.0, 50.0, 100.0,
            ]),
        )
        .expect("failed to create shadow_latency_diff histogram");

        // Register all metrics
        registry
            .register(Box::new(request_duration.clone()))
            .expect("failed to register request_duration");
        registry
            .register(Box::new(request_total.clone()))
            .expect("failed to register request_total");
        registry
            .register(Box::new(health_status.clone()))
            .expect("failed to register health_status");
        registry
            .register(Box::new(failover_total.clone()))
            .expect("failed to register failover_total");
        registry
            .register(Box::new(shadow_latency_diff.clone()))
            .expect("failed to register shadow_latency_diff");

        // Initialize health status for both gateways
        health_status.with_label_values(&["webmethods"]).set(1.0);
        health_status.with_label_values(&["rust"]).set(1.0);

        Self {
            registry: Arc::new(registry),
            request_duration,
            request_total,
            health_status,
            failover_total,
            shadow_latency_diff,
        }
    }

    /// Record a primary (webMethods) request.
    pub fn record_primary_request(&self, gateway: &str, duration: Duration, status: u16) {
        let secs = duration.as_secs_f64();
        let status_str = status.to_string();

        self.request_duration
            .with_label_values(&[gateway, "primary", &status_str])
            .observe(secs);
        self.request_total
            .with_label_values(&[gateway, "primary", &status_str])
            .inc();
    }

    /// Record a shadow (Rust) request.
    pub fn record_shadow_request(&self, gateway: &str, duration: Duration, status: u16) {
        let secs = duration.as_secs_f64();
        let status_str = status.to_string();

        self.request_duration
            .with_label_values(&[gateway, "shadow", &status_str])
            .observe(secs);
        self.request_total
            .with_label_values(&[gateway, "shadow", &status_str])
            .inc();
    }

    /// Record latency difference between shadow and primary.
    ///
    /// Positive = Rust is slower, Negative = Rust is faster
    /// Note: Used by P2 when shadow results are correlated back to primary.
    #[allow(dead_code)]
    pub fn record_latency_diff(&self, rust_ms: f64, webmethods_ms: f64) {
        let diff = rust_ms - webmethods_ms;
        self.shadow_latency_diff.observe(diff);
    }

    /// Record a failover event.
    pub fn record_failover(&self, from: &str, to: &str) {
        self.failover_total.with_label_values(&[from, to]).inc();
    }

    /// Set gateway health status.
    pub fn set_health(&self, gateway: &str, healthy: bool) {
        self.health_status
            .with_label_values(&[gateway])
            .set(if healthy { 1.0 } else { 0.0 });
    }

    /// Encode metrics in Prometheus text format.
    pub fn encode(&self) -> String {
        let encoder = TextEncoder::new();
        let metric_families = self.registry.gather();
        let mut buffer = Vec::new();
        encoder
            .encode(&metric_families, &mut buffer)
            .expect("failed to encode metrics");
        String::from_utf8(buffer).expect("metrics are not valid UTF-8")
    }
}

impl Default for Metrics {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_metrics_creation() {
        let metrics = Metrics::new();
        assert!(!metrics.encode().is_empty());
    }

    #[test]
    fn test_record_request() {
        let metrics = Metrics::new();
        metrics.record_primary_request("webmethods", Duration::from_millis(50), 200);
        metrics.record_shadow_request("rust", Duration::from_millis(5), 200);

        let output = metrics.encode();
        assert!(output.contains("gateway_request_total"));
        assert!(output.contains("gateway_request_duration_seconds"));
    }

    #[test]
    fn test_health_status() {
        let metrics = Metrics::new();
        metrics.set_health("webmethods", false);

        let output = metrics.encode();
        assert!(output.contains("gateway_health_status"));
    }

    #[test]
    fn test_failover() {
        let metrics = Metrics::new();
        metrics.record_failover("webmethods", "rust");

        let output = metrics.encode();
        assert!(output.contains("gateway_failover_total"));
    }
}
