//! HEGEMON Agent Lifecycle Metering (CAB-1720)
//!
//! Publishes agent lifecycle events to Kafka topic `hegemon.agent_events`
//! for centralized audit and observability.
//!
//! Events: `agent_authenticated`, `dispatch_started`, `dispatch_completed`,
//! `claim_reserved`, `claim_released`, `budget_checked`, `supervision_blocked`.
//!
//! Uses fire-and-forget pattern via existing `MeteringProducer::send_raw`.
//! In-memory ring buffer (1000 events) for admin API visibility.
//!
//! Config:
//! - `STOA_HEGEMON_AGENT_EVENTS_TOPIC` (default: "hegemon.agent_events")

use chrono::{DateTime, Utc};
use parking_lot::RwLock;
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tracing::{debug, warn};
use uuid::Uuid;

use crate::metering::MeteringProducer;

/// Agent lifecycle event types.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum AgentEventKind {
    AgentAuthenticated,
    DispatchStarted,
    DispatchCompleted,
    ClaimReserved,
    ClaimReleased,
    BudgetChecked,
    SupervisionBlocked,
}

impl std::fmt::Display for AgentEventKind {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            AgentEventKind::AgentAuthenticated => write!(f, "agent_authenticated"),
            AgentEventKind::DispatchStarted => write!(f, "dispatch_started"),
            AgentEventKind::DispatchCompleted => write!(f, "dispatch_completed"),
            AgentEventKind::ClaimReserved => write!(f, "claim_reserved"),
            AgentEventKind::ClaimReleased => write!(f, "claim_released"),
            AgentEventKind::BudgetChecked => write!(f, "budget_checked"),
            AgentEventKind::SupervisionBlocked => write!(f, "supervision_blocked"),
        }
    }
}

/// A single agent lifecycle event published to Kafka.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentEvent {
    pub event_id: Uuid,
    pub timestamp: DateTime<Utc>,
    pub kind: AgentEventKind,
    pub agent_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ticket_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub detail: Option<String>,
}

impl AgentEvent {
    /// Create a new agent lifecycle event.
    pub fn new(kind: AgentEventKind, agent_id: &str) -> Self {
        Self {
            event_id: Uuid::new_v4(),
            timestamp: Utc::now(),
            kind,
            agent_id: agent_id.to_string(),
            ticket_id: None,
            detail: None,
        }
    }

    /// Set optional ticket context.
    pub fn with_ticket(mut self, ticket_id: &str) -> Self {
        self.ticket_id = Some(ticket_id.to_string());
        self
    }

    /// Set optional detail message.
    pub fn with_detail(mut self, detail: &str) -> Self {
        self.detail = Some(detail.to_string());
        self
    }
}

// === In-memory Event Buffer ===

const DEFAULT_BUFFER_SIZE: usize = 1000;

/// Ring buffer for agent lifecycle events (admin API visibility).
pub struct AgentEventBuffer {
    events: RwLock<Vec<AgentEvent>>,
    max_size: usize,
}

impl AgentEventBuffer {
    pub fn new(max_size: usize) -> Self {
        Self {
            events: RwLock::new(Vec::with_capacity(max_size)),
            max_size,
        }
    }

    /// Push an event, evicting the oldest if full.
    pub fn push(&self, event: AgentEvent) {
        let mut events = self.events.write();
        if events.len() >= self.max_size {
            events.remove(0);
        }
        events.push(event);
    }

    /// Query recent events, newest first.
    pub fn recent(&self, limit: usize) -> Vec<AgentEvent> {
        let events = self.events.read();
        let limit = limit.min(500);
        events.iter().rev().take(limit).cloned().collect()
    }

    /// Count of buffered events.
    pub fn len(&self) -> usize {
        self.events.read().len()
    }

    /// Whether the buffer is empty.
    pub fn is_empty(&self) -> bool {
        self.events.read().is_empty()
    }
}

impl Default for AgentEventBuffer {
    fn default() -> Self {
        Self::new(DEFAULT_BUFFER_SIZE)
    }
}

// === Metering Emitter ===

/// Emits agent lifecycle events to Kafka and the in-memory buffer.
///
/// Graceful degradation: if Kafka is unavailable, events are logged and
/// buffered in-memory only.
pub struct AgentMeteringEmitter {
    topic: String,
    producer: Option<Arc<MeteringProducer>>,
    buffer: Arc<AgentEventBuffer>,
}

impl AgentMeteringEmitter {
    /// Create a new emitter with the given Kafka topic and producer.
    pub fn new(
        topic: String,
        producer: Option<Arc<MeteringProducer>>,
        buffer: Arc<AgentEventBuffer>,
    ) -> Self {
        Self {
            topic,
            producer,
            buffer,
        }
    }

    /// Emit an agent lifecycle event (fire-and-forget).
    ///
    /// The event is always added to the in-memory buffer.
    /// If a Kafka producer is available, it is also published to the topic.
    pub fn emit(&self, event: AgentEvent) {
        // Always buffer for admin API
        self.buffer.push(event.clone());

        // Publish to Kafka via send_raw (fire-and-forget)
        if let Some(ref producer) = self.producer {
            match serde_json::to_string(&event) {
                Ok(payload) => {
                    producer.send_raw(&self.topic, &event.agent_id, &payload);
                    debug!(
                        kind = %event.kind,
                        agent = %event.agent_id,
                        topic = %self.topic,
                        "Agent event emitted to Kafka"
                    );
                }
                Err(e) => {
                    warn!(error = %e, "Failed to serialize agent event");
                }
            }
        } else {
            debug!(
                kind = %event.kind,
                agent = %event.agent_id,
                "Agent event buffered (Kafka unavailable)"
            );
        }
    }

    /// Get a reference to the event buffer.
    pub fn buffer(&self) -> &Arc<AgentEventBuffer> {
        &self.buffer
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // === AgentEvent tests ===

    #[test]
    fn test_event_creation() {
        let event = AgentEvent::new(AgentEventKind::DispatchStarted, "worker-1");
        assert_eq!(event.kind, AgentEventKind::DispatchStarted);
        assert_eq!(event.agent_id, "worker-1");
        assert!(event.ticket_id.is_none());
        assert!(event.detail.is_none());
    }

    #[test]
    fn test_event_with_context() {
        let event = AgentEvent::new(AgentEventKind::ClaimReserved, "worker-2")
            .with_ticket("CAB-1720")
            .with_detail("Phase 1 claimed");
        assert_eq!(event.ticket_id.as_deref(), Some("CAB-1720"));
        assert_eq!(event.detail.as_deref(), Some("Phase 1 claimed"));
    }

    #[test]
    fn test_event_serialization() {
        let event =
            AgentEvent::new(AgentEventKind::AgentAuthenticated, "worker-1").with_ticket("CAB-100");
        let json = serde_json::to_string(&event).expect("serialize");
        assert!(json.contains("agent_authenticated"));
        assert!(json.contains("worker-1"));
        assert!(json.contains("CAB-100"));
    }

    #[test]
    fn test_event_serialization_skips_none() {
        let event = AgentEvent::new(AgentEventKind::BudgetChecked, "worker-1");
        let json = serde_json::to_string(&event).expect("serialize");
        assert!(!json.contains("ticket_id"));
        assert!(!json.contains("detail"));
    }

    #[test]
    fn test_event_kind_display() {
        assert_eq!(
            AgentEventKind::AgentAuthenticated.to_string(),
            "agent_authenticated"
        );
        assert_eq!(
            AgentEventKind::DispatchStarted.to_string(),
            "dispatch_started"
        );
        assert_eq!(
            AgentEventKind::DispatchCompleted.to_string(),
            "dispatch_completed"
        );
        assert_eq!(AgentEventKind::ClaimReserved.to_string(), "claim_reserved");
        assert_eq!(AgentEventKind::ClaimReleased.to_string(), "claim_released");
        assert_eq!(AgentEventKind::BudgetChecked.to_string(), "budget_checked");
        assert_eq!(
            AgentEventKind::SupervisionBlocked.to_string(),
            "supervision_blocked"
        );
    }

    // === AgentEventBuffer tests ===

    #[test]
    fn test_buffer_push_and_query() {
        let buf = AgentEventBuffer::new(10);
        buf.push(AgentEvent::new(AgentEventKind::DispatchStarted, "w1"));
        buf.push(AgentEvent::new(AgentEventKind::DispatchCompleted, "w1"));

        let events = buf.recent(10);
        assert_eq!(events.len(), 2);
        // Newest first
        assert_eq!(events[0].kind, AgentEventKind::DispatchCompleted);
        assert_eq!(events[1].kind, AgentEventKind::DispatchStarted);
    }

    #[test]
    fn test_buffer_eviction() {
        let buf = AgentEventBuffer::new(3);
        buf.push(AgentEvent::new(AgentEventKind::AgentAuthenticated, "w1"));
        buf.push(AgentEvent::new(AgentEventKind::DispatchStarted, "w1"));
        buf.push(AgentEvent::new(AgentEventKind::DispatchCompleted, "w1"));
        buf.push(AgentEvent::new(AgentEventKind::ClaimReserved, "w1"));

        assert_eq!(buf.len(), 3);
        let events = buf.recent(10);
        // Oldest (AgentAuthenticated) evicted
        assert_eq!(events[2].kind, AgentEventKind::DispatchStarted);
        assert_eq!(events[0].kind, AgentEventKind::ClaimReserved);
    }

    #[test]
    fn test_buffer_limit_cap() {
        let buf = AgentEventBuffer::new(1000);
        for i in 0..700 {
            buf.push(AgentEvent::new(
                AgentEventKind::DispatchStarted,
                &format!("w{}", i),
            ));
        }
        let events = buf.recent(999);
        assert_eq!(events.len(), 500); // capped at 500
    }

    #[test]
    fn test_buffer_empty() {
        let buf = AgentEventBuffer::default();
        assert!(buf.is_empty());
        assert_eq!(buf.len(), 0);
        let events = buf.recent(10);
        assert!(events.is_empty());
    }

    #[test]
    fn test_default_buffer_size() {
        let buf = AgentEventBuffer::default();
        assert_eq!(buf.max_size, 1000);
    }

    // === AgentMeteringEmitter tests ===

    #[test]
    fn test_emitter_buffers_without_kafka() {
        let buffer = Arc::new(AgentEventBuffer::default());
        let emitter =
            AgentMeteringEmitter::new("hegemon.agent_events".to_string(), None, buffer.clone());

        emitter.emit(AgentEvent::new(AgentEventKind::DispatchStarted, "w1"));
        assert_eq!(buffer.len(), 1);
    }

    #[test]
    fn test_emitter_buffers_with_noop_kafka() {
        use crate::metering::{MeteringProducer, MeteringProducerConfig};

        let config = MeteringProducerConfig {
            brokers: "localhost:9092".to_string(),
            metering_topic: "test.metering".to_string(),
            errors_topic: "test.errors".to_string(),
        };
        let producer = Arc::new(MeteringProducer::noop(config));
        let buffer = Arc::new(AgentEventBuffer::default());
        let emitter = AgentMeteringEmitter::new(
            "hegemon.agent_events".to_string(),
            Some(producer),
            buffer.clone(),
        );

        emitter.emit(
            AgentEvent::new(AgentEventKind::ClaimReserved, "w1")
                .with_ticket("CAB-1720")
                .with_detail("Phase 1"),
        );
        assert_eq!(buffer.len(), 1);

        let events = buffer.recent(1);
        assert_eq!(events[0].kind, AgentEventKind::ClaimReserved);
        assert_eq!(events[0].ticket_id.as_deref(), Some("CAB-1720"));
    }

    #[test]
    fn test_emitter_multiple_events() {
        let buffer = Arc::new(AgentEventBuffer::default());
        let emitter =
            AgentMeteringEmitter::new("hegemon.agent_events".to_string(), None, buffer.clone());

        emitter.emit(AgentEvent::new(AgentEventKind::AgentAuthenticated, "w1"));
        emitter.emit(AgentEvent::new(AgentEventKind::DispatchStarted, "w1"));
        emitter.emit(AgentEvent::new(AgentEventKind::BudgetChecked, "w1"));
        emitter.emit(AgentEvent::new(AgentEventKind::DispatchCompleted, "w1"));

        assert_eq!(buffer.len(), 4);
        let events = buffer.recent(4);
        assert_eq!(events[0].kind, AgentEventKind::DispatchCompleted);
        assert_eq!(events[3].kind, AgentEventKind::AgentAuthenticated);
    }

    #[test]
    fn test_emitter_buffer_ref() {
        let buffer = Arc::new(AgentEventBuffer::default());
        let emitter =
            AgentMeteringEmitter::new("hegemon.agent_events".to_string(), None, buffer.clone());
        assert!(Arc::ptr_eq(emitter.buffer(), &buffer));
    }
}
