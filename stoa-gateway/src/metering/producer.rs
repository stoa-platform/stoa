//! Metering Producer (Phase 3: CAB-1105)
//!
//! Publishes metering events and error snapshots to Kafka topics.
//! Uses fire-and-forget pattern — never blocks the request path.
//!
//! # Graceful Degradation
//!
//! - If Kafka is unavailable at startup: logs warning, metering disabled
//! - If Kafka becomes unavailable: events are dropped (logged via tracing)
//! - `STOA_KAFKA_ENABLED=false` (default): no-op producer, events logged only

use super::{ErrorSnapshot, KafkaConfig, ToolCallEvent};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use tracing::{debug, error, warn};

/// Producer configuration
#[derive(Debug, Clone)]
pub struct MeteringProducerConfig {
    /// Kafka brokers (comma-separated)
    pub brokers: String,
    /// Topic for metering events
    pub metering_topic: String,
    /// Topic for error snapshots
    pub errors_topic: String,
}

impl From<&KafkaConfig> for MeteringProducerConfig {
    fn from(config: &KafkaConfig) -> Self {
        Self {
            brokers: config.brokers.clone(),
            metering_topic: config.metering_topic.clone(),
            errors_topic: config.errors_topic.clone(),
        }
    }
}

/// Metering producer trait for fire-and-forget event publishing
pub trait MeteringProducerTrait: Send + Sync {
    /// Send a metering event (non-blocking, fire-and-forget)
    fn send_metering_event(&self, event: ToolCallEvent);

    /// Send an error snapshot (non-blocking, fire-and-forget)
    fn send_error_snapshot(&self, snapshot: ErrorSnapshot);

    /// Get count of events sent
    fn events_sent(&self) -> u64;

    /// Get count of errors sent
    fn errors_sent(&self) -> u64;
}

/// Metering producer that publishes events to Kafka or logs them
///
/// When `kafka` feature is not enabled or Kafka is unavailable,
/// events are logged via tracing (debug level).
pub struct MeteringProducer {
    config: MeteringProducerConfig,
    events_count: AtomicU64,
    errors_count: AtomicU64,
    #[cfg(feature = "kafka")]
    producer: Option<rdkafka::producer::FutureProducer>,
}

impl MeteringProducer {
    /// Create a new metering producer
    ///
    /// # Graceful Degradation
    ///
    /// - With `kafka` feature: attempts to connect to Kafka
    /// - Without `kafka` feature: uses no-op producer
    /// - If connection fails: logs warning, uses no-op mode
    pub fn new(config: MeteringProducerConfig) -> Result<Self, String> {
        #[cfg(feature = "kafka")]
        {
            use rdkafka::config::ClientConfig;
            use rdkafka::producer::FutureProducer;

            let producer: Result<FutureProducer, _> = ClientConfig::new()
                .set("bootstrap.servers", &config.brokers)
                .set("message.timeout.ms", "5000")
                .set("queue.buffering.max.ms", "100") // Batch for 100ms
                .set("batch.num.messages", "1000")
                .set("compression.type", "lz4")
                .create();

            match producer {
                Ok(p) => {
                    tracing::info!(
                        brokers = %config.brokers,
                        metering_topic = %config.metering_topic,
                        errors_topic = %config.errors_topic,
                        "Kafka metering producer initialized"
                    );
                    Ok(Self {
                        config,
                        events_count: AtomicU64::new(0),
                        errors_count: AtomicU64::new(0),
                        producer: Some(p),
                    })
                }
                Err(e) => {
                    warn!(
                        error = %e,
                        brokers = %config.brokers,
                        "Kafka connection failed — metering disabled"
                    );
                    Ok(Self {
                        config,
                        events_count: AtomicU64::new(0),
                        errors_count: AtomicU64::new(0),
                        producer: None,
                    })
                }
            }
        }

        #[cfg(not(feature = "kafka"))]
        {
            tracing::info!("Kafka metering producer (no-op mode — 'kafka' feature not enabled)");
            Ok(Self {
                config,
                events_count: AtomicU64::new(0),
                errors_count: AtomicU64::new(0),
            })
        }
    }

    /// Create a no-op producer for testing
    pub fn noop(config: MeteringProducerConfig) -> Self {
        Self {
            config,
            events_count: AtomicU64::new(0),
            errors_count: AtomicU64::new(0),
            #[cfg(feature = "kafka")]
            producer: None,
        }
    }
}

impl MeteringProducerTrait for MeteringProducer {
    fn send_metering_event(&self, event: ToolCallEvent) {
        self.events_count.fetch_add(1, Ordering::Relaxed);

        #[cfg(feature = "kafka")]
        if let Some(ref producer) = self.producer {
            let topic = self.config.metering_topic.clone();
            let key = event.tenant_id.clone();

            match serde_json::to_string(&event) {
                Ok(payload) => {
                    let producer = producer.clone();
                    tokio::spawn(async move {
                        use rdkafka::producer::FutureRecord;
                        use std::time::Duration;

                        let record = FutureRecord::to(&topic).key(&key).payload(&payload);

                        if let Err((e, _)) = producer.send(record, Duration::from_secs(0)).await {
                            error!(error = %e, "Failed to send metering event to Kafka");
                        } else {
                            debug!(topic = %topic, tenant = %key, "Metering event sent");
                        }
                    });
                }
                Err(e) => {
                    error!(error = %e, "Failed to serialize metering event");
                }
            }
            return;
        }

        // No-op mode: log the event
        debug!(
            event_id = %event.event_id,
            tenant = %event.tenant_id,
            tool = %event.tool_name,
            status = %event.status,
            latency_ms = event.latency_ms,
            "Metering event (no-op mode)"
        );
    }

    fn send_error_snapshot(&self, snapshot: ErrorSnapshot) {
        self.errors_count.fetch_add(1, Ordering::Relaxed);

        #[cfg(feature = "kafka")]
        if let Some(ref producer) = self.producer {
            let topic = self.config.errors_topic.clone();
            let key = snapshot.base_event.tenant_id.clone();

            match serde_json::to_string(&snapshot) {
                Ok(payload) => {
                    let producer = producer.clone();
                    tokio::spawn(async move {
                        use rdkafka::producer::FutureRecord;
                        use std::time::Duration;

                        let record = FutureRecord::to(&topic).key(&key).payload(&payload);

                        if let Err((e, _)) = producer.send(record, Duration::from_secs(0)).await {
                            error!(error = %e, "Failed to send error snapshot to Kafka");
                        } else {
                            debug!(topic = %topic, tenant = %key, "Error snapshot sent");
                        }
                    });
                }
                Err(e) => {
                    error!(error = %e, "Failed to serialize error snapshot");
                }
            }
            return;
        }

        // No-op mode: log the error
        warn!(
            event_id = %snapshot.base_event.event_id,
            tenant = %snapshot.base_event.tenant_id,
            tool = %snapshot.base_event.tool_name,
            error_type = %snapshot.error_type,
            status = snapshot.response_status,
            "Error snapshot (no-op mode)"
        );
    }

    fn events_sent(&self) -> u64 {
        self.events_count.load(Ordering::Relaxed)
    }

    fn errors_sent(&self) -> u64 {
        self.errors_count.load(Ordering::Relaxed)
    }
}

impl MeteringProducer {
    /// Send a raw payload to an arbitrary Kafka topic (fire-and-forget).
    ///
    /// Used by `DeployProgressEmitter` and other modules that need to publish
    /// pre-serialized events to custom topics beyond metering/errors.
    pub fn send_raw(&self, topic: &str, key: &str, payload: &str) {
        #[cfg(feature = "kafka")]
        if let Some(ref producer) = self.producer {
            let topic = topic.to_string();
            let key = key.to_string();
            let payload = payload.to_string();
            let producer = producer.clone();
            tokio::spawn(async move {
                use rdkafka::producer::FutureRecord;
                use std::time::Duration;

                let record = FutureRecord::to(&topic).key(&key).payload(&payload);
                if let Err((e, _)) = producer.send(record, Duration::from_secs(0)).await {
                    error!(error = %e, topic = %topic, "Failed to send raw event to Kafka");
                } else {
                    debug!(topic = %topic, key = %key, "Raw event sent to Kafka");
                }
            });
            return;
        }

        // No-op mode: log the event (payload intentionally not logged — may be large)
        let _ = payload;
        debug!(topic = %topic, key = %key, "Raw event (no-op mode — Kafka unavailable)");
    }
}

/// Thread-safe metering producer wrapper
pub type SharedMeteringProducer = Arc<MeteringProducer>;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_noop_producer() {
        let config = MeteringProducerConfig {
            brokers: "localhost:9092".to_string(),
            metering_topic: "test.metering".to_string(),
            errors_topic: "test.errors".to_string(),
        };

        let producer = MeteringProducer::noop(config);
        assert_eq!(producer.events_sent(), 0);
        assert_eq!(producer.errors_sent(), 0);

        // Send an event (should not panic)
        let event = ToolCallEvent::new(
            "tenant-test".to_string(),
            "test_tool".to_string(),
            "Read".to_string(),
        );
        producer.send_metering_event(event);
        assert_eq!(producer.events_sent(), 1);
    }

    #[test]
    fn test_config_from_kafka_config() {
        let kafka_config = KafkaConfig {
            brokers: "broker1:9092,broker2:9092".to_string(),
            metering_topic: "custom.metering".to_string(),
            errors_topic: "custom.errors".to_string(),
            enabled: true,
        };

        let config: MeteringProducerConfig = (&kafka_config).into();
        assert_eq!(config.brokers, "broker1:9092,broker2:9092");
        assert_eq!(config.metering_topic, "custom.metering");
    }
}
