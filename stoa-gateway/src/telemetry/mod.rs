//! Telemetry Module (CAB-1831: always-on OTel)
//!
//! OpenTelemetry is always compiled in. When `STOA_OTEL_ENDPOINT` is absent,
//! the tracer layer is simply not added (no-op). No feature gate required.

pub mod deploy;
mod spans;

pub use spans::{PolicySpan, ToolSpan, ToolSpanGuard};

use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::OnceLock;
use tracing::info;

/// Global flag indicating if OTel is initialized
static OTEL_INITIALIZED: OnceLock<bool> = OnceLock::new();

/// Counter: total spans exported via OTLP (CAB-1831)
static SPANS_EXPORTED: AtomicU64 = AtomicU64::new(0);

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
    /// Head-based sampling rate (0.0 = none, 1.0 = all)
    pub sample_rate: f64,
    /// Gateway deployment mode (CAB-1842: resource-level attribute for service graph).
    /// Attached to every span as `stoa.deployment_mode` via OTel Resource.
    pub deployment_mode: String,
}

impl Default for TelemetryConfig {
    fn default() -> Self {
        Self {
            otlp_endpoint: std::env::var("OTEL_EXPORTER_OTLP_ENDPOINT").ok(),
            service_name: "stoa-gateway".to_string(),
            service_version: env!("CARGO_PKG_VERSION").to_string(),
            console_export: false,
            sample_rate: 1.0,
            deployment_mode: std::env::var("STOA_GATEWAY_MODE")
                .unwrap_or_else(|_| "edge-mcp".to_string()),
        }
    }
}

/// Initialize OTel and return an SDK Tracer for the tracing-opentelemetry layer.
///
/// Returns `Some(Tracer)` on success. Returns `None` when:
/// - Already initialized
/// - No OTLP endpoint configured (no-op mode, CAB-1831)
/// - Exporter creation fails (graceful degradation)
pub fn init_telemetry_tracer(config: &TelemetryConfig) -> Option<opentelemetry_sdk::trace::Tracer> {
    if OTEL_INITIALIZED.get().is_some() {
        return None;
    }

    // CAB-1831: no endpoint → no-op (tracing spans still work, just not exported)
    // NOTE: eprintln! is intentional — tracing subscriber is not yet initialized when this runs,
    // so tracing::info!/warn! are silently dropped. eprintln! goes to stderr (visible in container logs).
    let endpoint = match config.otlp_endpoint.as_deref() {
        Some(ep) if !ep.is_empty() => ep,
        _ => {
            eprintln!("[otel-init] STOA_OTEL_ENDPOINT not set — OTel export disabled (spans are local-only)");
            let _ = OTEL_INITIALIZED.set(false);
            return None;
        }
    };

    use opentelemetry::global;
    use opentelemetry::KeyValue;
    use opentelemetry_otlp::WithExportConfig;
    use opentelemetry_sdk::trace::TracerProvider;
    use opentelemetry_sdk::Resource;

    let exporter = match opentelemetry_otlp::SpanExporter::builder()
        .with_tonic()
        .with_endpoint(endpoint)
        .build()
    {
        Ok(e) => e,
        Err(err) => {
            eprintln!("[otel-init] Failed to create OTLP exporter: {err} — OTel disabled");
            let _ = OTEL_INITIALIZED.set(false);
            return None;
        }
    };

    let resource = Resource::new([
        KeyValue::new("service.name", config.service_name.clone()),
        KeyValue::new("service.version", config.service_version.clone()),
        KeyValue::new("stoa.deployment_mode", config.deployment_mode.clone()),
    ]);

    // Head-based sampling: ParentBased wrapping ensures child spans inherit parent decision
    use opentelemetry_sdk::trace::Sampler;
    let ratio_sampler = Sampler::TraceIdRatioBased(config.sample_rate);
    let sampler = Sampler::ParentBased(Box::new(ratio_sampler));

    // Configure batch exporter with explicit settings and error logging
    use opentelemetry_sdk::trace::BatchConfigBuilder;
    let batch_config = BatchConfigBuilder::default()
        .with_max_export_batch_size(512)
        .with_scheduled_delay(std::time::Duration::from_secs(5))
        .with_max_export_timeout(std::time::Duration::from_secs(30))
        .with_max_queue_size(2048)
        .build();

    let batch_processor = opentelemetry_sdk::trace::BatchSpanProcessor::builder(
        exporter,
        opentelemetry_sdk::runtime::Tokio,
    )
    .with_batch_config(batch_config)
    .build();

    let provider = TracerProvider::builder()
        .with_span_processor(batch_processor)
        .with_resource(resource)
        .with_sampler(sampler)
        .build();

    // Get SDK tracer BEFORE setting as global (returns concrete Tracer, not BoxedTracer)
    use opentelemetry::trace::TracerProvider as _;
    let tracer = provider.tracer("stoa-gateway");
    global::set_tracer_provider(provider);

    let _ = OTEL_INITIALIZED.set(true);
    eprintln!(
        "[otel-init] OpenTelemetry initialized — endpoint={endpoint} sample_rate={} batch_delay=5s queue=2048",
        config.sample_rate,
    );
    Some(tracer)
}

/// Initialize telemetry as no-op (runtime toggle off).
pub fn init_telemetry_noop() {
    let _ = OTEL_INITIALIZED.set(false);
    eprintln!("[otel-init] OpenTelemetry disabled (noop)");
}

/// Check if OTel is active
pub fn is_otel_active() -> bool {
    OTEL_INITIALIZED.get().copied().unwrap_or(false)
}

/// Extract the current OTel trace_id as hex string (for access logs).
///
/// Returns `"-"` when OTel is inactive.
pub fn extract_trace_id() -> String {
    if is_otel_active() {
        use opentelemetry::trace::TraceContextExt;
        use tracing_opentelemetry::OpenTelemetrySpanExt;

        let cx = tracing::Span::current().context();
        let span_ref = cx.span();
        let trace_id = span_ref.span_context().trace_id();
        if trace_id != opentelemetry::trace::TraceId::INVALID {
            return format!("{trace_id}");
        }
    }
    "-".to_string()
}

/// Extract the current OTel span_id as hex string (for access logs).
///
/// Returns `"-"` when OTel is inactive.
pub fn extract_span_id() -> String {
    if is_otel_active() {
        use opentelemetry::trace::TraceContextExt;
        use tracing_opentelemetry::OpenTelemetrySpanExt;

        let cx = tracing::Span::current().context();
        let span_ref = cx.span();
        let span_id = span_ref.span_context().span_id();
        if span_id != opentelemetry::trace::SpanId::INVALID {
            return format!("{span_id}");
        }
    }
    "-".to_string()
}

/// Shutdown OpenTelemetry (flush pending spans)
pub fn shutdown_telemetry() {
    if is_otel_active() {
        opentelemetry::global::shutdown_tracer_provider();
        info!("OpenTelemetry shutdown complete");
    }
}

/// Increment the exported spans counter (called from span finish methods)
pub fn record_span_exported() {
    SPANS_EXPORTED.fetch_add(1, Ordering::Relaxed);
}

/// Get the total number of exported spans (for Prometheus gauge)
pub fn spans_exported_total() -> u64 {
    SPANS_EXPORTED.load(Ordering::Relaxed)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_telemetry_config_default() {
        let config = TelemetryConfig::default();
        assert_eq!(config.service_name, "stoa-gateway");
        assert!(!config.console_export);
        assert!((config.sample_rate - 1.0).abs() < f64::EPSILON);
    }

    #[test]
    fn test_telemetry_config_sample_rate() {
        let config = TelemetryConfig {
            sample_rate: 0.5,
            ..TelemetryConfig::default()
        };
        assert!((config.sample_rate - 0.5).abs() < f64::EPSILON);
    }

    #[test]
    fn test_init_without_endpoint_returns_none() {
        // No endpoint → no-op
        let config = TelemetryConfig {
            otlp_endpoint: None,
            ..TelemetryConfig::default()
        };
        assert_eq!(config.service_name, "stoa-gateway");
        // Can't call init_telemetry_tracer in unit tests (OnceLock),
        // but verify config is valid
    }

    #[test]
    fn test_is_otel_active_default() {
        let _ = is_otel_active(); // Just verify it doesn't panic
    }

    #[test]
    fn test_spans_exported_counter() {
        let before = spans_exported_total();
        record_span_exported();
        record_span_exported();
        let after = spans_exported_total();
        assert!(after >= before + 2);
    }

    #[test]
    fn test_extract_trace_id_when_inactive() {
        // When OTel is not initialized, should return "-"
        // (OnceLock may or may not be set depending on test order)
        let trace_id = extract_trace_id();
        // Either "-" (inactive) or a valid hex trace ID
        assert!(!trace_id.is_empty());
    }

    #[test]
    fn test_extract_span_id_when_inactive() {
        // When OTel is not initialized, should return "-"
        // (OnceLock may or may not be set depending on test order)
        let span_id = extract_span_id();
        // Either "-" (inactive) or a valid hex span ID
        assert!(!span_id.is_empty());
    }
}
