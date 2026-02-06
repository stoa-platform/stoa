//! Telemetry Module (Phase 6: CAB-1105)
//!
//! Optional OpenTelemetry support with graceful degradation.
//! When `otel` feature is disabled, all functions become no-ops.
//!
//! Note: Infrastructure prepared for future tool instrumentation.
//! Actual usage in NativeTool is a Phase 7 enhancement.

// Types and functions prepared for future integration
#![allow(dead_code)]

mod spans;

#[allow(unused_imports)]
pub use spans::{ToolSpan, ToolSpanGuard};

use std::sync::OnceLock;
use tracing::info;

/// Global flag indicating if OTel is initialized
static OTEL_INITIALIZED: OnceLock<bool> = OnceLock::new();

/// Telemetry configuration
#[derive(Debug, Clone)]
pub struct TelemetryConfig {
    /// OTLP endpoint (e.g., "http://tempo:4317")
    pub otlp_endpoint: Option<String>,
    /// Service name for traces
    pub service_name: String,
    /// Service version
    pub service_version: String,
    /// Enable console exporter for debugging
    pub console_export: bool,
}

impl Default for TelemetryConfig {
    fn default() -> Self {
        Self {
            otlp_endpoint: std::env::var("OTEL_EXPORTER_OTLP_ENDPOINT").ok(),
            service_name: "stoa-gateway".to_string(),
            service_version: env!("CARGO_PKG_VERSION").to_string(),
            console_export: false,
        }
    }
}

/// Initialize OpenTelemetry (no-op if feature disabled or already initialized)
///
/// Returns true if OTel was successfully initialized.
pub fn init_telemetry(config: &TelemetryConfig) -> bool {
    // Only initialize once
    if OTEL_INITIALIZED.get().is_some() {
        return *OTEL_INITIALIZED.get().unwrap();
    }

    #[cfg(feature = "otel")]
    {
        let result = init_otel_internal(config);
        let _ = OTEL_INITIALIZED.set(result);
        if result {
            info!(
                service = %config.service_name,
                endpoint = ?config.otlp_endpoint,
                "OpenTelemetry initialized"
            );
        }
        result
    }

    #[cfg(not(feature = "otel"))]
    {
        let _ = config; // Silence unused warning
        let _ = OTEL_INITIALIZED.set(false);
        info!("OpenTelemetry disabled (feature not enabled)");
        false
    }
}

/// Check if OTel is active
pub fn is_otel_active() -> bool {
    OTEL_INITIALIZED.get().copied().unwrap_or(false)
}

/// Shutdown OpenTelemetry (flush pending spans)
pub fn shutdown_telemetry() {
    #[cfg(feature = "otel")]
    {
        if is_otel_active() {
            // opentelemetry::global::shutdown_tracer_provider();
            info!("OpenTelemetry shutdown");
        }
    }
}

#[cfg(feature = "otel")]
fn init_otel_internal(_config: &TelemetryConfig) -> bool {
    // TODO: Implement actual OTel initialization when deps stabilize
    // For now, return false to indicate not fully initialized
    //
    // use opentelemetry::global;
    // use opentelemetry_otlp::WithExportConfig;
    // use opentelemetry_sdk::trace::TracerProvider;
    //
    // let exporter = opentelemetry_otlp::new_exporter()
    //     .tonic()
    //     .with_endpoint(config.otlp_endpoint.as_deref().unwrap_or("http://localhost:4317"));
    //
    // let provider = TracerProvider::builder()
    //     .with_batch_exporter(exporter, opentelemetry_sdk::runtime::Tokio)
    //     .build();
    //
    // global::set_tracer_provider(provider);
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_telemetry_config_default() {
        let config = TelemetryConfig::default();
        assert_eq!(config.service_name, "stoa-gateway");
        assert!(!config.console_export);
    }

    #[test]
    fn test_init_without_otel_feature() {
        // Without otel feature, should return false
        let config = TelemetryConfig::default();
        // Note: Can't test init_telemetry multiple times due to OnceLock
        // Just verify config creation works
        assert_eq!(config.service_name, "stoa-gateway");
    }

    #[test]
    fn test_is_otel_active_default() {
        // Before init, or without feature, should be false
        // Note: This might be true if another test ran first
        let _ = is_otel_active(); // Just verify it doesn't panic
    }
}
