//! Kafka CNS Event Consumer (Phase 2: CAB-1178)
//!
//! Consumes events from `stoa.*` Kafka topics and pushes them to
//! connected MCP clients via the SessionManager's NotificationBus.
//!
//! # Feature Gate
//!
//! - `kafka`: Enables rdkafka StreamConsumer for real Kafka consumption
//! - Without `kafka`: Module compiles but `start_cns_consumer` is a no-op

use crate::events::polling::EventBuffer;
use crate::mcp::session::SessionManager;
use std::sync::Arc;
use tracing::warn;

/// Start the CNS event consumer (Kafka feature enabled)
///
/// Spawns a background task that consumes from `stoa.*` topics and
/// broadcasts events to matching tenant sessions via SSE.
#[cfg(feature = "kafka")]
pub fn start_cns_consumer(
    brokers: &str,
    topics: &str,
    group_id: &str,
    session_manager: SessionManager,
    event_buffer: Arc<EventBuffer>,
) {
    use rdkafka::config::ClientConfig;
    use rdkafka::consumer::{Consumer, StreamConsumer};
    use tokio_stream::StreamExt;
    use tracing::{error, info};

    let consumer: StreamConsumer = match ClientConfig::new()
        .set("bootstrap.servers", brokers)
        .set("group.id", group_id)
        .set("auto.offset.reset", "latest")
        .set("enable.auto.commit", "true")
        .set("session.timeout.ms", "6000")
        .create()
    {
        Ok(c) => c,
        Err(e) => {
            error!(error = %e, "Failed to create Kafka CNS consumer — events disabled");
            return;
        }
    };

    // Subscribe to topics
    let topic_list: Vec<&str> = topics.split(',').map(|t| t.trim()).collect();
    if let Err(e) = consumer.subscribe(&topic_list) {
        error!(error = %e, topics = ?topic_list, "Failed to subscribe to CNS topics");
        return;
    }

    info!(
        topics = ?topic_list,
        group_id = %group_id,
        "Kafka CNS consumer started"
    );

    tokio::spawn(async move {
        let mut stream = consumer.stream();
        while let Some(result) = stream.next().await {
            match result {
                Ok(message) => {
                    use rdkafka::Message;
                    if let Some(payload) = message.payload() {
                        process_cns_message(payload, &session_manager, &event_buffer);
                    }
                }
                Err(e) => {
                    warn!(error = %e, "Kafka CNS consumer error (continuing)");
                }
            }
        }
        warn!("Kafka CNS consumer stream ended unexpectedly");
    });
}

/// Start the CNS event consumer (no-op when kafka feature is disabled)
#[cfg(not(feature = "kafka"))]
pub fn start_cns_consumer(
    _brokers: &str,
    _topics: &str,
    _group_id: &str,
    _session_manager: SessionManager,
    _event_buffer: Arc<EventBuffer>,
) {
    warn!("Kafka CNS consumer requested but 'kafka' feature not enabled — events disabled");
}

/// Process a single CNS message payload
///
/// Converts event to MCP `notifications/send` format (CAB-1179),
/// broadcasts to matching tenant SSE sessions, and pushes to
/// the polling EventBuffer for clients without SSE support.
#[cfg(any(feature = "kafka", test))]
fn process_cns_message(
    payload: &[u8],
    session_manager: &SessionManager,
    event_buffer: &EventBuffer,
) {
    use super::notifications::format_notification;
    use super::CnsEvent;
    use tracing::debug;

    let event: CnsEvent = match serde_json::from_slice(payload) {
        Ok(e) => e,
        Err(e) => {
            warn!(error = %e, "Failed to deserialize CNS event (skipping)");
            return;
        }
    };

    debug!(
        event_id = %event.id,
        event_type = %event.type_,
        tenant_id = %event.tenant_id,
        "Processing CNS event"
    );

    // Format as MCP notifications/send JSON-RPC envelope
    let notification = format_notification(&event);
    let sse_data = notification.to_string();

    // Push to SSE sessions matching this tenant
    let sent = session_manager.broadcast_to_tenant(&event.tenant_id, "notification", &sse_data);

    // Push to polling buffer (for clients without SSE support)
    event_buffer.push(event.clone());

    if sent > 0 {
        debug!(
            event_id = %event.id,
            tenant_id = %event.tenant_id,
            sessions = sent,
            "MCP notification delivered via SSE"
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::response::sse::Event;
    use tokio::sync::mpsc;

    #[tokio::test]
    async fn test_process_cns_message_valid() {
        let manager = SessionManager::new(30);
        let buffer = EventBuffer::new();
        manager
            .create(crate::mcp::session::Session::new(
                "s-1".into(),
                "acme".into(),
            ))
            .await;

        let (tx, mut rx) = mpsc::channel::<Event>(32);
        manager.register_channel("s-1", tx);

        let payload = serde_json::json!({
            "id": "evt-001",
            "type": "api-created",
            "source": "control-plane-api",
            "tenant_id": "acme",
            "timestamp": "2026-02-17T10:00:00Z",
            "payload": {"api_id": "api-42"}
        });

        process_cns_message(payload.to_string().as_bytes(), &manager, &buffer);

        // SSE delivery
        let received = rx.try_recv();
        assert!(received.is_ok());
        // Polling buffer
        assert_eq!(buffer.count(), 1);
    }

    #[tokio::test]
    async fn test_process_cns_message_invalid_json() {
        let manager = SessionManager::new(30);
        let buffer = EventBuffer::new();
        // Should not panic on invalid JSON
        process_cns_message(b"not json", &manager, &buffer);
        assert_eq!(buffer.count(), 0);
    }

    #[tokio::test]
    async fn test_process_cns_message_no_matching_tenant() {
        let manager = SessionManager::new(30);
        let buffer = EventBuffer::new();
        manager
            .create(crate::mcp::session::Session::new(
                "s-1".into(),
                "other".into(),
            ))
            .await;

        let (tx, mut rx) = mpsc::channel::<Event>(32);
        manager.register_channel("s-1", tx);

        let payload = serde_json::json!({
            "id": "evt-002",
            "type": "security-alert",
            "source": "gateway",
            "tenant_id": "acme",
            "timestamp": "2026-02-17T12:00:00Z"
        });

        process_cns_message(payload.to_string().as_bytes(), &manager, &buffer);

        // "other" tenant should NOT receive "acme" event via SSE
        assert!(rx.try_recv().is_err());
        // But event IS in the polling buffer (for acme tenant to poll later)
        assert_eq!(buffer.count(), 1);
    }

    #[tokio::test]
    async fn test_process_cns_message_notification_format() {
        let manager = SessionManager::new(30);
        let buffer = EventBuffer::new();
        manager
            .create(crate::mcp::session::Session::new(
                "s-1".into(),
                "acme".into(),
            ))
            .await;

        let (tx, mut rx) = mpsc::channel::<Event>(32);
        manager.register_channel("s-1", tx);

        let payload = serde_json::json!({
            "id": "evt-003",
            "type": "api-created",
            "source": "control-plane-api",
            "tenant_id": "acme",
            "timestamp": "2026-02-17T10:00:00Z",
            "payload": {"api_id": "api-42"}
        });

        process_cns_message(payload.to_string().as_bytes(), &manager, &buffer);

        // Verify SSE data is MCP JSON-RPC notification format
        let event = rx.try_recv().expect("should receive SSE event");
        let event_str = format!("{:?}", event);
        assert!(event_str.contains("notifications/send"));
        assert!(event_str.contains("jsonrpc"));
    }
}
