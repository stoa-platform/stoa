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
    use crate::metering::{ErrorSnapshot, EventStatus, GatewaySnapshot};

    fn make_config() -> MeteringProducerConfig {
        MeteringProducerConfig {
            brokers: "localhost:9092".to_string(),
            metering_topic: "test.metering".to_string(),
            errors_topic: "test.errors".to_string(),
        }
    }

    fn make_event() -> ToolCallEvent {
        ToolCallEvent::new(
            "tenant-test".to_string(),
            "test_tool".to_string(),
            "Read".to_string(),
        )
    }

    #[test]
    fn test_noop_producer() {
        let producer = MeteringProducer::noop(make_config());
        assert_eq!(producer.events_sent(), 0);
        assert_eq!(producer.errors_sent(), 0);
        producer.send_metering_event(make_event());
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
        assert_eq!(config.errors_topic, "custom.errors");
    }

    #[test]
    fn test_noop_producer_increments_event_count() {
        let producer = MeteringProducer::noop(make_config());
        for _ in 0..5 {
            producer.send_metering_event(make_event());
        }
        assert_eq!(producer.events_sent(), 5);
    }

    #[test]
    fn test_noop_producer_increments_error_count() {
        let producer = MeteringProducer::noop(make_config());
        let event = make_event().with_status(EventStatus::Error);
        let snapshot =
            ErrorSnapshot::from_event(event, "Timeout".to_string(), "timed out".to_string(), 504)
                .with_request("/mcp/tools/call".to_string(), "POST".to_string());
        producer.send_error_snapshot(snapshot);
        assert_eq!(producer.errors_sent(), 1);
        assert_eq!(producer.events_sent(), 0);
    }

    #[test]
    fn test_noop_producer_mixed_events_and_errors() {
        let producer = MeteringProducer::noop(make_config());
        producer.send_metering_event(make_event());
        producer.send_metering_event(make_event());
        let err_event = make_event().with_status(EventStatus::PolicyDenied);
        let snapshot = ErrorSnapshot::from_event(
            err_event,
            "PolicyDenied".to_string(),
            "denied".to_string(),
            403,
        );
        producer.send_error_snapshot(snapshot);
        assert_eq!(producer.events_sent(), 2);
        assert_eq!(producer.errors_sent(), 1);
    }

    #[tokio::test]
    async fn test_new_without_kafka_feature() {
        let producer = MeteringProducer::new(make_config()).unwrap();
        assert_eq!(producer.events_sent(), 0);
        producer.send_metering_event(make_event());
        assert_eq!(producer.events_sent(), 1);
    }

    #[test]
    fn test_send_raw_noop_mode() {
        let producer = MeteringProducer::noop(make_config());
        producer.send_raw("custom.topic", "key-1", r#"{"data":"test"}"#);
    }

    #[test]
    fn test_shared_producer_type() {
        let producer = MeteringProducer::noop(make_config());
        let shared: SharedMeteringProducer = Arc::new(producer);
        shared.send_metering_event(make_event());
        assert_eq!(shared.events_sent(), 1);
        let shared2 = Arc::clone(&shared);
        shared2.send_metering_event(make_event());
        assert_eq!(shared.events_sent(), 2);
    }

    #[test]
    fn test_config_fields() {
        let config = make_config();
        assert_eq!(config.brokers, "localhost:9092");
        assert_eq!(config.metering_topic, "test.metering");
        assert_eq!(config.errors_topic, "test.errors");
    }

    #[test]
    fn test_noop_producer_config_stored() {
        let config = MeteringProducerConfig {
            brokers: "kafka:9092".to_string(),
            metering_topic: "stoa.metering".to_string(),
            errors_topic: "stoa.errors".to_string(),
        };
        let producer = MeteringProducer::noop(config);
        assert_eq!(producer.config.brokers, "kafka:9092");
        assert_eq!(producer.config.metering_topic, "stoa.metering");
    }

    #[test]
    fn test_event_with_enrichment_fields() {
        let producer = MeteringProducer::noop(make_config());
        let event = make_event()
            .with_user(
                Some("user-1".to_string()),
                Some("user@test.com".to_string()),
            )
            .with_timing(100, 20, 80)
            .with_sizes(256, 1024)
            .with_federation(Some("sub-1"), Some("master-1"))
            .with_billing(Some("dept-eng"), 500, "premium", 2500);
        producer.send_metering_event(event);
        assert_eq!(producer.events_sent(), 1);
    }

    #[test]
    fn test_error_snapshot_with_gateway_state() {
        let producer = MeteringProducer::noop(make_config());
        let event = make_event().with_status(EventStatus::Error);
        let snapshot = ErrorSnapshot::from_event(
            event,
            "BackendError".to_string(),
            "connection refused".to_string(),
            502,
        )
        .with_request("/mcp/tools/call".to_string(), "POST".to_string())
        .with_gateway_state(GatewaySnapshot {
            active_sessions: 42,
            uptime_secs: 3600,
            rate_limit_buckets: 10,
            memory_rss_bytes: Some(128_000_000),
        });
        producer.send_error_snapshot(snapshot);
        assert_eq!(producer.errors_sent(), 1);
    }
}
