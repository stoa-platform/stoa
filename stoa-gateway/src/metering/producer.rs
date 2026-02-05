//! Kafka Metering Producer
//!
//! Fire-and-forget Kafka producer for metering events.
//! Uses rdkafka with delivery callbacks for reliability.

// Allow dead code: public API types for future consumption
#![allow(dead_code)]

use serde::Serialize;
use std::sync::Arc;
use std::time::Duration;
use tracing::{debug, warn};

#[cfg(feature = "metering")]
use tracing::{error, info};

#[cfg(feature = "metering")]
use rdkafka::{
    config::ClientConfig,
    producer::{FutureProducer, FutureRecord, Producer},
    util::Timeout,
};

use super::events::{HttpRequestEvent, ToolCallEvent};
use super::snapshots::ErrorSnapshot;

/// Metering producer configuration
#[derive(Debug, Clone)]
pub struct MeteringProducerConfig {
    /// Kafka broker list (comma-separated)
    pub brokers: String,

    /// Topic for metering events
    pub metering_topic: String,

    /// Topic for error snapshots
    pub errors_topic: String,

    /// Message delivery timeout in milliseconds
    pub delivery_timeout_ms: u64,

    /// Batch size for producer
    pub batch_size: usize,

    /// Linger time in milliseconds (wait for batch)
    pub linger_ms: u64,

    /// Compression type (none, gzip, snappy, lz4, zstd)
    pub compression: String,

    /// Enable idempotent producer
    pub enable_idempotence: bool,
}

impl Default for MeteringProducerConfig {
    fn default() -> Self {
        Self {
            brokers: "localhost:9092".to_string(),
            metering_topic: "stoa.metering".to_string(),
            errors_topic: "stoa.errors".to_string(),
            delivery_timeout_ms: 5000,
            batch_size: 16384,
            linger_ms: 5,
            compression: "lz4".to_string(),
            enable_idempotence: true,
        }
    }
}

/// Metering producer for sending events to Kafka
///
/// Fire-and-forget with delivery callbacks for reliability.
/// Events are batched for throughput.
#[derive(Clone)]
pub struct MeteringProducer {
    #[cfg(feature = "metering")]
    producer: Arc<FutureProducer>,

    #[cfg(not(feature = "metering"))]
    _phantom: std::marker::PhantomData<()>,

    config: MeteringProducerConfig,
    enabled: bool,
}

impl MeteringProducer {
    /// Create a new metering producer
    ///
    /// Returns None if metering is disabled or Kafka is unreachable.
    #[cfg(feature = "metering")]
    pub fn new(config: MeteringProducerConfig, enabled: bool) -> Option<Self> {
        if !enabled {
            info!("Metering disabled — events will not be sent to Kafka");
            return Some(Self {
                producer: Arc::new(Self::create_noop_producer()?),
                config,
                enabled: false,
            });
        }

        let producer = Self::create_producer(&config)?;

        info!(
            brokers = %config.brokers,
            metering_topic = %config.metering_topic,
            errors_topic = %config.errors_topic,
            "Metering producer initialized"
        );

        Some(Self {
            producer: Arc::new(producer),
            config,
            enabled: true,
        })
    }

    /// Create a new metering producer (no-op when metering feature disabled)
    #[cfg(not(feature = "metering"))]
    pub fn new(config: MeteringProducerConfig, enabled: bool) -> Option<Self> {
        if enabled {
            warn!("Metering feature not compiled in — events will not be sent to Kafka");
        }
        Some(Self {
            _phantom: std::marker::PhantomData,
            config,
            enabled: false,
        })
    }

    /// Create the Kafka producer
    #[cfg(feature = "metering")]
    fn create_producer(config: &MeteringProducerConfig) -> Option<FutureProducer> {
        let producer: FutureProducer = ClientConfig::new()
            .set("bootstrap.servers", &config.brokers)
            .set(
                "message.timeout.ms",
                config.delivery_timeout_ms.to_string(),
            )
            .set("batch.size", config.batch_size.to_string())
            .set("linger.ms", config.linger_ms.to_string())
            .set("compression.type", &config.compression)
            .set(
                "enable.idempotence",
                config.enable_idempotence.to_string(),
            )
            // Delivery report callback
            .set("acks", "all")
            // Client identification
            .set("client.id", "stoa-gateway-metering")
            .create()
            .map_err(|e| {
                error!(error = %e, "Failed to create Kafka producer");
            })
            .ok()?;

        Some(producer)
    }

    /// Create a no-op producer for disabled metering
    #[cfg(feature = "metering")]
    fn create_noop_producer() -> Option<FutureProducer> {
        // We still need a valid producer instance for the type system,
        // but we won't use it. Create with localhost which may fail gracefully.
        ClientConfig::new()
            .set("bootstrap.servers", "localhost:9092")
            .set("message.timeout.ms", "1000")
            .create()
            .ok()
    }

    /// Send a tool call event (fire-and-forget)
    pub fn send_tool_call(&self, event: ToolCallEvent) {
        if !self.enabled {
            debug!(
                tool = %event.tool_name,
                tenant = %event.tenant_id,
                "Metering disabled — skipping tool call event"
            );
            return;
        }

        self.send_event(&self.config.metering_topic, event.partition_key(), &event);
    }

    /// Send an HTTP request event (fire-and-forget)
    #[allow(dead_code)]
    pub fn send_http_request(&self, event: HttpRequestEvent) {
        if !self.enabled {
            debug!(
                path = %event.path,
                tenant = %event.tenant_id,
                "Metering disabled — skipping HTTP request event"
            );
            return;
        }

        self.send_event(&self.config.metering_topic, event.partition_key(), &event);
    }

    /// Send an error snapshot (fire-and-forget)
    pub fn send_error_snapshot(&self, snapshot: ErrorSnapshot) {
        if !self.enabled {
            debug!(
                error_type = %snapshot.error_type,
                "Metering disabled — skipping error snapshot"
            );
            return;
        }

        self.send_event(
            &self.config.errors_topic,
            snapshot.partition_key(),
            &snapshot,
        );
    }

    /// Internal: serialize and send event to Kafka
    #[cfg(feature = "metering")]
    fn send_event<T: Serialize>(&self, topic: &str, key: &str, event: &T) {
        let payload = match serde_json::to_vec(event) {
            Ok(p) => p,
            Err(e) => {
                error!(error = %e, "Failed to serialize metering event");
                return;
            }
        };

        let producer = self.producer.clone();
        let topic = topic.to_string();
        let key = key.to_string();

        // Fire-and-forget with async delivery
        tokio::spawn(async move {
            let record = FutureRecord::to(&topic).key(&key).payload(&payload);

            match producer.send(record, Timeout::After(Duration::from_secs(5))).await {
                Ok((partition, offset)) => {
                    debug!(
                        topic = %topic,
                        partition = partition,
                        offset = offset,
                        "Metering event delivered"
                    );
                }
                Err((e, _)) => {
                    warn!(
                        topic = %topic,
                        error = %e,
                        "Metering event delivery failed — event lost"
                    );
                }
            }
        });
    }

    /// No-op send when metering feature is disabled
    #[cfg(not(feature = "metering"))]
    fn send_event<T: Serialize>(&self, _topic: &str, _key: &str, _event: &T) {
        // No-op: metering feature not enabled
    }

    /// Check if producer is healthy
    #[cfg(feature = "metering")]
    pub fn is_healthy(&self) -> bool {
        if !self.enabled {
            return true; // Disabled is "healthy" (not broken)
        }

        // Check if we can reach the broker
        // FutureProducer doesn't have a direct health check,
        // but we can check the in-flight queue size
        self.producer.in_flight_count() < 10000
    }

    #[cfg(not(feature = "metering"))]
    pub fn is_healthy(&self) -> bool {
        true
    }

    /// Flush pending events (for graceful shutdown)
    #[cfg(feature = "metering")]
    pub fn flush(&self, timeout: Duration) {
        if !self.enabled {
            return;
        }

        info!("Flushing metering producer...");
        if let Err(e) = self.producer.flush(Timeout::After(timeout)) {
            warn!(error = %e, "Failed to flush metering producer");
        }
    }

    #[cfg(not(feature = "metering"))]
    pub fn flush(&self, _timeout: Duration) {
        // No-op
    }

    /// Check if metering is enabled
    pub fn is_enabled(&self) -> bool {
        self.enabled
    }
}

impl std::fmt::Debug for MeteringProducer {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("MeteringProducer")
            .field("enabled", &self.enabled)
            .field("brokers", &self.config.brokers)
            .field("metering_topic", &self.config.metering_topic)
            .field("errors_topic", &self.config.errors_topic)
            .finish()
    }
}

/// Shared metering producer handle
pub type SharedMeteringProducer = Arc<MeteringProducer>;

/// Create a shared metering producer
pub fn create_shared_producer(
    config: MeteringProducerConfig,
    enabled: bool,
) -> Option<SharedMeteringProducer> {
    MeteringProducer::new(config, enabled).map(Arc::new)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_config() {
        let config = MeteringProducerConfig::default();
        assert_eq!(config.brokers, "localhost:9092");
        assert_eq!(config.metering_topic, "stoa.metering");
        assert_eq!(config.errors_topic, "stoa.errors");
        assert_eq!(config.compression, "lz4");
        assert!(config.enable_idempotence);
    }

    #[test]
    fn test_producer_disabled() {
        let config = MeteringProducerConfig::default();
        // This should succeed even without Kafka (disabled mode)
        let producer = MeteringProducer::new(config, false);
        assert!(producer.is_some());

        let producer = producer.unwrap();
        assert!(!producer.is_enabled());
        assert!(producer.is_healthy());
    }

    #[test]
    fn test_producer_debug() {
        let config = MeteringProducerConfig::default();
        let producer = MeteringProducer::new(config, false).unwrap();
        let debug_str = format!("{:?}", producer);
        assert!(debug_str.contains("MeteringProducer"));
        assert!(debug_str.contains("enabled: false"));
    }
}
