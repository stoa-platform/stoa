//! OpenTelemetry Integration
//!
//! Production-grade observability setup:
//! - OTLP gRPC export for distributed traces
//! - Prometheus metrics (scraped) + optional OTLP metrics export
//! - Structured JSON logs with trace_id correlation
//!
//! Configuration via environment:
//! - STOA_OTEL_ENDPOINT: OTLP collector URL (e.g., http://grafana-alloy:4317)
//! - STOA_OTEL_SERVICE_NAME: Service name (default: stoa-gateway)
//! - STOA_OTEL_METRICS_ENABLED: Enable OTLP metrics export (default: false)
//!
//! When STOA_OTEL_ENDPOINT is not set, telemetry is disabled and only
//! local tracing (via tracing-subscriber) is active.

// Allow dead_code for Phase 6 components that will be wired in future handlers
#![allow(dead_code)]

use serde::{Deserialize, Serialize};
use tracing::{info, warn};
use tracing_subscriber::{fmt, layer::SubscriberExt, util::SubscriberInitExt, EnvFilter};

/// Telemetry configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TelemetryConfig {
    /// OTLP endpoint URL (e.g., http://grafana-alloy:4317)
    /// When None, OpenTelemetry is disabled
    pub otel_endpoint: Option<String>,

    /// Service name for traces/metrics (default: stoa-gateway)
    #[serde(default = "default_service_name")]
    pub service_name: String,

    /// Service version (default: from Cargo.toml)
    #[serde(default = "default_service_version")]
    pub service_version: String,

    /// Enable OTLP metrics export (default: false)
    /// Prometheus scrape endpoint is always available
    #[serde(default)]
    pub otel_metrics_enabled: bool,

    /// OTLP export timeout in seconds (default: 10)
    #[serde(default = "default_export_timeout")]
    pub export_timeout_secs: u64,

    /// Trace sampling ratio 0.0-1.0 (default: 1.0 = all traces)
    #[serde(default = "default_sample_ratio")]
    pub sample_ratio: f64,
}

fn default_service_name() -> String {
    "stoa-gateway".to_string()
}

fn default_service_version() -> String {
    env!("CARGO_PKG_VERSION").to_string()
}

fn default_export_timeout() -> u64 {
    10
}

fn default_sample_ratio() -> f64 {
    1.0
}

impl Default for TelemetryConfig {
    fn default() -> Self {
        Self {
            otel_endpoint: None,
            service_name: default_service_name(),
            service_version: default_service_version(),
            otel_metrics_enabled: false,
            export_timeout_secs: default_export_timeout(),
            sample_ratio: default_sample_ratio(),
        }
    }
}

impl TelemetryConfig {
    /// Create config from environment
    pub fn from_env() -> Self {
        Self {
            otel_endpoint: std::env::var("STOA_OTEL_ENDPOINT").ok(),
            service_name: std::env::var("STOA_OTEL_SERVICE_NAME")
                .unwrap_or_else(|_| default_service_name()),
            service_version: std::env::var("STOA_OTEL_SERVICE_VERSION")
                .unwrap_or_else(|_| default_service_version()),
            otel_metrics_enabled: std::env::var("STOA_OTEL_METRICS_ENABLED")
                .map(|v| v == "true" || v == "1")
                .unwrap_or(false),
            export_timeout_secs: std::env::var("STOA_OTEL_EXPORT_TIMEOUT")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or_else(default_export_timeout),
            sample_ratio: std::env::var("STOA_OTEL_SAMPLE_RATIO")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or_else(default_sample_ratio),
        }
    }

    /// Check if OTel is enabled
    pub fn is_enabled(&self) -> bool {
        self.otel_endpoint.is_some()
    }
}

/// Telemetry guard - drop to flush pending spans
pub struct TelemetryGuard {
    #[allow(dead_code)]
    otel_enabled: bool,
}

impl Drop for TelemetryGuard {
    fn drop(&mut self) {
        // Shutdown is handled by shutdown_telemetry()
    }
}

/// Initialize telemetry (tracing + optional OpenTelemetry)
///
/// # Arguments
/// * `config` - Telemetry configuration
///
/// # Returns
/// TelemetryGuard that should be held until shutdown
///
/// # Example
/// ```ignore
/// let config = TelemetryConfig::from_env();
/// let _guard = init_telemetry(&config);
/// // ... application runs ...
/// shutdown_telemetry();
/// ```
pub fn init_telemetry(config: &TelemetryConfig) -> TelemetryGuard {
    let filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new("info,stoa_gateway=debug"));

    let fmt_layer = fmt::layer().json().with_target(true).with_thread_ids(true);

    if let Some(endpoint) = &config.otel_endpoint {
        // OTel is configured but we use a stub implementation
        // TODO: Re-enable once opentelemetry 0.27+ API stabilizes
        //
        // The opentelemetry_sdk 0.27 has breaking changes in:
        // - SdkTracerProvider::builder() API
        // - Resource::new() signature
        // - BatchSpanProcessor configuration
        //
        // For now, log that OTel is requested but use plain tracing
        warn!(
            endpoint = %endpoint,
            service = %config.service_name,
            "OpenTelemetry configured but not yet enabled - using local tracing only"
        );

        tracing_subscriber::registry()
            .with(filter)
            .with(fmt_layer)
            .init();

        info!(
            service = %config.service_name,
            version = %config.service_version,
            "Telemetry initialized (OTel stub - local tracing only)"
        );

        TelemetryGuard { otel_enabled: true }
    } else {
        // No OTel endpoint - plain tracing only
        tracing_subscriber::registry()
            .with(filter)
            .with(fmt_layer)
            .init();

        info!(
            service = %config.service_name,
            version = %config.service_version,
            "Telemetry initialized (local tracing only)"
        );

        TelemetryGuard { otel_enabled: false }
    }
}

/// Shutdown telemetry and flush pending spans
///
/// Should be called before application exit to ensure all spans are exported.
pub fn shutdown_telemetry() {
    // TODO: Re-enable once opentelemetry 0.27+ API stabilizes
    // opentelemetry::global::shutdown_tracer_provider();
    info!("Telemetry shutdown complete");
}

// ============================================================================
// OpenTelemetry Integration (Stubbed - Enable when API stabilizes)
// ============================================================================
//
// The following code is the intended implementation for OTel integration.
// It's commented out until opentelemetry 0.27+ API is stable.
//
// ```rust
// use opentelemetry::trace::TracerProvider;
// use opentelemetry_otlp::WithExportConfig;
// use opentelemetry_sdk::{
//     runtime,
//     trace::{BatchConfig, RandomIdGenerator, Sampler, TracerProvider as SdkTracerProvider},
//     Resource,
// };
// use opentelemetry::KeyValue;
// use tracing_opentelemetry::OpenTelemetryLayer;
//
// fn init_otel_tracer(config: &TelemetryConfig) -> SdkTracerProvider {
//     let endpoint = config.otel_endpoint.as_ref().expect("OTel endpoint required");
//
//     let exporter = opentelemetry_otlp::new_exporter()
//         .tonic()
//         .with_endpoint(endpoint)
//         .with_timeout(Duration::from_secs(config.export_timeout_secs));
//
//     let sampler = if config.sample_ratio >= 1.0 {
//         Sampler::AlwaysOn
//     } else if config.sample_ratio <= 0.0 {
//         Sampler::AlwaysOff
//     } else {
//         Sampler::TraceIdRatioBased(config.sample_ratio)
//     };
//
//     let resource = Resource::new(vec![
//         KeyValue::new("service.name", config.service_name.clone()),
//         KeyValue::new("service.version", config.service_version.clone()),
//     ]);
//
//     SdkTracerProvider::builder()
//         .with_batch_exporter(exporter, runtime::Tokio)
//         .with_config(
//             opentelemetry_sdk::trace::Config::default()
//                 .with_sampler(sampler)
//                 .with_id_generator(RandomIdGenerator::default())
//                 .with_resource(resource),
//         )
//         .build()
// }
// ```

/// Extract current trace_id from tracing span (for Prometheus exemplars)
///
/// Returns None when OTel is not enabled or no active span.
#[allow(dead_code)]
pub fn current_trace_id() -> Option<String> {
    // TODO: Re-enable once opentelemetry 0.27+ API stabilizes
    // use tracing_opentelemetry::OpenTelemetrySpanExt;
    // tracing::Span::current()
    //     .context()
    //     .span()
    //     .span_context()
    //     .trace_id()
    //     .to_string()
    //     .into()
    None
}

/// Create a child span for downstream calls
///
/// Useful for propagating trace context to backend services.
#[allow(dead_code)]
pub fn create_child_span(name: &str) -> tracing::Span {
    tracing::info_span!(
        target: "stoa_gateway",
        "downstream_call",
        otel.name = %name,
        otel.kind = "client"
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_telemetry_config_default() {
        let config = TelemetryConfig::default();
        assert!(config.otel_endpoint.is_none());
        assert_eq!(config.service_name, "stoa-gateway");
        assert!(!config.otel_metrics_enabled);
        assert_eq!(config.sample_ratio, 1.0);
    }

    #[test]
    fn test_telemetry_config_is_enabled() {
        let mut config = TelemetryConfig::default();
        assert!(!config.is_enabled());

        config.otel_endpoint = Some("http://localhost:4317".to_string());
        assert!(config.is_enabled());
    }

    #[test]
    fn test_current_trace_id_returns_none() {
        // Without OTel enabled, should return None
        assert!(current_trace_id().is_none());
    }
}
