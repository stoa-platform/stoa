//! Telemetry Module
//!
//! Production-grade observability for STOA Gateway:
//! - OpenTelemetry distributed tracing (OTLP export)
//! - Prometheus metrics (dual export: scrape + OTLP)
//! - Structured JSON logging with trace correlation

pub mod otel;

#[allow(unused_imports)]
pub use otel::{init_telemetry, shutdown_telemetry, TelemetryConfig};
