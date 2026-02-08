//! Kafka Metering Module (Phase 3: CAB-1105)
//!
//! Zero-blind-spot metering for enterprise billing, audit, and SLA compliance (ADR-023).
//!
//! Every tool call generates a metering event. Every error generates an error snapshot.
//! Events are published to Kafka topics asynchronously (fire-and-forget, non-blocking).
//!
//! # Features
//!
//! - `kafka`: Enable rdkafka producer (requires librdkafka)
//! - Without `kafka`: Uses no-op producer (events logged via tracing)
//!
//! # Configuration
//!
//! - `STOA_KAFKA_ENABLED`: Enable Kafka metering (default: false)
//! - `STOA_KAFKA_BROKERS`: Kafka broker addresses (default: "redpanda:9092")
//! - `STOA_KAFKA_METERING_TOPIC`: Topic for metering events (default: "stoa.metering")
//! - `STOA_KAFKA_ERRORS_TOPIC`: Topic for error snapshots (default: "stoa.errors")

// Metering types are prepared for middleware integration (Phase 3 extension)
#![allow(dead_code)]
#![allow(unused_imports)]

mod events;
mod producer;

pub use events::{ErrorSnapshot, EventStatus, GatewaySnapshot, ToolCallEvent};
pub use producer::{MeteringProducer, MeteringProducerConfig, MeteringProducerTrait};

/// Kafka configuration for metering
#[derive(Debug, Clone)]
pub struct KafkaConfig {
    /// Kafka broker addresses (comma-separated)
    pub brokers: String,
    /// Topic for metering events
    pub metering_topic: String,
    /// Topic for error snapshots
    pub errors_topic: String,
    /// Enable Kafka metering
    pub enabled: bool,
}

impl Default for KafkaConfig {
    fn default() -> Self {
        Self {
            brokers: "redpanda:9092".to_string(),
            metering_topic: "stoa.metering".to_string(),
            errors_topic: "stoa.errors".to_string(),
            enabled: false, // Disabled by default — explicit opt-in
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_kafka_config_default() {
        let config = KafkaConfig::default();
        assert!(!config.enabled);
        assert_eq!(config.brokers, "redpanda:9092");
        assert_eq!(config.metering_topic, "stoa.metering");
        assert_eq!(config.errors_topic, "stoa.errors");
    }
}
